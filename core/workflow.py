# -*- coding: utf-8 -*-
"""bootstrap / ship 高层工作流。"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Sequence, Union

from core import git_ops
from core.remote import validate_remote_url
from core.sensitive import find_sensitive_files, format_sensitive_warning

PathLike = Union[str, Path]


@dataclass
class WorkflowResult:
    """工作流执行结果。"""

    ok: bool
    message: str
    steps: list[str] = field(default_factory=list)
    detail: str = ""
    sensitive_files: list[str] = field(default_factory=list)

    def add_step(self, text: str) -> None:
        self.steps.append(text)


def _fail(
    message: str,
    steps: Optional[list[str]] = None,
    detail: str = "",
    sensitive_files: Optional[list[str]] = None,
) -> WorkflowResult:
    return WorkflowResult(
        ok=False,
        message=message,
        steps=list(steps or []),
        detail=detail,
        sensitive_files=list(sensitive_files or []),
    )


def _ok(
    message: str,
    steps: Optional[list[str]] = None,
    detail: str = "",
    sensitive_files: Optional[list[str]] = None,
) -> WorkflowResult:
    return WorkflowResult(
        ok=True,
        message=message,
        steps=list(steps or []),
        detail=detail,
        sensitive_files=list(sensitive_files or []),
    )


def _validate_message(message: str) -> Optional[str]:
    if not (message or "").strip():
        return "提交说明不能为空"
    return None


def collect_sensitive_files(
    path: PathLike,
    paths: Optional[Sequence[str]] = None,
) -> list[str]:
    """
    收集待提交相关的敏感文件（与 ship/bootstrap/commit_only 门禁同一候选集）。
    paths 有值时只扫指定路径；否则合并 list_changed_files + staged_files。
    """
    if paths:
        candidates = list(paths)
    else:
        candidates = git_ops.list_changed_files(path)
        staged = git_ops.staged_files(path)
        if staged.ok and staged.stdout.strip():
            for line in staged.stdout.splitlines():
                item = line.strip()
                if item and item not in candidates:
                    candidates.append(item)
    return find_sensitive_files(candidates)


def _guard_sensitive(
    path: PathLike,
    paths: Optional[Sequence[str]],
    *,
    force: bool,
    steps: list[str],
) -> Optional[WorkflowResult]:
    """
    敏感文件门禁。
    命中且未 force 时返回失败结果；否则返回 None 并在 steps 中记录。
    """
    hits = collect_sensitive_files(path, paths)
    if not hits:
        return None
    warning = format_sensitive_warning(hits)
    if force:
        steps.append(f"已强制继续（忽略 {len(hits)} 个敏感文件提醒）")
        return None
    return _fail(
        "检测到疑似敏感文件，已中止。确认安全后请加 --force 或 GUI 确认继续。",
        steps,
        detail=warning,
        sensitive_files=hits,
    )


def plan_bootstrap(
    path: PathLike,
    remote_url: str,
    message: str,
    branch: str = "main",
    *,
    force: bool = False,
) -> WorkflowResult:
    """dry-run：只规划 bootstrap 步骤，不修改仓库。"""
    steps: list[str] = []
    target = Path(path).expanduser().resolve()

    git_check = git_ops.ensure_git_available()
    if not git_check.ok:
        return _fail(git_check.message or "git 不可用", steps)

    msg_err = _validate_message(message)
    if msg_err:
        return _fail(msg_err, steps)

    remote = (remote_url or "").strip()
    if remote and not validate_remote_url(remote):
        return _fail(f"远程 URL 无效: {remote}", steps)

    initial_branch = (branch or "main").strip() or "main"
    steps.append(f"[计划] 目标目录: {target}")
    steps.append(f"[计划] 提交说明: {message.strip()}")

    if not target.exists():
        steps.append(f"[计划] 创建目录: {target}")
    if not target.exists() or not git_ops.is_repo(target):
        steps.append(f"[计划] git init -b {initial_branch}")
    else:
        steps.append("[计划] 已是仓库，跳过 init")

    if remote:
        existing = git_ops.remote_get(target, name="origin") if target.exists() and git_ops.is_repo(target) else None
        if existing and existing.ok:
            steps.append(f"[计划] remote set-url origin → {remote}")
        else:
            steps.append(f"[计划] remote add origin → {remote}")
    else:
        steps.append("[计划] 未提供远程，跳过 remote/push")

    steps.append("[计划] git add .")
    if target.exists() and git_ops.is_repo(target):
        status = git_ops.status_porcelain(target)
        if status.ok and not status.stdout.strip() and git_ops.has_head(target):
            steps.append("[计划] 工作区无新变更，将跳过 commit")
        else:
            steps.append("[计划] git commit")
    else:
        steps.append("[计划] git commit")

    if remote:
        steps.append("[计划] git push -u origin <当前分支>")

    sensitive: list[str] = []
    detail = ""
    if target.exists() and git_ops.is_repo(target):
        detail = git_ops.diff_summary(target)
        sensitive = collect_sensitive_files(target)
        if sensitive:
            steps.append(f"[计划] 敏感文件提醒: {len(sensitive)} 个")
            detail = (detail or "") + "\n" + format_sensitive_warning(sensitive)
            if not force:
                steps.append("[计划] 未加 --force 时将中止（可用 --force 强制）")
    return _ok(
        "dry-run：bootstrap 计划（未执行）",
        steps,
        detail=detail,
        sensitive_files=sensitive,
    )


def bootstrap(
    path: PathLike,
    remote_url: str,
    message: str,
    branch: str = "main",
    *,
    dry_run: bool = False,
    force: bool = False,
) -> WorkflowResult:
    """
    初始化并推送：
    非仓库则 init → 可选 remote add → add . → commit → push -u（若给了 remote）
    任一步失败立即返回清晰错误。
    """
    if dry_run:
        return plan_bootstrap(path, remote_url, message, branch=branch, force=force)

    steps: list[str] = []
    target = Path(path).expanduser().resolve()

    git_check = git_ops.ensure_git_available()
    if not git_check.ok:
        return _fail(git_check.message or "git 不可用", steps)

    msg_err = _validate_message(message)
    if msg_err:
        return _fail(msg_err, steps)

    remote = (remote_url or "").strip()
    if remote and not validate_remote_url(remote):
        return _fail(f"远程 URL 无效: {remote}", steps)

    initial_branch = (branch or "main").strip() or "main"

    if not target.exists():
        try:
            target.mkdir(parents=True, exist_ok=True)
            steps.append(f"已创建目录: {target}")
        except OSError as exc:
            return _fail(f"无法创建目录: {exc}", steps)

    if not git_ops.is_repo(target):
        init_result = git_ops.init_repo(target, initial_branch=initial_branch)
        if not init_result.ok:
            return _fail(
                f"初始化仓库失败: {init_result.message}",
                steps,
                detail=init_result.stderr or init_result.stdout,
            )
        steps.append(f"已初始化仓库（分支 {initial_branch}）")
    else:
        steps.append("目录已是 Git 仓库，跳过 init")

    # 敏感文件：在 add 前检查工作区变更
    blocked = _guard_sensitive(target, None, force=force, steps=steps)
    if blocked is not None:
        return blocked

    if remote:
        existing = git_ops.remote_get(target, name="origin")
        if existing.ok:
            set_result = git_ops.remote_set_url(target, remote, name="origin")
            if not set_result.ok:
                return _fail(
                    f"设置远程失败: {set_result.message}",
                    steps,
                    detail=set_result.stderr or set_result.stdout,
                )
            steps.append(f"已更新 origin → {remote}")
        else:
            add_result = git_ops.remote_add(target, remote, name="origin")
            if not add_result.ok:
                return _fail(
                    f"添加远程失败: {add_result.message}",
                    steps,
                    detail=add_result.stderr or add_result.stdout,
                )
            steps.append(f"已添加 origin → {remote}")

    add_result = git_ops.add(target, ["."])
    if not add_result.ok:
        return _fail(
            f"暂存失败: {add_result.message}",
            steps,
            detail=add_result.stderr or add_result.stdout,
        )
    steps.append("已执行 git add .")

    # 无变更时 commit 会失败，给出明确提示
    status = git_ops.status_porcelain(target)
    if status.ok and not status.stdout.strip():
        # 可能已有提交；若从未提交过，仍需至少一次 commit 才能 push
        if not git_ops.has_head(target):
            return _fail("工作区无变更且尚无提交，请先添加文件后再 bootstrap", steps)
        steps.append("工作区无新变更，跳过 commit")
    else:
        commit_result = git_ops.commit(target, message)
        if not commit_result.ok:
            return _fail(
                f"提交失败: {commit_result.message}",
                steps,
                detail=commit_result.stderr or commit_result.stdout,
            )
        steps.append("已提交")

    if remote:
        branch_result = git_ops.current_branch(target)
        current = branch_result.stdout.strip() if branch_result.ok else initial_branch
        push_result = git_ops.push(
            target,
            set_upstream=True,
            remote="origin",
            branch=current or None,
        )
        if not push_result.ok:
            return _fail(
                f"推送失败: {push_result.message}",
                steps,
                detail=push_result.stderr or push_result.stdout,
            )
        steps.append(f"已推送并设置 upstream（origin/{current or initial_branch}）")
        return _ok("bootstrap 完成：已初始化并推送", steps, detail=push_result.stdout)

    return _ok("bootstrap 完成：已初始化并提交（未配置远程，跳过 push）", steps)


def plan_ship(
    path: PathLike,
    message: str,
    paths: Optional[Sequence[str]] = None,
    *,
    force: bool = False,
) -> WorkflowResult:
    """dry-run：只规划 ship 步骤，不修改仓库。"""
    steps: list[str] = []
    target = Path(path).expanduser().resolve()

    git_check = git_ops.ensure_git_available()
    if not git_check.ok:
        return _fail(git_check.message or "git 不可用", steps)

    msg_err = _validate_message(message)
    if msg_err:
        return _fail(msg_err, steps)

    if not target.exists():
        return _fail(f"路径不存在: {target}", steps)
    if not git_ops.is_repo(target):
        return _fail(f"不是 Git 仓库: {target}（请先 init 或 bootstrap）", steps)

    add_targets = list(paths) if paths else ["."]
    steps.append(f"[计划] 目标目录: {target}")
    steps.append(f"[计划] 提交说明: {message.strip()}")
    steps.append(f"[计划] git add -- {' '.join(add_targets)}")

    changed = git_ops.list_changed_files(target)
    staged = git_ops.staged_files(target)
    has_staged = staged.ok and bool(staged.stdout.strip())
    if not changed and not has_staged:
        return _fail("没有可提交的变更（dry-run）", steps)

    steps.append("[计划] git commit")
    remote = git_ops.remote_get(target, name="origin")
    if not remote.ok:
        steps.append("[计划] 未配置 origin，提交后跳过 push")
    else:
        if git_ops.has_upstream(target):
            steps.append("[计划] git push origin")
        else:
            branch = git_ops.current_branch(target)
            name = branch.stdout if branch.ok and branch.stdout else "HEAD"
            steps.append(f"[计划] git push -u origin {name}")

    sensitive = collect_sensitive_files(target, paths)
    detail = git_ops.diff_summary(target, paths=paths)
    if sensitive:
        steps.append(f"[计划] 敏感文件提醒: {len(sensitive)} 个")
        detail = (detail or "") + "\n" + format_sensitive_warning(sensitive)
        if not force:
            steps.append("[计划] 未加 --force 时将中止（可用 --force 强制）")
    return _ok(
        "dry-run：ship 计划（未执行）",
        steps,
        detail=detail,
        sensitive_files=sensitive,
    )


def ship(
    path: PathLike,
    message: str,
    paths: Optional[Sequence[str]] = None,
    *,
    dry_run: bool = False,
    force: bool = False,
) -> WorkflowResult:
    """
    日常发货：add → commit → push（无 upstream 则 -u）。
    """
    if dry_run:
        return plan_ship(path, message, paths=paths, force=force)

    steps: list[str] = []
    target = Path(path).expanduser().resolve()

    git_check = git_ops.ensure_git_available()
    if not git_check.ok:
        return _fail(git_check.message or "git 不可用", steps)

    msg_err = _validate_message(message)
    if msg_err:
        return _fail(msg_err, steps)

    if not target.exists():
        return _fail(f"路径不存在: {target}", steps)

    if not git_ops.is_repo(target):
        return _fail(f"不是 Git 仓库: {target}（请先 init 或 bootstrap）", steps)

    blocked = _guard_sensitive(target, paths, force=force, steps=steps)
    if blocked is not None:
        return blocked

    add_targets = list(paths) if paths else ["."]
    add_result = git_ops.add(target, add_targets)
    if not add_result.ok:
        return _fail(
            f"暂存失败: {add_result.message}",
            steps,
            detail=add_result.stderr or add_result.stdout,
        )
    steps.append(f"已暂存: {', '.join(add_targets)}")

    status = git_ops.status_porcelain(target)
    if status.ok and not status.stdout.strip():
        # 已暂存后仍无 porcelain，说明无待提交变更
        staged = git_ops.staged_files(target)
        if staged.ok and not staged.stdout.strip():
            return _fail("没有可提交的变更", steps)

    commit_result = git_ops.commit(target, message)
    if not commit_result.ok:
        # 常见：nothing to commit
        return _fail(
            f"提交失败: {commit_result.message}",
            steps,
            detail=commit_result.stderr or commit_result.stdout,
        )
    steps.append("已提交")

    branch_result = git_ops.current_branch(target)
    current = branch_result.stdout.strip() if branch_result.ok else ""

    remote = git_ops.remote_get(target, name="origin")
    if not remote.ok:
        return _ok(
            "已提交，但未配置 origin，跳过推送",
            steps,
            detail=commit_result.stdout,
        )

    need_upstream = not git_ops.has_upstream(target)
    push_result = git_ops.push(
        target,
        set_upstream=need_upstream,
        remote="origin",
        branch=current or None if need_upstream else None,
    )
    if not push_result.ok:
        return _fail(
            f"推送失败: {push_result.message}",
            steps,
            detail=push_result.stderr or push_result.stdout,
        )
    if need_upstream:
        steps.append(f"已推送并设置 upstream（origin/{current or 'HEAD'}）")
    else:
        steps.append("已推送")
    return _ok("ship 完成：已提交并推送", steps, detail=push_result.stdout)


def commit_only(
    path: PathLike,
    message: str,
    paths: Optional[Sequence[str]] = None,
    *,
    dry_run: bool = False,
    force: bool = False,
) -> WorkflowResult:
    """仅 add + commit，不推送。"""
    if dry_run:
        steps: list[str] = []
        target = Path(path).expanduser().resolve()
        git_check = git_ops.ensure_git_available()
        if not git_check.ok:
            return _fail(git_check.message or "git 不可用", steps)
        msg_err = _validate_message(message)
        if msg_err:
            return _fail(msg_err, steps)
        if not git_ops.is_repo(target):
            return _fail(f"不是 Git 仓库: {target}", steps)
        add_targets = list(paths) if paths else ["."]
        steps.append(f"[计划] git add -- {' '.join(add_targets)}")
        steps.append(f"[计划] git commit -m {message.strip()!r}")
        steps.append("[计划] 不推送")
        sensitive = collect_sensitive_files(target, paths)
        detail = git_ops.diff_summary(target, paths=paths)
        if sensitive:
            steps.append(f"[计划] 敏感文件提醒: {len(sensitive)} 个")
            detail = (detail or "") + "\n" + format_sensitive_warning(sensitive)
        return _ok(
            "dry-run：提交计划（未执行）",
            steps,
            detail=detail,
            sensitive_files=sensitive,
        )

    steps = []
    target = Path(path).expanduser().resolve()

    git_check = git_ops.ensure_git_available()
    if not git_check.ok:
        return _fail(git_check.message or "git 不可用", steps)

    msg_err = _validate_message(message)
    if msg_err:
        return _fail(msg_err, steps)

    if not git_ops.is_repo(target):
        return _fail(f"不是 Git 仓库: {target}", steps)

    blocked = _guard_sensitive(target, paths, force=force, steps=steps)
    if blocked is not None:
        return blocked

    add_targets = list(paths) if paths else ["."]
    add_result = git_ops.add(target, add_targets)
    if not add_result.ok:
        return _fail(f"暂存失败: {add_result.message}", steps, detail=add_result.stderr)

    commit_result = git_ops.commit(target, message)
    if not commit_result.ok:
        return _fail(
            f"提交失败: {commit_result.message}",
            steps,
            detail=commit_result.stderr or commit_result.stdout,
        )
    steps.append("已提交")
    return _ok("提交完成", steps, detail=commit_result.stdout)


def pull_workflow(
    path: PathLike,
    *,
    remote: str = "origin",
    branch: Optional[str] = None,
    rebase: bool = False,
    dry_run: bool = False,
) -> WorkflowResult:
    """拉取远程更新。"""
    steps: list[str] = []
    target = Path(path).expanduser().resolve()

    git_check = git_ops.ensure_git_available()
    if not git_check.ok:
        return _fail(git_check.message or "git 不可用", steps)

    if not target.exists():
        return _fail(f"路径不存在: {target}", steps)
    if not git_ops.is_repo(target):
        return _fail(f"不是 Git 仓库: {target}", steps)

    remote_name = (remote or "origin").strip() or "origin"
    branch_name = (branch or "").strip() or None
    mode = " --rebase" if rebase else ""

    if dry_run:
        if branch_name:
            steps.append(f"[计划] git pull{mode} {remote_name} {branch_name}")
        else:
            steps.append(f"[计划] git pull{mode} {remote_name}")
        current = git_ops.current_branch(target)
        if current.ok and current.stdout:
            steps.append(f"[计划] 当前分支: {current.stdout}")
        return _ok("dry-run：pull 计划（未执行）", steps)

    result = git_ops.pull(target, remote=remote_name, branch=branch_name, rebase=rebase)
    if not result.ok:
        return _fail(
            f"拉取失败: {result.message}",
            steps,
            detail=result.stderr or result.stdout,
        )
    steps.append(f"已执行 git pull{mode} {remote_name}" + (f" {branch_name}" if branch_name else ""))
    return _ok("pull 完成", steps, detail=result.stdout or result.stderr)


def checkout_workflow(
    path: PathLike,
    branch: str,
    *,
    create: bool = False,
    dry_run: bool = False,
) -> WorkflowResult:
    """切换或创建分支。"""
    steps: list[str] = []
    target = Path(path).expanduser().resolve()
    name = (branch or "").strip()

    git_check = git_ops.ensure_git_available()
    if not git_check.ok:
        return _fail(git_check.message or "git 不可用", steps)

    if not name:
        return _fail("分支名不能为空", steps)
    if not target.exists():
        return _fail(f"路径不存在: {target}", steps)
    if not git_ops.is_repo(target):
        return _fail(f"不是 Git 仓库: {target}", steps)

    if dry_run:
        if create:
            steps.append(f"[计划] git checkout -b {name}")
        else:
            steps.append(f"[计划] git checkout {name}")
        current = git_ops.current_branch(target)
        if current.ok and current.stdout:
            steps.append(f"[计划] 当前分支: {current.stdout} → {name}")
        return _ok("dry-run：checkout 计划（未执行）", steps)

    result = git_ops.checkout(target, name, create=create)
    if not result.ok:
        return _fail(
            f"切换分支失败: {result.message}",
            steps,
            detail=result.stderr or result.stdout,
        )
    action = "创建并切换" if create else "切换"
    steps.append(f"已{action}到分支: {name}")
    return _ok(f"已{action}到 {name}", steps, detail=result.stdout or result.stderr)


def list_branches_workflow(path: PathLike) -> WorkflowResult:
    """列出本地与远程分支摘要。"""
    steps: list[str] = []
    target = Path(path).expanduser().resolve()

    git_check = git_ops.ensure_git_available()
    if not git_check.ok:
        return _fail(git_check.message or "git 不可用", steps)

    if not target.exists():
        return _fail(f"路径不存在: {target}", steps)
    if not git_ops.is_repo(target):
        return _fail(f"不是 Git 仓库: {target}", steps)

    current = git_ops.current_branch(target)
    local = git_ops.list_branch_names(target, remote=False)
    remote_names = git_ops.list_branch_names(target, remote=True)

    lines = []
    cur = current.stdout if current.ok else "?"
    lines.append(f"当前分支: {cur}")
    lines.append(f"本地分支 ({len(local)}):")
    for item in local:
        mark = "*" if item == cur else " "
        lines.append(f"  {mark} {item}")
    lines.append(f"远程分支 ({len(remote_names)}):")
    if remote_names:
        for item in remote_names:
            lines.append(f"    {item}")
    else:
        lines.append("    (无)")
    return _ok("分支列表", steps, detail="\n".join(lines))
