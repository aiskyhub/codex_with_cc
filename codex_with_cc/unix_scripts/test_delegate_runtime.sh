#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/test_helpers.sh"
source "$SCRIPT_DIR/claude_delegate_backend_helpers.sh"
source "$SCRIPT_DIR/claude_session_pool.sh"

WORKFLOW_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
WORKFLOW_CONTAINER="$(dirname "$WORKFLOW_ROOT")"
if [[ "$(basename "$WORKFLOW_CONTAINER")" == "docs" ]]; then
    REPO_ROOT="$(cd "$WORKFLOW_CONTAINER/.." && pwd)"
else
    REPO_ROOT="$WORKFLOW_CONTAINER"
fi

TESTS_PASSED=0
TESTS_FAILED=0

run_test() {
    local name="$1"
    local test_func="$2"
    local result
    
    echo "Running test: $name"
    result="$($test_func)"
    printf '%s\n' "$result"
    if [[ "$result" == "true" ]]; then
        echo "  PASSED: $name"
        TESTS_PASSED=$((TESTS_PASSED + 1))
    else
        echo "  FAILED: $name" >&2
        TESTS_FAILED=$((TESTS_FAILED + 1))
    fi
}

test_child_thread_marker_missing() {
    local result
    result=$(unset CODEX_CLAUDE_CHILD_THREAD && bash "$SCRIPT_DIR/delegate_to_claude.sh" -t "test task" 2>&1 || true)
    
    if echo "$result" | grep -q "may only run inside a Codex spawn_agent child thread"; then
        echo "true"
    else
        echo "false"
    fi
}

test_lock_timeout_rejection() {
    local tmp_root
    tmp_root=$(mktemp -d)
    local lock_path="$tmp_root/delegate.lock"
    local tmp_home
    tmp_home=$(mktemp -d)
    
    mkdir -p "$(dirname "$lock_path")"
    echo '{"runId":"other-run","pid":999999,"startedAt":"2025-01-01T00:00:00Z"}' > "$lock_path"
    
    exec 3>"$lock_path"
    flock -x 3
    
    local result
    result=$(HOME="$tmp_home" XDG_CONFIG_HOME="$tmp_home/.config" CODEX_CLAUDE_CHILD_THREAD=1 timeout 5 bash "$SCRIPT_DIR/delegate_to_claude.sh" \
        -t "test task" \
        --artifact-root "$tmp_root" \
        --lock-timeout 2 \
        2>&1 || true)
    
    flock -u 3
    exec 3>&-
    
    rm -rf "$tmp_root"
    rm -rf "$tmp_home"
    
    if echo "$result" | grep -q "Another delegate_to_claude run is still active"; then
        echo "true"
    else
        echo "false"
    fi
}

test_unwritable_claude_state_emits_rerun_script() {
    local tmp_root
    tmp_root=$(mktemp -d)
    local home_parent
    home_parent=$(mktemp -d)
    local readonly_home="$home_parent/readonly-home"
    mkdir -p "$readonly_home"
    chmod 555 "$readonly_home"

    local result
    result=$(HOME="$readonly_home" CODEX_CLAUDE_CHILD_THREAD=1 bash "$SCRIPT_DIR/delegate_to_claude.sh" \
        -t "test task" \
        --artifact-root "$tmp_root" \
        2>&1 || true)

    local rerun_script
    rerun_script=$(find "$tmp_root" -maxdepth 1 -name 'rerun_*.sh' | head -n 1)

    chmod 755 "$readonly_home"
    rm -rf "$home_parent" "$tmp_root"

    if echo "$result" | grep -q "Trusted local terminal fallback script" && [[ -n "$rerun_script" ]]; then
        echo "true"
    else
        echo "false"
    fi
}

test_unstructured_output_normalization() {
    local text="This is a simple response without the required headings."
    
    local normalized
    normalized=$(convert_claude_delegate_unstructured_final_text "$text")
    
    if echo "$normalized" | grep -q "Final Result" && \
       echo "$normalized" | grep -q "UNSTRUCTURED_SUCCESS_NORMALIZED"; then
        echo "true"
    else
        echo "false"
    fi
}

test_stale_session_retry_detection() {
    local raw_lines='{"type":"assistant","message":{"role":"assistant","content":[{"type":"text","text":"Error: No conversation found for session ID abc123"}]}}
{"type":"result","subtype":"error"}'
    
    local decision
    decision=$(get_claude_delegate_retry_decision "$raw_lines" "true" 1 "true" "false" "false")
    
    local should_retry
    should_retry=$(echo "$decision" | jq -r '.shouldRetry')
    local retry_with_fresh
    retry_with_fresh=$(echo "$decision" | jq -r '.retryWithFreshSession')
    
    if [[ "$should_retry" == "true" ]] && [[ "$retry_with_fresh" == "true" ]]; then
        echo "true"
    else
        echo "false"
    fi
}

