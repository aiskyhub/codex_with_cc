#!/usr/bin/env bash

set -euo pipefail

TARGET_ROOT="$(pwd)"
PLATFORM="Auto"
SKIP_AGENT_ENTRYPOINTS="false"

usage() {
  cat <<'EOF'
Usage: install_codex_with_cc.sh [--target-root <path>] [--platform <Auto|Linux|macOS>] [--skip-agent-entrypoints]
EOF
}

die() {
  printf '%s\n' "$*" >&2
  exit 1
}

get_full_path() {
  local path="$1"
  if [[ -d "$path" ]]; then
    (
      cd "$path"
      pwd -P
    )
    return
  fi

  local parent
  parent="$(dirname "$path")"
  local name
  name="$(basename "$path")"

  (
    cd "$parent"
    printf '%s/%s\n' "$(pwd -P)" "$name"
  )
}

test_path_inside() {
  local child parent
  child="$(get_full_path "$1")"
  parent="$(get_full_path "$2")"
  case "$child/" in
    "$parent"/*) return 0 ;;
    *) return 1 ;;
  esac
}

resolve_install_platform() {
  local platform="$1"
  if [[ "$platform" != "Auto" ]]; then
    case "$platform" in
      Linux|macOS)
        printf '%s\n' "$platform"
        return
        ;;
      Windows)
        die 'The Bash installer only supports Linux and macOS. Use scripts/install_codex_with_cc.ps1 on Windows.'
        ;;
      *)
        die 'Unsupported install platform. Pass --platform Linux or --platform macOS explicitly.'
        ;;
    esac
  fi

  case "$(uname -s)" in
    Linux)
      printf 'Linux\n'
      ;;
    Darwin)
      printf 'macOS\n'
      ;;
    *)
      die 'Unsupported install platform. Pass --platform Linux or --platform macOS explicitly.'
      ;;
  esac
}

update_agent_entrypoint() {
  local path="$1"
  local block begin end tmp
  begin='<!-- BEGIN CODEX_WITH_CC -->'
  end='<!-- END CODEX_WITH_CC -->'
  block="$(cat <<'EOF'
<!-- BEGIN CODEX_WITH_CC -->
Codex with Claude Code workflow: before using this workflow, read `docs/codex_with_cc/CODEX_WITH_CC.md`.
If the task involves child agents, subagents, delegation, or any worker-execution step, you must read that file first and follow the custom `Codex main thread -> Codex child agent -> delegate_to_claude.* -> Claude Code CLI` workflow defined there.
<!-- END CODEX_WITH_CC -->
EOF
)"

  if [[ ! -f "$path" ]]; then
    printf '%s\n' "$block" >"$path"
    return
  fi

  tmp="$(mktemp)"
  awk -v block="$block" -v begin="$begin" -v end="$end" '
    BEGIN {
      in_block = 0
      replaced = 0
    }
    $0 == begin {
      if (!replaced) {
        print block
        replaced = 1
      }
      in_block = 1
      next
    }
    $0 == end {
      in_block = 0
      next
    }
    !in_block {
      print
    }
    END {
      if (!replaced) {
        if (NR > 0) {
          print ""
          print ""
        }
        print block
      }
    }
  ' "$path" >"$tmp"
  mv "$tmp" "$path"
}

update_gitignore() {
  local path="$1"
  local entry='.codex/codex_with_cc'

  if [[ -f "$path" ]]; then
    if grep -Fxq "$entry" "$path" || grep -Fxq "${entry}/" "$path"; then
      return
    fi
    if [[ -s "$path" ]]; then
      printf '\n%s\n' "$entry" >>"$path"
    else
      printf '%s\n' "$entry" >"$path"
    fi
    return
  fi

  printf '%s\n' "$entry" >"$path"
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --target-root)
      [[ $# -ge 2 ]] || die '--target-root requires a value.'
      TARGET_ROOT="$2"
      shift 2
      ;;
    --platform)
      [[ $# -ge 2 ]] || die '--platform requires a value.'
      PLATFORM="$2"
      shift 2
      ;;
    --skip-agent-entrypoints)
      SKIP_AGENT_ENTRYPOINTS="true"
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      die "Unknown argument: $1"
      ;;
  esac
done

script_dir="$(
  cd "$(dirname "$0")"
  pwd -P
)"
repo_root="$(
  cd "$script_dir/.."
  pwd -P
)"
install_platform="$(resolve_install_platform "$PLATFORM")"
source_workflow_root="$repo_root/codex_with_cc"

[[ -d "$source_workflow_root" ]] || die "Workflow source was not found: $source_workflow_root"

mkdir -p "$TARGET_ROOT"
resolved_target_root="$(
  cd "$TARGET_ROOT"
  pwd -P
)"
resolved_source_workflow_root="$(get_full_path "$source_workflow_root")"

if [[ "$repo_root" == "$resolved_target_root" ]]; then
  die "Refusing to install codex_with_cc into its own source repository. Choose a different --target-root so the installer does not modify its source repository: $repo_root"
fi

if test_path_inside "$resolved_target_root" "$repo_root"; then
  die "Refusing to install codex_with_cc into a subdirectory of its own source repository. Choose an external --target-root outside: $resolved_target_root"
fi

docs_root="$resolved_target_root/docs"
workflow_root="$docs_root/codex_with_cc"
codex_root="$resolved_target_root/.codex"
task_root="$codex_root/codex_with_cc/tasks"
mkdir -p "$docs_root"
resolved_workflow_root="$(get_full_path "$workflow_root")"

if [[ "$resolved_source_workflow_root" == "$resolved_workflow_root" ]]; then
  die "Refusing to install codex_with_cc into its own source repository. Choose a different --target-root so the installer does not remove its source workflow directory: $resolved_source_workflow_root"
fi

if [[ -e "$workflow_root" ]]; then
  test_path_inside "$workflow_root" "$resolved_target_root" || die "Refusing to remove workflow directory outside target root: $workflow_root"
  rm -rf "$workflow_root"
fi

mkdir -p "$workflow_root"
cp -R "$source_workflow_root"/. "$workflow_root"/

if [[ "$install_platform" == "Linux" || "$install_platform" == "macOS" ]]; then
  rm -rf "$workflow_root/windows_scripts"
else
  rm -rf "$workflow_root/unix_scripts"
fi

mkdir -p "$task_root"
rm -f "$task_root/.gitkeep"
update_gitignore "$resolved_target_root/.gitignore"

if [[ "$SKIP_AGENT_ENTRYPOINTS" != "true" ]]; then
  update_agent_entrypoint "$resolved_target_root/AGENTS.md"
fi

printf 'codex_with_cc installed into: %s\n' "$workflow_root"
if [[ "$SKIP_AGENT_ENTRYPOINTS" != "true" ]]; then
  printf 'Agent entrypoints updated: AGENTS.md\n'
fi
printf 'Next: read docs/codex_with_cc/CODEX_WITH_CC.md and use it as the single workflow contract.\n'
