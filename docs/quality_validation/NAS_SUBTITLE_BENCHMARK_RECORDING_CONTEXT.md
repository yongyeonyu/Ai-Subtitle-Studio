# NAS Subtitle Benchmark Recording Context

작성일: 2026-06-26
대상 계획: `docs/quality_validation/NAS_SUBTITLE_BENCHMARK_50_PLAN.md`
목적: 대표님이 영상별 녹음 상황을 직접 확인해 기록하고, 이후 상황별 자막 품질 튜닝과 LoRA 학습 후보를 분리한다.

## 사용 규칙

- 이 파일은 정답/녹음 상황 기록장이다. 자동 생성 점수만으로 녹음 상황을 확정하지 않는다.
- `owner_confirmed`가 `yes`인 항목만 상황별 튜닝 근거로 사용한다.
- 상황별 튜닝은 STT2, LLM, LoRA, VAD, 모델 선택 정책을 바로 바꾸는 근거가 아니다. 먼저 해당 상황 그룹에서 벤치 점수와 실패 패턴이 반복되는지 확인한다.
- 정답 SRT 자체가 실제 발화와 다르면 `reference_srt_quality`에 반드시 표시한다.
- 컷 경계 정답은 `cut_boundary_truth_status`와 `cut_boundary_notes`에 따로 적는다.

## 권장 태그

녹음 장소:

- `in_car_driving`
- `in_car_stationary`
- `outdoor_event`
- `indoor_event`
- `showroom`
- `motorshow`
- `track_event`
- `garage_or_parking`
- `screen_recording`
- `travel_or_vlog`
- `unknown`

음성/소음:

- `single_speaker`
- `multi_speaker`
- `interview`
- `narration`
- `camera_mic`
- `lav_mic`
- `external_recorder`
- `road_noise`
- `wind_noise`
- `crowd_noise`
- `music_bgm`
- `engine_or_exhaust_noise`
- `echo`
- `low_volume`
- `clipped_audio`
- `unknown_audio`

편집/컷:

- `dense_cuts`
- `long_takes`
- `screen_insert`
- `caption_burned_in`
- `music_only_sections`
- `long_silence`
- `hard_cut_speech_start`
- `reference_starts_before_cut`
- `reference_starts_on_cut`
- `unknown_cut_pattern`

## 항목 작성 템플릿

각 항목은 아래 필드를 사용한다.

```yaml
owner_confirmed: no
recording_situation:
audio_source:
noise_tags: []
speech_tags: []
cut_tags: []
reference_srt_quality:
cut_boundary_truth_status:
cut_boundary_notes:
tuning_notes:
lora_training_notes:
```

## 50 Recording Context Items

### 01. BYD 리뷰

- folder: `[20250117-18][영상]BYD Atto3 시승영상`
- video: `BYD 리뷰.mp4`
- truth: `BYD 리뷰.srt`

```yaml
owner_confirmed: no
recording_situation:
audio_source:
noise_tags: []
speech_tags: []
cut_tags: []
reference_srt_quality:
cut_boundary_truth_status:
cut_boundary_notes:
tuning_notes:
lora_training_notes:
```

### 02. X3 20 xDrive 리뷰

- folder: `[20250118][영상]X3 리뷰`
- video: `X3 20 xDrive 리뷰.MP4`
- truth: `X3 20 xDrive 리뷰.srt`

```yaml
owner_confirmed: no
recording_situation:
audio_source:
noise_tags: []
speech_tags: []
cut_tags: []
reference_srt_quality:
cut_boundary_truth_status:
cut_boundary_notes:
tuning_notes:
lora_training_notes:
```

### 03. KGM 일산익스피리언스 센터

- folder: `[20250208][영상]KGM`
- video: `KGM 일산익스피리언스 센터.mp4`
- truth: `KGM 일산익스피리언스 센터.srt`

```yaml
owner_confirmed: no
recording_situation:
audio_source:
noise_tags: []
speech_tags: []
cut_tags: []
reference_srt_quality:
cut_boundary_truth_status:
cut_boundary_notes:
tuning_notes:
lora_training_notes:
```

### 04. 푸조함평시승

- folder: `[20250214][영상]함평_e-2008 키친205`
- video: `푸조함평시승.MP4`
- truth: `푸조함평시승.srt`

```yaml
owner_confirmed: no
recording_situation:
audio_source:
noise_tags: []
speech_tags: []
cut_tags: []
reference_srt_quality:
cut_boundary_truth_status:
cut_boundary_notes:
tuning_notes:
lora_training_notes:
```