test_stream_json_startup_error_retry() {
    local raw_lines='Error: stream-json output format requires --verbose flag
{"type":"result","subtype":"error"}'
    
    local decision
    decision=$(get_claude_delegate_retry_decision "$raw_lines" "false" 1 "false" "false" "false")
    
    local should_retry
    should_retry=$(echo "$decision" | jq -r '.shouldRetry')
    local retry_reason
    retry_reason=$(echo "$decision" | jq -r '.retryReason')
    
    if [[ "$should_retry" == "true" ]] && [[ "$retry_reason" == "stream_json_startup" ]]; then
        echo "true"
    else
        echo "false"
    fi
}

test_tool_result_false_positive_exclusion() {
    local raw_lines='{"type":"assistant","message":{"role":"assistant","content":[{"type":"text","text":"The error message says: No conversation found for session ID but this is just a reference in the output."}]}}
{"type":"result","subtype":"success"}'
    
    local decision
    decision=$(get_claude_delegate_retry_decision "$raw_lines" "true" 0 "true" "true" "true")
    
    local should_retry
    should_retry=$(echo "$decision" | jq -r '.shouldRetry')
    
    if [[ "$should_retry" == "false" ]]; then
        echo "true"
    else
        echo "false"
    fi
}

test_final_result_heading_detection() {
    local text_with_heading="Some content before

Final Result
This is the final result.

More content after."
    
    local text_without_heading="Some content without the heading"
    
    local has_heading
    has_heading=$(test_claude_delegate_text_has_final_result_heading "$text_with_heading")
    
    local no_heading
    no_heading=$(test_claude_delegate_text_has_final_result_heading "$text_without_heading")
    
    if [[ "$has_heading" == "true" ]] && [[ "$no_heading" == "false" ]]; then
        echo "true"
    else
        echo "false"
    fi
}

test_output_resolution_success() {
    local final_text="Process Log
- Step 1 completed

Summary
Task completed successfully

Changed Files
- file1.sh

Verification
- All tests passed

Final Result
SUCCESS

Risks Or Follow-ups
None"
    
    local resolution
    resolution=$(get_claude_delegate_output_resolution "$final_text" "" 0 "true" "true")
    
    local delegate_succeeded
    delegate_succeeded=$(echo "$resolution" | jq -r '.delegateSucceeded')
    
    if [[ "$delegate_succeeded" == "true" ]]; then
        echo "true"
    else
        echo "false"
    fi
}

test_output_resolution_normalization() {
    local final_text="This is a simple response without headings."
    
    local resolution
    resolution=$(get_claude_delegate_output_resolution "$final_text" "" 0 "true" "false")
    
    local output_was_normalized
    output_was_normalized=$(echo "$resolution" | jq -r '.outputWasNormalized')
    
    if [[ "$output_was_normalized" == "true" ]]; then
        echo "true"
    else
        echo "false"
    fi
}

test_process_alive_check() {
    local current_pid=$$
    
    local is_alive
    is_alive=$(is_process_alive "$current_pid")
    
    local is_dead
    is_dead=$(is_process_alive 999999999)
    
    if [[ "$is_alive" == "true" ]] && [[ "$is_dead" == "false" ]]; then
        echo "true"
    else
        echo "false"
    fi
}

test_path_writable_check() {
    local tmp_file
    tmp_file=$(mktemp)
    
    local writable
    writable=$(test_claude_delegate_path_writable "$tmp_file")
    
    rm -f "$tmp_file"
    
    if [[ "$writable" == "true" ]]; then
        echo "true"
    else
        echo "false"
    fi
}

test_json_file_atomic_write() {
    local tmp_file
    tmp_file=$(mktemp)
    rm -f "$tmp_file"
    
    local test_data='{"test":"value","number":42}'
    write_claude_delegate_json_file "$tmp_file" "$test_data"
    
    if [[ -f "$tmp_file" ]]; then
        local field
        local number
        field=$(jq -r '.test' "$tmp_file")
        number=$(jq -r '.number' "$tmp_file")
        if [[ "$field" == "value" ]] && [[ "$number" == "42" ]]; then
            rm -f "$tmp_file"
            echo "true"
        else
            rm -f "$tmp_file"
            echo "false"
        fi
    else
        echo "false"
    fi
}

test_attempt_record_append() {
    local attempts='[]'
    local record='{"attempt":1,"sessionId":"session-1","resume":false,"retryReason":null,"exitCode":0,"sawAssistantText":true,"sawResultSuccess":true,"capturedFinalResult":true}'

    local updated
    updated=$(append_claude_delegate_attempt_record "$attempts" "$record")

    local length
    length=$(echo "$updated" | jq 'length')
    local session_id
    session_id=$(echo "$updated" | jq -r '.[0].sessionId')

    if [[ "$length" == "1" ]] && [[ "$session_id" == "session-1" ]]; then
        echo "true"
    else
        echo "false"
    fi
}

