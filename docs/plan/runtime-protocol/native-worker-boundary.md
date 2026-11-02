# Native worker 연결 경계와 확인 결과

상태: 미완. xsm_owned의 구현된 실행 provider는 아직 Claude/Codex뿐이다.
이 문서는 승인된 전체 계획의 worker 연결에 필요한 실제 native 증거와
제약을 기록한다. 런타임·기능·운영체제 범위를 제외하지 않는다.

## Hermes 0.22.5에서 실행한 경로

고정 commit bf0203a794a07aac3ff764972ab9087baa4e4f4e의
PluginContext.subagent_lifecycle은 공개된 host 서비스다. 실제 부모 AIAgent의
모델이 임시 native plugin 도구를 호출할 때 이 서비스를 사용했다. Native
context가 제공하는 부모 SID와 dispatcher SID가 같은지도 확인했다. 사용자
대화를 worker로 채택하거나 모델 인자로 부모 신원을 선택하지 않았다.

첫 표본은 실제 자식 모델의 확인 문구와 terminal result를 받았으나, 시험기가
reconnect 결과의 connected 필드를 supported로 잘못 읽어 실패했다. 이 표본의
전체 status는 failed로 보존했다. 당시 시험기 process exit0은 잘못된 종료
판정이므로 성공 근거로 쓰지 않는다.

새 nonce/새 부모/새 자식의 두 번째 실행은9개 검사가 통과했다. 자식의 실제
확인 문구, 결과 hash, 같은 프로세스 내 handle reconnect, 이미 종료된 자식을
새로 stop했다고 주장하지 않는 동작, correlation ID 중복 실행 거부를 포함한다.
부모 API calls3, 자식 API calls1이며13.844초였다. 부모/자식의 configured model은
live catalog의 anthropic/claude-sonnet-5-5였고 기존 loopback 구독 프록시를 썼다.
실제 served model ID는 이 응답에 없어 확인하지 못했다.

별도 stop 표본은10개 검사를16.763초에 통과했다. 자식 state=RUNNING에서
cancel accepted를 관측하고 terminal CANCELLED와 실제 결과를 확인했다.
자식 API calls는0이므로 공급자 요청이 진행 중인 모델을 중단했다는 증거는
아니다. Native 실행 경계에서 모델 호출 전 중단된 표본이다. 부모 API calls는3이다.

원시 결과와 실패 로그는 deliverables/protocol-foundation/의
hermes-native-worker-{first,second,cancel-first}/ 및 같은 이름의 log에 있다.
이들은 macOS의 실제 native parent/model/child 경로다. XSM 프로토콜을 거친
worker dispatch, Linux worker, CLI 재개 또는 Telegram worker를 인증하지 않는다.

## 현재 API의 제약

Stop 표본의 실제 native 호출은 working_directory, per-launch timeout_seconds,
blocked_tools를 각각 거부했다. 이를 기본 cwd나 다른 제한으로 조용히 바꾸면
안 된다. Allowed toolsets는 부모 권한을 넓힐 수 없으며 native 검사를 유지한다.

현재 public service는 자식을 프로세스 안에서 관리한다. 동일 프로세스에서
직렬화한 handle의 reconnect는 확인했지만 프로세스 재시작 뒤 자식의 재접속을
검증한 것은 아니다. 고정 소스의 계약도 재시작 뒤 RECONNECT_UNAVAILABLE를
반환하도록 선언한다. 이를 새 실행으로 대체하면 중복 작업이 될 수 있다.
Handle의 capability는 private 상태에만 보관하고 모델이나 공개 로그에 싣지 않는다.

사용자 UI는 별도 문제다. ask_choice는 동기 slash-command asker 문맥에만
연결되며 일반 native tool에는 그 문맥이 없다. 모델의 clarify는 별도 inline
executor가 실제 callback을 제공한다. 단순 registry dispatch나 provider 완료
응답을 사용자 승인으로 사용하지 않는다. 이 UI 연결과 전체 worker cwd/수명/
재접속은 구현 담당 세션이 계속 해결할 미완 기준이다.

## 공통 엔진과 native 연결의 책임

기존 owned journal의 요청 ID·본문 digest·소유 대화·generation·결과 저장과
reply recovery를 유지해야 한다. Native 연결은 실제 launch/status/cancel/result와
handle 검증을 제공하며, 엔진에 새 runtime 이름별 실행 분기를 추가하지 않는다.
모델이 전달한 임의 child ID/handle을 실행 권한으로 삼지 않는다.

