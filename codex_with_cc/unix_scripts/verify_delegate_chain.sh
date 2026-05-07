#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VERIFY_ARTIFACTS_SCRIPT="$SCRIPT_DIR/verify_delegate_artifacts.sh"

ANCHOR_RUN_ID=""
PARALLEL_RUN_IDS=()
REUSE_RUN_IDS=()
ARTIFACT_ROOT=""
SESSION_KEY=""

usage() {
    cat <<EOF
Usage: $0 [OPTIONS]

Options:
  --anchor-run-id RUN_ID      Anchor run ID
  --parallel-run-ids IDS      Parallel run IDs (comma-separated)
  --reuse-run-ids IDS         Reuse run IDs (comma-separated)
  -a, --artifact-root PATH    Artifact root directory
  --session-key KEY           Session key for session state verification
  -h, --help                  Show this help message
EOF
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --anchor-run-id)
            ANCHOR_RUN_ID="$2"
            shift 2
            ;;
        --parallel-run-ids)
            IFS=',;' read -ra PARTS <<< "$2"
            PARALLEL_RUN_IDS=("${PARTS[@]}")
            shift 2
            ;;
        --reuse-run-ids)
            IFS=',;' read -ra PARTS <<< "$2"
            REUSE_RUN_IDS=("${PARTS[@]}")
            shift 2
            ;;
        -a|--artifact-root)
            ARTIFACT_ROOT="$2"
            shift 2
            ;;
        --session-key)
            SESSION_KEY="$2"
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

if [[ -z "$ARTIFACT_ROOT" ]]; then
    echo "ArtifactRoot is required." >&2
    exit 1
fi

ALL_RUN_IDS=()
if [[ -n "$ANCHOR_RUN_ID" ]]; then
    ALL_RUN_IDS+=("$ANCHOR_RUN_ID")
fi
for rid in "${PARALLEL_RUN_IDS[@]}"; do
    if [[ -n "$rid" ]]; then
        ALL_RUN_IDS+=("$rid")
    fi
done
for rid in "${REUSE_RUN_IDS[@]}"; do
    if [[ -n "$rid" ]]; then
        ALL_RUN_IDS+=("$rid")
    fi
done