### 05. ACEMAN_SE_JCW_리뷰

- folder: `[20250315-16][영상]미니 페밀리 쇼케이스`
- video: `ACEMAN_SE_JCW_리뷰.MP4`
- truth: `ACEMAN_SE_JCW_리뷰.srt`

```yaml
owner_confirmed: no
recording_situation:
audio_source:
noise_tags: []
speech_tags: []
cut_tags: []
reference_srt_quality:
cut_boundary_truth_status:
cut_boundary_notes:
tuning_notes:
lora_training_notes:
```

### 06. 미니 ACEMAN 시승기

- folder: `[20250315-16][영상]미니 페밀리 쇼케이스`
- video: `미니 ACEMAN 시승기.MP4`
- truth: `미니 ACEMAN 시승기.srt`

```yaml
owner_confirmed: no
recording_situation:
audio_source:
noise_tags: []
speech_tags: []
cut_tags: []
reference_srt_quality:
cut_boundary_truth_status:
cut_boundary_notes:
tuning_notes:
lora_training_notes:
```

### 07. 미니_영종도행사

- folder: `[20250315-16][영상]미니 페밀리 쇼케이스`
- video: `미니_영종도행사.mp4`
- truth: `미니_영종도행사.srt`

```yaml
owner_confirmed: no
recording_situation:
audio_source:
noise_tags: []
speech_tags: []
cut_tags: []
reference_srt_quality:
cut_boundary_truth_status:
cut_boundary_notes:
tuning_notes:
lora_training_notes:
```

### 08. 토레스하이브리스시승

- folder: `[20250329][영상]토레스하이브리드 시승기`
- video: `토레스하이브리스시승.MP4`
- truth: `토레스하이브리스시승.srt`

```yaml
owner_confirmed: no
recording_situation:
audio_source:
noise_tags: []
speech_tags: []
cut_tags: []
reference_srt_quality:
cut_boundary_truth_status:
cut_boundary_notes:
tuning_notes:
lora_training_notes:
```

### 09. BMW

- folder: `[20250403]2025모빌리티쇼`
- video: `BMW.MP4`
- truth: `BMW.srt`

```yaml
owner_confirmed: no
recording_situation:
audio_source:
noise_tags: []
speech_tags: []
cut_tags: []
reference_srt_quality:
cut_boundary_truth_status:
cut_boundary_notes:
tuning_notes:
lora_training_notes:
```

### 10. BYD

- folder: `[20250403]2025모빌리티쇼`
- video: `BYD.mp4`
- truth: `BYD.srt`

```yaml
owner_confirmed: no
recording_situation:
audio_source:
noise_tags: []
speech_tags: []
cut_tags: []
reference_srt_quality:
cut_boundary_truth_status:
cut_boundary_notes:
tuning_notes:
lora_training_notes:
```

### 11. 기아

- folder: `[20250403]2025모빌리티쇼`
- video: `기아.mp4`
- truth: `기아.srt`

```yaml
owner_confirmed: no
recording_situation:
audio_source:
noise_tags: []
speech_tags: []
cut_tags: []
reference_srt_quality:
cut_boundary_truth_status:
cut_boundary_notes:
tuning_notes:
lora_training_notes:
```

### 12. 모터쇼

- folder: `[20250403]2025모빌리티쇼`
- video: `모터쇼.MP4`
- truth: `모터쇼.srt`

```yaml
owner_confirmed: no
recording_situation:
audio_source:
noise_tags: []
speech_tags: []
cut_tags: []
reference_srt_quality:
cut_boundary_truth_status:
cut_boundary_notes:
tuning_notes:
lora_training_notes:
```

### 13. 벤츠

- folder: `[20250403]2025모빌리티쇼`
- video: `벤츠.MP4`
- truth: `벤츠.srt`

```yaml
owner_confirmed: no
recording_situation:
audio_source:
noise_tags: []
speech_tags: []
cut_tags: []
reference_srt_quality:
cut_boundary_truth_status:
cut_boundary_notes:
tuning_notes:
lora_training_notes:
```

### 14. 제네시스

- folder: `[20250403]2025모빌리티쇼`
- video: `제네시스.MP4`
- truth: `제네시스.srt`

```yaml
owner_confirmed: no
recording_situation:
audio_source:
noise_tags: []
speech_tags: []
cut_tags: []
reference_srt_quality:
cut_boundary_truth_status:
cut_boundary_notes:
tuning_notes:
lora_training_notes:
```