실행 요청은 native launch 전에 영속화하고, 같은 요청을 다시 받으면 기존
상태를 조회한다. 연결 유실·프로세스 재시작으로 native 결과를 확인할 수 없으면
unknown으로 유지하며 모델을 자동 재실행하지 않는다. Waiter 취소와 child stop도
구별한다. 새 provider를 연결하기 전에는 현재 미지원 runtime 거부를 유지한다.
Native API가 거부하는 기능은 명시적으로 반환하고 전체 지원은 미완으로 남긴다.

재현용 scripts/probe-hermes-worker-lifecycle.py는 고정 native checkout과 live
loopback catalog를 확인하고 새 private profile에서만 실행한다. 모델 호출을
포함하므로120초 model-free 핵심 gate에 넣지 않는다. complete와 cancel 모드의
구현된 경계를 구분하며, 이 시험기를 제품 worker provider로 사용하지 않는다.

## 재현용 시험기 검증

통합 시험기의 complete 모드는9개 검사를15.432초에, cancel 모드는10개를
19.272초에 통과했다. 각각 native parent API calls3이며 complete의 child1,
cancel의 child0이다. 결과는 hermes-native-worker-harness-complete-v3/와
hermes-native-worker-harness-cancel/에 있다. Token과 native capability는
로그에 포함하지 않고 handle은 새 private profile의0600 파일에만 보관한다.

시험기 통합 중 두 실패도 보존했다. 첫 실행은 불필요한 PyYAML import가 고정
환경에 없어 모델 호출 전 실패했다. 의존성을 추가하지 않고 표준 JSON으로
config.yaml을 작성하도록 고쳤다. 다음 실행은 도구의 dict 인자가 CLI options를
가린 오류로 child launch 전 실패했다. 이 실행의 부모 API calls는3, child0이었다.
명령 옵션과 모델 인자를 분리하고 모델 없는 callback preflight를 추가했다.
그 검사는 수정 전 두 mode 모두 오류였고, 수정 후2개 검사가 통과했다.
기록은 hermes-worker-harness-preflight-{before,after}.log에 있다.

시험기는 기존 구독 경로를 사용하는 개발용 검사다. 예를 들어 고정 native
의존성이 설치된 Python으로 다음을 각각 실행한다. model은 해당 loopback
catalog에서 확인한 실제 ID를 지정한다.

```sh
/isolated/hermes/bin/python -B scripts/probe-hermes-worker-lifecycle.py \
  --native-source /isolated/hermes-source --model <live-model-id> \
  --mode complete --output /tmp/new-worker-complete
/isolated/hermes/bin/python -B scripts/probe-hermes-worker-lifecycle.py \
  --native-source /isolated/hermes-source --model <live-model-id> \
  --mode cancel --output /tmp/new-worker-cancel
```

이 검사는 native delegated child API에 한정된다. 별도의 고정 native CLI에는
chat --format stream-json, --query-file, --resume, --in 경로도 있으므로,
facade가 지원하지 않는 기존 worker 기능을 보존할 수 있는지 구현 담당자가
그 실제 경로를 추가 확인해야 한다. 이를 조사했다는 사실만으로 현재 provider의
cwd/재개 제약을 해결했다고 처리하지 않는다.

## 실제 native CLI의 cwd와 재개

동일 고정 버전에서 python -m hermes_cli.main chat --format stream-json
--query-file - 경로도 직접 실행했다. 새 private HOME/HERMES_HOME/XSM_HOME과
기존 구독 프록시 설정만 사용했다. 첫 CLI는 다른 프로세스 cwd에서 --in으로
지정한 workspace-a에 새 native 세션을 만들었다. 두 번째 CLI는 --resume으로
같은 실제 SID를 재개했고 첫 턴에서만 제시한 확인 token을 기억했다. 프로세스
cwd는 workspace-b였지만 native DB의 frozen cwd는 workspace-a로 유지됐다.

터미널 result의 session_id는70자이며 UUID가 아니었다. CLI 출력을 기존
Claude/Codex UUID 검사에 그대로 넣으면 안 된다. 두 turn 모두 stdout은
system/init→text→단일 terminal result였고 process/result exit0이었다.
총8개 검사를23.426초에 통과했다(hermes-native-cli-first/result.json 및
first/resume-events.json). 전체 stderr는 private profile에0600으로 보관했다.

이 시험이 만든 profile의 native 소유권 검사로 gateway PID를 확인한 뒤
그 PID만 종료했고, native process 생존 검사에서도 종료를 확인했다. 다른
프로필의 gateway를 찾거나 종료하지 않았다. 이 표본은 정상 생성/재개 경로며
gateway 재시작 뒤 재개, 프로세스 중단 후 unknown readback, 실제 XSM owned
provider 또는 worker 도구 송수신의 증거는 아니다.

