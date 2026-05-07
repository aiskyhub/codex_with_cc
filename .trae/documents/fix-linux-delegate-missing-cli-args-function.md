# 修复计划：Linux 委派脚本缺失 `new_claude_delegate_cli_args` 函数

## 问题描述

在 Linux 系统上，使用 `scripts/install_codex_with_cc.sh` 安装到目标项目后，Codex 开启子代理时**未正确使用 Claude Code**，而是使用了 Codex 自己的默认子代理。

## 根因分析

通过逐文件逐函数对比 Linux (`unix_scripts/`) 和 Windows (`windows_scripts/`) 的实现，定位到以下关键差异：

### 缺失函数

| 平台        | 文件                                                                                                                                                                     | 函数                             | 状态        |
| --------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------ | --------- |
| Windows   | [claude\_delegate\_backend\_helpers.ps1:L304-L340](file:///home/ken/project/codex_with_cc/codex_with_cc/windows_scripts/claude_delegate_backend_helpers.ps1#L304-L340) | `New-ClaudeDelegateCliArgs`    | ✅ 已定义     |
| **Linux** | [claude\_delegate\_backend\_helpers.sh](file:///home/ken/project/codex_with_cc/codex_with_cc/unix_scripts/claude_delegate_backend_helpers.sh)                          | `new_claude_delegate_cli_args` | ❌ **缺失！** |

### 调用链分析

`delegate_to_claude.sh` 中：

**L782-L790** — 调用此函数构建 CLAUDE\_ARGS 数组：

```bash
mapfile -t CLAUDE_ARGS < <(new_claude_delegate_cli_args \
    "$MODEL" "$EFFECTIVE_NAME" "$SESSION_ID" \
    "$attempt_resume" "${MAX_BUDGET_USD:-}" \
    "$BYPASS_PERMISSIONS" "$PROMPT_TEXT")
```

**L836** — 使用数组调用 claude：

```bash
done < <(claude "${CLAUDE_ARGS[@]}" 2>&1)
```

### 故障链路

1. Codex 主线程读取 `AGENTS.md` → `CODEX_WITH_CC.md`，创建 spawn\_agent 子代理
2. 子代理尝试运行 `delegate_to_claude.sh`
3. `delegate_to_claude.sh` 调用 `new_claude_delegate_cli_args` 构建 Claude Code CLI 参数
4. **函数未定义**，bash 报错 `command not found`，`mapfile` 得到空输入 → `CLAUDE_ARGS` 数组为空
5. `claude` 命令因缺少参数而失败
6. Codex 感知到子代理失败，**回退到 Codex 默认子代理机制**

## 修复方案

### 文件 1: [claude\_delegate\_backend\_helpers.sh](file:///home/ken/project/codex_with_cc/codex_with_cc/unix_scripts/claude_delegate_backend_helpers.sh)

在文件末尾（L424 之后）添加 `new_claude_delegate_cli_args` 函数：

```bash
new_claude_delegate_cli_args() {
    local model="$1"
    local session_name="$2"
    local session_id="$3"
    local resume="$4"
    local max_budget_usd="$5"
    local bypass_permissions="$6"

    printf '%s\n' '--verbose'
    printf '%s\n' '--print'
    printf '%s\n' '--output-format'
    printf '%s\n' 'stream-json'
    printf '%s\n' '--model'
    printf '%s\n' "$model"
    printf '%s\n' '--name'
    printf '%s\n' "$session_name"
    printf '%s\n' '--permission-mode'
    printf '%s\n' 'acceptEdits'

    if [[ "$resume" == "true" ]]; then
        printf '%s\n' '--resume'
    else
        printf '%s\n' '--session-id'
    fi
    printf '%s\n' "$session_id"

    if [[ -n "$max_budget_usd" ]]; then
        printf '%s\n' '--max-budget-usd'
        printf '%s\n' "$max_budget_usd"
    fi

    if [[ "$bypass_permissions" == "true" ]]; then
        printf '%s\n' '--dangerously-skip-permissions'
    fi
}
```

**与 Windows 版本的功能对应关系**：

| Windows (`New-ClaudeDelegateCliArgs`) | Linux (`new_claude_delegate_cli_args`)                   |
| ------------------------------------- | -------------------------------------------------------- |
| `'--verbose'`                         | `printf '%s\n' '--verbose'`                              |
| `'--print'`                           | `printf '%s\n' '--print'`                                |
| `'--output-format', 'stream-json'`    | `printf ... 'stream-json'`                               |
| `'--model', $Model`                   | `printf ... "$model"`                                    |
| `'--name', $SessionName`              | `printf ... "$session_name"`                             |
| `'--permission-mode', 'acceptEdits'`  | `printf ... 'acceptEdits'`                               |
| `'--resume', $SessionId`              | `printf ... '--resume'` + `printf ... "$session_id"`     |
| `'--session-id', $SessionId`          | `printf ... '--session-id'` + `printf ... "$session_id"` |
| `'--max-budget-usd', $MaxBudgetUsd`   | 条件分支 `printf ... "$max_budget_usd"`                      |
| `'--dangerously-skip-permissions'`    | 条件分支 `printf ... '--dangerously-skip-permissions'`       |

Prompt 文本不在 args 数组中，而是作为 claude 命令的最后一个位置参数单独传递（见下方文件 2 修改）。

### 文件 2: [delegate\_to\_claude.sh](file:///home/ken/project/codex_with_cc/codex_with_cc/unix_scripts/delegate_to_claude.sh)

**修改 A — L782-L790**：从调用中移除 `$PROMPT_TEXT`（6 个参数 → 6 个参数）

```diff
     mapfile -t CLAUDE_ARGS < <(new_claude_delegate_cli_args \
         "$MODEL" \
         "$EFFECTIVE_NAME" \
         "$SESSION_ID" \
         "$attempt_resume" \
         "${MAX_BUDGET_USD:-}" \
-        "$BYPASS_PERMISSIONS" \
-        "$PROMPT_TEXT")
+        "$BYPASS_PERMISSIONS")
```

**修改 B — L836**：将 `$PROMPT_TEXT` 作为最后一个位置参数传给 claude

```diff
-    done < <(claude "${CLAUDE_ARGS[@]}" 2>&1)
+    done < <(claude "${CLAUDE_ARGS[@]}" "$PROMPT_TEXT" 2>&1)
```

此方式与 Windows 版本 `$claudeArgs += $PromptText` 作为最后一个数组元素的逻辑**完全一致**。

### 完整修改总结

| # | 文件                                                                                                                                            | 位置      | 修改                                                                                |
| - | --------------------------------------------------------------------------------------------------------------------------------------------- | ------- | --------------------------------------------------------------------------------- |
| 1 | [claude\_delegate\_backend\_helpers.sh](file:///home/ken/project/codex_with_cc/codex_with_cc/unix_scripts/claude_delegate_backend_helpers.sh) | L424 之后 | **新增** `new_claude_delegate_cli_args` 函数（\~35行）                                   |
| 2 | [delegate\_to\_claude.sh](file:///home/ken/project/codex_with_cc/codex_with_cc/unix_scripts/delegate_to_claude.sh)                            | L790    | **删除** `"$PROMPT_TEXT"` 参数                                                        |
| 3 | [delegate\_to\_claude.sh](file:///home/ken/project/codex_with_cc/codex_with_cc/unix_scripts/delegate_to_claude.sh)                            | L836    | **修改** `claude "${CLAUDE_ARGS[@]}"` → `claude "${CLAUDE_ARGS[@]}" "$PROMPT_TEXT"` |

### 验证步骤

1. 运行安装器测试：
   ```bash
   bash tests/test_install_codex_with_cc.sh
   ```
2. 在目标项目执行 dry-run 验证：
   ```bash
   export CODEX_CLAUDE_CHILD_THREAD=1
   bash docs/codex_with_cc/unix_scripts/delegate_to_claude.sh \
     -t "echo hello" --session-mode PrimaryReuse \
     --session-key test --bypass-permissions --dry-run
   ```
   确认输出中 `claude` 参数列表完整，无报错

