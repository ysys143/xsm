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
