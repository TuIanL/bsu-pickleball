"""Command line entry for research evidence indexing.

Two subcommands, both strictly read-only with respect to source assets:

``build``  turns an explicit config into a package directory,
``verify`` checks an existing package without recomputing digests.

This module must stay importable without the application, the database, the
model runtime or the FastAPI lifespan.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from .builder import (
    BuildError,
    VerifyError,
    assert_output_is_safe,
    build_manifest,
    export_shareable_package,
    load_build_config,
    verify_package,
    write_package,
)

EXIT_OK = 0
EXIT_VERIFY_FAILED = 1
EXIT_ERROR = 2
EXIT_INTERRUPTED = 130


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="research_evidence",
        description="科研证据索引：受控构建与校验（不扫描磁盘，不改动源资产）",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    build = subparsers.add_parser(
        "build", help="按显式配置生成证据包", description="生成 manifest/checks/位置映射"
    )
    build.add_argument("--config", required=True, type=Path, help="构建配置 JSON")
    build.add_argument("--output", required=True, type=Path, help="新的空输出目录")
    build.add_argument(
        "--timeout-seconds",
        type=float,
        default=600.0,
        help="单个文件摘要计算超时（秒），默认 600",
    )

    verify = subparsers.add_parser(
        "verify", help="校验已有证据包", description="校验结构、引用与路径泄露"
    )
    verify.add_argument("--package", required=True, type=Path, help="包目录")
    verify.add_argument(
        "--deep",
        action="store_true",
        help="按本机映射重算摘要，检测内容是否被改动",
    )
    verify.add_argument(
        "--shareable",
        action="store_true",
        help="按分享包口径校验：允许缺少本机映射",
    )

    publish = subparsers.add_parser(
        "publish",
        help="导出可分享副本",
        description="只复制 manifest 与 checks，本机映射留在原处",
    )
    publish.add_argument("--package", required=True, type=Path, help="本机包目录")
    publish.add_argument("--output", required=True, type=Path, help="新的空输出目录")

    return parser


def _run_build(args: argparse.Namespace) -> int:
    try:
        config = load_build_config(args.config)
        assert_output_is_safe(args.output, config.roots_by_id())
        manifest, locations, _checks = build_manifest(
            config, timeout_seconds=args.timeout_seconds
        )
        write_package(args.output, manifest, locations)
    except BuildError as error:
        print(f"build 失败: {error}", file=sys.stderr)
        return EXIT_ERROR

    print(f"包已生成: {args.output}")
    print(f"  package_id: {manifest['package_id']}")
    print(f"  completeness: {manifest['completeness']}")
    print(f"  assets: {len(manifest['assets'])}")
    print(f"  limitations: {len(manifest['limitations'])}")
    for limitation in manifest["limitations"]:
        flag = "阻断" if limitation["block_completeness"] else "提示"
        print(f"    [{flag}] {limitation['code']}: {limitation['message']}")
    return EXIT_OK


def _run_verify(args: argparse.Namespace) -> int:
    try:
        report = verify_package(
            args.package, deep=args.deep, require_locations=not args.shareable
        )
    except VerifyError as error:
        print(f"verify 失败: {error}", file=sys.stderr)
        return EXIT_ERROR

    for check in report.checks:
        mark = "OK  " if check.ok else "FAIL"
        suffix = f" — {check.detail}" if check.detail else ""
        print(f"  [{mark}] {check.name}{suffix}")

    if report.ok:
        print("校验通过")
        return EXIT_OK

    print(f"校验未通过：{len(report.failures)} 项失败", file=sys.stderr)
    return EXIT_VERIFY_FAILED


def _run_publish(args: argparse.Namespace) -> int:
    try:
        manifest_path, checks_path = export_shareable_package(
            args.package, args.output
        )
    except BuildError as error:
        print(f"publish 失败: {error}", file=sys.stderr)
        return EXIT_ERROR

    print(f"分享包已导出: {args.output}")
    print(f"  {manifest_path.name}、{checks_path.name}")
    print("  locations.local.json 未导出（本机路径不随包分享）")
    return EXIT_OK


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "build":
            return _run_build(args)
        if args.command == "publish":
            return _run_publish(args)
        return _run_verify(args)
    except KeyboardInterrupt:
        print("已中断；源资产未被修改", file=sys.stderr)
        return EXIT_INTERRUPTED
