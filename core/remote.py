# -*- coding: utf-8 -*-
"""远程平台 HTTPS 模板与 URL 校验。"""

from __future__ import annotations

import re
from typing import Optional
from urllib.parse import urlparse

PROVIDERS = ("github", "gitlab", "gitee", "custom")

PROVIDER_LABELS = {
    "github": "GitHub",
    "gitlab": "GitLab",
    "gitee": "Gitee",
    "custom": "自定义",
}

HTTPS_TEMPLATES = {
    "github": "https://github.com/{owner}/{repo}.git",
    "gitlab": "https://gitlab.com/{owner}/{repo}.git",
    "gitee": "https://gitee.com/{owner}/{repo}.git",
}

_OWNER_REPO_RE = re.compile(r"^[A-Za-z0-9_.-]+$")
_HTTPS_GIT_RE = re.compile(
    r"^https://[A-Za-z0-9._~:/?#\[\]@!$&'()*+,;=%-]+$",
    re.IGNORECASE,
)


def build_https_url(provider: str, owner: str, repo: str) -> str:
    """按平台模板构建 HTTPS 远程 URL。"""
    key = (provider or "").strip().lower()
    if key not in HTTPS_TEMPLATES:
        raise ValueError(f"不支持的平台: {provider}（可选: github/gitlab/gitee）")
    owner = (owner or "").strip().strip("/")
    repo = (repo or "").strip().strip("/")
    if repo.endswith(".git"):
        repo = repo[:-4]
    if not owner or not repo:
        raise ValueError("owner 与 repo 不能为空")
    if not _OWNER_REPO_RE.match(owner) or not _OWNER_REPO_RE.match(repo):
        raise ValueError("owner/repo 仅允许字母、数字、点、下划线、连字符")
    return HTTPS_TEMPLATES[key].format(owner=owner, repo=repo)


def validate_remote_url(url: str) -> bool:
    """校验远程 URL（P0 以 HTTPS 为主，也接受常见 git@ SSH 形式便于识别）。"""
    text = (url or "").strip()
    if not text or any(ch.isspace() for ch in text):
        return False

    # SSH: git@host:owner/repo.git
    if text.startswith("git@"):
        return bool(re.match(r"^git@[^:\s]+:[^\s]+\.git$", text))

    if not text.lower().startswith("https://"):
        return False
    if not _HTTPS_GIT_RE.match(text):
        return False

    parsed = urlparse(text)
    if parsed.scheme.lower() != "https":
        return False
    if not parsed.netloc or not parsed.path or parsed.path == "/":
        return False
    # 路径至少要有一段
    parts = [p for p in parsed.path.split("/") if p]
    if len(parts) < 1:
        return False
    return True


def detect_provider(url: str) -> str:
    """根据 URL 识别平台，无法识别则 custom。"""
    text = (url or "").strip().lower()
    if not text:
        return "custom"

    host = ""
    if text.startswith("git@"):
        # git@github.com:owner/repo.git
        try:
            host = text.split("@", 1)[1].split(":", 1)[0]
        except IndexError:
            return "custom"
    else:
        parsed = urlparse(text if "://" in text else f"https://{text}")
        host = (parsed.netloc or "").lower()
        if "@" in host:
            host = host.rsplit("@", 1)[-1]
        if ":" in host and not host.startswith("["):
            host = host.split(":", 1)[0]

    if host in ("github.com", "www.github.com"):
        return "github"
    if host in ("gitlab.com", "www.gitlab.com"):
        return "gitlab"
    if host in ("gitee.com", "www.gitee.com"):
        return "gitee"
    return "custom"


def normalize_repo_name(name: str) -> str:
    """去掉 .git 后缀。"""
    text = (name or "").strip()
    if text.endswith(".git"):
        return text[:-4]
    return text


def parse_owner_repo(url: str) -> Optional[tuple[str, str]]:
    """尝试从 URL 解析 owner/repo。"""
    text = (url or "").strip()
    if not text:
        return None

    path = ""
    if text.startswith("git@"):
        try:
            path = text.split(":", 1)[1]
        except IndexError:
            return None
    else:
        parsed = urlparse(text if "://" in text else f"https://{text}")
        path = parsed.path or ""

    parts = [p for p in path.strip("/").split("/") if p]
    if len(parts) < 2:
        return None
    owner = parts[0]
    repo = normalize_repo_name(parts[1])
    if not owner or not repo:
        return None
    return owner, repo
