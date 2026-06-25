#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  tools/jammini_watchdog.sh --status [--conversation-id <id>]
  tools/jammini_watchdog.sh --queue-status [--conversation-id <id>]
  tools/jammini_watchdog.sh --ack-probe [--conversation-id <id>] [--timeout-seconds <n>]
  tools/jammini_watchdog.sh --handoff-probe [--conversation-id <id>] [--timeout-seconds <n>]
  tools/jammini_watchdog.sh --once [--conversation-id <id>] [--idle-minutes <n>] [--cooldown-minutes <n>] [--dry-run]
  tools/jammini_watchdog.sh --watch [--conversation-id <id>] [--idle-minutes <n>] [--cooldown-minutes <n>] [--interval-seconds <n>] [--dry-run]

Examples:
  tools/jammini_watchdog.sh --status
  tools/jammini_watchdog.sh --queue-status
  tools/jammini_watchdog.sh --ack-probe
  tools/jammini_watchdog.sh --handoff-probe
  tools/jammini_watchdog.sh --once --dry-run
  tools/jammini_watchdog.sh --watch --interval-seconds 900
EOF
}

script_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
workspace_root="$(git -C "$script_root" rev-parse --show-toplevel 2>/dev/null || printf '%s' "$script_root")"
conversation_dir="$HOME/.gemini/antigravity/conversations"
state_dir="$workspace_root/.codex_work/jammini_watchdog"
state_file="$state_dir/state.env"
log_file="$state_dir/watchdog.log"
delegate_script="$workspace_root/tools/jammini_delegate.sh"
action_items_file="$workspace_root/ACTION_ITEMS.md"
ag_new="/opt/homebrew/bin/antigravity-send.sh"
resolver_script="$workspace_root/tools/lib/jammini_conversation_resolver.py"

mode=""
conversation_id=""
idle_minutes=10
cooldown_minutes=10
interval_seconds=30
timeout_seconds=20
dry_run=0

mkdir -p "$state_dir"
conversation_resolution_cache=""
conversation_resolution_loaded=0

load_conversation_resolution() {
  (( conversation_resolution_loaded == 0 )) || return 0
  conversation_resolution_cache="$(
    python3 "$resolver_script" \
      --workspace-root "$workspace_root" \
      --conversation-dir "$conversation_dir" \
      --ag-path "$ag_new"
  )"
  conversation_resolution_loaded=1
}

conversation_resolution_value() {
  local key="$1"
  load_conversation_resolution
  printf '%s\n' "$conversation_resolution_cache" | sed -nE "s/^${key}=(.*)$/\\1/p" | head -n 1
}

active_project_conversation_id() {
  conversation_resolution_value active_conversation_id
}

canonical_project_conversation_id() {
  local canonical_id
  canonical_id="$(conversation_resolution_value canonical_conversation_id)"
  [[ -n "$canonical_id" ]] || return 1
  printf '%s\n' "$canonical_id"
}

jammini_team_conversation_id() {
  local teamwork_id
  teamwork_id="$(conversation_resolution_value jammini_team_conversation_id)"
  [[ -n "$teamwork_id" ]] || return 1
  printf '%s\n' "$teamwork_id"
}

brain_messages_dir() {
  local id="$1"
  printf '%s/.gemini/antigravity/brain/%s/.system_generated/messages\n' "$HOME" "$id"
}

