"""Preserve OpenCV image I/O semantics for Unicode Windows filenames."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any


def read_image(cv2: Any, filename: str | Path, flags: int | None = None):
    path = str(filename)
    if os.name != "nt" or path.isascii():
        return cv2.imread(path) if flags is None else cv2.imread(path, flags)
    import numpy as np

    try:
        contents = Path(filename).read_bytes()
    except OSError:
        return None
    if not contents:
        return None
    return cv2.imdecode(np.frombuffer(contents, dtype=np.uint8), cv2.IMREAD_COLOR if flags is None else flags)


def write_image(cv2: Any, filename: str | Path, image: Any, params: list[int] | None = None) -> bool:
    path = str(filename)
    if os.name != "nt" or path.isascii():
        return bool(cv2.imwrite(path, image) if params is None else cv2.imwrite(path, image, params))
    ok, encoded = cv2.imencode(Path(filename).suffix, image, [] if params is None else params)
    if not ok:
        return False
    try:
        Path(filename).write_bytes(encoded.tobytes())
    except OSError:
        return False
    return True