### 15. 현대

- folder: `[20250403]2025모빌리티쇼`
- video: `현대.MP4`
- truth: `현대.srt`

```yaml
owner_confirmed: no
recording_situation:
audio_source:
noise_tags: []
speech_tags: []
cut_tags: []
reference_srt_quality:
cut_boundary_truth_status:
cut_boundary_notes:
tuning_notes:
lora_training_notes:
```

### 16. GV80_Black

- folder: `[20250404]HMG드라이빙센터_2025모빌리티쇼_아이오닉9 리뷰`
- video: `GV80_Black.MP4`
- truth: `GV80_Black.srt`

```yaml
owner_confirmed: no
recording_situation:
audio_source:
noise_tags: []
speech_tags: []
cut_tags: []
reference_srt_quality:
cut_boundary_truth_status:
cut_boundary_notes:
tuning_notes:
lora_training_notes:
```

### 17. HMG 드라이빙 익스피리언스

- folder: `[20250404]HMG드라이빙센터_2025모빌리티쇼_아이오닉9 리뷰`
- video: `HMG 드라이빙 익스피리언스.mp4`
- truth: `HMG 드라이빙 익스피리언스.srt`

```yaml
owner_confirmed: no
recording_situation:
audio_source:
noise_tags: []
speech_tags: []
cut_tags: []
reference_srt_quality:
cut_boundary_truth_status:
cut_boundary_notes:
tuning_notes:
lora_training_notes:
```

### 18. 아이오닉9

- folder: `[20250404]HMG드라이빙센터_2025모빌리티쇼_아이오닉9 리뷰`
- video: `아이오닉9.MP4`
- truth: `아이오닉9.srt`

```yaml
owner_confirmed: no
recording_situation:
audio_source:
noise_tags: []
speech_tags: []
cut_tags: []
reference_srt_quality:
cut_boundary_truth_status:
cut_boundary_notes:
tuning_notes:
lora_training_notes:
```

### 19. 오네슈퍼레이스

- folder: `[20250419]오네슈퍼레이스`
- video: `오네슈퍼레이스.MP4`
- truth: `오네슈퍼레이스.srt`

```yaml
owner_confirmed: no
recording_situation:
audio_source:
noise_tags: []
speech_tags: []
cut_tags: []
reference_srt_quality:
cut_boundary_truth_status:
cut_boundary_notes:
tuning_notes:
lora_training_notes:
```

### 20. 포르쉐마칸시승

- folder: `[20250426]포르쉐마칸4 시승`
- video: `포르쉐마칸시승.MP4`
- truth: `포르쉐마칸시승.srt`

```yaml
owner_confirmed: no
recording_situation:
audio_source:
noise_tags: []
speech_tags: []
cut_tags: []
reference_srt_quality:
cut_boundary_truth_status:
cut_boundary_notes:
tuning_notes:
lora_training_notes:
```

### 21. 현대모터스튜디오고양

- folder: `[20250501]현대모터스튜디오고양`
- video: `현대모터스튜디오고양.MP4`
- truth: `현대모터스튜디오고양.srt`

```yaml
owner_confirmed: no
recording_situation:
audio_source:
noise_tags: []
speech_tags: []
cut_tags: []
reference_srt_quality:
cut_boundary_truth_status:
cut_boundary_notes:
tuning_notes:
lora_training_notes:
```

### 22. 미니쿠퍼 장거리

- folder: `[20250505]미니쿠퍼 장거리시승`
- video: `미니쿠퍼 장거리.MP4`
- truth: `미니쿠퍼 장거리.srt`

```yaml
owner_confirmed: no
recording_situation:
audio_source:
noise_tags: []
speech_tags: []
cut_tags: []
reference_srt_quality:
cut_boundary_truth_status:
cut_boundary_notes:
tuning_notes:
lora_training_notes:
```

### 23. 보령모터쇼

- folder: `[20250505]보령모터쇼`
- video: `보령모터쇼.MP4`
- truth: `보령모터쇼.srt`

```yaml
owner_confirmed: no
recording_situation:
audio_source:
noise_tags: []
speech_tags: []
cut_tags: []
reference_srt_quality:
cut_boundary_truth_status:
cut_boundary_notes:
tuning_notes:
lora_training_notes:
```

### 24. CLE드라이브

- folder: `[20250525]CLE200드라이브`
- video: `CLE드라이브.MP4`
- truth: `CLE드라이브.srt`

