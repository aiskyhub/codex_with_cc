# AI 安装说明

本文件是 `codex_with_cc` 的 **marketplace-only 安装契约**。仓库不再支持脚本式安装，也不再复制任何本地 skill 目录；安装必须先检查 `aiskyhub/aiskyhub` marketplace，再从 marketplace 安装 `codex-with-cc@aiskyhub`。

## 默认交互策略

只要用户是在让你“安装 / 集成 / 更新这套工作流”，默认进入零打扰安装模式：

1. 直接执行，不要先把安装过程变成问答游戏。
2. 如果检测到旧版脚本安装残留，先清理项目下旧安装产物和用户级旧版 `codex-with-cc` skill，再继续 marketplace 安装。
3. 默认执行用户级安装，不要切成项目级，除非用户明确要求。
4. 如果宿主环境还没有安装 `codex` CLI，先自动安装官方 CLI，再继续后续步骤。
5. 默认先检查 `aiskyhub` marketplace 是否已存在，再检查 `codex-with-cc@aiskyhub` 是否已启用。
6. marketplace 添加或插件安装失败时直接停止并报告，不要回退到复制文件、写入旧目录或执行本地安装脚本。
7. 必要时提醒用户重载插件列表或重启宿主。
8. 只有 marketplace 仓库不可达、宿主没有可用插件命令、或读取配置失败时，才停下来询问用户。

## 目标

把本仓库的 `Codex -> Codex 子代理 -> Claude Code CLI` 委派工作流，安装成 `aiskyhub/aiskyhub` marketplace 下的用户级插件，使后续凡是涉及子代理、子线程、多代理、委派、派工或执行层的任务，都强制触发 `$codex-with-cc`。

## 内部协议

安装入口和 marketplace 插件名保持不变，插件内部直接使用 workflow/task/run 协议：

- 每次用户请求对应一个 `WorkflowId`。
- 每个被拆出的子任务对应一个 `TaskId`。
- 每次 Claude Code 执行对应一个 `RunId`。
- 每个 worker 必须声明 `Role`，取值为 `planner`、`implementer`、`researcher`、`reviewer` 或 `final-verifier`。
- 当前 artifact schema 会额外生成 `workflow_<WorkflowId>.json`，用于聚合 workflow 下的 task 和 run。
- 单次运行使用 `verify_delegate_run` 或 `verify_delegate_artifacts` 验证；整条工作流使用 `verify_delegate_workflow` 验证。

这属于内部协议替换，不改变 README 中原有的中文安装口令，也不改变 `codex-with-cc@aiskyhub` 用户级安装路径。

Any user mention of child-agent, subagent, sub-agent, child-thread, subthread, delegation, worker-execution, or Chinese equivalents such as 子代理、子线程、多代理、委派、派工、执行层 is a workflow trigger.

触发后必须走：

```text
Codex 主线程 -> Codex spawn_agent 子线程 -> 已安装插件中的 delegate_to_claude.* -> scripts/*.py -> Claude Code CLI
```

不要把 Codex 默认子代理工作流、宿主环境内置代理流程、直接运行 `claude`、或主线程直接执行 `delegate_to_claude.*` 当作等价替代。

安装后的插件会声明 `./hooks/hooks.json` 平台 hook。宿主启用 Codex hooks 时，插件会在 `SessionStart` 以 `<EXTREMELY_IMPORTANT>` bootstrap 形式注入完整 `SKILL.md` 和 `CODEX_WITH_CC.md` 契约，在 `UserPromptSubmit` 遇到子代理/委派触发词时再次注入完整契约，并在 `PreToolUse` 可见的工具面上拦截直接 `claude`、直接主线程 `delegate_to_claude.*`、以及不合规的 `spawn_agent` 风格 payload。

## 分发源

唯一分发入口：

```text
Marketplace repo: https://github.com/aiskyhub/aiskyhub
Codex marketplace source: .agents/plugins/marketplace.json
Plugin name: codex-with-cc@aiskyhub
```

## 旧版安装残留清理

如果用户之前通过脚本安装过旧版 workflow，安装前先检查并删除这些旧入口，避免 marketplace 插件和旧 skill 同时存在。

### 1. 清理项目下旧安装产物

先清理目标项目根目录下这些旧产物：

- `docs/codex_with_cc`
- `doc/codex_with_cc`
- `.codex/skills/codex-with-cc`
- `AGENTS.md` 里的 `<!-- BEGIN CODEX_WITH_CC --> ... <!-- END CODEX_WITH_CC -->` 托管块

如果 `AGENTS.md` 删除托管块后变空，可以直接删除整个文件。

### 2. 清理用户级旧 skill

- 用户级旧 skill：`$HOME/.codex/skills/codex-with-cc`
- Windows 等价路径：`$env:USERPROFILE\.codex\skills\codex-with-cc`

如果这些路径存在，先删除，再继续 marketplace 安装。不要保留旧 skill 作为回退。

## Codex 安装协议

当前仓库只提供 Codex 插件入口，不提供 Claude 宿主插件配置。

Codex 当前 CLI 没有 `marketplace list` 子命令，因此“是否已添加 marketplace”必须通过读取 `~/.codex/config.toml` 判定。

### 1. 检查并安装 Codex CLI

先检查 `codex` 命令是否可用。

PowerShell：

```powershell
Get-Command codex -ErrorAction SilentlyContinue
```

macOS / Linux：

```bash
command -v codex
```

如果不存在，直接按 OpenAI 官方方式安装：

```bash
npm i -g @openai/codex
```

安装完成后再次确认 `codex` 命令可用，再继续 marketplace 安装流程。