latest_worker_handoff_details() {
  local canonical_id="$1"
  local messages_dir
  messages_dir="$(brain_messages_dir "$canonical_id")"
  [[ -d "$messages_dir" ]] || return 1

  python3 - "$messages_dir" "$canonical_id" <<'PY'
import glob
import json
import os
import re
import sys

messages_dir, canonical_id = sys.argv[1:3]
uuid_re = re.compile(r"^[0-9a-fA-F-]{36}$")
candidates = []

for path in glob.glob(os.path.join(messages_dir, "*.json")):
    base = os.path.basename(path)
    if base in {"cursor.json", "read.json"}:
        continue
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except Exception:
        continue
    if not isinstance(data, dict):
        continue

    sender = str(data.get("sender") or "")
    recipient = str(data.get("recipient") or canonical_id)
    if recipient != canonical_id or sender in {"", "system", canonical_id}:
        continue
    if not uuid_re.match(sender):
        continue

    tool = ((data.get("sourceMetadata") or {}).get("tool") or {})
    source_conversation_id = str(tool.get("conversationId") or "")
    message_title = str(((data.get("renderDetails") or {}).get("messageTitle")) or "")
    content = str(data.get("content") or "")

    score = 0
    if source_conversation_id == sender:
        score += 2
    if message_title == "Message from Root Agent":
        score += 2
    if content.startswith(("DEX_REVIEW_READY", "ACK", "WORKING", "DONE", "BLOCKED")):
        score += 1
    if score == 0:
        continue

    candidates.append((os.path.getmtime(path), score, sender))

if not candidates:
    raise SystemExit(1)

candidates.sort(reverse=True)
latest_mtime, _, latest_sender = candidates[0]
print(f"{latest_sender}\t{int(latest_mtime)}")
PY
}

conversation_pb_path() {
  local id="$1"
  printf '%s/%s.pb\n' "$conversation_dir" "$id"
}

conversation_last_epoch() {
  local id="$1"
  local pb_path
  pb_path="$(conversation_pb_path "$id")"
  if [[ -f "$pb_path" ]]; then
    stat -f '%m' "$pb_path"
    return 0
  fi
  return 1
}

