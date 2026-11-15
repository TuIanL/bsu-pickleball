"""Usage classification and formal-input admission for research evidence.

Three rules drive this module:

1. A file extension never proves a container. A text file renamed to ``.mp4``
   must not be admitted as formal research input.
2. Nothing is promoted to ``real`` by default. Without an operator declaration
   or an explicit source-root policy the answer is ``unknown``.
3. Synthetic media can be a perfectly valid AVI and still be a fixture. Content
   validity and research eligibility are separate judgements.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

UsageKind = Literal["real", "fixture", "unknown"]
ContainerKind = Literal["mp4", "avi", "matroska", "mpegts", "unknown"]
UsageBasis = Literal[
    "operator_declared",
    "root_policy",
    "container_unverified",
    "no_evidence",
]

HEADER_PROBE_BYTES = 4096
_MPEGTS_SYNC_BYTE = 0x47
_MPEGTS_PACKET_SIZE = 188

# Suffix to the containers it may legitimately carry. A suffix absent from this
# table is not rejected by itself; it simply cannot be used to authenticate a
# container.
EXPECTED_CONTAINERS: dict[str, frozenset[str]] = {
    ".mp4": frozenset({"mp4"}),
    ".m4v": frozenset({"mp4"}),
    ".mov": frozenset({"mp4"}),
    ".avi": frozenset({"avi"}),
    ".mkv": frozenset({"matroska"}),
    ".ts": frozenset({"mpegts"}),
}


class ClassificationError(ValueError):
    """Base error for classification and admission failures."""


class AdmissionError(ClassificationError):
    """Raised when a file may not enter formal research input."""


class UnreadableMediaError(ClassificationError):
    """Raised when the header of a candidate media file cannot be read."""


@dataclass(frozen=True)
class ClassificationEvidence:
    """A usage decision together with the evidence that produced it."""

    usage_kind: UsageKind
    basis: UsageBasis
    reason: str

    def to_manifest_field(self) -> dict[str, str]:
        """Shape used by the optional ``usage_basis`` manifest property."""
        return {"basis": self.basis, "reason": self.reason}


def _looks_like_mpegts(head: bytes) -> bool:
    if len(head) < _MPEGTS_PACKET_SIZE + 1:
        return False
    if head[0] != _MPEGTS_SYNC_BYTE:
        return False
    return head[_MPEGTS_PACKET_SIZE] == _MPEGTS_SYNC_BYTE


def probe_container(path: Path, *, max_bytes: int = HEADER_PROBE_BYTES) -> ContainerKind:
    """Identify the container from the file header only.

    This never decodes and never shells out, so it stays safe on large files and
    on a slow external disk.
    """
    try:
        with Path(path).open("rb") as handle:
            head = handle.read(max_bytes)
    except OSError as error:  # pragma: no cover - surfaced as a typed error
        raise UnreadableMediaError(f"cannot read media header: {path}") from error

    if len(head) >= 12 and head[4:8] == b"ftyp":
        return "mp4"
    if len(head) >= 12 and head[:4] == b"RIFF" and head[8:12] == b"AVI ":
        return "avi"
    if head[:4] == b"\x1a\x45\xdf\xa3":
        return "matroska"
    if _looks_like_mpegts(head):
        return "mpegts"
    return "unknown"


def extension_matches_container(suffix: str, container: ContainerKind) -> bool:
    """Return True when the suffix is consistent with the detected container."""
    expected = EXPECTED_CONTAINERS.get(suffix.lower())
    if expected is None:
        return False
    return container in expected


def classify_usage_kind(
    *,
    declared: UsageKind | None,
    root_policy: UsageKind | None,
    container: ContainerKind,
) -> ClassificationEvidence:
    """Decide how a file may be used, and record why.

    Precedence is operator declaration, then source-root policy. When neither is
    available the result is ``unknown`` even if the bytes look like a real video,
    because looking decodable is not evidence of research provenance.
    """
    if declared is not None:
        return ClassificationEvidence(
            usage_kind=declared,
            basis="operator_declared",
            reason=f"操作者显式声明 usage_kind={declared}",
        )
    if root_policy is not None:
        return ClassificationEvidence(
            usage_kind=root_policy,
            basis="root_policy",
            reason=f"来源根策略声明 usage_kind={root_policy}",
        )
    if container == "unknown":
        return ClassificationEvidence(
            usage_kind="unknown",
            basis="container_unverified",
            reason="文件头无法识别为受支持容器，来源与用途均不可判定",
        )
    return ClassificationEvidence(
        usage_kind="unknown",
        basis="no_evidence",
        reason="既无操作者声明也无来源根策略，容器可识别也不足以认证为正式素材",
    )


def assert_formal_input_eligible(
    *,
    usage_kind: UsageKind,
    container: ContainerKind,
    suffix: str,
    digest_status: str,
) -> None:
    """Raise AdmissionError unless the file may enter formal research input."""
    if usage_kind == "fixture":
        raise AdmissionError("合成或测试夹具不得进入正式科研输入")
    if usage_kind == "unknown":
        raise AdmissionError("用途未知的文件不得进入正式科研输入")
    if usage_kind != "real":
        raise AdmissionError(f"不支持的 usage_kind: {usage_kind!r}")

    if container == "unknown":
        raise AdmissionError("文件头不是受支持的媒体容器，疑似伪视频或损坏文件")
    if not extension_matches_container(suffix, container):
        raise AdmissionError(
            f"扩展名 {suffix or '<none>'} 与实际容器 {container} 不一致，疑似改名伪装"
        )
    if digest_status != "known":
        raise AdmissionError("内容摘要未知的文件不得作为正式科研输入")


def classify_path_for_admission(
    path: Path,
    *,
    declared: UsageKind | None = None,
    root_policy: UsageKind | None = None,
    digest_status: str = "unknown",
) -> ClassificationEvidence:
    """Convenience wrapper: probe, classify, then enforce formal-input rules."""
    container = probe_container(path)
    evidence = classify_usage_kind(
        declared=declared, root_policy=root_policy, container=container
    )
    assert_formal_input_eligible(
        usage_kind=evidence.usage_kind,
        container=container,
        suffix=Path(path).suffix,
        digest_status=digest_status,
    )
    return evidence
