# OpenClaw 2026.10.9 연결 경계

상태: 실험적 direct-turn 도구 연결. 실제 고정 로더의 등록·metadata 발견과,
명시적 caller fixture에서 실제 native 도구와 xsm 서버의 왕복·수명 정리를
확인했다. Guarded native 대기열과 prompt 소비 helper도 연결했다.
실제 agent turn·idle wake·설치·사용자 UI는 미완이다. 전체 계획은 미완이다.

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

초기 연결은 native 수신과 UI가 없는 pull-only였다. 질문이 필요한 작업은 승인 없이
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
않는다. 결과는 `openclaw-native-loader-final.json`이다. 이 초기 실행에서는
native 도구 execute·unload를 검사하지 않았다. 후속 결과는 다음 절에 구분한다.
One-shot CLI 수명·gateway 수명은 여전히 미완이다.

```sh
/isolated/node scripts/probe-openclaw-loader.mjs /isolated/node_modules/openclaw deliverables/openclaw-loader.json
```

위 명령은 전용 임시 HOME/native state/XSM_HOME을 만들고 자격 증명을 상속하지
않는다. 실제 사용자 프로필·권한 설정은 바꾸지 않는다. 제품의 owned 설치기는
아직 OpenClaw를 지원하지 않으며 이 파일 경로는 native 로더 probe에서만 명시했다.

## Native 도구 실행과 capture 경로

후속 probe의 `--execute`는 실제 native `resolvePluginTools`를 사용해 도구를
구성하고 실행한다. Context의 sessionId·route·workspace는 명시적 fixture다.
같은 route의 두 대화를 분리하고 DM/pull/ACK, 미연결 UI 거부를 실행한다.
공개 SDK의 global hook runner로 session-end를 전달해 참여 종료·이전 도구 거부·
같은 주소의 새 세대 resume를 확인한다. 마지막으로 native registry 폐기를
호출하고 모든 참여에 ended_at이 생겼는지 검사한다.

첫 실제 실행은 실패했다. OpenClaw가 JS를 native capture 폴더로 옮겨 로드하므로
import.meta.url 기준의 기본 명령이 복사되지 않은 bin/xsm을 가리켰다.
Binding의 기본 명령은 이제 native API의 원본 절대 source에서 계산한다.
향후 설치 loader는 immutable snapshot의 pinned command를 명시해야 한다.
실패 로그는 `openclaw-native-tools-first.log`, 수정 후 결과는
`openclaw-native-tools-expanded.json`에 있다. 도구 실행과 native 폐기·참여
종료가 통과했다. 실제 agent turn·model·사람의 UI 응답·one-shot CLI·gateway
검증은 포함하지 않는다.

```sh
/isolated/node scripts/probe-openclaw-loader.mjs /isolated/node_modules/openclaw deliverables/openclaw-tools.json --execute
```

## 자동 수신의 대상 대화 결속 실험

`probe-openclaw-session-guard.mjs`는 고정 native SDK의 실제 저장소를 사용한다.
모든 HOME/state는 임시 폴더이며 native agent나 모델은 실행하지 않는다.
대기열 metadata에 `expectedSessionId`를 넣는 것만으로는 검증되지 않았다.
동일 route의 저장된 sessionId를 교체한 뒤 이전 ID가 담긴 요청을 enqueue하면
교체된 대화의 대기열에 그대로 수락됐다. 따라서 route-only API에 metadata를
추가하는 것만으로 xsm의 정확한 대화 결속을 구현할 수 없다.

Public runtime의 `agent.session.patchSessionEntry`와 `assertCommitAllowed`도
실험했다. 이미 교체된 대화에 준비한 쓰기는 update callback이 실행된 뒤
최종 guard에서 거부됐다. Guard를 제거한 변이는 이 검사를 실패시켰다.

준비 callback을 중단한 상태의 교체 실험 4건은 다음처럼 구분한다.

