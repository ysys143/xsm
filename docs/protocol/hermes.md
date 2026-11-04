# Hermes 0.22.5 실험 연결

기본 지원: Hermes plugin으로 XSM 도구와 pull inbox/ACK를 사용한다. Native wake와 질문 bridge는 별도 opt-in이다.

상태: 실험 구현. 실제 PluginContext/도구 registry와 native agent turn,
macOS Telegram 개인 대화의 pull/ACK/reply 왕복을 확인했다.
CLI/TUI 전체 수명·자동 주입·실제 사용자 UI·worker 전체 행렬은 미완이다.
명시적 opt-in의 native clarify 질문 bridge를 추가했으며 native AIAgent의
model0/합성 UI callback으로 검증했다. 사람 UI나 실제 모델의 질문 경로 인증은 아니다.

후속 [Telegram 실제 사용자 질문 표본](../plan/runtime-protocol/hermes-telegram-ui-live.md)은
native adapter/AIAgent에서 실제 선택을 받아 적용했다. Provider는 scripted였고
GatewayRunner 전체 UI나 다른 표면의 인증으로 확대하지 않는다.
명시한 프로필에 대한 소유권 기반 파일 설치·업데이트·제거는 지원한다.

[`integrations/hermes/xsm.py`](../../integrations/hermes/xsm.py)의 `register(context)`는
공통 서버의 현재 스키마로 `xsm_migrate`를 포함한 native 도구 23개를 등록한다. 아래 초기 표본의
21개는 xsm_doc 추가 전 수치다. 도구 dispatcher가 제공한
`session_id`와 native `session_cwd()`를 사용하고 기존 참여의 폴더 일치를 확인한다.
모델 인자로 발신자를 고르거나 gateway 프로세스의 cwd를 대신 쓰지 않는다.
프로필은 등록 시 실제 Hermes home으로 고정한다.

`on_session_end`는 turn 종료이므로 idle로만 갱신한다. 실제 finalize/delete에서
참여를 닫고, 같은 native ID를 다시 열면 주소를 유지하면서 세대를 바꾼다.
Native 세션 시작 hook이 작업 폴더 변경을 확인하면 이전 참여를 닫고 같은
주소의 새 세대로 전환한다. 도구 호출만으로는 폴더를 바꿀 수 없으며, 이전
폴더의 늦은 호출도 거부한다.

SDK는 immutable root마다 별도 Python package namespace로 로드한다. 같은
프로세스에서 서로 다른 snapshot의 client 클래스가 먼저 import된 버전으로
섞이지 않게 한다. 비동기 수명과 정책은 공통 `XsmHost`가 처리한다.

## 현재 동작과 증거

Directory entry `__init__.py`와 도구 21개/수명 hook을 선언한 `plugin.yaml`을
제공한다. 실제 0.22.5 manifest parser와 directory loader의 import를 통과했다.
이 검사는 활성화 정책·plugin validator·실제 agent 실행을 증명하지 않는다.
원시 결과는 `hermes-directory-entry-fixed.log`에 남겼다. 첫 호출은 parser
인자를 잘못 전달해 실패했으며 그 로그도 보존했다.

후속 실제 native validator는 15개 검사를 경고 없이 통과했다
(`hermes-validator-final.log`). 기록용 context가 핸들을 반환하지 않는 경우도
native API 계약대로 허용하며 충돌 처리는 native registry에 맡긴다. SDK 직접
실행에서는 도구 21개가 실제 등록됨을 별도로 확인했다. Private session 모듈
import는 제거했다. 초기 validator 실패도 `hermes-validator-first.log`에 남겼다.

기본 연결은 pull 방식이다. Native push가 없어 events를 광고하지 않으며 기본값은
user-decisions도 광고하지 않는다. 읽기는 `xsm_inbox`, 소비는 명시적 `xsm_ack`로
구분한다. 질문/승인이 필요한 작업은 답을 만들지 않고 거부한다.

## Native 질문 bridge (실험적 opt-in)

