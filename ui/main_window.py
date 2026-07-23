# -*- coding: utf-8 -*-
"""Git Ship 主窗口：左右分栏。"""

from __future__ import annotations

import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Callable, Optional

from core import config as app_config
from core import git_ops
from core.remote import (
    PROVIDER_LABELS,
    PROVIDERS,
    build_https_url,
    detect_provider,
    validate_remote_url,
)
from core.sensitive import find_sensitive_files, format_sensitive_warning
from core.workflow import (
    bootstrap,
    checkout_workflow,
    collect_sensitive_files,
    commit_only,
    pull_workflow,
    ship,
)
from ui.widgets import LogText


class MainWindow:
    """主界面。"""

    WINDOW_TITLE = "Git Ship"
    WINDOW_SIZE = "1080x760"
    MIN_SIZE = (900, 640)

    def __init__(self, master: tk.Tk):
        self.master = master
        self.master.title(self.WINDOW_TITLE)
        self.master.geometry(self.WINDOW_SIZE)
        self.master.minsize(*self.MIN_SIZE)

        self._cfg = app_config.load_config()
        self.repo_var = tk.StringVar(value=str(self._cfg.get("last_repo_path") or ""))
        self.remote_var = tk.StringVar(value=str(self._cfg.get("last_remote_url") or ""))
        self.provider_var = tk.StringVar(
            value=PROVIDER_LABELS.get(
                str(self._cfg.get("default_provider") or "github"),
                "GitHub",
            )
        )
        self.owner_var = tk.StringVar()
        self.repo_name_var = tk.StringVar()
        self.branch_var = tk.StringVar(
            value=str(self._cfg.get("default_branch") or "main")
        )
        self.checkout_var = tk.StringVar()
        self.busy_var = tk.StringVar(value="")

        self._file_items: list[str] = []
        self._branch_items: list[str] = []
        self._busy = False
        self._result_queue: queue.Queue = queue.Queue()
        self._action_buttons: list[ttk.Button] = []
        self._diff_after_id: Optional[str] = None

        self._setup_style()
        self._build_ui()
        self._bind_events()
        self.master.after(120, self._poll_queue)

        if self.repo_var.get().strip():
            self.master.after(100, self.refresh_status)
        # 首次启动自动弹出使用说明
        if not bool(self._cfg.get("help_seen")):
            self.master.after(250, lambda: self.show_help(mark_seen=True))

    def _setup_style(self) -> None:
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("TButton", padding=4)
        style.configure("TLabelframe.Label", font=("Microsoft YaHei UI", 9, "bold"))
        style.configure("Title.TLabel", font=("Microsoft YaHei UI", 11, "bold"))
        style.configure("Muted.TLabel", foreground="#6b7280")
        style.configure("Busy.TLabel", foreground="#b45309")

    def _track_button(self, btn: ttk.Button) -> ttk.Button:
        self._action_buttons.append(btn)
        return btn

    def _build_ui(self) -> None:
        root = ttk.Frame(self.master, padding=10)
        root.pack(fill="both", expand=True)
        root.columnconfigure(0, weight=1, uniform="col")
        root.columnconfigure(1, weight=1, uniform="col")
        root.rowconfigure(0, weight=1)

        left = ttk.Frame(root)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
        left.columnconfigure(0, weight=1)
        left.rowconfigure(3, weight=1)

        right = ttk.Frame(root)
        right.grid(row=0, column=1, sticky="nsew", padx=(6, 0))
        right.columnconfigure(0, weight=1)
        right.rowconfigure(0, weight=2)
        right.rowconfigure(1, weight=1)
        right.rowconfigure(3, weight=1)

        # ---- 左：仓库 / 远程 / 分支 / 变更 ----
        repo_frame = ttk.LabelFrame(left, text="仓库", padding=8)
        repo_frame.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        repo_frame.columnconfigure(1, weight=1)

        ttk.Label(repo_frame, text="路径").grid(row=0, column=0, sticky="w", padx=(0, 6))
        ttk.Entry(repo_frame, textvariable=self.repo_var).grid(
            row=0, column=1, sticky="ew"
        )
        self._track_button(
            ttk.Button(repo_frame, text="浏览…", width=8, command=self.browse_repo)
        ).grid(row=0, column=2, padx=(6, 0))
        self._track_button(
            ttk.Button(repo_frame, text="刷新", width=8, command=self.refresh_status)
        ).grid(row=0, column=3, padx=(6, 0))

        self.status_label = ttk.Label(
            repo_frame, text="状态: —", style="Muted.TLabel", wraplength=420
        )
        self.status_label.grid(row=1, column=0, columnspan=4, sticky="w", pady=(8, 0))
        self.busy_label = ttk.Label(
            repo_frame, textvariable=self.busy_var, style="Busy.TLabel"
        )
        self.busy_label.grid(row=2, column=0, columnspan=4, sticky="w", pady=(4, 0))

        remote_frame = ttk.LabelFrame(left, text="远程（HTTPS）", padding=8)
        remote_frame.grid(row=1, column=0, sticky="ew", pady=(0, 8))
        remote_frame.columnconfigure(1, weight=1)

        ttk.Label(remote_frame, text="平台").grid(row=0, column=0, sticky="w", padx=(0, 6))
        provider_values = [PROVIDER_LABELS[p] for p in PROVIDERS]
        self.provider_combo = ttk.Combobox(
            remote_frame,
            textvariable=self.provider_var,
            values=provider_values,
            state="readonly",
            width=12,
        )
        self.provider_combo.grid(row=0, column=1, sticky="w")

        ttk.Label(remote_frame, text="Owner").grid(
            row=1, column=0, sticky="w", padx=(0, 6), pady=(6, 0)
        )
        ttk.Entry(remote_frame, textvariable=self.owner_var).grid(
            row=1, column=1, sticky="ew", pady=(6, 0)
        )
        ttk.Label(remote_frame, text="Repo").grid(
            row=2, column=0, sticky="w", padx=(0, 6), pady=(6, 0)
        )
        ttk.Entry(remote_frame, textvariable=self.repo_name_var).grid(
            row=2, column=1, sticky="ew", pady=(6, 0)
        )
        self._track_button(
            ttk.Button(
                remote_frame, text="生成 URL", width=10, command=self.fill_url_from_template
            )
        ).grid(row=2, column=2, padx=(6, 0), pady=(6, 0))

        ttk.Label(remote_frame, text="URL").grid(
            row=3, column=0, sticky="w", padx=(0, 6), pady=(6, 0)
        )
        ttk.Entry(remote_frame, textvariable=self.remote_var).grid(
            row=3, column=1, columnspan=2, sticky="ew", pady=(6, 0)
        )

        branch_row = ttk.Frame(remote_frame)
        branch_row.grid(row=4, column=0, columnspan=3, sticky="ew", pady=(6, 0))
        ttk.Label(branch_row, text="初始分支").pack(side="left")
        ttk.Entry(branch_row, textvariable=self.branch_var, width=12).pack(
            side="left", padx=(6, 0)
        )

        # 分支操作
        branch_frame = ttk.LabelFrame(left, text="分支 / 同步", padding=8)
        branch_frame.grid(row=2, column=0, sticky="ew", pady=(0, 8))
        branch_frame.columnconfigure(1, weight=1)

        ttk.Label(branch_frame, text="当前/目标").grid(
            row=0, column=0, sticky="w", padx=(0, 6)
        )
        self.checkout_combo = ttk.Combobox(
            branch_frame,
            textvariable=self.checkout_var,
            values=[],
            width=24,
        )
        self.checkout_combo.grid(row=0, column=1, sticky="ew")
        self._track_button(
            ttk.Button(branch_frame, text="切换", width=8, command=self.do_checkout)
        ).grid(row=0, column=2, padx=(6, 0))
        self._track_button(
            ttk.Button(
                branch_frame, text="新建并切换", width=10, command=self.do_checkout_create
            )
        ).grid(row=0, column=3, padx=(6, 0))

        sync_row = ttk.Frame(branch_frame)
        sync_row.grid(row=1, column=0, columnspan=4, sticky="ew", pady=(6, 0))
        self._track_button(
            ttk.Button(sync_row, text="Pull", command=self.do_pull)
        ).pack(side="left")
        self._track_button(
            ttk.Button(sync_row, text="Pull --rebase", command=self.do_pull_rebase)
        ).pack(side="left", padx=(6, 0))
        self._track_button(
            ttk.Button(sync_row, text="刷新分支", command=self.refresh_branches)
        ).pack(side="left", padx=(6, 0))

        files_frame = ttk.LabelFrame(left, text="文件变更", padding=8)
        files_frame.grid(row=3, column=0, sticky="nsew", pady=(0, 0))
        files_frame.columnconfigure(0, weight=1)
        files_frame.rowconfigure(0, weight=1)

        list_wrap = ttk.Frame(files_frame)
        list_wrap.grid(row=0, column=0, sticky="nsew")
        list_wrap.columnconfigure(0, weight=1)
        list_wrap.rowconfigure(0, weight=1)

        self.files_list = tk.Listbox(
            list_wrap,
            selectmode=tk.EXTENDED,
            font=("Consolas", 9),
            activestyle="dotbox",
            exportselection=False,
        )
        scroll = ttk.Scrollbar(list_wrap, orient="vertical", command=self.files_list.yview)
        self.files_list.configure(yscrollcommand=scroll.set)
        self.files_list.grid(row=0, column=0, sticky="nsew")
        scroll.grid(row=0, column=1, sticky="ns")

        btn_row = ttk.Frame(files_frame)
        btn_row.grid(row=1, column=0, sticky="ew", pady=(6, 0))
        self._track_button(
            ttk.Button(btn_row, text="全选", command=self.select_all_files)
        ).pack(side="left")
        self._track_button(
            ttk.Button(btn_row, text="刷新列表", command=self.refresh_files)
        ).pack(side="left", padx=(6, 0))
        self._track_button(
            ttk.Button(btn_row, text="预览 Diff", command=self.refresh_diff)
        ).pack(side="left", padx=(6, 0))
        self._track_button(
            ttk.Button(btn_row, text="敏感检查", command=self.do_check_sensitive)
        ).pack(side="left", padx=(6, 0))

        # ---- 右：Diff / 提交说明 / 操作 / 日志 ----
        diff_frame = ttk.LabelFrame(right, text="Diff 预览", padding=8)
        diff_frame.grid(row=0, column=0, sticky="nsew", pady=(0, 8))
        diff_frame.columnconfigure(0, weight=1)
        diff_frame.rowconfigure(0, weight=1)

        diff_wrap = ttk.Frame(diff_frame)
        diff_wrap.grid(row=0, column=0, sticky="nsew")
        diff_wrap.columnconfigure(0, weight=1)
        diff_wrap.rowconfigure(0, weight=1)

        self.diff_text = tk.Text(
            diff_wrap,
            wrap="none",
            height=12,
            font=("Consolas", 9),
            relief="solid",
            borderwidth=1,
            state="disabled",
        )
        diff_ys = ttk.Scrollbar(diff_wrap, orient="vertical", command=self.diff_text.yview)
        diff_xs = ttk.Scrollbar(
            diff_wrap, orient="horizontal", command=self.diff_text.xview
        )
        self.diff_text.configure(yscrollcommand=diff_ys.set, xscrollcommand=diff_xs.set)
        self.diff_text.grid(row=0, column=0, sticky="nsew")
        diff_ys.grid(row=0, column=1, sticky="ns")
        diff_xs.grid(row=1, column=0, sticky="ew")
        self.diff_text.tag_configure("add", foreground="#047857")
        self.diff_text.tag_configure("del", foreground="#b91c1c")
        self.diff_text.tag_configure("meta", foreground="#6b7280")
        self.diff_text.tag_configure("hunk", foreground="#1d4ed8")

        msg_frame = ttk.LabelFrame(right, text="提交说明", padding=8)
        msg_frame.grid(row=1, column=0, sticky="nsew", pady=(0, 8))
        msg_frame.columnconfigure(0, weight=1)
        msg_frame.rowconfigure(0, weight=1)

        self.message_text = tk.Text(
            msg_frame,
            wrap="word",
            height=5,
            font=("Microsoft YaHei UI", 10),
            relief="solid",
            borderwidth=1,
        )
        self.message_text.grid(row=0, column=0, sticky="nsew")

        action_frame = ttk.LabelFrame(right, text="操作", padding=8)
        action_frame.grid(row=2, column=0, sticky="ew", pady=(0, 8))
        action_frame.columnconfigure(0, weight=1)

        def _action_row(
            parent: ttk.Frame,
            row: int,
            label: str,
            buttons: list[tuple[str, Callable[[], None], bool]],
        ) -> None:
            """一行：左侧分组标签 + 等宽按钮网格。"""
            parent.columnconfigure(1, weight=1)
            ttk.Label(parent, text=label, style="Muted.TLabel", width=6).grid(
                row=row, column=0, sticky="nw", padx=(0, 8), pady=3
            )
            btn_wrap = ttk.Frame(parent)
            btn_wrap.grid(row=row, column=1, sticky="ew", pady=3)
            for col in range(3):
                btn_wrap.columnconfigure(col, weight=1, uniform="actbtn")
            for col, (text, cmd, track) in enumerate(buttons):
                btn = ttk.Button(btn_wrap, text=text, command=cmd)
                if track:
                    self._track_button(btn)
                btn.grid(row=0, column=col, sticky="ew", padx=(0, 6) if col < 2 else 0)

        # 日常提交
        _action_row(
            action_frame,
            0,
            "日常",
            [
                ("提交", self.do_commit, True),
                ("提交并推送", self.do_ship, True),
                ("试运行 Ship", self.do_ship_dry_run, True),
            ],
        )
        # 仓库初始化 / 远程
        _action_row(
            action_frame,
            1,
            "仓库",
            [
                ("初始化", self.do_init, True),
                ("设置远程", self.do_set_remote, True),
                ("Bootstrap", self.do_bootstrap, True),
            ],
        )
        # 预览与辅助（使用说明不参与 busy 禁用）
        _action_row(
            action_frame,
            2,
            "其他",
            [
                ("试运行 Bootstrap", self.do_bootstrap_dry_run, True),
                ("使用说明", self.show_help, False),
                ("清空日志", self.clear_log, True),
            ],
        )

        log_frame = ttk.LabelFrame(right, text="操作日志", padding=8)
        log_frame.grid(row=3, column=0, sticky="nsew")
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)
        self.log = LogText(log_frame)
        self.log.grid(row=0, column=0, sticky="nsew")

        self.log.append("Git Ship 已就绪。请选择仓库路径。", "muted")
        self._set_diff_text("（刷新仓库后显示 Diff 摘要）")

    def _bind_events(self) -> None:
        self.remote_var.trace_add("write", self._on_remote_changed)
        self.files_list.bind("<<ListboxSelect>>", self._on_files_selected)

    # ---- 异步 ----

    def _set_busy(self, busy: bool, text: str = "") -> None:
        self._busy = busy
        self.busy_var.set(text if busy else "")
        state = "disabled" if busy else "normal"
        for btn in self._action_buttons:
            try:
                btn.configure(state=state)
            except tk.TclError:
                pass

    def _run_async(
        self,
        label: str,
        worker: Callable[[], object],
        on_done: Callable[[object], None],
    ) -> None:
        if self._busy:
            messagebox.showinfo("请稍候", "已有操作在进行中")
            return
        self._set_busy(True, f"执行中: {label}…")
        self.log_info(f"开始: {label}")

        def _target() -> None:
            try:
                result = worker()
                self._result_queue.put(("ok", on_done, result))
            except Exception as exc:  # noqa: BLE001
                self._result_queue.put(("err", label, exc))

        threading.Thread(target=_target, daemon=True).start()

    def _poll_queue(self) -> None:
        try:
            while True:
                item = self._result_queue.get_nowait()
                kind = item[0]
                if kind == "ok":
                    _, on_done, result = item
                    self._set_busy(False)
                    try:
                        on_done(result)
                    except Exception as exc:  # noqa: BLE001
                        self.log_err(f"回调失败: {exc}")
                        messagebox.showerror("错误", str(exc))
                elif kind == "err":
                    _, label, exc = item
                    self._set_busy(False)
                    self.log_err(f"{label} 异常: {exc}")
                    messagebox.showerror("错误", f"{label}\n{exc}")
        except queue.Empty:
            pass
        self.master.after(120, self._poll_queue)

    def _provider_key(self) -> str:
        label = self.provider_var.get().strip()
        for key, value in PROVIDER_LABELS.items():
            if value == label:
                return key
        return "custom"

    def _repo_path(self) -> Path:
        return Path(self.repo_var.get().strip() or ".").expanduser().resolve()

    def _message(self) -> str:
        return self.message_text.get("1.0", "end").strip()

    def _persist(self) -> None:
        self._cfg["last_repo_path"] = str(self._repo_path()) if self.repo_var.get().strip() else ""
        self._cfg["last_remote_url"] = self.remote_var.get().strip()
        self._cfg["default_provider"] = self._provider_key()
        self._cfg["default_branch"] = self.branch_var.get().strip() or "main"
        try:
            app_config.save_config(self._cfg)
        except OSError as exc:
            self.log.append(f"保存配置失败: {exc}", "error")

    def log_info(self, msg: str) -> None:
        self.log.append(msg, "info")

    def log_ok(self, msg: str) -> None:
        self.log.append(msg, "ok")

    def log_err(self, msg: str) -> None:
        self.log.append(msg, "error")

    def browse_repo(self) -> None:
        if self._busy:
            return
        initial = self.repo_var.get().strip() or str(Path.home())
        chosen = filedialog.askdirectory(title="选择仓库目录", initialdir=initial)
        if chosen:
            self.repo_var.set(chosen)
            self.refresh_status()

    def fill_url_from_template(self) -> None:
        key = self._provider_key()
        if key == "custom":
            messagebox.showinfo("提示", "自定义平台请直接填写完整 HTTPS URL")
            return
        owner = self.owner_var.get().strip()
        repo = self.repo_name_var.get().strip()
        try:
            url = build_https_url(key, owner, repo)
        except ValueError as exc:
            messagebox.showerror("生成失败", str(exc))
            return
        self.remote_var.set(url)
        self.log_info(f"已生成 URL: {url}")

    def _on_remote_changed(self, *_args) -> None:
        url = self.remote_var.get().strip()
        if not url:
            return
        provider = detect_provider(url)
        label = PROVIDER_LABELS.get(provider, "自定义")
        if self.provider_var.get() != label:
            self.provider_var.set(label)

    def select_all_files(self) -> None:
        self.files_list.select_set(0, "end")
        self.refresh_diff()

    def _set_diff_text(self, content: str) -> None:
        self.diff_text.configure(state="normal")
        self.diff_text.delete("1.0", "end")
        for line in (content or "").splitlines():
            tag = None
            if line.startswith("+") and not line.startswith("+++"):
                tag = "add"
            elif line.startswith("-") and not line.startswith("---"):
                tag = "del"
            elif line.startswith("@@"):
                tag = "hunk"
            elif line.startswith(
                ("diff ", "index ", "===", "分支:", "远程:", "upstream:", "⚠")
            ):
                tag = "meta"
            if tag:
                self.diff_text.insert("end", line + "\n", tag)
            else:
                self.diff_text.insert("end", line + "\n")
        self.diff_text.see("1.0")
        self.diff_text.configure(state="disabled")

    def _on_files_selected(self, _event=None) -> None:
        if not self._file_items or self._busy:
            return
        # 防抖：快速多选时只触发最后一次 diff
        if self._diff_after_id is not None:
            try:
                self.master.after_cancel(self._diff_after_id)
            except tk.TclError:
                pass
            self._diff_after_id = None
        self._diff_after_id = self.master.after(250, self._debounced_refresh_diff)

    def _debounced_refresh_diff(self) -> None:
        self._diff_after_id = None
        if self._busy:
            return
        self.refresh_diff()

    def _apply_files_list(self, files: list[str]) -> None:
        self.files_list.delete(0, "end")
        self._file_items = list(files)
        for item in files:
            prefix = "⚠ " if find_sensitive_files([item]) else ""
            self.files_list.insert("end", f"{prefix}{item}")
        if not files:
            self.files_list.insert("end", "(无变更文件)")

    def _apply_branches(self, names: list[str], current: str) -> None:
        self._branch_items = list(names)
        self.checkout_combo.configure(values=names)
        if current:
            self.checkout_var.set(current)

    def refresh_diff(self) -> None:
        path = self._repo_path()
        if not path.exists() or not git_ops.is_repo(path):
            self._set_diff_text("（当前路径不是 Git 仓库）")
            return
        paths = self._selected_paths()

        def worker():
            text = git_ops.diff_summary(path, paths=paths, max_patch_chars=20000)
            hits = collect_sensitive_files(path, paths)
            if hits:
                text = (text or "") + "\n" + format_sensitive_warning(hits)
            return text or "(无 diff)"

        def done(text):
            self._set_diff_text(text)

        self._run_async("预览 Diff", worker, done)

    def refresh_files(self) -> None:
        path = self._repo_path()
        if not path.exists() or not git_ops.is_repo(path):
            self.files_list.delete(0, "end")
            self._file_items = []
            self._set_diff_text("（当前路径不是 Git 仓库）")
            return
        paths = self._selected_paths()

        def worker():
            files = git_ops.list_changed_files(path)
            text = git_ops.diff_summary(path, paths=paths, max_patch_chars=20000)
            hits = collect_sensitive_files(path, paths)
            if hits:
                text = (text or "") + "\n" + format_sensitive_warning(hits)
            return {"files": files, "diff": text or "(无 diff)"}

        def done(payload):
            self._apply_files_list(payload["files"])
            self._set_diff_text(payload["diff"])

        self._run_async("刷新文件列表", worker, done)

    def refresh_branches(self) -> None:
        path = self._repo_path()
        if not path.exists() or not git_ops.is_repo(path):
            self._branch_items = []
            self.checkout_combo.configure(values=[])
            return

        def worker():
            names = git_ops.list_branch_names(path, remote=False)
            current = git_ops.current_branch(path)
            cur = current.stdout if current.ok and current.stdout else ""
            return {"names": names, "current": cur}

        def done(payload):
            self._apply_branches(payload["names"], payload["current"])

        self._run_async("刷新分支", worker, done)

    def refresh_status(self) -> None:
        path = self._repo_path()

        def worker():
            check = git_ops.ensure_git_available()
            if not check.ok:
                return {"kind": "no_git", "message": check.message}
            if not path.exists():
                return {"kind": "missing", "path": str(path)}
            if not git_ops.is_repo(path):
                return {"kind": "not_repo", "path": str(path)}

            branch = git_ops.current_branch(path)
            remote = git_ops.remote_get(path)
            branch_name = branch.stdout if branch.ok and branch.stdout else "?"
            remote_url = remote.stdout if remote.ok else "(未配置 origin)"
            up = "有 upstream" if git_ops.has_upstream(path) else "无 upstream"
            files = git_ops.list_changed_files(path)
            names = git_ops.list_branch_names(path, remote=False)
            current = branch.stdout if branch.ok and branch.stdout else ""
            text = git_ops.diff_summary(path, paths=None, max_patch_chars=20000)
            hits = collect_sensitive_files(path, None)
            if hits:
                text = (text or "") + "\n" + format_sensitive_warning(hits)
            return {
                "kind": "ok",
                "path": str(path),
                "status": f"状态: 仓库 · 分支 {branch_name} · {up} · {remote_url}",
                "remote_url": remote.stdout if remote.ok else "",
                "files": files,
                "branches": names,
                "current": current,
                "diff": text or "(无 diff)",
            }

        def done(payload):
            kind = payload["kind"]
            if kind == "no_git":
                self.status_label.configure(text=f"状态: {payload['message']}")
                self.log_err(payload["message"])
                return
            if kind == "missing":
                self.status_label.configure(text=f"状态: 路径不存在 — {payload['path']}")
                return
            if kind == "not_repo":
                self.status_label.configure(text=f"状态: 非仓库 — {payload['path']}")
                self.files_list.delete(0, "end")
                self._file_items = []
                self._branch_items = []
                self.checkout_combo.configure(values=[])
                self._set_diff_text("（当前路径不是 Git 仓库）")
                return

            self.status_label.configure(text=payload["status"])
            if payload["remote_url"] and not self.remote_var.get().strip():
                self.remote_var.set(payload["remote_url"])
            self._apply_files_list(payload["files"])
            self._apply_branches(payload["branches"], payload["current"])
            self._set_diff_text(payload["diff"])
            self._persist()
            self.log_info(f"已刷新: {payload['path']}")

        self._run_async("刷新状态", worker, done)

    def _selected_paths(self) -> Optional[list[str]]:
        """选中的文件；全选/无选则提交全部。"""
        if not self._file_items:
            return None
        indices = self.files_list.curselection()
        if not indices:
            return None
        selected = []
        for i in indices:
            if 0 <= i < len(self._file_items):
                selected.append(self._file_items[i])
        if not selected or len(selected) == len(self._file_items):
            return None
        return selected

    def _confirm_sensitive(
        self,
        path: Path,
        paths: Optional[list[str]],
    ) -> Optional[bool]:
        """
        敏感文件确认。
        返回 True=强制继续，False=取消，None=无敏感文件。
        """
        hits = collect_sensitive_files(path, paths)
        if not hits:
            return None
        warning = format_sensitive_warning(hits)
        self.log_err(warning)
        ok = messagebox.askyesno(
            "敏感文件提醒",
            f"{warning}\n\n是否强制继续？",
            icon="warning",
        )
        return bool(ok)

    def do_init(self) -> None:
        path = self._repo_path()
        branch = self.branch_var.get().strip() or "main"

        def worker():
            check = git_ops.ensure_git_available()
            if not check.ok:
                return ("err", check.message)
            if git_ops.is_repo(path):
                return ("exists", None)
            result = git_ops.init_repo(path, initial_branch=branch)
            return ("result", result)

        def done(payload):
            kind = payload[0]
            if kind == "err":
                self.log_err(payload[1])
                messagebox.showerror("错误", payload[1])
            elif kind == "exists":
                self.log_ok("已是 Git 仓库，无需初始化")
                messagebox.showinfo("提示", "该目录已是 Git 仓库")
                self.refresh_status()
            else:
                result = payload[1]
                if result.ok:
                    self.log_ok(f"初始化成功（分支 {branch}）")
                    messagebox.showinfo("成功", f"已初始化仓库\n{path}")
                else:
                    self.log_err(result.message)
                    messagebox.showerror("失败", result.message)
                self.refresh_status()

        self._run_async("初始化仓库", worker, done)

    def do_set_remote(self) -> None:
        path = self._repo_path()
        url = self.remote_var.get().strip()
        if not validate_remote_url(url):
            msg = f"远程 URL 无效: {url}"
            self.log_err(msg)
            messagebox.showerror("错误", msg)
            return
        if not git_ops.is_repo(path):
            msg = f"不是 Git 仓库: {path}"
            self.log_err(msg)
            messagebox.showerror("错误", msg)
            return

        def worker():
            return git_ops.remote_set_url(path, url, name="origin")

        def done(result):
            if result.ok:
                self.log_ok(f"已设置 origin → {url}")
                self._persist()
                messagebox.showinfo("成功", f"已设置 origin\n{url}")
            else:
                self.log_err(result.message)
                messagebox.showerror("失败", result.message)
            self.refresh_status()

        self._run_async("设置远程", worker, done)

    def do_commit(self) -> None:
        path = self._repo_path()
        message = self._message()
        if not message:
            messagebox.showwarning("提示", "提交说明不能为空")
            return
        paths = self._selected_paths()
        sens = self._confirm_sensitive(path, paths)
        if sens is False:
            self.log_info("已取消（敏感文件）")
            return
        force = sens is True

        def worker():
            return commit_only(path, message=message, paths=paths, force=force)

        def done(result):
            self._show_workflow_result(result)
            self.refresh_status()

        self._run_async("提交", worker, done)

    def do_ship(self) -> None:
        path = self._repo_path()
        message = self._message()
        if not message:
            messagebox.showwarning("提示", "提交说明不能为空")
            return
        paths = self._selected_paths()
        sens = self._confirm_sensitive(path, paths)
        if sens is False:
            self.log_info("已取消（敏感文件）")
            return
        force = sens is True

        def worker():
            return ship(path, message=message, paths=paths, force=force)

        def done(result):
            self._show_workflow_result(result)
            self.refresh_status()

        self._run_async("提交并推送", worker, done)

    def do_bootstrap(self) -> None:
        path = self._repo_path()
        message = self._message()
        url = self.remote_var.get().strip()
        branch = self.branch_var.get().strip() or "main"
        if not message:
            messagebox.showwarning("提示", "提交说明不能为空")
            return
        if not url:
            messagebox.showwarning("提示", "请填写远程 URL")
            return
        if not validate_remote_url(url):
            messagebox.showerror("错误", f"远程 URL 无效: {url}")
            return
        if not messagebox.askyesno(
            "确认 Bootstrap",
            f"将在以下目录执行 init/add/commit/push：\n{path}\n\n远程: {url}\n是否继续？",
        ):
            return
        sens = self._confirm_sensitive(path, None)
        if sens is False:
            self.log_info("已取消（敏感文件）")
            return
        force = sens is True

        def worker():
            return bootstrap(
                path, remote_url=url, message=message, branch=branch, force=force
            )

        def done(result):
            self._show_workflow_result(result)
            self._persist()
            self.refresh_status()

        self._run_async("Bootstrap", worker, done)

    def do_ship_dry_run(self) -> None:
        path = self._repo_path()
        message = self._message()
        if not message:
            messagebox.showwarning("提示", "提交说明不能为空（试运行也需要）")
            return
        paths = self._selected_paths()

        def worker():
            return ship(path, message=message, paths=paths, dry_run=True)

        def done(result):
            self._show_workflow_result(result, dry_run=True)
            if result.detail.strip():
                self._set_diff_text(result.detail)

        self._run_async("试运行 Ship", worker, done)

    def do_bootstrap_dry_run(self) -> None:
        path = self._repo_path()
        message = self._message()
        url = self.remote_var.get().strip()
        branch = self.branch_var.get().strip() or "main"
        if not message:
            messagebox.showwarning("提示", "提交说明不能为空（试运行也需要）")
            return
        if not url:
            messagebox.showwarning("提示", "请填写远程 URL")
            return
        if not validate_remote_url(url):
            messagebox.showerror("错误", f"远程 URL 无效: {url}")
            return

        def worker():
            return bootstrap(
                path,
                remote_url=url,
                message=message,
                branch=branch,
                dry_run=True,
            )

        def done(result):
            self._show_workflow_result(result, dry_run=True)
            if result.detail.strip():
                self._set_diff_text(result.detail)

        self._run_async("试运行 Bootstrap", worker, done)

    def do_pull(self) -> None:
        self._do_pull(rebase=False)

    def do_pull_rebase(self) -> None:
        self._do_pull(rebase=True)

    def _do_pull(self, *, rebase: bool) -> None:
        path = self._repo_path()
        label = "Pull --rebase" if rebase else "Pull"

        def worker():
            return pull_workflow(path, rebase=rebase)

        def done(result):
            self._show_workflow_result(result)
            self.refresh_status()

        self._run_async(label, worker, done)

    def do_checkout(self) -> None:
        self._do_checkout(create=False)

    def do_checkout_create(self) -> None:
        self._do_checkout(create=True)

    def _do_checkout(self, *, create: bool) -> None:
        path = self._repo_path()
        name = self.checkout_var.get().strip()
        if not name:
            messagebox.showwarning("提示", "请填写分支名")
            return
        label = "新建并切换分支" if create else "切换分支"

        def worker():
            return checkout_workflow(path, name, create=create)

        def done(result):
            self._show_workflow_result(result)
            self.refresh_status()

        self._run_async(label, worker, done)

    def do_check_sensitive(self) -> None:
        path = self._repo_path()
        if not path.exists() or not git_ops.is_repo(path):
            messagebox.showinfo("提示", "当前不是 Git 仓库")
            return
        paths = self._selected_paths()
        hits = collect_sensitive_files(path, paths)
        if not hits:
            self.log_ok("未发现疑似敏感文件")
            messagebox.showinfo("敏感检查", "未发现疑似敏感文件")
            return
        warning = format_sensitive_warning(hits)
        self.log_err(warning)
        messagebox.showwarning("敏感检查", warning)

    def _show_workflow_result(self, result, *, dry_run: bool = False) -> None:
        for step in result.steps:
            self.log_info(f"  · {step}")
        if result.ok:
            self.log_ok(result.message)
            if result.detail.strip() and not dry_run:
                preview = result.detail.strip()
                if len(preview) > 800:
                    preview = preview[:800] + "\n…"
                self.log.append(preview, "muted")
            title = "试运行" if dry_run else "成功"
            messagebox.showinfo(title, result.message)
        else:
            self.log_err(result.message)
            if result.detail.strip():
                self.log.append(result.detail.strip(), "error")
            messagebox.showerror("失败", result.message)


    def clear_log(self) -> None:
        self.log.clear()

    def show_help(self, mark_seen: bool = False) -> None:
        """弹出使用说明窗口。"""
        win = tk.Toplevel(self.master)
        win.title("Git Ship — 使用说明")
        win.geometry("640x520")
        win.minsize(480, 360)
        win.transient(self.master)
        try:
            win.grab_set()
        except tk.TclError:
            pass

        frame = ttk.Frame(win, padding=12)
        frame.pack(fill="both", expand=True)
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(0, weight=1)

        text = tk.Text(
            frame,
            wrap="word",
            font=("Microsoft YaHei UI", 10),
            relief="solid",
            borderwidth=1,
            padx=8,
            pady=8,
        )
        scroll = ttk.Scrollbar(frame, orient="vertical", command=text.yview)
        text.configure(yscrollcommand=scroll.set)
        text.grid(row=0, column=0, sticky="nsew")
        scroll.grid(row=0, column=1, sticky="ns")

        help_body = (
            "Git Ship 使用说明\n"
            "════════════════════════════════════\n\n"
            "一、准备工作\n"
            "  1. 系统已安装 Git，终端可执行 git --version\n"
            "  2. 推送使用系统 Git 凭据（本工具不保存账号密码）\n"
            "  3. 默认 HTTPS；支持 GitHub / GitLab / Gitee 模板\n\n"
            "二、日常提交流程（已有仓库）\n"
            "  1. 浏览选择仓库路径 → 刷新\n"
            "  2. 左侧查看变更文件，可选中部分文件\n"
            "  3. 右侧 Diff 预览确认改动\n"
            "  4. 填写提交说明（不可为空）\n"
            "  5. 「提交」仅本地 commit；「提交并推送」= ship\n"
            "  6. 建议先点「试运行 Ship」预览计划，再正式推送\n\n"
            "三、新仓库 Bootstrap\n"
            "  1. 选择空目录或项目目录\n"
            "  2. 填写 Owner/Repo 生成 URL，或直接粘贴远程 URL\n"
            "  3. 设置初始分支（默认 main）\n"
            "  4. 填写提交说明 → Bootstrap（初始化并推送）\n"
            "  5. 可用「试运行 Bootstrap」只看计划不写仓库\n\n"
            "四、分支与同步\n"
            "  · 下拉选择本地分支 →「切换」\n"
            "  · 输入新分支名 →「新建并切换」\n"
            "  · Pull / Pull --rebase 拉取远程更新\n\n"
            "五、敏感文件提醒\n"
            "  · 变更列表中 ⚠ 标记疑似密钥、.env 等文件\n"
            "  · 提交/推送前会弹窗确认；确认后才会继续\n"
            "  · 也可点「敏感检查」单独扫描\n\n"
            "六、其他说明\n"
            "  · 不支持 force push，避免误覆盖远程历史\n"
            "  · 耗时操作在后台执行，期间按钮会暂时禁用\n"
            "  · 配置保存在 ~/.git-ship/config.json\n"
            "  · CLI 用法见项目 README（git_ship_cli.py）\n\n"
            "快捷建议：先试运行 → 再正式提交/推送。\n"
        )
        text.insert("1.0", help_body)
        text.configure(state="disabled")

        btn_row = ttk.Frame(frame)
        btn_row.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(10, 0))

        dont_show = tk.BooleanVar(value=bool(self._cfg.get("help_seen")))

        def _close() -> None:
            if mark_seen or dont_show.get():
                self._cfg["help_seen"] = True
                try:
                    app_config.save_config(self._cfg)
                except OSError:
                    pass
            win.destroy()

        if mark_seen or not bool(self._cfg.get("help_seen")):
            ttk.Checkbutton(
                btn_row,
                text="不再自动弹出",
                variable=dont_show,
            ).pack(side="left")

        ttk.Button(btn_row, text="关闭", command=_close, width=10).pack(side="right")
        win.protocol("WM_DELETE_WINDOW", _close)
        win.focus_set()


def run_app() -> None:
    root = tk.Tk()
    MainWindow(root)
    root.mainloop()