| 교체 경로 | 최종 guard | 준비 중 교체 완료 | 결과 |
|---|---|---|---|
| 같은 프로세스 | 없음 | 아니요 | native 직렬화 뒤 교체. 교체 전 guard의 효과를 입증하는 표본이 아님 |
| 같은 프로세스 | 있음 | 아니요 | native 직렬화 뒤 교체. guard 1회 호출 |
| 별도 프로세스 | 없음 | 예 | native의 SQLite 상태 변경 검사에서 쓰기 거부 |
| 별도 프로세스 | 있음 | 예 | 같은 native 검사에서 거부. 사용자 guard는 호출되지 않음 |

거부된 쓰기의 표식은 교체된 대화에 남지 않았다. 뒤의 두 결과를 사용자
guard가 막았다고 해석하지 않는다. 이 결과는 native patch의 동시 변경 보호를
보여 주며 native queue의 자동 수신 구현이나 실제 reset UI 인증은 아니다.

`openclaw-session-guard-final.json`과 `openclaw-session-guard-mutation.json`에
결과를 남긴다. `openclaw-session-guard-first.json`은 같은 프로세스만 시험한
초기 표본이며, 교체가 준비 중 완료되지 않아 경쟁 방어 근거로 쓰지 않는다.
후속 구현은 exact sessionId/수명과 native 최종 admission을 결속하고, 실제
대기열 소비·취소·재시도·용량·prompt-injection 정책까지 실행 검증해야 한다.

```sh
/isolated/node scripts/probe-openclaw-session-guard.mjs /isolated/node_modules/openclaw deliverables/openclaw-guard.json
```

## Guarded native context queue

`context-queue.mjs`는 native runtime의 공개 `agent.session.patchSessionEntry`와
`assertCommitAllowed`로 공개 SessionEntry의 xsm next-turn queue를 갱신한다.
Route-only enqueue API 대신 이 경로를 쓰는 이유는 대상 sessionId·수명·정책을
최종 쓰기에 결속하기 위해서다. 고정 2026.10.9의 queue record 형식과 용량에
의존하므로 다른 버전으로 자동 확대하지 않는다. Native 내부 구현을 복사하거나
DB 파일을 직접 수정하지 않는다.

Native agentId·sessionId·저장소와 필요한 runtime API가 있고 prompt injection이
금지되지 않은 경우에만 이 수신기를 연결한다. 등록 당시 설정과 현재 runtime
설정 중 하나라도 명시적으로 거부하면 pull 방식이다. 비어 있는 runtime 설정이
등록 당시의 거부를 넓힐 수 없다.
Native lifecycle의 background context에서 공통 host pump를 시작해 최초 도구
호출의 수명과 분리한다. 최종 쓰기는 binding epoch, 중단 신호, native sessionId,
lifecycleRevision, 현재 store와 prompt-injection 정책을 검사한다. 저장 후 실제
queue의 ID·metadata·본문을 확인한 뒤에만 Node host가 admitted를 보고한다.
Queue 수락이나 prompt helper의 소비는 canonical 메시지의 소비 ACK가 아니다.

같은 원문 묶음의 재시도는 대기 중인 injection과 결속한다. 이전 claim token이
만료되면 실제 수신 에이전트가 inbox에서 현재 token을 읽고 ACK하도록 안내한다.
다른 plugin의 queue는 보존한다. 고정 native 한도는 xsm queue 32개와 본문
32768자다. 용량·길이 초과는 오류와 claim 반환으로 처리하며 원문은 정본에
남는다. 본문 한도는 ACK 안내 등을 포함한 조각별 최종 문자열의 UTF-16 길이다.
큰 본문의 원자적 분할은 아래 후속 구현에서 추가했다. 32개 조각을 넘는 배치의
다중 turn 전송이나 파일 전환은 여전히 미완이다.

Native idle wake는 아직 연결하지 않았다. 입력은 다음 실제 native turn이
소비할 queue에 들어간다. FYI는 알림으로 깨우지 않으며, conversation-access
권한이 있는 agent-end 경계에서 queue로 옮긴다. 권한 없는 표면의 FYI 자동
경계와 idle/busy/now의 전체 동작은 미완이다. 권한을 자동으로 켜지 않는다.

