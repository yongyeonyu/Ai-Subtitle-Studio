#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  tools/jammini_delegate.sh --bootstrap [--new] [--conversation-id <id>] [--dry-run]
  tools/jammini_delegate.sh --role <role> --request <text> [--scope <text>] [--file <path> ...] [--conversation-id <id>] [--dry-run]
  tools/jammini_delegate.sh --stop [--conversation-id <id>] [--dry-run]

Examples:
  tools/jammini_delegate.sh --bootstrap --dry-run
  tools/jammini_delegate.sh --bootstrap --conversation-id <id>
  tools/jammini_delegate.sh --bootstrap --new
  tools/jammini_delegate.sh --role 서린 --scope "NLE adapter risk" --request "false confidence와 compatibility risk만 검토"
  tools/jammini_delegate.sh --role 한결 --file core/project/project_format.py --request "file-scoped review only"
  tools/jammini_delegate.sh --stop
EOF
}

script_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
workspace_root="$(git -C "$script_root" rev-parse --show-toplevel 2>/dev/null || printf '%s' "$script_root")"
ag_send_last="/opt/homebrew/bin/ag-send-last"
ag_send="/opt/homebrew/bin/ag-send"
ag_new="/opt/homebrew/bin/antigravity-send.sh"
ag_stop="/opt/homebrew/bin/ag-stop"
conversation_dir="$HOME/.gemini/antigravity/conversations"
resolver_script="$workspace_root/tools/lib/jammini_conversation_resolver.py"

mode=""
role="잼민이"
request=""
scope=""
conversation_id=""
dry_run=0
new_conversation=0
files=()
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

