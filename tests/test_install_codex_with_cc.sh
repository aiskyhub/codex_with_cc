#!/usr/bin/env bash

set -euo pipefail

repo_root="$(
  cd "$(dirname "$0")/.."
  pwd -P
)"

installer_path="$repo_root/scripts/install_codex_with_cc.sh"
source_workflow_root="$repo_root/codex_with_cc"
legacy_templates_root="$repo_root/templates"
temp_root="$(mktemp -d "${TMPDIR:-/tmp}/codex_with_cc_install.XXXXXX")"
target_root="$temp_root/host-project"

assert_true() {
  local name="$1"
  shift
  if "$@"; then
    printf 'PASS: %s\n' "$name"
    return
  fi
  printf 'FAIL: %s\n' "$name" >&2
  exit 1
}

assert_contains() {
  local name="$1"
  local haystack="$2"
  local needle="$3"
  if [[ "$haystack" == *"$needle"* ]]; then
    printf 'PASS: %s\n' "$name"
    return
  fi
  printf 'FAIL: %s\nMissing: %s\n' "$name" "$needle" >&2
  exit 1
}

assert_not_contains() {
  local name="$1"
  local haystack="$2"
  local needle="$3"
  if [[ "$haystack" == *"$needle"* ]]; then
    printf 'FAIL: %s\nUnexpected: %s\n' "$name" "$needle" >&2
    exit 1
  fi
  printf 'PASS: %s\n' "$name"
}

cleanup() {
  rm -rf "$temp_root"
}
trap cleanup EXIT

mkdir -p "$target_root"
printf '# Host Project\n' >"$target_root/README.md"
printf 'build\n.claude\n' >"$target_root/.gitignore"
cat <<'EOF' >"$target_root/AGENTS.md"
# Existing Host Instructions

Keep this project-specific rule.
EOF

assert_true "installer-exists" test -f "$installer_path"
assert_true "source-workflow-root-exists-at-repo-root" test -d "$source_workflow_root"
assert_true "legacy-templates-root-removed" test ! -e "$legacy_templates_root"

install_output="$(bash "$installer_path" --target-root "$target_root" --platform Linux 2>&1)"

workflow_root="$target_root/docs/codex_with_cc"
task_root="$target_root/.codex/codex_with_cc/tasks"
assert_true "workflow-root-created" test -d "$workflow_root"
assert_true "codex-with-cc-entry-created" test -f "$workflow_root/CODEX_WITH_CC.md"
assert_true "delegate-script-created" test -f "$workflow_root/unix_scripts/delegate_to_claude.sh"
assert_true "chain-verifier-created" test -f "$workflow_root/unix_scripts/verify_delegate_chain.sh"
assert_true "linux-install-does-not-copy-windows-scripts" test ! -e "$workflow_root/windows_scripts"
assert_true "tasks-dir-created-under-codex-root" test -d "$task_root"
assert_true "tasks-gitkeep-not-created" test ! -e "$task_root/.gitkeep"
assert_true "legacy-docs-ai-not-created" test ! -e "$target_root/docs/ai"
assert_true "legacy-docs-scripts-ai-not-created" test ! -e "$target_root/docs/scripts/ai"

gitignore_text="$(cat "$target_root/.gitignore")"
assert_contains "gitignore-contains-targeted-codex-with-cc-entry" "$gitignore_text" '.codex/codex_with_cc'
assert_true "gitignore-does-not-ignore-shared-codex-root" bash -lc "! grep -Fxq '.codex' \"$0\"" "$target_root/.gitignore"
assert_true "gitignore-does-not-ignore-shared-codex-root-slash" bash -lc "! grep -Fxq '.codex/' \"$0\"" "$target_root/.gitignore"

agents_text="$(cat "$target_root/AGENTS.md")"
assert_contains "existing-agents-content-preserved" "$agents_text" 'Keep this project-specific rule.'
assert_contains "agents-managed-block-added" "$agents_text" '<!-- BEGIN CODEX_WITH_CC -->'
assert_contains "agents-managed-block-points-to-central-entry" "$agents_text" 'docs/codex_with_cc/CODEX_WITH_CC.md'
assert_contains "agents-managed-block-keeps-markdown-code-format" "$agents_text" '`docs/codex_with_cc/CODEX_WITH_CC.md`'
assert_contains "agents-managed-block-requires-reading-workflow-before-subagent-logic" "$agents_text" 'If the task involves child agents, subagents, delegation, or any worker-execution step, you must read that file first'
assert_contains "agents-managed-block-points-to-custom-subagent-chain" "$agents_text" 'Codex main thread -> Codex child agent -> delegate_to_claude.* -> Claude Code CLI'
assert_true "claude-entrypoint-not-created" test ! -e "$target_root/CLAUDE.md"
assert_true "gemini-entrypoint-not-created" test ! -e "$target_root/GEMINI.md"
assert_contains "install-output-lists-only-agents" "$install_output" 'Agent entrypoints updated: AGENTS.md'