```yaml
owner_confirmed: no
recording_situation:
audio_source:
noise_tags: []
speech_tags: []
cut_tags: []
reference_srt_quality:
cut_boundary_truth_status:
cut_boundary_notes:
tuning_notes:
lora_training_notes:
```

### 25. M5_1st

- folder: `[20250601]BMW M Fest`
- video: `M5_1st.MP4`
- truth: `M5_1st.srt`

```yaml
owner_confirmed: no
recording_situation:
audio_source:
noise_tags: []
speech_tags: []
cut_tags: []
reference_srt_quality:
cut_boundary_truth_status:
cut_boundary_notes:
tuning_notes:
lora_training_notes:
```

### 26. m3_cs

- folder: `[20250601]BMW M Fest`
- video: `m3_cs.MP4`
- truth: `m3_cs.srt`

```yaml
owner_confirmed: no
recording_situation:
audio_source:
noise_tags: []
speech_tags: []
cut_tags: []
reference_srt_quality:
cut_boundary_truth_status:
cut_boundary_notes:
tuning_notes:
lora_training_notes:
```

### 27. 익스프레스_카밋

- folder: `[20250615]익스프레스카밋`
- video: `익스프레스_카밋.MP4`
- truth: `익스프레스_카밋.srt`

```yaml
owner_confirmed: no
recording_situation:
audio_source:
noise_tags: []
speech_tags: []
cut_tags: []
reference_srt_quality:
cut_boundary_truth_status:
cut_boundary_notes:
tuning_notes:
lora_training_notes:
```

### 28. 420i 컨버터블 시승

- folder: `[20250621]440i 시승`
- video: `420i 컨버터블 시승.MP4`
- truth: `420i 컨버터블 시승.srt`

```yaml
owner_confirmed: no
recording_situation:
audio_source:
noise_tags: []
speech_tags: []
cut_tags: []
reference_srt_quality:
cut_boundary_truth_status:
cut_boundary_notes:
tuning_notes:
lora_training_notes:
```

### 29. GLB250 4MATIC

- folder: `[20250621]GLB250 4MATIC시승`
- video: `GLB250 4MATIC.MP4`
- truth: `GLB250 4MATIC.srt`

```yaml
owner_confirmed: no
recording_situation:
audio_source:
noise_tags: []
speech_tags: []
cut_tags: []
reference_srt_quality:
cut_boundary_truth_status:
cut_boundary_notes:
tuning_notes:
lora_training_notes:
```

### 30. 2025카케어페스티벌

- folder: `[20250628] 카 케어 페스티발`
- video: `2025카케어페스티벌.MP4`
- truth: `2025카케어페스티벌.srt`

```yaml
owner_confirmed: no
recording_situation:
audio_source:
noise_tags: []
speech_tags: []
cut_tags: []
reference_srt_quality:
cut_boundary_truth_status:
cut_boundary_notes:
tuning_notes:
lora_training_notes:
```

### 31. BYD HAN L 분해하기_자막

- folder: `[20250722-24]BYD HAN L`
- video: `BYD HAN L 분해하기_자막.MP4`
- truth: `BYD HAN L 분해하기_자막.srt`

```yaml
owner_confirmed: no
recording_situation:
audio_source:
noise_tags: []
speech_tags: []
cut_tags: []
reference_srt_quality:
cut_boundary_truth_status:
cut_boundary_notes:
tuning_notes:
lora_training_notes:
```

### 32. 마세라티 그레칼레 리뷰

- folder: `[20250730-0801]마세라티 그레칼레 시승`
- video: `마세라티 그레칼레 리뷰.mp4`
- truth: `마세라티 그레칼레 리뷰.srt`

```yaml
owner_confirmed: no
recording_situation:
audio_source:
noise_tags: []
speech_tags: []
cut_tags: []
reference_srt_quality:
cut_boundary_truth_status:
cut_boundary_notes:
tuning_notes:
lora_training_notes:
```

### 33. 마세라티 그레칼레 시승기

- folder: `[20250730-0801]마세라티 그레칼레 시승`
- video: `마세라티 그레칼레 시승기.MP4`
- truth: `마세라티 그레칼레 시승기.srt`

```yaml
owner_confirmed: no
recording_situation:
audio_source:
noise_tags: []
speech_tags: []
cut_tags: []
reference_srt_quality:
cut_boundary_truth_status:
cut_boundary_notes:
tuning_notes:
lora_training_notes:
```

### 34. CLE200_세차

- folder: `[20250802]CLE200세차`
- video: `CLE200_세차.MP4`
- truth: `CLE200_세차.srt`

