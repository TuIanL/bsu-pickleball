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
from .locations import (
    LOCATIONS_SCHEMA_VERSION,
    SourceRoot,
    build_locator,
    find_local_paths,
    resolve_locator,
)
from .media_probe import DEFAULT_PROBE_TIMEOUT_SECONDS, probe_media

MANIFEST_SCHEMA_VERSION = "pb.research-evidence-manifest.v1.0"
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
    notes: tuple[str, ...] = ()

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
                    notes=tuple(entry.get("notes") or ()),
                )
            )
        except KeyError as error:
            raise BuildError(f"asset 缺少字段: {error}") from error
    return tuple(assets)


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
    cancel: Callable[[], bool] | None,
) -> tuple[dict[str, Any], list[dict[str, Any]], str | None]:
    """Return (asset entry, checks, admission warning)."""
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
        probe = probe_media(resolved, timeout_seconds=DEFAULT_PROBE_TIMEOUT_SECONDS)

    usage = classify_usage_kind(
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
                usage_kind=usage.usage_kind,
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
            "scope": "授权来源根内路径解析",
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
                "scope": "全文件分块 SHA-256",
                "detail": inspection.detail,
            }
        )

    if probe is not None:
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

    # 构建阶段的摘要计算即建立基准：算出完整摘要视为核验成功，
    # 否则一律 not_checked/unknown，避免把「没比过」写成「比过了」。
    if inspection.availability == "present":
        verification = "verified" if inspection.sha256 else "not_checked"
    elif inspection.availability == "missing":
        verification = "unknown"
    else:
        verification = "not_checked"

    entry: dict[str, Any] = {
        "asset_id": asset_id,
        "kind": spec.kind,
        "usage_kind": usage.usage_kind,
        "usage_basis": usage.to_manifest_field(),
        "requirement": spec.requirement,
        "locator": spec.locator,
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
        "provenance": {
            "source_root_id": root.root_id,
            "source_kind": root.source_kind,
            "originated_at": None,
            "note": None,
        },
        "media_metadata": (
            None
            if probe is None or probe.status != "ok"
            else {
                "duration_seconds": probe.duration_seconds,
                "width": probe.width,
                "height": probe.height,
                "fps_nominal": probe.fps_nominal,
                "frame_count": probe.frame_count,
                "probe_status": "ok",
            }
        ),
        "notes": list(spec.notes),
    }
    return entry, checks, warning


# --- build ------------------------------------------------------------------


def _completeness(assets: list[dict[str, Any]], limitations: list[dict[str, Any]]) -> str:
    if any(limit["block_completeness"] for limit in limitations):
        return "partial"
    for asset in assets:
        if asset["requirement"] != "required":
            continue
        if asset["availability"] != "present" or asset["verification"] != "verified":
            return "partial"
    return "complete"


def build_manifest(
    config: BuildConfig,
    *,
    timeout_seconds: float = 600.0,
    cancel: Callable[[], bool] | None = None,
) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
    """Build (manifest, locations, extra checks) without touching the disk output."""
    roots = config.roots_by_id()
    roots_by_key = config.roots_by_key()

    assets: list[dict[str, Any]] = []
    checks: list[dict[str, Any]] = []
    location_assets: dict[str, Any] = {}
    limitations: list[dict[str, Any]] = []

    pending: dict[str, list[tuple[AssetSpec, dict[str, Any], list[dict[str, Any]], str | None]]] = {}

    for spec in config.assets:
        root = roots_by_key.get(spec.root_id)
        if root is None:
            raise BuildError(f"asset 引用了未声明的来源根: {spec.root_id}")

        try:
            resolved = resolve_locator(spec.locator, roots)
        except Exception as error:
            raise BuildError(f"无法解析 {spec.locator}: {error}") from error

        entry, asset_checks, warning = _build_asset_entry(
            spec,
            root,
            resolved,
            timeout_seconds=timeout_seconds,
            cancel=cancel,
        )
        pending.setdefault(entry["asset_id"], []).append(
            (spec, entry, asset_checks, warning)
        )

    # 内容身份相同的多个位置归并为一个资产：路径不是 ID，副本不重复登记。
    for asset_id, group in sorted(pending.items()):
        group.sort(key=lambda item: item[1]["locator"])
        spec, entry, asset_checks, warning = group[0]
        alternates = [item[1]["locator"] for item in group[1:]]

        kinds = {item[1]["kind"] for item in group}
        if len(kinds) > 1:
            raise BuildError(
                f"同一内容 {asset_id} 被声明为不同 kind: {sorted(kinds)}；"
                "请确认这是否其实是不同资产"
            )

        if alternates:
            entry = dict(entry)
            entry["notes"] = list(entry["notes"]) + [
                f"同内容副本（未重复登记）：{locator}" for locator in alternates
            ]

        assets.append(entry)
        checks.extend(asset_checks)
        location_assets[asset_id] = {
            "locator": entry["locator"],
            "relative_path": spec.relative_path,
            "source_root_id": spec.root_id,
            "alternate_locators": alternates,
        }

        if warning:
            limitations.append(
                {
                    "code": "formal_input_rejected",
                    "message": f"{asset_id}: {warning}",
                    "block_completeness": entry["requirement"] == "required",
                    "affects": [asset_id],
                    "notion_task": None,
                }
            )

        if entry["availability"] != "present":
            limitations.append(
                {
                    "code": f"asset_{entry['availability']}",
                    "message": f"{asset_id} 不可用，未纳入核验",
                    "block_completeness": entry["requirement"] == "required",
                    "affects": [asset_id],
                    "notion_task": None,
                }
            )

    manifest = {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "package_id": config.package_id,
        "generated_at": _utc_now(),
        "baseline": config.baseline,
        "assets": assets,
        "run_refs": [],
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

    locators = [
        asset.get("locator") for asset in assets if isinstance(asset, dict)
    ]
    duplicate_locators = sorted({loc for loc in locators if locators.count(loc) > 1})
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

    # 必需项与非必需项必须区别对待：只有 required 不达标才否定 complete。
    required_gaps = [
        asset.get("asset_id")
        for asset in assets
        if isinstance(asset, dict)
        and asset.get("requirement") == "required"
        and (
            asset.get("availability") != "present"
            or asset.get("verification") != "verified"
        )
    ]
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
            checks.append(
                VerifyCheck("deep_digest_match", False, "缺少本机映射，无法重算摘要")
            )
        else:
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
    """Recompute digests from the local mapping.

    Returns (content changed, could not be verified). The two are deliberately
    separated: a changed file is evidence of tampering, while an unreadable file
    may simply be an unmounted disk.
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
        if asset.get("availability") != "present":
            continue
        expected = (asset.get("digest") or {}).get("sha256")
        if not expected:
            continue

        asset_id = str(asset.get("asset_id"))
        try:
            resolved = resolve_locator(asset.get("locator", ""), roots)
        except Exception:
            unreadable.append(f"{asset_id}:无法解析定位")
            continue

        result = inspect_file(resolved, expected_sha256=expected)
        if result.verification == "mismatch":
            mismatched.append(asset_id)
        elif result.verification != "verified":
            unreadable.append(f"{asset_id}:{result.verification}")

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
