# -*- coding: utf-8 -*-
"""可复用小组件。"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Callable, Optional


class LabeledEntry(ttk.Frame):
    """标签 + 输入框（可选按钮）。"""

    def __init__(
        self,
        master,
        label: str,
        textvariable: Optional[tk.Variable] = None,
        button_text: str = "",
        button_command: Optional[Callable[[], None]] = None,
        **kwargs,
    ):
        super().__init__(master, **kwargs)
        self.columnconfigure(1, weight=1)
        ttk.Label(self, text=label, width=10, anchor="w").grid(
            row=0, column=0, sticky="w", padx=(0, 6)
        )
        self.entry = ttk.Entry(self, textvariable=textvariable)
        self.entry.grid(row=0, column=1, sticky="ew")
        if button_text and button_command:
            ttk.Button(self, text=button_text, command=button_command, width=8).grid(
                row=0, column=2, sticky="e", padx=(6, 0)
            )


class LogText(ttk.Frame):
    """带滚动条的操作日志。"""

    def __init__(self, master, **kwargs):
        super().__init__(master, **kwargs)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)

        self.text = tk.Text(
            self,
            wrap="word",
            height=12,
            state="disabled",
            font=("Consolas", 9),
            relief="flat",
            borderwidth=1,
        )
        scroll = ttk.Scrollbar(self, orient="vertical", command=self.text.yview)
        self.text.configure(yscrollcommand=scroll.set)
        self.text.grid(row=0, column=0, sticky="nsew")
        scroll.grid(row=0, column=1, sticky="ns")

        self.text.tag_configure("info", foreground="#1f2937")
        self.text.tag_configure("ok", foreground="#047857")
        self.text.tag_configure("error", foreground="#b91c1c")
        self.text.tag_configure("muted", foreground="#6b7280")

    def append(self, message: str, level: str = "info") -> None:
        tag = level if level in ("info", "ok", "error", "muted") else "info"
        self.text.configure(state="normal")
        self.text.insert("end", message.rstrip() + "\n", tag)
        self.text.see("end")
        self.text.configure(state="disabled")

    def clear(self) -> None:
        self.text.configure(state="normal")
        self.text.delete("1.0", "end")
        self.text.configure(state="disabled")