## Native CLI 명령/결과 연결 모듈

integrations/hermes/worker_cli.py에 native CLI 명령 생성과 엄격한 terminal 결과
해석을 추가했다. 이는 권한·신원·journal을 대신하지 않는 transport 코드이며
아직 xsm_owned runtime 선택에 연결하지 않았다. 첫 실행은 admitted executable과
workspace를 받고 query는 stdin으로만 전달한다. Resume는 소유한 opaque native
ID만 사용하며 새 cwd/model/permission 옵션으로 기존 native launch를 덮지 않는다.
빈 resume ID나 잘못된 ID를 새 세션 생성으로 바꾸지 않는다.

결과는 실제 system/init과 마지막의 단일 result, native exit0, 비어 있지 않은
실제 answer, 동일한 native ID를 요구한다. 중복 JSON key·NaN·실패·불완전한
출력은 거부하고 본문의 JSON은 실행 metadata로 해석하지 않는다. Native UUID를
강제하지 않는다. Task outcome 해석과 provider admission은 공통 서비스의 별도
책임이며 이 모듈은 현재 provider 활성화를 뜻하지 않는다.

순수 framing 검사7개와 임시 소스 변이3개(native ID 교체 허용, 실패 result 허용,
빈 resume를 새 launch로 변환)를 확인했다. 세 변이 모두 assertion 실패로
검출됐고 원본은 변경하지 않았다. 증거는 hermes-worker-cli-contract-unit.log와
hermes-worker-cli-mutants.json 및 각 mutant log다.

이 모듈이 실제 첫 CLI 출력도 읽게 하고, build_command가 만든 native 명령으로
앞서 종료한 private gateway를 다시 시작해 같은 SID를 재개했다. 이전 turn에만
제시한 token을 실제 모델이 기억했다. 새 terminal 결과도 같은 모듈로 해석했고
4개 검사가14.022초에 통과했다(hermes-cli-adapter-resume/result.json).
별도 read-only native DB audit에서 cwd 보존, 누적 API calls3/tool0,
custom/127.0.0.1 경로도 확인했다(native-db-audit.json). Served model은 미확인이다.
시험 gateway는 native 소유권을 확인한 PID만 종료해 실제 생존 검사로 종료를
확인했다. 최초 임시 probe의 package import 실패는 모델/하위 프로세스 시작 전
발생했으며 hermes-cli-adapter-resume-preflight.log로 보존했다.

새 core gate는 Python486+SDK50+Node127=663개 및 독립 mock39/변이14를
84.859초에 통과했다(hermes-worker-cli-contract-core.log). 일반 provider 등록,
profile/binary admission, XSM owned journal/실제 회신 연결은 다음 필수 구현으로
남는다. 이 모듈과 CLI 표본만으로 Hermes worker 지원 완료를 표시하지 않는다.

## Owned 실행 연결과 모델 전 결속 (2026-11-02)

설치본의 고정 provider catalog와 공통 dispatch를 추가했다. Hermes CLI provider는
xsm_owned create/run/status/retry/reconcile와 같은 owned journal·publisher를
사용한다. Classic spawn 경로는 확장하지 않았다. 이전 섹션의 '아직 연결하지
않았다'는 당시 단계이며, 후속 연결의 현재 경계는 native-workers.md에 있다.

첫 직접 native 표본은 실제 모델 결과/회신 저장까지 성공했지만 status의
incoming claim을 시험기가 무시하고 다시 inbox를 읽어 실패했다. 다음 표본은
result-ready를 송신 완료로 해석해 controller를 너무 일찍 닫았다. Sending은
그 자체로 종료 증거가 아니다. 두 실패 파일은 그대로 두고 같은 owned owner와
요청을 재개해, 저장된 결과/동일 reply ID의 전송을 복구했다. 첫 모델 작업은
재실행하지 않았다.

재개한 실제 경로는19개 검사가39.280초에 통과했다
(hermes-owned-native-recovered/result.json). 세 회신의 원문 읽기/명시적 ACK,
70자 native ID의 실제 문맥 재사용, 동일 요청의 idempotent result 재사용,
workspace 보존을 확인했다. Native DB에서 첫 작업+recall은2 calls/tool0,
추가 depth 검사 후 누적5 calls/tool2였다. 실제 native model이 xsm_owned create를
시도했고 상속된 max_depth 거부가 tool transcript에 남았으며 새 서비스는
만들어지지 않았다. Configured model은 live catalog의 anthropic/claude-sonnet-5-5,
served model은 미확인이다. 기존 local proxy의 anthropic authMode=oauth도
읽기 전용으로 다시 확인했다. 시험 gateway는 소유권을 확인한 PID만 종료했다.

