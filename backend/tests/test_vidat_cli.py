import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_vidat_clis_keep_supported_commands():
    for script in ("export_to_vidat.py", "import_from_vidat.py", "vidat_workbench.py"):
        result = subprocess.run([sys.executable, str(ROOT / "scripts" / script), "--help"], capture_output=True, text=True)
        assert result.returncode == 0
    result = subprocess.run([sys.executable, str(ROOT / "scripts" / "import_from_vidat.py"),
        "--package", "vap_test", "--apply"], capture_output=True, text=True)
    assert result.returncode != 0
    assert "--confirmation-token" in result.stderr
