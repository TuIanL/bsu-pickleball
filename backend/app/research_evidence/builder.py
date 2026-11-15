"""Controlled package building and verification.

The builder never scans a disk. Every indexed file is named explicitly in the
build config, so the authorised roots act as a blast radius rather than a search
space. Two hard refusals protect the inputs:

* the output directory may not sit inside any authorised source root, and
* an existing non-empty output directory is never overwritten.

Asset identity is derived from content when a digest can be computed. A missing
or unreadable asset must supply an explicit ``asset_id`` in the config, because
an absent digest cannot yield a content identity and inventing one would be a
lie about provenance.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from .classification import (
    AdmissionError,
    assert_formal_input_eligible,
    classify_usage_kind,
    probe_container,
)
from .hashing import inspect_file
from .identity import asset_id_from_digest
from .importers import (
    import_job_result_file,
    import_quality_report_file,
    iter_quality_reports,
)
from .locations import (
    LOCATIONS_SCHEMA_VERSION,
    SourceRoot,
    build_locator,
    find_local_paths,
    resolve_locator,
)
from .media_probe import probe_media

MANIFEST_SCHEMA_VERSION = "pb.research-evidence-manifest.v1.0"
EMPTY_PATCH_SHA256 = (
    "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
)
# 只有工具自身代码参与「工作区是否干净」的判定，交付产物不影响工具版本可信度。
TOOLING_PATHS = (
    "backend/app/research_evidence",
    "backend/contracts/research_evidence",
    "backend/scripts/research_evidence.py",
)
MANIFEST_FILENAME = "manifest.json"
CHECKS_FILENAME = "checks.json"
LOCATIONS_FILENAME = "locations.local.json"

SCHEMA_PATH = (
    Path(__file__).resolve().parents[2]
    / "contracts"
    / "research_evidence"
    / "v1"
    / "schemas"
    / "research_evidence_manifest.schema.json"
)

AssetKind = Literal[
    "source_video",
    "pts_sidecar",
    "sync_manifest",
    "calibration",
    "roster",
    "model_weight",
    "model_config",
    "model_package",
    "job_artifact",
    "annotation",
    "other",
]


class BuildError(ValueError):
    """Raised when a package cannot be built without breaking a guarantee."""


class VerifyError(ValueError):
    """Raised when an existing package fails structural verification."""


@dataclass(frozen=True)
class AssetSpec:
    """One explicitly named file to index."""

    root_id: str
    relative_path: str
    kind: AssetKind
    usage_kind: Literal["real", "fixture", "unknown"]
    requirement: Literal["required", "optional"]
    asset_id: str | None = None
    notion_task: str | None = None
    view_role: Literal["cam1", "cam2", "single_view", "unspecified"] = "unspecified"
    time_base: Literal[
        "cfr_nominal", "pts_actual", "take_unified", "not_applicable"
    ] = "not_applicable"
    notes: tuple[str, ...] = ()

    @property
    def locator(self) -> str:
        return build_locator(self.root_id, self.relative_path)


@dataclass(frozen=True)
class HistoricalJobSpec:
    """A historical job directory whose range and verdict should be recorded."""

    root_id: str
    relative_path: str

    @property
    def locator(self) -> str:
        return build_locator(self.root_id, self.relative_path)


@dataclass(frozen=True)
class BuildConfig:
    """A complete, explicit description of what to index."""

    package_id: str
    source_roots: tuple[SourceRoot, ...]
    assets: tuple[AssetSpec, ...]
    baseline: dict[str, Any] = field(default_factory=dict)
    historical_jobs: tuple[HistoricalJobSpec, ...] = ()

    def roots_by_id(self) -> dict[str, str]:
        return {root.root_id: root.path for root in self.source_roots}

    def roots_by_key(self) -> dict[str, SourceRoot]:
        return {root.root_id: root for root in self.source_roots}


@dataclass(frozen=True)
class VerifyCheck:
    name: str
    ok: bool
    detail: str | None = None


@dataclass(frozen=True)
class VerifyReport:
    ok: bool
    checks: tuple[VerifyCheck, ...]

    @property
    def failures(self) -> tuple[VerifyCheck, ...]:
        return tuple(check for check in self.checks if not check.ok)


# --- config -----------------------------------------------------------------


def _load_source_roots(raw: Any) -> tuple[SourceRoot, ...]:
    if not isinstance(raw, list) or not raw:
        raise BuildError("配置必须声明至少一个 source_root")
    roots = []
    for entry in raw:
        if not isinstance(entry, Mapping):
            raise BuildError("source_root 条目应为对象")
        try:
            roots.append(SourceRoot.model_validate(entry))
        except Exception as error:  # pydantic ValidationError
            raise BuildError(f"source_root 无效: {error}") from error
    return tuple(roots)


def _load_assets(raw: Any) -> tuple[AssetSpec, ...]:
    if not isinstance(raw, list) or not raw:
        raise BuildError("配置必须声明至少一个 asset")
    assets = []
    for entry in raw:
        if not isinstance(entry, Mapping):
            raise BuildError("asset 条目应为对象")
        try:
            assets.append(
                AssetSpec(
                    root_id=str(entry["root_id"]),
                    relative_path=str(entry["relative_path"]),
                    kind=entry["kind"],
                    usage_kind=entry["usage_kind"],
                    requirement=entry["requirement"],
                    asset_id=entry.get("asset_id"),
                    notion_task=entry.get("notion_task"),
                    view_role=entry.get("view_role", "unspecified"),
                    time_base=entry.get("time_base", "not_applicable"),
                    notes=tuple(entry.get("notes") or ()),
                )
            )
        except KeyError as error:
            raise BuildError(f"asset 缺少字段: {error}") from error
    return tuple(assets)


def _load_historical_jobs(raw: Any) -> tuple[HistoricalJobSpec, ...]:
    if not raw:
        return ()
    if not isinstance(raw, list):
        raise BuildError("historical_jobs 应为数组")
    jobs = []
    for entry in raw:
        if not isinstance(entry, Mapping):
            raise BuildError("historical_jobs 条目应为对象")
        try:
            jobs.append(
                HistoricalJobSpec(
                    root_id=str(entry["root_id"]),
                    relative_path=str(entry["relative_path"]),
                )
            )
        except KeyError as error:
            raise BuildError(f"historical_jobs 缺少字段: {error}") from error
    return tuple(jobs)


def load_build_config(path: Path) -> BuildConfig:
    """Load and validate a build config from JSON."""
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise BuildError(f"配置文件不存在: {path}") from error
    except json.JSONDecodeError as error:
        raise BuildError(f"配置文件不是合法 JSON: {path}") from error

    if not isinstance(raw, Mapping):
        raise BuildError("配置文件顶层应为对象")

    package_id = raw.get("package_id")
    if not isinstance(package_id, str):
        raise BuildError("配置缺少 package_id")

    baseline = dict(raw.get("baseline") or {})
    if not baseline.get("selected_revision"):
        raise BuildError(
            "配置必须提供 baseline.selected_revision：科研基线须由负责人钉到具体提交"
        )

    return BuildConfig(
        package_id=package_id,
        source_roots=_load_source_roots(raw.get("source_roots")),
        assets=_load_assets(raw.get("assets")),
        baseline=baseline,
        historical_jobs=_load_historical_jobs(raw.get("historical_jobs")),
    )


def assert_output_is_safe(output_dir: Path, source_roots: Mapping[str, str]) -> None:
    """Refuse an output location that could damage inputs or prior results."""
    target = Path(output_dir).resolve()

    for root_id, root_path in source_roots.items():
        root = Path(root_path).resolve()
        if target == root or target.is_relative_to(root):
            raise BuildError(
                f"输出目录位于授权来源根 {root_id} 内，拒绝写入: {target}"
            )
        if root.is_relative_to(target):
            raise BuildError(
                f"输出目录包含授权来源根 {root_id}，拒绝写入: {target}"
            )

    if target.exists():
        if not target.is_dir():
            raise BuildError(f"输出路径已存在且不是目录: {target}")
        if any(target.iterdir()):
            raise BuildError(f"输出目录已存在且非空，拒绝覆写: {target}")


# --- asset entry ------------------------------------------------------------


def _build_asset_entry(
    spec: AssetSpec,
    root: SourceRoot,
    resolved: Path,
    *,
    timeout_seconds: float,
    probe_timeout_seconds: float = 60.0,
    cancel: Callable[[], bool] | None,
) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]], str | None]:
    """Return (content, usage, checks, admission warning).

    内容层与使用关系分开产出：同一个 asset_id 的多条 usage 各自保留机位、用途
    与必需性，任何一侧都不得被另一侧的代表值覆盖。
    """
    inspection = inspect_file(resolved, timeout_seconds=timeout_seconds, cancel=cancel)
    digest_status = "known" if inspection.sha256 else "unknown"

    if inspection.sha256 is not None:
        asset_id = asset_id_from_digest(inspection.sha256)
    elif spec.asset_id:
        asset_id = spec.asset_id
    else:
        raise BuildError(
            f"无法为 {spec.locator} 派生内容身份（摘要不可用），请在配置中显式给出 asset_id"
        )

    container = None
    probe = None
    if inspection.availability == "present" and spec.kind == "source_video":
        container = probe_container(resolved)
        probe = probe_media(resolved, timeout_seconds=probe_timeout_seconds)

    usage_evidence = classify_usage_kind(
        declared=spec.usage_kind, root_policy=None, container=container or "unknown"
    )

    warning: str | None = None
    if (
        spec.kind == "source_video"
        and spec.usage_kind == "real"
        and inspection.availability == "present"
    ):
        try:
            assert_formal_input_eligible(
                usage_kind=usage_evidence.usage_kind,
                container=container or "unknown",
                suffix=resolved.suffix,
                digest_status=digest_status,
            )
        except AdmissionError as error:
            warning = str(error)

    checks: list[dict[str, Any]] = [
        {
            "check_id": f"c_{asset_id}_existence",
            "target_asset_id": asset_id,
            "kind": "existence",
            "status": "passed" if inspection.availability == "present" else "failed",
            "scope": f"授权来源根内路径解析（{spec.view_role}）",
            "detail": inspection.detail,
        }
    ]

    if inspection.sha256:
        checks.append(
            {
                "check_id": f"c_{asset_id}_digest",
                "target_asset_id": asset_id,
                "kind": "digest",
                "status": "passed",
                "scope": f"全文件分块 SHA-256（{spec.view_role}）",
                "detail": inspection.detail,
            }
        )

    # 只读证据入包：读取前后 size/mtime 是否被改动，必须可审计。
    checks.append(
        {
            "check_id": f"c_{asset_id}_readonly",
            "target_asset_id": asset_id,
            "kind": "readonly",
            "status": "passed" if inspection.input_unchanged else "failed",
            "scope": f"读取前后 size/mtime 比对（{spec.view_role}）",
            "detail": None
            if inspection.input_unchanged
            else "读取期间文件被修改，本次摘要不可作为稳定基准",
        }
    )

    media_failed = False
    if probe is not None:
        media_failed = probe.status != "ok"
        checks.append(
            {
                "check_id": f"c_{asset_id}_probe",
                "target_asset_id": asset_id,
                "kind": "metadata_probe",
                "status": "passed" if probe.status == "ok" else "failed",
                "scope": "只读容器元数据，未全解码",
                "detail": probe.detail,
            }
        )

    # 摘要核验与媒体有效性是两件独立的事：
    # - 文件根本不是受支持容器 → mismatch（内容与声明的媒体类型不符）
    # - 是媒体但探测失败或超时 → not_checked（有效媒体性未确认）
    # - 读取期间文件被改动 → not_checked（摘要不能作为稳定基准）
    # optional 只影响包完整性阻断，不影响本条结论；但绝不能标成 verified。
    if inspection.availability == "present":
        if inspection.sha256 is None:
            verification = "not_checked"
        elif spec.kind == "source_video" and container == "unknown":
            verification = "mismatch"
        elif media_failed:
            verification = "not_checked"
        elif not inspection.input_unchanged:
            verification = "not_checked"
        else:
            verification = "verified"
    elif inspection.availability == "missing":
        verification = "unknown"
    else:
        verification = "not_checked"

    media_metadata: dict[str, Any] | None = None
    if probe is not None and probe.status == "ok":
        media_metadata = {
            "duration_seconds": probe.duration_seconds,
            "width": probe.width,
            "height": probe.height,
            "fps_nominal": probe.fps_nominal,
            "frame_count": probe.frame_count,
            "probe_status": "ok",
        }
    elif probe is not None:
        media_metadata = {"probe_status": probe.status}

    content: dict[str, Any] = {
        "asset_id": asset_id,
        "kind": spec.kind,
        "size_bytes": inspection.size_bytes,
        "digest": (
            {"status": "known", "sha256": inspection.sha256}
            if inspection.sha256
            else {
                "status": "unknown",
                "sha256": None,
                "reason": inspection.detail or "摘要不可用",
            }
        ),
        "availability": inspection.availability,
        "verification": verification,
        "media_metadata": media_metadata,
        "notes": [],
        "_readonly_ok": inspection.input_unchanged,
    }

    usage: dict[str, Any] = {
        "locator": spec.locator,
        "view_role": spec.view_role,
        "usage_kind": usage_evidence.usage_kind,
        "requirement": spec.requirement,
        "source_root_id": root.root_id,
        "source_kind": root.source_kind,
        "usage_basis": usage_evidence.to_manifest_field(),
        "time_base": spec.time_base,
        "context": None,
        "notes": list(spec.notes),
    }
    return content, usage, checks, warning


# --- build ------------------------------------------------------------------


def _import_historical_runs(
    jobs: tuple[HistoricalJobSpec, ...], roots: dict[str, str]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Import historical verdicts as run refs. Never promotes and never erases them."""
    run_refs: list[dict[str, Any]] = []
    limitations: list[dict[str, Any]] = []

    for job in jobs:
        try:
            job_dir = resolve_locator(job.locator, roots)
        except Exception as error:
            raise BuildError(f"无法解析历史任务 {job.locator}: {error}") from error

        result_path = job_dir / "result.json"
        if not result_path.is_file():
            limitations.append(
                {
                    "code": "historical_run_missing",
                    "message": f"{job.locator} 缺少 result.json，未纳入对照",
                    "block_completeness": True,
                    "affects": [],
                    "notion_task": None,
                }
            )
            continue

        run = import_job_result_file(result_path)
        reports = list(iter_quality_reports(job_dir))
        quality = None
        unmatched_job_ids: list[str] = []
        for report_path in reports:
            candidate = import_quality_report_file(report_path)
            if candidate.job_id == run.job_id:
                quality = candidate
                break
            unmatched_job_ids.append(candidate.job_id)

        if reports and quality is None:
            # 宁可没有质量结论，也不能把别的 job 的判定嫁给这次运行。
            limitations.append(
                {
                    "code": "historical_quality_unmatched",
                    "message": (
                        f"{run.job_id} 目录内存在质量报告但 job_id 不匹配"
                        f"（{sorted(set(unmatched_job_ids))}），未生成质量结论"
                    ),
                    "block_completeness": False,
                    "affects": [],
                    "notion_task": None,
                }
            )

        verdict = quality.verdict if quality else "unknown"

        if run.range is None:
            limitations.append(
                {
                    "code": "historical_run_range_unknown",
                    "message": (
                        f"{run.job_id} 无轨道数据，原判定 {verdict}，"
                        "范围未知，未写入 run_refs"
                    ),
                    "block_completeness": False,
                    "affects": [],
                    "notion_task": None,
                }
            )
            continue

        scope = f"观测覆盖 {run.range.start_seconds:.1f}–{run.range.end_seconds:.1f}s"
        run_refs.append(
            {
                "run_id": run.job_id,
                "origin": "product_job",
                "code_revision": {
                    "label": "runtime",
                    "status": "unknown",
                    "commit": None,
                    "worktree_clean": None,
                    "dirty_patch": {
                        "status": "unknown",
                        "sha256": None,
                        "reason": "历史产物未记录代码版本，禁止用当前 HEAD 回填",
                    },
                    "note": None,
                },
                "consumes": [],
                "range": {
                    "start_seconds": run.range.start_seconds,
                    "end_seconds": run.range.end_seconds,
                    "frame_start": None,
                    "frame_end": None,
                    "time_base": "pts_actual",
                },
                "algorithm_verdict": {
                    "result": verdict if verdict in {"pass", "fail"} else "unknown",
                    "scope": scope,
                    "recorded_source": "quality_report" if quality else "none",
                    "detail": "范围由轨道时间戳推导，非任务声明窗口",
                },
            }
        )

        if verdict == "fail":
            limitations.append(
                {
                    "code": "historical_run_failed",
                    "message": (
                        f"{run.job_id} 历史判定 fail（{scope}），"
                        "原结论保留，不代表整段通过"
                    ),
                    "block_completeness": False,
                    "affects": [],
                    "notion_task": None,
                }
            )

    return run_refs, limitations