단순 프로세스 env의 XSM_WORKER는 공유 gateway의 다른 세션에 섞일 수 있어,
private descriptor로 native 생성 관측을 journal에 먼저 결속했다. 원래 native
CLI 정책/실행을 사용하며 frontend process의 formatter binding 관측만 추가한다.
Ordinary CID는 모델 전에 거부하며, 실제 callback의 PID/generation을 확인하고
새 context ID를 고정한다. Native actor의 raw/protocol-projected 신원을 같은
worker budget으로 찾으며, 다른 profile의 ordinary actor는 worker가 되지 않는다.
이 결속은 입력 큐 수락·원문 ACK·사용자 승인과 별개다.

모델 없는 실제 frontend/process/socket/journal 검사와 기존 회귀를 확대했다.
임시 소스에서 결속 없는 결과 허용, actor budget 무시, ordinary CID의 거부를
모델 후로 지연, idle worker의 snapshot 참조 누락을 각각 주입하자 관련 검사가
모두 assertion 실패했다(native-provider-mutants.json 및 각 mutant log).
출력에 callback PID나 native ID를 정의만 한 검사가 아니라 실행 순서와
결과/중복/회수의 실제 경로를 검사했다. Native SDK를 stub한 검사는 model0이며
실제 모델 인증과 구분한다.

초기 확대 검사에서는 새 provider 지원 목록을 반영하지 않은 기존 assertion과
CLI parser 함수명 오기가 각각 실패했다. 모델 없는 Hermes lifecycle fixture는
native 환경 factory가 없는 모의 문맥에 대해 explicit 격리 env를 제공하도록
맞췄고, 별도 검사로 native profile secret-scoping 호출을 확인했다. Loader의
동시 초기화 경합도 제어된 검사에서 실패한 뒤 직렬화했다. 알려진 native
admission 거부가 internal error로 빠지던 경로는 ToolError로 보존하고,
예상치 못한 IO 예외는 그대로 내부 오류 경계로 남겼다. 각 실패/수정 로그는
native-provider-* 접두어로 보존했다.

전체 core 첫 실행은 OpenClaw의 정적 catalog가 공통 runtime enum과 달라
490개 중1개가 실패했다. 공통 operation generator가 OpenClaw catalog도 갱신하게
수정했다. 당시 전체692개와 독립 mock39/변이14개는96.253초에 통과했다.
이후 추가한 interpreter 고정·참조 손상 검사 등의 최종 수치는 후속 기록을 따른다.

## 최종 관련 회귀와 설치 참조

마지막 core는 Python490+SDK50+native provider26+Node127=693개와 독립 mock39 /
변이14개를96.319초에 통과했다(native-provider-core-release-check.log).
Native provider26개는 다른 검사와 분리된 HOME/XSM_HOME에서 병렬 실행한다.
기존 항목을 제거하거나120초 기한을 늘리지 않았다. Python/console이 다른
버전이 되는 경우도 모델 전에 거부하며, 실제로 사용한 native venv interpreter의
0.22.5 확인도 모델 호출0으로 통과했다(native-provider-actual-interpreter.json).

논리 service가 남아 있으면 PID가 없는 idle 상태에도 frontend의 runtime root를
참조로 보존한다. 참조 metadata나 worker pointer가 손상·symlink·판독 불가인
경우 snapshot 정리는 보수적으로 모든 후보를 유지한다. 해당 검사는 임시
cache만 사용했다. Runtime root 참조가 명시적 service 제거 뒤 풀리는 것도
확인했다. 원시 로그는 native-provider-retention-final.log와 core 출력에 있다.

첫 uncontrolled native 표본에서 놓친 회신도 원래 owner/request로 별도 읽기·ACK를
복구했다.4개 검사가 통과했고 DB의 API calls는1로 유지됐다
(hermes-owned-native-first-reply-recovery.json). 기존 failed 파일의 판정은 바꾸지
않았다. 이 기록은 read/recovery이며 그 작업을 다시 실행한 결과가 아니다.

현재 macOS에서 owned 정상 실행·문맥 재사용·저장 결과/전송 회수·중복 방지·
상속 depth를 실제 native 모델로 확인했다. Linux native model/worker, 실시간
중단/unknown native turn의 gateway readback, classic spawn/pane, native 사용자
승인 UI 및 나머지 runtime/provider/전체 matrix는 계속 미완이다.

