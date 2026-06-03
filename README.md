# codex-with-cc-anthropic

Local compatibility layer for running Claude Code through an Anthropic-compatible DeepSeek endpoint when the backend emits `thinking` content blocks.

中文说明：这是一个给 `codex-with-cc` / Claude Code 使用的本地 Anthropic 兼容代理。它用于绕过 DeepSeek Anthropic 兼容端点在 `thinking` 续轮协议上的 400 错误，让 Claude Code 看不到 thinking block，同时仍能把必要上下文传给上游。

The proxy sits between Claude Code and the upstream Anthropic-compatible API:

```text
Claude Code
  ANTHROPIC_BASE_URL=http://127.0.0.1:9099
      |
      v
thinking-strip proxy
      |
      v
https://api.deepseek.com/anthropic
```

It strips `thinking` / `redacted_thinking` blocks before Claude Code sees them, and keeps enough hidden state to reinject thinking blocks into upstream tool-result turns when the backend requires the continuation protocol.

中文注释：Claude Code 侧只看到普通 text/tool_use/tool_result；DeepSeek 侧如果要求上一轮 thinking，本代理会按 tool_use 关系处理，避免 `content[].thinking in the thinking mode must be passed back`。

## Contents

- `scripts/thinking_strip_proxy.py` - standard-library Python proxy.
- `scripts/start_thinking_strip_proxy.ps1` - Windows helper that starts the proxy if it is not already healthy.
- `examples/settings.example.json` - safe Claude settings example with no real token.
- `examples/delegate_command.windows.ps1` - codex-with-cc dispatch command template.
- `docs/README.zh-CN.md` - full Chinese usage notes and comments.
- `docs/BACKUP_AND_ROLLBACK.md` - backup and rollback notes.
- `docs/VERIFICATION.md` - local verification evidence from the repaired setup.

中文目录说明：

- `scripts/`：可运行脚本，不含真实密钥。
- `examples/`：示例配置和派工命令模板，上传 GitHub 前无需替换真实 token。
- `docs/`：备份、回滚、验证证据，方便迁移到其他机器。

## Quick Start

1. Back up Claude settings.

中文注释：先备份，避免误改 `~/.claude/settings.json` 后无法恢复。

```powershell
Copy-Item "$env:USERPROFILE\.claude\settings.json" "$env:USERPROFILE\.claude\settings.json.bak_$(Get-Date -Format yyyyMMdd_HHmmss)"
```

2. Point Claude Code at the local proxy.

中文注释：真实 token 不要提交到 GitHub；示例里的 `sk-REPLACE_WITH_YOUR_TOKEN` 必须本机替换。

```json
{
  "env": {
    "ANTHROPIC_BASE_URL": "http://127.0.0.1:9099",
    "ANTHROPIC_AUTH_TOKEN": "sk-REPLACE_WITH_YOUR_TOKEN"
  }
}
```

3. Start or verify the proxy.

中文注释：这个脚本会先检查健康状态；如果 9099 已经可用，就不会重复启动。

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\start_thinking_strip_proxy.ps1
```

4. Health check.

```powershell
Invoke-RestMethod -Uri http://127.0.0.1:9099/health
```

Expected:

```json
{"ok":true,"upstream":"https://api.deepseek.com/anthropic"}
```

## Codex Dispatch Defaults

For codex-with-cc delegation on Windows:

- Keep the proxy running on `127.0.0.1:9099`.
- Use `powershell -NoProfile -ExecutionPolicy Bypass -File`, because `pwsh` may not be installed.
- Set `CODEX_CLAUDE_CHILD_THREAD=1` in the child thread before invoking `delegate_to_claude.ps1`.
- Use `-BypassPermissions`.
- Keep `-MaxRetryCount` at `1` or higher so the wrapper can repair occasional structured-report formatting failures.
- Ensure each `-Tests` value appears verbatim in the worker `Verification` section.
- Do not let workers print full environment variables or recurse into `claude`.

中文派工规则：

- 后续 Codex 派工前先确认代理健康：`Invoke-RestMethod http://127.0.0.1:9099/health`。
- Windows 本机优先使用 `powershell`，不要假设安装了 `pwsh`。
- 常规派工必须保留 `-MaxRetryCount 1` 或更高，方便 wrapper 自动修复 Claude Code 偶发的报告格式前缀。
- `-Tests` 传入的验证文本必须逐字出现在 worker 最终 `Verification` 中，否则 workflow verifier 会失败。
- worker 禁止打印完整环境变量，尤其是 `ANTHROPIC_AUTH_TOKEN`。

See `examples/delegate_command.windows.ps1`.