wait_for_probe_receipts() {
  local canonical_id="$1"
  local worker_id="$2"
  local start_epoch="$3"
  local timeout="$4"

  python3 - "$canonical_id" "$worker_id" "$start_epoch" "$timeout" <<'PY'
import glob
import json
import os
import sys
import time

canonical_id, worker_id, start_epoch, timeout = sys.argv[1], sys.argv[2], int(sys.argv[3]), int(sys.argv[4])
home = os.path.expanduser("~")

def messages_dir(conversation_id):
    return os.path.join(home, ".gemini", "antigravity", "brain", conversation_id, ".system_generated", "messages")

def scan_match(directory, predicate):
    if not os.path.isdir(directory):
        return None
    best = None
    for path in glob.glob(os.path.join(directory, "*.json")):
        base = os.path.basename(path)
        if base in {"cursor.json", "read.json"}:
            continue
        try:
            mtime = int(os.path.getmtime(path))
        except OSError:
            continue
        if mtime < start_epoch:
            continue
        try:
            with open(path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
        except Exception:
            continue
        if not isinstance(data, dict) or not predicate(data):
            continue
        if best is None or mtime > best[0]:
            best = (mtime, path, data)
    return best

def compact_content(data):
    return str(data.get("content") or "").replace("\n", "\\n")[:400]

root_dir = messages_dir(canonical_id)
worker_dir = messages_dir(worker_id)
root_signal = None
root_ack = None
worker_delivery = None
worker_receipt = None
worker_error = None
deadline = time.time() + timeout

while time.time() <= deadline:
    if root_signal is None:
        root_signal = scan_match(
            root_dir,
            lambda data: str(data.get("sender") or "") == worker_id
            and str(data.get("recipient") or "") == canonical_id
            and str(data.get("content") or "").startswith(("ACK |", "WORKING |")),
        )
    if root_ack is None:
        root_ack = scan_match(
            root_dir,
            lambda data: str(data.get("sender") or "") == worker_id
            and str(data.get("recipient") or "") == canonical_id
            and str(data.get("content") or "").startswith("ACK |"),
        )
    if worker_delivery is None:
        worker_delivery = scan_match(
            worker_dir,
            lambda data: str(data.get("recipient") or "") == worker_id
            and "DEX_TASK_PACKET" in str(data.get("content") or "")
            and "ACK route probe" in str(data.get("content") or ""),
        )
    if worker_id != canonical_id and worker_receipt is None:
        worker_receipt = scan_match(
            worker_dir,
            lambda data: str(data.get("recipient") or "") == worker_id
            and str(data.get("sender") or "") not in {"", "system", canonical_id}
            and str(data.get("content") or "").startswith("WORKING |"),
        )
    if worker_error is None:
        worker_error = scan_match(
            worker_dir,
            lambda data: str(data.get("sender") or "") == "system"
            and str(data.get("recipient") or "") == worker_id
            and "RESOURCE_EXHAUSTED" in str(data.get("content") or ""),
        )
    if root_ack and (worker_id == canonical_id or worker_receipt):
        break
    time.sleep(1)

print(f"root_signal_visible={'yes' if root_signal else 'no'}")
if root_signal:
    print(f"root_signal_path={root_signal[1]}")
    print(f"root_signal_content={compact_content(root_signal[2])}")

print(f"root_ack_visible={'yes' if root_ack else 'no'}")
if root_ack:
    print(f"root_ack_path={root_ack[1]}")
    print(f"root_ack_content={compact_content(root_ack[2])}")
    print("root_ack_protocol=ok")
elif root_signal:
    print("root_ack_protocol=fail-non-ack-root-signal")
else:
    print("root_ack_protocol=missing")

if worker_id == canonical_id:
    print("worker_chat_visible=same-conversation")
elif worker_receipt:
    print("worker_chat_visible=yes")
    print(f"worker_chat_path={worker_receipt[1]}")
    print(f"worker_chat_content={compact_content(worker_receipt[2])}")
elif worker_delivery:
    print("worker_chat_visible=yes")
    print(f"worker_chat_path={worker_delivery[1]}")
    print(f"worker_chat_content={compact_content(worker_delivery[2])}")
else:
    print("worker_chat_visible=no")

print(f"worker_receipt_visible={'yes' if worker_receipt else 'no'}")
if worker_receipt:
    print(f"worker_receipt_path={worker_receipt[1]}")
    print(f"worker_receipt_content={compact_content(worker_receipt[2])}")
elif worker_delivery:
    print(f"worker_delivery_path={worker_delivery[1]}")
    print(f"worker_delivery_content={compact_content(worker_delivery[2])}")

print(f"worker_error_visible={'yes' if worker_error else 'no'}")
if worker_error:
    print(f"worker_error_path={worker_error[1]}")
    print(f"worker_error_content={compact_content(worker_error[2])}")
PY
}

load_state() {
  last_dispatch_epoch=0
  task_index=0
  last_role=""
  last_assignment=""
  last_conversation_id=""
  if [[ -f "$state_file" ]]; then
    # shellcheck disable=SC1090
    source "$state_file"
  fi
}

save_state() {
  local quoted_role quoted_assignment quoted_conversation
  printf -v quoted_role '%q' "$last_role"
  printf -v quoted_assignment '%q' "$last_assignment"
  printf -v quoted_conversation '%q' "$last_conversation_id"
  cat >"$state_file" <<EOF
last_dispatch_epoch=${last_dispatch_epoch}
task_index=${task_index}
last_role=${quoted_role}
last_assignment=${quoted_assignment}
last_conversation_id=${quoted_conversation}
EOF
}

log_line() {
  local level="$1"
  shift
  printf '%s [%s] %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$level" "$*" | tee -a "$log_file" >/dev/null
}

current_queue_item() {
  awk '
    /^## Active Execution Queue/ { in_queue = 1; next }
    in_queue && /^## / { exit }
    in_queue && /^### / {
      line = $0
      sub(/^### +[0-9]+\.? +/, "", line)
      print line
      exit
    }
  ' "$action_items_file"
}

quality_scope_for_index() {
  local index="$1"
  case $(( index % 6 )) in
    0) printf '%s\n' "NLE owner-map and compatibility audit" ;;
    1) printf '%s\n' "roughcut exact-join / sidecar restore risk audit" ;;
    2) printf '%s\n' "project save-load / direct SRT reopen risk audit" ;;
    3) printf '%s\n' "render-plan / export duration parity audit" ;;
    4) printf '%s\n' "source-app QA and artifact checklist prep" ;;
    5) printf '%s\n' "test gap / false-confidence review" ;;
  esac
}

