# 실제 Hermes gateway drain과 native hook 전달

상태: 실제 고정 runtime의 local 실행 경로 검증. 구독 모델·화면·messaging·전체
계획의 완료 증거는 아니다.

`scripts/probe-hermes-gateway-drain.py`는 실제 설치 plugin/PluginContext,
GatewayRunner/SessionAuthority/local FIFO drain/AIAgent/native hooks/Tool Hub를
사용한다. Native handler·drain·질문 문맥을 context facade로 바꾸지 않는다.
새 격리 HOME/HERMES_HOME/XSM_HOME/workspace와 localhost scripted provider를
사용하며 실제 모델 과금 호출은0이다. Native source는 clean v0.22.5 exact tag다.

## 실제 schema에서 드러난 설정 결함

207181d는 allow_gateway_injection을 `get_config()`로 읽었다. Native PluginContext의
그 함수는 settings 하위만 읽지만 실제 권한은 plugin entry 바로 아래에 있다.
기존 facade는 두 값을 동시에 true로 반환해 결함을 가렸다. 영향은 새 native_wake
opt-in의 실제 로딩, 해당 설정 검사·facade와 설정 문서다. 기존 기본 pull/context
모드의 회귀 통과와 native FIFO 자체의 저장 증거를 무효화하는 결함은 아니다.
사용자 설정·실제 계정·공개 릴리즈는 이 시험에서 변경하지 않았다.

새 actual-plugin red에서는 registry에 xsm_inbox가 등록되지 않아 실패했다.
Native permission API `_gateway_injection_allowed()`로 고치자 실제 schema의
entry 권한만으로 로드됐다. settings에 같은 이름을 임의로 추가하지 않는다.
새 단위 검사는 settings permission만으로는 허용하지 않고, native API의 명시적
true와 native_context/native_wake만으로는 허용함을 확인한다.

## 실행 경로와 결과

실제 local user admission으로 warmup을 실행해 native hook이 정확한 gateway
대화로 XSM host를 연 것을 확인했다. 그 뒤 다른 XSM 참여자의 원문 저장만으로
local FIFO가 깨어나 native turn을 실행했다. 실제 provider 입력의 user content에
원문이 있었고, native Tool Hub가 그 안의 정확한 토큰으로 xsm_ack를 실행했다.
FIFO 완료와 원문 미재전달, context pending 없음과 plugin unload도 확인했다.

이어서 strict FYI를 저장했다.300ms 관측 구간 동안 새 FIFO admission/provider
호출이 없었다. 이후 실제 user admission이 만든 다음 자연 turn의 nonce context에
FYI가 들어갔고, native tool ACK와 원문 미재전달을 확인했다. 이 유한 관측을
모든 시간·부하에서의 무깨우기 증명이나 p95 측정으로 확장하지 않는다.

Fourth 실행은21개 checkpoint/13개 scripted HTTP request를 통과했고 unload됐다.
Third는 awake 경로12개/9개 request를 통과한 이전 표본이다.
Native permission 회귀를 포함한 Mac 전체960개와 schema/v7 검사는58.678초에
통과했다. 실제 native drain probe는 core와 별도로 실행했다.

Second는 이전 FYI fixture의 marker 조건을 FIFO 원문 입력에도 요구해 실패를
반복했다. 실패 입력은 assertion 전에 저장되지 않아 원문과 marker 중 무엇이
빠졌는지 그 표본만으로 판정할 수 없다. 해당 프로브 PID77909만 확인해 SIGINT했고
실패·unload 기록을 보존했다. 새 fixture는 입력을 검사 전에 저장하고 요청16개·
outer100초 상한과 첫 thread assertion 실패 시 중단을 적용한다. Awake에는 user
원문, FYI 자연 turn에는 추가 marker를 확인한다. 성공 fourth에는 assertion 재시도가 없다.

원시는 `deliverables/protocol-foundation/hermes-gateway-drain/`다. Linux 고정 source,
busy/now/혼합·취소/재시작, p95 100표본과 실제 모델/UI/messaging 행렬은 미완이다.

8f003bd 고정 Linux 후속 검증도 native21개/13개 HTTP request와 core960개/
schema/v7을 통과했다(3.11 84.154초,3.14 107.991초). 최종 status=passed/stopExit=0이다.
