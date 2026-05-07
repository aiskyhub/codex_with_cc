#!/usr/bin/env bash
set -euo pipefail

new_claude_session_id() {
    if command -v uuidgen &>/dev/null; then
        uuidgen | tr '[:upper:]' '[:lower:]'
    elif [[ -f /proc/sys/kernel/random/uuid ]]; then
        cat /proc/sys/kernel/random/uuid
    elif command -v python3 &>/dev/null; then
        python3 -c "import uuid; print(uuid.uuid4())"
    else
        echo "session-$(date +%s)-$$"
    fi
}

get_effective_session_key() {
    local value="${1:-}"
    
    if [[ -n "$value" ]]; then
        echo "$value"
        return
    fi
    
    if [[ -n "${CODEX_THREAD_ID:-}" ]]; then
        echo "$CODEX_THREAD_ID"
        return
    fi
    
    if [[ -n "${CODEX_SESSION_ID:-}" ]]; then
        echo "$CODEX_SESSION_ID"
        return
    fi
    
    echo "Using default Claude session key fallback." >&2
    echo "default"
}

get_safe_session_key() {
    local value="${1:-}"
    
    local safe
    safe=$(echo "$value" | sed 's/[^A-Za-z0-9_.-]/_/g')
    
    if [[ -z "$safe" ]]; then
        echo "default"
    else
        echo "$safe"
    fi
}