quality_request_for_index() {
  local index="$1"
  case $(( index % 6 )) in
    0) printf '%s\n' "Source-App Internal NLE Timeline Architecture Plan 기준으로 owner-map, duplicate mutable timing state risk, rollback risk만 좁게 정리해줘. 구현은 하지 말고 DEX_REVIEW_READY로 멈춰." ;;
    1) printf '%s\n' "roughcut exact join, _edl.json, _render_plan.json, stitched_cut_boundaries reopen 경로에서 NLE marker/edit-point 매핑 전 false confidence risk만 검토해줘." ;;
    2) printf '%s\n' ".aissproj, direct SRT open, editor segment reload, project roughcut state의 legacy compatibility risk와 focused tests만 정리해줘." ;;
    3) printf '%s\n' "render/export plan을 NLE snapshot으로 라우팅하기 전 output duration, sidecar metadata, sync-safe render parity gate를 정리해줘." ;;
    4) printf '%s\n' "Macau/X5 source-app proof와 output/manual_verification/latest artifact checklist를 준비해줘. 실제 실행은 하지 말고 명령/증거 항목만." ;;
    5) printf '%s\n' "현재 ACTION_ITEMS.md NLE 계획 기준으로 빠진 테스트/문서/검증 게이트 3개를 우선순위로 추천해줘." ;;
  esac
}

role_for_index() {
  local index="$1"
  case $(( index % 3 )) in
    0) printf '%s\n' "한결" ;;
    1) printf '%s\n' "서린" ;;
    2) printf '%s\n' "유진" ;;
  esac
}

assign_task_once() {
  local resolved_conversation_id="$1"
  local now_epoch="$2"
  local queue_item role scope request assignment_summary

  queue_item="$(current_queue_item || true)"
  role="$(role_for_index "$task_index")"

  if [[ -n "$queue_item" ]]; then
    scope="top live queue item"
    request="현재 ACTION_ITEMS.md 최상단 live queue 1개만 support slice로 분석해줘: ${queue_item}. owner files, regression risk, proof plan만 정리하고 DEX_REVIEW_READY로 멈춰."
    assignment_summary="queue:${queue_item}"
  else
    scope="$(quality_scope_for_index "$task_index")"
    request="$(quality_request_for_index "$task_index")"
    assignment_summary="quality:${scope}"
  fi

  local cmd=(
    "$delegate_script"
    --conversation-id "$resolved_conversation_id"
    --role "$role"
    --scope "$scope"
    --request "$request"
  )

  if (( dry_run )); then
    cmd+=(--dry-run)
  fi

  if (( dry_run )); then
    log_line "DRYRUN" "dispatching role=${role} conversation=${resolved_conversation_id} assignment=${assignment_summary}"
  else
    log_line "INFO" "dispatching role=${role} conversation=${resolved_conversation_id} assignment=${assignment_summary}"
  fi
  "${cmd[@]}"

  if (( dry_run )); then
    return 0
  fi

  last_dispatch_epoch="$now_epoch"
  last_role="$role"
  last_assignment="$assignment_summary"
  last_conversation_id="$resolved_conversation_id"
  task_index=$((task_index + 1))
  save_state
}

