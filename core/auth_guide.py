# -*- coding: utf-8 -*-
"""凭据配置引导与只读诊断（不接管认证、不存储密码）。"""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

from core.remote import detect_provider

# 官方文档（只读引导用）
DOC_LINKS = {
    "github_https": (
        "https://docs.github.com/zh/authentication/"
        "keeping-your-account-and-data-secure/managing-your-personal-access-tokens"
    ),
    "github_ssh": (
        "https://docs.github.com/zh/authentication/connecting-to-github-with-ssh"
    ),
    "gitlab_https": "https://docs.gitlab.com/ee/user/profile/personal_access_tokens.html",
    "gitlab_ssh": "https://docs.gitlab.com/ee/user/ssh.html",
    "gitee_https": "https://gitee.com/help/articles/4191",
    "gitee_ssh": "https://gitee.com/help/articles/4181",
    "gcm": "https://github.com/git-ecosystem/git-credential-manager",
    "gcm_install": (
        "https://github.com/git-ecosystem/git-credential-manager/blob/release/docs/install.md"
    ),
}

_AUTH_MARKERS = (
    "authentication failed",
    "could not read username",
    "invalid username or password",
    "permission denied",
    "publickey",
    "host key verification failed",
    "access denied",
    "terminal prompts disabled",
    "could not read password",
    "auth fail",
    "unauthorized",
)


@dataclass
class CheckItem:
    """单项诊断结果。"""

    name: str
    ok: bool
    detail: str


@dataclass
class DiagnosisResult:
    """凭据环境只读诊断。"""

    items: list[CheckItem] = field(default_factory=list)
    protocol: str = "unknown"  # https | ssh | unknown
    provider: str = "custom"
    remote_url: str = ""

    @property
    def summary_lines(self) -> list[str]:
        lines: list[str] = []
        for item in self.items:
            mark = "OK" if item.ok else "!!"
            lines.append(f"[{mark}] {item.name}: {item.detail}")
        return lines


def is_auth_error(text: str) -> bool:
    """判断文本是否像认证失败。"""
    lower = (text or "").lower()
    if not lower:
        return False
    if any(m in lower for m in _AUTH_MARKERS):
        return True
    # 常见 HTTP 状态（避免误伤普通输出中的 401/403 需结合上下文，此处仅作弱匹配）
    if " 401 " in f" {lower} " or " 403 " in f" {lower} ":
        return True
    if "status code 401" in lower or "status code 403" in lower:
        return True
    return False


def classify_protocol(url: str) -> str:
    """识别远程 URL 协议：https / ssh / unknown。"""
    text = (url or "").strip()
    if not text:
        return "unknown"
    lower = text.lower()
    if lower.startswith("git@") or lower.startswith("ssh://"):
        return "ssh"
    if lower.startswith("https://"):
        return "https"
    return "unknown"


def ssh_host_from_url(url: str) -> str:
    """从 SSH/HTTPS URL 提取主机名。"""
    text = (url or "").strip()
    if not text:
        return ""
    if text.startswith("git@"):
        try:
            return text.split("@", 1)[1].split(":", 1)[0]
        except IndexError:
            return ""
    parsed = urlparse(text if "://" in text else f"https://{text}")
    return (parsed.hostname or "").strip()


def default_ssh_test_target(url: str = "", provider: str = "") -> str:
    """生成 ssh -T 探测目标，如 git@github.com。"""
    host = ssh_host_from_url(url)
    if host:
        return f"git@{host}"
    key = (provider or "").strip().lower()
    mapping = {
        "github": "git@github.com",
        "gitlab": "git@gitlab.com",
        "gitee": "git@gitee.com",
    }
    return mapping.get(key, "git@github.com")