초기 `test_openclaw_context_queue.mjs`의 8개 검사는 최종 guard, 수락 관찰, 실제
본문, 중복·용량·취소·정책·세대·타 plugin 보존을 확인한다. 최종 guard, 용량,
관찰, 본문 확인, 등록 정책 거부 확인을 각각 제거한 다섯 변이가 모두 실패했다
(`openclaw-queue-complete-mutations.json`). 등록 정책을 무시한 변이는 실제
SDK 검사도 실패시켰다(`openclaw-native-policy-mutant.json`). Native SDK 검사는 다음 명령으로 실제
대기열과 prompt 소비 helper, 명시적 ACK를 실행한다. Agent/model/UI 실행은
포함하지 않으며, 실패 시 partial sample과 failed 상태를 결과에 남긴다.

```sh
/isolated/node scripts/probe-openclaw-loader.mjs /isolated/node_modules/openclaw deliverables/openclaw-queue.json --queue 100
```

최종 macOS arm64 표본은 Node 24.22.2 / protocol Python 3.14.6에서 100/100
queue 수락·prompt helper 소비·명시적 ACK를 완료했다. Native sender execute
직전부터 실제 queue 관찰까지의 p95 상한은 401.576ms다. 정본 저장 시간도
포함한 상한이며 `openclaw-native-queue-100-current.json`에 100개 원시 수치를
남겼다. Native idle wake나 실제 agent/model turn의 지연이 아니다. Linux·다른
버전과 플랫폼의 표본으로 확대하지 않는다.

강화한 중간 실행은 첫 표본에서 0/100으로 실패했다
(`openclaw-native-queue-100-final.json`). 표식 `<sample=0>`이 안전 렌더링에서
이스케이프됐는데 raw 문자열로 비교한 fixture 오류였다. 격리 저장소의 원문
SHA-256 일치와 보호 인코딩을 대조했다
(`openclaw-queue-failed-sample-analysis.json`). 이후 표식은 ASCII로 만들었으며
실패 표본과 재실행 표본을 합치지 않았다. 초기 100개와 별도 후속 100개의
로그도 보존한다. 최초 100개는 최종 정책/본문 검사 변경 전의 표본이다.

실제 SDK의 주입 거부 fixture는 등록 설정이 false, runtime 설정에 항목이 없는
경우에도 자동 queue 주입 없이 inbox/ACK를 유지했다
(`openclaw-native-queue-denied.json`). 이 설정은 임시 프로필의 메모리 구성이다.
실제 사용자 정책·권한은 변경하지 않았다.

## 큰 본문의 원자적 분할

본문이 한 조각의 native 한도를 넘으면 번호가 있는 peer-data frame들로 나눈다.
각 frame은 끝 표식을 두어 native prompt helper의 trim이 본문의 끝 공백을
지우지 못하게 한다. UTF-16 surrogate pair 사이에서는 자르지 않는다. ACK
안내는 별도 마지막 조각에만 두어 token이 교체돼도 본문 조각의 경계가 유지된다.

한 번의 native patch에서 전체 조각의 자리부터 확보한다. 공간이 부족하면
일부만 쓰지 않고 전체를 거부한다. 같은 원문의 대기 중 조각은 재사용하고,
조각이 빠진 기존 묶음은 완전한 수락으로 해석하지 않는다. 수락 관찰도 모든
조각의 ID·본문·번호를 확인한 뒤 완료한다. 앞서 수락된 단일 본문은 token
변경으로 새 encoding이 커지더라도 완전한 기존 본문을 재사용할 수 있다.

현재 제어된 native seam 검사는 14개다. Surrogate 경계, trim 방지, 전체 공간
예약, 모든 조각의 수락 확인, 중복 재시도, 수명·정책 guard 등 9개 변이가 모두
검사를 실패시켰다(`openclaw-fragment-mutations.json`). 공통 검사 278개가
Python 3.9.6에서 37.938초에 통과했다(`openclaw-fragments-final-py39.log`).

실제 2026.10.9 SDK에서 약 8만 UTF-16 단위의 Korean/emoji 본문 100개가 각각
4개 조각으로 들어갔다. 총 400개 조각의 queue 수락·prompt helper 소비와 원문별
명시적 ACK 100개가 완료됐다. macOS arm64 / Node 24.22.2 / protocol Python
3.14.6에서 sender 실행 직전→native queue 관찰의 p95 상한은 701.295ms였다.
검사기는 100개 이상 표본에서는 p95가 1초 이상이면 failed로 기록한다.
`openclaw-native-large-100.json`에 모든 표본과 조각 수를 남겼다.
앞 절의 401.576ms는 분할 추가 전 작은 본문 표본이며, 같은 조건의 성능 비교가 아니다.