```yaml
owner_confirmed: no
recording_situation:
audio_source:
noise_tags: []
speech_tags: []
cut_tags: []
reference_srt_quality:
cut_boundary_truth_status:
cut_boundary_notes:
tuning_notes:
lora_training_notes:
```

### 35. BMW X1 m35i

- folder: `[20250822] BMW X1 m35i 시승`
- video: `BMW X1 m35i.MP4`
- truth: `BMW X1 m35i.srt`

```yaml
owner_confirmed: no
recording_situation:
audio_source:
noise_tags: []
speech_tags: []
cut_tags: []
reference_srt_quality:
cut_boundary_truth_status:
cut_boundary_notes:
tuning_notes:
lora_training_notes:
```

### 36. ES300h 시승기

- folder: `[20250913] 렉서스 ES300h 시승`
- video: `ES300h 시승기.MP4`
- truth: `ES300h 시승기.srt`

```yaml
owner_confirmed: no
recording_situation:
audio_source:
noise_tags: []
speech_tags: []
cut_tags: []
reference_srt_quality:
cut_boundary_truth_status:
cut_boundary_notes:
tuning_notes:
lora_training_notes:
```

### 37. ES300h_리뷰

- folder: `[20250913] 렉서스 ES300h 시승`
- video: `ES300h_리뷰.MP4`
- truth: `ES300h_리뷰.srt`

```yaml
owner_confirmed: no
recording_situation:
audio_source:
noise_tags: []
speech_tags: []
cut_tags: []
reference_srt_quality:
cut_boundary_truth_status:
cut_boundary_notes:
tuning_notes:
lora_training_notes:
```

### 38. 미얀마 봉사 ep1

- folder: `[20250921-26] 미얀마해외봉사`
- video: `미얀마 봉사 ep1.MP4`
- truth: `미얀마 봉사 ep1.srt`

```yaml
owner_confirmed: no
recording_situation:
audio_source:
noise_tags: []
speech_tags: []
cut_tags: []
reference_srt_quality:
cut_boundary_truth_status:
cut_boundary_notes:
tuning_notes:
lora_training_notes:
```

### 39. 미얀마 봉사 ep2

- folder: `[20250921-26] 미얀마해외봉사`
- video: `미얀마 봉사 ep2.MP4`
- truth: `미얀마 봉사 ep2.srt`

```yaml
owner_confirmed: no
recording_situation:
audio_source:
noise_tags: []
speech_tags: []
cut_tags: []
reference_srt_quality:
cut_boundary_truth_status:
cut_boundary_notes:
tuning_notes:
lora_training_notes:
```

### 40. 미얀마 봉사 ep3

- folder: `[20250921-26] 미얀마해외봉사`
- video: `미얀마 봉사 ep3.MP4`
- truth: `미얀마 봉사 ep3.srt`

```yaml
owner_confirmed: no
recording_situation:
audio_source:
noise_tags: []
speech_tags: []
cut_tags: []
reference_srt_quality:
cut_boundary_truth_status:
cut_boundary_notes:
tuning_notes:
lora_training_notes:
```

### 41. iX 45 리뷰

- folder: `[20251018]BMW iX45 MSP 시승`
- video: `iX 45 리뷰.MP4`
- truth: `iX 45 리뷰.srt`

```yaml
owner_confirmed: no
recording_situation:
audio_source:
noise_tags: []
speech_tags: []
cut_tags: []
reference_srt_quality:
cut_boundary_truth_status:
cut_boundary_notes:
tuning_notes:
lora_training_notes:
```

### 42. iX45 msp 시승기

- folder: `[20251018]BMW iX45 MSP 시승`
- video: `iX45 msp 시승기.MP4`
- truth: `iX45 msp 시승기.srt`

```yaml
owner_confirmed: no
recording_situation:
audio_source:
noise_tags: []
speech_tags: []
cut_tags: []
reference_srt_quality:
cut_boundary_truth_status:
cut_boundary_notes:
tuning_notes:
lora_training_notes:
```

### 43. 2025 서울 클래식카 쇼

- folder: `[20251024] 서울 클래식카 쇼`
- video: `2025 서울 클래식카 쇼.MP4`
- truth: `2025 서울 클래식카 쇼.srt`

```yaml
owner_confirmed: no
recording_situation:
audio_source:
noise_tags: []
speech_tags: []
cut_tags: []
reference_srt_quality:
cut_boundary_truth_status:
cut_boundary_notes:
tuning_notes:
lora_training_notes:
```