test_verify_delegate_artifacts_valid_completed_run() {
    local tmp_root
    tmp_root=$(mktemp -d)
    local run_id="test_run"
    local output_path="$tmp_root/claude_${run_id}.md"
    local prompt_path="$tmp_root/prompt_${run_id}.md"
    local raw_stream_path="$tmp_root/stream_${run_id}.jsonl"
    local trace_path="$tmp_root/trace_${run_id}.log"
    local status_path="$tmp_root/status_${run_id}.json"
    local config_path="$tmp_root/config_${run_id}.json"

    cat <<'EOF' > "$output_path"
Process Log
- test

Summary
ok

Changed Files
None

Verification
- ok

Final Result
SUCCESS

Risks Or Follow-ups
None
EOF
    printf 'prompt\n' > "$prompt_path"
    : > "$raw_stream_path"
    printf '[trace] ok\n' > "$trace_path"

    cat <<EOF > "$status_path"
{
  "artifactSchema": 2,
  "invocationContract": "spawn_agent_child_only",
  "childThreadMarkerName": "CODEX_CLAUDE_CHILD_THREAD",
  "childThreadMarkerValidated": true,
  "runId": "$run_id",
  "status": "completed",
  "pid": 123,
  "outputPath": "$output_path",
  "promptPath": "$prompt_path",
  "rawStreamPath": "$raw_stream_path",
  "tracePath": "$trace_path",
  "linesWritten": 0,
  "outputBytes": 1,
  "exitCode": 0,
  "attemptCount": 1,
  "retryCount": 0,
  "maxRetryCount": 5,
  "outputWasNormalized": false,
  "failureDisposition": null,
  "failureSummary": null,
  "attempts": [
    {
      "attempt": 1,
      "sessionId": "session-1",
      "resume": false,
      "retryReason": null,
      "exitCode": 0,
      "sawAssistantText": true,
      "sawResultSuccess": true,
      "capturedFinalResult": true
    }
  ]
}
EOF

    cat <<EOF > "$config_path"
{
  "artifactSchema": 2,
  "invocationContract": "spawn_agent_child_only",
  "childThreadMarkerName": "CODEX_CLAUDE_CHILD_THREAD",
  "childThreadMarkerValidated": true,
  "runId": "$run_id",
  "repoRoot": "/tmp/repo",
  "mode": "Implement",
  "model": "sonnet",
  "sessionName": "codex-delegate-test",
  "sessionMode": "PrimaryReuse",
  "sessionKey": "test-session",
  "sessionStatePath": "/tmp/session.json",
  "sessionStateLockPath": "/tmp/session.lock",
  "promptPath": "$prompt_path",
  "outputPath": "$output_path",
  "statusPath": "$status_path",
  "rawStreamPath": "$raw_stream_path",
  "tracePath": "$trace_path",
  "lockPath": "/tmp/delegate.lock",
  "taskFile": null,
  "maxBudgetUsd": null,
  "bypassPermissions": true,
  "allowParallel": false,
  "initialSessionId": "session-1",
  "initialResume": false,
  "sessionId": "session-1",
  "resume": false,
  "attemptCount": 1,
  "retryCount": 0,
  "maxRetryCount": 5
}
EOF

    local result="false"
    if bash "$SCRIPT_DIR/verify_delegate_artifacts.sh" -r "$run_id" -a "$tmp_root" >/dev/null 2>&1; then
        result="true"
    fi

    rm -rf "$tmp_root"
    echo "$result"
}

echo "========================================"
echo "Running delegate runtime tests"
echo "========================================"
echo ""

run_test "child_thread_marker_missing" test_child_thread_marker_missing
run_test "lock_timeout_rejection" test_lock_timeout_rejection
run_test "unwritable_claude_state_emits_rerun_script" test_unwritable_claude_state_emits_rerun_script
run_test "unstructured_output_normalization" test_unstructured_output_normalization
run_test "stale_session_retry_detection" test_stale_session_retry_detection
run_test "stream_json_startup_error_retry" test_stream_json_startup_error_retry
run_test "tool_result_false_positive_exclusion" test_tool_result_false_positive_exclusion
run_test "final_result_heading_detection" test_final_result_heading_detection
run_test "output_resolution_success" test_output_resolution_success
run_test "output_resolution_normalization" test_output_resolution_normalization
run_test "process_alive_check" test_process_alive_check
run_test "path_writable_check" test_path_writable_check
run_test "json_file_atomic_write" test_json_file_atomic_write
run_test "attempt_record_append" test_attempt_record_append
run_test "verify_delegate_artifacts_valid_completed_run" test_verify_delegate_artifacts_valid_completed_run

echo ""
echo "========================================"
echo "Test Results"
echo "========================================"
echo "Passed: $TESTS_PASSED"
echo "Failed: $TESTS_FAILED"
echo ""

if [[ $TESTS_FAILED -gt 0 ]]; then
    exit 1
fi

exit 0
