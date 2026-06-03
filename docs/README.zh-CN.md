# codex-with-cc-anthropic 中文说明

## 这个仓库解决什么问题

Claude Code 接 DeepSeek Anthropic 兼容端点时，真实工具派工可能因为 thinking 续轮协议失败：

```text
content[].thinking in the thinking mode must be passed back
```

这个仓库提供一个本地轻量代理：

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

代理做两件事：

- 响应方向：把 DeepSeek 返回的 `thinking` / `redacted_thinking` block 从 Claude Code 可见内容里剥掉。
- 请求方向：清理 Claude Code history 里的 thinking，并在需要时把缓存的隐藏 thinking 按 `tool_use.id` 关系回注给上游。

结果：Claude Code 不直接看到 thinking block，DeepSeek 又能拿到必要续轮信息，从而绕过 400。

## 文件说明

- `scripts/thinking_strip_proxy.py`
  - 代理主体，纯 Python 标准库，无第三方依赖。
  - 监听默认地址：`127.0.0.1:9099`。
  - 默认上游：`https://api.deepseek.com/anthropic`。

- `scripts/start_thinking_strip_proxy.ps1`
  - Windows 启动/健康检查脚本。
  - 已改成 ASCII 注释，避免 Windows PowerShell 5.1 在无 BOM UTF-8 脚本中误读中文注释。
  - 中文说明集中写在本文件和 README 中。

- `examples/settings.example.json`
  - Claude settings 示例。
  - 不包含真实 token。

- `examples/delegate_command.windows.ps1`
  - codex-with-cc Windows 派工命令模板。
  - 使用 `powershell`，不假设本机安装 `pwsh`。

- `docs/BACKUP_AND_ROLLBACK.md`
  - 本机改动文件、备份文件、回滚方式说明。

- `docs/VERIFICATION.md`
  - 本次修复后的验证记录。

## 使用步骤

1. 备份 Claude 配置：

```powershell
Copy-Item "$env:USERPROFILE\.claude\settings.json" "$env:USERPROFILE\.claude\settings.json.bak_$(Get-Date -Format yyyyMMdd_HHmmss)"
```

2. 修改 Claude 配置：

```json
{
  "env": {
    "ANTHROPIC_BASE_URL": "http://127.0.0.1:9099",
    "ANTHROPIC_AUTH_TOKEN": "sk-REPLACE_WITH_YOUR_TOKEN"
  }
}
```

注意：真实 `ANTHROPIC_AUTH_TOKEN` 不要提交到 GitHub。

3. 启动或检查代理：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\start_thinking_strip_proxy.ps1
```

4. 健康检查：

```powershell
Invoke-RestMethod -Uri http://127.0.0.1:9099/health
```

期望返回：

```json
{"ok":true,"upstream":"https://api.deepseek.com/anthropic"}
```

## 后续 Codex 派工规则

在本机后续使用 codex-with-cc 派工前：

- 先启动或确认 `thinking-strip proxy` 健康。
- Windows 使用 `powershell -NoProfile -ExecutionPolicy Bypass -File ...`。
- 子线程必须设置 `CODEX_CLAUDE_CHILD_THREAD=1`。
- 真实派工建议加 `-BypassPermissions`。
- `-MaxRetryCount` 至少设为 `1`，让 wrapper 可以修复 Claude Code 偶发的结构化报告格式问题。
- `-Tests` 传入的文本必须逐字出现在 worker 最终 `Verification` 中。
- worker 禁止打印完整环境变量，尤其是 `ANTHROPIC_AUTH_TOKEN`。
- worker 禁止递归运行 `claude` 或 `delegate_to_claude.*`。

## 已验证结论

最终真实派工链路已经通过：

- RunId: `20260529_142857_085_6c7ae93c`
- WorkflowId: `plus-c-proxy-smoke-final`
- `verify_delegate_run.ps1`: passed
- `verify_delegate_workflow.ps1`: passed
- plus_C 本地测试：`64 passed`

结论：`codex_with_cc_plus_C` 可以作为派工工具使用，前提是本地代理保持运行。
