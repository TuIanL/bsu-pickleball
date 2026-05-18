from __future__ import annotations

import json
import os
import re
import shutil
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Sequence


DEFAULT_SPLITS = ("train", "val", "test")
REQUIRED_SPLITS = ("train", "val")
SPLIT_ALIASES = {
    "train": ("train",),
    "val": ("val", "valid", "validation"),
    "valid": ("valid", "val", "validation"),
    "test": ("test",),
}


class COCODatasetValidationError(ValueError):
    def __init__(self, message: str, report: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.report = report or {}


class COCODatasetConversionError(ValueError):
    pass


def validate_coco_segmentation_dataset(
    dataset_root: str | Path,
    splits: Sequence[str] | None = None,
    required_splits: Sequence[str] = REQUIRED_SPLITS,
    raise_on_error: bool = True,
    target_category: str | None = None,
    target_strategy: str | None = None,
    evidence_output: str | Path | None = None,
    preview_samples_per_split: int = 0,
) -> dict[str, Any]:
    """Validate a local COCO segmentation dataset for court-line training."""

    root = Path(dataset_root).expanduser()
    requested_splits = tuple(splits or DEFAULT_SPLITS)
    split_reports: list[dict[str, Any]] = []
    errors: list[str] = []

    for split in requested_splits:
        annotation_path = _find_annotation_path(root, split)
        if annotation_path is None:
            if split in required_splits:
                errors.append(f"{split}: missing annotation JSON")
            continue

        split_report = _validate_split(root, split, annotation_path)
        split_reports.append(split_report)
        errors.extend(f"{split}: {error}" for error in split_report["errors"])

    available_splits = {item["split"] for item in split_reports}
    for split in required_splits:
        if split not in available_splits:
            errors.append(f"{split}: required split is not ready")

    totals = {
        "images": sum(item["image_count"] for item in split_reports),
        "annotations": sum(item["annotation_count"] for item in split_reports),
        "missing_images": sum(item["missing_image_count"] for item in split_reports),
    }
    categories = sorted({name for item in split_reports for name in item["categories"]})
    category_usage = {name: 0 for name in categories}
    for item in split_reports:
        for category, count in item["category_usage"].items():
            category_usage[category] = category_usage.get(category, 0) + int(count)
    category_usage = dict(sorted(category_usage.items()))
    annotated_categories = sorted(category for category, count in category_usage.items() if count > 0)
    unused_categories = sorted(category for category, count in category_usage.items() if count == 0)
    segmentation_types = Counter()
    for item in split_reports:
        segmentation_types.update(item["segmentation_types"])
    structural_ready = not errors
    target_readiness = _evaluate_target_readiness(
        category_usage=category_usage,
        target_category=target_category,
        target_strategy=target_strategy,
    )
    leakage_report = _detect_split_leakage(split_reports)
    warnings = list(target_readiness["warnings"])
    if leakage_report["risk"]:
        warnings.append(
            f"{leakage_report['token_count']} likely source token(s) appear in multiple dataset splits"
        )

    public_splits = [_public_split_report(item) for item in split_reports]
    report = {
        "dataset_root": str(root),
        "ready": structural_ready and target_readiness["ready"] is not False,
        "structural_ready": structural_ready,
        "target_ready": target_readiness["ready"],
        "target_readiness": target_readiness,
        "required_splits": list(required_splits),
        "available_splits": sorted(available_splits),
        "categories": categories,
        "annotated_categories": annotated_categories,
        "unused_categories": unused_categories,
        "category_usage": category_usage,
        "segmentation_types": dict(segmentation_types),
        "split_leakage": leakage_report,
        "totals": totals,
        "splits": public_splits,
        "errors": errors,
        "target_errors": target_readiness["errors"],
        "warnings": warnings,
    }

    if evidence_output is not None:
        report["acceptance"] = _write_acceptance_evidence(
            root=root,
            report=report,
            output_root=Path(evidence_output).expanduser(),
            preview_samples_per_split=preview_samples_per_split,
        )

    if not report["ready"] and raise_on_error:
        raise COCODatasetValidationError("COCO segmentation dataset is not ready", report=report)

    return report


def prepare_yolo_segmentation_dataset(
    dataset_root: str | Path,
    output_root: str | Path,
    class_name: str = "court_line",
    splits: Sequence[str] | None = None,
) -> dict[str, Any]:
    """Convert polygon COCO segmentation annotations into YOLO segment labels.

    All COCO categories are mapped to one class by default because the MVP court
    calibration model only needs a court-line mask.
    """

    root = Path(dataset_root).expanduser()
    output = Path(output_root).expanduser()
    report = validate_coco_segmentation_dataset(root, splits=splits)
    converted_splits: list[str] = []

    for split_report in report["splits"]:
        split = split_report["split"]
        annotation_path = Path(split_report["annotation_path"])
        payload = _read_json(annotation_path)
        images = {int(image["id"]): image for image in payload.get("images", [])}
        annotations_by_image: dict[int, list[dict[str, Any]]] = defaultdict(list)
        for annotation in payload.get("annotations", []):
            annotations_by_image[int(annotation.get("image_id", -1))].append(annotation)

        image_output_dir = output / "images" / split
        label_output_dir = output / "labels" / split
        image_output_dir.mkdir(parents=True, exist_ok=True)
        label_output_dir.mkdir(parents=True, exist_ok=True)

        for image_id, image in images.items():
            source_path = _resolve_image_path(root, split, str(image.get("file_name", "")))
            if source_path is None:
                continue

            suffix = Path(str(image.get("file_name", ""))).suffix or source_path.suffix
            target_stem = f"{image_id:08d}"
            target_image = image_output_dir / f"{target_stem}{suffix.lower()}"
            _link_or_copy(source_path, target_image)

            rows: list[str] = []
            width = float(image.get("width") or 0)
            height = float(image.get("height") or 0)
            if width <= 0 or height <= 0:
                raise COCODatasetConversionError(f"{split}: image {image_id} is missing width/height")

            for annotation in annotations_by_image.get(image_id, []):
                segmentation = annotation.get("segmentation")
                if isinstance(segmentation, dict):
                    raise COCODatasetConversionError(
                        f"{split}: image {image_id} uses RLE segmentation; convert to polygons before YOLO training"
                    )
                if not isinstance(segmentation, list):
                    continue
                for polygon in segmentation:
                    normalized = _normalize_polygon(polygon, width=width, height=height)
                    if normalized:
                        rows.append("0 " + " ".join(f"{value:.6f}" for value in normalized))

            (label_output_dir / f"{target_stem}.txt").write_text("\n".join(rows), encoding="utf-8")

        converted_splits.append(split)

    dataset_yaml = output / "court-line-seg.yaml"
    yaml_lines = [
        f"path: {output.resolve()}",
        "train: images/train",
        "val: images/val",
    ]
    if "test" in converted_splits:
        yaml_lines.append("test: images/test")
    yaml_lines.extend(["names:", f"  0: {class_name}"])
    dataset_yaml.write_text("\n".join(yaml_lines) + "\n", encoding="utf-8")

    return {
        "dataset_yaml": str(dataset_yaml),
        "output_root": str(output),
        "converted_splits": converted_splits,
        "class_name": class_name,
        "validation": report,
    }


def _evaluate_target_readiness(
    category_usage: dict[str, int],
    target_category: str | None,
    target_strategy: str | None,
) -> dict[str, Any]:
    strategy = (target_strategy or ("category" if target_category else "unspecified")).strip().lower()
    errors: list[str] = []
    warnings: list[str] = []
    annotated_categories = sorted(category for category, count in category_usage.items() if count > 0)
    unused_categories = sorted(category for category, count in category_usage.items() if count == 0)

    if strategy in {"merge", "one-class", "one_class", "all"}:
        if not annotated_categories:
            errors.append("target strategy merges all categories, but no annotated categories are present")
        elif unused_categories:
            warnings.append(
                "target strategy merges annotated categories; unused categories are ignored: "
                + ", ".join(unused_categories)
            )
        return {
            "ready": not errors,
            "strategy": "merge",
            "target_category": target_category,
            "annotated_categories": annotated_categories,
            "unused_categories": unused_categories,
            "errors": errors,
            "warnings": warnings,
        }

    if strategy not in {"unspecified", "category"}:
        errors.append(f"unsupported target strategy: {target_strategy}")

    if strategy == "unspecified":
        warnings.append("target category or strategy is not specified; target readiness is pending")
        return {
            "ready": None,
            "strategy": "unspecified",
            "target_category": None,
            "annotated_categories": annotated_categories,
            "unused_categories": unused_categories,
            "errors": errors,
            "warnings": warnings,
        }

    if not target_category:
        errors.append("target strategy 'category' requires a target category")
    elif target_category not in category_usage:
        errors.append(f"target category '{target_category}' is not present in COCO categories")
    elif category_usage[target_category] == 0:
        errors.append(f"target category '{target_category}' has zero annotations")
    elif any(category != target_category for category in annotated_categories):
        errors.append(
            f"annotations are present outside target category '{target_category}': "
            + ", ".join(category for category in annotated_categories if category != target_category)
        )

    if target_category and target_category in unused_categories:
        warnings.append(f"target category '{target_category}' is listed but unused")
    if unused_categories:
        warnings.append("unused categories: " + ", ".join(unused_categories))

    return {
        "ready": not errors,
        "strategy": "category",
        "target_category": target_category,
        "annotated_categories": annotated_categories,
        "unused_categories": unused_categories,
        "errors": errors,
        "warnings": warnings,
    }


def _detect_split_leakage(split_reports: Sequence[dict[str, Any]], max_examples: int = 20) -> dict[str, Any]:
    splits_by_token: dict[str, dict[str, list[str]]] = defaultdict(dict)
    for split_report in split_reports:
        split = str(split_report["split"])
        for token, examples in split_report.get("_source_tokens", {}).items():
            splits_by_token[token][split] = examples

    risky_tokens = {
        token: split_examples
        for token, split_examples in splits_by_token.items()
        if len(split_examples) > 1
    }
    examples = [
        {
            "source_token": token,
            "splits": sorted(split_examples),
            "examples": {
                split: values[:2]
                for split, values in sorted(split_examples.items())
            },
        }
        for token, split_examples in sorted(risky_tokens.items())
    ][:max_examples]

    return {
        "risk": bool(risky_tokens),
        "token_count": len(risky_tokens),
        "examples": examples,
    }


def _write_acceptance_evidence(
    root: Path,
    report: dict[str, Any],
    output_root: Path,
    preview_samples_per_split: int,
) -> dict[str, Any]:
    output_root.mkdir(parents=True, exist_ok=True)
    summary_path = output_root / "summary.json"
    preview_dir = output_root / "previews"
    previews: list[dict[str, str]] = []

    if preview_samples_per_split > 0:
        preview_dir.mkdir(parents=True, exist_ok=True)
        previews = _write_annotation_previews(
            root=root,
            split_reports=report["splits"],
            output_root=preview_dir,
            samples_per_split=preview_samples_per_split,
        )

    acceptance = {
        "summary_path": str(summary_path),
        "preview_dir": str(preview_dir) if previews else None,
        "previews": previews,
    }
    summary_payload = dict(report)
    summary_payload["acceptance"] = acceptance
    summary_path.write_text(json.dumps(summary_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return acceptance


def _write_annotation_previews(
    root: Path,
    split_reports: Sequence[dict[str, Any]],
    output_root: Path,
    samples_per_split: int,
) -> list[dict[str, str]]:
    try:
        import cv2  # type: ignore
        import numpy as np
    except ImportError:
        return []

    previews: list[dict[str, str]] = []
    for split_report in split_reports:
        split = str(split_report["split"])
        annotation_path = Path(str(split_report["annotation_path"]))
        payload = _read_json(annotation_path)
        images = [image for image in payload.get("images", []) if isinstance(image, dict)]
        annotations_by_image: dict[int, list[dict[str, Any]]] = defaultdict(list)
        for annotation in payload.get("annotations", []):
            if isinstance(annotation, dict) and annotation.get("image_id") is not None:
                annotations_by_image[int(annotation["image_id"])].append(annotation)

        written = 0
        for image in images:
            if written >= samples_per_split:
                break
            image_id = image.get("id")
            if image_id is None:
                continue
            source_path = _resolve_image_path(root, split, str(image.get("file_name", "")))
            if source_path is None:
                continue
            frame = cv2.imread(str(source_path))
            if frame is None:
                continue
            overlay = frame.copy()
            for annotation in annotations_by_image.get(int(image_id), []):
                _draw_annotation(overlay, annotation, cv2=cv2, np=np)
            output = cv2.addWeighted(overlay, 0.55, frame, 0.45, 0)
            output_path = output_root / f"{split}-{written + 1:02d}-{Path(str(image.get('file_name'))).stem}.jpg"
            if cv2.imwrite(str(output_path), output):
                previews.append(
                    {
                        "split": split,
                        "image_id": str(image_id),
                        "source": str(source_path),
                        "preview": str(output_path),
                    }
                )
                written += 1
    return previews


def _draw_annotation(frame: Any, annotation: dict[str, Any], cv2: Any, np: Any) -> None:
    segmentation = annotation.get("segmentation")
    color = (30, 220, 255)
    if not isinstance(segmentation, list):
        return
    for polygon in segmentation:
        values = _coerce_numeric_list(polygon)
        if values is None or len(values) < 6 or len(values) % 2 != 0:
            continue
        points = np.asarray(values, dtype=np.float32).reshape((-1, 2)).round().astype(np.int32)
        cv2.fillPoly(frame, [points], color)
        cv2.polylines(frame, [points], isClosed=True, color=(20, 120, 255), thickness=2)


def _public_split_report(split_report: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in split_report.items() if not key.startswith("_")}


def _find_annotation_path(root: Path, split: str) -> Path | None:
    candidates = []
    for alias in _split_aliases(split):
        candidates.extend(
            [
                root / "annotations" / f"instances_{alias}.json",
                root / "annotations" / f"{alias}.json",
                root / alias / "_annotations.coco.json",
                root / f"{alias}.json",
            ]
        )
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def _validate_split(root: Path, split: str, annotation_path: Path) -> dict[str, Any]:
    errors: list[str] = []
    payload = _read_json(annotation_path)
    images_payload = payload.get("images")
    annotations_payload = payload.get("annotations")
    categories_payload = payload.get("categories")

    if not isinstance(images_payload, list):
        errors.append("images must be a list")
        images_payload = []
    if not isinstance(annotations_payload, list):
        errors.append("annotations must be a list")
        annotations_payload = []
    if not isinstance(categories_payload, list):
        errors.append("categories must be a list")
        categories_payload = []

    categories = {
        int(category.get("id")): str(category.get("name"))
        for category in categories_payload
        if isinstance(category, dict) and category.get("id") is not None
    }
    if not categories:
        errors.append("at least one category is required")

    images_by_id: dict[int, dict[str, Any]] = {}
    missing_files: list[str] = []
    for image in images_payload:
        if not isinstance(image, dict) or image.get("id") is None:
            errors.append("image entry missing id")
            continue
        image_id = int(image["id"])
        images_by_id[image_id] = image
        file_name = str(image.get("file_name", ""))
        if not file_name:
            errors.append(f"image {image_id} missing file_name")
        elif _resolve_image_path(root, split, file_name) is None:
            missing_files.append(file_name)

    if missing_files:
        errors.append(f"{len(missing_files)} image file(s) are missing")

    segmentation_types: Counter[str] = Counter()
    annotations_by_category: Counter[str] = Counter()
    source_tokens: dict[str, list[str]] = defaultdict(list)
    for image in images_by_id.values():
        file_name = str(image.get("file_name", ""))
        token = _source_token_for_image(file_name)
        if token and len(source_tokens[token]) < 3:
            source_tokens[token].append(file_name)
    for annotation in annotations_payload:
        if not isinstance(annotation, dict):
            errors.append("annotation entry must be an object")
            continue
        image_id = annotation.get("image_id")
        category_id = annotation.get("category_id")
        if image_id not in images_by_id:
            errors.append(f"annotation {annotation.get('id', '?')} references unknown image_id {image_id}")
        if category_id not in categories:
            errors.append(f"annotation {annotation.get('id', '?')} references unknown category_id {category_id}")
        else:
            annotations_by_category[categories[int(category_id)]] += 1

        segmentation = annotation.get("segmentation")
        segmentation_type, segmentation_error = _validate_segmentation(segmentation)
        if segmentation_type:
            segmentation_types[segmentation_type] += 1
        if segmentation_error:
            errors.append(f"annotation {annotation.get('id', '?')}: {segmentation_error}")

    return {
        "split": split,
        "annotation_path": str(annotation_path),
        "ready": not errors,
        "image_count": len(images_payload),
        "annotation_count": len(annotations_payload),
        "category_count": len(categories),
        "categories": sorted(categories.values()),
        "category_usage": {name: annotations_by_category.get(name, 0) for name in sorted(categories.values())},
        "unused_categories": [
            name for name in sorted(categories.values()) if annotations_by_category.get(name, 0) == 0
        ],
        "annotations_by_category": dict(annotations_by_category),
        "segmentation_types": dict(segmentation_types),
        "missing_image_count": len(missing_files),
        "missing_images": missing_files[:20],
        "errors": errors,
        "_source_tokens": dict(source_tokens),
    }


def _validate_segmentation(segmentation: Any) -> tuple[str | None, str | None]:
    if isinstance(segmentation, list):
        if not segmentation:
            return "polygon", "empty polygon segmentation"
        for polygon in segmentation:
            values = _coerce_numeric_list(polygon)
            if values is None:
                return "polygon", "polygon coordinates must be numeric"
            if len(values) < 6 or len(values) % 2 != 0:
                return "polygon", "polygon must contain at least three x/y pairs"
        return "polygon", None

    if isinstance(segmentation, dict):
        if "counts" not in segmentation or "size" not in segmentation:
            return "rle", "RLE segmentation must contain counts and size"
        size = segmentation.get("size")
        if not isinstance(size, list) or len(size) != 2:
            return "rle", "RLE size must be [height, width]"
        return "rle", None

    return None, "segmentation must be polygon list or RLE object"


def _normalize_polygon(polygon: Any, width: float, height: float) -> list[float]:
    values = _coerce_numeric_list(polygon)
    if values is None or len(values) < 6 or len(values) % 2 != 0:
        return []
    normalized: list[float] = []
    for index, value in enumerate(values):
        dimension = width if index % 2 == 0 else height
        normalized.append(min(1.0, max(0.0, float(value) / dimension)))
    return normalized


def _coerce_numeric_list(values: Any) -> list[float] | None:
    if not isinstance(values, list):
        return None
    try:
        return [float(value) for value in values]
    except (TypeError, ValueError):
        return None


def _source_token_for_image(file_name: str) -> str:
    stem = Path(file_name).stem.lower()
    stem = re.sub(r"\.rf\.[0-9a-f]{8,}$", "", stem)
    stem = re.sub(r"_jpg$", "", stem)
    stem = re.sub(r"[-_](jpg|jpeg|png)$", "", stem)
    stem = re.sub(r"[-_](?:copy|aug|flip|rotate|rot|scale|crop|blur|bright|dark)\d*$", "", stem)
    stem = re.sub(r"[^a-z0-9]+", "_", stem).strip("_")
    return stem or Path(file_name).stem.lower()


def _resolve_image_path(root: Path, split: str, file_name: str) -> Path | None:
    path = Path(file_name)
    candidates = [path] if path.is_absolute() else []
    if not path.is_absolute():
        candidates.extend(
            [
                root / file_name,
                root / "images" / file_name,
            ]
        )
        for alias in _split_aliases(split):
            candidates.extend(
                [
                    root / alias / file_name,
                    root / "images" / alias / file_name,
                ]
            )
    for candidate in candidates:
        if candidate.exists() and candidate.is_file():
            return candidate
    return None


def _link_or_copy(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() or target.is_symlink():
        target.unlink()
    try:
        os.symlink(source.resolve(), target)
    except OSError:
        shutil.copy2(source, target)


def _read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise COCODatasetValidationError(f"{path} must contain a COCO JSON object")
    return payload


def _split_aliases(split: str) -> tuple[str, ...]:
    return SPLIT_ALIASES.get(split, (split,))
