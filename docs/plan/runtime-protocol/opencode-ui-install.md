# OpenCode UI 설치의 남은 구현

상태: 부분 구현. 기본 설치의 `nativeUi` 활성화와 TUI 등록, JSONC 보존,
중단 journal, 서버/TUI component 수명 기록을 구현했다. 실제 설치 경로의
선택·취소가 통과했다. 아래 native 전체 수명 검증은 아직 남아 있다.

## 구현한 소유 변경

- 기존 `plugins/xsm.js` 로더에서 native UI 연결을 활성화한다.
- 별도 TUI 로더 대신 immutable snapshot의 `integrations/opencode/tui.mjs` URI를
  native `tui.json`/`tui.jsonc`의 plugin 목록에 등록한다. 이 모듈은 기본
  TUI entry와 id를 이미 제공한다. 서버 plugin 디렉터리에 넣으면 안 된다.
- 기존 사용자 설정·댓글·다른 plugin과 auth/권한 설정을 보존한다. JSONC를
  정규화해 다시 쓰지 않고 원문 위치를 찾아 소유 URI만 삽입·갱신·제거한다.
- 최초 생성 파일은 소유 기록이 있고 내용이 그대로인 경우에만 제거한다.
  사용자가 다른 설정을 더했으면 자기 URI만 제거하고 파일을 유지한다.
- 설치/제거 전 두 대상 모두 검사한다. 기존 소유권/CAS/no-follow 경계를
  유지하고, 준비/완료 journal로 중단 후 복구한다. 사용자 수정 위에 과거
  backup을 덮어 복구하지 않는다.

## 구현한 snapshot 참조

- 서버 로더와 UI URI가 서로 다른 버전을 가리키는 준비 중 상태에서도 둘 다
  정리 대상에서 제외해야 한다. 소유 기록의 UI 참조를 로더 갱신에서 잃지 않는다.
- TUI 프로세스는 별도 xsm 대화 참여자가 아니다. 따라서 대화 registry만으로
  실행 중인 old TUI snapshot 사용을 알 수 없다. native TUI 수명에 결속한
  내부 component lease로 실제 PID/시작 세대/소스 root를 기록한다. 서버의 JS
  코드도 대화가 없는 동안 보존한다. 생성과 정리는 동일 잠금을 사용한다.
  조회는 기록된 PID에 한정하며 시작 시각은 C locale/UTC로 고정한다.
- 소유 기록과 다른 URI를 사용자가 설정했어도 그 실제 snapshot 참조를 보존한다.
  참조 보존은 변경 소유권을 주장하거나 사용자 편집을 덮는 근거가 아니다.

## 완료한 검사

`python3 scripts/check-protocol.py`의 핵심 180개 + Python 클라이언트 18개 +
Node 45개, 총 243개가 Python 3.9.6에서 43.324초, 3.14.6에서 28.600초에
통과했다. 별도 기존 설치 회귀 104개도 65.389초에 통과했다.
`py39-ui-install-release.log`, `py314-ui-install-release.log`, `ui-install-regression-release.log`가 근거다.

`probe-opencode-question-ui.py --native-bridge --installed --action choose|cancel`은
격리된 실제 OpenCode 1.19.5에서 통과했다. 개발 로더 대신 기본 설치된 서버와
UI를 사용했고 소스 root와 실제 UI PID의 UTC 수명 기록을 확인했다.
모델과 키 입력은 명시적 fixture이며 실제 사람의 응답으로 부르지 않는다.

JSONC 댓글/후행 쉼표·중단 후 반복 갱신·사용자 plugin 추가·늦은 파일 편집·
경로 교체·제거 중단 후 복구·살아 있는 수명 기록의 snapshot 보존은 격리 검사로
통과했다. CAS, 사용자 설정 보존, 활성 component 보존, 정리 잠금을 제거한
네 변이는 관련 검사를 실패시켰다(`ui-install-mutations.json`).

## 남은 native 수명 검증

설치 전부터 있던 대화의 문맥을 보존하는 설치·갱신·재개, 실행 중 old UI의
실제 보존과 종료 후 정리, 제거 후 재시작을 native 프로세스로 확인해야 한다.
격리 검사로 확인한 사용자 편집·JSONC·중단·경로 교체도 그 전체 수명 시나리오와
구분해 기록한다. 실제 사용자 프로필을 시험 대상으로 삼지 않는다.

완료 증거에는 기본 설치 경로에서 native 도구→TUI→호스트 적용/취소,
모델 입력에서 제어 프레임 제외, 설치/제거 뒤 사용자 설정 보존을 포함한다.
기본 설치의 선택·취소 증거를 native 갱신/재개/제거 전체의 완료 증거로 대체하지 않는다.
