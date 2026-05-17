import json

import pytest

from app.vision.courtvision_calibration_engine.coco_dataset import (
    COCODatasetValidationError,
    prepare_yolo_segmentation_dataset,
    validate_coco_segmentation_dataset,
)


def test_coco_segmentation_validation_reports_supported_dataset(tmp_path):
    dataset = make_coco_dataset(tmp_path)

    report = validate_coco_segmentation_dataset(dataset)

    assert report["ready"] is True
    assert report["available_splits"] == ["train", "val"]
    assert report["categories"] == ["court_line"]
    assert report["totals"]["images"] == 2
    assert report["segmentation_types"]["polygon"] == 2


def test_coco_segmentation_validation_rejects_missing_images(tmp_path):
    dataset = make_coco_dataset(tmp_path, create_images=False)

    with pytest.raises(COCODatasetValidationError) as exc:
        validate_coco_segmentation_dataset(dataset)

    assert exc.value.report["ready"] is False
    assert "image file(s) are missing" in " ".join(exc.value.report["errors"])


def test_prepare_yolo_segmentation_dataset_writes_labels_and_yaml(tmp_path):
    dataset = make_coco_dataset(tmp_path / "source")
    output = tmp_path / "converted"

    report = prepare_yolo_segmentation_dataset(dataset, output)

    assert report["dataset_yaml"].endswith("court-line-seg.yaml")
    assert (output / "court-line-seg.yaml").exists()
    assert (output / "labels" / "train" / "00000001.txt").exists()
    label = (output / "labels" / "train" / "00000001.txt").read_text(encoding="utf-8")
    assert label.startswith("0 ")
    assert "0.100000" in label


def make_coco_dataset(root, create_images=True):
    root.mkdir(parents=True, exist_ok=True)
    (root / "annotations").mkdir()
    for split, image_id in [("train", 1), ("val", 2)]:
        (root / split).mkdir()
        if create_images:
            (root / split / f"{split}.jpg").write_bytes(b"fake-jpeg")
        payload = {
            "images": [
                {
                    "id": image_id,
                    "file_name": f"{split}.jpg",
                    "width": 100,
                    "height": 100,
                }
            ],
            "categories": [{"id": 1, "name": "court_line"}],
            "annotations": [
                {
                    "id": image_id,
                    "image_id": image_id,
                    "category_id": 1,
                    "segmentation": [[10, 10, 90, 10, 90, 90, 10, 90]],
                    "area": 6400,
                    "bbox": [10, 10, 80, 80],
                    "iscrowd": 0,
                }
            ],
        }
        (root / "annotations" / f"instances_{split}.json").write_text(
            json.dumps(payload),
            encoding="utf-8",
        )
    return root