如果 `npm` 不存在、CLI 安装失败、或安装后仍然无法调用 `codex`，直接报告失败并停止，不要跳过这一步继续执行。

### 2. 检查 marketplace

检查：

```toml
[marketplaces.aiskyhub]
```

如果不存在，执行：

```bash
codex plugin marketplace add aiskyhub/aiskyhub
```

### 3. 检查插件

检查：

```toml
[plugins."codex-with-cc@aiskyhub"]
```

如果不存在或未启用，在 Codex 中执行：

```text
/plugin install codex-with-cc@aiskyhub --scope user
```

安装后如未即时生效，可提示用户重载插件或重启 Codex。

### 4. 启用 Codex hooks 半硬门

如果目标 Codex 宿主支持 hooks，需要确认用户配置启用了：

```toml
[features]
codex_hooks = true
```

没有启用 hooks 时，插件仍会通过 `$codex-with-cc` skill 做工作流约束；启用后会额外获得平台级 `SessionStart`、`UserPromptSubmit` 和 `PreToolUse` 拦截层。

### 5. 定位已安装 workflow 根目录

后续委派命令里的 `<installed-workflow-root>` 指已安装插件包内部的 `skills/codex-with-cc` 目录，例如：

```text
<codex-home>/plugins/cache/aiskyhub/codex-with-cc/<version-or-hash>/skills/codex-with-cc
```

不要把 `<version-or-hash>` 包根目录当成 workflow 根目录；`scripts`、`windows_scripts` 和 `macos_scripts` 都在 `skills/codex-with-cc` 下面。

## 失败处理

- marketplace 添加失败：直接报告失败并停止
- 插件安装失败：直接报告失败并停止
- 不要复制仓库文件到任何本地 skill 目录
- 不要创建或恢复旧的安装脚本路径
- 不要把失败处理成“先手动复制再说”

## 安装或更新完成后告知用户

最终回复至少要明确这些信息：

- 这次是安装成功、更新成功，还是只完成了前置检查
- 是否新增了 `aiskyhub` marketplace
- 是否清理了项目下旧安装产物
- 是否清理了用户级旧版 `codex-with-cc` skill
- `codex-with-cc@aiskyhub` 是否已经安装或更新完成
- 是否需要用户执行 `/plugin install codex-with-cc@aiskyhub --scope user`
- 是否需要用户重载插件列表或重启 Codex
- 如果有步骤没执行，必须说明阻塞原因

不要只说“好了”或“已完成”，要把本次更新实际变更和剩余动作交代清楚。

## 委派规则

```powershell
$env:CODEX_CLAUDE_CHILD_THREAD = '1'
pwsh -NoProfile -File "<installed-workflow-root>\windows_scripts\delegate_to_claude.ps1" `
  -TaskFile .\.codex\codex_with_cc\tasks\<yyyyMMdd>\<HHmmssfff>-<short-id>-<task-file>.md `
  -WorkflowId <workflow-id> `
  -TaskId <task-id> `
  -Role implementer `
  -Scope <changed-or-inspected-path> `
  -SessionMode PrimaryReuse `
  -SessionKey <stable-session-key> `
  -BypassPermissions
```

macOS 子线程标准调用形态：

```bash
export CODEX_CLAUDE_CHILD_THREAD=1
"<installed-workflow-root>/macos_scripts/delegate_to_claude.sh" \
  -TaskFile ./.codex/codex_with_cc/tasks/<yyyyMMdd>/<HHmmssfff>-<short-id>-<task-file>.md \
  -WorkflowId <workflow-id> \
  -TaskId <task-id> \
  -Role implementer \
  -Scope <changed-or-inspected-path> \
  -SessionMode PrimaryReuse \
  -SessionKey <stable-session-key> \
  -BypassPermissions
```

并行任务按场景使用：

- `PrimaryAnchor -AllowParallel`：并行批次的主线锚点。
- `ParallelPool -AllowParallel`：独立支线任务池。

只有任务范围互不冲突时才允许并行。多个子代理同时修改同一批文件时，必须拆分写入边界或改为串行。

## 验证与产物

委派运行产物默认写在当前项目：

```text
.codex/codex_with_cc/claude-delegate
```

常见文件包括：

- `workflow_<WorkflowId>.json`
- `claude_<RunId>.md`
- `status_<RunId>.json`
- `config_<RunId>.json`
- `prompt_<RunId>.md`
- `stream_<RunId>.jsonl`
- `trace_<RunId>.log`
- `session-pools/<SessionKey>.json`

检查单次委派产物：

```powershell
pwsh -NoProfile -File "<installed-workflow-root>\windows_scripts\verify_delegate_artifacts.ps1"
pwsh -NoProfile -File "<installed-workflow-root>\windows_scripts\verify_delegate_run.ps1"
```

```bash
"<installed-workflow-root>/macos_scripts/verify_delegate_artifacts.sh"
"<installed-workflow-root>/macos_scripts/verify_delegate_run.sh"
```

检查整条 workflow：

```powershell
pwsh -NoProfile -File "<installed-workflow-root>\windows_scripts\verify_delegate_workflow.ps1" -WorkflowId <workflow-id>
```

```bash
"<installed-workflow-root>/macos_scripts/verify_delegate_workflow.sh" -WorkflowId <workflow-id>
```

检查多轮链路连续性：

```powershell
pwsh -NoProfile -File "<installed-workflow-root>\windows_scripts\verify_delegate_chain.ps1"
```

```bash
"<installed-workflow-root>/macos_scripts/verify_delegate_chain.sh"
```
