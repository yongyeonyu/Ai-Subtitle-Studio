#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
queue_file="${repo_root}/doc/ACTION_ITEMS.md"
state_dir="${repo_root}/.codex_work/jammini_watchdog"
state_file="${state_dir}/state.env"
log_file="${state_dir}/watchdog.log"
sentinel_dir="${repo_root}/.agents/sentinel"
handoff_dir="${sentinel_dir}/handoffs"
handoff_index_file="${sentinel_dir}/handoff.md"
project_root="${repo_root}"
conversation_id=""
interval_sec=300
dispatch_cooldown_sec=600
once=0
dry_run=0
reset_state=0
drain_pending_queue=0
queue_status=0
status=0
handoff_probe=0
handoff_list=0
handoff_limit=10

usage() {
  cat <<'EOF'
usage: tools/jammini_watchdog.sh [--conversation-id <id>] [options]

Options:
  --conversation-id <id>     Antigravity conversation id, or "auto" to pick
                             the latest conversation for this project root
  --queue-file <path>        Queue source file (default: doc/ACTION_ITEMS.md)
  --interval-sec <n>         Seconds between watchdog checks in loop mode
  --dispatch-cooldown-sec <n>
                             Minimum seconds between delegated task dispatches
  --project-root <path>      Project root label to include in messages
  --once                     Run one watchdog cycle and exit
  --dry-run                  Print packets instead of sending them
  --reset-state              Reset local watchdog cursor state before running
  --drain-pending-queue      Dispatch every currently pending JW queue item, then exit
  --queue-status             Print current JW queue dispatch status as JSON, then exit
  --status                   Print local watchdog / handoff route status as JSON
  --handoff-probe            Create a local .agents/sentinel physical handoff probe
  --handoff-list             List local .agents/sentinel physical handoffs as JSON
  --handoff-limit <n>        Maximum handoffs to list (default: 10)
  --help                     Show this message
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --conversation-id)
      conversation_id="${2:-}"
      shift 2
      ;;
    --queue-file)
      queue_file="${2:-}"
      shift 2
      ;;
    --interval-sec)
      interval_sec="${2:-}"
      shift 2
      ;;
    --dispatch-cooldown-sec)
      dispatch_cooldown_sec="${2:-}"
      shift 2
      ;;
    --project-root)
      project_root="${2:-}"
      shift 2
      ;;
    --once)
      once=1
      shift
      ;;
    --dry-run)
      dry_run=1
      shift
      ;;
    --reset-state)
      reset_state=1
      shift
      ;;
    --drain-pending-queue)
      drain_pending_queue=1
      shift
      ;;
    --queue-status)
      queue_status=1
      shift
      ;;
    --status)
      status=1
      shift
      ;;
    --handoff-probe)
      handoff_probe=1
      shift
      ;;
    --handoff-list)
      handoff_list=1
      shift
      ;;
    --handoff-limit)
      handoff_limit="${2:-}"
      shift 2
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    *)
      echo "unknown argument: $1" >&2
      usage >&2
      exit 1
      ;;
  esac
done

resolve_auto_conversation_id() {
  if [[ "${conversation_id}" != "auto" ]]; then
    return 0
  fi
  if [[ ! -x /opt/homebrew/bin/antigravity-send.sh ]]; then
    echo "antigravity-send.sh is required for --conversation-id auto" >&2
    exit 1
  fi
  local output resolved_id
  output="$(/opt/homebrew/bin/antigravity-send.sh stop-all --project "${repo_root}" --limit 30 --dry-run 2>/dev/null || true)"
  resolved_id="$(
    printf '%s\n' "${output}" \
      | awk '/^conversations:$/ {in_list=1; next} in_list && /^[0-9a-fA-F-]{36}$/ {print; exit}'
  )"
  if [[ -z "${resolved_id}" ]]; then
    echo "could not resolve Antigravity conversation for project: ${repo_root}" >&2
    exit 1
  fi
  conversation_id="${resolved_id}"
}

resolve_auto_conversation_id

if [[ "${queue_status}" -ne 1 && "${status}" -ne 1 && "${handoff_probe}" -ne 1 && "${handoff_list}" -ne 1 && -z "${conversation_id}" ]]; then
  echo "--conversation-id is required" >&2
  usage >&2
  exit 1
