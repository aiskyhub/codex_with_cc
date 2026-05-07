# 项目结构与路径约定

这个文件专门解决一件事：区分“源仓库里的路径”和“安装到目标项目后的路径”。

## 先记这一条

- 当前仓库是**源仓库**，工作流文件放在 `codex_with_cc/...`
- 安装到别的项目后是**目标项目**，工作流文件放在 `docs/codex_with_cc/...`

不要把这两套路径混用。

## 源仓库结构

当前仓库根目录：

```text
AGENTS.md
AI_INSTALL.md
PROJECT_STRUCTURE.md
README.md
scripts/
  install_codex_with_cc.ps1
  install_codex_with_cc.sh
codex_with_cc/
  CODEX_WITH_CC.md
  windows_scripts/
  unix_scripts/
tests/
```

关键点：

- Windows 安装脚本在 `scripts/install_codex_with_cc.ps1`
- Linux/macOS 安装脚本在 `scripts/install_codex_with_cc.sh`
- 工作流契约文档在 `codex_with_cc/CODEX_WITH_CC.md`
- Windows 脚本在 `codex_with_cc/windows_scripts/`
- Linux/macOS 脚本在 `codex_with_cc/unix_scripts/`

## 安装后目标项目结构

安装到目标项目后，目标项目里应当出现：

```text
AGENTS.md
docs/
  codex_with_cc/
    CODEX_WITH_CC.md
    windows_scripts/
    unix_scripts/
.codex/
  codex_with_cc/
    tasks/
```

关键点：

- 安装后的工作流目录是 `docs/codex_with_cc/`
- 运行产物和任务文件在 `.codex/codex_with_cc/`
- 目标项目里**不会**有源仓库里的 `scripts/install_codex_with_cc.ps1` 这类安装器副本

## 路径映射表

| 源仓库路径 | 目标项目安装后路径 |
| --- | --- |
| `codex_with_cc/CODEX_WITH_CC.md` | `docs/codex_with_cc/CODEX_WITH_CC.md` |
| `codex_with_cc/windows_scripts/delegate_to_claude.ps1` | `docs/codex_with_cc/windows_scripts/delegate_to_claude.ps1` |
| `codex_with_cc/unix_scripts/delegate_to_claude.sh` | `docs/codex_with_cc/unix_scripts/delegate_to_claude.sh` |
| `codex_with_cc/windows_scripts/test_delegate_runtime.ps1` | `docs/codex_with_cc/windows_scripts/test_delegate_runtime.ps1` |
| `codex_with_cc/unix_scripts/test_delegate_runtime.sh` | `docs/codex_with_cc/unix_scripts/test_delegate_runtime.sh` |

## AI 阅读规则

如果你是 AI，在读这个仓库时按下面规则判断路径：

1. 你正在修改**源仓库本身**：
   使用 `codex_with_cc/...`
2. 你正在把这套工作流安装到**目标项目**：
   使用 `docs/codex_with_cc/...`
3. 你在写安装命令：
   Windows 用 `scripts/install_codex_with_cc.ps1`，Linux/macOS 用 `scripts/install_codex_with_cc.sh`
4. 你在写委派命令或验证命令：
   对目标项目一律引用 `docs/codex_with_cc/...`

## 平台区分

- Windows：使用 `windows_scripts/` 下的 `.ps1` 脚本
- Linux/macOS：使用 `unix_scripts/` 下的 `.sh` 脚本

不要再引入 `macos_scripts/` 这种第三套目录名，除非未来真的新增独立目录并同步修改安装器、测试和文档。
