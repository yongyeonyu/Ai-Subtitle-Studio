# AI Subtitle Studio SVG Icon Assets

이 폴더는 앱 UI에서 사용하는 직접 수정 가능한 SVG 아이콘 자산입니다.

## 폴더

- `ui/`: 하단 메뉴, 사이드바, 상태/모드 버튼, 설정창, 러프컷, 타임라인 공용 아이콘
- `app_icon.svg`: 앱 창/실행 아이콘 후보 자산

## 규칙

- 기본 크기는 `24x24` viewBox를 사용합니다.
- 색상은 `currentColor`로 지정합니다.
- 실제 색상은 `ui/style.py`의 `line_icon(name, color, size)` 호출에서 전달합니다.
- 선 아이콘은 `fill="none"`, `stroke="currentColor"`, `stroke-linecap="round"`, `stroke-linejoin="round"`를 기본으로 합니다.
- 의미가 같은 이름은 `ui/style.py`의 alias에서 공용 SVG로 연결합니다.
  - 예: `stt -> mic`, `gap -> sliders`, `document -> file`, `write -> edit`

## 수정 방법

1. `assets/icons/ui/{아이콘명}.svg`를 직접 수정합니다.
2. 앱을 다시 실행하면 변경된 SVG가 반영됩니다.
3. 새 아이콘을 추가할 때는 파일명을 영문 소문자 snake/kebab 없이 단일 단어로 맞추고, 필요하면 `ui/style.py`의 `_ICON_ALIASES`에 연결합니다.

## Fallback

SVG 파일이 없거나 렌더링에 실패하면 `ui/style.py`의 기존 QPainter 기반 아이콘으로 자동 fallback 됩니다.