run_ack_probe() {
  local resolved_conversation_id canonical_conversation_id teamwork_conversation_id active_conversation_id resolution_reason requested_conversation_id conversation_rebased
  canonical_conversation_id="$(canonical_project_conversation_id || true)"
  teamwork_conversation_id="$(jammini_team_conversation_id || true)"
  active_conversation_id="$(active_project_conversation_id || true)"
  resolution_reason="$(conversation_resolution_value resolution_reason || true)"
  if [[ -z "$canonical_conversation_id" ]]; then
    printf 'status=no-canonical-conversation\n'
    return 0
  fi

  requested_conversation_id="$conversation_id"
  conversation_rebased="no"
  if [[ -n "$conversation_id" ]]; then
    if [[ "$conversation_id" == "$canonical_conversation_id" && -n "$teamwork_conversation_id" && "$teamwork_conversation_id" != "$canonical_conversation_id" ]]; then
      resolved_conversation_id="$teamwork_conversation_id"
      conversation_rebased="canonical-to-teamwork"
    else
      resolved_conversation_id="$conversation_id"
    fi
  elif [[ -n "$teamwork_conversation_id" ]]; then
    resolved_conversation_id="$teamwork_conversation_id"
  elif [[ -n "$canonical_conversation_id" ]]; then
    resolved_conversation_id="$canonical_conversation_id"
  else
    printf 'status=no-conversation\n'
    return 0
  fi

  local probe_start_epoch
  probe_start_epoch="$(date +%s)"
  "$delegate_script" \
    --conversation-id "$resolved_conversation_id" \
    --role "잼민이" \
    --scope "ACK route probe" \
    --request "이 패킷은 통신 확인용입니다. root conversation에는 ACK | 잼민이 | ACK route probe 한 줄을 남기고, 현재 worker conversation에는 WORKING | 잼민이 | packet received 한 줄을 남긴 뒤 추가 작업 없이 멈춰."

  printf 'active_conversation_id=%s\n' "$active_conversation_id"
  printf 'canonical_conversation_id=%s\n' "$canonical_conversation_id"
  printf 'jammini_team_conversation_id=%s\n' "$teamwork_conversation_id"
  printf 'resolution_reason=%s\n' "$resolution_reason"
  printf 'requested_conversation_id=%s\n' "$requested_conversation_id"
  printf 'conversation_rebased=%s\n' "$conversation_rebased"
  printf 'conversation_id=%s\n' "$resolved_conversation_id"
  printf 'probe_start_epoch=%s\n' "$probe_start_epoch"
  wait_for_probe_receipts "$canonical_conversation_id" "$resolved_conversation_id" "$probe_start_epoch" "$timeout_seconds"
}

wait_for_handoff_probe() {
  local handoff_path="$1"
  local probe_id="$2"
  local timeout="$3"
  local deadline now handoff_file_visible handoff_index_visible handoff_first_line
  deadline=$(( $(date +%s) + timeout ))
  handoff_file_visible="no"
  handoff_index_visible="no"
  handoff_first_line=""

  while true; do
    if [[ -f "$handoff_path" ]] && grep -Fq "PROBE_ID=${probe_id}" "$handoff_path"; then
      handoff_file_visible="yes"
      handoff_first_line="$(sed -n '1p' "$handoff_path")"
      if grep -Fq "$handoff_path" "$workspace_root/.agents/sentinel/handoff.md" \
        || grep -Fq "${handoff_path#$workspace_root/}" "$workspace_root/.agents/sentinel/handoff.md"; then
        handoff_index_visible="yes"
      fi
      if [[ "$handoff_index_visible" == "yes" ]]; then
        printf 'handoff_file_visible=yes\n'
        printf 'handoff_path=%s\n' "$handoff_path"
        printf 'handoff_first_line=%s\n' "$handoff_first_line"
        printf 'handoff_marker_visible=yes\n'
        printf 'handoff_index_visible=yes\n'
        return 0
      fi
    fi

    now="$(date +%s)"
    if (( now >= deadline )); then
      printf 'handoff_file_visible=%s\n' "$handoff_file_visible"
      printf 'handoff_path=%s\n' "$handoff_path"
      [[ -n "$handoff_first_line" ]] && printf 'handoff_first_line=%s\n' "$handoff_first_line"
      printf 'handoff_marker_visible=%s\n' "$handoff_file_visible"
      printf 'handoff_index_visible=%s\n' "$handoff_index_visible"
      return 0
    fi
    sleep 1
  done
}