fi

mkdir -p "${state_dir}"

if [[ "${reset_state}" -eq 1 ]]; then
  rm -f "${state_file}"
fi

last_check_epoch=0
last_dispatch_epoch=0
queue_cursor=0
evergreen_cursor=0

if [[ -f "${state_file}" ]]; then
  # shellcheck disable=SC1090
  source "${state_file}"
fi

if [[ "${drain_pending_queue}" -eq 1 ]]; then
  queue_cursor=0
fi

save_state() {
  if [[ "${dry_run}" -eq 1 ]]; then
    return 0
  fi
  cat >"${state_file}" <<EOF
last_check_epoch=${last_check_epoch}
last_dispatch_epoch=${last_dispatch_epoch}
queue_cursor=${queue_cursor}
evergreen_cursor=${evergreen_cursor}
EOF
}

log_line() {
  local kind="$1"
  local detail="$2"
  printf '%s\t%s\t%s\n' "$(date '+%Y-%m-%dT%H:%M:%S%z')" "${kind}" "${detail}" >>"${log_file}"
}

send_packet() {
  local label="$1"
  local body="$2"
  local detail="${3:-sent}"
  if [[ "${dry_run}" -eq 1 ]]; then
    printf '=== %s ===\n%s\n\n' "${label}" "${body}"
    log_line "${label}" "dry-run:${detail}"
    return 0
  fi

  if [[ -x /opt/homebrew/bin/antigravity-send.sh ]]; then
    # shellcheck disable=SC1091
    source <(/opt/homebrew/bin/antigravity-send.sh env --shell)
  fi

  /opt/homebrew/bin/ag-send "${conversation_id}" "${body}" >/dev/null
  log_line "${label}" "${detail}"
}

collect_queue_items() {
  awk '
    function trim(s) {
      gsub(/^[ \t]+|[ \t]+$/, "", s)
      return s
    }
    /#### Jammini Watchdog Queue/ {in_section=1; next}
    in_section && /^#### / {exit}
    in_section && /^\| JW-/ {
      split($0, cols, "|")
      id=trim(cols[2])
      status=tolower(trim(cols[3]))
      scope=trim(cols[5])
      output=trim(cols[6])
      if (status != "completed" && status != "done" && status != "cancelled" && status != "deferred") {
        printf "%s\t%s\t%s\n", id, scope, output
      }
    }
  ' "${queue_file}"
}

