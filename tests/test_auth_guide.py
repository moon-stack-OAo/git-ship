# -*- coding: utf-8 -*-
"""auth_guide 单元测试。"""

from __future__ import annotations

import unittest
from unittest import mock

from core.auth_guide import (
    classify_protocol,
    format_auth_failure_guide,
    format_auth_help,
    format_diagnosis,
    is_auth_error,
    open_doc_urls,
    ssh_host_from_url,
    diagnose_auth,
    CheckItem,
    DiagnosisResult,
)


class TestAuthMarkers(unittest.TestCase):
    def test_is_auth_error(self):
        self.assertTrue(is_auth_error("fatal: Authentication failed"))
        self.assertTrue(is_auth_error("Permission denied (publickey)"))
        self.assertTrue(is_auth_error("terminal prompts disabled"))
        self.assertFalse(is_auth_error("Everything up-to-date"))
        self.assertFalse(is_auth_error(""))


class TestProtocol(unittest.TestCase):
    def test_classify(self):
        self.assertEqual(classify_protocol("https://github.com/a/b.git"), "https")
        self.assertEqual(classify_protocol("git@github.com:a/b.git"), "ssh")
        self.assertEqual(classify_protocol("ssh://git@github.com/a/b.git"), "ssh")
        self.assertEqual(classify_protocol(""), "unknown")

    def test_ssh_host(self):
        self.assertEqual(ssh_host_from_url("git@github.com:a/b.git"), "github.com")
        self.assertEqual(
            ssh_host_from_url("ssh://git@gitlab.com/a/b.git"), "gitlab.com"
        )


class TestAuthHelp(unittest.TestCase):
    def test_help_contains_principles(self):
        text = format_auth_help(protocol="https", provider="github")
        self.assertIn("不保存账号密码", text)
        self.assertIn("GIT_TERMINAL_PROMPT", text)
        self.assertIn("Personal Access Token", text)
        self.assertIn("docs.github.com", text)

    def test_help_ssh(self):
        text = format_auth_help(protocol="ssh", provider="github")
        self.assertIn("ssh-keygen", text)
        self.assertIn("ssh -T", text)

    def test_open_doc_urls(self):
        urls = open_doc_urls("github")
        self.assertTrue(any("github.com" in u for u in urls))
        self.assertTrue(any("credential-manager" in u for u in urls))


class TestDiagnosisFormat(unittest.TestCase):
    def test_format_diagnosis(self):
        diag = DiagnosisResult(
            items=[
                CheckItem("Git 可执行", True, "git version 2.0"),
                CheckItem("credential.helper", False, "未配置"),
            ],
            protocol="https",
            provider="github",
        )
        text = format_diagnosis(diag)
        self.assertIn("[OK] Git 可执行", text)
        self.assertIn("[!!] credential.helper", text)

    def test_failure_guide_without_diag(self):
        text = format_auth_failure_guide(
            "Authentication failed",
            remote_url="https://github.com/a/b.git",
            include_diagnosis=False,
        )
        self.assertIn("Authentication failed", text)
        self.assertIn("如何配置 Git 凭据", text)
        self.assertNotIn("凭据环境诊断", text)

    def test_diagnose_auth_mocked(self):
        with mock.patch("core.auth_guide.shutil.which") as which_mock:
            which_mock.side_effect = lambda name: (
                "C:/git/git.exe" if name == "git" else None
            )
            with mock.patch("core.auth_guide._run_capture") as run_mock:
                run_mock.return_value = (0, "git version 2.45.0", "")
                with mock.patch("core.auth_guide._git_config_value", return_value="manager"):
                    with mock.patch(
                        "core.auth_guide._list_ssh_public_keys", return_value=[]
                    ):
                        diag = diagnose_auth(
                            remote_url="https://github.com/a/b.git",
                            run_ssh_test=False,
                        )
        self.assertTrue(any(i.name == "Git 可执行" and i.ok for i in diag.items))
        self.assertEqual(diag.protocol, "https")


if __name__ == "__main__":
    unittest.main()
