# Version: 03.02.10
# Phase: PHASE2
"""Structured help content used by the main help dialog."""

HELP_TABS = [
    {
        "title": "시작 / 프로젝트",
        "summary": "파일, 폴더, iCloud/NAS 자동처리, 프로젝트 저장과 불러오기를 시작하는 영역입니다.",
        "steps": [
            "왼쪽 사이드바에서 파일 또는 폴더를 열어 단일 클립 작업을 시작합니다.",
            "프로젝트 패널에서 현재 영상, 자막, 러프컷 상태를 확인하고 프로젝트 파일로 저장합니다.",
            "프로젝트 정보는 접기/펼치기로 열 수 있으며, 편집 화면을 유지한 상태에서 상태만 보여줍니다.",
        ],
        "examples": [
            "예시: MP4 하나를 열고 자막 생성 후 프로젝트로 저장하면 다음 실행 때 단일클립 편집 상태로 복원됩니다.",
            "예시: 여러 영상을 추가하면 멀티클립 프로젝트로 저장되며 clip boundary와 자막 상태가 함께 저장됩니다.",
        ],
        "shortcuts": [
            "상황: 프로젝트를 열었는데 자막이 비어 있어도 저장된 영상 상태가 있으면 편집 화면으로 복원됩니다.",
            "상황: 러프컷에서 저장한 프로젝트는 러프컷 상태와 일반 편집 상태를 분리해서 보관합니다.",
        ],
    },
    {
        "title": "자막 생성",
        "summary": "VAD 검토, Whisper 인식, 자막 생성, LLM 교정, 완료 단계로 이어지는 기본 파이프라인입니다.",
        "steps": [
            "하단 시작 버튼을 눌러 현재 파일의 자막 생성 파이프라인을 실행합니다.",
            "처리중에는 버튼이 정지 아이콘으로 바뀌고, 재처리가 가능할 때는 재시작 상태로 전환됩니다.",
            "상단 상태 버튼은 검토, 인식, 생성, 교정, 완료 중 현재 단계에 맞춰 표시됩니다.",
        ],
        "examples": [
            "예시: 긴 영상은 VAD로 음성 구간을 먼저 찾고 Whisper가 각 구간을 인식한 뒤 LLM이 자막을 다듬습니다.",
            "예시: STT 품질 프리셋을 정밀로 바꾸면 처리 시간은 늘지만 누락 구간을 줄이는 데 유리합니다.",
        ],
        "shortcuts": [
            "상황: 생성 직후 바로 재생해도 비디오 플레이어의 자막 overlay가 현재 에디터 자막과 동기화됩니다.",
        ],
    },
    {
        "title": "자막 편집",
        "summary": "자막 텍스트, 시간, 화자, 세그먼트 선택과 타임라인 편집을 다루는 기본 편집 화면입니다.",
        "steps": [
            "자막 리스트에서 항목을 선택하면 디테일 캔버스의 같은 세그먼트가 함께 선택됩니다.",
            "타임라인과 디테일 캔버스는 현재 선택 상태를 노란색 기준선과 테두리로 표시합니다.",
            "Undo와 Redo는 하단 버튼으로 실행하며, 가능한 경우 현재 편집 상태를 되돌리거나 다시 적용합니다.",
        ],
        "examples": [
            "예시: 자막 텍스트 일부를 수정하면 저장 시 SRT와 프로젝트 JSON에 같은 값이 반영됩니다.",
            "예시: 단일클립 자막의 화자명을 수정한 뒤 러프컷으로 돌아가면 러프컷 자막 컨텍스트에도 반영됩니다.",
        ],
        "shortcuts": [
            "상황: Lock Edit이 켜져 있으면 실수로 세그먼트 경계를 움직이는 조작을 제한합니다.",
            "상황: 비디오 화면은 현재 높이 기준 16:9 비율로 고정되어 편집 화면 폭 변화에 맞춰 안정적으로 배치됩니다.",
        ],
    },
    {
        "title": "STT 모드",
        "summary": "마이크 또는 짧은 음성 입력을 빠르게 받아 현재 자막 편집 흐름에 연결하는 모드입니다.",
        "steps": [
            "하단 STT 버튼으로 STT 모드를 켜고 끕니다.",
            "STT가 켜져 있으면 마이크 아이콘이 빨간색, 꺼져 있으면 회색으로 표시됩니다.",
            "STT 결과는 현재 편집 컨텍스트에 맞춰 임시 자막 또는 후보 텍스트로 연결됩니다.",
        ],
        "examples": [
            "예시: 현장에서 짧은 멘트를 다시 받아 자막 후보로 추가한 뒤 편집할 수 있습니다.",
        ],
        "shortcuts": [
            "상황: STT 버튼 텍스트는 ON/OFF 대신 STT로 고정되고, 상태는 아이콘 색으로 확인합니다.",
        ],
    },
    {
        "title": "멀티클립",
        "summary": "여러 영상 파일을 하나의 타임라인으로 이어서 자막과 러프컷에 연결하는 작업 방식입니다.",
        "steps": [
            "단일클립 편집 중 영상을 추가하면 멀티클립 컨텍스트로 전환됩니다.",
            "각 클립은 프로젝트 JSON에 경로, 순서, 시작/종료 boundary를 유지합니다.",
            "자막과 타임라인은 전체 timeline time과 clip-local time을 함께 사용합니다.",
        ],
        "examples": [
            "예시: A 영상 3분, B 영상 2분을 연결하면 B 영상의 첫 자막은 전체 타임라인 3분 이후에 배치됩니다.",
            "예시: 멀티클립에서 러프컷을 만들면 EDL은 실제 source_path와 clip-local source range를 보존합니다.",
        ],
        "shortcuts": [
            "상황: 멀티클립에서 다시 프로젝트를 열면 클립 순서와 자막 상태가 같이 복원됩니다.",
        ],
    },
    {
        "title": "러프컷",
        "summary": "분석된 자막과 장면 정보를 바탕으로 챕터, 스토리 구조, 컷 후보, EDL을 만드는 PHASE2 편집 기능입니다.",
        "steps": [
            "러프컷 편집 도우미에서 현재 단일/멀티클립 자막을 기준으로 분석을 실행합니다.",
            "챕터 테이블에서 사용 여부, 라벨, 컷 후보를 검토하고 필요한 항목만 출력합니다.",
            "EDL, 마크다운 가이드, retimed SRT, 렌더 계획 파일을 저장할 수 있습니다.",
        ],
        "examples": [
            "예시: 단일클립에서 러프컷으로 이동하면 editor_state와 roughcut_state가 프로젝트 안에 분리 저장됩니다.",
            "예시: 러프컷에서 단일클립으로 돌아가 자막을 수정하면 다음 러프컷 진입 때 변경된 자막 signature로 재분석됩니다.",
        ],
        "shortcuts": [
            "상황: 러프컷 결과가 이전 자막과 맞지 않으면 저장된 signature를 비교해서 stale 상태로 보고 재분석합니다.",
            "상황: 멀티클립 러프컷 EDL은 timeline_start/timeline_end와 source_start/source_end를 모두 보존합니다.",
        ],
    },
    {
        "title": "출력 / 저장",
        "summary": "SRT, 화자 SRT, 프로젝트 JSON, 러프컷 산출물, 렌더 계획을 저장하는 기능입니다.",
        "steps": [
            "하단 저장 버튼은 현재 편집 상태와 프로젝트 상태를 저장합니다.",
            "자막 버튼은 내보내기 창을 열어 SRT 또는 관련 자막 파일을 저장합니다.",
            "러프컷 화면에서는 EDL JSON, 편집 가이드, retimed SRT, 렌더 계획을 별도로 저장합니다.",
        ],
        "examples": [
            "예시: 프로젝트 JSON을 저장하면 단일클립, 멀티클립, 러프컷 상태를 다음 작업에서 다시 불러올 수 있습니다.",
            "예시: 화자 정보가 있는 자막은 speaker 값까지 저장되어 재로드 후에도 유지됩니다.",
        ],
        "shortcuts": [
            "상황: 앱 종료 전 저장된 상태는 왼쪽 하단 저장 상태 라벨과 프로젝트 파일로 확인합니다.",
        ],
    },
    {
        "title": "설정 / 모델",
        "summary": "AI 모델, Whisper 품질, 화자, gap, 자동처리 경로와 고급 옵션을 관리합니다.",
        "steps": [
            "하단 AI, 설정, 화자, 간격 버튼으로 각각의 설정 창을 엽니다.",
            "자동설정은 iCloud/NAS 자동처리 경로와 감시 옵션을 관리합니다.",
            "캐쉬삭제는 미리보기/처리 중 생성된 캐시를 정리할 때 사용합니다.",
        ],
        "examples": [
            "예시: Whisper 모델을 large-v3 계열로 두면 한국어 긴 영상 인식 품질이 좋아질 수 있습니다.",
            "예시: gap 설정을 조절하면 너무 짧은 무음 또는 문장 사이 구간을 다루는 방식이 달라집니다.",
        ],
        "shortcuts": [
            "상황: API Key 같은 민감 정보는 평문 문서에 남기지 않는 것을 원칙으로 합니다.",
        ],
    },
    {
        "title": "자동처리 / 큐",
        "summary": "iCloud 또는 NAS 드롭존에 들어온 파일을 감지해 자동으로 처리하고 큐에서 상태를 확인합니다.",
        "steps": [
            "자동 버튼으로 자동처리 상태를 켜거나 끕니다.",
            "사이드바의 큐 리스트에서 파일명, 예상시간과 진행 상태를 확인합니다.",
        ],
        "examples": [
            "예시: iCloud 드롭존에 영상이 들어오면 안정화 시간을 거친 뒤 큐에 등록됩니다.",
            "예시: NAS 자동처리는 설정된 경로가 연결되어 있을 때만 감시를 시작합니다.",
        ],
        "shortcuts": [
            "상황: 자동처리 중 파일이 아직 복사 중이면 안정화 대기 상태로 남습니다.",
        ],
    },
    {
        "title": "단축키 / 문제상황",
        "summary": "자주 마주치는 화면 상태와 문제상황을 빠르게 확인하는 참고 탭입니다.",
        "steps": [
            "재생 관련 단축키와 세부 조작은 현재 에디터/비디오 컨트롤 상태를 따릅니다.",
            "자막이 안 보이면 현재 에디터 자막 provider와 비디오 플레이어 provider 동기화를 먼저 확인합니다.",
            "화면 테두리나 선택 표시가 어긋나면 캔버스 선택 상태와 스크롤 위치를 확인합니다.",
        ],
        "examples": [
            "예시: 생성 직후 비디오 overlay가 비어 있으면 저장된 SRT가 아니라 현재 editor segment provider를 기준으로 표시됩니다.",
            "예시: 러프컷 결과가 예상과 다르면 단일/멀티클립의 현재 자막을 저장한 뒤 러프컷을 다시 실행합니다.",
        ],
        "shortcuts": [
            "상황: 추후 스크린샷이 추가되면 각 탭의 이미지 영역에 실제 화면 예시가 들어갑니다.",
        ],
    },
]


