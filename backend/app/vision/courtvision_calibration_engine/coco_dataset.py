"""COCO 数据集工具 —— 验证和转换 COCO 分割数据集以用于球场线 YOLO 训练。

本文件的两个核心职责：
1. `validate_coco_segmentation_dataset`：检查本地的 COCO 标注数据集
   结构是否完整（图像、标注、类别是否齐全，分割格式是否合法，
   训练/验证/测试集是否有"数据泄漏"等）。
2. `prepare_yolo_segmentation_dataset`：把 COCO 的"多边形 segmentation"
   标注转换成 YOLO-seg 训练需要的 `labels/*.txt` 文件，并生成
   `court-line-seg.yaml` 数据集描述文件。

名词解释（初学者向）：
- COCO：一种常见的计算机视觉数据集标注格式，用单个 JSON 文件描述
  若干 images（图像）、annotations（标注）、categories（类别）。
- YOLO-seg：一种实例分割训练格式，每张图对应一个 .txt，每行
  `class_id x1 y1 x2 y2 ...`（坐标是归一化到 0~1 的相对值）。
- 分割（segmentation）：用多边形顶点或 RLE 掩码描述物体的轮廓。
"""

from __future__ import annotations

import json
import os
import re
import shutil
from collections import Counter, defaultdict
from collections.abc import Sequence
from pathlib import Path
from typing import Any

# 默认会去检查的"数据集划分"名称：训练 / 验证 / 测试
DEFAULT_SPLITS = ("train", "val", "test")
# 一个能用于训练的数据集"必须"提供的划分（缺了就不合格）
REQUIRED_SPLITS = ("train", "val")
# 不同来源的数据集对"验证集"叫法不一，这里做别名映射，
# 例如 "valid" / "validation" 都视作 "val"。
SPLIT_ALIASES = {
    "train": ("train",),
    "val": ("val", "valid", "validation"),
    "valid": ("valid", "val", "validation"),
    "test": ("test",),
}