프로필의 `plugins.entries.xsm.settings.native_questions: true`를 명시하고 plugin을
다시 로드하면 user-decisions를 연결한다. 설치기가 이 설정을 바꾸지는 않는다.
기존 native toolset 목록에는 `xsm`과 `clarify`가 있어야 한다. Native UI를 제공하지
않는 실행 모드나 도구 정책을 이 bridge가 우회하지 않는다.

XSM 작업은 waiting-for-user와 native_ui 지시를 반환한다. 모델은 그 인수 그대로
native clarify를 호출하고 원 XSM 작업을 동일 인자로 다시 호출한다. 실제 답은
모델의 본문/인용에서 받지 않고 native post_tool_call 관측에서 수집한다. SDK는
답 저장 영수증을 기다리지만 원 작업 적용은 자동으로 하지 않는다.

Native 질문에는 표시 ID/nonce heading과 원 질문 본문이 있다. Protocol의 displayed는
이 본문을 정확히 attestation한다. Bridge는 heading·본문·선택지 모두를 검증한다.
긴 canonical 선택값은 본문 legend에 온전히 두고 짧은 Value 번호로 매핑한다.
Native의4개 선택지 제한에는 값2개+이전/다음 페이지를 사용하며 선택값을 자르지 않는다.
자유 입력도 native callback에서 실제 반환된 값만 받는다.
선택지 질문의 Other 입력도 canonical 값과 정확히 일치하면 받으며, UI 번호나
현재 제공된 navigation label과 충돌하면 표시된 UI 동작을 우선한다.

현재 profile, session, protocol 실행 세대, 질문 표시, native turn/API request/
tool occurrence/질문 index를 결속한다. 이미 사용한 occurrence, 늦은 이전 표시,
변경된 본문/선택지와 중복 질문의 상충 응답은 승인으로 적용하지 않는다.
UI 미제공·timeout은 답을 만들지 않고 표시 포기로 처리한다. 취소도 허용이나
거부로 바꾸지 않는다. [구현 증거와 미완 조건](../plan/runtime-protocol/hermes-native-questions.md)을 따른다.

`scripts/probe-hermes-tools.py`는 실제 고정 SDK의 PluginContext, registry.dispatch,
hook dispatcher에서 등록·세션/폴더 분리·전송/pull/ACK·caller 불일치 거부·
turn 종료와 finalize/resume 구분·미연결 UI 거부를 확인한다. 호출 세션은 명시적
fixture이며 실제 Hermes agent나 외부 메신저의 동작을 시험한 것은 아니다.

```sh
/isolated/hermes-env/bin/python scripts/probe-hermes-tools.py --native-source /isolated/hermes-source --output deliverables/hermes-tools
```

모든 HOME/HERMES_HOME/XSM_HOME은 새 임시 경로다. v0.22.5 tag와 실제 import
경로를 대조한다. SDK 의존성은 고정 lock으로 설치하며 API 키나 실제 모델을
사용하지 않는다. 직접 등록 경로의 결과는 `hermes-public-api-final/result.json`에 있다.
최초 전송은 서로 다른 비 git 폴더라 정책이 거부했다. 같은 저장소의 두 작업
폴더를 만드는 것으로 fixture를 고쳤으며 그 거부를 우회하지 않았다.

## 안정판 API 감사와 남은 연결

`probe-hermes-tools.py --discover`는 새 임시 프로필의 plugin 폴더와 enabled 목록을
준비하고 실제 native discovery로 활성화한다. 도구 21개 등록부터 dispatch,
세션 수명, unload 뒤 도구 제거와 모든 참여 종료까지 7개 검사가 통과했다
(`hermes-discovery-unload/result.json`). 프로필은 전부 시험용이며 실제 agent
turn·설치기의 소유권 관리·자동 주입·UI를 검증한 것은 아니다.