일반 크기와 주입 거부 정책도 실제 SDK에서 각각 재검사했다
(`openclaw-fragments-short.json`, `openclaw-fragments-denied.json`). 모든 native
시험은 caller와 prompt 소비를 fixture로 제공한다. 모델·실제 agent turn·idle
wake·사용자 UI 인증으로 확대하지 않는다. 32개 조각을 넘는 전송, owned 설치,
worker와 전체 P0–P5 기준은 미완이다.

## Native 용량 거부 후 자동 재시도

한 묶음 자체가 native 한도에 맞지만 기존 queue가 자리를 차지한 경우,
native patch는 내용을 바꾸지 않고 끝낸다. Native 수명·정책 guard를 다시
확인한 뒤 SDK의 RetryAdmission을 반환한다. 오류는 native SDK 경계를 벗어난
뒤 생성해, native API의 오류 직렬화가 재시도 분류를 바꾸지 않게 한다.
일반 권한·수명 오류와 본문 자체의 batch 한도 초과는 이 분류를 사용하지 않는다.

고정 SDK 시험은 32개 fixture 항목으로 queue를 채우고 원문을 보냈다.
정본의 previous_claim으로 거부 뒤 claim 반환을 읽기 전용으로 확인한 다음,
fixture 항목만 제거했다. 새 메시지나 native wake 없이 원문이 재인수·queue
수락·prompt helper 소비·ACK됐고 수명 정리도 통과했다
(`openclaw-native-capacity-retry-first.json`). SDK의 retry 처리를 제거한 변이에서는
claim 반환까지 됐지만 이후 수락이 없어서 실패했다
(`native-retry-sdk-mutant.json`). 모델·사람은 실행하지 않은 fixture 시험이다.

```sh
/isolated/node scripts/probe-openclaw-loader.mjs /isolated/node_modules/openclaw deliverables/openclaw-capacity.json --queue 1 --capacity-retry
```

이는 자동 수신의 용량 회복 경로다. FYI 경계의 후속 구현은 아래에 기록한다.
바이트 예산, binding 기본 배치, 32조각 초과 전송과 전체 agent/UI 인증은 미완이다.

## FYI 경계의 용량 회복

Native agent_end 경계에서 수락하지 못한 FYI도 SDK의 백그라운드 재시도로
넘긴다. Hook은 예약된 RetryAdmission만 처리하고 현재 turn을 진행시킨다.
일반 권한·수명 오류는 숨기지 않는다. SDK는 실제 재인수한 packet의 명시적
wake metadata만 사용하며, FYI와 metadata가 없는 packet을 깨우지 않는다.

`--capacity-fyi` fixture는 임시 native 구성에만 conversation-access를 허용하고
실제 global hook runner를 호출한다. 32개 fixture 항목 때문에 FYI claim이
반환된 것을 정본에서 확인하고, fixture 항목을 비운 뒤 새 메시지/notification
없이 재수락·prompt helper 소비·ACK를 확인했다
(`openclaw-native-fyi-capacity-first.json`). 예약 처리를 제거한 변이에서는
hook 반환과 claim 반환 뒤 수락이 없어 실패했다(`fyi-boundary-sdk-mutant.json`).
SDK caller와 hook은 fixture이며 실제 agent/model/UI 실행은 아니다.

```sh
/isolated/node scripts/probe-openclaw-loader.mjs /isolated/node_modules/openclaw deliverables/openclaw-fyi-capacity.json --queue 1 --capacity-fyi
```

## 바이트 예산과 큰 원문의 burst

Native 수신기의 구현 기본값은 16개 항목/512 KiB UTF-8 렌더 본문이다.
SDK가 제한된 inbox를 읽고 cursor를 따라 진행한다. Native 세대·정책 guard와
전체 조각 공간 예약은 그대로 적용한다. 첫 oversized 원문은 단독으로 받으며,
그 원문 자체가 32조각을 넘는 경우의 전송은 여전히 미완이다.

