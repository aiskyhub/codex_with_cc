#!/usr/bin/env bash
set -euo pipefail

EXPECTED_ARTIFACT_SCHEMA=2
EXPECTED_INVOCATION_CONTRACT='spawn_agent_child_only'
EXPECTED_CHILD_THREAD_MARKER_NAME='CODEX_CLAUDE_CHILD_THREAD'

RUN_ID=""
ARTIFACT_ROOT=""

usage() {
    cat <<EOF
Usage: $0 -r RUN_ID -a ARTIFACT_ROOT

Options:
  -r, --run-id RUN_ID       Run ID to verify
  -a, --artifact-root PATH  Artifact root directory
  -h, --help                Show this help message
EOF
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        -r|--run-id)
            RUN_ID="$2"
            shift 2
            ;;
        -a|--artifact-root)
            ARTIFACT_ROOT="$2"
            shift 2
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            echo "Unknown option: $1" >&2
            usage >&2
            exit 1
            ;;
    esac
done

if [[ -z "$RUN_ID" ]]; then
    echo "RunId is required." >&2
    exit 1
fi

if [[ -z "$ARTIFACT_ROOT" ]]; then
    echo "ArtifactRoot is required." >&2
    exit 1
fi

STATUS_PATH="$ARTIFACT_ROOT/status_${RUN_ID}.json"
CONFIG_PATH="$ARTIFACT_ROOT/config_${RUN_ID}.json"
OUTPUT_PATH="$ARTIFACT_ROOT/claude_${RUN_ID}.md"
RAW_STREAM_PATH="$ARTIFACT_ROOT/stream_${RUN_ID}.jsonl"
TRACE_PATH="$ARTIFACT_ROOT/trace_${RUN_ID}.log"
PROMPT_PATH="$ARTIFACT_ROOT/prompt_${RUN_ID}.md"

if [[ ! -f "$STATUS_PATH" ]]; then
    echo "Missing status file: $STATUS_PATH" >&2
    exit 1
fi

if [[ ! -f "$CONFIG_PATH" ]]; then
    echo "Missing config file: $CONFIG_PATH" >&2
    exit 1
fi

if [[ ! -f "$OUTPUT_PATH" ]]; then
    echo "Missing output file: $OUTPUT_PATH" >&2
    exit 1
fi

STATUS=$(cat "$STATUS_PATH")
CONFIG=$(cat "$CONFIG_PATH")

has_json_field() {
    local json="$1"
    local field="$2"
    echo "$json" | jq -e ".${field}" >/dev/null 2>&1
}

ARTIFACT_SCHEMA_STATUS=$(echo "$STATUS" | jq -r '.artifactSchema // 0')
ARTIFACT_SCHEMA_CONFIG=$(echo "$CONFIG" | jq -r '.artifactSchema // 0')

if ! has_json_field "$STATUS" "artifactSchema" || ! has_json_field "$STATUS" "invocationContract" || \
   ! has_json_field "$CONFIG" "artifactSchema" || ! has_json_field "$CONFIG" "invocationContract"; then
    echo "Legacy delegate artifact is unsupported; rerun with current spawn_agent-based flow." >&2
    exit 1
fi

if [[ "$ARTIFACT_SCHEMA_STATUS" != "$EXPECTED_ARTIFACT_SCHEMA" ]] || \
   [[ "$ARTIFACT_SCHEMA_CONFIG" != "$EXPECTED_ARTIFACT_SCHEMA" ]]; then
    echo "Unexpected delegate artifact schema. Expected $EXPECTED_ARTIFACT_SCHEMA." >&2
    exit 1
fi

INVOCATION_CONTRACT_STATUS=$(echo "$STATUS" | jq -r '.invocationContract // ""')
INVOCATION_CONTRACT_CONFIG=$(echo "$CONFIG" | jq -r '.invocationContract // ""')

if [[ "$INVOCATION_CONTRACT_STATUS" != "$EXPECTED_INVOCATION_CONTRACT" ]] || \
   [[ "$INVOCATION_CONTRACT_CONFIG" != "$EXPECTED_INVOCATION_CONTRACT" ]]; then
    echo "Unexpected invocation contract. Expected '$EXPECTED_INVOCATION_CONTRACT'." >&2
    exit 1
fi

