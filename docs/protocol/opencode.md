# OpenCode 1.19.5 실험 연결

상태: 개발 중. 전체 OpenCode 지원이나 릴리즈 인증을 뜻하지 않는다.

[`integrations/opencode/xsm.mjs`](../../integrations/opencode/xsm.mjs)는 서버
플러그인이며 공통 호스트 API를 사용한다. 하나의 서버에 있는 각 native 대화
ID를 별도의 xsm 참여자로 등록한다. 도구 호출의 sessionID와 directory를
확인한다. 모델 인자로 발신 대화를 고르지 않는다. 같은 프로필/대화를
재개하면 주소는 유지하고 참여 세대는 바꾼다.

자동 수신은 배치당 16개/512 KiB UTF-8의 구현 기본값을 사용한다. 첫 oversized
원문은 단독으로 반환하며, 나머지는 공통 SDK의 cursor와 backpressure 재시도로
진행한다. FYI를 인수한 background 배치가 새 native turn을 깨우지는 않는다.

실제 protocol 서버와 native API fixture에서 30만 자 원문 3개를 미리 쌓고
입력 3개로 나누어 저장하며 추가 wake가 없음을 확인했다. 기본 예산을 제거한
변이는 실패했다(`native-default-budget-mutants.json`). 실제 1.19.5 SDK의 정상
수신과 native ACK도 100/100 완료했다. macOS 수락 p95 상한은 349.474ms였다
(`opencode-batch-defaults-native-100/result.json`). Assistant packet과 ACK는
loopback fixture이며 실제 모델이나 사람을 실행하지 않았다.

## 명시적 프로필 설치

```sh
xsm protocol install opencode --home /explicit/opencode-config --dry-run
xsm protocol install opencode --home /explicit/opencode-config
xsm protocol inspect opencode --home /explicit/opencode-config
xsm protocol uninstall opencode --home /explicit/opencode-config
```

`--home`은 OpenCode 설정 디렉터리 자체이다. XDG_CONFIG_HOME을 사용한다면
그 아래의 `opencode` 디렉터리이다. 설치기는 `plugins/xsm.js`와 native TUI
설정의 xsm plugin URI를 관리한다. 다른 설정 값·auth·권한은 수정하지 않는다.
설치·갱신·제거 후에는 native
재시작/재로딩이 필요하다. 실행 중 서버를 종료하지 않는다.

TUI 설정은 기존 소유 파일이 있으면 그 파일을 사용하고, 최초 설치는 기존
`tui.jsonc`를 우선한다. 둘 다 없으면 `tui.json`을 생성한다. 댓글·후행 쉼표·
다른 plugin을 보존하고 xsm URI만 편집한다. 원래 파일은 무변경 상태라면
제거 뒤 byte 단위로 복구한다. 새 파일에 사용자가 설정을 더했다면 자기 URI만
제거하고 파일을 남긴다. 변경 직전 revision과 디렉터리를 다시 확인한다.

설치 중단은 준비 journal로 복구하며 과거 backup을 사용자 편집 위에 덮지 않는다.
실행 중인 서버/TUI의 snapshot은 PID·시작 세대와 실제 소스 root를 기록해 보존한다.
이 기록은 별도 에이전트 참여가 아니며 정리기는 등록된 PID만 조회한다.

로더는 immutable xsm snapshot과 설치 당시 Python을 참조한다. 도구 스키마는
공통 서버에서 가져와 native SDK의 `tool.schema`로 변환한다. SDK는 OpenCode가
자체 프로필에 설치한 `@opencode-ai/plugin`에서 import한다. 이 의존성 설치는
OpenCode의 기존 시작 동작이다. xsm snapshot에서 별도 npm 설치를 하지 않는다.

## 전달과 사용자 UI

본문과 ACK 토큰을 synthetic native 사용자 메시지로 저장한다. `noReply: true`
저장 뒤 메시지 ID·대화 ID·본문·메타데이터를 native API로 다시 읽어 확인한
경우에만 admitted를 보고한다. 저장은 소비 ACK가 아니다. 읽은 에이전트가
본문의 토큰으로 `xsm_ack`를 호출해야 한다.

