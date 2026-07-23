# -*- coding: utf-8 -*-
"""敏感文件检测：提交/推送前提醒，不阻止（可强制继续）。"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable, Sequence

# 常见敏感文件名（小写匹配 basename）
SENSITIVE_BASENAMES = frozenset(
    {
        ".env",
        ".env.local",
        ".env.production",
        ".env.development",
        ".env.staging",
        ".env.test",
        ".env.prod",
        ".env.dev",
        "credentials.json",
        "service-account.json",
        "id_rsa",
        "id_dsa",
        "id_ecdsa",
        "id_ed25519",
        "secrets.yaml",
        "secrets.yml",
        "secrets.json",
        "private.key",
        "private.pem",
        "keystore.jks",
        "keystore.p12",
        "google-services.json",
        "agconnect-services.json",
    }
)

# 路径片段：需结合文件类型判断（.ssh 下任意文件视为敏感）
SENSITIVE_PATH_PARTS = frozenset(
    {
        ".ssh",
        "secrets",
        "credentials",
    }
)

# secrets/credentials 目录下视为配置/密钥的扩展名（排除 .md/.txt 文档）
_PATH_CONFIG_EXTENSIONS = frozenset(
    {
        ".json",
        ".yml",
        ".yaml",
        ".toml",
        ".ini",
        ".env",
        ".properties",
        ".conf",
        ".cfg",
        ".pem",
        ".p12",
        ".pfx",
        ".jks",
        ".keystore",
        ".key",
    }
)

# 扩展名
SENSITIVE_EXTENSIONS = frozenset(
    {
        ".pem",
        ".p12",
        ".pfx",
        ".jks",
        ".keystore",
        ".key",
    }
)

# 通常可提交：公钥、示例/模板
_SAFE_NAME_SUFFIXES = (
    ".pub",
    ".example",
    ".sample",
    ".template",
    ".dist",
)

# 正则：仅匹配 basename 上的具体敏感命名（避免 secret/token 等裸子串）
_SENSITIVE_NAME_PATTERNS = (
    re.compile(r"^\.env(\.|$)", re.I),
    re.compile(r"\.env$", re.I),
    re.compile(
        r"(^|[._-])secrets?([._-].*)?\.(json|ya?ml|toml|ini|env|properties)$",
        re.I,
    ),
    re.compile(r"credentials?\.(json|ya?ml|toml|ini|env)$", re.I),
    re.compile(
        r"(password|passwd|token)s?\.(json|ya?ml|toml|txt|env|properties)$",
        re.I,
    ),
    re.compile(r"^id_(rsa|ed25519|ecdsa|dsa)$", re.I),
)


def _has_safe_suffix(name_lower: str) -> bool:
    return any(name_lower.endswith(s) for s in _SAFE_NAME_SUFFIXES)


def _has_sensitive_extension(name_lower: str) -> bool:
    """检查后缀链是否含敏感扩展名（如 private.pem.bak）。"""
    return any(s in SENSITIVE_EXTENSIONS for s in Path(name_lower).suffixes)


def _path_part_hit(parent_parts: set[str], name_lower: str, suffix: str) -> bool:
    """路径段命中：.ssh 任意文件；secrets/credentials 仅配置/密钥类文件。"""
    if ".ssh" in parent_parts:
        return True
    if parent_parts & {"secrets", "credentials"}:
        return suffix in _PATH_CONFIG_EXTENSIONS or name_lower in SENSITIVE_BASENAMES
    return False


def is_sensitive_path(path: str) -> bool:
    """判断单个路径是否疑似敏感。"""
    raw = (path or "").strip().replace("\\", "/")
    if not raw:
        return False
    # 去掉重命名左侧
    if " -> " in raw:
        raw = raw.split(" -> ", 1)[1].strip()

    p = Path(raw)
    name = p.name
    name_lower = name.lower()

    if not name_lower or _has_safe_suffix(name_lower):
        return False

    if name_lower in SENSITIVE_BASENAMES:
        return True

    if _has_sensitive_extension(name_lower):
        return True

    for pattern in _SENSITIVE_NAME_PATTERNS:
        if pattern.search(name):
            return True

    parent_parts = {part.lower() for part in p.parts[:-1] if part not in (".", "..")}
    if _path_part_hit(parent_parts, name_lower, p.suffix.lower()):
        return True

    return False


def find_sensitive_files(paths: Sequence[str] | Iterable[str]) -> list[str]:
    """从路径列表中筛出敏感文件（保持顺序、去重）。"""
    seen: set[str] = set()
    hits: list[str] = []
    for item in paths:
        text = (item or "").strip()
        if not text or text in seen:
            continue
        if is_sensitive_path(text):
            seen.add(text)
            hits.append(text)
    return hits


def format_sensitive_warning(files: Sequence[str], *, limit: int = 20) -> str:
    """生成可读警告文本。"""
    if not files:
        return ""
    lines = [
        f"⚠ 检测到 {len(files)} 个疑似敏感文件，请确认后再提交/推送：",
    ]
    for item in list(files)[:limit]:
        lines.append(f"  - {item}")
    if len(files) > limit:
        lines.append(f"  … 另有 {len(files) - limit} 个")
    lines.append("如确认无误，可使用 --force 或 GUI 确认后继续。")
    return "\n".join(lines)