CHILD_THREAD_MARKER_NAME_STATUS=$(echo "$STATUS" | jq -r '.childThreadMarkerName // ""')
CHILD_THREAD_MARKER_NAME_CONFIG=$(echo "$CONFIG" | jq -r '.childThreadMarkerName // ""')
CHILD_THREAD_MARKER_VALIDATED_STATUS=$(echo "$STATUS" | jq -r '.childThreadMarkerValidated // false')
CHILD_THREAD_MARKER_VALIDATED_CONFIG=$(echo "$CONFIG" | jq -r '.childThreadMarkerValidated // false')

if ! has_json_field "$STATUS" "childThreadMarkerName" || ! has_json_field "$CONFIG" "childThreadMarkerName"; then
    echo "Delegate artifact is missing child-thread marker metadata." >&2
    exit 1
fi

if [[ "$CHILD_THREAD_MARKER_NAME_STATUS" != "$EXPECTED_CHILD_THREAD_MARKER_NAME" ]] || \
   [[ "$CHILD_THREAD_MARKER_NAME_CONFIG" != "$EXPECTED_CHILD_THREAD_MARKER_NAME" ]]; then
    echo "Missing or incorrect childThreadMarkerName." >&2
    exit 1
fi

if ! has_json_field "$STATUS" "childThreadMarkerValidated" || ! has_json_field "$CONFIG" "childThreadMarkerValidated"; then
    echo "Delegate artifact is missing child-thread validation state." >&2
    exit 1
fi

if [[ "$CHILD_THREAD_MARKER_VALIDATED_STATUS" != "true" ]] || \
   [[ "$CHILD_THREAD_MARKER_VALIDATED_CONFIG" != "true" ]]; then
    echo "childThreadMarkerValidated must be true." >&2
    exit 1
fi

CONFIG_OUTPUT_PATH=$(echo "$CONFIG" | jq -r '.outputPath // ""')
STATUS_OUTPUT_PATH=$(echo "$STATUS" | jq -r '.outputPath // ""')

if [[ "$CONFIG_OUTPUT_PATH" != "$OUTPUT_PATH" ]]; then
    echo "Config outputPath mismatch. Expected: $OUTPUT_PATH ; Actual: $CONFIG_OUTPUT_PATH" >&2
    exit 1
fi
if [[ "$STATUS_OUTPUT_PATH" != "$OUTPUT_PATH" ]]; then
    echo "Status outputPath mismatch. Expected: $OUTPUT_PATH ; Actual: $STATUS_OUTPUT_PATH" >&2
    exit 1
fi

DELEGATE_STATUS=$(echo "$STATUS" | jq -r '.status // ""')

if [[ "$DELEGATE_STATUS" != "completed" ]] && [[ "$DELEGATE_STATUS" != "failed" ]]; then
    echo "Delegate status must be 'completed' or 'failed'. Current: $DELEGATE_STATUS" >&2
    exit 1
fi

IS_COMPLETED="false"
IS_STRUCTURED_FAILURE="false"
if [[ "$DELEGATE_STATUS" == "completed" ]]; then
    IS_COMPLETED="true"
elif [[ "$DELEGATE_STATUS" == "failed" ]]; then
    IS_STRUCTURED_FAILURE="true"
fi

OUTPUT_CONTENT=$(cat "$OUTPUT_PATH")
if [[ "$OUTPUT_CONTENT" != *"Final Result"* ]]; then
    echo "Output file must contain 'Final Result' heading." >&2
    exit 1
fi

EXIT_CODE=$(echo "$STATUS" | jq -r '.exitCode // 0')
if [[ "$IS_COMPLETED" == "true" ]] && [[ "$EXIT_CODE" != "0" ]]; then
    echo "Completed delegate exitCode is not zero: $EXIT_CODE" >&2
    exit 1
fi
if [[ "$IS_STRUCTURED_FAILURE" == "true" ]] && [[ "$EXIT_CODE" == "0" ]]; then
    echo "Structured failed delegate must record a non-zero exitCode." >&2
    exit 1
fi

if ! has_json_field "$STATUS" "attempts"; then
    echo "Delegate status is missing attempts[] audit data." >&2
    exit 1
fi

if ! has_json_field "$CONFIG" "sessionMode"; then
    echo "Delegate config is missing sessionMode." >&2
    exit 1
fi
if ! has_json_field "$CONFIG" "sessionKey"; then
    echo "Delegate config is missing sessionKey." >&2
    exit 1
fi

ATTEMPTS=$(echo "$STATUS" | jq -c '.attempts // []')
ATTEMPTS_LENGTH=$(echo "$ATTEMPTS" | jq 'length')