깨우기가 필요한 idle 대화에는 native 비동기 turn을 요청한다. Busy 대화에는
입력을 추가하고 실행 중 loop를 사용한다. `now`의 실행 중 개입·중단 우선순위는
아직 인증하지 않았다. FYI는 공통 호스트의 자연스러운 입력 경계에서 전달한다.

기본 설치는 서버의 native UI 모드를 켜고 TUI companion을 등록한다. 고정 버전
SDK의 Question API에는 ask가 없어 아래의 native API 경로를 사용한다.
서버만 실행 중이거나 TUI가 표시하지 못하면 승인을 기록하지 않고 오류를 반환한다.

개발 연결부는 명시적 `present(conversation, event, controls)` callback이나
`nativeUi: true`일 때 해당 능력을 광고한다. 후자는
[`tui.mjs`](../../integrations/opencode/tui.mjs) companion과 native API로 직접 연결한다.
소스 연결을 직접 구성하는 개발용 callback도 유지한다.

제어 전송은 빈 `ignored`/`synthetic` native 텍스트 부분의 메타데이터를 쓴다.
기존 native 서버 API와 인증 경계를 사용하며 별도 listener를 열지 않는다.
UI 한 곳이 질문의 일회용 값을 먼저 받고 실제 render callback을 보고해야
답을 받는다. 대화 ID·일회용 값·선택된 UI instance가 다른 응답은 무시한다.
호스트의 세션 핸들과 원래 승인 challenge는 TUI에 전달하지 않는다.
화면이 없거나 렌더되지 않으면 답으로 해석하지 않고 오류로 끝낸다.

[`question-ui.mjs`](../../integrations/opencode/question-ui.mjs)는 고정 버전의
native DialogSelect/DialogPrompt를 사용한다. 표시 원문·질문 ID를 보존하고
실제 선택/입력 callback만 답으로 돌려준다. 다른 대화, 만료, 종료, 이미 열린
dialog는 거부한다. 다른 dialog가 질문 화면을 대체하면 취소로 끝내며 늦은
callback으로 그 화면을 지우지 않는다.

## 검증과 남은 조건

빠른 검사에는 별도 대화 등록·동시 초기화·재개 세대·도구 directory 결속·
저장 검증 실패 후 회복·명시적 소비 ACK 검사가 있다. 이 검사는 SDK callback
fixture를 사용하며 모델이나 물리적 UI 검사가 아니다.

```sh
python3 scripts/check-protocol.py
python3 scripts/probe-opencode-protocol.py --native-root /isolated/npm-root --output deliverables/opencode-probe --samples 100
python3 scripts/probe-opencode-question-ui.py --native-root /isolated/npm-root --output deliverables/opencode-ui --action choose
python3 scripts/probe-opencode-question-ui.py --native-root /isolated/npm-root --output deliverables/opencode-ui-cancel --action cancel
python3 scripts/probe-opencode-question-ui.py --native-root /isolated/npm-root --output deliverables/opencode-bridge --native-bridge --action choose
python3 scripts/probe-opencode-question-ui.py --native-root /isolated/npm-root --output deliverables/opencode-bridge-cancel --native-bridge --action cancel
python3 scripts/probe-opencode-question-ui.py --native-root /isolated/npm-root --output deliverables/opencode-installed-ui --native-bridge --installed --action choose
```

Native 하네스는 실제 고정 버전 binary와 autoload, 실제 Zod 도구 스키마,
대화 생성, native 기록 진입을 확인한다. 명시적 loopback assistant fixture의
tool-call 패킷으로 native 실행 커널의 xsm_ack와 반환값도 검사한다. 각 표본
시작 전에 idle을 확인한다. HOME·설정·상태는 모두 새 임시 경로에 둔다.
실제 모델 추론이나 유료 API를 호출하지 않는다. 모델 실행·실제 사람의 UI
응답·Linux·전체 설치 수명·자동 재접속·worker·
원격/메신저 조합은 이 하네스의 통과만으로 완료되지 않는다.