next_queue_item() {
  local queue_items=()
  local line
  while IFS= read -r line; do
    [[ -n "${line}" ]] || continue
    queue_items+=("${line}")
  done < <(collect_queue_items)
  if [[ ${#queue_items[@]} -eq 0 ]]; then
    return 1
  fi
  if (( queue_cursor > ${#queue_items[@]} )); then
    queue_cursor=0
  fi
  if (( queue_cursor >= ${#queue_items[@]} )); then
    return 1
  fi
  printf '%s' "${queue_items[queue_cursor]}"
}

pending_queue_count() {
  local count=0
  while IFS= read -r line; do
    [[ -n "${line}" ]] || continue
    count=$((count + 1))
  done < <(collect_queue_items)
  if (( count < queue_cursor )); then
    queue_cursor=0
  fi
  if (( count <= queue_cursor )); then
    printf '0'
    return 0
  fi
  printf '%s' "$((count - queue_cursor))"
}

print_queue_status() {
  local queue_items=()
  local line
  while IFS= read -r line; do
    [[ -n "${line}" ]] || continue
    queue_items+=("${line}")
  done < <(collect_queue_items)
  local count="${#queue_items[@]}"
  local effective_cursor="${queue_cursor}"
  if (( effective_cursor > count )); then
    effective_cursor=0
  fi
  QUEUE_CURSOR="$effective_cursor" python3 - "$count" "${queue_items[@]}" <<'PY'
import json
import os
import sys

count = int(sys.argv[1])
rows = sys.argv[2:]
cursor = int(os.environ.get("QUEUE_CURSOR", "0") or 0)

items = []
for row in rows:
    parts = row.split("\t")
    queue_id = parts[0].strip() if len(parts) > 0 else ""
    scope = parts[1].strip() if len(parts) > 1 else ""
    required_output = parts[2].strip() if len(parts) > 2 else ""
    items.append(
        {
            "queue_id": queue_id,
            "scope": scope,
            "required_output": required_output,
        }
    )

payload = {
    "ok": True,
    "queue_cursor": cursor,
    "pending_total_count": count,
    "dispatched_awaiting_review_count": min(cursor, count),
    "remaining_to_dispatch_count": max(0, count - cursor),
    "dispatched_awaiting_review": items[:cursor],
    "remaining_to_dispatch": items[cursor:],
}
print(json.dumps(payload, ensure_ascii=False, indent=2))
PY
}

print_status() {
  local queue_file_exists=0
  local state_file_exists=0
  local sentinel_exists=0
  local handoff_dir_exists=0
  local handoff_index_exists=0
  local ag_send_available=0
  local antigravity_env_helper_available=0
  local handoff_count=0
  local remaining_count=0

  [[ -f "${queue_file}" ]] && queue_file_exists=1
  [[ -f "${state_file}" ]] && state_file_exists=1
  [[ -d "${sentinel_dir}" ]] && sentinel_exists=1
  [[ -d "${handoff_dir}" ]] && handoff_dir_exists=1
  [[ -f "${handoff_index_file}" ]] && handoff_index_exists=1
  [[ -x /opt/homebrew/bin/ag-send ]] && ag_send_available=1
  [[ -x /opt/homebrew/bin/antigravity-send.sh ]] && antigravity_env_helper_available=1

  if [[ -d "${handoff_dir}" ]]; then
    handoff_count="$(find "${handoff_dir}" -maxdepth 1 -type f -name '*.md' | wc -l | tr -d ' ')"
  fi
  remaining_count="$(pending_queue_count)"

  python3 - "$repo_root" "$project_root" "$queue_file" "$state_dir" "$log_file" \
    "$sentinel_dir" "$handoff_dir" "$handoff_index_file" "$conversation_id" \
    "$queue_file_exists" "$state_file_exists" "$sentinel_exists" "$handoff_dir_exists" \
    "$handoff_index_exists" "$ag_send_available" "$antigravity_env_helper_available" \
    "$handoff_count" "$remaining_count" <<'PY'
import json
import sys

(
    repo_root,
    project_root,
    queue_file,
    state_dir,
    log_file,
    sentinel_dir,
    handoff_dir,
    handoff_index_file,
    conversation_id,
    queue_file_exists,
    state_file_exists,
    sentinel_exists,
    handoff_dir_exists,
    handoff_index_exists,
    ag_send_available,
    antigravity_env_helper_available,
    handoff_count,
    remaining_count,
) = sys.argv[1:]

payload = {
    "ok": True,
    "project_root": project_root,
    "repo_root": repo_root,
    "conversation_id_present": bool(conversation_id),
    "queue_file": queue_file,
    "queue_file_exists": queue_file_exists == "1",
    "remaining_queue_count": int(remaining_count or 0),
    "state_dir": state_dir,
    "state_file_exists": state_file_exists == "1",
    "log_file": log_file,
    "sentinel_dir": sentinel_dir,
    "sentinel_exists": sentinel_exists == "1",
    "handoff_dir": handoff_dir,
    "handoff_dir_exists": handoff_dir_exists == "1",
    "handoff_index_file": handoff_index_file,
    "handoff_index_exists": handoff_index_exists == "1",
    "handoff_count": int(handoff_count or 0),
    "ag_send_available": ag_send_available == "1",
    "antigravity_env_helper_available": antigravity_env_helper_available == "1",
    "chat_signal_is_proof": False,
    "physical_handoff_is_proof": True,
}
print(json.dumps(payload, ensure_ascii=False, indent=2))
PY
}

write_handoff_probe() {
  local timestamp rel_path tmp_index
  timestamp="$(date '+%Y%m%d-%H%M%S')"
  mkdir -p "${handoff_dir}" "${state_dir}"
  local probe_file="${handoff_dir}/${timestamp}-watchdog-handoff-probe.md"
  rel_path="${probe_file#"${repo_root}/"}"

  cat >"${probe_file}" <<EOF
# Jammini Watchdog Handoff Probe

DEX_REVIEW_READY

Queue ID: handoff-probe
Scope: repo-local Jammini physical handoff route
Files:
- tools/jammini_watchdog.sh
Findings/Proposal:
- The local physical handoff path is writable.
- Chat ACK/WORKING/DONE/BLOCKED remains a progress signal, not final proof.
Validation:
- Created by \`tools/jammini_watchdog.sh --handoff-probe\`.
Open Risks:
- This probe does not prove an Antigravity chat route or worker ACK.
EOF

  tmp_index="$(mktemp "${state_dir}/handoff-index.XXXXXX")"
  if [[ -f "${handoff_index_file}" ]]; then
    {
      printf -- '- %s\n\n' "${rel_path}"
      cat "${handoff_index_file}"
    } >"${tmp_index}"
  else
    {
      printf '# Jammini Handoff Index\n\n'
      printf -- '- %s\n' "${rel_path}"
    } >"${tmp_index}"
  fi
  mv "${tmp_index}" "${handoff_index_file}"
  log_line "HANDOFF_PROBE" "created:${rel_path}"

  python3 - "$probe_file" "$rel_path" "$handoff_index_file" <<'PY'
import json
import sys

probe_file, rel_path, handoff_index_file = sys.argv[1:]
print(json.dumps({
    "ok": True,
    "probe_file": probe_file,
    "relative_probe_file": rel_path,
    "handoff_index_file": handoff_index_file,
    "chat_signal_is_proof": False,
    "physical_handoff_is_proof": True,
}, ensure_ascii=False, indent=2))
PY
}

print_handoff_list() {
  python3 - "$repo_root" "$handoff_dir" "$handoff_index_file" "$handoff_limit" <<'PY'
import json
import sys
from pathlib import Path

repo_root = Path(sys.argv[1])
handoff_dir = Path(sys.argv[2])
handoff_index_file = Path(sys.argv[3])
try:
    limit = max(1, int(sys.argv[4]))
except (TypeError, ValueError):
    limit = 10

items = []
if handoff_dir.exists():
    files = sorted(
        handoff_dir.glob("*.md"),
        key=lambda p: (p.stat().st_mtime, p.name),
        reverse=True,
    )
    for path in files[:limit]:
        stat = path.stat()
        try:
            rel = str(path.relative_to(repo_root))
        except ValueError:
            rel = str(path)
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            text = ""
        first_heading = ""
        for line in text.splitlines():
            stripped = line.strip()
            if stripped:
                first_heading = stripped
                break
        items.append(
            {
                "path": str(path),
                "relative_path": rel,
                "modified_epoch": int(stat.st_mtime),
                "size_bytes": stat.st_size,
                "first_heading": first_heading,
                "contains_dex_review_ready": "DEX_REVIEW_READY" in text,
            }
        )

index_entries = []
if handoff_index_file.exists():
    try:
        lines = handoff_index_file.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        lines = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("- "):
            index_entries.append(stripped[2:].strip())

print(
    json.dumps(
        {
            "ok": True,
            "handoff_dir": str(handoff_dir),
            "handoff_dir_exists": handoff_dir.exists(),
            "handoff_index_file": str(handoff_index_file),
            "handoff_index_exists": handoff_index_file.exists(),
            "limit": limit,
            "handoff_count": len(list(handoff_dir.glob("*.md"))) if handoff_dir.exists() else 0,
            "items": items,
            "index_entries": index_entries[:limit],
            "chat_signal_is_proof": False,
            "physical_handoff_is_proof": True,
        },
        ensure_ascii=False,
        indent=2,
    )
)
PY
}

evergreen_task() {
  local ids=(
    "EW-01"
    "EW-02"
    "EW-03"
    "EW-04"
  )
  local scopes=(
    "Take the token-heavy file/log/artifact scan for the active feature and return one bounded quality-improvement shortlist only. No patch."
    "Prepare the next narrow validation bundle for the active feature and absorb the repetitive command/proof setup work. List only the minimum commands and artifacts needed."
    "Review docs and handoff drift between doc/ACTION_ITEMS.md, doc/HANDOFF.md, and the current owner-file focus. Draft deltas only, and absorb the long-form comparison work."
    "Inspect one current owner-file cluster for unused/simple cleanup candidates and separate harmless cleanup from anything risky. Treat repeated low-risk scouting as Jammini-owned."
  )
  if (( evergreen_cursor >= ${#ids[@]} )); then
    evergreen_cursor=0
  fi
  printf '%s\t%s' "${ids[evergreen_cursor]}" "${scopes[evergreen_cursor]}"
}

watchdog_check_body() {
  cat <<EOF
WATCHDOG_CHECK
프로젝트: ${project_root}
상태만 한 줄로 답해라: WORKING / WAITING / BLOCKED
같은 줄에 현재 bounded scope를 짧게 덧붙여라.
WAITING이면 다음 slice를 바로 받을 준비라고 적어라.
EOF
}

watchdog_nudge_body() {
  local queue_id="$1"
  local scope="$2"
  local required_output="$3"
  cat <<EOF
WATCHDOG_NUDGE
프로젝트: ${project_root}
Queue ID: ${queue_id}
idle 금지. safe bounded slice가 남아 있으니 바로 시작해라.
우선순위 규칙:
- token 많이 드는 탐색/로그읽기/아티팩트 비교는 전부 잼민이가 먼저 맡는다
- 단순 반복 작업과 오래 걸리는 준비/검증 보조도 전부 잼민이가 먼저 맡는다
- 덱스는 accept/reject 판단과 위험한 구현 결정만 남긴다
범위: ${scope}
제한:
- simple / bounded / draft-review-doc-prep only
- broad rewrite 금지
- code patch는 owner 또는 덱스가 승격할 때만
- 이 Queue ID가 doc/ACTION_ITEMS.md의 ordered JW queue 일부라면, 현재 항목을 끝낸 뒤 다음 pending JW simple slice도 대기 없이 이어서 처리해라
반환 형식:
DEX_REVIEW_READY
Queue ID: ${queue_id}
필수 출력: ${required_output}
끝나면 다음 일을 멋대로 넓히지 말고 review-ready로 넘겨라.
EOF
}

run_cycle() {
  local now next_item queue_id scope output evergreen task_body
  now="$(date +%s)"

  if (( now - last_check_epoch >= interval_sec )); then
    send_packet "WATCHDOG_CHECK" "$(watchdog_check_body)" "sent:check"
    last_check_epoch="${now}"
  fi

  if (( now - last_dispatch_epoch < dispatch_cooldown_sec )); then
    save_state
    return 0
  fi

  if next_item="$(next_queue_item)"; then
    IFS=$'\t' read -r queue_id scope output <<<"${next_item}"
    task_body="$(watchdog_nudge_body "${queue_id}" "${scope}" "${output}")"
    send_packet "WATCHDOG_NUDGE" "${task_body}" "sent:${queue_id}"
    queue_cursor=$((queue_cursor + 1))
  else
    evergreen="$(evergreen_task)"
    IFS=$'\t' read -r queue_id scope <<<"${evergreen}"
    task_body="$(watchdog_nudge_body "${queue_id}" "${scope}" "DEX_REVIEW_READY packet with the narrow result, touched files, validation/proof status, and open risks.")"
    send_packet "WATCHDOG_NUDGE" "${task_body}" "sent:${queue_id}"
    evergreen_cursor=$((evergreen_cursor + 1))
  fi

  last_dispatch_epoch="${now}"
  save_state
}

if [[ "${status}" -eq 1 ]]; then
  print_status
  exit 0
fi

if [[ "${handoff_probe}" -eq 1 ]]; then
  write_handoff_probe
  exit 0
fi

if [[ "${handoff_list}" -eq 1 ]]; then
  print_handoff_list
  exit 0
fi

if [[ "${drain_pending_queue}" -eq 1 ]]; then
  while [[ "$(pending_queue_count)" != "0" ]]; do
    run_cycle
    if [[ "${dry_run}" -eq 0 ]]; then
      sleep 0.1
    fi
  done
  exit 0
fi

if [[ "${queue_status}" -eq 1 ]]; then
  print_queue_status
  exit 0
fi

run_cycle

if [[ "${once}" -eq 1 ]]; then
  exit 0
fi

while true; do
  sleep "${interval_sec}"
  run_cycle
done