## 네이티브 하위 대화의 한도 상속

공개 `native-lineage` 능력과 `session.open.parent_conversation`을 추가했다.
부모 식별자는 같은 runtime/profile 안에서 투영하며 재접속에서 생략해도
유지한다. 다른 부모로 교체하는 요청은 거부한다. 한도 조회는 native 조상을
따라 owned worker를 찾고, 누락된 조상이나 순환은 무제한 루트로 처리하지
않는다. 이 경로는 범위·팀·사용자 승인을 상속하지 않는다.

OpenCode 연결부는 실제 session.get의 parentID를 확인한다. Owned 루트에
도달한 자식은 루트 문맥을 다시 결속하지 않고 참여한다. Hermes 연결부는
0.22.5의 공개 subagent_start(parent_session_id, child_session_id) 훅을 받아
자식의 최초 등록에 부모를 넘긴다. 현재 증거는 모의 호스트와 실제 공통
서비스 경로이며, 실제 native 하위 에이전트 전체 실행의 인증은 미완이다.

macOS Python3.14.6 핵심 검사에서 Python491+SDK50+native31+Node139=711개가
85.371초에 통과했다(native-lineage-core-second.log). 기존 검사를 유지하면서
독립 Node 그룹을 Python 그룹과 함께 실행하도록 순서만 조정했다.
120초 기한은 유지했다. 이전 a2cf4ef의 Linux3.14 검사는 실제로120초를
초과했으며(node-control-linux/314/protocol.log), 이 변경의 Linux 재검증은
아직 미완이다. Linux3.11 이전 표본의 성공을 이번 변경의 증거로 쓰지 않는다.

새 훅 시험은 최초에 monitors를 초기화하지 않은 시험 구성 오류로 실패했다.
수정 후 관련17개가 통과했다(native-lineage-binding-second.log).
부모 추적을 끊는 변이는 시험 초기화 뒤 적용한 실행에서 검출됐다
(native-lineage-mutant-second.log). 최초 변이 시도는 시험의 모듈 재로딩으로
변이가 사라져 무효였으며 해당 로그도 보존했다. 공개 스키마 검사는16개
메서드 구조를 통과했으나 실제 wire capture는 제공하지 않았다
(native-lineage-schema.json의 observed=0). 실제 native 하위 대화 시험과 두
Linux 버전의120초 재검증은 계속 남아 있다.

후속 SDK 시험에서는 Python21개와 Node26개가 통과했다
(native-lineage-sdk-python.log, native-lineage-sdk-node.log). 양쪽 모두 능력이
없는 서버에 부모 등록을 보내기 전에 거부하며 기존 연결은 계속 사용할 수
있었다. 능력이 있는 서버에는 정확한 부모와 native-lineage 능력을 전송했고,
호출자가 넘긴 capabilities 목록을 변경하지 않았다. 이 수치는 각 클라이언트
시험 파일만의 결과이며 앞의711개 전체 검사와 별도다.

이후77de8dc 고정 번들로 Linux 재검증도 끝났다. 같은711개와 독립 mock39/
변이14개가 Python3.11.2에서64.574초, Python3.14.10에서83.092초에 통과했다.
앞서 적은 Linux 재검증 미완 상태는 이 표본에서 해소됐으며 실제 native
모델/하위 에이전트 전체 검증은 여전히 남는다. VM은 stopExit0으로 종료됐다.
번들 해시와 범위는 linux-validation.md의77de8dc 기록을 따른다.

Hermes0.22.5의 실제 PluginManager/PluginContext에도 연결부를 등록하고,
native 디스패처의 subagent_start 호출에서 실제 stdio session.open까지
실행했다. 부모 정보 유지·자식 등록·부모 runtime·서로 다른 투영 신원4개를
확인했다(hermes-native-lineage-dispatch/run.log). 격리 HOME/HERMES_HOME/
XSM_HOME과 설치된 venv interpreter를 사용했으며 모델 호출은0회다.
이 증거는 native 플러그인 디스패치와 등록 경로이며 실제 child 실행은 아니다.

## 실제 Hermes 자식의 한도 상속

macOS의 Hermes0.22.5에서 공개 owned 생성·실행부터 실제 native 자식까지
실행했다(hermes-owned-native-lineage/result.json). Generic reference parent가
xsm_owned create/run을 호출하고, 격리 프로필의 시험 플러그인이 공개 native
subagent_lifecycle로 자식 하나를 시작했다. 자식이 실제 xsm_owned create를
호출하자 공통 서비스가 부모의 max_depth로 거부했다. 여기서는 worker 기록을
시험에서 심지 않았으며 실제 공개 생성 경로의 기록을 사용했다.