HELP_QA_COVERAGE = {
    "시작 / 프로젝트": {
        "profiles": ["quick", "major"],
        "owners": ["ui/home_ui.py", "ui/editor/editor_segments_reload.py", "core/project/project_manager.py"],
        "artifacts": ["home", "editor restored"],
    },
    "자막 생성": {
        "profiles": ["full"],
        "owners": ["core/pipeline/single_pipeline.py", "core/audio/media_processor_transcribe.py"],
        "artifacts": ["tinyping_full_verify.json", "queue processing"],
    },
    "자막 편집": {
        "profiles": ["major"],
        "owners": ["ui/timeline/timeline_canvas.py", "ui/editor/ux/timeline_inline_text_editor.py"],
        "artifacts": ["timeline full", "inline edit", "split menu"],
    },
    "STT 모드": {
        "profiles": ["major"],
        "owners": ["ui/editor/editor_automation.py", "core/audio/media_processor_transcribe.py"],
        "artifacts": ["menu_stt_lora_macau"],
    },
    "멀티클립": {
        "profiles": ["major"],
        "owners": ["ui/project/multiclip_panel.py", "core/project/project_frames.py"],
        "artifacts": ["multiclip state"],
    },
    "러프컷": {
        "profiles": ["major"],
        "owners": ["core/roughcut", "ui/editor/editor_roughcut_draft.py"],
        "artifacts": ["roughcut view"],
    },
    "출력 / 저장": {
        "profiles": ["major"],
        "owners": ["ui/editor/editor_save_manager.py", "tools/remote_verify.py"],
        "artifacts": ["save_export_macau"],
    },
    "설정 / 모델": {
        "profiles": ["major"],
        "owners": ["ui/settings", "ui/settings/settings_dictionary.py"],
        "artifacts": ["settings", "dictionary"],
    },
    "자동처리 / 큐": {
        "profiles": ["quick", "major"],
        "owners": ["ui/home_sidebar.py", "ui/queue/sidebar_queue_panel.py"],
        "artifacts": ["queue idle", "queue processing"],
    },
    "단축키 / 문제상황": {
        "profiles": ["quick", "major", "full"],
        "owners": ["test_case.md", "README.md", "tools/qa_suite_runner.py"],
        "artifacts": ["suite_result.json", "suite_result.md"],
    },
}
