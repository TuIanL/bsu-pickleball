"""Path-aware SQLite connection settings shared by ORM and control-plane stores."""

from __future__ import annotations

import plistlib
import subprocess
import sys
from pathlib import Path
from typing import Any


def _macos_volume_is_internal(path: Path) -> bool | None:
    try:
        filesystem = subprocess.run(
            ["df", "-P", str(path)],
            check=False,
            capture_output=True,
            text=True,
            timeout=3,
        )
        lines = filesystem.stdout.splitlines()
        if filesystem.returncode != 0 or len(lines) < 2:
            return None
        mountpoint = lines[-1].split()[-1]
        result = subprocess.run(
            ["diskutil", "info", "-plist", mountpoint],
            check=False,
            capture_output=True,
            timeout=3,
        )
        if result.returncode != 0:
            return None
        info: Any = plistlib.loads(result.stdout)
    except (OSError, subprocess.SubprocessError, plistlib.InvalidFileException):
        return None
    if not isinstance(info, dict):
        return None
    internal = info.get("Internal")
    if isinstance(internal, bool):
        return internal
    location = info.get("DeviceLocation")
    if isinstance(location, str) and location.lower() in {"internal", "external"}:
        return location.lower() == "internal"
    removable = info.get("RemovableMedia")
    if isinstance(removable, bool):
        return not removable
    return None


def _linux_mount_is_fixed_local(path: Path) -> bool | None:
    """Return whether the containing Linux block device is confirmed non-removable."""
    mount_info = Path("/proc/self/mountinfo")
    try:
        lines = mount_info.read_text(encoding="utf-8").splitlines()
    except OSError:
        return None

    resolved = path.resolve(strict=False)
    best: tuple[int, str, str] | None = None
    for line in lines:
        try:
            left, right = line.split(" - ", 1)
            fields = left.split()
            mountpoint = Path(fields[4].replace("\\040", " ")).resolve(strict=False)
            fstype, source, _super_options = right.split(maxsplit=2)
            resolved.relative_to(mountpoint)
        except (ValueError, IndexError):
            continue
        candidate = (len(str(mountpoint)), fstype, source)
        if best is None or candidate[0] > best[0]:
            best = candidate
    if best is None:
        return None

    _, fstype, source = best
    if fstype in {"nfs", "nfs4", "cifs", "smb3", "sshfs", "9p", "fuse.sshfs"}:
        return False
    if not source.startswith("/dev/"):
        return None

    try:
        sys_device = (Path("/sys/class/block") / Path(source).name).resolve(strict=True)
    except OSError:
        return None
    # USB and FireWire transports are removable/external even when the device itself
    # reports removable=0 (common for external SSD enclosures).
    if any(token in str(sys_device).lower() for token in ("/usb", "/firewire", "/ieee1394")):
        return False
    for candidate in (sys_device, *sys_device.parents):
        try:
            removable = (candidate / "removable").read_text(encoding="utf-8").strip()
        except OSError:
            continue
        return removable == "0"
    return None


def is_confirmed_local_filesystem(path: Path) -> bool:
    """Conservatively identify fixed local storage; unknown mounts stay off WAL."""
    resolved = path.expanduser().resolve(strict=False)
    probe_path = resolved if resolved.exists() else resolved.parent
    if not probe_path.exists():
        # A missing parent may be an offline mount point. Do not create a database
        # there or infer its policy from a different ancestor's filesystem.
        return False
    if sys.platform == "darwin":
        return _macos_volume_is_internal(probe_path) is True
    if sys.platform.startswith("linux"):
        return _linux_mount_is_fixed_local(probe_path) is True
    if sys.platform == "win32":
        try:
            import ctypes

            drive = str(resolved.anchor or resolved)[:3]
            drive_type = ctypes.windll.kernel32.GetDriveTypeW(drive)
            return drive_type == 3  # DRIVE_FIXED
        except (AttributeError, OSError):
            return False
    return False


def sqlite_journal_mode(path: Path, *companion_paths: Path) -> str:
    """Use WAL only when every related database is on confirmed fixed local storage.

    The main database and analysis control plane share one policy. If either path is
    on an external or unknown volume, both use rollback journaling.
    """
    return "WAL" if all(is_confirmed_local_filesystem(item) for item in (path, *companion_paths)) else "DELETE"


def apply_sqlite_pragmas(connection, path: Path, *, journal_mode: str | None = None) -> None:
    """Apply the shared connection policy to sqlite3 or SQLAlchemy DB-API handles."""
    cursor = connection.cursor()
    try:
        cursor.execute("PRAGMA busy_timeout = 30000")
        cursor.execute(f"PRAGMA journal_mode = {journal_mode or sqlite_journal_mode(path)}")
        cursor.execute("PRAGMA synchronous = NORMAL")
    finally:
        cursor.close()