def format_auth_help(
    *,
    protocol: str = "auto",
    provider: str = "",
    remote_url: str = "",
) -> str:
    """生成「如何配置凭据」说明（纯文案，不执行诊断）。"""
    proto = (protocol or "auto").strip().lower()
    if proto == "auto":
        proto = classify_protocol(remote_url)
    prov = (provider or detect_provider(remote_url) or "custom").strip().lower()
    system = platform.system()

    lines: list[str] = [
        "如何配置 Git 凭据（Git Ship 不保存账号密码）",
        "════════════════════════════════════",
        "",
        "原则：",
        "  · 本工具通过系统 git 推送，禁用交互式密码输入（GIT_TERMINAL_PROMPT=0）",
        "  · 请在系统侧预先配置 HTTPS Token 或 SSH Key，再重试推送",
        "  · 不要把密码写进远程 URL，也不要提交 token 到仓库",
        "",
    ]

    if proto in ("https", "unknown", "auto"):
        lines.extend(
            [
                "一、HTTPS（Personal Access Token + 凭据助手）",
                "  1. 在平台创建 PAT / 私人令牌（不要用账户登录密码）",
                "  2. 安装或启用 Git Credential Manager（GCM）",
                "  3. 执行一次 git push / git pull，按系统弹窗登录或粘贴 Token",
                "  4. 之后凭据由系统保管，Git Ship 直接复用",
                "",
            ]
        )
        if system == "Windows":
            lines.extend(
                [
                    "  Windows 提示：",
                    "  · 官方 Git for Windows 通常已带 GCM",
                    "  · 检查：git config --global credential.helper",
                    "  · 常见值：manager / manager-core",
                    "  · 也可在「凭据管理器」中管理 github.com 条目",
                    "",
                ]
            )
        elif system == "Darwin":
            lines.extend(
                [
                    "  macOS 提示：",
                    "  · 可用 osxkeychain：git config --global credential.helper osxkeychain",
                    "  · 或安装 Git Credential Manager",
                    "",
                ]
            )
        else:
            lines.extend(
                [
                    "  Linux 提示：",
                    "  · 可安装 Git Credential Manager，或使用 libsecret / store（按需）",
                    "  · 检查：git config --global credential.helper",
                    "",
                ]
            )

    if proto in ("ssh", "unknown", "auto"):
        lines.extend(
            [
                "二、SSH（推荐长期使用）",
                "  1. 生成密钥：ssh-keygen -t ed25519 -C \"your@email\"",
                "  2. 将公钥（*.pub）添加到平台 SSH Keys",
                "  3. 远程使用 SSH 地址，例如 git@github.com:owner/repo.git",
                "  4. 验证：ssh -T git@github.com（或对应主机）",
                "  5. 若密钥有口令，请先用 ssh-agent 加载，避免交互卡死",
                "",
            ]
        )
        if system == "Windows":
            lines.extend(
                [
                    "  Windows 提示：",
                    "  · OpenSSH 客户端：设置 → 应用 → 可选功能",
                    "  · 可启用 ssh-agent 服务并 ssh-add 私钥",
                    "",
                ]
            )

    lines.extend(
        [
            "三、相关文档",
        ]
    )
    docs = _docs_for(prov)
    for title, link in docs:
        lines.append(f"  · {title}: {link}")
    lines.extend(
        [
            "",
            "四、本工具相关",
            "  · CLI 诊断：python git_ship_cli.py doctor [--path .]",
            "  · GUI：操作区 →「配置凭据」",
            "  · 超时：GIT_SHIP_TIMEOUT / GIT_SHIP_REMOTE_TIMEOUT（秒）",
            "",
            "配置完成后，回到 Git Ship 重新执行「提交并推送」或 Bootstrap 即可。",
        ]
    )
    return "\n".join(lines)


def _docs_for(provider: str) -> list[tuple[str, str]]:
    key = (provider or "custom").lower()
    items: list[tuple[str, str]] = []
    if key == "github":
        items.append(("GitHub HTTPS (PAT)", DOC_LINKS["github_https"]))
        items.append(("GitHub SSH", DOC_LINKS["github_ssh"]))
    elif key == "gitlab":
        items.append(("GitLab HTTPS (PAT)", DOC_LINKS["gitlab_https"]))
        items.append(("GitLab SSH", DOC_LINKS["gitlab_ssh"]))
    elif key == "gitee":
        items.append(("Gitee HTTPS", DOC_LINKS["gitee_https"]))
        items.append(("Gitee SSH", DOC_LINKS["gitee_ssh"]))
    else:
        items.append(("GitHub HTTPS (PAT，通用参考)", DOC_LINKS["github_https"]))
        items.append(("GitHub SSH（通用参考）", DOC_LINKS["github_ssh"]))
    items.append(("Git Credential Manager", DOC_LINKS["gcm"]))
    items.append(("GCM 安装说明", DOC_LINKS["gcm_install"]))
    return items


