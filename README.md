# Git Ship

![Python](https://img.shields.io/badge/python-3.11-blue.svg)
![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey.svg)
![Windows](https://img.shields.io/badge/Windows%20(v0.2.1)-0078D6?logo=windows&logoColor=white)
![macOS](https://img.shields.io/badge/macOS%20(v0.2.1)-000000?logo=apple&logoColor=white)
![Version](https://img.shields.io/badge/version-0.2.1-brightgreen.svg)
![License](https://img.shields.io/badge/license-MIT-green.svg)

简洁的 Git 代码提交小工具：CLI + GUI，核心逻辑共用。支持 Windows / macOS。

通过系统 `git` 命令完成 init / add / commit / push / pull / checkout，**不**直接操作 `.git` 对象库，**不**存储账号密码（复用系统
Git 凭据），默认 HTTPS。

## 功能

- 初始化仓库（默认分支 `main`）
- 设置远程 `origin`（GitHub / GitLab / Gitee 模板 + 自定义 URL）
- 查看状态与变更文件列表
- **Diff 预览**（统计 + patch 摘要，可按选中文件过滤）
- **Dry-run 试运行**（只展示计划与 diff，不写仓库）
- **分支切换 / 新建分支**
- **Pull / Pull --rebase**
- **敏感文件提醒**（`.env`、密钥等；`--force` 或 GUI 确认后可继续）
- **GUI 异步执行**耗时 Git 操作，避免界面卡死
- 提交（自由 message，仅校验非空）
- 提交并推送（无 upstream 时自动 `push -u`）
- Bootstrap：init → remote → add → commit → push -u

## 环境要求

- Python 3.10+
- 系统已安装 [Git](https://git-scm.com/)，终端可执行 `git --version`
- GUI：tkinter（官方 Python 安装包一般自带）

## 安装

无第三方依赖，克隆或拷贝本目录即可：

```bash
cd D:\moon\tools\git-ship
python -m unittest discover -s tests -v
```

## CLI 用法

在 `git-ship` 目录下：

```bash
# 查看状态
python git_ship_cli.py status --path .

# 查看变更摘要 / diff
python git_ship_cli.py diff --path .
python git_ship_cli.py diff --path . --stat-only
python git_ship_cli.py diff --path . src/app.py

# 初始化仓库
python git_ship_cli.py init --path . --branch main

# 设置远程
python git_ship_cli.py remote set --url https://github.com/owner/repo.git --path .

# 分支
python git_ship_cli.py branch list --path .
python git_ship_cli.py checkout feature/x --path .
python git_ship_cli.py checkout feature/y -b --path .

# 拉取
python git_ship_cli.py pull --path .
python git_ship_cli.py pull --path . --rebase
python git_ship_cli.py pull --path . --dry-run

# 敏感文件检查
python git_ship_cli.py check-sensitive --path .

# 一键初始化并推送
python git_ship_cli.py bootstrap --remote https://github.com/owner/repo.git -m "初始提交" --path .

# 仅预览 bootstrap（不执行）
python git_ship_cli.py bootstrap --remote https://github.com/owner/repo.git -m "初始提交" --path . --dry-run

# 日常提交并推送
python git_ship_cli.py ship -m "修复登录问题" --path .

# 忽略敏感提醒强制提交推送
python git_ship_cli.py ship -m "fix" --path . --force

# 仅预览 ship（不执行）
python git_ship_cli.py ship -m "修复登录问题" --path . --dry-run
```

失败时进程退出码非 0。

## GUI 用法

```bash
python git_ship.py
```

窗口标题 **Git Ship**，左右分栏：

| 左侧                      | 右侧                      |
|-------------------------|-------------------------|
| 仓库路径、远程 URL、平台下拉        | **Diff 预览**（彩色 patch）   |
| Owner/Repo 生成 HTTPS URL | 提交说明                    |
| **分支切换 / 新建 / Pull**    | 提交 / 提交并推送 / 初始化 / 设置远程 |
| 变更文件列表（敏感文件标 ⚠）         | Bootstrap / 试运行 / 清空日志  |
| 敏感检查                    | 操作日志（异步执行进度）            |

选中左侧文件后，Diff 面板会按选中文件过滤；未选中则显示全部变更。  
提交/推送前若命中敏感文件，会弹窗确认，确认后以 force 继续。

## 目录结构

```
git-ship/
├── git_ship.py          # GUI 入口
├── git_ship_cli.py      # CLI 入口
├── requirements.txt
├── README.md
├── core/                # 纯逻辑，无 UI
│   ├── git_ops.py
│   ├── remote.py
│   ├── workflow.py
│   ├── sensitive.py
│   └── config.py
├── ui/
│   ├── main_window.py
│   └── widgets.py
├── cli/
│   └── app.py
└── tests/
```

## 配置

用户配置目录：`~/.git-ship/config.json`（可用环境变量 `GIT_SHIP_HOME` 覆盖）。

默认项：`default_branch=main`，`default_protocol=https`。

## 注意事项

1. **凭据**：不保存账号密码；HTTPS 推送依赖系统 Git Credential Manager / 凭据助手。
2. **协议**：默认与模板均为 HTTPS；SSH URL 可识别与校验，但模板生成只出 HTTPS。
3. **不支持 force push**：无强制推送能力，避免误覆盖远程历史。`--force` 仅用于忽略敏感文件提醒。
4. **提交规范**：不强制 Conventional Commits，message 仅需非空。
5. **远程平台**：GitHub / GitLab / Gitee 为常用模板；其他主机选「自定义」并填写完整 URL。
6. **Dry-run**：不执行 `init/add/commit/push/pull/checkout` 写操作，仅输出计划步骤与当前 diff 摘要。
7. **敏感文件**：默认拦截疑似密钥/环境变量文件；CLI 用 `--force`，GUI 弹窗确认后继续。
8. **GUI 异步**：耗时 Git 操作在后台线程执行，期间按钮禁用；请勿强制关闭窗口中途杀进程。

## 变更记录

见 [CHANGELOG.md](./CHANGELOG.md)。

## 许可证

[MIT License](./LICENSE) — Copyright (c) 2026 Moon / Git Ship contributors
