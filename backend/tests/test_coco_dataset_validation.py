import json
from pathlib import Path

import pytest

from app.vision.courtvision_calibration_engine.coco_dataset import (
    COCODatasetValidationError,
    prepare_yolo_segmentation_dataset,
    validate_coco_segmentation_dataset,
)


def test_coco_segmentation_validation_reports_supported_dataset(tmp_path):
    dataset = make_coco_dataset(tmp_path)

    report = validate_coco_segmentation_dataset(dataset, target_category="court_line")

    assert report["ready"] is True
    assert report["structural_ready"] is True
    assert report["target_ready"] is True
    assert report["available_splits"] == ["train", "val"]
    assert report["categories"] == ["court_line"]
    assert report["annotated_categories"] == ["court_line"]
    assert report["unused_categories"] == []
    assert report["category_usage"] == {"court_line": 2}
    assert report["totals"]["images"] == 2
    assert report["segmentation_types"]["polygon"] == 2


def test_coco_segmentation_validation_allows_pending_target_when_unspecified(tmp_path):
    dataset = make_coco_dataset(tmp_path)

    report = validate_coco_segmentation_dataset(dataset)

    assert report["ready"] is True
    assert report["structural_ready"] is True
    assert report["target_ready"] is None
    assert report["target_readiness"]["strategy"] == "unspecified"
    assert "target category or strategy is not specified" in " ".join(report["warnings"])


def test_coco_segmentation_validation_rejects_missing_images(tmp_path):
    dataset = make_coco_dataset(tmp_path, create_images=False)

    with pytest.raises(COCODatasetValidationError) as exc:
        validate_coco_segmentation_dataset(dataset)

    assert exc.value.report["ready"] is False
    assert exc.value.report["structural_ready"] is False
    assert "image file(s) are missing" in " ".join(exc.value.report["errors"])


def test_coco_segmentation_validation_reports_unused_categories(tmp_path):
    dataset = make_coco_dataset(
        tmp_path,
        categories=[{"id": 1, "name": "Court"}, {"id": 2, "name": "Court-Line"}],
        annotation_category_id=1,
    )

    report = validate_coco_segmentation_dataset(dataset, target_category="Court")

    assert report["ready"] is True
    assert report["category_usage"] == {"Court": 2, "Court-Line": 0}
    assert report["unused_categories"] == ["Court-Line"]
    assert report["target_readiness"]["unused_categories"] == ["Court-Line"]


def test_coco_segmentation_validation_rejects_zero_annotation_target_category(tmp_path):
    dataset = make_coco_dataset(
        tmp_path,
        categories=[{"id": 1, "name": "Court"}, {"id": 2, "name": "Court-Line"}],
        annotation_category_id=1,
    )

    with pytest.raises(COCODatasetValidationError) as exc:
        validate_coco_segmentation_dataset(dataset, target_category="Court-Line")

    report = exc.value.report
    assert report["ready"] is False
    assert report["structural_ready"] is True
    assert report["target_ready"] is False
    assert "target category 'Court-Line' has zero annotations" in " ".join(report["target_errors"])


def test_coco_segmentation_validation_preserves_structural_ready_on_target_mismatch(tmp_path):
    dataset = make_coco_dataset(
        tmp_path,
        categories=[{"id": 1, "name": "Court"}, {"id": 2, "name": "Court-Line"}],
        annotation_category_id=1,
    )

    report = validate_coco_segmentation_dataset(
        dataset,
        target_category="Court-Line",
        raise_on_error=False,
    )

    assert report["ready"] is False
    assert report["structural_ready"] is True
    assert report["target_ready"] is False
    assert report["target_readiness"]["annotated_categories"] == ["Court"]


def test_coco_segmentation_validation_accepts_merge_strategy_with_unused_categories(tmp_path):
    dataset = make_coco_dataset(
        tmp_path,
        categories=[{"id": 1, "name": "Court"}, {"id": 2, "name": "Court-Line"}],
        annotation_category_id=1,
    )

    report = validate_coco_segmentation_dataset(dataset, target_strategy="merge")

    assert report["ready"] is True
    assert report["target_ready"] is True
    assert report["target_readiness"]["strategy"] == "merge"
    assert report["target_readiness"]["annotated_categories"] == ["Court"]


def test_coco_segmentation_validation_reports_split_leakage_risk(tmp_path):
    dataset = make_coco_dataset(
        tmp_path,
        file_names={"train": "frames_0001_jpg.rf.abc123ef.jpg", "val": "frames_0001_jpg.rf.def456ab.jpg"},
    )

    report = validate_coco_segmentation_dataset(dataset, target_category="court_line")

    assert report["ready"] is True
    assert report["split_leakage"]["risk"] is True
    assert report["split_leakage"]["token_count"] == 1
    assert report["split_leakage"]["examples"][0]["source_token"] == "frames_0001"


def test_coco_segmentation_validation_writes_acceptance_summary(tmp_path):
    dataset = make_coco_dataset(tmp_path / "source")
    evidence = tmp_path / "evidence"

    report = validate_coco_segmentation_dataset(
        dataset,
        target_category="court_line",
        evidence_output=evidence,
    )

    summary_path = evidence / "summary.json"
    assert report["acceptance"]["summary_path"] == str(summary_path)
    assert summary_path.exists()
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    assert summary["structural_ready"] is True
    assert summary["target_ready"] is True


def test_coco_segmentation_validation_writes_annotation_previews(tmp_path):
    pytest.importorskip("cv2")
    dataset = make_coco_dataset(tmp_path / "source", image_kind="opencv")
    evidence = tmp_path / "evidence"

    report = validate_coco_segmentation_dataset(
        dataset,
        target_category="court_line",
        evidence_output=evidence,
        preview_samples_per_split=1,
    )

    previews = report["acceptance"]["previews"]
    assert len(previews) == 2
    assert all((evidence / "previews" / Path(item["preview"]).name).exists() for item in previews)


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


def make_coco_dataset(
    root,
    create_images=True,
    categories=None,
    annotation_category_id=1,
    file_names=None,
    image_kind="fake",
):
    root.mkdir(parents=True, exist_ok=True)
    (root / "annotations").mkdir()
    categories = categories or [{"id": 1, "name": "court_line"}]
    file_names = file_names or {}
    for split, image_id in [("train", 1), ("val", 2)]:
        (root / split).mkdir()
        file_name = file_names.get(split, f"{split}.jpg")
        if create_images:
            image_path = root / split / file_name
            if image_kind == "opencv":
                cv2 = pytest.importorskip("cv2")
                import numpy as np

                cv2.imwrite(str(image_path), np.full((100, 100, 3), 80, dtype=np.uint8))
            else:
                image_path.write_bytes(b"fake-jpeg")
        payload = {
            "images": [
                {
                    "id": image_id,
                    "file_name": file_name,
                    "width": 100,
                    "height": 100,
                }
            ],
            "categories": categories,
            "annotations": [
                {
                    "id": image_id,
                    "image_id": image_id,
                    "category_id": annotation_category_id,
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
