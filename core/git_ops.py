# -*- coding: utf-8 -*-
"""Git 命令封装：通过 subprocess 调用系统 git。"""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Sequence, Union

PathLike = Union[str, Path]

# 默认超时（秒）：本地命令 120s；网络相关 push/pull 等 300s
DEFAULT_TIMEOUT = 120.0
NETWORK_TIMEOUT = 300.0
_NETWORK_COMMANDS = frozenset({"push", "pull", "fetch", "clone", "ls-remote"})


@dataclass
class GitResult:
    """结构化 Git 命令结果。"""

    ok: bool
    code: int
    stdout: str
    stderr: str
    command: list[str]

    @property
    def message(self) -> str:
        text = (self.stderr or self.stdout or "").strip()
        return text


def _as_path(path: PathLike) -> Path:
    return Path(path).expanduser().resolve()


def _resolve_timeout(args: Sequence[str], timeout: Optional[float]) -> float:
    """根据子命令选择默认超时；显式传入 timeout 时优先使用。"""
    if timeout is not None:
        return timeout
    if args and args[0] in _NETWORK_COMMANDS:
        return NETWORK_TIMEOUT
    return DEFAULT_TIMEOUT


def _run(
    args: Sequence[str],
    cwd: PathLike,
    *,
    check: bool = False,
    env: Optional[dict] = None,
    timeout: Optional[float] = None,
) -> GitResult:
    """执行 git 子命令。timeout=None 时按命令类型使用默认超时策略。"""
    command = ["git", *args]
    run_env = os.environ.copy()
    # 避免交互式编辑器/分页器阻塞
    run_env.setdefault("GIT_TERMINAL_PROMPT", "0")
    run_env.setdefault("GIT_PAGER", "cat")
    if env:
        run_env.update(env)

    effective_timeout = _resolve_timeout(args, timeout)
    try:
        completed = subprocess.run(
            command,
            cwd=str(_as_path(cwd)),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=run_env,
            check=False,
            timeout=effective_timeout,
        )
    except FileNotFoundError:
        return GitResult(
            ok=False,
            code=127,
            stdout="",
            stderr="未找到 git 命令，请确认已安装并加入 PATH",
            command=list(command),
        )
    except subprocess.TimeoutExpired:
        return GitResult(
            ok=False,
            code=124,
            stdout="",
            stderr=(
                f"git 命令超时（{effective_timeout:g} 秒）: {' '.join(command)}。"
                "网络操作可检查连通性或稍后重试。"
            ),
            command=list(command),
        )
    except OSError as exc:
        return GitResult(
            ok=False,
            code=1,
            stdout="",
            stderr=f"执行 git 失败: {exc}",
            command=list(command),
        )

    result = GitResult(
        ok=completed.returncode == 0,
        code=completed.returncode,
        stdout=completed.stdout or "",
        stderr=completed.stderr or "",
        command=list(command),
    )
    if check and not result.ok:
        raise RuntimeError(result.message or f"git 命令失败: {' '.join(command)}")
    return result


def ensure_git_available() -> GitResult:
    """检查系统 PATH 中是否存在可用的 git。"""
    git_path = shutil.which("git")
    if not git_path:
        return GitResult(
            ok=False,
            code=127,
            stdout="",
            stderr="未找到 git，请先安装 Git 并确保可在终端中执行 `git --version`",
            command=["git", "--version"],
        )
    result = _run(["--version"], cwd=Path.cwd())
    if result.ok:
        result.stdout = result.stdout.strip() or f"git available: {git_path}"
    return result


def is_repo(path: PathLike) -> bool:
    """判断路径是否为 Git 仓库（工作区或子目录）。"""
    target = _as_path(path)
    if not target.exists():
        return False
    result = _run(["rev-parse", "--is-inside-work-tree"], cwd=target)
    return result.ok and result.stdout.strip().lower() == "true"


def init_repo(path: PathLike, initial_branch: str = "main") -> GitResult:
    """初始化仓库，默认分支 main。"""
    target = _as_path(path)
    target.mkdir(parents=True, exist_ok=True)
    branch = (initial_branch or "main").strip() or "main"
    # 优先使用 -b；旧版 git 不支持时回退
    result = _run(["init", "-b", branch], cwd=target)
    if result.ok:
        return result
    result = _run(["init"], cwd=target)
    if not result.ok:
        return result
    # 尝试切换/创建默认分支
    checkout = _run(["checkout", "-b", branch], cwd=target)
    if checkout.ok:
        return GitResult(
            ok=True,
            code=0,
            stdout=(result.stdout + checkout.stdout).strip(),
            stderr=(result.stderr + checkout.stderr).strip(),
            command=result.command,
        )
    # 已在目标分支时 checkout -b 可能失败，再试 rename
    rename = _run(["branch", "-M", branch], cwd=target)
    if rename.ok:
        return GitResult(
            ok=True,
            code=0,
            stdout=(result.stdout + rename.stdout).strip(),
            stderr=(result.stderr + rename.stderr).strip(),
            command=result.command,
        )
    return result


