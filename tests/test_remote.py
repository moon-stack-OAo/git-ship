# -*- coding: utf-8 -*-
"""remote 模块单元测试。"""

from __future__ import annotations

import unittest

from core.remote import (
    build_https_url,
    detect_provider,
    parse_owner_repo,
    validate_remote_url,
)


class TestBuildHttpsUrl(unittest.TestCase):
    def test_github(self):
        self.assertEqual(
            build_https_url("github", "acme", "demo"),
            "https://github.com/acme/demo.git",
        )

    def test_gitlab(self):
        self.assertEqual(
            build_https_url("gitlab", "acme", "demo"),
            "https://gitlab.com/acme/demo.git",
        )

    def test_gitee(self):
        self.assertEqual(
            build_https_url("gitee", "acme", "demo"),
            "https://gitee.com/acme/demo.git",
        )

    def test_strip_git_suffix(self):
        url = build_https_url("github", "acme", "demo.git")
        self.assertEqual(url, "https://github.com/acme/demo.git")

    def test_invalid_provider(self):
        with self.assertRaises(ValueError):
            build_https_url("bitbucket", "a", "b")

    def test_empty_owner(self):
        with self.assertRaises(ValueError):
            build_https_url("github", "", "repo")


class TestValidateRemoteUrl(unittest.TestCase):
    def test_valid_https(self):
        self.assertTrue(validate_remote_url("https://github.com/acme/demo.git"))
        self.assertTrue(validate_remote_url("https://gitlab.com/group/proj.git"))
        self.assertTrue(validate_remote_url("https://gitee.com/u/r.git"))

    def test_valid_ssh(self):
        self.assertTrue(validate_remote_url("git@github.com:acme/demo.git"))

    def test_invalid(self):
        self.assertFalse(validate_remote_url(""))
        self.assertFalse(validate_remote_url("not-a-url"))
        self.assertFalse(validate_remote_url("http://github.com/a/b.git"))  # 非 https
        self.assertFalse(validate_remote_url("https://"))
        self.assertFalse(validate_remote_url("https://github.com"))
        self.assertFalse(validate_remote_url("https://github.com/a b/c.git"))


class TestDetectProvider(unittest.TestCase):
    def test_github(self):
        self.assertEqual(detect_provider("https://github.com/a/b.git"), "github")
        self.assertEqual(detect_provider("git@github.com:a/b.git"), "github")

    def test_gitlab(self):
        self.assertEqual(detect_provider("https://gitlab.com/a/b.git"), "gitlab")

    def test_gitee(self):
        self.assertEqual(detect_provider("https://gitee.com/a/b.git"), "gitee")

    def test_custom(self):
        self.assertEqual(detect_provider("https://git.example.com/a/b.git"), "custom")
        self.assertEqual(detect_provider(""), "custom")


class TestParseOwnerRepo(unittest.TestCase):
    def test_https(self):
        self.assertEqual(
            parse_owner_repo("https://github.com/acme/demo.git"),
            ("acme", "demo"),
        )

    def test_ssh(self):
        self.assertEqual(
            parse_owner_repo("git@github.com:acme/demo.git"),
            ("acme", "demo"),
        )


if __name__ == "__main__":
    unittest.main()
