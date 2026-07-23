# -*- coding: utf-8 -*-
"""git_ops 本地仓库测试（tempfile，不 push 远程）。"""

from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from core import git_ops
from core.workflow import bootstrap, commit_only, ship


def _git_available() -> bool:
    return git_ops.ensure_git_available().ok


@unittest.skipUnless(_git_available(), "系统未安装 git")
class TestGitOpsLocal(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        # 隔离全局 git 配置，保证 commit 可用
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

    def test_init_and_is_repo(self):
        self.assertFalse(git_ops.is_repo(self.root))
        result = git_ops.init_repo(self.root, initial_branch="main")
        self.assertTrue(result.ok, result.message)
        self.assertTrue(git_ops.is_repo(self.root))
        branch = git_ops.current_branch(self.root)
        self.assertTrue(branch.ok)
        self.assertEqual(branch.stdout, "main")

    def test_add_commit(self):
        git_ops.init_repo(self.root)
        (self.root / "README.md").write_text("hello\n", encoding="utf-8")
        add_result = git_ops.add(self.root, ["."])
        self.assertTrue(add_result.ok, add_result.message)
        commit_result = git_ops.commit(self.root, "init")
        self.assertTrue(commit_result.ok, commit_result.message)
        self.assertTrue(git_ops.has_head(self.root))
        status = git_ops.status_porcelain(self.root)
        self.assertTrue(status.ok)
        self.assertEqual(status.stdout.strip(), "")

    def test_commit_empty_message(self):
        git_ops.init_repo(self.root)
        result = git_ops.commit(self.root, "   ")
        self.assertFalse(result.ok)
        self.assertIn("不能为空", result.stderr)

    def test_remote_set_url_add(self):
        git_ops.init_repo(self.root)
        url = "https://github.com/acme/demo.git"
        result = git_ops.remote_set_url(self.root, url)
        self.assertTrue(result.ok, result.message)
        got = git_ops.remote_get(self.root)
        self.assertTrue(got.ok)
        self.assertEqual(got.stdout, url)
        # 更新
        url2 = "https://gitee.com/acme/demo.git"
        result2 = git_ops.remote_set_url(self.root, url2)
        self.assertTrue(result2.ok, result2.message)
        self.assertEqual(git_ops.remote_get(self.root).stdout, url2)

    def test_list_changed_files(self):
        git_ops.init_repo(self.root)
        (self.root / "a.txt").write_text("a\n", encoding="utf-8")
        files = git_ops.list_changed_files(self.root)
        self.assertIn("a.txt", files)

    def test_commit_only_workflow(self):
        git_ops.init_repo(self.root)
        (self.root / "f.txt").write_text("x\n", encoding="utf-8")
        result = commit_only(self.root, "feat: add f")
        self.assertTrue(result.ok, result.message)

    def test_ship_without_remote_skips_push_after_commit(self):
        git_ops.init_repo(self.root)
        (self.root / "f.txt").write_text("x\n", encoding="utf-8")
        result = ship(self.root, "ship msg")
        # 无 origin：提交成功但跳过推送，仍 ok
        self.assertTrue(result.ok, result.message)
        self.assertIn("跳过推送", result.message)

    def test_bootstrap_without_remote_files(self):
        # bootstrap 要求 remote；用空目录 + 文件测本地部分
        (self.root / "f.txt").write_text("x\n", encoding="utf-8")
        # 直接测 init+add+commit 路径：remote 为空字符串时 bootstrap 跳过 push
        # 规格要求 bootstrap 带 remote；此处用 workflow 内部逻辑：
        from core.workflow import bootstrap as boot

        # remote 无效应失败
        bad = boot(self.root, remote_url="bad", message="m")
        self.assertFalse(bad.ok)

        # 有效 remote 但 push 会失败（假远程）——至少 init/commit 步骤应执行
        # 为不依赖网络，mock push
        with mock.patch.object(git_ops, "push") as push_mock:
            push_mock.return_value = git_ops.GitResult(
                ok=True, code=0, stdout="pushed", stderr="", command=["git", "push"]
            )
            result = boot(
                self.root,
                remote_url="https://github.com/acme/demo.git",
                message="bootstrap",
                branch="main",
            )
            self.assertTrue(result.ok, result.message)
            push_mock.assert_called()

    def test_diff_summary_and_stat(self):
        git_ops.init_repo(self.root)
        (self.root / "a.txt").write_text("one\n", encoding="utf-8")
        git_ops.add(self.root, ["a.txt"])
        git_ops.commit(self.root, "init")
        (self.root / "a.txt").write_text("two\n", encoding="utf-8")
        (self.root / "b.txt").write_text("new\n", encoding="utf-8")

        stat = git_ops.diff_stat(self.root, staged=False)
        self.assertTrue(stat.ok, stat.message)

        summary = git_ops.diff_summary(self.root)
        self.assertIn("变更文件", summary)
        self.assertIn("a.txt", summary)

        limited = git_ops.diff_summary(self.root, paths=["a.txt"])
        self.assertIn("a.txt", limited)

    def test_ship_dry_run_does_not_commit(self):
        git_ops.init_repo(self.root)
        (self.root / "c.txt").write_text("c\n", encoding="utf-8")
        before = git_ops.has_head(self.root)
        self.assertFalse(before)

        result = ship(self.root, "dry msg", dry_run=True)
        self.assertTrue(result.ok, result.message)
        self.assertIn("dry-run", result.message.lower())
        self.assertFalse(git_ops.has_head(self.root))
        # 文件仍未暂存为提交
        files = git_ops.list_changed_files(self.root)
        self.assertIn("c.txt", files)

    def test_bootstrap_dry_run_no_side_effect(self):
        (self.root / "d.txt").write_text("d\n", encoding="utf-8")
        result = bootstrap(
            self.root,
            remote_url="https://github.com/acme/demo.git",
            message="boot dry",
            dry_run=True,
        )
        self.assertTrue(result.ok, result.message)
        self.assertFalse(git_ops.is_repo(self.root))


class TestGitOpsMock(unittest.TestCase):
    def test_add_command_args(self):
        with mock.patch("core.git_ops.subprocess.run") as run_mock:
            run_mock.return_value = mock.Mock(
                returncode=0, stdout="", stderr=""
            )
            result = git_ops.add("/tmp/repo", ["a.py", "b.py"])
            self.assertTrue(result.ok)
            args = run_mock.call_args[0][0]
            self.assertEqual(args[:2], ["git", "add"])
            self.assertIn("a.py", args)
            self.assertIn("b.py", args)

    def test_commit_command_args(self):
        with mock.patch("core.git_ops.subprocess.run") as run_mock:
            run_mock.return_value = mock.Mock(
                returncode=0, stdout="", stderr=""
            )
            result = git_ops.commit("/tmp/repo", "hello world")
            self.assertTrue(result.ok)
            args = run_mock.call_args[0][0]
            self.assertEqual(args, ["git", "commit", "-m", "hello world"])

    def test_push_set_upstream_args(self):
        with mock.patch("core.git_ops.subprocess.run") as run_mock:
            run_mock.return_value = mock.Mock(
                returncode=0, stdout="", stderr=""
            )
            result = git_ops.push("/tmp/repo", set_upstream=True, branch="main")
            self.assertTrue(result.ok)
            args = run_mock.call_args[0][0]
            self.assertEqual(args, ["git", "push", "-u", "origin", "main"])

    def test_diff_patch_command_args(self):
        with mock.patch("core.git_ops.subprocess.run") as run_mock:
            run_mock.return_value = mock.Mock(returncode=0, stdout="diff", stderr="")
            result = git_ops.diff_patch("/tmp/repo", paths=["a.py"], staged=True)
            self.assertTrue(result.ok)
            args = run_mock.call_args[0][0]
            self.assertEqual(args[:3], ["git", "diff", "--cached"])
            self.assertIn("a.py", args)

    def test_run_timeout_returns_124(self):
        with mock.patch("core.git_ops.subprocess.run") as run_mock:
            run_mock.side_effect = subprocess.TimeoutExpired(
                cmd=["git", "status"], timeout=1.0
            )
            result = git_ops._run(["status"], cwd="/tmp/repo", timeout=1.0)
            self.assertFalse(result.ok)
            self.assertEqual(result.code, 124)
            self.assertIn("超时", result.stderr)
            self.assertEqual(result.command, ["git", "status"])

    def test_push_default_network_timeout(self):
        with mock.patch("core.git_ops.subprocess.run") as run_mock:
            run_mock.return_value = mock.Mock(returncode=0, stdout="", stderr="")
            result = git_ops.push("/tmp/repo")
            self.assertTrue(result.ok)
            self.assertEqual(
                run_mock.call_args.kwargs.get("timeout"),
                git_ops.NETWORK_TIMEOUT,
            )

    def test_pull_default_network_timeout(self):
        with mock.patch("core.git_ops.subprocess.run") as run_mock:
            run_mock.return_value = mock.Mock(returncode=0, stdout="", stderr="")
            result = git_ops.pull("/tmp/repo", remote="origin", branch="main")
            self.assertTrue(result.ok)
            self.assertEqual(
                run_mock.call_args.kwargs.get("timeout"),
                git_ops.NETWORK_TIMEOUT,
            )

    def test_local_command_default_timeout(self):
        with mock.patch("core.git_ops.subprocess.run") as run_mock:
            run_mock.return_value = mock.Mock(returncode=0, stdout="", stderr="")
            result = git_ops.status_porcelain("/tmp/repo")
            self.assertTrue(result.ok)
            self.assertEqual(
                run_mock.call_args.kwargs.get("timeout"),
                git_ops.DEFAULT_TIMEOUT,
            )

    def test_push_custom_timeout(self):
        with mock.patch("core.git_ops.subprocess.run") as run_mock:
            run_mock.return_value = mock.Mock(returncode=0, stdout="", stderr="")
            result = git_ops.push("/tmp/repo", timeout=42.0)
            self.assertTrue(result.ok)
            self.assertEqual(run_mock.call_args.kwargs.get("timeout"), 42.0)

    def test_list_branch_names_filters_remote_pseudo(self):
        stdout = "\n".join(
            [
                "origin",
                "origin/HEAD",
                "origin/main",
                "origin/feature/x",
                "upstream",
                "upstream/HEAD",
                "upstream/dev",
            ]
        )
        with mock.patch.object(
            git_ops,
            "list_branches",
            return_value=git_ops.GitResult(
                ok=True,
                code=0,
                stdout=stdout,
                stderr="",
                command=["git", "branch", "-r"],
            ),
        ):
            names = git_ops.list_branch_names("/tmp/repo", remote=True)
        self.assertEqual(
            names,
            ["origin/main", "origin/feature/x", "upstream/dev"],
        )
        self.assertNotIn("origin", names)
        self.assertNotIn("origin/HEAD", names)
        self.assertNotIn("upstream", names)

    def test_list_branch_names_local_unfiltered(self):
        stdout = "\n".join(["main", "HEAD", "feature/x", "origin"])
        with mock.patch.object(
            git_ops,
            "list_branches",
            return_value=git_ops.GitResult(
                ok=True,
                code=0,
                stdout=stdout,
                stderr="",
                command=["git", "branch"],
            ),
        ):
            names = git_ops.list_branch_names("/tmp/repo", remote=False)
        self.assertEqual(names, ["main", "HEAD", "feature/x", "origin"])


if __name__ == "__main__":
    unittest.main()