def status_porcelain(path: PathLike) -> GitResult:
    """porcelain 状态（便于解析）。"""
    return _run(["status", "--porcelain"], cwd=path)


def status_short(path: PathLike) -> GitResult:
    """短格式状态。"""
    return _run(["status", "-sb"], cwd=path)


def add(path: PathLike, paths: Optional[Sequence[str]] = None) -> GitResult:
    """git add，paths 默认 ['.']。"""
    targets = list(paths) if paths else ["."]
    if not targets:
        targets = ["."]
    return _run(["add", "--", *targets], cwd=path)


def commit(path: PathLike, message: str) -> GitResult:
    """提交，message 必须非空。"""
    msg = (message or "").strip()
    if not msg:
        return GitResult(
            ok=False,
            code=1,
            stdout="",
            stderr="提交说明不能为空",
            command=["git", "commit", "-m", ""],
        )
    return _run(["commit", "-m", msg], cwd=path)


def current_branch(path: PathLike) -> GitResult:
    """当前分支名（detached 时可能失败）。"""
    result = _run(["branch", "--show-current"], cwd=path)
    if result.ok:
        result.stdout = result.stdout.strip()
    return result


def has_upstream(path: PathLike) -> bool:
    """当前分支是否已设置 upstream。"""
    result = _run(
        ["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"],
        cwd=path,
    )
    return result.ok


def remote_get(path: PathLike, name: str = "origin") -> GitResult:
    """获取远程 URL。"""
    result = _run(["remote", "get-url", name], cwd=path)
    if result.ok:
        result.stdout = result.stdout.strip()
    return result


def remote_add(path: PathLike, url: str, name: str = "origin") -> GitResult:
    """添加远程。"""
    remote_url = (url or "").strip()
    if not remote_url:
        return GitResult(
            ok=False,
            code=1,
            stdout="",
            stderr="远程 URL 不能为空",
            command=["git", "remote", "add", name, ""],
        )
    return _run(["remote", "add", name, remote_url], cwd=path)


def remote_set_url(path: PathLike, url: str, name: str = "origin") -> GitResult:
    """设置已有远程 URL；不存在则 add。"""
    remote_url = (url or "").strip()
    if not remote_url:
        return GitResult(
            ok=False,
            code=1,
            stdout="",
            stderr="远程 URL 不能为空",
            command=["git", "remote", "set-url", name, ""],
        )
    existing = remote_get(path, name=name)
    if existing.ok:
        return _run(["remote", "set-url", name, remote_url], cwd=path)
    return remote_add(path, remote_url, name=name)


def push(
    path: PathLike,
    set_upstream: bool = False,
    remote: str = "origin",
    branch: Optional[str] = None,
    *,
    timeout: Optional[float] = None,
) -> GitResult:
    """推送到远程。不支持 force push。默认超时 300 秒。"""
    args: list[str] = ["push"]
    if set_upstream:
        args.append("-u")
    args.append(remote)
    if branch:
        args.append(branch)
    # timeout=None 时由 _run 按网络命令默认 300s
    return _run(args, cwd=path, timeout=timeout)


def pull(
    path: PathLike,
    remote: str = "origin",
    branch: Optional[str] = None,
    *,
    rebase: bool = False,
    timeout: Optional[float] = None,
) -> GitResult:
    """拉取远程更新。不支持 force。默认超时 300 秒。"""
    args: list[str] = ["pull"]
    if rebase:
        args.append("--rebase")
    args.append(remote)
    if branch:
        args.append(branch)
    return _run(args, cwd=path, timeout=timeout)


def list_branches(path: PathLike, *, remote: bool = False) -> GitResult:
    """列出分支（name-only）。remote=True 时列出远程分支。"""
    args = ["branch", "--format=%(refname:short)"]
    if remote:
        args.insert(1, "-r")
    return _run(args, cwd=path)


def _is_remote_pseudo_branch(name: str) -> bool:
    """远程列表中的伪分支：仅 remote 名（如 origin）或 */HEAD。"""
    if name.endswith("/HEAD") or name == "HEAD":
        return True
    # origin/HEAD 经 short 解析后常为无斜杠的 remote 名
    if "/" not in name:
        return True
    return False


def list_branch_names(path: PathLike, *, remote: bool = False) -> list[str]:
    """解析分支名列表。remote=True 时过滤 origin 等伪分支名。"""
    result = list_branches(path, remote=remote)
    if not result.ok:
        return []
    names: list[str] = []
    for line in result.stdout.splitlines():
        name = line.strip()
        if not name:
            continue
        if remote and _is_remote_pseudo_branch(name):
            continue
        names.append(name)
    return names


