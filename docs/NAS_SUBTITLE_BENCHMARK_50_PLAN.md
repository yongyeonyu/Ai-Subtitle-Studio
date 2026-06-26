# NAS Subtitle Benchmark 50 Action Plan

작성일: 2026-06-26
대상 NAS 루트: `/Volumes/photo/22_유튜브영상_개인`
앱 버전 기준: `04.00.17`
기본 실행 모드: High
녹음 상황 기록: `docs/NAS_SUBTITLE_BENCHMARK_RECORDING_CONTEXT.md`

## 목적

NAS 원본 영상과 기존 정답 SRT를 기준으로 AI Subtitle Studio 현재 버전의 High 생성 결과를 50개 fixture에 대해 반복 측정한다.

각 fixture는 해당 원본 폴더 안에 `자막벤치` 폴더를 만들고, 아래 파일을 남긴다.

- `{영상이름}_정답_{YYYYMMDD}.srt`
- `{영상이름}_벤치_v04.00.17_{YYYYMMDD}.srt`
- `{영상이름}_벤치_v04.00.17_{YYYYMMDD}.txt`

## 고정 규칙

- NAS 영상에서 직접 실행한다. MacBook 로컬 `test video` 폴더를 재생성하거나 복사본을 만들지 않는다.
- 기존 원본 영상/SRT는 수정하지 않는다.
- `자막벤치` 폴더는 fixture 폴더별로 만든다. 한 폴더에 영상이 여러 개 있으면 같은 `자막벤치` 폴더 안에 파일명으로 구분한다.
- 정답 SRT는 실행 시점에 `자막벤치`로 복사한다.
- 벤치 생성 SRT/TXT는 같은 날짜/버전 파일이 있으면 덮어쓰지 말고 suffix를 붙인다.
- 텍스트 정확도 판정에서 괄호 안 주석과 ASCII dash `-`는 제외한다.
- 시간 점수는 시작시간을 최우선으로 본다. 기본 가중은 시작 70%, 종료 30%다.
- 컷 경계 검수는 자동 detector 결과와 owner check 결과를 분리한다.
- STT2, LLM, LoRA, VAD, 모델 선택 정책은 이 벤치 계획 때문에 바꾸지 않는다.

## 실행 트리거

대표님이 `1번 벤치마킹하자`처럼 번호를 지정하면 해당 액션아이템 하나만 실행한다.

실행 순서:

1. 대상 영상/SRT 존재 확인
2. 대상 폴더에 `자막벤치` 생성
3. 정답 SRT 복사: `{영상이름}_정답_{YYYYMMDD}.srt`
4. 현재 앱 버전 High 모드로 자막 생성
5. 생성 SRT 저장: `{영상이름}_벤치_v04.00.17_{YYYYMMDD}.srt`
6. 비교 TXT 저장: `{영상이름}_벤치_v04.00.17_{YYYYMMDD}.txt`
7. TXT에 성능표, 컷 경계 detector/check 블록, low-score 원인 후보, LoRA 학습 후보를 포함
8. `docs/NAS_SUBTITLE_BENCHMARK_RECORDING_CONTEXT.md`에서 owner-confirmed 녹음 상황 태그를 읽어 상황별 원인 후보를 함께 기록
9. 50개 전체 진행 시 전체 순위표를 갱신

## TXT 리포트 포맷

각 `{영상이름}_벤치_v04.00.17_{YYYYMMDD}.txt`는 아래 섹션을 포함한다.

```text
# Truth Pair
truth_video=
truth_subtitle=
pair_basis=exact_stem_match

# Benchmark Metadata
video=
truth_srt=
truth_copy=
generated_srt=
app_version=04.00.17
mode=high
created_at=

# Score Summary
| metric | value |
| --- | --- |
| quality_score | |
| cer | |
| text_score | |
| timing_mae_sec | |
| start_timing_mae_sec | |
| end_timing_mae_sec | |
| start_weighted_timing_mae_sec | |
| overlap_score | |
| reference_segments | |
| generated_segments | |

# Worst Timing Rows
| rank | ref_start | hyp_start | start_err | ref_end | hyp_end | end_err | ref_text | hyp_text |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |

# Low Score Cause Notes
- scoring_false_negative:
- reference_mismatch_candidate:
- generation_error_candidate:
- cut_boundary_candidate:
- owner_review_needed:

# Cut Boundary Review
[det]{001|time=|frame=|score=|source=auto|note=}
[det]{002|time=|frame=|score=|source=auto|note=}
[check]{001-037}

# Manual Missing Cut Boundary Additions
# owner may append lines below; Dex will sort by time/frame on next pass.
[missing]{time=|frame=|note=}

# LoRA Training Candidates
# Add only reviewable evidence. Owner-confirmed rows can later be promoted into training data.
{"status":"pending_owner_check","reason":"","ref_start":0.0,"ref_end":0.0,"reference_text":"","generated_text":"","suggested_text":"","notes":""}
```