run_handoff_probe() {
  local resolved_conversation_id canonical_conversation_id teamwork_conversation_id active_conversation_id resolution_reason requested_conversation_id conversation_rebased
  canonical_conversation_id="$(canonical_project_conversation_id || true)"
  teamwork_conversation_id="$(jammini_team_conversation_id || true)"
  active_conversation_id="$(active_project_conversation_id || true)"
  resolution_reason="$(conversation_resolution_value resolution_reason || true)"
  if [[ -z "$canonical_conversation_id" ]]; then
    printf 'status=no-canonical-conversation\n'
    return 0
  fi

  requested_conversation_id="$conversation_id"
  conversation_rebased="no"
  if [[ -n "$conversation_id" ]]; then
    if [[ "$conversation_id" == "$canonical_conversation_id" && -n "$teamwork_conversation_id" && "$teamwork_conversation_id" != "$canonical_conversation_id" ]]; then
      resolved_conversation_id="$teamwork_conversation_id"
      conversation_rebased="canonical-to-teamwork"
    else
      resolved_conversation_id="$conversation_id"
    fi
  elif [[ -n "$teamwork_conversation_id" ]]; then
    resolved_conversation_id="$teamwork_conversation_id"
  elif [[ -n "$canonical_conversation_id" ]]; then
    resolved_conversation_id="$canonical_conversation_id"
  else
    printf 'status=no-conversation\n'
    return 0
  fi

  local probe_id handoff_rel handoff_path
  probe_id="$(date +%Y%m%d-%H%M%S)"
  handoff_rel=".agents/sentinel/handoffs/${probe_id}-watchdog-handoff-probe.md"
  handoff_path="$workspace_root/$handoff_rel"

  "$delegate_script" \
    --conversation-id "$resolved_conversation_id" \
    --role "잼민이" \
    --scope "handoff route probe ${probe_id}" \
    --request "통신 확인용 파일 handoff probe입니다. 코드/앱 파일은 읽거나 수정하지 마세요. 반드시 ${handoff_rel} 파일을 새로 만들고, 첫 줄은 DEX_REVIEW_READY, 본문에는 PROBE_ID=${probe_id} 와 판정대기: 덱스 직접 회수 필요 를 포함하세요. .agents/sentinel/handoff.md는 기존 내용을 절대 덮어쓰지 말고 상단 index에 ${handoff_rel} 포인터 1줄만 prepend하세요. chat ACK/WORKING은 참고용이므로 실패해도 괜찮고, root conversation에 WORKING은 보내지 마세요. 완료 후 추가 작업 없이 멈추세요."

  printf 'active_conversation_id=%s\n' "$active_conversation_id"
  printf 'canonical_conversation_id=%s\n' "$canonical_conversation_id"
  printf 'jammini_team_conversation_id=%s\n' "$teamwork_conversation_id"
  printf 'resolution_reason=%s\n' "$resolution_reason"
  printf 'requested_conversation_id=%s\n' "$requested_conversation_id"
  printf 'conversation_rebased=%s\n' "$conversation_rebased"
  printf 'conversation_id=%s\n' "$resolved_conversation_id"
  printf 'probe_id=%s\n' "$probe_id"
  wait_for_handoff_probe "$handoff_path" "$probe_id" "$timeout_seconds"
}