while (( $# > 0 )); do
  case "$1" in
    -h|--help)
      usage
      exit 0
      ;;
    --bootstrap)
      mode="bootstrap"
      shift
      ;;
    --stop)
      mode="stop"
      shift
      ;;
    --new)
      new_conversation=1
      shift
      ;;
    --dry-run)
      dry_run=1
      shift
      ;;
    --role)
      (( $# >= 2 )) || { echo "--role requires a value" >&2; exit 1; }
      role="$2"
      shift 2
      ;;
    --request)
      (( $# >= 2 )) || { echo "--request requires a value" >&2; exit 1; }
      request="$2"
      shift 2
      ;;
    --scope)
      (( $# >= 2 )) || { echo "--scope requires a value" >&2; exit 1; }
      scope="$2"
      shift 2
      ;;
    --file)
      (( $# >= 2 )) || { echo "--file requires a value" >&2; exit 1; }
      files+=("$2")
      shift 2
      ;;
    --conversation-id)
      (( $# >= 2 )) || { echo "--conversation-id requires a value" >&2; exit 1; }
      conversation_id="$2"
      shift 2
      ;;
    *)
      echo "unknown argument: $1" >&2
      usage >&2
      exit 1
      ;;
  esac
done

bootstrap_prompt() {
  local root_conversation_id
  root_conversation_id="$(canonical_project_conversation_id || true)"
  cat <<EOF
이 프로젝트에서 Codex(덱스)와 협업합니다.

프로젝트:
- ${workspace_root}

작업 전 반드시 읽으세요:
1. AGENTS.md
2. ACTION_ITEMS.md
3. File_structure.txt
4. docs/README.md
5. docs/PROJECT_STATE.md
6. docs/FEATURE_REGISTRY.md
7. docs/ARCHITECTURE.md
8. docs/VALIDATION.md
9. docs/HANDOFF.md
10. cooperation.md

역할:
- 덱스는 최종 구현, 검증, owner 보고를 담당합니다.
- 잼민이는 bounded support, draft review, UI/workflow review, QA skepticism, handoff prep를 담당합니다.
- 한결/서린/유진 역할이 필요하면 각각 architecture / QA / workflow 관점으로 답하세요.

규칙:
- 요청 범위를 넓히지 말 것
- 구현하지 말라고 한 packet은 구현하지 말 것
- dirty worktree 보존
- UI/UX labels, layout, colors, shortcuts, menus, and popup behavior do not change unless the owner explicitly asks
- 물리 파일 handoff가 source of truth다:
  1. 완료 산출물은 .agents/sentinel/handoffs/ 아래 개별 파일에 남길 것
  2. .agents/sentinel/handoff.md는 기존 내용을 덮어쓰지 말고 상단 index pointer만 prepend할 것
  3. chat ACK/WORKING은 참고용이다. root conversation에 WORKING을 보내지 말고, 확실하지 않으면 chat signal을 생략할 것
- Source-app proof and focused tests are preferred; DMG/package/App Store work is opt-in only
- release/commit/push/account/payment/ad-console decision은 owner나 덱스의 명시 승인 없이는 하지 말 것
- 덱스와의 내부 통신은 compact protocol을 우선 사용하고, 사람 설명은 필요할 때만 최소화할 것
- active task가 있을 때는 recurring timer, self-spawned heartbeat job, 30-second idle ping을 만들지 말 것
- 진행 신호는 ACK, WORKING, DONE, BLOCKED 네 가지로만 짧게 남길 것
- 정말 idle이고 bounded task가 하나도 없을 때만 새 일감을 요청하되 cadence는 10분보다 촘촘하면 안 된다
- 오래된 규칙보다 최신 DEX control update가 우선이다
- delegated slice가 끝나면 DEX_REVIEW_READY로 반환하고 멈출 것

출력 형식:
1. 좁은 작업 범위
2. 읽은 파일
3. findings or draft
4. validation or proof status
5. open risk
EOF
}

delegate_prompt() {
  local file_list="(none)"
  local root_conversation_id
  root_conversation_id="$(canonical_project_conversation_id || true)"
  if (( ${#files[@]} > 0 )); then
    file_list=""
    local file
    for file in "${files[@]}"; do
      file_list+="- \`${file}\`"$'\n'
    done
  fi

  cat <<EOF
DEX_TASK_PACKET
프로젝트: ${workspace_root}
역할: ${role}
범위: ${scope:-bounded support slice}
요청: ${request}

HANDOFF_CONTRACT:
1. Chat ACK/WORKING은 참고용이다. 최종 신뢰 기준은 물리 파일이다.
2. review/draft 결과가 있으면 .agents/sentinel/handoffs/ 아래 새 timestamp 파일에 DEX_REVIEW_READY 형식으로 저장한다.
3. .agents/sentinel/handoff.md는 기존 내용을 절대 overwrite하지 말고, 상단 index pointer만 prepend한다.
4. root conversation에 WORKING을 보내지 않는다. 확실히 ACK를 보낼 수 없으면 chat signal을 생략하고 파일 handoff만 완료한다.

대상 파일:
${file_list}
규칙:
- 구현하지 말고 요청된 support/review/draft만 수행
- 요청 범위를 넓히지 말 것
- dirty worktree 보존
- UI/UX labels, layout, colors, shortcuts, menus, and popup behavior do not change unless the owner explicitly asks
- root conversation id: ${root_conversation_id:-unknown}
- HANDOFF_CONTRACT가 이 규칙 목록보다 우선한다
- Source-app proof and focused tests are preferred; DMG/package/App Store work is opt-in only
- release/commit/push/account/payment/ad-console decision은 하지 말 것
- recurring timer, self-spawned heartbeat, idle nag task를 만들지 말 것
- active 상태에서는 ACK, WORKING, DONE, BLOCKED만 짧게 출력할 것
- 정말 idle이고 현재 bounded task가 없을 때만 10분 이상 간격으로 새 일감을 요청할 것
- 최신 DEX control update가 오래된 규칙보다 우선이다

반환 형식:
DEX_REVIEW_READY
역할:
범위:
읽은 파일:
결론:
findings:
defer:
덱스 확인 포인트:
EOF
}

send_prompt() {
  local prompt="$1"
  if (( dry_run )); then
    printf '%s\n' "$prompt"
    return
  fi

  if (( new_conversation )); then
    local output
    if ! output="$("$ag_new" new "$prompt" 2>&1)"; then
      printf '%s\n' "$output" >&2
      printf '%s\n' "jammini_delegate: failed to create a new Antigravity conversation. Open the project in Antigravity first or pass --conversation-id." >&2
      return 1
    fi
    printf '%s\n' "$output"
    if ! grep -Eq '[0-9a-fA-F-]{36}' <<<"$output"; then
      printf '%s\n' "jammini_delegate: Antigravity did not return a conversation id. Use an existing project conversation with --conversation-id." >&2
      return 1
    fi
    return 0
  fi

  local target_conv=""
  if [[ -n "$conversation_id" ]]; then
    target_conv="$conversation_id"
  elif target_conv="$(jammini_team_conversation_id 2>/dev/null)"; then
    :
  elif target_conv="$(canonical_project_conversation_id 2>/dev/null)"; then
    :
  fi

  if [[ -z "$target_conv" ]]; then
    printf '%s\n' "jammini_delegate: could not find a Jammini Teamwork conversation or canonical Antigravity project conversation under $workspace_root. Open the AI Subtitle Studio project conversation in Antigravity first or pass --conversation-id." >&2
    return 1
  fi

  # Notify the root conversation when delegating to a sub-conversation or active conversation
  local canonical_id
  canonical_id="$(canonical_project_conversation_id 2>/dev/null || true)"
  if [[ -n "$canonical_id" ]]; then
    local clean_request
    if [[ "$mode" == "bootstrap" ]]; then
      clean_request="대화 채널 바인딩 수동 갱신 (Bootstrap)"
    else
      clean_request="$(printf '%s' "${request:-}" | tr '\n' ' ' | sed -e 's/[[:space:]]\{1,\}/ /g' | cut -c 1-200)"
    fi
    local notify_msg="[Jammini Dispatch] 역할: ${role} | 범위: ${scope:-작업 분석} | 일감 수신: ${clean_request}"
    local notify_err
    notify_err="$(mktemp)"
    if ! "$ag_send" "$canonical_id" "$notify_msg" >/dev/null 2>"$notify_err"; then
      local err_content
      err_content="$(cat "$notify_err" 2>/dev/null || true)"
      printf 'jammini_delegate: warning: failed to send status update to root conversation (%s): %s\n' "$canonical_id" "$err_content" >&2
    fi
    rm -f "$notify_err"
  fi

  exec "$ag_send" "$target_conv" "$prompt"
}

case "$mode" in
  bootstrap)
    if [[ -n "$conversation_id" ]]; then
      cache_dir="${XDG_CACHE_HOME:-$HOME/.cache}/antigravity-send"
      mkdir -p "$cache_dir"
      printf '%s\n' "$conversation_id" >"$cache_dir/last_conversation_id"
    fi
    send_prompt "$(bootstrap_prompt)"
    ;;
  stop)
    if (( dry_run )); then
      if [[ -n "$conversation_id" ]]; then
        "$ag_stop" --dry-run --conversation-id "$conversation_id"
      else
        "$ag_stop" --dry-run
      fi
    elif [[ -n "$conversation_id" ]]; then
      "$ag_stop" --conversation-id "$conversation_id"
    else
      "$ag_stop"
    fi
    ;;
  "")
    [[ -n "$request" ]] || { usage >&2; exit 1; }
    send_prompt "$(delegate_prompt)"
    ;;
  *)
    echo "unknown mode: $mode" >&2
    exit 1
    ;;
esac