normalize_claude_delegate_list() {
    local items=("$@")
    local -a normalized=()
    
    for item in "${items[@]}"; do
        if [[ -z "$item" ]]; then
            continue
        fi
        
        IFS=';' read -ra parts <<< "$item"
        for part in "${parts[@]}"; do
            local trimmed
            trimmed=$(echo "$part" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')
            if [[ -n "$trimmed" ]]; then
                normalized+=("$trimmed")
            fi
        done
    done
    
    printf '%s\n' "${normalized[@]}"
}

get_task_fingerprint() {
    local text="$1"
    local scope="$2"
    local tests="$3"
    local mode="$4"
    
    local prefix="${text:0:1000}"
    
    local raw="mode=$mode
scope=$scope
tests=$tests
task=$prefix"
    
    echo -n "$raw" | sha256sum | cut -d' ' -f1
}

test_lease_expired() {
    local item="$1"
    local timeout_seconds="$2"
    
    if [[ -z "$item" ]] || [[ "$item" == "null" ]] || [[ "$timeout_seconds" -lt 0 ]]; then
        echo "false"
        return
    fi
    
    local status
    status=$(echo "$item" | jq -r '.status // empty' 2>/dev/null || echo "")
    if [[ "$status" != "leased" ]]; then
        echo "false"
        return
    fi
    
    local leased_at
    leased_at=$(echo "$item" | jq -r '.leasedAt // empty' 2>/dev/null || echo "")
    if [[ -z "$leased_at" ]]; then
        echo "true"
        return
    fi
    
    local leased_timestamp
    if date --date="$leased_at" +%s >/dev/null 2>&1; then
        leased_timestamp=$(date --date="$leased_at" +%s)
    else
        echo "Warning: Failed to parse leasedAt timestamp '$leased_at'" >&2
        echo "true"
        return
    fi
    
    local now
    now=$(date +%s)
    
    if [[ $((now - leased_timestamp)) -ge $timeout_seconds ]]; then
        echo "true"
    else
        echo "false"
    fi
}

new_session_pool_state() {
    local key="$1"
    local now
    now=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
    
    cat <<EOF
{
  "version": 1,
  "sessionKey": "$key",
  "createdAt": "$now",
  "updatedAt": "$now",
  "primary": {
    "sessionId": null,
    "status": "available",
    "leaseRunId": null,
    "leasePid": null,
    "leasedAt": null,
    "lastUsedAt": null,
    "lastRunId": null,
    "lastResetAt": null,
    "lastResetReason": null,
    "lastResetFromSessionId": null,
    "lastResetFromRunId": null
  },
  "parallelPool": []
}
EOF
}

ensure_session_pool_slot_audit_fields() {
    local slot="$1"
    local include_fingerprint="${2:-false}"
    
    local properties=("lastResetAt" "lastResetReason" "lastResetFromSessionId" "lastResetFromRunId" "leasePid")
    
    for prop in "${properties[@]}"; do
        if ! echo "$slot" | jq -e ".${prop}" >/dev/null 2>&1; then
            slot=$(echo "$slot" | jq --arg key "$prop" '. + {($key): null}')
        fi
    done
    
    if [[ "$include_fingerprint" == "true" ]]; then
        if ! echo "$slot" | jq -e '.lastTaskFingerprint' >/dev/null 2>&1; then
            slot=$(echo "$slot" | jq '. + {"lastTaskFingerprint": null}')
        fi
    fi
    
    echo "$slot"
}

read_session_pool_state() {
    local path="$1"
    local key="$2"
    
    if [[ ! -f "$path" ]]; then
        new_session_pool_state "$key"
        return
    fi
    
    local state
    state=$(cat "$path")
    
    if ! echo "$state" | jq -e '.primary' >/dev/null 2>&1; then
        local primary
        primary=$(new_session_pool_state "$key" | jq '.primary')
        state=$(echo "$state" | jq --argjson primary "$primary" '. + {primary: $primary}')
    fi
    
    if ! echo "$state" | jq -e '.parallelPool' >/dev/null 2>&1; then
        state=$(echo "$state" | jq '. + {"parallelPool": []}')
    fi
    
    local primary
    primary=$(echo "$state" | jq '.primary')
    primary=$(ensure_session_pool_slot_audit_fields "$primary" "false")
    state=$(echo "$state" | jq --argjson primary "$primary" '. + {primary: $primary}')
    
    local pool_count
    pool_count=$(echo "$state" | jq '.parallelPool | length')
    for ((i=0; i<pool_count; i++)); do
        local slot
        slot=$(echo "$state" | jq ".parallelPool[$i]")
        slot=$(ensure_session_pool_slot_audit_fields "$slot" "true")
        state=$(echo "$state" | jq --argjson slot "$slot" ".parallelPool[$i] = \$slot")
    done
    
    echo "$state"
}

write_session_pool_state() {
    local path="$1"
    local state="$2"
    
    local dir
    dir=$(dirname "$path")
    local filename
    filename=$(basename "$path")
    local tmpfile="${dir}/.${filename}.$$.tmp"
    
    local now
    now=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
    state=$(echo "$state" | jq --arg now "$now" '. + {updatedAt: $now}')
    
    mkdir -p "$dir"
    echo "$state" > "$tmpfile"
    mv "$tmpfile" "$path"
}

invoke_session_state_update() {
    local state_path="$1"
    local lock_path="$2"
    local key="$3"
    local timeout_seconds="$4"
    local update_script="$5"
    
    local deadline=$(( $(date +%s) + timeout_seconds ))
    local lock_fd=3
    
    mkdir -p "$(dirname "$lock_path")"
    
    while true; do
        exec 3>"$lock_path"
        if flock -x -n 3; then
            break
        fi
        
        if [[ $(date +%s) -ge $deadline ]]; then
            echo "Timed out waiting for Claude session pool lock: $lock_path" >&2
            return 1
        fi
        
        sleep 0.1
    done
    
    local result
    {
        local state
        state=$(read_session_pool_state "$state_path" "$key")
        result=$(eval "$update_script" <<< "$state")
        if [[ -n "$result" ]]; then
            if echo "$result" | jq -e 'has("state") and has("result")' >/dev/null 2>&1; then
                local next_state
                next_state=$(echo "$result" | jq -c '.state')
                write_session_pool_state "$state_path" "$next_state"
                echo "$result" | jq -c '.result'
            elif echo "$result" | jq -e 'has("primary") and has("parallelPool")' >/dev/null 2>&1; then
                write_session_pool_state "$state_path" "$result"
                echo "$result"
            else
                echo "$result"
            fi
        else
            echo "$result"
        fi
    }
    
    flock -u 3
    exec 3>&-
}

acquire_claude_session_lease() {
    local state_path="$1"
    local lock_path="$2"
    local key="$3"
    local mode="$4"
    local run_id="$5"
    local fingerprint="$6"
    local lease_timeout_seconds="$7"
    local wait_seconds="$8"
    local reset_primary="${9:-false}"
    local reset_pool="${10:-false}"
    
    local deadline=$(( $(date +%s) + wait_seconds ))
    
    while true; do
        local lease
        lease=$(
            invoke_session_state_update "$state_path" "$lock_path" "$key" 30 "
                local state=\$(cat)
                local now=\$(date -u +'%Y-%m-%dT%H:%M:%SZ')
                
                if [[ '$reset_primary' == 'true' ]]; then
                    state=\$(echo \"\$state\" | jq '.primary = {
                        sessionId: null,
                        status: \"available\",
                        leaseRunId: null,
                        leasePid: null,
                        leasedAt: null,
                        lastUsedAt: null,
                        lastRunId: null,
                        lastResetAt: null,
                        lastResetReason: null,
                        lastResetFromSessionId: null,
                        lastResetFromRunId: null
                    }')
                fi
                
                if [[ '$reset_pool' == 'true' ]]; then
                    state=\$(echo \"\$state\" | jq '.parallelPool = []')
                fi
                
                local primary
                primary=\$(echo \"\$state\" | jq -c '.primary')
                local expired
                expired=\$(test_lease_expired \"\$primary\" $lease_timeout_seconds)
                
                if [[ \"\$expired\" == 'true' ]]; then
                    echo 'Reclaiming expired primary Claude session lease.' >&2
                    state=\$(echo \"\$state\" | jq '.primary.status = \"available\" | .primary.leaseRunId = null | .primary.leasePid = null | .primary.leasedAt = null')
                fi
                
                local lease_pid
                lease_pid=\$(echo \"\$state\" | jq -r '.primary.leasePid // 0')
                if [[ \"\$lease_pid\" -gt 0 ]] && [[ \$(is_process_alive \"\$lease_pid\") == 'false' ]]; then
                    echo 'Reclaiming primary lease from dead process (PID '\$lease_pid')' >&2
                    state=\$(echo \"\$state\" | jq '.primary.status = \"available\" | .primary.leaseRunId = null | .primary.leasePid = null | .primary.leasedAt = null')
                fi
                
                local pool_count
                pool_count=\$(echo \"\$state\" | jq '.parallelPool | length')
                for ((i=0; i<pool_count; i++)); do
                    local slot
                    slot=\$(echo \"\$state\" | jq -c \".parallelPool[\$i]\")
                    expired=\$(test_lease_expired \"\$slot\" $lease_timeout_seconds)
                    if [[ \"\$expired\" == 'true' ]]; then
                        echo 'Reclaiming expired parallel Claude session lease.' >&2
                        state=\$(echo \"\$state\" | jq \".parallelPool[\$i].status = \\\"available\\\" | .parallelPool[\$i].leaseRunId = null | .parallelPool[\$i].leasePid = null | .parallelPool[\$i].leasedAt = null\")
                    else
                        lease_pid=\$(echo \"\$slot\" | jq -r '.leasePid // 0')
                        if [[ \"\$lease_pid\" -gt 0 ]] && [[ \$(is_process_alive \"\$lease_pid\") == 'false' ]]; then
                            echo 'Reclaiming parallel lease from dead process (PID '\$lease_pid')' >&2
                            state=\$(echo \"\$state\" | jq \".parallelPool[\$i].status = \\\"available\\\" | .parallelPool[\$i].leaseRunId = null | .parallelPool[\$i].leasePid = null | .parallelPool[\$i].leasedAt = null\")
                        fi
                    fi
                done
                
                if [[ '$mode' == 'PrimaryReuse' ]] || [[ '$mode' == 'PrimaryAnchor' ]]; then
                    local primary_status
                    primary_status=\$(echo \"\$state\" | jq -r '.primary.status')
                    if [[ \"\$primary_status\" == 'leased' ]]; then
                        echo 'null'
                        exit 0
                    fi
                    
                    local session_id
                    session_id=\$(echo \"\$state\" | jq -r '.primary.sessionId // empty')
                    local resume='false'
                    if [[ -n \"\$session_id\" ]] && [[ \"\$session_id\" != 'null' ]]; then
                        resume='true'
                    else
                        session_id=\$(new_claude_session_id)
                    fi
                    
                    state=\$(echo \"\$state\" | jq \\
                        --arg sid \"\$session_id\" \\
                        --arg rid '$run_id' \\
                        --arg pid '$$' \\
                        --arg now \"\$now\" \\
                        '.primary.sessionId = \$sid | .primary.status = \"leased\" | .primary.leaseRunId = \$rid | .primary.leasePid = (\$pid | tonumber) | .primary.leasedAt = \$now')
                    
                    jq -n \\
                        --argjson state \"\$state\" \\
                        --arg mode '$mode' \\
                        --arg sid \"\$session_id\" \\
                        --argjson resume \"\$resume\" \\
                        '{state: \$state, result: {mode: \$mode, sessionId: \$sid, resume: \$resume, poolIndex: null, leased: true}}'
                    exit 0
                fi
                
                local available_indices=()
                for ((i=0; i<pool_count; i++)); do
                    local slot_status
                    slot_status=\$(echo \"\$state\" | jq -r \".parallelPool[\$i].status\")
                    if [[ \"\$slot_status\" != 'leased' ]]; then
                        available_indices+=(\$i)
                    fi
                done
                
                local selected_index=''
                for idx in \"\${available_indices[@]}\"; do
                    local slot_fp
                    slot_fp=\$(echo \"\$state\" | jq -r \".parallelPool[\$idx].lastTaskFingerprint // empty\")
                    if [[ \"\$slot_fp\" == '$fingerprint' ]]; then
                        selected_index=\$idx
                        break
                    fi
                done
                
                if [[ -z \"\$selected_index\" ]] && [[ \${#available_indices[@]} -gt 0 ]]; then
                    selected_index=\${available_indices[0]}
                fi
                
                if [[ -z \"\$selected_index\" ]]; then
                    local new_session_id
                    new_session_id=\$(new_claude_session_id)
                    local new_slot
                    new_slot=\$(jq -n \\
                        --arg sid \"\$new_session_id\" \\
                        --arg rid '$run_id' \\
                        --arg pid '$$' \\
                        --arg now \"\$now\" \\
                        --arg fp '$fingerprint' \\
                        '{
                            sessionId: \$sid,
                            status: \"leased\",
                            leaseRunId: \$rid,
                            leasePid: (\$pid | tonumber),
                            leasedAt: \$now,
                            lastUsedAt: null,
                            lastRunId: null,
                            lastTaskFingerprint: \$fp,
                            lastResetAt: null,
                            lastResetReason: null,
                            lastResetFromSessionId: null,
                            lastResetFromRunId: null
                        }')
                    state=\$(echo \"\$state\" | jq --argjson slot \"\$new_slot\" '.parallelPool += [\$slot]')
                    
                    jq -n \\
                        --argjson state \"\$state\" \\
                        --arg mode '$mode' \\
                        --arg sid \"\$new_session_id\" \\
                        --argjson resume false \\
                        --argjson idx \$((pool_count)) \\
                        '{state: \$state, result: {mode: \$mode, sessionId: \$sid, resume: \$resume, poolIndex: \$idx, leased: true}}'
                    exit 0
                fi
                
                local slot
                slot=\$(echo \"\$state\" | jq -c \".parallelPool[\$selected_index]\")
                local session_id
                session_id=\$(echo \"\$slot\" | jq -r '.sessionId // empty')
                local resume='false'
                if [[ -n \"\$session_id\" ]] && [[ \"\$session_id\" != 'null' ]]; then
                    resume='true'
                else
                    session_id=\$(new_claude_session_id)
                fi
                
                state=\$(echo \"\$state\" | jq \\
                    --arg idx \"\$selected_index\" \\
                    --arg sid \"\$session_id\" \\
                    --arg rid '$run_id' \\
                    --arg pid '$$' \\
                    --arg now \"\$now\" \\
                    --arg fp '$fingerprint' \\
                    '.parallelPool[(\$idx | tonumber)].sessionId = \$sid | .parallelPool[(\$idx | tonumber)].status = \"leased\" | .parallelPool[(\$idx | tonumber)].leaseRunId = \$rid | .parallelPool[(\$idx | tonumber)].leasePid = (\$pid | tonumber) | .parallelPool[(\$idx | tonumber)].leasedAt = \$now | .parallelPool[(\$idx | tonumber)].lastTaskFingerprint = \$fp')
                
                jq -n \\
                    --argjson state \"\$state\" \\
                    --arg mode '$mode' \\
                    --arg sid \"\$session_id\" \\
                    --argjson resume \"\$resume\" \\
                    --argjson idx \"\$selected_index\" \\
                    '{state: \$state, result: {mode: \$mode, sessionId: \$sid, resume: \$resume, poolIndex: \$idx, leased: true}}'
            "
        )
        
        if [[ "$lease" != "null" ]] && [[ -n "$lease" ]]; then
            echo "$lease"
            return 0
        fi
        
        if [[ $(date +%s) -ge $deadline ]]; then
            echo "Claude primary session is leased by another delegate. SessionKey: $key. Use a longer wait time or choose ParallelPool." >&2
            return 1
        fi
        
        sleep 0.25
    done
}

release_claude_session_lease() {
    local state_path="$1"
    local lock_path="$2"
    local key="$3"
    local lease="$4"
    local run_id="$5"
    local fingerprint="$6"
    
    if [[ -z "$lease" ]] || [[ "$lease" == "null" ]]; then
        return 0
    fi
    
    local leased
    leased=$(echo "$lease" | jq -r '.leased // false')
    if [[ "$leased" != "true" ]]; then
        return 0
    fi
    
    invoke_session_state_update "$state_path" "$lock_path" "$key" 30 "
        local state=\$(cat)
        local now=\$(date -u +'%Y-%m-%dT%H:%M:%SZ')
        local mode=\$(echo '$lease' | jq -r '.mode')
        local session_id=\$(echo '$lease' | jq -r '.sessionId')
        
        if [[ \"\$mode\" == 'PrimaryReuse' ]] || [[ \"\$mode\" == 'PrimaryAnchor' ]]; then
            local lease_run_id
            lease_run_id=\$(echo \"\$state\" | jq -r '.primary.leaseRunId')
            if [[ \"\$lease_run_id\" == '$run_id' ]]; then
                state=\$(echo \"\$state\" | jq \\
                    --arg now \"\$now\" \\
                    --arg rid '$run_id' \\
                    '.primary.status = \"available\" | .primary.leaseRunId = null | .primary.leasePid = null | .primary.leasedAt = null | .primary.lastUsedAt = \$now | .primary.lastRunId = \$rid')
            fi
            echo \"\$state\"
            exit 0
        fi
        
        if [[ \"\$mode\" == 'ParallelPool' ]]; then
            local pool_count
            pool_count=\$(echo \"\$state\" | jq '.parallelPool | length')
            for ((i=0; i<pool_count; i++)); do
                local slot_sid
                slot_sid=\$(echo \"\$state\" | jq -r \".parallelPool[\$i].sessionId\")
                local slot_rid
                slot_rid=\$(echo \"\$state\" | jq -r \".parallelPool[\$i].leaseRunId\")
                if [[ \"\$slot_sid\" == \"\$session_id\" ]] && [[ \"\$slot_rid\" == '$run_id' ]]; then
                    state=\$(echo \"\$state\" | jq \\
                        --arg idx \"\$i\" \\
                        --arg now \"\$now\" \\
                        --arg rid '$run_id' \\
                        --arg fp '$fingerprint' \\
                        '.parallelPool[(\$idx | tonumber)].status = \"available\" | .parallelPool[(\$idx | tonumber)].leaseRunId = null | .parallelPool[(\$idx | tonumber)].leasePid = null | .parallelPool[(\$idx | tonumber)].leasedAt = null | .parallelPool[(\$idx | tonumber)].lastUsedAt = \$now | .parallelPool[(\$idx | tonumber)].lastRunId = \$rid | .parallelPool[(\$idx | tonumber)].lastTaskFingerprint = \$fp')
                    break
                fi
            done
            echo \"\$state\"
        fi
    " >/dev/null
}

reset_claude_session_lease_for_fresh_session() {
    local state_path="$1"
    local lock_path="$2"
    local key="$3"
    local lease="$4"
    local run_id="$5"
    local fingerprint="$6"
    local reason="${7:-fresh_session_retry}"
    
    if [[ -z "$lease" ]] || [[ "$lease" == "null" ]]; then
        echo "Cannot reset a Claude session lease that is not currently leased." >&2
        return 1
    fi
    
    local leased
    leased=$(echo "$lease" | jq -r '.leased // false')
    if [[ "$leased" != "true" ]]; then
        echo "Cannot reset a Claude session lease that is not currently leased." >&2
        return 1
    fi
    
    invoke_session_state_update "$state_path" "$lock_path" "$key" 30 "
        local state=\$(cat)
        local now=\$(date -u +'%Y-%m-%dT%H:%M:%SZ')
        local mode=\$(echo '$lease' | jq -r '.mode')
        local old_session_id=\$(echo '$lease' | jq -r '.sessionId')
        local new_session_id=\$(new_claude_session_id)
        
        if [[ \"\$mode\" == 'PrimaryReuse' ]] || [[ \"\$mode\" == 'PrimaryAnchor' ]]; then
            local lease_run_id
            lease_run_id=\$(echo \"\$state\" | jq -r '.primary.leaseRunId')
            if [[ \"\$lease_run_id\" != '$run_id' ]]; then
                echo \"Cannot reset primary Claude session lease; expected run '$run_id' but found '\$lease_run_id'.\" >&2
                exit 1
            fi
            
            state=\$(echo \"\$state\" | jq \\
                --arg sid \"\$new_session_id\" \\
                --arg rid '$run_id' \\
                --arg now \"\$now\" \\
                --arg reason '$reason' \\
                --arg old_sid \"\$old_session_id\" \\
                --arg old_rid '$run_id' \\
                '.primary.sessionId = \$sid | .primary.status = \"leased\" | .primary.leaseRunId = \$rid | .primary.leasedAt = \$now | .primary.lastUsedAt = null | .primary.lastRunId = null | .primary.lastResetAt = \$now | .primary.lastResetReason = \$reason | .primary.lastResetFromSessionId = \$old_sid | .primary.lastResetFromRunId = \$old_rid')
            
            jq -n \\
                --argjson state \"\$state\" \\
                --arg mode \"\$mode\" \\
                --arg sid \"\$new_session_id\" \\
                '{state: \$state, result: {mode: \$mode, sessionId: \$sid, resume: false, poolIndex: null, leased: true}}'
            exit 0
        fi
        
        if [[ \"\$mode\" == 'ParallelPool' ]]; then
            local pool_count
            pool_count=\$(echo \"\$state\" | jq '.parallelPool | length')
            for ((i=0; i<pool_count; i++)); do
                local slot_sid
                slot_sid=\$(echo \"\$state\" | jq -r \".parallelPool[\$i].sessionId\")
                local slot_rid
                slot_rid=\$(echo \"\$state\" | jq -r \".parallelPool[\$i].leaseRunId\")
                if [[ \"\$slot_sid\" == \"\$old_session_id\" ]] && [[ \"\$slot_rid\" == '$run_id' ]]; then
                    state=\$(echo \"\$state\" | jq \\
                        --arg idx \"\$i\" \\
                        --arg sid \"\$new_session_id\" \\
                        --arg rid '$run_id' \\
                        --arg now \"\$now\" \\
                        --arg fp '$fingerprint' \\
                        --arg reason '$reason' \\
                        --arg old_sid \"\$old_session_id\" \\
                        --arg old_rid '$run_id' \\
                        '.parallelPool[(\$idx | tonumber)].sessionId = \$sid | .parallelPool[(\$idx | tonumber)].status = \"leased\" | .parallelPool[(\$idx | tonumber)].leaseRunId = \$rid | .parallelPool[(\$idx | tonumber)].leasedAt = \$now | .parallelPool[(\$idx | tonumber)].lastUsedAt = null | .parallelPool[(\$idx | tonumber)].lastRunId = null | .parallelPool[(\$idx | tonumber)].lastTaskFingerprint = \$fp | .parallelPool[(\$idx | tonumber)].lastResetAt = \$now | .parallelPool[(\$idx | tonumber)].lastResetReason = \$reason | .parallelPool[(\$idx | tonumber)].lastResetFromSessionId = \$old_sid | .parallelPool[(\$idx | tonumber)].lastResetFromRunId = \$old_rid')
                    
                    jq -n \\
                        --argjson state \"\$state\" \\
                        --arg mode \"\$mode\" \\
                        --arg sid \"\$new_session_id\" \\
                        --argjson idx \"\$i\" \\
                        '{state: \$state, result: {mode: \$mode, sessionId: \$sid, resume: false, poolIndex: \$idx, leased: true}}'
                    exit 0
                fi
            done
            
            echo \"Cannot reset parallel Claude session lease for run '$run_id'; the leased session was not found.\" >&2
            exit 1
        fi
        
        echo \"Unsupported Claude session mode for reset: \$mode\" >&2
        exit 1
    "
}