def checkout(
    path: PathLike,
    branch: str,
    *,
    create: bool = False,
) -> GitResult:
    """切换分支；create=True 时等价 checkout -b。"""
    name = (branch or "").strip()
    if not name:
        return GitResult(
            ok=False,
            code=1,
            stdout="",
            stderr="分支名不能为空",
            command=["git", "checkout"],
        )
    if create:
        return _run(["checkout", "-b", name], cwd=path)
    return _run(["checkout", name], cwd=path)


def has_head(path: PathLike) -> bool:
    """仓库是否至少有一次提交（HEAD 存在）。"""
    result = _run(["rev-parse", "--verify", "HEAD"], cwd=path)
    return result.ok


def staged_files(path: PathLike) -> GitResult:
    """已暂存文件列表（name-only）。"""
    return _run(["diff", "--cached", "--name-only"], cwd=path)


def list_changed_files(path: PathLike) -> list[str]:
    """解析 porcelain 输出，返回变更文件路径列表。"""
    result = status_porcelain(path)
    if not result.ok:
        return []
    files: list[str] = []
    for line in result.stdout.splitlines():
        if not line or len(line) < 4:
            continue
        # 格式: XY PATH 或 XY ORIG -> PATH
        entry = line[3:].strip()
        if " -> " in entry:
            entry = entry.split(" -> ", 1)[1].strip()
        # 去掉可能的引号
        if len(entry) >= 2 and entry[0] == entry[-1] == '"':
            entry = entry[1:-1]
        if entry:
            files.append(entry)
    return files


def diff_stat(path: PathLike, *, staged: bool = False) -> GitResult:
    """变更统计摘要（--stat）。"""
    args = ["diff", "--stat"]
    if staged:
        args.append("--cached")
    return _run(args, cwd=path)


def diff_name_status(path: PathLike, *, staged: bool = False) -> GitResult:
    """变更文件名与状态。"""
    args = ["diff", "--name-status"]
    if staged:
        args.append("--cached")
    return _run(args, cwd=path)


def diff_patch(
    path: PathLike,
    paths: Optional[Sequence[str]] = None,
    *,
    staged: bool = False,
) -> GitResult:
    """完整 diff patch；paths 可选限定文件。"""
    args = ["diff"]
    if staged:
        args.append("--cached")
    if paths:
        args.append("--")
        args.extend(list(paths))
    return _run(args, cwd=path)


def diff_summary(
    path: PathLike,
    paths: Optional[Sequence[str]] = None,
    *,
    max_patch_chars: int = 12000,
) -> str:
    """
    生成推送前可读摘要：
    未暂存 + 已暂存统计，以及可选 patch（过长截断）。
    """
    target = _as_path(path)
    lines: list[str] = []

    branch = current_branch(target)
    if branch.ok and branch.stdout:
        lines.append(f"分支: {branch.stdout}")
    remote = remote_get(target)
    if remote.ok and remote.stdout:
        lines.append(f"远程: {remote.stdout}")
    else:
        lines.append("远程: (未配置 origin)")
    lines.append(f"upstream: {'已设置' if has_upstream(target) else '未设置'}")
    lines.append("")

    changed = list_changed_files(target)
    if paths:
        selected = list(paths)
        lines.append(f"关注文件 ({len(selected)}):")
        for item in selected:
            lines.append(f"  - {item}")
    else:
        lines.append(f"变更文件 ({len(changed)}):")
        if changed:
            for item in changed[:50]:
                lines.append(f"  - {item}")
            if len(changed) > 50:
                lines.append(f"  … 另有 {len(changed) - 50} 个文件")
        else:
            lines.append("  (无)")
    lines.append("")

    unstaged = diff_stat(target, staged=False)
    staged_stat = diff_stat(target, staged=True)
    lines.append("=== 未暂存 (--stat) ===")
    lines.append((unstaged.stdout or "").strip() or "(无)")
    lines.append("")
    lines.append("=== 已暂存 (--stat) ===")
    lines.append((staged_stat.stdout or "").strip() or "(无)")
    lines.append("")

    # patch：优先未暂存；若无则看已暂存
    patch = diff_patch(target, paths=paths, staged=False)
    patch_text = (patch.stdout or "").strip()
    label = "未暂存"
    if not patch_text:
        patch = diff_patch(target, paths=paths, staged=True)
        patch_text = (patch.stdout or "").strip()
        label = "已暂存"

    lines.append(f"=== Diff patch（{label}）===")
    if not patch_text:
        lines.append("(无 diff 内容)")
    elif len(patch_text) > max_patch_chars:
        lines.append(patch_text[:max_patch_chars])
        lines.append("")
        lines.append(f"… 已截断，完整长度约 {len(patch_text)} 字符")
    else:
        lines.append(patch_text)

    return "\n".join(lines).rstrip() + "\n"