STATUS_ATTEMPT_COUNT=$(echo "$STATUS" | jq -r '.attemptCount // 0')
STATUS_RETRY_COUNT=$(echo "$STATUS" | jq -r '.retryCount // 0')
CONFIG_ATTEMPT_COUNT=$(echo "$CONFIG" | jq -r '.attemptCount // 0')
CONFIG_RETRY_COUNT=$(echo "$CONFIG" | jq -r '.retryCount // 0')

if [[ $ATTEMPTS_LENGTH -ne $STATUS_ATTEMPT_COUNT ]]; then
    echo "Delegate attempts[] count mismatch. attempts=$ATTEMPTS_LENGTH status.attemptCount=$STATUS_ATTEMPT_COUNT" >&2
    exit 1
fi

if [[ $STATUS_ATTEMPT_COUNT -lt 1 ]]; then
    echo "Delegate attemptCount must be >= 1. Current: $STATUS_ATTEMPT_COUNT" >&2
    exit 1
fi

if [[ $CONFIG_ATTEMPT_COUNT -ne $STATUS_ATTEMPT_COUNT ]]; then
    echo "Config/status attemptCount mismatch. config=$CONFIG_ATTEMPT_COUNT status=$STATUS_ATTEMPT_COUNT" >&2
    exit 1
fi

if [[ $CONFIG_RETRY_COUNT -ne $STATUS_RETRY_COUNT ]]; then
    echo "Config/status retryCount mismatch. config=$CONFIG_RETRY_COUNT status=$STATUS_RETRY_COUNT" >&2
    exit 1
fi

if [[ $STATUS_RETRY_COUNT -gt $MAX_RETRY_COUNT ]]; then
    MAX_RETRY_COUNT=$(echo "$STATUS" | jq -r '.maxRetryCount // 0')
    echo "Delegate retryCount ($STATUS_RETRY_COUNT) cannot exceed maxRetryCount ($MAX_RETRY_COUNT)." >&2
    exit 1
fi

if [[ "$IS_STRUCTURED_FAILURE" == "true" ]]; then
    for prop in failureDisposition failureSummary maxRetryCount; do
        if ! has_json_field "$STATUS" "$prop"; then
            echo "Structured failed delegate status is missing '$prop'." >&2
            exit 1
        fi
        if ! has_json_field "$CONFIG" "$prop"; then
            echo "Structured failed delegate config is missing '$prop'." >&2
            exit 1
        fi
    done

    FAILURE_DISPOSITION_STATUS=$(echo "$STATUS" | jq -r '.failureDisposition // ""')
    FAILURE_DISPOSITION_CONFIG=$(echo "$CONFIG" | jq -r '.failureDisposition // ""')

    if [[ "$FAILURE_DISPOSITION_STATUS" != "NEED_HUMAN_INTERVENTION" ]]; then
        echo "Structured failed delegate must set failureDisposition to 'NEED_HUMAN_INTERVENTION'. Actual: $FAILURE_DISPOSITION_STATUS" >&2
        exit 1
    fi
    if [[ "$FAILURE_DISPOSITION_CONFIG" != "$FAILURE_DISPOSITION_STATUS" ]]; then
        echo "Structured failed delegate failureDisposition must match between config and status." >&2
        exit 1
    fi

    FAILURE_SUMMARY=$(echo "$STATUS" | jq -r '.failureSummary // ""')
    FAILURE_SUMMARY_CONFIG=$(echo "$CONFIG" | jq -r '.failureSummary // ""')
    if [[ -z "$FAILURE_SUMMARY" ]]; then
        echo "Structured failed delegate must record a non-empty failureSummary." >&2
        exit 1
    fi
    if [[ "$FAILURE_SUMMARY_CONFIG" != "$FAILURE_SUMMARY" ]]; then
        echo "Structured failed delegate failureSummary must match between config and status." >&2
        exit 1
    fi

    CONFIG_MAX_RETRY=$(echo "$CONFIG" | jq -r '.maxRetryCount // 0')
    STATUS_MAX_RETRY=$(echo "$STATUS" | jq -r '.maxRetryCount // 0')
    if [[ "$CONFIG_MAX_RETRY" != "$STATUS_MAX_RETRY" ]]; then
        echo "Structured failed delegate maxRetryCount must match between config and status." >&2
        exit 1
    fi
fi

RECORDED_RETRY_REASONS=0
RECORDED_RETRY_REASONS=$(echo "$ATTEMPTS" | jq '[.[] | select(.retryReason != null and .retryReason != "")] | length')
ATTEMPT_PROPERTIES=("attempt" "sessionId" "resume" "retryReason" "exitCode" "sawAssistantText" "sawResultSuccess" "capturedFinalResult")

