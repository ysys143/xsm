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
