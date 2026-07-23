# -*- coding: utf-8 -*-
"""argparse CLI 实现。"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Optional, Sequence

from core import git_ops
from core.remote import validate_remote_url
from core.sensitive import find_sensitive_files, format_sensitive_warning
from core.workflow import (
    bootstrap,
    checkout_workflow,
    list_branches_workflow,
    pull_workflow,
    ship,
)


def _print_ok(text: str) -> None:
    print(text)


def _print_err(text: str) -> None:
    print(text, file=sys.stderr)


def _resolve_path(path: Optional[str]) -> Path:
    return Path(path or ".").expanduser().resolve()


def cmd_status(args: argparse.Namespace) -> int:
    path = _resolve_path(args.path)
    check = git_ops.ensure_git_available()
    if not check.ok:
        _print_err(check.message)
        return 1

    if not path.exists():
        _print_err(f"路径不存在: {path}")
        return 1

    if not git_ops.is_repo(path):
        _print_err(f"不是 Git 仓库: {path}")
        return 1

    branch = git_ops.current_branch(path)
    remote = git_ops.remote_get(path, name="origin")
    status = git_ops.status_short(path)

    _print_ok(f"仓库: {path}")
    if branch.ok and branch.stdout:
        _print_ok(f"分支: {branch.stdout}")
    else:
        _print_ok("分支: (未知/detached)")
    if remote.ok:
        _print_ok(f"远程 origin: {remote.stdout}")
    else:
        _print_ok("远程 origin: (未配置)")
    _print_ok(f"upstream: {'已设置' if git_ops.has_upstream(path) else '未设置'}")
    _print_ok("--- 状态 ---")
    if status.ok:
        text = status.stdout.strip() or "(干净工作区)"
        _print_ok(text)
        return 0
    _print_err(status.message or "获取状态失败")
    return status.code or 1


def cmd_init(args: argparse.Namespace) -> int:
    path = _resolve_path(args.path)
    branch = (args.branch or "main").strip() or "main"
    check = git_ops.ensure_git_available()
    if not check.ok:
        _print_err(check.message)
        return 1

    if git_ops.is_repo(path):
        _print_ok(f"已是 Git 仓库: {path}")
        return 0

    result = git_ops.init_repo(path, initial_branch=branch)
    if result.ok:
        _print_ok(f"已初始化仓库: {path}（分支 {branch}）")
        if result.stdout.strip():
            _print_ok(result.stdout.strip())
        return 0
    _print_err(f"初始化失败: {result.message}")
    return result.code or 1


def cmd_remote_set(args: argparse.Namespace) -> int:
    path = _resolve_path(args.path)
    url = (args.url or "").strip()
    check = git_ops.ensure_git_available()
    if not check.ok:
        _print_err(check.message)
        return 1

    if not url:
        _print_err("请通过 --url 指定远程地址")
        return 1
    if not validate_remote_url(url):
        _print_err(f"远程 URL 无效: {url}")
        return 1
    if not git_ops.is_repo(path):
        _print_err(f"不是 Git 仓库: {path}")
        return 1

    result = git_ops.remote_set_url(path, url, name="origin")
    if result.ok:
        _print_ok(f"已设置 origin → {url}")
        return 0
    _print_err(f"设置远程失败: {result.message}")
    return result.code or 1


def _print_workflow(result) -> int:
    for step in result.steps:
        _print_ok(f"  · {step}")
    if result.ok:
        _print_ok(result.message)
        if result.detail.strip():
            _print_ok("--- 摘要 ---")
            _print_ok(result.detail.strip())
        return 0
    _print_err(result.message)
    if result.detail.strip():
        _print_err(result.detail.strip())
    return 1


def cmd_diff(args: argparse.Namespace) -> int:
    path = _resolve_path(args.path)
    check = git_ops.ensure_git_available()
    if not check.ok:
        _print_err(check.message)
        return 1
    if not path.exists():
        _print_err(f"路径不存在: {path}")
        return 1
    if not git_ops.is_repo(path):
        _print_err(f"不是 Git 仓库: {path}")
        return 1

    paths = list(args.file) if getattr(args, "file", None) else None
    if args.stat_only:
        unstaged = git_ops.diff_stat(path, staged=False)
        staged = git_ops.diff_stat(path, staged=True)
        _print_ok("=== 未暂存 (--stat) ===")
        _print_ok((unstaged.stdout or "").strip() or "(无)")
        _print_ok("")
        _print_ok("=== 已暂存 (--stat) ===")
        _print_ok((staged.stdout or "").strip() or "(无)")
        return 0 if unstaged.ok or staged.ok else 1

    summary = git_ops.diff_summary(
        path,
        paths=paths,
        max_patch_chars=int(args.max_chars) if args.max_chars else 12000,
    )
    _print_ok(summary.rstrip())
    return 0


def cmd_bootstrap(args: argparse.Namespace) -> int:
    path = _resolve_path(args.path)
    remote = (args.remote or "").strip()
    message = args.message or ""
    branch = (args.branch or "main").strip() or "main"

    if not remote:
        _print_err("请通过 --remote 指定远程 URL")
        return 1

    result = bootstrap(
        path,
        remote_url=remote,
        message=message,
        branch=branch,
        dry_run=bool(args.dry_run),
        force=bool(args.force),
    )
    return _print_workflow(result)


def cmd_ship(args: argparse.Namespace) -> int:
    path = _resolve_path(args.path)
    message = args.message or ""
    result = ship(
        path,
        message=message,
        paths=None,
        dry_run=bool(args.dry_run),
        force=bool(args.force),
    )
    return _print_workflow(result)


def cmd_pull(args: argparse.Namespace) -> int:
    path = _resolve_path(args.path)
    result = pull_workflow(
        path,
        remote=(args.remote or "origin").strip() or "origin",
        branch=(args.branch or "").strip() or None,
        rebase=bool(args.rebase),
        dry_run=bool(args.dry_run),
    )
    return _print_workflow(result)


def cmd_branch_list(args: argparse.Namespace) -> int:
    path = _resolve_path(args.path)
    result = list_branches_workflow(path)
    return _print_workflow(result)


def cmd_checkout(args: argparse.Namespace) -> int:
    path = _resolve_path(args.path)
    result = checkout_workflow(
        path,
        args.name,
        create=bool(args.create),
        dry_run=bool(args.dry_run),
    )
    return _print_workflow(result)


def cmd_check_sensitive(args: argparse.Namespace) -> int:
    path = _resolve_path(args.path)
    check = git_ops.ensure_git_available()
    if not check.ok:
        _print_err(check.message)
        return 1
    if not path.exists() or not git_ops.is_repo(path):
        _print_err(f"不是 Git 仓库: {path}")
        return 1
    files = git_ops.list_changed_files(path)
    hits = find_sensitive_files(files)
    if not hits:
        _print_ok("未发现疑似敏感文件")
        return 0
    _print_err(format_sensitive_warning(hits))
    return 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="git-ship",
        description="Git Ship — 简洁的 Git 提交/推送小工具（CLI）",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_status = sub.add_parser("status", help="查看仓库状态")
    p_status.add_argument("--path", default=".", help="仓库路径，默认当前目录")
    p_status.set_defaults(func=cmd_status)

    p_diff = sub.add_parser("diff", help="查看变更摘要 / diff")
    p_diff.add_argument("--path", default=".", help="仓库路径，默认当前目录")
    p_diff.add_argument(
        "--stat-only",
        action="store_true",
        help="仅显示 --stat 统计，不输出 patch",
    )
    p_diff.add_argument(
        "--max-chars",
        type=int,
        default=12000,
        help="patch 最大字符数，超出截断（默认 12000）",
    )
    p_diff.add_argument(
        "file",
        nargs="*",
        help="可选：限定文件路径",
    )
    p_diff.set_defaults(func=cmd_diff)

    p_init = sub.add_parser("init", help="初始化 Git 仓库")
    p_init.add_argument("--path", default=".", help="仓库路径，默认当前目录")
    p_init.add_argument("--branch", default="main", help="初始分支，默认 main")
    p_init.set_defaults(func=cmd_init)

    p_remote = sub.add_parser("remote", help="远程相关")
    remote_sub = p_remote.add_subparsers(dest="remote_command", required=True)
    p_remote_set = remote_sub.add_parser("set", help="设置 origin URL")
    p_remote_set.add_argument("--url", required=True, help="远程 HTTPS URL")
    p_remote_set.add_argument("--path", default=".", help="仓库路径，默认当前目录")
    p_remote_set.set_defaults(func=cmd_remote_set)

    p_boot = sub.add_parser("bootstrap", help="初始化 + 提交 + 推送")
    p_boot.add_argument("--remote", required=True, help="远程 HTTPS URL")
    p_boot.add_argument("-m", "--message", required=True, help="提交说明")
    p_boot.add_argument("--path", default=".", help="仓库路径，默认当前目录")
    p_boot.add_argument("--branch", default="main", help="初始分支，默认 main")
    p_boot.add_argument(
        "--dry-run",
        action="store_true",
        help="仅预览计划与 diff，不执行写操作",
    )
    p_boot.add_argument(
        "--force",
        action="store_true",
        help="忽略敏感文件提醒并继续",
    )
    p_boot.set_defaults(func=cmd_bootstrap)

    p_ship = sub.add_parser("ship", help="add + commit + push")
    p_ship.add_argument("-m", "--message", required=True, help="提交说明")
    p_ship.add_argument("--path", default=".", help="仓库路径，默认当前目录")
    p_ship.add_argument(
        "--dry-run",
        action="store_true",
        help="仅预览计划与 diff，不执行写操作",
    )
    p_ship.add_argument(
        "--force",
        action="store_true",
        help="忽略敏感文件提醒并继续",
    )
    p_ship.set_defaults(func=cmd_ship)

    p_pull = sub.add_parser("pull", help="拉取远程更新")
    p_pull.add_argument("--path", default=".", help="仓库路径，默认当前目录")
    p_pull.add_argument("--remote", default="origin", help="远程名，默认 origin")
    p_pull.add_argument("--branch", default="", help="可选：指定远程分支")
    p_pull.add_argument("--rebase", action="store_true", help="使用 --rebase")
    p_pull.add_argument(
        "--dry-run",
        action="store_true",
        help="仅预览计划，不执行",
    )
    p_pull.set_defaults(func=cmd_pull)

    p_branch = sub.add_parser("branch", help="分支相关")
    branch_sub = p_branch.add_subparsers(dest="branch_command", required=True)
    p_branch_list = branch_sub.add_parser("list", help="列出本地/远程分支")
    p_branch_list.add_argument("--path", default=".", help="仓库路径，默认当前目录")
    p_branch_list.set_defaults(func=cmd_branch_list)

    p_checkout = sub.add_parser("checkout", help="切换分支")
    p_checkout.add_argument("name", help="分支名")
    p_checkout.add_argument("--path", default=".", help="仓库路径，默认当前目录")
    p_checkout.add_argument(
        "-b",
        "--create",
        action="store_true",
        help="创建并切换到新分支",
    )
    p_checkout.add_argument(
        "--dry-run",
        action="store_true",
        help="仅预览计划，不执行",
    )
    p_checkout.set_defaults(func=cmd_checkout)

    p_sens = sub.add_parser("check-sensitive", help="检查变更中的敏感文件")
    p_sens.add_argument("--path", default=".", help="仓库路径，默认当前目录")
    p_sens.set_defaults(func=cmd_check_sensitive)

    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    func = getattr(args, "func", None)
    if not callable(func):
        parser.print_help()
        return 2
    try:
        return int(func(args))
    except KeyboardInterrupt:
        _print_err("\n已取消")
        return 130
    except Exception as exc:  # noqa: BLE001 — CLI 顶层兜底
        _print_err(f"未预期错误: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
