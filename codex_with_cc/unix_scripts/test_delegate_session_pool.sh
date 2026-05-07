#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/test_helpers.sh"
source "$SCRIPT_DIR/claude_delegate_backend_helpers.sh"
source "$SCRIPT_DIR/claude_session_pool.sh"

TEST_ROOT=""
TESTS_PASSED=0
TESTS_FAILED=0

setup_test_env() {
    TEST_ROOT=$(mktemp -d)
    mkdir -p "$TEST_ROOT/session-pools"
}

cleanup_test_env() {
    if [[ -n "$TEST_ROOT" ]] && [[ -d "$TEST_ROOT" ]]; then
        rm -rf "$TEST_ROOT"
    fi
}

run_test() {
    local name="$1"
    local test_func="$2"
    local result
    
    echo "Running test: $name"
    setup_test_env
    result="$($test_func)"
    printf '%s\n' "$result"
    if [[ "$result" == "true" ]]; then
        echo "  PASSED: $name"
        TESTS_PASSED=$((TESTS_PASSED + 1))
    else
        echo "  FAILED: $name" >&2
        TESTS_FAILED=$((TESTS_FAILED + 1))
    fi
    cleanup_test_env
}

test_new_claude_session_id() {
    local session_id
    session_id=$(new_claude_session_id)
    
    if [[ -n "$session_id" ]] && [[ ${#session_id} -ge 10 ]]; then
        echo "true"
    else
        echo "false"
    fi
}

test_get_effective_session_key() {
    local key1
    key1=$(get_effective_session_key "explicit-key")
    
    local key2
    CODEX_THREAD_ID="thread-123"
    key2=$(get_effective_session_key "")
    unset CODEX_THREAD_ID
    
    local key3
    key3=$(get_effective_session_key "")
    
    if [[ "$key1" == "explicit-key" ]] && \
       [[ "$key2" == "thread-123" ]] && \
       [[ "$key3" == "default" ]]; then
        echo "true"
    else
        echo "false"
    fi
}

test_get_safe_session_key() {
    local safe1
    safe1=$(get_safe_session_key "test-key-123")
    
    local safe2
    safe2=$(get_safe_session_key "test key with spaces")
    
    local safe3
    safe3=$(get_safe_session_key "")
    
    if [[ "$safe1" == "test-key-123" ]] && \
       [[ "$safe2" == "test_key_with_spaces" ]] && \
       [[ "$safe3" == "default" ]]; then
        echo "true"
    else
        echo "false"
    fi
}

test_get_task_fingerprint() {
    local fp1
    fp1=$(get_task_fingerprint "task text" "scope" "tests" "Implement")
    
    local fp2
    fp2=$(get_task_fingerprint "task text" "scope" "tests" "Implement")
    
    local fp3
    fp3=$(get_task_fingerprint "different task" "scope" "tests" "Implement")
    
    if [[ "$fp1" == "$fp2" ]] && [[ "$fp1" != "$fp3" ]]; then
        echo "true"
    else
        echo "false"
    fi
}

test_new_session_pool_state() {
    local state
    state=$(new_session_pool_state "test-key")
    
    local version
    version=$(echo "$state" | jq -r '.version')
    local key
    key=$(echo "$state" | jq -r '.sessionKey')
    local primary_status
    primary_status=$(echo "$state" | jq -r '.primary.status')
    
    if [[ "$version" == "1" ]] && \
       [[ "$key" == "test-key" ]] && \
       [[ "$primary_status" == "available" ]]; then
        echo "true"
    else
        echo "false"
    fi
}

test_read_session_pool_state_creates_default() {
    local state_path="$TEST_ROOT/session-pools/test-key.json"
    
    local state
    state=$(read_session_pool_state "$state_path" "test-key")
    
    local key
    key=$(echo "$state" | jq -r '.sessionKey')
    
    if [[ "$key" == "test-key" ]]; then
        echo "true"
    else
        echo "false"
    fi
}

test_write_session_pool_state() {
    local state_path="$TEST_ROOT/session-pools/test-key.json"
    local state='{"version":1,"sessionKey":"test-key","primary":{"status":"available"},"parallelPool":[]}'
    
    write_session_pool_state "$state_path" "$state"
    
    if [[ -f "$state_path" ]]; then
        local read_state
        read_state=$(cat "$state_path")
        local has_updated
        has_updated=$(echo "$read_state" | jq -r '.updatedAt // empty')
        
        if [[ -n "$has_updated" ]]; then
            echo "true"
        else
            echo "false"
        fi
    else
        echo "false"
    fi
}

test_acquire_primary_reuse_lease() {
    local state_path="$TEST_ROOT/session-pools/test-key.json"
    local lock_path="$TEST_ROOT/session-pools/test-key.lock"
    
    local lease
    lease=$(acquire_claude_session_lease \
        "$state_path" \
        "$lock_path" \
        "test-key" \
        "PrimaryReuse" \
        "run-001" \
        "fingerprint-abc" \
        21600 \
        30 \
        "false" \
        "false")
    
    local mode
    mode=$(echo "$lease" | jq -r '.mode')
    local session_id
    session_id=$(echo "$lease" | jq -r '.sessionId')
    local leased
    leased=$(echo "$lease" | jq -r '.leased')
    
    if [[ "$mode" == "PrimaryReuse" ]] && \
       [[ -n "$session_id" ]] && \
       [[ "$leased" == "true" ]]; then
        echo "true"
    else
        echo "false"
    fi
}

test_acquire_primary_anchor_lease() {
    local state_path="$TEST_ROOT/session-pools/test-key.json"
    local lock_path="$TEST_ROOT/session-pools/test-key.lock"
    
    local lease
    lease=$(acquire_claude_session_lease \
        "$state_path" \
        "$lock_path" \
        "test-key" \
        "PrimaryAnchor" \
        "run-001" \
        "fingerprint-abc" \
        21600 \
        30 \
        "false" \
        "false")
    
    local mode
    mode=$(echo "$lease" | jq -r '.mode')
    
    if [[ "$mode" == "PrimaryAnchor" ]]; then
        echo "true"
    else
        echo "false"
    fi
}

test_acquire_parallel_pool_lease() {
    local state_path="$TEST_ROOT/session-pools/test-key.json"
    local lock_path="$TEST_ROOT/session-pools/test-key.lock"
    
    local lease
    lease=$(acquire_claude_session_lease \
        "$state_path" \
        "$lock_path" \
        "test-key" \
        "ParallelPool" \
        "run-001" \
        "fingerprint-abc" \
        21600 \
        30 \
        "false" \
        "false")
    
    local mode
    mode=$(echo "$lease" | jq -r '.mode')
    local pool_index
    pool_index=$(echo "$lease" | jq -r '.poolIndex')
    
    if [[ "$mode" == "ParallelPool" ]] && [[ "$pool_index" == "0" ]]; then
        echo "true"
    else
        echo "false"
    fi
}

test_acquire_parallel_pool_reuses_matching_fingerprint() {
    local state_path="$TEST_ROOT/session-pools/test-key.json"
    local lock_path="$TEST_ROOT/session-pools/test-key.lock"
    
    local lease1
    lease1=$(acquire_claude_session_lease \
        "$state_path" \
        "$lock_path" \
        "test-key" \
        "ParallelPool" \
        "run-001" \
        "fingerprint-abc" \
        21600 \
        30 \
        "false" \
        "false")
    
    release_claude_session_lease \
        "$state_path" \
        "$lock_path" \
        "test-key" \
        "$lease1" \
        "run-001" \
        "fingerprint-abc"
    
    local lease2
    lease2=$(acquire_claude_session_lease \
        "$state_path" \
        "$lock_path" \
        "test-key" \
        "ParallelPool" \
        "run-002" \
        "fingerprint-abc" \
        21600 \
        30 \
        "false" \
        "false")
    
    local session_id1
    session_id1=$(echo "$lease1" | jq -r '.sessionId')
    local session_id2
    session_id2=$(echo "$lease2" | jq -r '.sessionId')
    local resume2
    resume2=$(echo "$lease2" | jq -r '.resume')
    
    if [[ "$session_id1" == "$session_id2" ]] && [[ "$resume2" == "true" ]]; then
        echo "true"
    else
        echo "false"
    fi
}

test_release_primary_lease() {
    local state_path="$TEST_ROOT/session-pools/test-key.json"
    local lock_path="$TEST_ROOT/session-pools/test-key.lock"
    
    local lease
    lease=$(acquire_claude_session_lease \
        "$state_path" \
        "$lock_path" \
        "test-key" \
        "PrimaryReuse" \
        "run-001" \
        "fingerprint-abc" \
        21600 \
        30 \
        "false" \
        "false")
    
    release_claude_session_lease \
        "$state_path" \
        "$lock_path" \
        "test-key" \
        "$lease" \
        "run-001" \
        "fingerprint-abc"
    
    local state
    state=$(cat "$state_path")
    local primary_status
    primary_status=$(echo "$state" | jq -r '.primary.status')
    
    if [[ "$primary_status" == "available" ]]; then
        echo "true"
    else
        echo "false"
    fi
}

test_release_parallel_pool_lease() {
    local state_path="$TEST_ROOT/session-pools/test-key.json"
    local lock_path="$TEST_ROOT/session-pools/test-key.lock"
    
    local lease
    lease=$(acquire_claude_session_lease \
        "$state_path" \
        "$lock_path" \
        "test-key" \
        "ParallelPool" \
        "run-001" \
        "fingerprint-abc" \
        21600 \
        30 \
        "false" \
        "false")
    
    release_claude_session_lease \
        "$state_path" \
        "$lock_path" \
        "test-key" \
        "$lease" \
        "run-001" \
        "fingerprint-abc"
    
    local state
    state=$(cat "$state_path")
    local slot_status
    slot_status=$(echo "$state" | jq -r '.parallelPool[0].status')
    
    if [[ "$slot_status" == "available" ]]; then
        echo "true"
    else
        echo "false"
    fi
}

test_expired_lease_reclaimed() {
    local state_path="$TEST_ROOT/session-pools/test-key.json"
    local lock_path="$TEST_ROOT/session-pools/test-key.lock"
    
    local lease
    lease=$(acquire_claude_session_lease \
        "$state_path" \
        "$lock_path" \
        "test-key" \
        "PrimaryReuse" \
        "run-001" \
        "fingerprint-abc" \
        21600 \
        30 \
        "false" \
        "false")
    
    local state
    state=$(cat "$state_path")
    local old_time="2020-01-01T00:00:00Z"
    state=$(echo "$state" | jq --arg time "$old_time" '.primary.leasedAt = $time')
    echo "$state" > "$state_path"
    
    local new_lease
    new_lease=$(acquire_claude_session_lease \
        "$state_path" \
        "$lock_path" \
        "test-key" \
        "PrimaryReuse" \
        "run-002" \
        "fingerprint-xyz" \
        1 \
        30 \
        "false" \
        "false")
    
    local new_run_id
    new_run_id=$(echo "$new_lease" | jq -r '.leased // false')
    
    if [[ "$new_run_id" == "true" ]]; then
        echo "true"
    else
        echo "false"
    fi
}

test_reset_session_for_fresh_session() {
    local state_path="$TEST_ROOT/session-pools/test-key.json"
    local lock_path="$TEST_ROOT/session-pools/test-key.lock"
    
    local lease
    lease=$(acquire_claude_session_lease \
        "$state_path" \
        "$lock_path" \
        "test-key" \
        "PrimaryReuse" \
        "run-001" \
        "fingerprint-abc" \
        21600 \
        30 \
        "false" \
        "false")
    
    local old_session_id
    old_session_id=$(echo "$lease" | jq -r '.sessionId')
    
    local new_lease
    new_lease=$(reset_claude_session_lease_for_fresh_session \
        "$state_path" \
        "$lock_path" \
        "test-key" \
        "$lease" \
        "run-001" \
        "fingerprint-abc" \
        "stale_session")
    
    local new_session_id
    new_session_id=$(echo "$new_lease" | jq -r '.sessionId')
    local resume
    resume=$(echo "$new_lease" | jq -r '.resume')
    
    if [[ "$new_session_id" != "$old_session_id" ]] && [[ "$resume" == "false" ]]; then
        echo "true"
    else
        echo "false"
    fi
}

test_primary_lease_blocks_concurrent_primary() {
    local state_path="$TEST_ROOT/session-pools/test-key.json"
    local lock_path="$TEST_ROOT/session-pools/test-key.lock"
    
    local lease1
    lease1=$(acquire_claude_session_lease \
        "$state_path" \
        "$lock_path" \
        "test-key" \
        "PrimaryReuse" \
        "run-001" \
        "fingerprint-abc" \
        21600 \
        30 \
        "false" \
        "false")
    
    local lease2
    lease2=$(timeout 2 bash -c "
        source '$SCRIPT_DIR/claude_session_pool.sh'
        source '$SCRIPT_DIR/claude_delegate_backend_helpers.sh'
        acquire_claude_session_lease \
            '$state_path' \
            '$lock_path' \
            'test-key' \
            'PrimaryReuse' \
            'run-002' \
            'fingerprint-xyz' \
            21600 \
            1 \
            'false' \
            'false'
    " 2>&1 || echo "timeout")
    
    if [[ "$lease2" == "null" ]] || [[ "$lease2" == *"timeout"* ]] || [[ -z "$lease2" ]]; then
        echo "true"
    else
        echo "false"
    fi
}

echo "========================================"
echo "Running session pool tests"
echo "========================================"
echo ""

run_test "new_claude_session_id" test_new_claude_session_id
run_test "get_effective_session_key" test_get_effective_session_key
run_test "get_safe_session_key" test_get_safe_session_key
run_test "get_task_fingerprint" test_get_task_fingerprint
run_test "new_session_pool_state" test_new_session_pool_state
run_test "read_session_pool_state_creates_default" test_read_session_pool_state_creates_default
run_test "write_session_pool_state" test_write_session_pool_state
run_test "acquire_primary_reuse_lease" test_acquire_primary_reuse_lease
run_test "acquire_primary_anchor_lease" test_acquire_primary_anchor_lease
run_test "acquire_parallel_pool_lease" test_acquire_parallel_pool_lease
run_test "acquire_parallel_pool_reuses_matching_fingerprint" test_acquire_parallel_pool_reuses_matching_fingerprint
run_test "release_primary_lease" test_release_primary_lease
run_test "release_parallel_pool_lease" test_release_parallel_pool_lease
run_test "expired_lease_reclaimed" test_expired_lease_reclaimed
run_test "reset_session_for_fresh_session" test_reset_session_for_fresh_session
run_test "primary_lease_blocks_concurrent_primary" test_primary_lease_blocks_concurrent_primary

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
