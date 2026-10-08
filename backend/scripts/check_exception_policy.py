"""Check newly changed broad, silent exception handlers without flagging the backlog."""
from __future__ import annotations

import argparse
import ast
from pathlib import Path
import re
import subprocess


def policy_errors(source: str, changed_lines: set[int], path: str) -> list[str]:
    tree = ast.parse(source, filename=path)
    parents = {child: node for node in ast.walk(tree) for child in ast.iter_child_nodes(node)}
    errors = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for decorator in node.decorator_list:
                if not isinstance(decorator, ast.Call) or not _is_swallow(decorator.func):
                    continue
                if not changed_lines.intersection(range(node.lineno, node.end_lineno + 1)):
                    continue
                reason = next((keyword.value for keyword in decorator.keywords if keyword.arg == "why"), None)
                if not isinstance(reason, ast.Constant) or not isinstance(reason.value, str) or not reason.value.strip():
                    errors.append(f"{path}:{decorator.lineno}: @swallow requires a non-empty literal why")
        if not isinstance(node, ast.ExceptHandler) or not _is_broad(node.type):
            continue
        if not all(isinstance(statement, (ast.Pass, ast.Continue)) for statement in node.body):
            continue
        if not changed_lines.intersection(range(node.lineno, node.end_lineno + 1)):
            continue
        parent = parents.get(node)
        while parent is not None and not isinstance(parent, (ast.FunctionDef, ast.AsyncFunctionDef)):
            parent = parents.get(parent)
        declared = parent is not None and any(
            isinstance(decorator, ast.Call) and _is_swallow(decorator.func)
            and any(keyword.arg == "why" and isinstance(keyword.value, ast.Constant)
                    and isinstance(keyword.value.value, str) and keyword.value.value.strip()
                    for keyword in decorator.keywords)
            for decorator in parent.decorator_list
        )
        if not declared:
            errors.append(f"{path}:{node.lineno}: silent broad exception needs an explicit @swallow(why=...) policy")
    return errors


def _is_swallow(node: ast.expr) -> bool:
    return isinstance(node, ast.Name) and node.id == "swallow" or isinstance(node, ast.Attribute) and node.attr == "swallow"


def _is_broad(node: ast.expr | None) -> bool:
    return node is None or isinstance(node, ast.Name) and node.id in {"Exception", "BaseException"} or isinstance(node, ast.Tuple) and any(_is_broad(item) for item in node.elts)


def changed_python_lines(base: str) -> dict[str, set[int]]:
    diff = subprocess.check_output(["git", "diff", "--no-ext-diff", "--unified=0", base, "--", "backend/app"], text=True)
    changed = {}
    path = None
    for line in diff.splitlines():
        if line.startswith("+++ b/"):
            path = line[6:]
        elif line.startswith("@@") and path and path.endswith(".py"):
            match = re.search(r"\+(\d+)(?:,(\d+))? @@", line)
            if match:
                start, count = int(match[1]), int(match[2] or 1)
                changed.setdefault(path, set()).update(range(start, start + count))
    untracked = subprocess.check_output(["git", "ls-files", "--others", "--exclude-standard", "--", "backend/app"], text=True)
    for path in untracked.splitlines():
        if path.endswith(".py"):
            changed[path] = set(range(1, len(Path(path).read_text().splitlines()) + 1))
    return changed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", default="HEAD", help="Git ref to compare against; CI passes the PR base or prior push SHA")
    args = parser.parse_args()
    errors = []
    changed = changed_python_lines(args.base)
    for path, lines in changed.items():
        if Path(path).is_file():
            errors.extend(policy_errors(Path(path).read_text(), lines, path))
    for error in errors:
        print(error)
    print(f"Exception policy: {len(changed)} changed Python files, {len(errors)} violations")
    return bool(errors)


if __name__ == "__main__":
    raise SystemExit(main())