PluginContext에 session_key 메서드가 없다는 이전 조사만으로 불가능하다고
판정하지 않는다. 고정 버전에는 별도
[plugin_session](https://github.com/NousResearch/hermes-agent/blob/v0.22.5/hermes_cli/plugin_session.py)의
task-local session_key와
[session_context](https://github.com/NousResearch/hermes-agent/blob/v0.22.5/gateway/session_context.py)의
async_delivery_supported가 있다.

[inject_message](https://github.com/NousResearch/hermes-agent/blob/v0.22.5/hermes_cli/plugins_injection.py)의
True는 표면별로 의미가 다르다. Local TUI는 실제 큐 수락이지만 messaging
gateway는 작업 예약 뒤 비동기 dispatch 결과가 실패할 수 있다. Classic CLI는
session_key를 검사하기 전에 현재 REPL 큐로 들어간다. 이를 동일하게 admitted로
바꾸지 않으며, 실제 세션/세대와 수락 근거가 검증되는 adapter가 추가로 필요하다.

[ask_choice](https://github.com/NousResearch/hermes-agent/blob/v0.22.5/hermes_cli/plugin_choices.py)는
동기 slash-command의 asker 문맥에 한정된다. 일반 native 도구에서 그대로
호출해 사용자 응답을 확보할 수 있다고 가정하지 않는다. Agent의 clarify는
별도 inline 실행 경로를 쓰므로 registry.dispatch만으로 UI를 대신하지 않는다.
Native UI 결속과 messaging requester 신원은 미완으로 유지한다.

고정 SDK의 일반 모델 dispatcher는 optional parent_agent를 전달하지 않았고,
직접 registry 호출에 이를 넣은 표본과 구분했다. Native MCP elicitation의
accept도 선택 필드 없이 content={}를 반환했다. 따라서 이를 실제 answer로
보충하지 않는다. [UI 경계 재검증](../plan/runtime-protocol/hermes-ui-boundary.md)은
의존성 누락으로 실패한 초회와 MCP extra를 격리 설치한8개 확인을 구분하며,
실제 agent나 사용자 UI 지원 완료를 뜻하지 않는다.

## Workspace 전환과 동시 종료

후속 discovery 검사는 native session-start의 폴더 전환, 같은 주소의 세대 교체,
이전 폴더의 늦은 도구 호출 거부를 포함해 8개다.
`hermes-finalize-native/result.json`에 결과를 남긴다.

연결 생성 중 finalize가 참여 항목을 먼저 제거하면 `KeyError`가 발생했다.
`tests.test_hermes_binding`은 SDK open을 의도적으로 지연시켜 이 순서를
재현한다. 수정 전 실패 로그는 `hermes-finalize-race-red.log`이며, 연결 생성과
종료를 같은 락으로 직렬화한 뒤 Python 3.9/3.14에서 통과했다.
이는 coordinator의 제어된 동시 실행 검사이며 실제 agent 실행 증거는 아니다.


## 프로필 설치와 제거

```sh
xsm protocol install hermes --home /path/to/hermes-profile --dry-run
xsm protocol install hermes --home /path/to/hermes-profile
xsm protocol inspect hermes --home /path/to/hermes-profile
xsm protocol uninstall hermes --home /path/to/hermes-profile
```

설치기는 `plugins/xsm/__init__.py`와 `plugin.yaml`을 생성하며 고정 Python과
불변 xsm 스냅샷을 사용한다. 파일별 해시와 변경 전 기록으로 중단된 설치·
업데이트·제거를 재시도한다. 사용자 편집, 소유하지 않은 파일, 심볼릭 링크는
덮어쓰지 않는다. 제거는 두 소유 파일만 지우며 다른 파일과 디렉터리를 남긴다.

Hermes 0.22.5는 `config.yaml`의 `plugins.enabled`에 `xsm`이 포함돼야 불러온다.
설치기는 이 활성화 목록이나 권한 설정을 변경하지 않는다. 결과의
`activation: operator-opt-in`은 이 별도 활성화 요건을 나타내며 현재 활성화
여부를 판독했다는 뜻은 아니다. 적용 후 Hermes를 다시 불러와야 한다.

`probe-hermes-tools.py --installed`는 임시 프로필에 명시적 활성화 목록을 먼저
준비한 뒤 실제 설치·native discovery·21개 도구 등록·전송/pull/ACK·수명주기·
제거와 설정 보존을 확인한다. 9개 검사는
`hermes-owned-install-native-canonical/result.json`에 기록했다. 최초 비교는
macOS의 `/var`와 `/private/var` 표기 차이로 실패했고 원시 로그를 보존했다.
이 검사는 모델·실제 사용자 UI·push·Linux·자동 활성화 상태 판독을 검증하지 않는다.

## 로드된 스냅샷의 수명

설치 스냅샷에서 등록된 플러그인은 Hermes 프로세스의 PID·시작 시각에 결속한
`hermes-plugin` component lease를 먼저 확보한다. 세션을 아직 열지 않았거나
설치 파일을 제거한 뒤에도 snapshot prune이 실행 중인 코드를 보존한다.
등록 실패와 native unload에서 coordinator를 닫은 다음 정확히 자신이 만든
lease를 해제한다. 수정된 lease나 다른 부모 프로세스의 lease는 지우지 않는다.
Checkout 직접 등록은 설치 스냅샷 lease를 만들지 않는다.

실제 0.22.5의 `--installed` 프로브는 로드 직후 설치 파일을 제거한 상태에서
도구 호출을 계속하고, unload 뒤 lease 파일이 사라지는 것까지 11개 검사를
통과했다(`hermes-component-lease-native/result.json`). Lease 생성을 생략한
변이는 같은 검사에서 실패했다(`hermes-component-lease-mutant/result.json`).
별도 prune 검사는 native 세션과 설치 loader 없이 살아 있는 Hermes lease만으로
이전 스냅샷이 남는 것을 확인한다. 실제 모델·UI·Linux 검증은 포함하지 않는다.

## Native injection 반환값과 대상 감사

`scripts/probe-hermes-injection.py`는 v0.22.5의 실제 PluginContext와
`plugins_injection`, TUI `plugin_inject`, `_enqueue_prompt` 함수 본문을
사용한다. Native method_ctx 방식으로 함수들을 시험 namespace에 결속한다.
세션 행·프로필·busy 상태는 명시적 fixture이며 실제 TUI 서버나 모델은 아니다.
두 임시 프로필에만 주입 허용/거부 설정을 만들며 사용자 설정은 읽거나
바꾸지 않는다. 모델 drain은 시험 guard로 막는다.

고정 태그와 tracked 소스 일치를 확인한 실행의 9개 검사는 다음을 보였다
(`hermes-native-injection-source-verified/result.json`).

- 프로필 정책이 거부하면 native 큐가 바뀌지 않는다.
- 허용된 keyed busy TUI 주입은 일치하는 세션 큐에 들어간다. 기존 사용자
  입력과 transport를 유지하며 실행 중 turn을 중단하지 않는다.
- TUI 키가 없고 gateway도 없으면 False다. Gateway callback을 붙이면 같은
  누락 키가 True를 반환할 수 있으며 TUI 큐에는 들어가지 않는다. 이 True는
  시험 gateway의 예약 수락이며 실제 메신저 전달이 아니다.
- Classic CLI는 session_key가 맞지 않아도 현재 REPL의 pending 큐로 넣는다.
- 이미 진행 중인 원문과 같은 text는 새 큐 항목을 만들지 않아도 True다.
  이 경우 별도 readback 없이 새 큐 수락 시간으로 계측하지 않는다.
- 서로 다른 프로필의 fixture 행에 같은 키를 두면 native TUI matcher는 먼저
  나온 행을 선택한다. 이 시험은 실제 운영에서 중복 키가 생성된다는 증거가
  아니며, API 반환값이 프로필 결속까지 검증한다는 보장도 아니다.

키 비교를 제거하거나 정책 거부를 우회한 시험 변이는 각각 keyed routing과
거부 뒤 무변경 검사에 실패했다(`hermes-injection-mutant-ignore-key/result.json`,
`hermes-injection-mutant-ignore-policy/result.json`). 원본 native 파일은 수정하지
않고 시험 프로세스의 함수·객체에만 변이를 넣었다.

현재 제품의 pull 연결을 단순히 inject_message=True이면 admitted인 연결로
바꾸지 않았다. 자동 수신 구현에는 native 대화 ID·프로필·세대와 라우팅 키의
검증, queue/context readback, gateway 비동기 실패와 구분된 수락 근거가 필요하다.
이는 남은 구현 조건이며 범위에서 제외한 것이 아니다. Idle wake·busy/now의
실제 우선순위·실제 native turn·UI·메신저와 전체 P4/P5는 여전히 미완이다.

## 백엔드 종료 뒤 다음 호출에서 복구

프로토콜 백엔드가 종료된 뒤에도 Hermes의 native 세션은 살아 있을 수 있다.
다음 xsm 도구 호출이나 session-start hook은 실패한 host를 닫고 같은 native
대화·프로필·검증된 workspace로 다시 참여한다. 주소는 유지하지만 participation
세대·프로세스·claim 토큰은 새로 만든다. 이전 세대의 claim으로 ACK할 수 없으며
원문을 다시 읽고 새 토큰으로 소비해야 한다.

이미 실패한 작업은 이 경로가 자동 재실행하지 않는다. 전송·권한 변경처럼
효과가 불명확한 작업은 해당 request ID와 도메인 상태를 확인해야 한다.
위 표본은 다음 native 호출에서의 복구를 다룬다. 입력 없는 복구는 아래 후속 절로
구분하며 모든 런타임의 재접속 완료를 뜻하지 않는다.

새 실제 backend 검사는 기존 claim이 있는 서버를 강제 종료한 뒤 같은 주소의
새 세대에서 원문 회수·이전 토큰 거부·새 토큰 ACK를 확인한다. 제어된 SDK 검사도
실패한 전송을 반복하지 않고 다음 inbox 호출만 새 host로 보내는 것을 확인한다.
변경 전 실제 검사 실패는 `hermes-recover-red.log`에 있다. 최초 수정 검사는
ACK 오류 문구를 잘못 예상해 실패했고 그 로그도 보존했다. 최종 검사는 공개
오류 코드 `-32602`를 대조한다.

`probe-hermes-tools.py --installed --crash`는 실제 0.22.5 plugin discovery와
registry.dispatch에서 같은 복구를 포함한 12개 검사를 통과했다
(`hermes-recovery-native/result.json`). 시험은 종료 대상의 부모 PID가 현재
프로브인지 확인하며 임시 프로필의 자체 backend만 종료한다. Native agent,
UI·메신저를 실행한 결과가 아니다.


## 등록 참여의 입력 없는 복구

세션별 monitor가 등록된 host의 transport 실패를 관측해 같은 native SID와
마지막으로 검증된 workspace에 다시 참여한다. 정상 시 확인 간격은 250ms이며
연결 실패가 계속되면 대기를 두 배로 늘려 최대 5초로 제한한다. 마지막 hook의
busy/idle 상태를 복원한다. SDK 작업이나 native 작업은 자동 재실행하지 않고
inbox도 자동으로 읽거나 ACK하지 않는다.

Workspace 전환은 이전 monitor를 취소한다. Finalize/delete/reset과 unload는
복구 task를 취소하며, unload는 진행 중 backend open도 취소한 뒤 coordinator
thread와 component lease를 정리한다. 마지막으로 검증한 workspace를 유지하는
동작이며 새 작업 폴더의 신원을 background에서 추정하지 않는다.

Python 3.9.6 관련 8개는 실제 backend 종료 뒤 입력 없는 재등록·상태 복원·
finalize 취소, unload 중 미완료 open 취소와 backoff를 통과했다
(`hermes-auto-reconnect-final-tests.log`). Monitor를 끈 변이는 자동 등록 검사에
실패했다(`hermes-auto-reconnect-disabled-mutant.log`). 실제 0.22.5 설치본 registry도
native dispatch 전 새 PID/세대·상태 복원을 관측했고 원문 보존·이전 claim 거부·
새 ACK를 포함한 13개가 통과했다(`hermes-auto-reconnect-native-final/result.json`).
현재 연결 코드 해시도 대조했다. 호출자는 fixture이며 실제 agent/model 실행이 아니다.

공통 389개는 65.631초에 통과했다(`hermes-auto-reconnect-gate-final.log`). Native
push/UI·최초 생성 실패의 자동 복구·handshake 응답 기한과 대화별 등록 동시성
확대, worker·Linux·메신저와 전체 P0–P5는 미완이다. Pull-only 연결이므로 이
결과를 native queue p95나 모델 소비 인증으로 쓰지 않는다.

## 대화별 등록 잠금

등록·복구·finalize 잠금을 native SID별로 분리했다. 다른 대화가 초기 응답을
기다리는 동안 이미 열린 대화의 요청과 별도의 새 등록이 진행된다. 같은 SID의
생성/종료는 계속 직렬화한다. 종료가 시작되면 새 open을 막고, 대기하던 open이
끝나더라도 host를 닫아 호출자에게 종료 오류를 전달한다. Unload는 미완료 open을
취소한 뒤 대화별 잠금을 정리하므로 backend를 남기지 않는다.

기존 공통 잠금에서는 느린 등록이 빠른 대화를 막아 새 검사가 실패했다
(`hermes-conversation-lock-red.log`). 수정 후 Python 3.9.6 관련 9개가 통과했다
(`hermes-conversation-lock-final-tests.log`). 첫 확대 검사는 finalize 중 열린 host를
그대로 반환한다고 기대해 실패했다. 기준을 host 닫힘과 호출자의 종료 오류로
맞춘 뒤 통과했으며 이전 로그도 보존했다.

실제 Hermes 0.22.5 PluginContext/registry.dispatch에서도 한 backend의 session.open을
marker로 막고 다른 대화의 inbox 요청을 보냈다. 느린 등록이 대기 중인 동안 빠른
호출이 완료됐다(`hermes-conversation-isolation-native/result.json`). 이 표본은 직접
등록한 native API fixture이며 설치/autoload나 실제 agent turn의 동시 실행으로
확대하지 않는다. 별도 설치본 자동 복구 회귀 13개도 통과했다
(`hermes-conversation-lock-native/result.json`).

공통 390개는 65.863초에 통과했다(`hermes-conversation-lock-gate-final.log`).
초기 handshake 응답 기한·Native push/UI·worker·Linux·메신저와 전체 P0–P5의
남은 조건은 미완이다.

## Linux arm64의 고정 native API 검증

Hermes v0.22.5/commit `bf0203a794a07aac3ff764972ab9087baa4e4f4e`를
Python 3.14.10의 격리 Linux image에서 실행했다. 실제 plugin 도구·설치·
자동 복구·수명 검사 13개와 주입 API 관측 9개가 통과했다
(`linux-hermes-native/output/{tools,injection}/result.json`). 같은 환경에
고정 Node 24.22.2를 더한 공통 gate 416개는 100.502초에 통과했다
(`linux-python-314-hermes-core/result.json`).

위 Linux 미실행 기록의 후속 표본이다. Dependency/image/source hash와
fixture 경계는 [Linux 검증 기록](../plan/runtime-protocol/linux-validation.md)에
있다. 주입 API의 session 행·namespace는 fixture이며, 실제 agent turn·
물리적 CLI/TUI·모델·사람 UI·native push p95·worker 인증은 아니다.
기본 제품 연결은 계속 pull-only이며 events/user-decisions를 광고하지 않는다.

별도 `--slow-registration`의 native 8개도 통과해 다른 세션의 느린
backend 등록이 정상 세션 도구를 막지 않는 것을 확인했다
(`linux-hermes-slow-registration/output/result/result.json`). 앞선
13개와 중복되는 항목은 별도 표본으로 구분한다.

## macOS 실제 agent 및 Telegram pull 왕복

이후 전용 시험 프로필에서 실제 AIAgent와 GatewayRunner를 실행했다. 기존 구독
프록시의 live catalog 모델을 사용했으며 API 키 과금 경로를 만들지 않았다.
모델의 native tool_search→xsm_inbox→xsm_ack→xsm_send 호출과 sender의 reply
수신/ACK를 실제로 확인했다. Telegram 개인 대화에서도 사용자가 보낸 지시로
생성된 native 세션이 같은 pull/ACK/reply를 수행하고, 확인 nonce의 최종 외부
전달이 native delivery ledger의 delivered로 기록됐다. 시험용 gateway는 종료됐다.

Telegram 표본의7개 검사는 통과했지만, 모델이 처음 xsm_send에 잘못된 `to` 인수를
전달한 실패1회와 이후 성공을 모두 보존했다. 첫 대기 timeout도 별도 실패로
기록했다. configured/requested model과 실제 served model을 구분하며, 후자는
이 표본에서 확인하지 못했다. 전용 프로필·수신자 식별자·비밀 token은 저장소에
포함하지 않는다.

상세 경계와 실행 기록은 [Telegram 시험 기록](../plan/runtime-protocol/hermes-telegram-live.md)에
있다. 이 증거는 wake=never인 FYI의 pull 경로다. native push/idle p95·사용자 승인
UI·worker·다중 대화·Discord·Linux Telegram 또는 전체30방향 조합의 통과를
뜻하지 않는다. 앞선 API fixture의21개 도구 수치와 이번 실제 agent 표본도
서로 다른 시점의 관측으로 구분한다.

## Native child worker API의 실제 표본

고정 버전의 공개 PluginContext.subagent_lifecycle을 실제 native 부모 모델의
도구 호출에서 실행했다. Launch/status/wait/result·같은 프로세스 내 reconnect·
correlation 중복 거부의9개와 별도 cancellation/미지원 옵션 거부의10개를
확인했다. Cancellation 표본은 자식 모델 호출 전에 종료됐으므로 공급자 요청
도중 중단의 증거는 아니다. 이 경로는 아직 xsm_owned provider에 연결되지 않았다.
작업 폴더 지정·실행별 timeout·개별 도구 차단 등 기존 기능의 제약과 실패 기록은
[native worker 연결 기록](../plan/runtime-protocol/native-worker-boundary.md)에 있다.
기존 worker 입력 enum이나 지원 상태는 이 API 표본만으로 확장하지 않는다.

## Opt-in natural-turn FYI context

`plugins.entries.xsm.settings.native_context: true` connects `pre_llm_call` and
`pre_api_request` in Hermes0.22.5. The first hook stages unread peer context for
that exact native session/turn. The second verifies the complete nonce-tagged
text in the actual native user-context messages before recording admission.
Private question display, profile and host-generation checks remain separate.

The host uses natural-boundary-only SDK delivery: an idle FYI starts no model
turn, and retries/batches do not escape into background delivery. Closing a turn
before observation releases its original claims; consumption still requires an
explicit xsm_ack. The default remains off until enabled by the profile operator.
This mode alone does not connect idle push/wake or certify actual user UI.

## Opt-in gateway FIFO delivery

On the pinned Hermes0.22.5 gateway path, setting
`plugins.entries.xsm.settings.native_context: true`,
`plugins.entries.xsm.settings.native_wake: true`, and the native permission
`plugins.entries.xsm.allow_gateway_injection: true` enables native FIFO admission
for wakeable messages. The permission belongs to the entry itself, outside settings.
The plugin does not change these settings. A non-boolean native_wake or missing
dependency is rejected. Classic standalone CLI is not connected through this mode.
Messaging routes require a previously committed native connector envelope and current
platform authorization; a named route alone cannot create that provenance.

The binding captures the native manager's published gateway owner and the calling
turn's actual session key and SID. It pins the profile authority and epoch, checks
the exact conversation again on the native loop, and submits an internal automation
input. Local FIFO preserves an explicit bot author. Messaging FIFO uses native
automation provenance without promoting the input to viewer authority; its borrowed
source identifies the authorized connector route, not the peer's authorship. It
checks the durable admission receipt and full original before
reporting queue acceptance. A reused name/route, replaced owner, revoked injection
permission or differing receipt cannot become acceptance. Claim IDs/tokens form the
stable producer identity for an exact retry. FIFO acceptance never calls xsm_ack.

FYI still uses the next natural-turn context boundary. The initial local FIFO probe
disables drain scheduling and uses a context facade. A subsequent
[actual native drain probe](../plan/runtime-protocol/hermes-gateway-drain.md) loads
the installed plugin with the real PluginContext, runs the FIFO and AIAgent hooks,
and checks awake delivery and strict FYI through native tool ACK. Its provider is
scripted localhost HTTP. A [messaging probe](../plan/runtime-protocol/hermes-messaging.md)
also runs the real DiscordAdapter or TelegramAdapter and native messaging FIFO with
local platform transport. Real inference, interactive UI and external platform delivery remain unverified.
Evidence and remaining work: [local gateway delivery](../plan/runtime-protocol/hermes-gateway-wake.md).