부모의 실제 결과, 정본 회신 읽기·ACK, DB의 자식1개, 자식 tool 원문의 한도
거부, 미생성된 서비스, 호스트의 부모 결속과 같은 owned ID의 한도 상속까지
9개를 확인했다. 부모와 자식 각각 model calls3/tool calls2였으며 configured
model은 live catalog의 anthropic/claude-sonnet-5-5, served model은 미확인이다.
기존 loopback proxy의 anthropic authMode=oauth와 API key 미설정을 확인했고
메신저는 사용하지 않았다. 해당 owned gateway는 PID 소유권을 확인해 종료했다.
원문은 child-tool-results.json, lineage-records.json, native-usage.json에 보존했다.

선행 seeded-budget 시험은 별도 표본이다. 첫 실행에서는 macOS의 /var와
/private/var 표기가 달라 시험이 서로 다른 opaque profile로 한도를 심었고
실패했다(hermes-native-lineage/result.json). 부모 프로필 표기를 맞추고 native
SessionDB를 열어 도구 원문을 보존한 v2는14개를 통과했다. 이 표본을 공개
owned 생성의 증거로 쓰지 않으며 실패 로그도 유지했다. 공개 생성까지 포함한
뒤의9개 표본이 해당 빈칸을 확인한다. Linux의 실제 native child/model 및 다른
runtime의 owned 자식 실행은 여전히 미완이다.

재현 명령은 `scripts/probe-hermes-owned-lineage.py --native-source <고정 소스>
--native-cli <설치된 hermes 절대 경로> --model <live catalog ID> --output <새 경로>`다.
실제 스크립트로도9개 항목을 다시 통과했다(hermes-owned-lineage-script/result.json).
0.22.5 tag와 clean tracked source, 현재 loopback proxy catalog를 확인하고
격리 홈에서 실행한다. 고정 모델명을 기본값으로 넣지 않으며 기존 결과 경로를
덮어쓰지 않는다. 이 명령은 실제 구독 모델을 호출하므로120초 model0 core
검사에는 포함하지 않는다. 반복 실행도 시험 gateway 종료를 확인했다.

## OpenCode owned 제공자: native CLI와 공통 저널

OpenCode1.19.5 제공자를 고정 catalog에 추가했다. 공통 엔진에 runtime 분기를
추가하지 않고 managed profile·operator executable·버전·설치된 binding hash를
확인한다. stdin으로 요청하고 명시적인 native session ID로 재개한다.
--auto/--continue/--fork/권한 덮어쓰기는 넣지 않는다. 기존 native plugin의
awaited chat.message가 private descriptor로 모델 전에 문맥을 결속한다.

결과는 실제 step_start/text/step_finish 이벤트를 읽는다. 같은 대화와 마지막
stop, 실제 답변이 있어야 수락하며 길이 제한·도구 호출만 끝난 결과·오류·다른
대화·중복 JSON 키·잘린 결과는 거부한다. 업무 outcome 판정은 기존 공통
함수로 유지한다. 공개 operation schema와 OpenClaw 생성 catalog도 갱신했다.

실제 native CLI 수락/거부4개 검사가 통과했다
(opencode-worker-control-cli-v3/result.json). 수락의 provider fixture 요청2회는
대화와 보조 제목 요청을 포함하며 실제 모델 호출이 아니다. 거부는 provider0회다.
첫 실행은 text 모드 누락으로 시험이 실패했고, 두 번째는 보조 요청을 세지 않은
기대값으로 실패했다. 원시 실패를 보존했다. 새 CLI/provider 단위7개와 관련
owned 시험을 합한22개가 통과했다(opencode-owned-targeted.log).

공개 xsm_owned 생성/실행을 실제 CLI에 연결한 model0 표본은10개가 통과했다
(opencode-owned-native-fixture-v2/result.json). 정본 회신2개의 실제 읽기/ACK,
같은 native 대화 재개, 같은 요청의 reply/execution 재사용과 추가 provider
호출 없음, 각 turn의 사전 결속을 확인했다. 초기 표본의 검사 이름에 남은
Hermes 표기를 고쳐 별도 v2로 실행했으며 초기 기록을 덮어쓰지 않았다.