## 컷 경계 검수 포맷 제안

대표님 확정 기준은 `[det]{번호|time=|frame=|score=}` + `[check]{001-037}` + `[missing]{time=|frame=}` 구조다.

권장 형식:

```text
[det]{001|time=12.345|frame=740|score=0.91}
[check]{001-037}
[missing]{time=15.200|frame=912}
```

의미:

- `[det]`: detector가 찾은 컷 경계 후보
- `[check]`: 대표님이 실제로 맞다고 확인한 detector 번호 범위 또는 목록
- `[missing]`: detector가 놓친 컷 경계를 대표님이 하단에 추가한 것

다음 Dex 실행 시 처리:

- `[det]`와 `[missing]`을 모두 time/frame 기준으로 정렬
- 중복 후보는 같은 시간대 tolerance 안에서 병합 후보로 표시
- `[check]`는 detector 번호를 재번호 매김 후 다시 매핑
- TXT 하단에 owner 확인이 필요한 충돌 행을 남김

## 50개 완료 후 전체 순위 산출

50개 실행이 끝나면 별도 전체 summary를 만든다.

권장 위치:

- repo artifact: `output/manual_verification/latest/nas_subtitle_benchmark_50_{YYYYMMDD}/summary.md`
- NAS root summary: `/Volumes/photo/22_.../자막벤치_전체서머리_v04.00.17_{YYYYMMDD}.md`

전체 순위 기준:

1. start_weighted_timing_score
2. quality_score
3. CER
4. overlap_count / max_overlap
5. reference/generated segment count gap

점수가 낮은 항목의 TXT에는 원인 후보를 별도 기록한다.

원인 후보 예시:

- 정답 SRT와 실제 발화가 다름
- 정답 SRT가 편집 자막이라 STT 발화 시작보다 늦거나 빠름
- detector 컷 경계가 실제 컷과 어긋남
- 영상 내 삽입 자막/화면녹화/음악/환경음이 reference와 혼재
- STT 오인식
- 생성 자막 병합/분할 기준이 정답 SRT와 다름
- benchmark scorer false-negative

## 발견된 exact pair 상태

현재 NAS에서 exact video/SRT stem pair는 52개가 발견됐다. 대표님 요청에 따라 `카이엔 일렉트릭 리뷰`를 primary 50에 포함하고, `M FEST 2026`은 extra 후보로 유지한다.

중복 X1 후보 중 `BMW X1 m35i`를 primary에 남기고 `BMW X1 m35i 리뷰`를 extra 후보로 이동한다.

## 50 Action Items