watchdog_cycle() {
  load_state

  local resolved_conversation_id
  if [[ -n "$conversation_id" ]]; then
    resolved_conversation_id="$conversation_id"
  elif resolved_conversation_id="$(jammini_team_conversation_id)"; then
    :
  elif resolved_conversation_id="$(canonical_project_conversation_id)"; then
    :
  else
    log_line "WARN" "no Antigravity project conversation found for $workspace_root"
    printf 'status=no-conversation\n'
    return 0
  fi

  local now_epoch last_activity_epoch idle_for cooldown_for
  local active_conversation_id canonical_conversation_id teamwork_conversation_id resolution_reason worker_handoff_conversation_id worker_handoff_last_message_epoch worker_handoff_details
  now_epoch="$(date +%s)"
  active_conversation_id="$(active_project_conversation_id || true)"
  canonical_conversation_id="$(canonical_project_conversation_id || true)"
  teamwork_conversation_id="$(jammini_team_conversation_id || true)"
  resolution_reason="$(conversation_resolution_value resolution_reason || true)"
  worker_handoff_conversation_id=""
  worker_handoff_last_message_epoch=0
  if [[ -n "$canonical_conversation_id" ]]; then
    worker_handoff_details="$(latest_worker_handoff_details "$canonical_conversation_id" || true)"
    if [[ -n "$worker_handoff_details" ]]; then
      IFS=$'\t' read -r worker_handoff_conversation_id worker_handoff_last_message_epoch <<<"$worker_handoff_details"
    elif [[ -n "$teamwork_conversation_id" ]]; then
      worker_handoff_conversation_id="$teamwork_conversation_id"
    fi
  fi
  last_activity_epoch="$(conversation_last_epoch "$resolved_conversation_id" || printf '0')"
  idle_for=$(( now_epoch - last_activity_epoch ))
  cooldown_for=$(( now_epoch - last_dispatch_epoch ))
  (( idle_for < 0 )) && idle_for=0
  (( cooldown_for < 0 )) && cooldown_for=0

  if [[ "$mode" == "status" ]]; then
    printf 'active_conversation_id=%s\n' "$active_conversation_id"
    printf 'canonical_conversation_id=%s\n' "$canonical_conversation_id"
    printf 'jammini_team_conversation_id=%s\n' "$teamwork_conversation_id"
    printf 'resolution_reason=%s\n' "$resolution_reason"
    printf 'conversation_id=%s\n' "$resolved_conversation_id"
    printf 'worker_handoff_conversation_id=%s\n' "$worker_handoff_conversation_id"
    printf 'worker_handoff_last_message_epoch=%s\n' "$worker_handoff_last_message_epoch"
    printf 'last_activity_epoch=%s\n' "$last_activity_epoch"
    printf 'idle_seconds=%s\n' "$idle_for"
    printf 'last_dispatch_epoch=%s\n' "$last_dispatch_epoch"
    printf 'cooldown_seconds=%s\n' "$cooldown_for"
    printf 'last_role=%s\n' "$last_role"
    printf 'last_assignment=%s\n' "$last_assignment"
    return 0
  fi

  if (( last_activity_epoch == 0 )); then
    log_line "WARN" "conversation exists but last activity timestamp is unavailable; dispatching guarded packet"
  elif (( idle_for < idle_minutes * 60 )); then
    log_line "INFO" "jammini still active idle_seconds=${idle_for}; no new assignment"
    return 0
  fi

  if (( cooldown_for < cooldown_minutes * 60 )); then
    log_line "INFO" "cooldown active cooldown_seconds=${cooldown_for}; no new assignment"
    return 0
  fi

  assign_task_once "$resolved_conversation_id" "$now_epoch"
}

while (( $# > 0 )); do
  case "$1" in
    -h|--help)
      usage
      exit 0
      ;;
    --status|--queue-status)
      mode="status"
      shift
      ;;
    --ack-probe)
      mode="ack-probe"
      shift
      ;;
    --handoff-probe)
      mode="handoff-probe"
      shift
      ;;
    --once)
      mode="once"
      shift
      ;;
    --watch)
      mode="watch"
      shift
      ;;
    --conversation-id)
      (( $# >= 2 )) || { echo "--conversation-id requires a value" >&2; exit 1; }
      conversation_id="$2"
      shift 2
      ;;
    --idle-minutes)
      (( $# >= 2 )) || { echo "--idle-minutes requires a value" >&2; exit 1; }
      idle_minutes="$2"
      shift 2
      ;;
    --cooldown-minutes)
      (( $# >= 2 )) || { echo "--cooldown-minutes requires a value" >&2; exit 1; }
      cooldown_minutes="$2"
      shift 2
      ;;
    --interval-seconds)
      (( $# >= 2 )) || { echo "--interval-seconds requires a value" >&2; exit 1; }
      interval_seconds="$2"
      shift 2
      ;;
    --timeout-seconds)
      (( $# >= 2 )) || { echo "--timeout-seconds requires a value" >&2; exit 1; }
      timeout_seconds="$2"
      shift 2
      ;;
    --dry-run)
      dry_run=1
      shift
      ;;
    *)
      echo "unknown argument: $1" >&2
      usage >&2
      exit 1
      ;;
  esac
done

case "$mode" in
  ack-probe)
    run_ack_probe
    ;;
  handoff-probe)
    run_handoff_probe
    ;;
  status)
    watchdog_cycle
    ;;
  once)
    watchdog_cycle
    ;;
  watch)
    while true; do
      watchdog_cycle
      sleep "$interval_seconds"
    done
    ;;
  *)
    usage >&2
    exit 1
    ;;
esac
