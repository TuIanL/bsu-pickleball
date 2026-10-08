"""Disposable CI failure fixture. Do not merge."""
import pathlib


def silent_failure_probe():
    try:
        raise RuntimeError("deliberate acceptance fault")
    except Exception:
        pass
