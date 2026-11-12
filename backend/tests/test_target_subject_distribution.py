"""Exercise the actual source-distribution/wheel boundary without network or source fallback."""
from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import zipfile


def test_sdist_roundtrip_wheel_contains_usable_provider_contracts(tmp_path):
    backend = Path(__file__).resolve().parents[1]
    source = tmp_path / "source"
    source.mkdir()
    shutil.copyfile(backend / "pyproject.toml", source / "pyproject.toml")
    shutil.copyfile(backend / "README.md", source / "README.md")
    shutil.copytree(backend / "app", source / "app", ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    env["PIP_NO_INDEX"] = "1"
    dist = tmp_path / "dist"
    _build(source, dist, "--sdist", env)
    unpacked = tmp_path / "unpacked"
    with tarfile.open(next(dist.glob("*.tar.gz"))) as archive:
        archive.extractall(unpacked, filter="data")
    _build(next(unpacked.iterdir()), dist, "--wheel", env)
    installed = tmp_path / "installed"
    with zipfile.ZipFile(next(dist.glob("*.whl"))) as wheel:
        assert any("contract_data/v1/schemas/provider_request.schema.json" in name for name in wheel.namelist())
        wheel.extractall(installed)
    code = """
import json, pathlib, sys
sys.path.insert(0, sys.argv[1])
from app.vision.target_subject_provider import contracts
from app.vision.target_subject_provider.cli import main
assert pathlib.Path(contracts.__file__).is_relative_to(pathlib.Path(sys.argv[1]))
for name in ('provider_request','provider_result','provider_run_manifest'):
    fixture=json.loads((contracts.CONTRACT_ROOT/'fixtures'/f'{name}.example.json').read_text())
    contracts.validate_contract(name,fixture)
assert 'app.database' not in sys.modules
try:
    main(['--help'])
except SystemExit as exc:
    assert exc.code == 0
else:
    raise AssertionError('CLI help did not exit')
"""
    result = subprocess.run(
        [sys.executable, "-I", "-c", code, str(installed)], cwd=tmp_path, env=env,
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def _build(source, outdir, kind, env):
    result = subprocess.run(
        [sys.executable, "-m", "build", kind, "--no-isolation", "--outdir", str(outdir)],
        cwd=source, env=env, capture_output=True, text=True, timeout=90,
    )
    assert result.returncode == 0, result.stdout + result.stderr