def _run_capture(
    command: list[str],
    *,
    timeout: float = 15.0,
    env: Optional[dict] = None,
) -> tuple[int, str, str]:
    run_env = os.environ.copy()
    if env:
        run_env.update(env)
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
            env=run_env,
        )
        return (
            completed.returncode,
            (completed.stdout or "").strip(),
            (completed.stderr or "").strip(),
        )
    except FileNotFoundError:
        return 127, "", f"未找到命令: {command[0]}"
    except subprocess.TimeoutExpired:
        return 124, "", f"命令超时: {' '.join(command)}"
    except OSError as exc:
        return 1, "", str(exc)


def _git_config_value(key: str) -> str:
    code, out, _err = _run_capture(["git", "config", "--get", key], timeout=10)
    if code != 0:
        return ""
    return out.strip()


def _list_ssh_public_keys() -> list[str]:
    ssh_dir = Path.home() / ".ssh"
    if not ssh_dir.is_dir():
        return []
    names: list[str] = []
    for pattern in ("id_ed25519.pub", "id_rsa.pub", "id_ecdsa.pub", "id_dsa.pub"):
        if (ssh_dir / pattern).is_file():
            names.append(pattern)
    # 也识别其他 *.pub（不读内容）
    try:
        for path in sorted(ssh_dir.glob("*.pub")):
            if path.name not in names:
                names.append(path.name)
    except OSError:
        pass
    return names


