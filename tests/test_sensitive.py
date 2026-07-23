# -*- coding: utf-8 -*-
"""敏感文件检测测试。"""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from core import git_ops
from core.sensitive import (
    find_sensitive_files,
    format_sensitive_warning,
    is_sensitive_path,
)
from core.workflow import commit_only, ship


class TestSensitiveDetect(unittest.TestCase):
    def test_basenames(self):
        self.assertTrue(is_sensitive_path(".env"))
        self.assertTrue(is_sensitive_path("config/.env.local"))
        self.assertTrue(is_sensitive_path("id_rsa"))
        self.assertTrue(is_sensitive_path("certs/private.pem"))
        self.assertTrue(is_sensitive_path("app/credentials.json"))
        self.assertTrue(is_sensitive_path("secrets.yaml"))
        self.assertTrue(is_sensitive_path("foo.pem"))

    def test_safe_files(self):
        self.assertFalse(is_sensitive_path("src/main.py"))
        self.assertFalse(is_sensitive_path("README.md"))
        self.assertFalse(is_sensitive_path("package.json"))

    def test_false_positives_avoided(self):
        """源码/文档中的 token/secret/password 等不应误报。"""
        self.assertFalse(is_sensitive_path("src/token_utils.py"))
        self.assertFalse(is_sensitive_path("auth/password_reset.py"))
        self.assertFalse(is_sensitive_path("get_token.go"))
        self.assertFalse(is_sensitive_path("MySecretService.java"))
        self.assertFalse(is_sensitive_path("docs/secrets.md"))
        self.assertFalse(is_sensitive_path("credentials/readme.txt"))
        self.assertFalse(is_sensitive_path("id_rsa.pub"))
        self.assertFalse(is_sensitive_path("config/env.example"))
        self.assertFalse(is_sensitive_path("foo.env.sample"))
        self.assertFalse(is_sensitive_path(".env.example"))
        self.assertFalse(is_sensitive_path("keys/id_ed25519.pub"))

    def test_true_positives_patterns(self):
        self.assertTrue(is_sensitive_path("app.secrets.json"))
        self.assertTrue(is_sensitive_path("token.json"))
        self.assertTrue(is_sensitive_path("passwords.yml"))
        self.assertTrue(is_sensitive_path("id_ed25519"))
        self.assertTrue(is_sensitive_path("private.pem.bak"))
        self.assertTrue(is_sensitive_path("secrets/app.json"))
        self.assertTrue(is_sensitive_path(".ssh/config.conf"))

    def test_find_and_format(self):
        files = ["src/a.py", ".env", "ok.txt", "secrets/key.pem"]
        hits = find_sensitive_files(files)
        self.assertEqual(hits, [".env", "secrets/key.pem"])
        text = format_sensitive_warning(hits)
        self.assertIn("2 个", text)
        self.assertIn(".env", text)


def _git_available() -> bool:
    return git_ops.ensure_git_available().ok


@unittest.skipUnless(_git_available(), "系统未安装 git")
class TestSensitiveWorkflow(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self._env_patch = mock.patch.dict(
            os.environ,
            {
                "GIT_AUTHOR_NAME": "git-ship-test",
                "GIT_AUTHOR_EMAIL": "git-ship-test@example.com",
                "GIT_COMMITTER_NAME": "git-ship-test",
                "GIT_COMMITTER_EMAIL": "git-ship-test@example.com",
                "GIT_CONFIG_COUNT": "2",
                "GIT_CONFIG_KEY_0": "user.name",
                "GIT_CONFIG_VALUE_0": "git-ship-test",
                "GIT_CONFIG_KEY_1": "user.email",
                "GIT_CONFIG_VALUE_1": "git-ship-test@example.com",
            },
            clear=False,
        )
        self._env_patch.start()

    def tearDown(self) -> None:
        self._env_patch.stop()
        self._tmp.cleanup()

    def test_ship_blocks_sensitive_without_force(self):
        git_ops.init_repo(self.root)
        (self.root / "ok.txt").write_text("ok\n", encoding="utf-8")
        git_ops.add(self.root, ["ok.txt"])
        git_ops.commit(self.root, "init")
        (self.root / ".env").write_text("SECRET=1\n", encoding="utf-8")

        blocked = ship(self.root, "add env", force=False)
        self.assertFalse(blocked.ok)
        self.assertTrue(blocked.sensitive_files)
        self.assertIn(".env", blocked.sensitive_files)
        # 确认未提交 .env
        status = git_ops.status_porcelain(self.root)
        self.assertIn(".env", status.stdout)

        forced = ship(self.root, "add env", force=True)
        # 无 origin 会跳过 push，但仍应提交成功
        self.assertTrue(forced.ok, forced.message)

    def test_commit_only_force(self):
        git_ops.init_repo(self.root)
        (self.root / "id_rsa").write_text("fake-key\n", encoding="utf-8")
        blocked = commit_only(self.root, "bad", force=False)
        self.assertFalse(blocked.ok)
        ok = commit_only(self.root, "bad", force=True)
        self.assertTrue(ok.ok, ok.message)


@unittest.skipUnless(_git_available(), "系统未安装 git")
class TestBranchPullOps(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self._env_patch = mock.patch.dict(
            os.environ,
            {
                "GIT_AUTHOR_NAME": "git-ship-test",
                "GIT_AUTHOR_EMAIL": "git-ship-test@example.com",
                "GIT_COMMITTER_NAME": "git-ship-test",
                "GIT_COMMITTER_EMAIL": "git-ship-test@example.com",
                "GIT_CONFIG_COUNT": "2",
                "GIT_CONFIG_KEY_0": "user.name",
                "GIT_CONFIG_VALUE_0": "git-ship-test",
                "GIT_CONFIG_KEY_1": "user.email",
                "GIT_CONFIG_VALUE_1": "git-ship-test@example.com",
            },
            clear=False,
        )
        self._env_patch.start()

    def tearDown(self) -> None:
        self._env_patch.stop()
        self._tmp.cleanup()

    def test_checkout_create_and_list(self):
        git_ops.init_repo(self.root, initial_branch="main")
        (self.root / "a.txt").write_text("a\n", encoding="utf-8")
        git_ops.add(self.root, ["."])
        git_ops.commit(self.root, "init")

        created = git_ops.checkout(self.root, "feature/x", create=True)
        self.assertTrue(created.ok, created.message)
        branch = git_ops.current_branch(self.root)
        self.assertEqual(branch.stdout, "feature/x")

        names = git_ops.list_branch_names(self.root)
        self.assertIn("main", names)
        self.assertIn("feature/x", names)

        switched = git_ops.checkout(self.root, "main", create=False)
        self.assertTrue(switched.ok, switched.message)
        self.assertEqual(git_ops.current_branch(self.root).stdout, "main")

    def test_pull_command_args(self):
        with mock.patch("core.git_ops.subprocess.run") as run_mock:
            run_mock.return_value = mock.Mock(returncode=0, stdout="", stderr="")
            result = git_ops.pull("/tmp/repo", remote="origin", branch="main", rebase=True)
            self.assertTrue(result.ok)
            args = run_mock.call_args[0][0]
            self.assertEqual(args, ["git", "pull", "--rebase", "origin", "main"])


if __name__ == "__main__":
    unittest.main()
