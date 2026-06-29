DEX_READY
SCOUT_ID=20260629-162317

### G4 NLE 레퍼런스 벤치마킹 및 응답성 최적화 검토 보고서

#### 1. 공식 NLE Reference 벤치마킹 분석
- **Final Cut Pro (Magnetic Timeline)**:
  * *적용*: 카드 삭제, 분할, 병합 시 카드 간 빈 공백(Gap)이 생기지 않도록 자동으로 옆 노드들이 달라붙는 'Magnetic Node Snapping' 구조를 2D 캔버스에 구현하여 타임라인 빈 공간을 능동 제어합니다.
- **DaVinci Resolve (Cut Page / Speed Editor workflow)**:
  * *적용*: 설정박스 내 트림 슬라이더 조작 시, 복잡한 입출력 연산 없이 메모리 내 비디오/자막 인아웃 프레임만 즉각 변경하여 노란색 비디오박스 프리뷰와 싱크를 실시간 업데이트하는 초고속 레이턴시 루프를 도입합니다.
- **Adobe Premiere Productions (Asset reference isolation)**:
  * *적용*: 다중 연습노트 후보군 전환 시 무거운 비디오/오디오 버퍼를 복제하지 않고, 경량의 `Reference ID` 포인터 배열만 교체하여 연습노트 간의 스위칭 속도를 ms 단위로 단축합니다.
- **Lightworks (Database-centric Timeline)**:
  * *적용*: NLE 조작 내역을 디스크가 아닌 인메모리 저널(InMemory Transaction Journal) 단위로 안전하게 누적 트래킹하여, 예기치 못한 크래시에도 100% 무결성을 보장하고 빠른 실행취소(Undo/Redo)를 가능케 합니다.

#### 2. 응답성(Responsiveness) 최적화 계획 및 UI Risk
- **GUI 반응성 가드**: 수백 개의 카드 노드와 연결선이 배치된 2D GraphicsView 캔버스 줌인/패닝 시, PyQt6 Paint 이벤트에서 미사용 객체의 드로잉을 즉각 생략하는 2D 뷰포트 클리핑(Viewport clipping) 최적화가 필수적입니다.
- **비디오-오디오 스레드 락 충돌 방지**: 비디오 재생 버퍼와 자막 렌더링 스레드가 하나의 오디오 디바이스를 호출할 때 스레드 데드락(Deadlock)이 발생하는 리스크가 있으므로, 오디오 스트림은 Core Audio 계층으로 추상화 격리 호출하여 처리해야 합니다.

#### 3. validation checklist
- [ ] 노드 카드 100개 이상 로드 및 패닝 시, CPU/메모리 부하가 임계치를 초과하지 않고 30 FPS 이상 매끄럽게 유지되는지 검증
- [ ] 연습노트(A/B) 간의 전환 시, 레이아웃 갱신 소요 시간이 50ms 미만인지 성능 정밀 프로파일링
- [ ] 설정박스 트림 조작 시 딜레이 없이 실시간으로 비디오 썸네일과 재생 싱크가 연동되어 표시되는지 검증
- [ ] 비정상적인 강제 프로세스 킬 상황에서 인메모리 트랜잭션 저널을 통해 직전 씬까지 유실 없이 자동 백업 복구되는지 검증

#### 4. do-not-touch list
- [ ] OpenGL 가속 레이어 및 외부 3D 뷰어 컴포넌트 강제 배제
- [ ] STT/VAD 음성 인식 파이프라인 및 자막 원본 결정 커널
