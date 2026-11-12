import copy
import hashlib
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, ValidationError
from app.vision.target_subject_provider.contracts import CONTRACT_ROOT as PACKAGED_ROOT


CONTRACT_ROOT = Path(__file__).resolve().parents[1] / "contracts" / "target_subject" / "v1"
SCHEMAS = CONTRACT_ROOT / "schemas"
FIXTURES = CONTRACT_ROOT / "fixtures"
CONTRACT_NAMES = ("provider_request", "provider_result", "provider_run_manifest")


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_vendored_contract_bundle_hashes_match_manifest():
    manifest = _load(CONTRACT_ROOT / "contract_bundle.sha256.json")

    for logical_path, expected in manifest["files"].items():
        actual = hashlib.sha256((CONTRACT_ROOT / logical_path).read_bytes()).hexdigest()
        assert actual == expected


@pytest.mark.parametrize("name", CONTRACT_NAMES)
def test_vendored_example_validates_without_dataset_runtime(name: str):
    schema = _load(SCHEMAS / f"{name}.schema.json")
    fixture = _load(FIXTURES / f"{name}.example.json")

    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(fixture)


def test_provider_request_rejects_label_or_protocol_inputs():
    schema = _load(SCHEMAS / "provider_request.schema.json")
    fixture = _load(FIXTURES / "provider_request.example.json")

    for forbidden_field, value in (
        ("stroke_type", "serve"),
        ("profile", "baseline4"),
        ("nested_loso_role", "outer_test"),
    ):
        payload = copy.deepcopy(fixture)
        payload[forbidden_field] = value
        with pytest.raises(ValidationError):
            Draft202012Validator(schema).validate(payload)


def test_provider_result_keeps_non_top_one_candidates():
    fixture = _load(FIXTURES / "provider_result.example.json")

    assert [candidate["rank"] for candidate in fixture["candidates"]] == [1, 2]
    assert len(fixture["candidates"]) > 1


def test_packaged_contract_mirror_matches_public_bundle():
    public_files = {str(p.relative_to(CONTRACT_ROOT)) for p in CONTRACT_ROOT.rglob("*.json")}
    packaged_files = {str(p.relative_to(PACKAGED_ROOT)) for p in PACKAGED_ROOT.rglob("*.json")}
    assert packaged_files == public_files
    for name in public_files:
        assert (PACKAGED_ROOT / name).read_bytes() == (CONTRACT_ROOT / name).read_bytes()
