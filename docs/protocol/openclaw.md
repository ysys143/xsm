# OpenClaw 2026.10.9 연결 경계

상태: 실험적 direct-turn 도구 연결. 실제 고정 로더의 등록·metadata 발견과,
명시적 caller fixture에서 실제 xsm 서버와의 왕복을 확인했다. Native 도구
실행·agent turn·설치·수신 주입·UI는 미완이다. 전체 계획은 미완이다.

## 고정 버전과 격리 환경

공식 npm `openclaw@2026.10.9`와 Git tag `v2026.10.9`를 대조했다.
소스 commit은 `8b18b5578f66eab1501cba4cef2310d88bfb9a41`이다.
[package.json](https://github.com/openclaw/openclaw/blob/v2026.10.9/package.json)의
Node 요구 조건은 `>=24.22.1 <25 || >=26.12.1`이다. 조사 시 전역 Node
24.19.0은 이를 충족하지 않았다. 공식 배포의 SHA-256을 대조한 Node 24.22.2를
임시 폴더에 풀고 실행 파일의 `--version`을 확인했다. 전역 Node는 바꾸지 않았다.

[LICENSE](https://github.com/openclaw/openclaw/blob/v2026.10.9/LICENSE)는
MIT, OpenClaw Foundation 2026이다. 소스는 임시 폴더에만 받았으며 제품 코드에
복사하지 않았다. 파일별 해시와 Node 확인 결과는
`deliverables/protocol-foundation/openclaw-stable-api.json`에 있다.

## 등록·신원·수명

| 연결 지점 | 고정 버전에서 확인한 계약 | xsm에 필요한 처리 |
|---|---|---|
| `register(api)` | 동기식. async 등록은 loader가 오류 처리 | 공통 작업 스키마를 등록 시 사용할 수 있어야 함. 비동기 operations/list를 그대로 await할 수 없음 |
| `registerTool` factory | native context의 `workspaceDir`, `agentDir`, `sessionId`, `sessionKey` 제공 가능 | 모델 인자로 신원을 받지 않고, 필수 context가 없으면 명시적으로 거부 |
| `sessionId` | `/new`, `/reset`에서 바뀌는 대화 UUID | xsm conversation의 대화 분리에 사용. 재사용되는 route key만으로 주소를 만들지 않음 |
| `sessionKey` | native 라우팅 키 | 수신 라우팅에 사용하되 현재 sessionId와의 결속을 별도로 검증 |
| `runtime.state.resolveStateDir` | native state 경로 resolver | 실제 프로필 경로 확정에 사용. native config/agentDir와의 관계는 실행 검증 필요 |
| `session_start` / `session_end` | sessionId/key, end reason 및 nextSessionId/key 제공 | reset·삭제·재시작과 참여 세대를 결속. 세션 hook에는 workspace가 없어 임의 폴더 추측 금지 |
| lifecycle / service | runtime cleanup 및 서비스 start/stop 등록 | plugin 교체·종료 중 열린 host와 작업을 정리하고, 늦은 callback 거부 |

근거:
[tool context](https://github.com/openclaw/openclaw/blob/v2026.10.9/src/plugins/tool-types.ts),
[등록 API](https://github.com/openclaw/openclaw/blob/v2026.10.9/src/plugins/plugin-api.types.ts),
[수명 hook](https://github.com/openclaw/openclaw/blob/v2026.10.9/src/plugins/hook-types.ts),
[동기 등록 검사](https://github.com/openclaw/openclaw/blob/v2026.10.9/src/plugins/loader.base.test-utils.ts).

## 후속 실행의 권한 결속

Version 2 factory의 `assertInvocationCurrent`는 await 이후에도 전달하고 최종
동기 쓰기·요청 guard에서 호출해야 한다. Owner bit만 확인하거나 RPC 시작 전에
한 번 호출하는 것으로 이 조건을 충족하지 않는다. 일반 function/static 도구는
계속 지원되지만 continued owner identity를 받지 않는다.

xsm의 subprocess RPC에서 native guard와 정본 효과의 최종 admission을 어떻게
결속할지는 미해결이다. 이 경로가 구현·검증되기 전에는 version 2 후속 실행
지원을 주장할 수 없다. 입력 취소와 이미 수락한 효과의 정리도 구분해야 한다.

근거: [owner-authorized continuations](https://github.com/openclaw/openclaw/blob/v2026.10.9/docs/plugins/tool-plugins.md).

## 수신 큐와 ACK

공개 `system-event-runtime`은 session별 event enqueue/peek/consume을 제공한다.
내부 큐는 메모리에 있고 최대 20개이며, enqueue의 반환값은 발생 건 또는
boolean이다. Session store 교체, 중복, 빈 본문, 큐 용량 등으로 거부될 수 있다.
이 반환을 모델 소비 ACK로 해석하지 않는다.

Store 경로 검사만으로 `/new` 이후 같은 route에 속한 다른 대화로의 오배송이
막힌다고 가정하지 않는다. xsm 참여의 native sessionId/세대와 현재 라우팅의
결속을 확인하고 실제 queue occurrence를 관찰해야 admission 근거가 된다.
Wake 요청도 별도이며 큐 수락과 다음 turn의 소비는 별개다. 100개 표본 지연
검사에는 큐 용량·배출·거부·재시도를 함께 기록해야 한다.

근거:
[공개 exports](https://github.com/openclaw/openclaw/blob/v2026.10.9/src/plugin-sdk/system-event-runtime.ts),
[SDK 라우팅](https://github.com/openclaw/openclaw/blob/v2026.10.9/src/plugins/runtime/system-events.ts),
[실제 큐](https://github.com/openclaw/openclaw/blob/v2026.10.9/src/infra/system-events.ts).

## 남은 실행 기준

담당은 구현 세션이다. 같은 고정 버전에서 native loader·factory 호출을 먼저
연결하고, 세션 분리·reset·플러그인 교체·취소·오래된 실행 거부를 실제 경로로
검사해야 한다. 이어 UI 질문의 requester/표시/응답 결속, owned 설치·업데이트·
제거, native queue p95, worker와 원격 기능을 구현·검증한다. Linux·교차 런타임·
메신저까지 원래 완료 조건을 유지한다. 다음 절의 로더 검증 이후에도 native
agent 실행·모델·사용자 UI 시험은 미완이다.

## 실험 연결부와 후속 실행 증거

`integrations/openclaw/xsm.mjs`는 native function factory를 동기 등록한다.
`tools.mjs`는 공통 `operation_schema.TOOLS`에서 생성한 정적 catalog이며
`tests.test_openclaw_schema`가 전체 값과 manifest의 이름 목록을 대조한다.
새 기능의 독립 정책을 복제하지 않고 대화별 Node XsmHost를 사용한다.
Manifest·catalog·binding은 immutable runtime snapshot에 포함된다.

Native metadata-only factory는 null을 반환하고 참여를 만들지 않는다.
실행 context의 sessionId/route/workspace를 사용하며 모델 인자는 이 신원을
바꾸지 못한다. 같은 route의 다른 UUID는 분리한다. Session-end와 native
lifecycle cleanup에서 세대를 무효화하고 pending open 종료도 기다린다.
이전 factory는 다시 열 수 없으며 새 factory의 resume는 주소를 유지하고
참여 세대를 바꾼다. Workspace 변경은 기존 참여 종료를 요구한다.

Native 수신과 UI는 연결하지 않아 pull-only다. 질문이 필요한 작업은 승인 없이
거부된다. Version 2 continuation은 광고하지 않는다. 외부 플러그인의
`agent_end`는 native `hooks.allowConversationAccess=true`가 필요하다. 이를
명시적으로 허용한 프로필에서만 hook과 busy/idle 갱신을 사용한다. 기본
프로필의 native busy/idle 관찰은 미완이며 자동으로 권한을 켜지 않는다.

`clients/tests/test_openclaw_binding.mjs`의 4개 검사는 fixture API와 실제 xsm
subprocess로 동시 연결·대화 분리·DM/pull/ACK·종료/resume·늦은 도구 거부·
취소·미연결 UI·plugin 폐기를 실행한다. 최초 검사는 Mac의 realpath 차이와
activity 필드 오독으로 2개 실패했고 fixture를 수정했다. 이 검사를 native
OpenClaw 도구 실행으로 세지 않는다. 세대 검사를 제거하거나 route를 대화 ID로
사용하거나 catalog를 바꾼 세 변이는 모두 관련 검사를 실패시켰다.

별도 `scripts/probe-openclaw-loader.mjs`는 실제 2026.10.9 로더에서 도구 21개를
경고 없이 등록하고 metadata factory가 참여를 만들지 않는 것을 확인했다.
Native host 내부 loader는 이 고정 probe에서만 import하며 제품에서는 import하지
않는다. 결과는 `openclaw-native-loader-final.json`이다. Native 도구 execute·
unload·one-shot CLI 수명·gateway 수명은 아직 검증하지 않았다.

```sh
/isolated/node scripts/probe-openclaw-loader.mjs /isolated/node_modules/openclaw deliverables/openclaw-loader.json
```

위 명령은 전용 임시 HOME/native state/XSM_HOME을 만들고 자격 증명을 상속하지
않는다. 실제 사용자 프로필·권한 설정은 바꾸지 않는다. 제품의 owned 설치기는
아직 OpenClaw를 지원하지 않으며 이 파일 경로는 native 로더 probe에서만 명시했다.