for ((i=0; i<ATTEMPTS_LENGTH; i++)); do
    for prop in "${ATTEMPT_PROPERTIES[@]}"; do
        if ! echo "$ATTEMPTS" | jq -e ".[$i].${prop}" >/dev/null 2>&1; then
            echo "Delegate attempt[$i] is missing '$prop'." >&2
            exit 1
        fi
    done

    ATTEMPT_NUM=$(echo "$ATTEMPTS" | jq -r ".[$i].attempt")
    if [[ "$ATTEMPT_NUM" -ne $((i + 1)) ]]; then
        echo "Delegate attempt numbering is not sequential at index $i. Expected $((i + 1)) but found $ATTEMPT_NUM." >&2
        exit 1
    fi
done

if [[ $RECORDED_RETRY_REASONS -ne $STATUS_RETRY_COUNT ]]; then
    echo "Delegate retry count mismatch. attempts-with-retryReason=$RECORDED_RETRY_REASONS status.retryCount=$STATUS_RETRY_COUNT" >&2
    exit 1
fi

if [[ $ATTEMPTS_LENGTH -gt 0 ]]; then
    FIRST_ATTEMPT=$(echo "$ATTEMPTS" | jq -c '.[0]')
    FINAL_ATTEMPT=$(echo "$ATTEMPTS" | jq -c ".[$((ATTEMPTS_LENGTH - 1))]")

    if ! has_json_field "$CONFIG" "initialSessionId"; then
        echo "Delegate config is missing initialSessionId." >&2
        exit 1
    fi
    if ! has_json_field "$CONFIG" "initialResume"; then
        echo "Delegate config is missing initialResume." >&2
        exit 1
    fi

    CONFIG_INITIAL_SESSION_ID=$(echo "$CONFIG" | jq -r '.initialSessionId // ""')
    FIRST_ATTEMPT_SESSION_ID=$(echo "$FIRST_ATTEMPT" | jq -r '.sessionId // ""')
    if [[ "$CONFIG_INITIAL_SESSION_ID" != "$FIRST_ATTEMPT_SESSION_ID" ]]; then
        echo "Config initialSessionId mismatch. Expected first attempt session $FIRST_ATTEMPT_SESSION_ID but found $CONFIG_INITIAL_SESSION_ID" >&2
        exit 1
    fi

    CONFIG_INITIAL_RESUME=$(echo "$CONFIG" | jq -r '.initialResume // false')
    FIRST_ATTEMPT_RESUME=$(echo "$FIRST_ATTEMPT" | jq -r '.resume // false')
    if [[ "$CONFIG_INITIAL_RESUME" != "$FIRST_ATTEMPT_RESUME" ]]; then
        echo "Config initialResume mismatch. Expected first attempt resume $FIRST_ATTEMPT_RESUME but found $CONFIG_INITIAL_RESUME" >&2
        exit 1
    fi

    CONFIG_SESSION_ID=$(echo "$CONFIG" | jq -r '.sessionId // ""')
    FINAL_ATTEMPT_SESSION_ID=$(echo "$FINAL_ATTEMPT" | jq -r '.sessionId // ""')
    if [[ -n "$CONFIG_SESSION_ID" ]] && [[ "$CONFIG_SESSION_ID" != "$FINAL_ATTEMPT_SESSION_ID" ]]; then
        echo "Config final sessionId mismatch. Expected final attempt session $FINAL_ATTEMPT_SESSION_ID but found $CONFIG_SESSION_ID" >&2
        exit 1
    fi

    CONFIG_RESUME=$(echo "$CONFIG" | jq -r '.resume // ""')
    FINAL_ATTEMPT_RESUME=$(echo "$FINAL_ATTEMPT" | jq -r '.resume // false')
    if [[ -n "$CONFIG_RESUME" ]] && [[ "$CONFIG_RESUME" != "$FINAL_ATTEMPT_RESUME" ]]; then
        echo "Config final resume mismatch. Expected final attempt resume $FINAL_ATTEMPT_RESUME but found $CONFIG_RESUME" >&2
        exit 1
    fi

    FINAL_ATTEMPT_EXIT_CODE=$(echo "$FINAL_ATTEMPT" | jq -r '.exitCode // 0')
    if [[ "$FINAL_ATTEMPT_EXIT_CODE" != "$EXIT_CODE" ]]; then
        echo "Final attempt exitCode mismatch. Expected $EXIT_CODE but found $FINAL_ATTEMPT_EXIT_CODE" >&2
        exit 1
    fi

    if [[ "$IS_COMPLETED" == "true" ]]; then
        SAW_RESULT_SUCCESS=$(echo "$FINAL_ATTEMPT" | jq -r '.sawResultSuccess // false')
        if [[ "$SAW_RESULT_SUCCESS" != "true" ]]; then
            echo "Completed delegate must record sawResultSuccess=true on the final attempt." >&2
            exit 1
        fi
        CAPTURED_FINAL_RESULT=$(echo "$FINAL_ATTEMPT" | jq -r '.capturedFinalResult // false')
        if [[ "$CAPTURED_FINAL_RESULT" != "true" ]]; then
            echo "Completed delegate must record capturedFinalResult=true on the final attempt." >&2
            exit 1
        fi
    fi

    if [[ "$IS_STRUCTURED_FAILURE" == "true" ]]; then
        CAPTURED_FINAL_RESULT=$(echo "$FINAL_ATTEMPT" | jq -r '.capturedFinalResult // false')
        if [[ "$CAPTURED_FINAL_RESULT" != "true" ]]; then
            echo "Structured failed delegate must record capturedFinalResult=true on the final attempt." >&2
            exit 1
        fi
    fi