if [[ ${#ALL_RUN_IDS[@]} -eq 0 ]]; then
    echo "At least one run ID is required." >&2
    exit 1
fi

echo "Verifying ${#ALL_RUN_IDS[@]} delegate run(s)..."

for RUN_ID in "${ALL_RUN_IDS[@]}"; do
    echo "Verifying run: $RUN_ID"
    bash "$VERIFY_ARTIFACTS_SCRIPT" -r "$RUN_ID" -a "$ARTIFACT_ROOT"
done

if [[ -n "$ANCHOR_RUN_ID" ]]; then
    ANCHOR_CONFIG_PATH="$ARTIFACT_ROOT/config_${ANCHOR_RUN_ID}.json"
    if [[ -f "$ANCHOR_CONFIG_PATH" ]]; then
        ANCHOR_CONFIG=$(cat "$ANCHOR_CONFIG_PATH")
        ANCHOR_SESSION_MODE=$(echo "$ANCHOR_CONFIG" | jq -r '.sessionMode // ""')
        ANCHOR_SESSION_KEY=$(echo "$ANCHOR_CONFIG" | jq -r '.sessionKey // ""')
        
        if [[ "$ANCHOR_SESSION_MODE" != "PrimaryAnchor" ]]; then
            echo "Anchor run must use PrimaryAnchor session mode. Found: $ANCHOR_SESSION_MODE" >&2
            exit 1
        fi
        
        if [[ -n "$SESSION_KEY" ]] && [[ "$ANCHOR_SESSION_KEY" != "$SESSION_KEY" ]]; then
            echo "Anchor run session key mismatch. Expected: $SESSION_KEY, Found: $ANCHOR_SESSION_KEY" >&2
            exit 1
        fi
        
        echo "Anchor run verified: sessionMode=$ANCHOR_SESSION_MODE, sessionKey=$ANCHOR_SESSION_KEY"
    fi
fi

for RID in "${PARALLEL_RUN_IDS[@]}"; do
    if [[ -z "$RID" ]]; then
        continue
    fi
    
    PARALLEL_CONFIG_PATH="$ARTIFACT_ROOT/config_${RID}.json"
    if [[ -f "$PARALLEL_CONFIG_PATH" ]]; then
        PARALLEL_CONFIG=$(cat "$PARALLEL_CONFIG_PATH")
        PARALLEL_SESSION_MODE=$(echo "$PARALLEL_CONFIG" | jq -r '.sessionMode // ""')
        
        if [[ "$PARALLEL_SESSION_MODE" != "ParallelPool" ]]; then
            echo "Parallel run must use ParallelPool session mode. Found: $PARALLEL_SESSION_MODE" >&2
            exit 1
        fi
        
        echo "Parallel run verified: sessionMode=$PARALLEL_SESSION_MODE"
    fi
done

for RID in "${REUSE_RUN_IDS[@]}"; do
    if [[ -z "$RID" ]]; then
        continue
    fi
    
    REUSE_CONFIG_PATH="$ARTIFACT_ROOT/config_${RID}.json"
    if [[ -f "$REUSE_CONFIG_PATH" ]]; then
        REUSE_CONFIG=$(cat "$REUSE_CONFIG_PATH")
        REUSE_SESSION_MODE=$(echo "$REUSE_CONFIG" | jq -r '.sessionMode // ""')
        REUSE_INITIAL_RESUME=$(echo "$REUSE_CONFIG" | jq -r '.initialResume // false')
        
        if [[ "$REUSE_SESSION_MODE" != "PrimaryReuse" ]]; then
            echo "Reuse run must use PrimaryReuse session mode. Found: $REUSE_SESSION_MODE" >&2
            exit 1
        fi
        
        if [[ "$REUSE_INITIAL_RESUME" != "true" ]]; then
            REUSE_STATUS_PATH="$ARTIFACT_ROOT/status_${RID}.json"
            if [[ -f "$REUSE_STATUS_PATH" ]]; then
                REUSE_STATUS=$(cat "$REUSE_STATUS_PATH")
                ATTEMPTS=$(echo "$REUSE_STATUS" | jq -r '.attempts // []')
                FIRST_ATTEMPT_RESUME=$(echo "$ATTEMPTS" | jq -r '.[0].resume // false')
                
                if [[ "$FIRST_ATTEMPT_RESUME" != "true" ]]; then
                    echo "Reuse run should attempt resume=true on first attempt (or after stale session reset)." >&2
                fi
            fi
        fi
        
        echo "Reuse run verified: sessionMode=$REUSE_SESSION_MODE, initialResume=$REUSE_INITIAL_RESUME"
    fi
done

if [[ -n "$SESSION_KEY" ]]; then
    SESSION_STATE_PATH="$ARTIFACT_ROOT/session-pools/$SESSION_KEY.json"
    
    if [[ -f "$SESSION_STATE_PATH" ]]; then
        SESSION_STATE=$(cat "$SESSION_STATE_PATH")
        
        PRIMARY_STATUS=$(echo "$SESSION_STATE" | jq -r '.primary.status // ""')
        if [[ "$PRIMARY_STATUS" != "available" ]]; then
            echo "Primary session must be 'available' after chain completion. Found: $PRIMARY_STATUS" >&2
            exit 1
        fi
        
        POOL_COUNT=$(echo "$SESSION_STATE" | jq '.parallelPool | length')
        for ((i=0; i<POOL_COUNT; i++)); do
            SLOT_STATUS=$(echo "$SESSION_STATE" | jq -r ".parallelPool[$i].status // \"\"")
            if [[ "$SLOT_STATUS" != "available" ]]; then
                echo "Parallel pool slot $i must be 'available' after chain completion. Found: $SLOT_STATUS" >&2
                exit 1
            fi
        done
        
        echo "Session state verified: primary=$PRIMARY_STATUS, parallelPool slots=$POOL_COUNT"
    fi
fi

echo "Delegate chain verification passed."
echo "Total runs verified: ${#ALL_RUN_IDS[@]}"
if [[ -n "$ANCHOR_RUN_ID" ]]; then
    echo "  Anchor: $ANCHOR_RUN_ID"
fi
if [[ ${#PARALLEL_RUN_IDS[@]} -gt 0 ]]; then
    echo "  Parallel: ${PARALLEL_RUN_IDS[*]}"
fi
if [[ ${#REUSE_RUN_IDS[@]} -gt 0 ]]; then
    echo "  Reuse: ${REUSE_RUN_IDS[*]}"
fi