delegate_text="$(cat "$workflow_root/unix_scripts/delegate_to_claude.sh")"
assert_contains "delegate-uses-central-workflow-entry" "$delegate_text" 'docs/codex_with_cc/CODEX_WITH_CC.md'
assert_contains "delegate-prompt-uses-central-script-path" "$delegate_text" 'docs/codex_with_cc/unix_scripts/delegate_to_claude.sh'

printf 'stale\n' >"$workflow_root/obsolete.txt"
printf 'stale host rules\n' >"$workflow_root/HOST_PROJECT_RULES.md"
printf 'stale project memory\n' >"$workflow_root/PROJECT_MEMORY.md"
mkdir -p "$task_root"
: >"$task_root/.gitkeep"

reinstall_output="$(bash "$installer_path" --target-root "$target_root" --platform Linux 2>&1)"
agents_text_after_reinstall="$(cat "$target_root/AGENTS.md")"
managed_block_count="$(grep -c '<!-- BEGIN CODEX_WITH_CC -->' "$target_root/AGENTS.md")"
[[ "$managed_block_count" == "1" ]] || {
  printf 'FAIL: reinstall-keeps-one-managed-block\n' >&2
  exit 1
}
printf 'PASS: reinstall-keeps-one-managed-block\n'
assert_true "reinstall-removes-obsolete-file" test ! -e "$workflow_root/obsolete.txt"
assert_true "reinstall-removes-stale-host-rules" test ! -e "$workflow_root/HOST_PROJECT_RULES.md"
assert_true "reinstall-removes-stale-project-memory" test ! -e "$workflow_root/PROJECT_MEMORY.md"
assert_true "reinstall-removes-stale-gitkeep" test ! -e "$task_root/.gitkeep"
assert_true "reinstall-recreates-tasks-dir" test -d "$task_root"
assert_contains "reinstall-output-lists-only-agents" "$reinstall_output" 'Agent entrypoints updated: AGENTS.md'

self_install_root="$temp_root/self-install-source"
mkdir -p "$self_install_root/scripts"
cp "$installer_path" "$self_install_root/scripts/install_codex_with_cc.sh"
cp -R "$source_workflow_root" "$self_install_root/codex_with_cc"

nested_target_root="$self_install_root/source-subdir"
mkdir -p "$nested_target_root"
set +e
nested_install_output="$(bash "$self_install_root/scripts/install_codex_with_cc.sh" --target-root "$nested_target_root" 2>&1)"
nested_install_status=$?
set -e
if [[ $nested_install_status -eq 0 ]]; then
  printf 'FAIL: nested-source-install-refuses-source-subdir-target\n' >&2
  exit 1
fi
printf 'PASS: nested-source-install-refuses-source-subdir-target\n'
assert_contains "nested-source-install-error-is-clear" "$nested_install_output" 'Refusing to install codex_with_cc into a subdirectory of its own source repository'

set +e
self_install_output="$(bash "$self_install_root/scripts/install_codex_with_cc.sh" --target-root "$self_install_root" 2>&1)"
self_install_status=$?
set -e
if [[ $self_install_status -eq 0 ]]; then
  printf 'FAIL: self-install-refuses-source-target-overlap\n' >&2
  exit 1
fi
printf 'PASS: self-install-refuses-source-target-overlap\n'
assert_contains "self-install-error-is-clear" "$self_install_output" 'Refusing to install codex_with_cc into its own source repository'
assert_true "self-install-keeps-source-workflow" test -f "$self_install_root/codex_with_cc/CODEX_WITH_CC.md"
assert_true "self-install-keeps-source-scripts" test -f "$self_install_root/codex_with_cc/unix_scripts/delegate_to_claude.sh"

mac_target_root="$temp_root/mac-host-project"
mkdir -p "$mac_target_root"
mac_install_output="$(bash "$installer_path" --target-root "$mac_target_root" --platform macOS --skip-agent-entrypoints 2>&1)"
mac_workflow_root="$mac_target_root/docs/codex_with_cc"
assert_true "mac-install-copies-workflow-doc" test -f "$mac_workflow_root/CODEX_WITH_CC.md"
assert_true "mac-install-copies-unix-scripts" test -f "$mac_workflow_root/unix_scripts/delegate_to_claude.sh"
assert_true "mac-install-does-not-copy-windows-scripts" test ! -e "$mac_workflow_root/windows_scripts"
assert_true "mac-install-skip-agent-entrypoints-keeps-agents-absent" test ! -e "$mac_target_root/AGENTS.md"
mac_delegate_text="$(cat "$mac_workflow_root/unix_scripts/delegate_to_claude.sh")"
assert_contains "mac-unix-script-points-to-central-entry" "$mac_delegate_text" 'docs/codex_with_cc/unix_scripts/delegate_to_claude.sh'
assert_contains "mac-install-output-keeps-install-message" "$mac_install_output" 'codex_with_cc installed into:'
assert_not_contains "mac-install-output-omits-agent-update" "$mac_install_output" 'Agent entrypoints updated: AGENTS.md'

printf 'install shell tests passed\n'
