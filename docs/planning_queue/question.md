# G4 Roughcut Scenario Composer Questions

Purpose: unresolved owner questions for the G4 roughcut scenario composer, roughcut editor, shortform handoff, save/reopen, export, and restore workflow.

How to answer: write under each `대표님 답변:` line. Short answers are fine. If a question is not important for the first implementation slice, write `나중에`.

Reference artifacts:

- `docs/planning_queue/ACTION_ITEMS.md` - `G4. Roughcut Scenario Composer And Generation Plan`
- `output/manual_verification/latest/g4_roughcut_demo_board_20260630/g4_roughcut_demo_board.png`
- `output/manual_verification/latest/g4_roughcut_demo_board_20260630/g4_roughcut_demo_flow_h264.mp4`
- `output/manual_verification/latest/g4_roughcut_demo_board_20260630/SCENARIO_MEETING_NOTES.md`

## Priority Questions

1. First roughcut entry default selection

Question: 러프컷 에디터에 처음 들어왔을 때 기본으로 선택되어 있어야 하는 순서는 `기본순서(에디터 편집 순서)`인가요, `LLM 추천 순서`인가요?

Dex assumption: `기본순서(에디터 편집 순서)`를 기본 선택으로 열고, `LLM 추천 순서`는 바로 옆 후보로 보여줍니다.

대표님 답변:

2. Roughcut -> Editor commit timing

Question: 러프컷에서 카드 순서, 분할, 통합, 길이 조정을 했을 때 에디터에 반영되는 시점은 언제여야 하나요?

Options to clarify: `드래그 즉시`, `적용/커밋 버튼을 눌렀을 때`, `저장 버튼을 눌렀을 때`, `시나리오 확정 버튼을 눌렀을 때`.

Dex assumption: preview는 즉시 보이지만, 에디터/NLE에 실제 반영은 명시적 `적용/커밋` 경계에서만 합니다.

대표님 답변:

3. Editor changes while roughcut has manual work

Question: 러프컷에서 수동으로 시나리오를 조립한 뒤, 메인 에디터에서 자막을 수정하면 러프컷은 자동 갱신해야 하나요, 아니면 `변경 감지됨 - 갱신/유지 선택` 같은 확인을 받아야 하나요?

Dex assumption: 카드 텍스트/시간은 최신 NLE projection으로 갱신하되, LLM 요약/관계 점수/숏폼 후보는 stale 표시하고 자동 재작성하지 않습니다.

대표님 답변:

4. Practice notebook behavior

Question: 연습노트 A/B/C는 자동 저장되어야 하나요, 아니면 사용자가 `연습노트 저장`을 눌러야 저장되어야 하나요?

Dex assumption: 수동 편집 중인 현재 노트는 임시 자동 백업하고, 이름 있는 연습노트는 사용자가 저장/복제/불러오기 할 수 있게 합니다.

대표님 답변:

5. Seed switching after manual edits

Question: 수동 조립 후 `기본순서`와 `LLM 추천 순서`를 전환할 때 어떤 UX가 맞나요?

Options to clarify: `항상 경고`, `자동으로 임시 백업 후 전환`, `저장하지 않으면 전환 불가`, `그냥 전환`.

Dex assumption: 자동 임시 백업을 만든 뒤 경고/확인하고 전환합니다.

대표님 답변:

6. Split through an active subtitle row

Question: 중분류 세그먼트를 자를 때 컷 지점이 자막 한 줄의 중간을 지나면 어떻게 처리해야 하나요?

Options to clarify: `가까운 자막 경계로 스냅`, `자막 텍스트를 둘로 나눔`, `분할 차단 후 경고`, `사용자 선택`.

Dex assumption: 첫 구현은 가까운 자막 경계로 스냅하고, 애매하면 경고/차단합니다.

대표님 답변:

7. Merge rules

