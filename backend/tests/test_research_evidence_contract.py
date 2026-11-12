"""科研证据清单契约测试。

覆盖 research_evidence_manifest.v1 的表达能力：未知摘要、历史缺项、partial
与算法质量 fail 必须可分别表达且互不混淆，反例必须被 Schema 拒绝。

本测试只验证契约形态，不校验真实资产；真实核验由 CLI 与后续任务承担。
"""

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, ValidationError

CONTRACT_ROOT = Path(__file__).resolve().parents[1] / "contracts" / "research_evidence" / "v1"
SCHEMA_PATH = CONTRACT_ROOT / "schemas" / "research_evidence_manifest.schema.json"
FIXTURES = CONTRACT_ROOT / "fixtures"

# 每个反例必须命中的错误路径前缀，防止 Schema 退化后错误位置漂移。
INVALID_CASES = (
    ("invalid.known-digest-without-sha.json", ("assets", 0, "digest")),
    ("invalid.unknown-digest-with-sha.json", ("assets", 0, "digest", "sha256")),
    ("invalid.absolute-path-locator.json", ("assets", 0, "locator")),
    ("invalid.complete-with-blocking-limitation.json", ("limitations", 0, "block_completeness")),
    ("invalid.unknown-baseline.json", ("baseline", "selected_revision", "status")),
    ("invalid.complete-required-unverified.json", ("assets", 0, "verification")),
)

VALID_CASES = (
    "manifest.complete.example.json",
    "manifest.partial-windows-missing.example.json",
    "manifest.historical-gap.example.json",
    "manifest.fixture-present.example.json",
)


def _load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def _schema() -> dict:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def _validator() -> Draft202012Validator:
    schema = _schema()
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def test_schema_is_valid_draft_2020_12():
    Draft202012Validator.check_schema(_schema())


@pytest.mark.parametrize("name", VALID_CASES)
def test_positive_fixtures_validate(name: str):
    _validator().validate(_load(name))


@pytest.mark.parametrize(("name", "expected_path"), INVALID_CASES)
def test_negative_fixtures_are_rejected_at_expected_path(name: str, expected_path: tuple):
    with pytest.raises(ValidationError) as excinfo:
        _validator().validate(_load(name))

    actual = tuple(excinfo.value.absolute_path)
    assert actual[: len(expected_path)] == expected_path, f"{name} 报错位置漂移: {actual}"


def test_unknown_digest_cannot_carry_a_value():
    """未知摘要必须显式 sha256=null + reason，不能留占位值冒充已核验。

    历史缺项有两种形态：代码版本不可知（revision unknown）与内容摘要不可知
    （digest unknown）。这里跨全部正例收集，确保两种形态都被真实覆盖。
    """
    collected = []
    for name in VALID_CASES:
        manifest = _load(name)
        for asset in manifest["assets"]:
            if asset["digest"]["status"] == "unknown":
                collected.append((name, asset))

    assert len(collected) >= 2, "正例集合必须覆盖多个未知摘要形态"
    for name, asset in collected:
        assert asset["digest"]["sha256"] is None, f"{name}: unknown 摘要不得携带值"
        assert asset["digest"]["reason"], f"{name}: unknown 摘要必须说明原因"


def test_history_gap_keeps_revision_unknown_instead_of_backfilling():
    """历史外部产物缺版本时保持 unknown，禁止用当前 HEAD 回填。"""
    manifest = _load("manifest.historical-gap.example.json")
    run = manifest["run_refs"][0]

    assert run["origin"] == "external"
    assert run["code_revision"]["status"] == "unknown"
    assert run["code_revision"]["commit"] is None
    assert run["algorithm_verdict"]["recorded_source"] == "original_job"


def test_availability_and_verification_are_orthogonal():
    """不可达是 availability 结论，不得写成摘要不符。"""
    manifest = _load("manifest.partial-windows-missing.example.json")
    unreachable = [a for a in manifest["assets"] if a["availability"] == "unreachable"]

    assert unreachable, "partial fixture 必须体现不可达资产"
    for asset in unreachable:
        assert asset["verification"] in {"not_checked", "unknown"}
        assert asset["verification"] != "mismatch"


def test_complete_package_may_still_carry_algorithm_failure():
    """索引完整与算法质量正交：complete 不表示质量通过。"""
    manifest = _load("manifest.complete.example.json")

    assert manifest["completeness"] == "complete"
    assert manifest["run_refs"][0]["algorithm_verdict"]["result"] == "fail"
    assert manifest["run_refs"][0]["algorithm_verdict"]["recorded_source"] == "quality_report"


def test_partial_package_requires_a_blocking_limitation():
    manifest = _load("manifest.partial-windows-missing.example.json")

    assert manifest["completeness"] == "partial"
    blocking = [l for l in manifest["limitations"] if l["block_completeness"]]
    assert blocking, "partial 包必须说明是什么阻断完整声明"
    assert any(l.get("notion_task") == "PB-004" for l in blocking)


def test_optional_asset_does_not_block_completeness():
    """complete 判定只聚合 required 资产；optional 未核验不应导致 partial。"""
    manifest = _load("manifest.complete.example.json")
    optional = [a for a in manifest["assets"] if a["requirement"] == "optional"]

    assert optional, "complete fixture 必须包含 optional 资产以验证聚合口径"
    assert all(a["verification"] != "verified" for a in optional)
    assert manifest["completeness"] == "complete"


def test_fixture_assets_are_distinguishable_from_real_assets():
    manifest = _load("manifest.fixture-present.example.json")
    kinds = {a["usage_kind"] for a in manifest["assets"]}

    assert "fixture" in kinds and "real" in kinds
    fixture_assets = [a for a in manifest["assets"] if a["usage_kind"] == "fixture"]
    for asset in fixture_assets:
        assert asset["provenance"]["note"], "合成夹具必须说明来源，避免被当作正式素材"


def test_locator_never_contains_absolute_path():
    """路径不是 ID：可分享 manifest 不允许出现本机绝对路径。"""
    for name in VALID_CASES:
        manifest = _load(name)
        for asset in manifest["assets"]:
            locator = asset["locator"]
            assert not locator.startswith("/"), f"{name} 泄露绝对路径: {locator}"
            assert "asset://" in locator