현재 설치 경로 표본은 macOS·OpenCode 1.19.5·Python 3.9.6에서 100회 모두
native 입력과 fixture ACK를 완료했다. send 시작부터 기록 진입 관측까지의
p95 상한은 약 0.379초였다. 결과·실제 origin·소스 해시는
`deliverables/protocol-foundation/opencode-native-ack-100/result.json`에 있다.
소비 ACK 없이 81회 뒤 관측에 실패한 초기 실행도 별도 로그로 보존한다.

TUI 하네스는 실제 서버 대화와 고정 버전 TUI를 격리 PTY로 연다. 질문은 실제
프로토콜의 decision/request에서 가져오고 native 화면의 제목·Scope를 확인한
뒤 시험용 Enter/Escape를 보낸다. Enter는 host-user 답 저장 후 원 작업 재호출에서
applied가 되고, Escape는 dismissed이며 적용이 없다. 이는 자동 키 입력 시험이다.
사람이 실제로 답했다는 주장이나 제품용 서버–TUI IPC/설치 완료의 증거가 아니다.
결과는 `opencode-tui-protocol-{choose,cancel}/result.json`에 구분해 남긴다.

`--native-bridge` 시험은 Python 질문 relay를 사용하지 않는다. 실제 native
실행 커널의 xsm_decide가 서버 플러그인→TUI→서버로 답을 받아 완료한다.
Enter와 Escape의 두 실행 모두 통과했다. 각각 5개 제어 프레임을 관측했고,
도구 실행 뒤 모델에 보낸 요청에서 프레임과 일회용 값이 제외된 것도 확인했다.
이는 loopback assistant/키 입력 fixture이며 모델 추론이나 사람의 실제 답은 아니다.
`opencode-native-ui-render-{choose,cancel}/result.json`이 근거다.
기본 설치 경로의 선택·취소도 실제 native TUI에서 통과했다. 서버와 UI의 실제
소스 root가 설치된 snapshot과 일치하며 UI PID 수명 기록도 관측했다.
이 모드의 추가 TUI observer는 읽기만 하며 dialog 표시나 답 전달을 하지 않는다.
`opencode-installed-ui-release-{choose,cancel}/result.json`이 근거다.
Native 갱신·재개·제거는 기본 조건과 사용자 편집 조건에서 각각 8단계를
통과했다. 이전 UI만 남았을 때의 snapshot 보존과 종료 뒤 실제 정리도 포함한다.
세부 경로와 실패/변이 기록은 [설치 수용 조건](../plan/runtime-protocol/opencode-ui-install.md)을 따른다.

설치 잠금은 상위 경로 별칭을 정규화하되 마지막 symlink는 따라가지 않는다.
같은 파일의 별칭이 다른 잠금을 만들거나 갱신 중인 symlink의 잠금이 바뀌는
것을 실제 두 프로세스 검사로 막는다. 이 검증은 해당 macOS 고정 버전에 한정한다.

