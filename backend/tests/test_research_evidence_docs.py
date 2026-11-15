"""Keep docs/research-evidence-contract.md in sync with the contract.

The document is treated as a checked artifact rather than prose: every fixture it
lists must exist, every path it cites must resolve, and every field name it
mentions must appear in the schema.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DOC_PATH = REPO_ROOT / "docs" / "research-evidence-contract.md"
CONTRACT_ROOT = (
    REPO_ROOT / "backend" / "contracts" / "research_evidence" / "v1"
)
FIXTURES = CONTRACT_ROOT / "fixtures"
SCHEMA_PATH = CONTRACT_ROOT / "schemas" / "research_evidence_manifest.schema.json"

_FIXTURE_PATTERN = re.compile(
    r"(?<![a-z_])(?:manifest|invalid)\.[a-z0-9\-]+(?:\.example)?\.json"
)
_BACKTICK_PATTERN = re.compile(r"`([^`]+)`")
_SNAKE_CASE = re.compile(r"^[a-z][a-z0-9_]+$")
# Field names are declared in the first column of the field tables only; that
# keeps helper function names out of the schema comparison.
_TABLE_FIELD = re.compile(r"^\|\s*`([^`]+)`\s*\|", re.MULTILINE)


def _doc_text() -> str:
    return DOC_PATH.read_text(encoding="utf-8")


def test_contract_doc_exists():
    assert DOC_PATH.is_file(), f"缺少契约文档: {DOC_PATH.relative_to(REPO_ROOT)}"
    assert len(_doc_text()) > 1500, "契约文档内容过短，疑似被截断"


def test_documented_fixtures_match_the_fixture_directory():
    documented = set(_FIXTURE_PATTERN.findall(_doc_text()))
    on_disk = {path.name for path in FIXTURES.glob("*.json")}

    assert documented, "文档必须列出 fixtures 覆盖矩阵"
    assert documented == on_disk, (
        f"文档与 fixtures 目录不一致: 文档缺 {sorted(on_disk - documented)}, "
        f"文档多出 {sorted(documented - on_disk)}"
    )


def test_documented_code_paths_resolve():
    text = _doc_text()
    candidates = [
        token
        for token in _BACKTICK_PATTERN.findall(text)
        if "/" in token and Path(token).suffix in {".py", ".json", ".md"}
    ]
    assert candidates, "文档必须引用实现文件路径"

    missing = [
        token
        for token in candidates
        if "{" not in token and not (REPO_ROOT / token).exists()
    ]
    assert not missing, f"文档引用了不存在的路径: {missing}"


def test_documented_field_names_exist_in_the_schema():
    schema_text = SCHEMA_PATH.read_text(encoding="utf-8")
    fields = set()
    for raw in _TABLE_FIELD.findall(_doc_text()):
        if raw.endswith(".json"):
            continue
        base = raw.split(".")[0].replace("[]", "").strip()
        if _SNAKE_CASE.fullmatch(base):
            fields.add(base)

    assert fields, "文档必须用表格声明字段名"
    missing = sorted(token for token in fields if f'"{token}"' not in schema_text)
    assert not missing, f"文档提到的字段不在 Schema 中: {missing}"


def test_documented_enum_values_exist_in_the_schema():
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    schema_text = json.dumps(schema, ensure_ascii=False)

    for value in ("real", "fixture", "unknown", "complete", "partial"):
        assert f'"{value}"' in schema_text, f"文档使用的枚举值 {value} 不在 Schema 中"


def test_documented_rules_match_implementation_defaults():
    """Guard the two rules that are easy to weaken by accident."""
    from app.research_evidence.classification import (
        classify_usage_kind,
        extension_matches_container,
    )
    from app.research_evidence.locations import LOCATIONS_SCHEMA_VERSION

    # 无任何依据时不得默认 real。
    evidence = classify_usage_kind(declared=None, root_policy=None, container="mp4")
    assert evidence.usage_kind == "unknown"

    # 扩展名不能替代容器判断。
    assert extension_matches_container(".mp4", "avi") is False

    # 文档声明的本地映射版本必须与实现一致。
    assert LOCATIONS_SCHEMA_VERSION in _doc_text()
