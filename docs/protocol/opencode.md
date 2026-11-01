# OpenCode 1.19.5 실험 연결

상태: 개발 중. 전체 OpenCode 지원이나 릴리즈 인증을 뜻하지 않는다.

[`integrations/opencode/xsm.mjs`](../../integrations/opencode/xsm.mjs)는 서버
플러그인이며 공통 호스트 API를 사용한다. 하나의 서버에 있는 각 native 대화
ID를 별도의 xsm 참여자로 등록한다. 도구 호출의 sessionID와 directory를
확인한다. 모델 인자로 발신 대화를 고르지 않는다. 같은 프로필/대화를
재개하면 주소는 유지하고 참여 세대는 바꾼다.

## 명시적 프로필 설치

```sh
xsm protocol install opencode --home /explicit/opencode-config --dry-run
xsm protocol install opencode --home /explicit/opencode-config
xsm protocol inspect opencode --home /explicit/opencode-config
xsm protocol uninstall opencode --home /explicit/opencode-config
```

`--home`은 OpenCode 설정 디렉터리 자체이다. XDG_CONFIG_HOME을 사용한다면
그 아래의 `opencode` 디렉터리이다. 설치기는 `plugins/xsm.js`만 관리하며
다른 설정·auth·권한 파일을 수정하지 않는다. 설치·갱신·제거 후에는 native
재시작/재로딩이 필요하다. 실행 중 서버를 종료하지 않는다.

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

현재 서버 연결은 `user-decisions`를 광고하지 않는다. 고정 버전 SDK의 Question
API는 list/reply/reject를 제공하지만 ask는 제공하지 않으며 MCP elicitation도
연결되어 있지 않다. 실제 TUI dialog와 요청 결속이 추가로 필요하다. 사용자
답이 필요한 작업은 승인을 기록하지 않고 오류를 반환한다.

## 검증과 남은 조건

빠른 검사에는 별도 대화 등록·동시 초기화·재개 세대·도구 directory 결속·
저장 검증 실패 후 회복·명시적 소비 ACK 검사가 있다. 이 검사는 SDK callback
fixture를 사용하며 모델이나 물리적 UI 검사가 아니다.

```sh
python3 scripts/check-protocol.py
python3 scripts/probe-opencode-protocol.py --native-root /isolated/npm-root --output deliverables/opencode-probe --samples 100
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

API 근거는 [고정 버전 플러그인](https://github.com/anomalyco/opencode/blob/v1.19.5/packages/plugin/src/index.ts),
[도구 스키마 처리](https://github.com/anomalyco/opencode/blob/v1.19.5/packages/opencode/src/tool/registry.ts),
[native 입력 처리](https://github.com/anomalyco/opencode/blob/v1.19.5/packages/opencode/src/session/prompt.ts)이다.
