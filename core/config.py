# -*- coding: utf-8 -*-
"""用户配置：路径与默认项（简单 JSON）。"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

APP_NAME = "git-ship"
CONFIG_DIR_NAME = ".git-ship"
CONFIG_FILE_NAME = "config.json"

DEFAULTS: dict[str, Any] = {
    "default_branch": "main",
    "default_protocol": "https",
    "default_provider": "github",
    "last_repo_path": "",
    "last_remote_url": "",
    "help_seen": False,
}


def get_config_dir() -> Path:
    """用户配置目录：~/.git-ship/（Windows 下为用户主目录）。"""
    home = Path.home()
    # 允许通过环境变量覆盖
    override = os.environ.get("GIT_SHIP_HOME", "").strip()
    if override:
        return Path(override).expanduser().resolve()
    return (home / CONFIG_DIR_NAME).resolve()


def get_config_path() -> Path:
    return get_config_dir() / CONFIG_FILE_NAME


def ensure_config_dir() -> Path:
    path = get_config_dir()
    path.mkdir(parents=True, exist_ok=True)
    return path


def load_config() -> dict[str, Any]:
    """加载配置，失败时返回默认值副本。"""
    cfg = dict(DEFAULTS)
    path = get_config_path()
    if not path.is_file():
        return cfg
    try:
        with path.open("r", encoding="utf-8") as fp:
            data = json.load(fp)
        if isinstance(data, dict):
            for key, value in data.items():
                cfg[key] = value
    except (OSError, json.JSONDecodeError, TypeError):
        pass
    return cfg


def save_config(config: dict[str, Any]) -> Path:
    """保存配置，返回配置文件路径。"""
    ensure_config_dir()
    path = get_config_path()
    merged = dict(DEFAULTS)
    if isinstance(config, dict):
        merged.update(config)
    with path.open("w", encoding="utf-8") as fp:
        json.dump(merged, fp, ensure_ascii=False, indent=2)
        fp.write("\n")
    return path


def get_default_branch() -> str:
    cfg = load_config()
    branch = str(cfg.get("default_branch") or "main").strip()
    return branch or "main"


def get_default_protocol() -> str:
    cfg = load_config()
    protocol = str(cfg.get("default_protocol") or "https").strip().lower()
    return protocol or "https"
