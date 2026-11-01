# OpenClaw 2026.10.9 연결 경계

상태: 고정 소스 API 조사. 연결부·설치·native 실행은 미구현이며 전체 계획은
미완이다. 다른 런타임의 검사를 OpenClaw 지원 근거로 세지 않는다.

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
메신저까지 원래 완료 조건을 유지한다. 현재 자료는 소스 조사와 격리 Node
실행 확인이며, native OpenClaw 프로세스나 모델·사용자 UI를 실행한 증거는 아니다.