class COCODatasetValidationError(ValueError):
    """数据集校验失败时抛出的异常。

    相比普通的 ValueError，它额外携带一个 `report` 字典，方便调用方
    拿到完整的结构化校验报告（而不是只看一句错误信息）。
    """

    def __init__(self, message: str, report: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        # 校验报告（默认空字典），由调用方读取以排查问题
        self.report = report or {}


class COCODatasetConversionError(ValueError):
    """数据集转换（COCO → YOLO）失败时抛出的异常。"""

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
    """Validate a local COCO segmentation dataset for court-line training.

    逐个划分（train/val/test）读取标注 JSON，统计图像数、标注数、
    类别使用情况，并检测"数据集泄漏"（同一来源的图像出现在多个划分中）。
    最终返回一个"数据集是否 ready"的汇总报告字典。
    """

    # 统一转成 Path 对象，并展开 "~" 这样的用户目录简写
    root = Path(dataset_root).expanduser()
    # 要检查的划分列表；不传就用默认三件套
    requested_splits = tuple(splits or DEFAULT_SPLITS)
    # 每个划分各自的校验结果
    split_reports: list[dict[str, Any]] = []
    # 收集所有错误字符串
    errors: list[str] = []

    # 遍历每个划分，分别读取并校验其标注文件
    for split in requested_splits:
        # 在常见位置寻找该划分的标注 JSON（如 annotations/instances_val.json）
        annotation_path = _find_annotation_path(root, split)
        if annotation_path is None:
            # 找不到标注文件：如果是必需要划分就记为错误
            if split in required_splits:
                errors.append(f"{split}: missing annotation JSON")
            continue

        # 读这个划分并做结构校验
        split_report = _validate_split(root, split, annotation_path)
        split_reports.append(split_report)
        # 把该划分内的每一条错误都加上前缀，归集到总错误列表
        errors.extend(f"{split}: {error}" for error in split_report["errors"])

    # 检查"必需要划分"是否都真的存在
    available_splits = {item["split"] for item in split_reports}
    for split in required_splits:
        if split not in available_splits:
            errors.append(f"{split}: required split is not ready")

    # 汇总所有划分的统计总量（图像数、标注数、缺失图像数）
    totals = {
        "images": sum(item["image_count"] for item in split_reports),
        "annotations": sum(item["annotation_count"] for item in split_reports),
        "missing_images": sum(item["missing_image_count"] for item in split_reports),
    }
    # 所有出现过的类别名（去重并排序）
    categories = sorted({name for item in split_reports for name in item["categories"]})
    # 每个类别被标注使用的次数（用于发现"定义了但没用"的类别）
    category_usage = {name: 0 for name in categories}
    for item in split_reports:
        for category, count in item["category_usage"].items():
            category_usage[category] = category_usage.get(category, 0) + int(count)
    category_usage = dict(sorted(category_usage.items()))
    # 有标注的类别 / 完全没用到的类别
    annotated_categories = sorted(category for category, count in category_usage.items() if count > 0)
    unused_categories = sorted(category for category, count in category_usage.items() if count == 0)
    # 统计分割类型（polygon / rle 的分布）
    segmentation_types = Counter()
    for item in split_reports:
        segmentation_types.update(item["segmentation_types"])
    # "结构是否完整"：没有任何错误即视为结构就绪
    structural_ready = not errors
    # 评估"目标类别"是否就绪（取决于 target_category / target_strategy）
    target_readiness = _evaluate_target_readiness(
        category_usage=category_usage,
        target_category=target_category,
        target_strategy=target_strategy,
    )
    # 检测训练/验证/测试之间是否"数据泄漏"
    leakage_report = _detect_split_leakage(split_reports)
    warnings = list(target_readiness["warnings"])
    if leakage_report["risk"]:
        warnings.append(f"{leakage_report['token_count']} likely source token(s) appear in multiple dataset splits")

    # 对外公开的每个划分报告（去掉内部用的 "_" 开头字段）
    public_splits = [_public_split_report(item) for item in split_reports]
    report = {
        "dataset_root": str(root),
        # 最终是否 ready：结构就绪 且 目标类别也"没被判定为不就绪"
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

    # 如果需要产出"验收证据"（summary.json + 标注预览图），就写盘
    if evidence_output is not None:
        report["acceptance"] = _write_acceptance_evidence(
            root=root,
            report=report,
            output_root=Path(evidence_output).expanduser(),
            preview_samples_per_split=preview_samples_per_split,
        )

    # 不 ready 且要求"出错就抛异常"时，抛出带完整报告的异常
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
    # 先校验数据集结构，不通过会直接抛异常（由 validate 内部负责）
    report = validate_coco_segmentation_dataset(root, splits=splits)
    converted_splits: list[str] = []

    # 遍历每个划分，逐个图像转换标注 + 复制/链接图像文件
    for split_report in report["splits"]:
        split = split_report["split"]
        annotation_path = Path(split_report["annotation_path"])
        payload = _read_json(annotation_path)
        # 建立 image_id -> image 的索引，方便按图取标注
        images = {int(image["id"]): image for image in payload.get("images", [])}
        # 建立 image_id -> [该图所有 annotation] 的索引
        annotations_by_image: dict[int, list[dict[str, Any]]] = defaultdict(list)
        for annotation in payload.get("annotations", []):
            annotations_by_image[int(annotation.get("image_id", -1))].append(annotation)

        # 为每个划分准备好 images/ 与 labels/ 输出目录
        image_output_dir = output / "images" / split
        label_output_dir = output / "labels" / split
        image_output_dir.mkdir(parents=True, exist_ok=True)
        label_output_dir.mkdir(parents=True, exist_ok=True)

        for image_id, image in images.items():
            # 找到图像文件在磁盘上的真实路径（可能位于多个候选目录）
            source_path = _resolve_image_path(root, split, str(image.get("file_name", "")))
            if source_path is None:
                continue

            # 保留原扩展名；用 8 位零填充的 image_id 作为新文件名（如 00000001.jpg），
            # 这样能保证文件名稳定、无重名
            suffix = Path(str(image.get("file_name", ""))).suffix or source_path.suffix
            target_stem = f"{image_id:08d}"
            target_image = image_output_dir / f"{target_stem}{suffix.lower()}"
            # 软链接优先，失败则复制（节省磁盘）
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
                    # 把绝对像素坐标归一化到 0~1，并拼成 YOLO 一行
                    normalized = _normalize_polygon(polygon, width=width, height=height)
                    if normalized:
                        rows.append("0 " + " ".join(f"{value:.6f}" for value in normalized))

            # 把当前图的所有分割行写成 labels/<split>/<image_id>.txt
            (label_output_dir / f"{target_stem}.txt").write_text("\n".join(rows), encoding="utf-8")

        converted_splits.append(split)

    # 生成 YOLO 训练用的数据集 yaml 描述文件
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
    """评估"目标类别"是否可用。

    支持三种策略：
    - merge / one-class：把所有类别合并为单一类（MVP 默认场景，只要
      有任一带标注的类别即可）。
    - category：必须精确指定一个 target_category，且该类别有标注、
      且其它类别不能有标注。
    - unspecified：未指定策略，仅给警告， readiness 置为 None（待定）。
    """
    strategy = (target_strategy or ("category" if target_category else "unspecified")).strip().lower()
    errors: list[str] = []
    warnings: list[str] = []
    annotated_categories = sorted(category for category, count in category_usage.items() if count > 0)
    unused_categories = sorted(category for category, count in category_usage.items() if count == 0)

    # 合并为单类策略：只要存在带标注的类别即可，未使用的类别只警告
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

    # 未指定策略：暂不判定为就绪，仅给警告
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

    # category 策略：要求精确指定一个存在且有标注的目标类别，且其它类别不能有标注
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
    """检测"数据集泄漏"：同一来源的图像是否出现在多个划分中。

    做法：从每个图像的 file_name 中提取"来源 token"（去掉增强/复制
    后缀后的原始名），看它是否跨多个 split 出现。跨划分出现即视为
    有泄漏风险（测试集会"见过"训练数据，评估结果不可信）。
    """
    # token -> {split -> [示例文件名]}
    splits_by_token: dict[str, dict[str, list[str]]] = defaultdict(dict)
    for split_report in split_reports:
        split = str(split_report["split"])
        for token, examples in split_report.get("_source_tokens", {}).items():
            splits_by_token[token][split] = examples

    # 出现在超过 1 个划分里的 token 才算"危险"
    risky_tokens = {
        token: split_examples for token, split_examples in splits_by_token.items() if len(split_examples) > 1
    }
    examples = [
        {
            "source_token": token,
            "splits": sorted(split_examples),
            "examples": {split: values[:2] for split, values in sorted(split_examples.items())},
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
    """把校验报告写成 summary.json，并可选择性地生成标注叠加预览图。"""
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
    # ensure_ascii=False 让中文也能正常写入
    summary_path.write_text(json.dumps(summary_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return acceptance


def _write_annotation_previews(
    root: Path,
    split_reports: Sequence[dict[str, Any]],
    output_root: Path,
    samples_per_split: int,
) -> list[dict[str, str]]:
    """为每个划分各画若干张"标注叠加在图上"的预览图，便于人工抽检。

    依赖 OpenCV（cv2），如果环境里没装就直接返回空列表（不影响主流程）。
    """
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
            # 复制一份用于画半透明叠加层
            overlay = frame.copy()
            for annotation in annotations_by_image.get(int(image_id), []):
                _draw_annotation(overlay, annotation, cv2=cv2, np=np)
            # addWeighted 把彩色标注层与原始图按 0.55/0.45 混合，得到半透明效果
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
    """在 frame 上用半透明填充 + 描边画出一条 polygon 分割轮廓。"""
    segmentation = annotation.get("segmentation")
    color = (30, 220, 255)
    if not isinstance(segmentation, list):
        return
    for polygon in segmentation:
        values = _coerce_numeric_list(polygon)
        if values is None or len(values) < 6 or len(values) % 2 != 0:
            continue
        # 把 [x0,y0,x1,y1,...] 重排成 N×2 的点数组，并取整为 OpenCV 需要的 int32
        points = np.asarray(values, dtype=np.float32).reshape((-1, 2)).round().astype(np.int32)
        cv2.fillPoly(frame, [points], color)
        cv2.polylines(frame, [points], isClosed=True, color=(20, 120, 255), thickness=2)


def _public_split_report(split_report: dict[str, Any]) -> dict[str, Any]:
    """去掉 split_report 里以 "_" 开头的内部字段，得到对外公开版本。"""
    return {key: value for key, value in split_report.items() if not key.startswith("_")}


def _find_annotation_path(root: Path, split: str) -> Path | None:
    """在若干常见位置寻找某个划分的标注 JSON 文件。

    会尝试 annotations/instances_<alias>.json、annotations/<alias>.json、
    <split>/_annotations.coco.json、<split>.json 等命名。找到第一个存在的就返回。
    """
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
    """读取并校验单个划分的标注 JSON，返回该划分的详细校验报告。"""
    errors: list[str] = []
    payload = _read_json(annotation_path)
    images_payload = payload.get("images")
    annotations_payload = payload.get("annotations")
    categories_payload = payload.get("categories")

    # 三个顶层字段必须是 list，否则记为错误并降级为空列表继续统计
    if not isinstance(images_payload, list):
        errors.append("images must be a list")
        images_payload = []
    if not isinstance(annotations_payload, list):
        errors.append("annotations must be a list")
        annotations_payload = []
    if not isinstance(categories_payload, list):
        errors.append("categories must be a list")
        categories_payload = []

    # 类别 id -> name 映射；没有类别直接报错
    categories = {
        int(category.get("id")): str(category.get("name"))
        for category in categories_payload
        if isinstance(category, dict) and category.get("id") is not None
    }
    if not categories:
        errors.append("at least one category is required")

    # 检查每个图像：id 是否齐全、file_name 是否有对应磁盘文件
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
    # 记录每个"来源 token"对应的样本（最多保留 3 个），用于泄漏检测
    source_tokens: dict[str, list[str]] = defaultdict(list)
    for image in images_by_id.values():
        file_name = str(image.get("file_name", ""))
        token = _source_token_for_image(file_name)
        if token and len(source_tokens[token]) < 3:
            source_tokens[token].append(file_name)
    # 逐条标注校验：引用的 image_id / category_id 必须存在，分割格式必须合法
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
    """校验单条分割数据，返回 (类型, 错误描述)。

    COCO 的 segmentation 有两种合法形式：
    - 多边形列表：[[x0,y0,x1,y1,...], ...]，要求成对且至少 3 个点。
    - RLE 字典：{"counts": ..., "size": [h, w]}。
    """
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
    """把多边形绝对像素坐标归一化到 0~1（除以图像宽高，并裁剪到 [0,1]）。

    返回形如 [x0, y0, x1, y1, ...] 的浮点列表；非法输入返回空列表。
    """
    values = _coerce_numeric_list(polygon)
    if values is None or len(values) < 6 or len(values) % 2 != 0:
        return []
    normalized: list[float] = []
    for index, value in enumerate(values):
        # 偶数位是 x（用宽度归一化），奇数位是 y（用高度归一化）
        dimension = width if index % 2 == 0 else height
        normalized.append(min(1.0, max(0.0, float(value) / dimension)))
    return normalized


def _coerce_numeric_list(values: Any) -> list[float] | None:
    """尝试把一个 list 里的元素都转成 float；任何元素无法转换就返回 None。"""
    if not isinstance(values, list):
        return None
    try:
        return [float(value) for value in values]
    except (TypeError, ValueError):
        return None


def _source_token_for_image(file_name: str) -> str:
    """从文件名提取"来源 token"：去掉增强/复制/格式等后缀后的原始图像名。

    例：'game01.rf.a1b2c3d4.jpg' -> 'game01'，这样同一原始图的不同增强版本
    会被识别为"同一个来源"，用于检测跨划分的数据泄漏。
    """
    stem = Path(file_name).stem.lower()
    # 去掉 roboflow 生成的 .rf.<hex> 后缀
    stem = re.sub(r"\.rf\.[0-9a-f]{8,}$", "", stem)
    stem = re.sub(r"_jpg$", "", stem)
    stem = re.sub(r"[-_](jpg|jpeg|png)$", "", stem)
    # 去掉常见的增强后缀（copy/aug/flip/rotate/...）
    stem = re.sub(r"[-_](?:copy|aug|flip|rotate|rot|scale|crop|blur|bright|dark)\d*$", "", stem)
    # 把其余非字母数字字符统一成下划线
    stem = re.sub(r"[^a-z0-9]+", "_", stem).strip("_")
    return stem or Path(file_name).stem.lower()


def _resolve_image_path(root: Path, split: str, file_name: str) -> Path | None:
    """根据文件名在若干候选目录中查找图像真实路径，找到存在的就返回。

    候选包括：file_name 本身是绝对路径、root/file_name、root/images/file_name，
    以及按 split 别名划分的目录（root/<split>/file_name 等）。
    """
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
    """优先用软链接（省空间）；软链接失败（如跨文件系统）就退回到复制。"""
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() or target.is_symlink():
        target.unlink()
    try:
        os.symlink(source.resolve(), target)
    except OSError:
        shutil.copy2(source, target)


def _read_json(path: Path) -> dict[str, Any]:
    """读取并解析一个 COCO JSON 文件，要求顶层必须是对象（dict）。"""
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise COCODatasetValidationError(f"{path} must contain a COCO JSON object")
    return payload


def _split_aliases(split: str) -> tuple[str, ...]:
    """返回某划分名对应的所有别名（用于在不同目录命名约定下查找文件）。"""
    return SPLIT_ALIASES.get(split, (split,))