def diagnose_auth(
    *,
    remote_url: str = "",
    run_ssh_test: bool = True,
) -> DiagnosisResult:
    """只读诊断：git / 凭据助手 / SSH 密钥 / 可选 ssh -T。不交互、不存密。"""
    result = DiagnosisResult(
        remote_url=(remote_url or "").strip(),
        protocol=classify_protocol(remote_url),
        provider=detect_provider(remote_url) if remote_url else "custom",
    )

    git_path = shutil.which("git")
    if git_path:
        code, out, err = _run_capture(["git", "--version"], timeout=10)
        detail = out or err or git_path
        result.items.append(CheckItem("Git 可执行", code == 0, detail))
    else:
        result.items.append(
            CheckItem("Git 可执行", False, "未在 PATH 中找到 git，请先安装 Git")
        )
        return result

    helper = _git_config_value("credential.helper")
    if helper:
        result.items.append(CheckItem("credential.helper", True, helper))
    else:
        hint = "未配置。Windows 建议安装/启用 Git Credential Manager（manager-core）"
        if platform.system() == "Darwin":
            hint = "未配置。可设置 osxkeychain 或安装 GCM"
        elif platform.system() != "Windows":
            hint = "未配置。可安装 GCM 或按发行版配置 libsecret 等"
        result.items.append(CheckItem("credential.helper", False, hint))

    # GCM 是否在 PATH
    gcm = shutil.which("git-credential-manager") or shutil.which(
        "git-credential-manager-core"
    )
    if gcm:
        result.items.append(CheckItem("Git Credential Manager", True, gcm))
    else:
        # helper 名称里带 manager 也算可能已集成
        if "manager" in (helper or "").lower():
            result.items.append(
                CheckItem(
                    "Git Credential Manager",
                    True,
                    f"已通过 credential.helper 引用（{helper}）",
                )
            )
        else:
            result.items.append(
                CheckItem(
                    "Git Credential Manager",
                    False,
                    f"未检测到独立 GCM 可执行文件。文档: {DOC_LINKS['gcm_install']}",
                )
            )

    pubs = _list_ssh_public_keys()
    if pubs:
        result.items.append(
            CheckItem("本机 SSH 公钥", True, f"发现 {', '.join(pubs)}")
        )
    else:
        result.items.append(
            CheckItem(
                "本机 SSH 公钥",
                False,
                "未在 ~/.ssh 发现 *.pub，若使用 SSH 请先 ssh-keygen",
            )
        )

    ssh_bin = shutil.which("ssh")
    if not ssh_bin:
        result.items.append(CheckItem("OpenSSH 客户端", False, "PATH 中未找到 ssh"))
    else:
        result.items.append(CheckItem("OpenSSH 客户端", True, ssh_bin))

    if run_ssh_test and ssh_bin and result.protocol in ("ssh", "unknown"):
        target = default_ssh_test_target(remote_url, result.provider)
        # BatchMode：绝不交互要密码/口令
        code, out, err = _run_capture(
            [
                "ssh",
                "-o",
                "BatchMode=yes",
                "-o",
                "StrictHostKeyChecking=accept-new",
                "-o",
                "ConnectTimeout=8",
                "-T",
                target,
            ],
            timeout=20,
        )
        combined = f"{out}\n{err}".strip()
        lower = combined.lower()
        # GitHub 成功时仍可能 exit 1，但含 "successfully authenticated"
        success = (
            "successfully authenticated" in lower
            or "you've successfully authenticated" in lower
            or "welcome to gitlab" in lower
            or "authenticated" in lower and "permission denied" not in lower
        )
        if success:
            result.items.append(
                CheckItem(
                    f"ssh -T {target}",
                    True,
                    combined.splitlines()[0] if combined else "认证成功",
                )
            )
        else:
            preview = combined.replace("\n", " ").strip()
            if len(preview) > 200:
                preview = preview[:200] + "…"
            if not preview:
                preview = f"退出码 {code}（BatchMode，未交互）"
            result.items.append(
                CheckItem(
                    f"ssh -T {target}",
                    False,
                    preview or f"失败（code={code}）",
                )
            )
    elif run_ssh_test and result.protocol == "https":
        result.items.append(
            CheckItem(
                "ssh -T",
                True,
                "当前远程为 HTTPS，已跳过 SSH 探测（改用 SSH 地址时可测）",
            )
        )

    if remote_url:
        result.items.append(
            CheckItem(
                "远程 URL",
                True,
                f"{remote_url}（协议={result.protocol}, 平台={result.provider}）",
            )
        )

    return result


def format_diagnosis(diagnosis: DiagnosisResult) -> str:
    """格式化诊断结果。"""
    lines = [
        "凭据环境诊断（只读，不修改任何配置）",
        "────────────────────────────────────",
    ]
    lines.extend(diagnosis.summary_lines)
    lines.append("")
    lines.append("说明：诊断失败不代表无法使用；请按下方文档完成配置后重试推送。")
    return "\n".join(lines)


def format_auth_failure_guide(
    raw_error: str,
    *,
    remote_url: str = "",
    include_diagnosis: bool = True,
) -> str:
    """认证失败时的完整引导：错误摘要 + 诊断 + 配置说明。"""
    protocol = classify_protocol(remote_url)
    provider = detect_provider(remote_url) if remote_url else "custom"
    parts: list[str] = []

    err = (raw_error or "").strip()
    if err:
        parts.append(err)

    parts.append("")
    parts.append("提示：疑似认证/权限失败。Git Ship 不接管登录，请在系统侧配置凭据。")

    if include_diagnosis:
        try:
            diag = diagnose_auth(
                remote_url=remote_url,
                run_ssh_test=(protocol == "ssh"),
            )
            parts.append("")
            parts.append(format_diagnosis(diag))
        except Exception as exc:  # noqa: BLE001 — 诊断失败不影响主流程
            parts.append(f"\n（诊断跳过: {exc}）")

    parts.append("")
    parts.append(
        format_auth_help(
            protocol=protocol if protocol != "unknown" else "auto",
            provider=provider,
            remote_url=remote_url,
        )
    )
    return "\n".join(parts).strip()


def open_doc_urls(provider: str = "", protocol: str = "auto") -> list[str]:
    """返回建议打开的文档 URL 列表。"""
    return [link for _title, link in _docs_for(provider or "custom")]