def _aggregate_availability(values: list[str]) -> str:
    if any(value == "present" for value in values):
        return "present"
    if all(value == "missing" for value in values):
        return "missing"
    if any(value == "unreachable" for value in values):
        return "unreachable"
    return "not_checked"


def _aggregate_verification(values: list[str]) -> str:
    if any(value == "mismatch" for value in values):
        return "mismatch"
    if all(value == "verified" for value in values):
        return "verified"
    if any(value == "not_checked" for value in values):
        return "not_checked"
    return "unknown"


def _completeness(assets: list[dict[str, Any]], limitations: list[dict[str, Any]]) -> str:
    if any(limit["block_completeness"] for limit in limitations):
        return "partial"
    for asset in assets:
        required_usages = [
            usage
            for usage in asset.get("usages") or []
            if usage.get("requirement") == "required"
        ]
        if not required_usages:
            continue
        if asset["availability"] != "present" or asset["verification"] != "verified":
            return "partial"
    return "complete"


def build_manifest(
    config: BuildConfig,
    *,
    timeout_seconds: float = 600.0,
    probe_timeout_seconds: float = 60.0,
    cancel: Callable[[], bool] | None = None,
) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
    """Build (manifest, locations, extra checks) without touching the disk output."""
    roots = config.roots_by_id()
    roots_by_key = config.roots_by_key()

    assets: list[dict[str, Any]] = []
    checks: list[dict[str, Any]] = []
    location_assets: dict[str, Any] = {}
    limitations: list[dict[str, Any]] = []

    pending: dict[str, list[dict[str, Any]]] = {}

    for spec in config.assets:
        root = roots_by_key.get(spec.root_id)
        if root is None:
            raise BuildError(f"asset 引用了未声明的来源根: {spec.root_id}")

        try:
            resolved = resolve_locator(spec.locator, roots)
        except Exception as error:
            raise BuildError(f"无法解析 {spec.locator}: {error}") from error

        content, usage, asset_checks, warning = _build_asset_entry(
            spec,
            root,
            resolved,
            timeout_seconds=timeout_seconds,
            probe_timeout_seconds=probe_timeout_seconds,
            cancel=cancel,
        )
        pending.setdefault(content["asset_id"], []).append(
            {
                "spec": spec,
                "content": content,
                "usage": usage,
                "checks": asset_checks,
                "warning": warning,
            }
        )

    # 内容身份相同的多个位置聚合为一个内容资产，每个位置各自保留为一条使用关系。
    for asset_id, group in sorted(pending.items()):
        group.sort(key=lambda item: item["usage"]["locator"])
        contents = [item["content"] for item in group]
        usages = [item["usage"] for item in group]

        kinds = {content["kind"] for content in contents}
        if len(kinds) > 1:
            raise BuildError(
                f"同一内容 {asset_id} 被声明为不同 kind: {sorted(kinds)}；"
                "请确认这是否其实是不同资产"
            )

        digests = {
            content["digest"]["sha256"]
            for content in contents
            if content["digest"].get("sha256")
        }
        if len(digests) > 1:
            raise BuildError(
                f"同一内容身份 {asset_id} 出现不同摘要: {sorted(digests)}"
            )

        asset: dict[str, Any] = {
            "asset_id": asset_id,
            "kind": contents[0]["kind"],
            "size_bytes": contents[0]["size_bytes"],
            "digest": contents[0]["digest"],
            "availability": _aggregate_availability(
                [content["availability"] for content in contents]
            ),
            "verification": _aggregate_verification(
                [content["verification"] for content in contents]
            ),
            "media_metadata": contents[0]["media_metadata"],
            "usages": usages,
            "notes": [],
        }

        if len(group) > 1:
            asset["notes"] = [
                f"内容与 {item['usage']['locator']} 相同（同一 SHA-256），"
                "按使用关系分别记录于 usages"
                for item in group[1:]
            ]

        assets.append(asset)

        # 同一内容的同类检查结果通常相同；但任一副本失败必须保留失败结论
        seen_kinds: dict[tuple[str, str], int] = {}
        for item in group:
            for check in item["checks"]:
                key = (check["target_asset_id"], check["kind"])
                if key in seen_kinds:
                    index = seen_kinds[key]
                    if checks[index]["status"] == "failed":
                        continue
                    if check["status"] == "failed":
                        checks[index] = check
                    continue
                seen_kinds[key] = len(checks)
                checks.append(check)

        location_assets[asset_id] = {
            "locator": usages[0]["locator"],
            "relative_path": group[0]["spec"].relative_path,
            "source_root_id": group[0]["spec"].root_id,
            "alternate_locators": [usage["locator"] for usage in usages[1:]],
        }

        # 每条使用关系独立评估阻断策略：required 阻断，optional 只记录。
        for item in group:
            usage = item["usage"]
            content = item["content"]
            blocking = usage["requirement"] == "required"
            spec = item["spec"]

            if item["warning"]:
                limitations.append(
                    {
                        "code": "formal_input_rejected",
                        "message": (
                            f"{asset_id}@{usage['view_role']}: {item['warning']}"
                        ),
                        "block_completeness": blocking,
                        "affects": [asset_id],
                        "notion_task": spec.notion_task,
                    }
                )

            if content["availability"] != "present":
                limitations.append(
                    {
                        "code": f"asset_{content['availability']}",
                        "message": (
                            f"{asset_id}@{usage['locator']} 不可用，未纳入核验"
                        ),
                        "block_completeness": blocking,
                        "affects": [asset_id],
                        "notion_task": spec.notion_task,
                    }
                )

            if not content.get("_readonly_ok", True):
                limitations.append(
                    {
                        "code": "readonly_violation",
                        "message": (
                            f"{asset_id}@{usage['locator']} 读取期间被修改，"
                            "本次摘要不可作为稳定基准"
                        ),
                        "block_completeness": blocking,
                        "affects": [asset_id],
                        "notion_task": spec.notion_task,
                    }
                )

            probe_status = (content.get("media_metadata") or {}).get("probe_status")

            if content["verification"] == "mismatch":
                limitations.append(
                    {
                        "code": "content_type_mismatch",
                        "message": (
                            f"{asset_id}@{usage['locator']} 声明为媒体但容器不可识别"
                        ),
                        "block_completeness": blocking,
                        "affects": [asset_id],
                        "notion_task": spec.notion_task,
                    }
                )
            elif (
                content["kind"] == "source_video"
                and content["availability"] == "present"
                and content["verification"] == "not_checked"
                and probe_status in {"timeout", "error", "skipped"}
            ):
                if probe_status == "skipped":
                    code = "media_probe_unavailable"
                    message = (
                        f"{asset_id}@{usage['locator']} 环境缺少 ffprobe，"
                        "媒体有效性未核验"
                    )
                else:
                    code = "media_probe_failed"
                    message = (
                        f"{asset_id}@{usage['locator']} 容器元数据探测未通过，"
                        "有效媒体性未确认"
                    )
                limitations.append(
                    {
                        "code": code,
                        "message": message,
                        "block_completeness": blocking,
                        "affects": [asset_id],
                        "notion_task": spec.notion_task,
                    }
                )

    run_refs, history_limitations = _import_historical_runs(
        config.historical_jobs, roots
    )
    limitations.extend(history_limitations)

    manifest = {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "package_id": config.package_id,
        "generated_at": _utc_now(),
        "baseline": config.baseline,
        "tooling": {
            "name": "research_evidence",
            "revision": detect_tooling_revision(),
            "config_sha256": config_core_digest(config),
        },
        "assets": assets,
        "run_refs": run_refs,
        "checks": checks,
        "completeness": _completeness(assets, limitations),
        "limitations": limitations,
    }

    locations = {
        "schema_version": LOCATIONS_SCHEMA_VERSION,
        "package_id": config.package_id,
        "source_roots": {
            root.root_id: root.model_dump() for root in config.source_roots
        },
        "assets": location_assets,
    }

    schema_result = _check_schema(manifest)
    if not schema_result.ok:
        raise BuildError(f"生成的 manifest 不符合契约: {schema_result.detail}")

    return manifest, locations, checks


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _git_output(args: list[str]) -> str | None:
    import subprocess

    try:
        completed = subprocess.run(
            ["git", *args],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
            cwd=str(Path(__file__).resolve().parents[3]),
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if completed.returncode != 0:
        return None
    return completed.stdout.strip()


def detect_tooling_revision() -> dict[str, Any]:
    """Record the indexing tool's own version, independently of the analysis baseline.

    A missing git environment yields an explicit unknown rather than a guess.
    """
    commit = _git_output(["rev-parse", "HEAD"])
    dirty = _git_output(["status", "--porcelain", "--", *TOOLING_PATHS])

    if not commit:
        return {
            "label": "tooling",
            "status": "unknown",
            "commit": None,
            "worktree_clean": None,
            "dirty_patch": {
                "status": "unknown",
                "sha256": None,
                "reason": "无法读取 git 版本，索引工具版本未知",
            },
            "note": None,
        }

    clean = dirty == ""
    return {
        "label": "tooling",
        "status": "known",
        "commit": commit,
        "worktree_clean": clean,
        "dirty_patch": (
            {"status": "known", "sha256": EMPTY_PATCH_SHA256}
            if clean
            else {
                "status": "unknown",
                "sha256": None,
                "reason": "工作区存在未提交改动，未记录 patch 摘要",
            }
        ),
        "note": None,
    }


def config_core_digest(config: BuildConfig) -> str:
    """Digest the portable part of the config: no local paths, no root ids mapping to paths."""
    import hashlib

    core = {
        "package_id": config.package_id,
        "assets": [
            {
                "root_id": spec.root_id,
                "relative_path": spec.relative_path,
                "kind": spec.kind,
                "usage_kind": spec.usage_kind,
                "requirement": spec.requirement,
                "asset_id": spec.asset_id,
                "notion_task": spec.notion_task,
                "view_role": spec.view_role,
                "time_base": spec.time_base,
            }
            for spec in config.assets
        ],
        "historical_jobs": [
            {"root_id": job.root_id, "relative_path": job.relative_path}
            for job in config.historical_jobs
        ],
        "baseline": config.baseline,
    }
    payload = json.dumps(core, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def write_package(
    output_dir: Path,
    manifest: dict[str, Any],
    locations: dict[str, Any],
) -> tuple[Path, Path, Path]:
    """Write the three package files. Refuses to overwrite anything."""
    target = Path(output_dir)
    target.mkdir(parents=True, exist_ok=True)

    manifest_path = target / MANIFEST_FILENAME
    checks_path = target / CHECKS_FILENAME
    locations_path = target / LOCATIONS_FILENAME

    payloads = (
        (manifest_path, manifest),
        (checks_path, {"checks": manifest.get("checks", [])}),
        (locations_path, locations),
    )
    for path, payload in payloads:
        if path.exists():
            raise BuildError(f"目标文件已存在，拒绝覆写: {path}")

    for path, payload in payloads:
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    return manifest_path, locations_path, checks_path


# --- verify -----------------------------------------------------------------


def _check_schema(manifest: Any) -> VerifyCheck:
    try:
        from jsonschema import Draft202012Validator
    except ImportError:  # pragma: no cover - dependency is declared
        return VerifyCheck("schema_valid", False, "jsonschema 未安装，无法校验")

    if not SCHEMA_PATH.is_file():
        return VerifyCheck("schema_valid", False, f"缺少契约文件: {SCHEMA_PATH}")

    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    errors = sorted(
        Draft202012Validator(schema).iter_errors(manifest), key=lambda e: list(e.path)
    )
    if not errors:
        return VerifyCheck("schema_valid", True)
    first = errors[0]
    location = "/".join(str(part) for part in first.absolute_path) or "<root>"
    return VerifyCheck(
        "schema_valid", False, f"{location}: {first.message}（共 {len(errors)} 处）"
    )


def verify_package(
    package_dir: Path,
    *,
    deep: bool = False,
    require_locations: bool = True,
) -> VerifyReport:
    """Verify a package. ``deep`` also recomputes digests from the local mapping.

    ``require_locations=False`` is used for shareable packages, which contain no
    local mapping by design.
    """
    target = Path(package_dir)
    if not target.is_dir():
        raise VerifyError(f"包目录不存在: {target}")

    checks: list[VerifyCheck] = []

    manifest_path = target / MANIFEST_FILENAME
    if not manifest_path.is_file():
        return VerifyReport(
            False, (VerifyCheck("manifest_present", False, f"缺少 {MANIFEST_FILENAME}"),)
        )
    checks.append(VerifyCheck("manifest_present", True))

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        checks.append(VerifyCheck("manifest_json", False, str(error)))
        return VerifyReport(False, tuple(checks))
    checks.append(VerifyCheck("manifest_json", True))

    checks.append(_check_schema(manifest))

    tooling = manifest.get("tooling")
    has_tooling = (
        isinstance(tooling, dict)
        and isinstance(tooling.get("revision"), dict)
        and bool(tooling["revision"])
    )
    checks.append(
        VerifyCheck(
            "tooling_recorded",
            has_tooling,
            None
            if has_tooling
            else "缺少 tooling.revision：索引工具版本必须与科研基线分开记录",
        )
    )

    offenders = find_local_paths(manifest)
    checks.append(
        VerifyCheck(
            "no_local_paths",
            not offenders,
            "; ".join(offenders[:3]) if offenders else None,
        )
    )

    assets = manifest.get("assets") or []
    asset_ids = [asset.get("asset_id") for asset in assets if isinstance(asset, dict)]
    duplicate_ids = sorted({aid for aid in asset_ids if asset_ids.count(aid) > 1})
    checks.append(
        VerifyCheck(
            "unique_asset_ids",
            not duplicate_ids,
            f"重复: {duplicate_ids}" if duplicate_ids else None,
        )
    )

    all_locators: list[str] = []
    for asset in assets:
        if not isinstance(asset, dict):
            continue
        for usage in asset.get("usages") or []:
            if isinstance(usage, dict) and usage.get("locator"):
                all_locators.append(str(usage["locator"]))
    duplicate_locators = sorted(
        {locator for locator in all_locators if all_locators.count(locator) > 1}
    )
    checks.append(
        VerifyCheck(
            "unique_locators",
            not duplicate_locators,
            f"重复: {duplicate_locators}" if duplicate_locators else None,
        )
    )

    known = set(asset_ids)
    dangling: list[str] = []
    for run in manifest.get("run_refs") or []:
        if not isinstance(run, dict):
            continue
        for asset_id in run.get("consumes") or []:
            if asset_id not in known:
                dangling.append(f"run_refs.{run.get('run_id')}→{asset_id}")
    for check in manifest.get("checks") or []:
        if not isinstance(check, dict):
            continue
        target_id = check.get("target_asset_id")
        if target_id not in known:
            dangling.append(f"checks.{check.get('check_id')}→{target_id}")
    checks.append(
        VerifyCheck(
            "references_resolve",
            not dangling,
            f"悬空引用: {dangling[:3]}" if dangling else None,
        )
    )

    usage_gaps: list[str] = []
    for asset in assets:
        if not isinstance(asset, dict):
            continue
        if not asset.get("usages"):
            usage_gaps.append(str(asset.get("asset_id")))
    checks.append(
        VerifyCheck(
            "usages_present",
            not usage_gaps,
            f"缺少使用关系: {usage_gaps[:3]}" if usage_gaps else None,
        )
    )

    locations_payload: dict[str, Any] | None = None
    locations_path = target / LOCATIONS_FILENAME
    if not locations_path.is_file():
        checks.append(
            VerifyCheck(
                "locations_present",
                not require_locations,
                (
                    f"缺少 {LOCATIONS_FILENAME}（本机映射应保留在本机）"
                    if require_locations
                    else "分享包按约定不含本机映射"
                ),
            )
        )
    else:
        try:
            locations_payload = json.loads(locations_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as error:
            checks.append(VerifyCheck("locations_json", False, str(error)))
        else:
            checks.append(VerifyCheck("locations_json", True))
            same_package = (
                locations_payload.get("package_id") == manifest.get("package_id")
            )
            checks.append(
                VerifyCheck(
                    "locations_package_matches",
                    same_package,
                    None if same_package else "package_id 不一致",
                )
            )
            mapped = set((locations_payload.get("assets") or {}).keys())
            missing = sorted(known - mapped)
            extra = sorted(mapped - known)
            checks.append(
                VerifyCheck(
                    "locations_cover_assets",
                    not missing and not extra,
                    (
                        None
                        if not missing and not extra
                        else f"缺 {missing[:3]}，多 {extra[:3]}"
                    ),
                )
            )

    # 必需项与非必需项必须区别对待：只有带 required 使用关系的资产才参与判定。
    required_gaps: list[str] = []
    for asset in assets:
        if not isinstance(asset, dict):
            continue
        required_usages = [
            usage
            for usage in asset.get("usages") or []
            if isinstance(usage, dict) and usage.get("requirement") == "required"
        ]
        if not required_usages:
            continue
        if (
            asset.get("availability") != "present"
            or asset.get("verification") != "verified"
        ):
            required_gaps.append(str(asset.get("asset_id")))
    declared_complete = manifest.get("completeness") == "complete"
    checks.append(
        VerifyCheck(
            "completeness_consistent",
            not (declared_complete and required_gaps),
            (
                f"声称完整但必需项未达标: {required_gaps[:3]}"
                if declared_complete and required_gaps
                else None
            ),
        )
    )

    if deep:
        if locations_payload is None:
            # 没有本机映射就没有深度核验：不能把「无法访问」记成「已通过」。
            checks.append(
                VerifyCheck(
                    "deep_possible",
                    False,
                    "缺少本机映射，深度核验未执行；便携包不得声称已完成深度校验",
                )
            )
        else:
            checks.append(VerifyCheck("deep_possible", True))
            mismatched, unreadable = _deep_check(manifest, locations_payload)
            checks.append(
                VerifyCheck(
                    "deep_digest_match",
                    not mismatched,
                    f"内容已变更: {mismatched[:3]}" if mismatched else None,
                )
            )
            checks.append(
                VerifyCheck(
                    "deep_assets_readable",
                    not unreadable,
                    f"重新核验未通过: {unreadable[:3]}" if unreadable else None,
                )
            )

    return VerifyReport(all(check.ok for check in checks), tuple(checks))


def _deep_check(
    manifest: dict[str, Any], locations: dict[str, Any]
) -> tuple[list[str], list[str]]:
    """Recompute digests for every usage location, not one representative.

    Returns (content changed, could not be verified). A changed file is evidence
    of drift; an unreadable location may simply be an unmounted disk. Both are
    reported — neither is silently passed.
    """
    roots = {
        root_id: entry.get("path")
        for root_id, entry in (locations.get("source_roots") or {}).items()
        if isinstance(entry, dict)
    }
    mismatched: list[str] = []
    unreadable: list[str] = []

    for asset in manifest.get("assets") or []:
        if not isinstance(asset, dict):
            continue
        expected = (asset.get("digest") or {}).get("sha256")
        if not expected:
            continue

        asset_id = str(asset.get("asset_id"))
        usages = asset.get("usages") or []
        if not usages:
            unreadable.append(f"{asset_id}:无使用关系，无法核验")
            continue

        for usage in usages:
            if not isinstance(usage, dict):
                continue
            role = str(usage.get("view_role") or "unspecified")
            locator = str(usage.get("locator") or "")
            label = f"{asset_id}@{role}"

            try:
                resolved = resolve_locator(locator, roots)
            except Exception:
                unreadable.append(f"{label}:无法解析定位")
                continue

            result = inspect_file(resolved, expected_sha256=expected)
            if result.verification == "mismatch":
                mismatched.append(label)
            elif result.verification != "verified":
                unreadable.append(f"{label}:{result.verification}")

    return mismatched, unreadable


def export_shareable_package(
    package_dir: Path, output_dir: Path
) -> tuple[Path, Path]:
    """Copy only the shareable part of a package.

    ``locations.local.json`` stays behind by construction: a shared index must not
    carry the author's directory layout. The manifest is re-checked for absolute
    paths on the way out, so a package built by an older version cannot leak one.
    """
    source = Path(package_dir)
    manifest_path = source / MANIFEST_FILENAME
    if not manifest_path.is_file():
        raise BuildError(f"缺少 {MANIFEST_FILENAME}: {source}")

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise BuildError(f"{MANIFEST_FILENAME} 不是合法 JSON") from error

    offenders = find_local_paths(manifest)
    if offenders:
        raise BuildError(
            f"manifest 含本机绝对路径，拒绝导出: {'; '.join(offenders[:3])}"
        )

    checks_source = source / CHECKS_FILENAME
    checks_payload: Any = {"checks": manifest.get("checks", [])}
    if checks_source.is_file():
        try:
            checks_payload = json.loads(checks_source.read_text(encoding="utf-8"))
        except json.JSONDecodeError as error:
            raise BuildError(f"{CHECKS_FILENAME} 不是合法 JSON") from error
        checks_offenders = find_local_paths(checks_payload)
        if checks_offenders:
            raise BuildError(
                f"checks 含本机绝对路径，拒绝导出: {'; '.join(checks_offenders[:3])}"
            )

    target = Path(output_dir)
    assert_output_is_safe(target, {})
    target.mkdir(parents=True, exist_ok=True)

    manifest_out = target / MANIFEST_FILENAME
    checks_out = target / CHECKS_FILENAME
    for path in (manifest_out, checks_out):
        if path.exists():
            raise BuildError(f"目标文件已存在，拒绝覆写: {path}")

    manifest_out.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    checks_out.write_text(
        json.dumps(checks_payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return manifest_out, checks_out
