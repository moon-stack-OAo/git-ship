# Changelog

本项目所有重要变更均记录于此。

格式基于 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，
版本号遵循 [Semantic Versioning](https://semver.org/lang/zh-CN/)。

## [Unreleased]

## [0.2.1] - 2026-07-23

### 新增

- GUI「使用说明」弹窗：首次启动自动显示，可勾选「不再自动弹出」；操作区随时可打开
- Git 命令超时：本地默认 120s，push/pull 等网络命令默认 300s；超时返回 code 124

### 变更

- **敏感文件检测**收紧规则，减少 `token_utils.py`、`password_reset.py`、文档类路径等误报；`*.pub` / `*.example` 等视为可提交
- GUI 状态/文件/分支/Diff 刷新改为异步，文件选择 Diff 防抖 250ms
- GUI 敏感确认与 workflow 共用 `collect_sensitive_files`（含 staged）
- 远程分支列表过滤 `origin` / `*/HEAD` 伪分支名

## [0.2.0] - 2026-07-22

### 新增

- **分支管理**：`checkout` / `checkout -b`，CLI `branch list`、`checkout`
- **拉取**：`pull` / `pull --rebase`，CLI 与 GUI 均支持
- **敏感文件提醒**：检测 `.env`、密钥、凭据等；CLI `--force` / GUI 确认后可继续
- **GUI 异步**：耗时 Git 操作后台线程执行，避免界面卡死
- **GitHub Actions**：`.github/workflows/build.yml`（测试 + PyInstaller 多平台打包 + tag Release）
- CLI 命令：`check-sensitive`

### 变更

- `ship` / `bootstrap` / `commit_only` 增加 `force` 参数
- `WorkflowResult` 增加 `sensitive_files` 字段
- README 补充分支 / pull / 敏感文件 / 异步说明

## [0.1.0] - 2026-07-22

### 新增

- **P0 核心能力**
    - 初始化仓库（默认分支 `main`）
    - 设置远程 `origin`（GitHub / GitLab / Gitee HTTPS 模板）
    - 日常提交并推送：`ship`（add → commit → push，无 upstream 时 `-u`）
    - Bootstrap：init → remote → add → commit → push
    - CLI（argparse）与 GUI（tkinter 左右分栏）
    - 不存储凭据；不支持 force push
- **P1 增强**
    - Diff 预览（`--stat` + patch 摘要，可按文件过滤）
    - Dry-run：`ship` / `bootstrap` 的 `--dry-run` 与 GUI 试运行
    - CLI `diff` 命令
- 单元测试（`unittest`）与 README

### 说明

- 运行依赖：Python 3.10+、系统 Git、tkinter（GUI）
- 无第三方 Python 运行时依赖；打包使用 PyInstaller（CI）

---

[Unreleased]: https://github.com/moon-stack-OAo/git-ship/compare/v0.2.1...HEAD

[0.2.1]: https://github.com/moon-stack-OAo/git-ship/compare/v0.2.0...v0.2.1

[0.2.0]: https://github.com/moon-stack-OAo/git-ship/compare/v0.1.0...v0.2.0

[0.1.0]: https://github.com/moon-stack-OAo/git-ship/releases/tag/v0.1.0