fi

OPTIONAL_PATHS=()
for prop in rawStreamPath tracePath promptPath; do
    CONFIG_VAL=$(echo "$CONFIG" | jq -r ".$prop // \"\"" 2>/dev/null || echo "")
    if [[ -n "$CONFIG_VAL" ]] && [[ "$CONFIG_VAL" != "null" ]]; then
        OPTIONAL_PATHS+=("$CONFIG_VAL")
    fi
    STATUS_VAL=$(echo "$STATUS" | jq -r ".$prop // \"\"" 2>/dev/null || echo "")
    if [[ -n "$STATUS_VAL" ]] && [[ "$STATUS_VAL" != "null" ]]; then
        OPTIONAL_PATHS+=("$STATUS_VAL")
    fi
done

if [[ ${#OPTIONAL_PATHS[@]} -gt 0 ]]; then
    readarray -t UNIQUE_PATHS < <(printf '%s\n' "${OPTIONAL_PATHS[@]}" | sort -u)
    for path in "${UNIQUE_PATHS[@]}"; do
        if [[ ! -f "$path" ]]; then
            echo "Referenced artifact path is missing: $path" >&2
            exit 1
        fi
    done
fi

if [[ ! -f "$RAW_STREAM_PATH" ]]; then
    echo "Missing raw stream file: $RAW_STREAM_PATH" >&2
    exit 1
fi

if [[ ! -f "$TRACE_PATH" ]]; then
    echo "Missing trace file: $TRACE_PATH" >&2
    exit 1
fi

SESSION_STATE_PATH=$(echo "$CONFIG" | jq -r '.sessionStatePath // ""')
SESSION_KEY=$(echo "$CONFIG" | jq -r '.sessionKey // ""')
SESSION_MODE=$(echo "$CONFIG" | jq -r '.sessionMode // ""')

if [[ -n "$SESSION_STATE_PATH" ]] && [[ -f "$SESSION_STATE_PATH" ]]; then
    SESSION_STATE=$(cat "$SESSION_STATE_PATH")

    if echo "$SESSION_STATE" | jq -e '.primary' >/dev/null 2>&1; then
        PRIMARY_LEASE_RUN_ID=$(echo "$SESSION_STATE" | jq -r '.primary.leaseRunId // ""')
        if [[ "$PRIMARY_LEASE_RUN_ID" == "$RUN_ID" ]]; then
            echo "Primary session lease is still held by run $RUN_ID." >&2
            exit 1
        fi
    fi

    if echo "$SESSION_STATE" | jq -e '.parallelPool' >/dev/null 2>&1; then
        POOL_COUNT=$(echo "$SESSION_STATE" | jq '.parallelPool | length')
        for ((i=0; i<POOL_COUNT; i++)); do
            SLOT_LEASE_RUN_ID=$(echo "$SESSION_STATE" | jq -r ".parallelPool[$i].leaseRunId // \"\"")
            if [[ "$SLOT_LEASE_RUN_ID" == "$RUN_ID" ]]; then
                echo "Parallel session lease is still held by run $RUN_ID." >&2
                exit 1
            fi
        done
    fi
fi

echo "Delegate artifacts verified successfully for run $RUN_ID."
echo "Status: $DELEGATE_STATUS"
echo "Attempts: $STATUS_ATTEMPT_COUNT"
echo "Retries: $STATUS_RETRY_COUNT"
echo "Output: $OUTPUT_PATH"