- [ ] 01. `BYD 리뷰` | folder: `[20250117-18][영상]BYD Atto3 시승영상` | video: `BYD 리뷰.mp4` | truth: `BYD 리뷰.srt`
- [ ] 02. `X3 20 xDrive 리뷰` | folder: `[20250118][영상]X3 리뷰` | video: `X3 20 xDrive 리뷰.MP4` | truth: `X3 20 xDrive 리뷰.srt`
- [ ] 03. `KGM 일산익스피리언스 센터` | folder: `[20250208][영상]KGM` | video: `KGM 일산익스피리언스 센터.mp4` | truth: `KGM 일산익스피리언스 센터.srt`
- [ ] 04. `푸조함평시승` | folder: `[20250214][영상]함평_e-2008 키친205` | video: `푸조함평시승.MP4` | truth: `푸조함평시승.srt`
- [ ] 05. `ACEMAN_SE_JCW_리뷰` | folder: `[20250315-16][영상]미니 페밀리 쇼케이스` | video: `ACEMAN_SE_JCW_리뷰.MP4` | truth: `ACEMAN_SE_JCW_리뷰.srt`
- [ ] 06. `미니 ACEMAN 시승기` | folder: `[20250315-16][영상]미니 페밀리 쇼케이스` | video: `미니 ACEMAN 시승기.MP4` | truth: `미니 ACEMAN 시승기.srt`
- [ ] 07. `미니_영종도행사` | folder: `[20250315-16][영상]미니 페밀리 쇼케이스` | video: `미니_영종도행사.mp4` | truth: `미니_영종도행사.srt`
- [ ] 08. `토레스하이브리스시승` | folder: `[20250329][영상]토레스하이브리드 시승기` | video: `토레스하이브리스시승.MP4` | truth: `토레스하이브리스시승.srt`
- [ ] 09. `BMW` | folder: `[20250403]2025모빌리티쇼` | video: `BMW.MP4` | truth: `BMW.srt`
- [ ] 10. `BYD` | folder: `[20250403]2025모빌리티쇼` | video: `BYD.mp4` | truth: `BYD.srt`
- [ ] 11. `기아` | folder: `[20250403]2025모빌리티쇼` | video: `기아.mp4` | truth: `기아.srt`
- [ ] 12. `모터쇼` | folder: `[20250403]2025모빌리티쇼` | video: `모터쇼.MP4` | truth: `모터쇼.srt`
- [ ] 13. `벤츠` | folder: `[20250403]2025모빌리티쇼` | video: `벤츠.MP4` | truth: `벤츠.srt`
- [ ] 14. `제네시스` | folder: `[20250403]2025모빌리티쇼` | video: `제네시스.MP4` | truth: `제네시스.srt`
- [ ] 15. `현대` | folder: `[20250403]2025모빌리티쇼` | video: `현대.MP4` | truth: `현대.srt`
- [ ] 16. `GV80_Black` | folder: `[20250404]HMG드라이빙센터_2025모빌리티쇼_아이오닉9 리뷰` | video: `GV80_Black.MP4` | truth: `GV80_Black.srt`
- [ ] 17. `HMG 드라이빙 익스피리언스` | folder: `[20250404]HMG드라이빙센터_2025모빌리티쇼_아이오닉9 리뷰` | video: `HMG 드라이빙 익스피리언스.mp4` | truth: `HMG 드라이빙 익스피리언스.srt`
- [ ] 18. `아이오닉9` | folder: `[20250404]HMG드라이빙센터_2025모빌리티쇼_아이오닉9 리뷰` | video: `아이오닉9.MP4` | truth: `아이오닉9.srt`
- [ ] 19. `오네슈퍼레이스` | folder: `[20250419]오네슈퍼레이스` | video: `오네슈퍼레이스.MP4` | truth: `오네슈퍼레이스.srt`
- [ ] 20. `포르쉐마칸시승` | folder: `[20250426]포르쉐마칸4 시승` | video: `포르쉐마칸시승.MP4` | truth: `포르쉐마칸시승.srt`
- [ ] 21. `현대모터스튜디오고양` | folder: `[20250501]현대모터스튜디오고양` | video: `현대모터스튜디오고양.MP4` | truth: `현대모터스튜디오고양.srt`
- [ ] 22. `미니쿠퍼 장거리` | folder: `[20250505]미니쿠퍼 장거리시승` | video: `미니쿠퍼 장거리.MP4` | truth: `미니쿠퍼 장거리.srt`
- [ ] 23. `보령모터쇼` | folder: `[20250505]보령모터쇼` | video: `보령모터쇼.MP4` | truth: `보령모터쇼.srt`
- [ ] 24. `CLE드라이브` | folder: `[20250525]CLE200드라이브` | video: `CLE드라이브.MP4` | truth: `CLE드라이브.srt`
- [ ] 25. `M5_1st` | folder: `[20250601]BMW M Fest` | video: `M5_1st.MP4` | truth: `M5_1st.srt`
- [ ] 26. `m3_cs` | folder: `[20250601]BMW M Fest` | video: `m3_cs.MP4` | truth: `m3_cs.srt`
- [ ] 27. `익스프레스_카밋` | folder: `[20250615]익스프레스카밋` | video: `익스프레스_카밋.MP4` | truth: `익스프레스_카밋.srt`
- [ ] 28. `420i 컨버터블 시승` | folder: `[20250621]440i 시승` | video: `420i 컨버터블 시승.MP4` | truth: `420i 컨버터블 시승.srt`
- [ ] 29. `GLB250 4MATIC` | folder: `[20250621]GLB250 4MATIC시승` | video: `GLB250 4MATIC.MP4` | truth: `GLB250 4MATIC.srt`
- [ ] 30. `2025카케어페스티벌` | folder: `[20250628] 카 케어 페스티발` | video: `2025카케어페스티벌.MP4` | truth: `2025카케어페스티벌.srt`
- [ ] 31. `BYD HAN L 분해하기_자막` | folder: `[20250722-24]BYD HAN L` | video: `BYD HAN L 분해하기_자막.MP4` | truth: `BYD HAN L 분해하기_자막.srt`
- [ ] 32. `마세라티 그레칼레 리뷰` | folder: `[20250730-0801]마세라티 그레칼레 시승` | video: `마세라티 그레칼레 리뷰.mp4` | truth: `마세라티 그레칼레 리뷰.srt`
- [ ] 33. `마세라티 그레칼레 시승기` | folder: `[20250730-0801]마세라티 그레칼레 시승` | video: `마세라티 그레칼레 시승기.MP4` | truth: `마세라티 그레칼레 시승기.srt`
- [ ] 34. `CLE200_세차` | folder: `[20250802]CLE200세차` | video: `CLE200_세차.MP4` | truth: `CLE200_세차.srt`
- [ ] 35. `BMW X1 m35i` | folder: `[20250822] BMW X1 m35i 시승` | video: `BMW X1 m35i.MP4` | truth: `BMW X1 m35i.srt`
- [ ] 36. `ES300h 시승기` | folder: `[20250913] 렉서스 ES300h 시승` | video: `ES300h 시승기.MP4` | truth: `ES300h 시승기.srt`
- [ ] 37. `ES300h_리뷰` | folder: `[20250913] 렉서스 ES300h 시승` | video: `ES300h_리뷰.MP4` | truth: `ES300h_리뷰.srt`
- [ ] 38. `미얀마 봉사 ep1` | folder: `[20250921-26] 미얀마해외봉사` | video: `미얀마 봉사 ep1.MP4` | truth: `미얀마 봉사 ep1.srt`
- [ ] 39. `미얀마 봉사 ep2` | folder: `[20250921-26] 미얀마해외봉사` | video: `미얀마 봉사 ep2.MP4` | truth: `미얀마 봉사 ep2.srt`
- [ ] 40. `미얀마 봉사 ep3` | folder: `[20250921-26] 미얀마해외봉사` | video: `미얀마 봉사 ep3.MP4` | truth: `미얀마 봉사 ep3.srt`
- [ ] 41. `iX 45 리뷰` | folder: `[20251018]BMW iX45 MSP 시승` | video: `iX 45 리뷰.MP4` | truth: `iX 45 리뷰.srt`
- [ ] 42. `iX45 msp 시승기` | folder: `[20251018]BMW iX45 MSP 시승` | video: `iX45 msp 시승기.MP4` | truth: `iX45 msp 시승기.srt`
- [ ] 43. `2025 서울 클래식카 쇼` | folder: `[20251024] 서울 클래식카 쇼` | video: `2025 서울 클래식카 쇼.MP4` | truth: `2025 서울 클래식카 쇼.srt`
- [ ] 44. `2025_벤츠_신형_E클래스_E200_1000만원할인_시승기_CLE비교` | folder: `[20251118] E200 시승기` | video: `2025_벤츠_신형_E클래스_E200_1000만원할인_시승기_CLE비교.MP4` | truth: `2025_벤츠_신형_E클래스_E200_1000만원할인_시승기_CLE비교.srt`
- [ ] 45. `BMW 220 M Sports Design 시승기` | folder: `[20251207]BMW 220 MSP Desgin` | video: `BMW 220 M Sports Design 시승기.MP4` | truth: `BMW 220 M Sports Design 시승기.srt`
- [ ] 46. `AMG CLE 53 시승기` | folder: `[20260207]AMG CLE 53 Cabriolet` | video: `AMG CLE 53 시승기.MP4` | truth: `AMG CLE 53 시승기.srt`
- [ ] 47. `AMG cle53_리뷰` | folder: `[20260207]AMG CLE 53 Cabriolet` | video: `AMG cle53_리뷰.mp4` | truth: `AMG cle53_리뷰.srt`
- [ ] 48. `헤이딜러_최종` | folder: `[20260209]헤이딜러광고` | video: `헤이딜러_최종.MP4` | truth: `헤이딜러_최종.srt`
- [ ] 49. `BMW X5 시승기` | folder: `[20260308]BMW X5` | video: `BMW X5 시승기.MP4` | truth: `BMW X5 시승기.srt`
- [ ] 50. `카이엔 일렉트릭 리뷰` | folder: `[20260327]카이엔 전기차` | video: `카이엔 일렉트릭 리뷰.MP4` | truth: `카이엔 일렉트릭 리뷰.srt`

## Extra Candidates

These two exact pairs are outside the confirmed primary 50. They can replace a primary item or be run as 51-52 if the owner wants a 52-item sweep.

- [ ] 51. `BMW X1 m35i 리뷰` | folder: `[20250822] BMW X1 m35i 시승` | video: `BMW X1 m35i 리뷰.MP4` | truth: `BMW X1 m35i 리뷰.srt`
- [ ] 52. `M FEST 2026` | folder: `[20260425] BMW M FEST 2026` | video: `M FEST 2026.mp4` | truth: `M FEST 2026.srt`

## Confirmed Decisions

1. Primary 50 selection is confirmed as sorted-first list with `카이엔 일렉트릭 리뷰` added and `BMW X1 m35i 리뷰` moved to extra.
2. Cut-boundary check format is confirmed as `[check]{001-037}` for a continuous detector-number range. The parser should still tolerate `[check]{001,004,008}` later if representative review needs sparse selections.
3. LoRA training rows should stay `pending_owner_check` until 대표님 confirms the reference/generated/suggested text is correct. This avoids teaching the model from a wrong answer sheet.
