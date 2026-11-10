from pathlib import Path

import numpy as np
import pytest

from app.vision.image_io import read_image, write_image

cv2 = pytest.importorskip("cv2")


def test_image_round_trip_in_chinese_directory(tmp_path: Path):
    directory = tmp_path / "比赛标定"
    directory.mkdir()
    path = directory / "预览.png"
    image = np.arange(90, dtype=np.uint8).reshape(5, 6, 3)
    assert write_image(cv2, path, image)
    restored = read_image(cv2, path)
    assert restored is not None
    np.testing.assert_array_equal(restored, image)


def test_missing_image_in_chinese_directory_returns_none(tmp_path: Path):
    assert read_image(cv2, tmp_path / "不存在.png") is None