실제 SDK의 burst fixture는 약 8만 UTF-16 길이 원문 32개를 소비 없이 먼저
전송했다. 이후 native prompt helper에서 전체 본문·Unicode·공백과 조각을
검사하고 원문별로 명시적 ACK를 보냈다. 2개씩 16묶음/총 96조각으로 모두
수락·소비·ACK됐고 중복 소비는 없었다(`openclaw-byte-burst-first.json`).
고의적인 소비 지연을 포함한 회복 시험이며 정상 부하의 100표본 p95 인증이 아니다.
모델·사람과 실제 agent turn도 실행하지 않았다.

```sh
/isolated/node scripts/probe-openclaw-loader.mjs /isolated/node_modules/openclaw deliverables/openclaw-burst.json --queue 32 --burst-context
```

```sh
/isolated/node scripts/probe-openclaw-loader.mjs /isolated/node_modules/openclaw deliverables/openclaw-large.json --queue 100 --large-context
```

## Native commit 직후 소비되는 경우

`patchSessionEntry`가 반환한 committed entry에서 SID·lifecycle revision과
전체 조각의 내용을 검증한다. Prompt consumer가 commit 직후 큐를 비워도
뒤따르는 재조회가 비었다는 이유로 이미 수락된 claim을 반환하지 않는다.
반환값이 null이면 현재 큐의 정확한 전체 조각 검증을 유지하며, 다른 대화의
반환 entry는 거부한다. 즉시 drain 회귀는 수정 전 실패·수정 후 통과했다.

Linux burst에서 관측한 간헐적 ACK token 실패는 별도 미결이다. 재실행
32/32 통과를 그 실패의 해결 증거로 쓰지 않는다. 플랫폼별 상세 표본과
미실행 범위는 [Linux 검증 기록](../plan/runtime-protocol/linux-validation.md)에 있다.

## Backend 종료 뒤 다음 도구 호출에서 복구

등록한 backend의 transport 종료를 관측한 뒤 다음 native 도구 호출은
이전 host를 닫고 같은 대화·ref에 새 세대로 등록한다. 동시에 들어온
호출은 복구 하나를 공유한다. Session end/dispose 중인 복구는 새 host를
만들지 않으며, 실패한 operation은 자동 재실행하지 않는다.

이 진입 경로와 별도로, 아래의 등록 세션 자동 재접속도 구현했다.
`agent_end` hook도 아래의 turn 종료 복구 경로를 사용한다. 종료 전에 claim한
원문과 기존 native queue의 token 회수는 별도 검증이 필요하며, 빈 inbox
상태에서 종료한 표본을 그 증거로 쓰지 않는다.

```sh
/isolated/node scripts/probe-openclaw-loader.mjs /isolated/node_modules/openclaw deliverables/openclaw-recovery.json --queue 100 --recover-context
```

이 fixture는 실제 native loader·도구와 prompt helper를 사용하지만
모델·사람 UI·실제 agent turn·메신저를 실행하지 않는다.

Mac 고정 SDK에서 위 경로로 재등록한 뒤 큰 원문 100/100 수락·소비·ACK,
복구 후 전송 p95 상한 504.905ms가 통과했다
(`openclaw-boundary-recovery-native-100.json`). 공통 gate는 406개/68.904초다.
이 표본의 Linux native·종료 전 claim 회수는 미완이다. 자동 재접속의 후속
검증은 다음 절에서 구분한다.

## 등록 세션의 자동 재접속

이미 등록된 host의 transport 종료를 감지하면 새 native 호출 없이
250ms 뒤 재등록한다. 일시적 transport 오류의 재시도 간격은 두 배씩
최대 5초까지 늘리고 성공하면 초기값으로 되돌린다. 같은 대화·workspace와
ref를 유지하며 새 generation을 사용하고 이전 busy/idle 상태를 복원한다.
수신 native scope는 등록 시의 대화 정보에서 만들며 이전 도구 호출의
assertInvocationCurrent callback을 재사용하지 않는다. Session end·dispose는
예약을 취소하고 진행 중 복구도 epoch 검사로 차단한다. 실패한 작업을
재실행하지 않는다. Native agent를 깨우거나 모델을 호출하는 기능과는
구분한다. 최초 등록 전 실패의 자동 재시도와 종료 전 claim·기존 queue
token 회수, agent_end의 별도 복구, Linux 검증은 아직 미완이다.