API 근거는 [고정 버전 플러그인](https://github.com/anomalyco/opencode/blob/v1.19.5/packages/plugin/src/index.ts),
[TUI dialog API](https://github.com/anomalyco/opencode/blob/v1.19.5/packages/plugin/src/tui.ts),
[도구 스키마 처리](https://github.com/anomalyco/opencode/blob/v1.19.5/packages/opencode/src/tool/registry.ts),
[native 입력 처리](https://github.com/anomalyco/opencode/blob/v1.19.5/packages/opencode/src/session/prompt.ts)이다.

## 백엔드 종료 뒤 native 진입에서 복구

종료되거나 transport 실패로 중단된 host를 다음 도구/chat/status 진입에서
교체한다. 기존 UI 질문을 닫고 backend 정리를 마친 뒤 같은 native 대화를
새 participation 세대로 연다. 복구 Promise를 세션 map에 보관하므로 동시에
들어온 호출들이 같은 새 참여를 기다린다. 실패한 도구 호출을 이 경로가
자동 재실행하지 않는다. 유휴 중 선제 재시작은 아직 미구현이다.

실제 protocol server와 OpenCode API fixture의 충돌 검사는 원문을 claim한
backend를 종료한 뒤 두 native 도구 호출을 동시에 보낸다. 같은 ref·다른
PID/세대에서 원문을 새 token으로 회수하고, 이전 token의 ACK를 거부한 뒤
새 token으로 소비했다. FYI가 unsolicited native 입력으로 바뀌지 않는 것도
확인했다. 변경 전 실패는 `opencode-backend-recovery-red.log`, 수정 후 관련
8개 검사 통과는 `opencode-backend-recovery-green.log`에 기록했다.

고정 OpenCode 1.19.5의 실제 설치본 프로브도 `--crash`를 지원한다. 자체
프로세스 그룹의 backend만 종료한 뒤 실제 `/session/{id}/message`의 noReply
chat 경계를 거쳐 같은 주소의 새 세대를 확인한다. 그 후 native 수락과 scripted
assistant의 native ACK를 100/100개 완료했다. macOS/protocol Python 3.14.6의
p95 상한은 347.275ms다(`opencode-backend-recovery-native-100/result.json`).
이 native 프로브의 강제 종료 시점에는 미소비 claim을 남기지 않았다. 원문·
claim을 남긴 충돌 회복은 앞의 API fixture 결과와 구분한다. 모델 추론·사람
UI·Linux 인증도 아니다.

첫 실제 프로브는 시험 코드가 `/prompt` 경로를 잘못 사용해 실패했다
(`opencode-backend-recovery-native/result.json`). 고정 SDK가 쓰는 `/message`로
고친 5회 smoke와 이후 100회 결과를 따로 보존했다. 공통 355개는 59.428초에
통과했다(`opencode-backend-recovery-gate.log`). Pi 및 다른 runtime의 복구,
유휴 재접속·worker와 전체 P3/P5는 미완이다.

## 참여 생성 후 초기 갱신 실패 정리

Backend 참여가 열린 뒤 최초 상태·제목 갱신이 실패하면 그 host도 닫는다.
정리가 끝나고 등록 Promise가 거부되므로 다음 native 진입은 같은 주소를
새 세대로 다시 등록할 수 있다. 정리 자체가 실패하면 별도 진단으로 보내고
원래 등록 오류를 호출자에게 유지한다.

실제 protocol server를 사용하는 API fixture는 첫 갱신을 실패시키고 host 종료,
등록 기록의 ended_at, 다음 등록의 같은 ref·새 세대를 확인한다. 수정 전에는
host가 열린 채 남았다(`opencode-initial-update-red.log`). 수정 후 관련 9개가
통과했다(`opencode-initial-update-green.log`).

고정 OpenCode 1.19.5 설치본의 `--initial-update-failure` 프로브는 임시 Python
wrapper로 첫 session.update만 거부한다. Native session 등록이 종료됐음을
확인한 뒤 noReply chat 경계를 보내 재등록했다. 이후 native 수락·scripted
assistant의 native ACK 5회가 통과했다
(`opencode-initial-update-native/result.json`). 기존 프로브의 receiver 판독도
ended_at을 확인해 종료된 행을 live로 오인하지 않도록 보완했다. 모델 추론·
실제 사람 UI를 실행하지 않았으며 5회를 지연 인증으로 쓰지 않는다.

공통 363개는 58.657초에 통과했다(`opencode-initial-update-gate.log`). 이 검사는
plugin 도구 목록 조회가 끝난 뒤 참여의 초기 갱신 실패를 다룬다. Plugin 자체의
최초 descriptor 조회 실패, 유휴 중 자동 재접속·worker·Linux 및 전체 P0–P5의
남은 조건은 미완이다.