실제 구독 모델 표본은 실패했다(opencode-owned-native-subscription/result.json).
기존 OAuth loopback proxy를 통한 공급자가 extra usage 소진 오류를 반환했고
native CLI가 exit1로 끝났다. 요청은 unknown으로 보존하며 자동으로 재실행하거나
추가 과금하지 않았다. stdout/stderr는 같은 디렉터리의 native-run에 복사했다.
따라서 OpenCode 실제 모델의 문맥 재사용은 아직 미검증이다. native CLI 종료 시
TransportError: client closed 진단도 관측됐으며 원인 해결은 미완이다.

macOS Python3.14.6 core는491+SDK52+native38+Node141=722개와 독립 mock39/
변이14개를86.696초에 통과했다(opencode-owned-core-second.log). 첫 전체
실행은 OpenCode를 미지원으로 기대한 기존 assertion2개가 실패했으며, 이제
제공자 승인 메타데이터 없는 retained worker가 Codex 결과를 채택하지 못하는
검사로 유지했다. 불완전 finish를 수락하는 변이는 assertion2개로 검출했다
(opencode-worker-cli-mutant.log). 공개 스키마도 통과했다(opencode-owned-schema.json).
이번 제공자의 Linux 재검증, 실제 모델·자식·승인 UI·전체 설치 행렬은 미완이다.

후속으로 종료 시 상태 갱신 경합을 수정했다. native event가 기다리던
session.update를 dispose가 종료하면 예상된 TransportError가 native handler로
다시 전파됐다. 종료 중인 transport 거부만 정리하고 live 오류는 계속 전파한다.
결정적으로 abort를 주입한 시험은 수정 전 unwanted rejection으로 실패했다
(opencode-shutdown-red.log). 수정 후 연결 시험22개가 통과했고
(opencode-shutdown-green.log), 실제 CLI v4 수락/거부4개도 통과했다.
정상 CLI stderr의 client-closed 진단은0건이며 두 native process 모두 종료됐다.
이 수정의 전체 core와 Linux 근거는 해당 후속 실행 기록을 따른다.

종료 경합 수정을 포함한 macOS 전체 core는 Python491+SDK52+native38+Node142=
723개와 독립 mock39/변이14개를86.119초에 통과했다
(opencode-owned-core-third.log). d553fc2의 Linux722개는3.11/3.14에서 각각
64.558/85.031초로 통과했으며 VM도 종료됐다(linux-validation.md). Linux 표본에
종료 경합 수정은 포함되지 않았다. 실제 구독 모델 실패나 native UI/자식/전체
설치 미완 상태는 이 core 결과로 해소된 것으로 간주하지 않는다.

## Pi의 native 입력 결속 경계

Pi1.4.0 binding에도 private worker descriptor를 연결했다. 일반 참여자는
descriptor가 없으면 기존 동작을 유지한다. Owned 입력은 native input 훅에서
실제 session ID를 먼저 결속하며, 실패하면 공개 handled 계약으로 입력을
차단한다. before_agent_start에서도 같은 결속을 확인하고 실패 시 ctx.abort를
요청한다. Native new/resume/fork 전환에는 descriptor를 유지하고 최종 종료에
닫는다. Pi owned 제공자는 아직 catalog에 등록하지 않았다.

Pi의 hook 예외는 native runner가 기록하고 계속 실행한다. ctx.abort만 넣은
초기 표본에서는 custom stream 함수가 이미 중단된 signal을 받고도 진입했다.
따라서 이 경로를 입력 차단의 증거로 채택하지 않았다. input handled를 추가한
native v5에서는 수락 시 stream 진입1회, 거부 시0회였다. 수락은 입력/시작의
두 경계에서 같은 실제 ID로 결속2회, 거부는1회였다. 앞선 v4는 수락 결속을
1회만 기대한 시험 드라이버 때문에 실패했으며 로그를 보존했다.

재현 명령은 `python3 -B scripts/probe-pi-owned-gate.py --native-package <Pi1.4.0
package root> --output <새 경로>`다. 실제 native SDK/extension loader와 private
socket을 사용하고, streamFunction은 명시적인 호출 계수 fixture로 바꾼다.
이 명령도 수락/거부 양쪽 통과했다(pi-worker-control-script/result.json).
모델 추론·업무 결과·owned journal 인증은 아니며 provider API는 호출하지 않는다.
별도 임시 소스에서 handled를 제거하자 거부 뒤 stream 진입1회로 실제 SDK
검사가 실패했다(pi-worker-control-mutant/refuse.json). 중단 signal=true도
함께 보존했다. 단순히 오류를 출력했는지 보는 검사가 아니다.