### 44. 2025_벤츠_신형_E클래스_E200_1000만원할인_시승기_CLE비교

- folder: `[20251118] E200 시승기`
- video: `2025_벤츠_신형_E클래스_E200_1000만원할인_시승기_CLE비교.MP4`
- truth: `2025_벤츠_신형_E클래스_E200_1000만원할인_시승기_CLE비교.srt`

```yaml
owner_confirmed: no
recording_situation:
audio_source:
noise_tags: []
speech_tags: []
cut_tags: []
reference_srt_quality:
cut_boundary_truth_status:
cut_boundary_notes:
tuning_notes:
lora_training_notes:
```

### 45. BMW 220 M Sports Design 시승기

- folder: `[20251207]BMW 220 MSP Desgin`
- video: `BMW 220 M Sports Design 시승기.MP4`
- truth: `BMW 220 M Sports Design 시승기.srt`

```yaml
owner_confirmed: no
recording_situation:
audio_source:
noise_tags: []
speech_tags: []
cut_tags: []
reference_srt_quality:
cut_boundary_truth_status:
cut_boundary_notes:
tuning_notes:
lora_training_notes:
```

### 46. AMG CLE 53 시승기

- folder: `[20260207]AMG CLE 53 Cabriolet`
- video: `AMG CLE 53 시승기.MP4`
- truth: `AMG CLE 53 시승기.srt`

```yaml
owner_confirmed: no
recording_situation:
audio_source:
noise_tags: []
speech_tags: []
cut_tags: []
reference_srt_quality:
cut_boundary_truth_status:
cut_boundary_notes:
tuning_notes:
lora_training_notes:
```

### 47. AMG cle53_리뷰

- folder: `[20260207]AMG CLE 53 Cabriolet`
- video: `AMG cle53_리뷰.mp4`
- truth: `AMG cle53_리뷰.srt`

```yaml
owner_confirmed: no
recording_situation:
audio_source:
noise_tags: []
speech_tags: []
cut_tags: []
reference_srt_quality:
cut_boundary_truth_status:
cut_boundary_notes:
tuning_notes:
lora_training_notes:
```

### 48. 헤이딜러_최종

- folder: `[20260209]헤이딜러광고`
- video: `헤이딜러_최종.MP4`
- truth: `헤이딜러_최종.srt`

```yaml
owner_confirmed: no
recording_situation:
audio_source:
noise_tags: []
speech_tags: []
cut_tags: []
reference_srt_quality:
cut_boundary_truth_status:
cut_boundary_notes:
tuning_notes:
lora_training_notes:
```

### 49. BMW X5 시승기

- folder: `[20260308]BMW X5`
- video: `BMW X5 시승기.MP4`
- truth: `BMW X5 시승기.srt`

```yaml
owner_confirmed: no
recording_situation:
audio_source:
noise_tags: []
speech_tags: []
cut_tags: []
reference_srt_quality:
cut_boundary_truth_status:
cut_boundary_notes:
tuning_notes:
lora_training_notes:
```

### 50. 카이엔 일렉트릭 리뷰

- folder: `[20260327]카이엔 전기차`
- video: `카이엔 일렉트릭 리뷰.MP4`
- truth: `카이엔 일렉트릭 리뷰.srt`

```yaml
owner_confirmed: no
recording_situation:
audio_source:
noise_tags: []
speech_tags: []
cut_tags: []
reference_srt_quality:
cut_boundary_truth_status:
cut_boundary_notes:
tuning_notes:
lora_training_notes:
```

## Extra Recording Context Candidates

### 51. BMW X1 m35i 리뷰

- folder: `[20250822] BMW X1 m35i 시승`
- video: `BMW X1 m35i 리뷰.MP4`
- truth: `BMW X1 m35i 리뷰.srt`

```yaml
owner_confirmed: no
recording_situation:
audio_source:
noise_tags: []
speech_tags: []
cut_tags: []
reference_srt_quality:
cut_boundary_truth_status:
cut_boundary_notes:
tuning_notes:
lora_training_notes:
```

### 52. M FEST 2026

- folder: `[20260425] BMW M FEST 2026`
- video: `M FEST 2026.mp4`
- truth: `M FEST 2026.srt`

```yaml
owner_confirmed: no
recording_situation:
audio_source:
noise_tags: []
speech_tags: []
cut_tags: []
reference_srt_quality:
cut_boundary_truth_status:
cut_boundary_notes:
tuning_notes:
lora_training_notes:
```