Question: 중분류 세그먼트 통합은 시간상 인접한 카드끼리만 허용할까요, 아니면 떨어진 카드도 시나리오 순서 기준으로 통합할 수 있게 할까요?

Dex assumption: 첫 구현은 인접 또는 같은 시나리오 묶음 안의 카드만 안전하게 통합하고, 떨어진 원본 구간 통합은 review-required로 둡니다.

대표님 답변:

8. Alternate take and B-roll scope

Question: 대체 테이크, B-roll, insert, reaction 레이어는 G4 첫 구현에 실제 기능으로 포함할까요, 아니면 데모/설계에만 남기고 후속 단계로 미룰까요?

Dex assumption: 첫 구현은 metadata/preview 설계만 만들고, 실제 다중 비디오 레이어 편집은 후속 단계로 둡니다.

대표님 답변:

9. Settings box editable fields

Question: 설정박스에서 사용자가 직접 수정할 수 있어야 하는 필드는 어디까지인가요?

Current plan: `주제`, `태그`, `요약/메모`, `관계 점수`, `리뷰 상태`는 편집 가능. `자막 원문`, `시작/종료 시간`, `duration`은 read-only 또는 컷 편집 경로만 허용.

대표님 답변:

10. Relationship score scale

Question: 컷 궁합 점수는 `0..100` 숫자로 고정할까요, 아니면 `좋음/보통/나쁨` 같은 단계형도 같이 보여줄까요?

Dex assumption: 내부 값은 `0..100`, UI는 색상/선/라벨을 같이 보여줍니다.

대표님 답변:

11. Manual relationship priority

Question: 대표님이 직접 입력한 컷 관계 점수와 LLM/자동 점수가 충돌하면, 항상 대표님 수동 입력이 우선인가요?

Dex assumption: 수동 입력이 항상 최우선이고, LLM/자동 점수는 제안만 합니다.

대표님 답변:

12. LLM rewrite trigger

Question: 시나리오 줄거리/요약/대본 재작성은 언제 실행되어야 하나요?

Options to clarify: `사용자가 버튼 클릭`, `카드 이동 후 자동 debounce`, `저장 시 자동`, `시나리오 확정 전 자동`.

Dex assumption: 첫 구현은 사용자가 명시적으로 `재작성`을 누를 때만 실행합니다.

대표님 답변:

13. LLM privacy mode

Question: 러프컷 LLM이 외부 API를 쓸 수 있나요, 아니면 로컬/내부 모델만 우선해야 하나요?

Dex assumption: App Store/privacy 안정성을 위해 외부 전송은 명시적 사용자 실행 + redacted summary 우선 + privacy gate 뒤에 둡니다.

대표님 답변:

14. Shortform 60-second boundary

Question: 숏폼 제한은 정확히 `60.0초 이하`인가요? `60.000초`는 허용하고 `60.001초`부터 차단하면 될까요?

Dex assumption: `<= 60.0`은 허용, `> 60.0`은 차단합니다. 단, QE 검토에서는 부동소수점 안전을 위해 경계 여유를 둘 수 있습니다.

대표님 답변:

15. Shortform maker first output

Question: 숏폼 제작기의 첫 결과물은 무엇이어야 하나요?

Options to clarify: `9:16 미리보기만`, `숏폼 draft 저장`, `숏폼 MP4 출력`, `자막 스타일 적용까지`, `SNS 업로드 제외`.

Dex assumption: 첫 구현은 9:16 preview + draft 저장 + 로컬 MP4 출력 계획까지만, SNS 업로드/계정/클라우드는 제외합니다.

대표님 답변:

16. Save button scope

Question: `저장` 버튼을 누를 때 stale/review-required 상태도 그대로 저장해야 하나요, 아니면 stale 상태가 있으면 저장을 막아야 하나요?

Dex assumption: stale 상태도 저장하되, reopen 시 stale/review-required로 표시합니다. 최종 출력/커밋만 차단합니다.

대표님 답변:

17. Original baseline definition

