from __future__ import annotations

import json
from importlib.resources import files
from typing import Any

from jsonschema import Draft202012Validator


CONTRACT_ROOT = files(__package__).joinpath("contract_data", "v1")


def load_schema(name: str) -> dict[str, Any]:
    path = CONTRACT_ROOT / "schemas" / f"{name}.schema.json"
    return json.loads(path.read_text(encoding="utf-8"))


def validate_contract(name: str, payload: dict[str, Any]) -> None:
    Draft202012Validator(load_schema(name)).validate(payload)
