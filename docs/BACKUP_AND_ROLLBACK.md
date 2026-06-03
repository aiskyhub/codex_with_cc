# Backup And Rollback

中文说明：本文件记录本次本机修复涉及的文件、备份位置和回滚方法。真实 token 不记录、不提交。

## Files Changed In The Local Setup

Project files added:

- `C:\Users\user\Documents\jhr_platform\scripts\thinking_strip_proxy.py`
- `C:\Users\user\Documents\jhr_platform\scripts\start_thinking_strip_proxy.ps1`
- `C:\Users\user\Documents\jhr_platform\codex_with_cc_artifacts\codex_with_cc_plus_C_issue_summary_20260529.md`

Claude settings changed:

- `C:\Users\user\.claude\settings.json`
- `ANTHROPIC_BASE_URL` now points to `http://127.0.0.1:9099`.
- The real auth token is intentionally not recorded in this repository.

Task file added for smoke testing:

- `C:\Users\user\Downloads\codex_with_cc-master_extracted\codex_with_cc_plus_C\.codex\codex_with_cc\tasks\20260529\proxy_smoke_minimal.md`

codex-with-cc dispatch documentation updated:

- `C:\Users\user\Downloads\codex_with_cc-master_extracted\codex_with_cc_plus_C\skills\codex-with-cc-dispatching\SKILL.md`
- `C:\Users\user\Downloads\codex_with_cc-master_extracted\codex_with_cc_plus_C\skills\codex-with-cc\CODEX_WITH_CC.md`
- `C:\Users\user\Documents\jhr_platform\.codex\codex_with_cc\ANTHROPIC_DISPATCH.md`

## Existing Local Backups

Before changing Claude settings, these backup files existed or were created:

- `C:\Users\user\.claude\settings.json.bak_20260529`
- `C:\Users\user\.claude\settings.json.bak_20260529_135859`

Check backups:

```powershell
Get-ChildItem "$env:USERPROFILE\.claude" -Filter 'settings.json*'
```

## Roll Back Claude Settings

To restore a backup:

中文注释：如果本地代理不可用，或者想恢复直连配置，用下面命令把备份覆盖回当前 settings。

```powershell
Copy-Item "$env:USERPROFILE\.claude\settings.json.bak_20260529" "$env:USERPROFILE\.claude\settings.json" -Force
```

Stop the proxy process if needed:

```powershell
$conn = Get-NetTCPConnection -LocalAddress 127.0.0.1 -LocalPort 9099 -ErrorAction SilentlyContinue
if ($conn) {
  Stop-Process -Id $conn.OwningProcess -Force
}
```

## Token Safety

Do not commit real `ANTHROPIC_AUTH_TOKEN` values.

中文注释：上传 GitHub 前只保留 `examples/settings.example.json`，不要上传真实 `settings.json`。

The local smoke-test artifacts were scanned and token-like `sk-...` strings were redacted from logs.