```sh
/isolated/node scripts/probe-openclaw-loader.mjs /isolated/node_modules/openclaw deliverables/openclaw-auto-recovery.json --queue 100 --auto-recover-context
```

고정 native SDK/macOS arm64/Node 24.22.2에서 native 호출 없는 재등록 후
큰 원문 100/100 수락·소비·ACK가 통과했다. 복구 후 전송 p95 상한은
511.044ms다(`openclaw-auto-reconnect-native-100.json`). Outage 전체 지연이나
종료 전 claim 회수의 증거는 아니다. 모델·사람·실제 agent turn은 0회다.

Linux arm64의 같은 고정 SDK에서도 native 재진입 없는 자동 복구와
복구 뒤 큰 원문 100/100 수락·소비·ACK가 통과했다. 복구 후 전송 p95
상한은 409.313ms다
(`linux-openclaw-auto-reconnect-native-100/output/native-queue-100.json`).
종료 전 claim·기존 queue token 회수·간헐적 burst ACK 실패와 전체 지원
범위는 미완이며, 위 Linux 미실행 기록의 후속 표본으로 구분한다.

## 종료 전에 큐에 수락된 원문의 token 복구

자동 재등록 뒤에도 이전 큐의 본문과 이전 token 안내를 보존한다. 이전
token은 새 host에서 거부된다. 이때 ACK 안내의 `message_ids`로
`xsm_inbox`를 조회하면 이미 소유한 현재 token을 읽을 수 있다. Lease를
연장하거나 원문을 다시 수행하지 않고, 새 token으로 명시적 ACK한다.

고정 native SDK/macOS에서 큰 원문을 수락한 뒤 backend를 종료하고
자동 재등록·기존 큐 보존·이전 token 거부·현재 token 재조회·ACK 및
중복 prompt 소비 없음을 확인했다(`openclaw-owned-claim-recovery.json`).
이는 해당 표본의 claim 복구이며 간헐적 Linux burst ACK 오류 전체를
해결했다는 판정은 아니다. Linux의 이 경로 검증은 아직 미실행이다.
모델·실제 agent turn·사람 UI는 0회다.

```sh
/isolated/node scripts/probe-openclaw-loader.mjs /isolated/node_modules/openclaw deliverables/openclaw-claimed-recovery.json --queue 1 --recover-claimed-context
```

## Agent turn 종료 시 transport 복구

Conversation access를 명시적으로 허용한 `agent_end` hook은 등록된
host가 종료됐다면 도구·자동 재접속과 같은 복구를 공유한다. 새 host에서
자연 inbox 경계를 처리한 뒤 idle 상태를 기록한다. 이전 도구 호출의
invocation callback은 재사용하지 않는다. 다른 route의 hook은 무시하고
이미 session_end/dispose한 참여는 다시 열지 않는다. 복구 중 종료되면
새 host 생성과 후속 idle 쓰기를 막는다.

연결 fixture 12개가 통과했으며, 실제 native hook runner 검증은 별도
프로브로 구분한다. 이 경로가 실제 모델 turn 종료나 물리적 UI 실행을
검증했다는 뜻은 아니다.

```sh
/isolated/node scripts/probe-openclaw-loader.mjs /isolated/node_modules/openclaw deliverables/openclaw-boundary-recovery.json --queue 100 --recover-boundary-context
```

고정 OpenClaw 2026.10.9/macOS arm64/Node 24.22.2의 실제 hook runner에서
재등록·idle 복원 뒤 큰 원문 100/100 수락·소비·ACK가 통과했다
(`openclaw-agent-end-native-100-verified.json`). 복구 후 전송 p95 상한은
514.525ms다. 공통 gate 416개는 74.598초에 통과했다. 모델·실제 turn·
사람 UI 실행과 Linux의 이 hook 경로 검증은 아직 미완이다.