초기 계측에서는 streamFn이라는 읽히지 않는 필드를 사용했다. 추적 파일
전수 조사에서 scripts/probe-pi-sdk.mjs1개와 이번 초기 원시 시험 파일1개를
확인했다. 설치된 native agent가 사용하는 streamFunction으로 수정했다.
과거 modelCalls=0 필드만으로는 해당 계측의 무호출을 증명할 수 없으며 이번
수정 결과를 과거 표본에 소급하지 않는다. 기존 SDK 도구 실행 시험도 잘못된
21개 기대값을 현재22개에 맞춰 다시 실행해 통과했다
(pi-sdk-counter-corrected.json). Native 버전은1.4.0을 유지했다.

Pi 단위15개가 통과했고, macOS 전체는 Python491+SDK52+native38+Node145=
726개 및 독립 mock39/변이14개를85.034초에 통과했다
(pi-worker-control-core-first.log). 이 변경의 Linux와 native CLI/owned 제공자,
실제 모델·워커 재개/중단/하위 대화 검증은 여전히 미완이다.

## Pi owned CLI 제공자와 문맥 분리

Pi1.4.0 제공자를 고정 catalog에 추가했다. Managed 설치와 frontend hash,
operator PATH 또는 절대 XSM_PI의 실제 버전을 확인한다. 기존0.58.1을
대체 표본으로 사용하지 않는다. 공통 엔진에 runtime 이름별 분기를 넣지 않고
기존 journal·사전 결속·결과 공개 경로를 사용한다.

CLI는 --print --mode json과 정확한 --session-id UUID를 사용한다. 작업의
session_seed 또는 이미 결속된 native ID만 전달하며 부분 ID·최근 세션 선택·
--continue·--resume·--approve·도구/권한 덮어쓰기는 넣지 않는다. Native 저장은
프로필의 owned-sessions/<worker ID>로 구분한다. stdin은 기존 엔진이 전달한다.

실제 Pi CLI의 수락은 local provider fixture 요청1회, 거부는0회였다
(pi-worker-cli-native/result.json). 거부 시 native CLI도 exit0이므로 종료 코드만
성공 근거로 삼지 않는다. 같은 session header와 실제 assistant stop 답변,
agent_end(willRetry=false), 마지막 agent_settled(aborted=false)가 필요하다.
절단·오류·도구 호출·취소·재시도·다른 cwd/ID와 비어 있는 답변은 거부한다.

공개 xsm_owned부터 실제 CLI까지의 첫10개 표본이 통과했고, 다른 work context
분리를 추가한 v2는14개가 통과했다(pi-owned-native-fixture-v2/result.json).
동일 문맥은 같은 ID로 재개되고 다른 문맥은 다른 ID를 사용했다. 두 ID는
같은 논리 worker에 결속됐다. 정본 회신3개를 실제로 읽고 ACK했으며 같은
request 재사용에는 provider 요청이 추가되지 않았다. Native 프로세스는
각 turn마다 종료됐고 scripted provider 요청은 총3회다. 실제 LLM 추론이나
기억력을 증명하는 표본이 아니며 API 키 과금 경로는 사용하지 않았다.

재현 명령은 `python3 -B scripts/probe-pi-owned-native.py --native-cli <설치된
Pi1.4.0 절대 경로> --output <새 경로>`다. 이 실제 스크립트로도14개를 통과했다
(pi-owned-native-script/result.json). Local scripted assistant와 격리 홈만 쓰고
기존 native 설정·권한을 변경하지 않는다. Unit7개와 기존 owned 검사를 합한
22개도 통과했다. Aborted 상태를 수락하는 변이는 assertion2개로 검출했다
(pi-owned-settled-mutant.log). 공개 스키마 검사도 통과했다(pi-owned-schema.json).

macOS Python3.14.6 core는491+SDK52+native45+Node145=733개와 독립 mock39/
변이14개를81.156초에 통과했다(pi-owned-core-first.log). 앞선448927c의
Linux726개는 별도 표본이며 이 제공자의 Linux 검증으로 소급하지 않는다.

실행 중 취소 검사는 미실행이다. 조사 결과 공통 owned API에는 cancel/stop
action이 없고 workers.stop은 busy/unknown owned 서비스 제거를 거부한다.
따라서 Pi 전용 kill로 이를 우회하지 않았으며 공통 owned 실행 취소 구현과
각 runtime의 실제 중단 검증은 미완이다. 이 미결사항은 범위 제외가 아니다.
Pi 실제 구독 모델·Linux native CLI·하위 대화·승인 UI와 전체 설치 행렬도 남는다.