Question: `원본으로 돌리기`의 원본 기준은 무엇인가요?

Options to clarify: `처음 생성된 자막`, `처음 불러온 SRT`, `대표님이 첫 저장한 상태`, `프로젝트 열 때의 상태`.

Dex assumption: 외부 SRT가 있으면 최초 import SRT, 없으면 첫 accepted generated subtitle state를 원본 baseline으로 둡니다.

대표님 답변:

18. Scenario export collision

Question: `_시나리오.srt` 또는 `_시나리오.mp4` 파일이 이미 있을 때 기본 동작은 무엇이어야 하나요?

Options to clarify: `덮어쓰기 확인`, `자동 번호 붙이기`, `timestamp 붙이기`, `항상 다른 이름으로 저장`.

Dex assumption: 기본은 자동 번호/timestamp로 새 파일을 만들고, 덮어쓰기는 명시 확인을 요구합니다.

대표님 답변:

19. Scenario SRT timing basis

Question: `_시나리오.srt`의 시간은 원본 영상 시간 기준인가요, 재조립된 `_시나리오.mp4` 출력 타임라인 기준인가요?

Dex assumption: `_시나리오.srt`는 재조립된 `_시나리오.mp4` 타임라인 기준입니다.

대표님 답변:

20. First implementation slice

Question: G4를 실제 구현할 때 첫 번째로 만들 화면/기능은 무엇이어야 하나요?

Options to clarify: `4박스 빈 화면`, `기본순서/LLM추천 시드`, `재료카드 drag/drop`, `저장/reopen`, `시나리오 재작성`, `숏폼 바구니`.

Dex assumption: 첫 slice는 4박스 빈 화면 + 기존 UI 숨김 + 기본순서/LLM추천 시드 표시 + 저장/reopen skeleton까지가 안전합니다.

대표님 답변:

21. Demo board visual direction

Question: 현재 데모보드처럼 어두운 기존 앱 톤에 흰/파/노/빨 테두리로 역할만 보여주는 방향이 맞나요, 아니면 실제 구현에서는 더 강한 색상 박스로 보여줘야 하나요?

Dex assumption: 기존 앱의 다크 톤을 유지하고, 색상은 테두리/헤더/상태 강조로만 사용합니다.

대표님 답변:

22. User-facing labels

Question: 실제 UI 라벨은 한국어 중심으로 갈까요, 아니면 `Scenario`, `Material`, `Video`, `Settings` 같은 영어 병기를 넣을까요?

Dex assumption: 대표님 지정 용어인 `시나리오박스`, `재료박스`, `비디오박스`, `설정박스`를 우선하고, 내부 개발 objectName만 영어로 둡니다.

대표님 답변:

23. Trace/debug visibility

Question: UI/UX trace는 일반 사용자 화면에도 상태로 보여줄까요, 아니면 내부 로그/진단 번들로만 남길까요?

Dex assumption: 일반 UI에는 최소 상태만 보여주고, 자세한 trace는 redacted local diagnostic bundle로만 내보냅니다.

대표님 답변:

24. App Store release scope

Question: G4 러프컷/숏폼 기능은 App Store 첫 제출 후보에 포함해야 하나요, 아니면 source-app에서 충분히 검증한 뒤 다음 버전으로 미루는 게 맞나요?

Dex assumption: G4는 source-app/local proof를 먼저 만들고, App Store 제출 포함은 별도 G0 privacy/sandbox/signing proof 후 결정합니다.

대표님 답변:

25. Evidence expected after first implementation

Question: 첫 구현 완료 후 대표님이 보고 싶은 증거는 무엇인가요?

Options to clarify: `스크린샷`, `동작 영상`, `save/reopen 파일`, `SRT/MP4 출력물`, `QA 로그`, `전체`.

Dex assumption: 최소 증거는 스크린샷 + 동작 영상 + save/reopen + scenario export naming proof입니다.

대표님 답변:
