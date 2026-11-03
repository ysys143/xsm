# Hermes 실제 자연 turn context 전달

상태: P4의 부분 진척이다. 전체 계획은 미완이다.

NativeContext는 session/host/turn별로 다음 자연 turn의 원문을 stage한다. Native
pre_llm_call이 nonce-tagged peer context를 반환하고 pre_api_request가 정확한
session/turn/API request와 전체 user-context 본문을 관측한 뒤 SDK admission을
완료한다. Assistant/tool text, 다른 SID/host/turn, 빈 API ID, 잘린 본문은 거부한다.
SDK natural-boundary-only 모드를 사용하며 idle 이벤트나 자동 ACK를 만들지 않는다.
Native question bridge는 별도로 유지한다. Opt-in native_context bool이 아니면 거부한다.

실제 protocol 저장소를 쓰는 새4개 검사는 관측 전 대기, 정확 관측 후 admission과
별도 ACK, 관측 없이 종료 시 원문 release, inbox RPC 응답 중 close의 정확한 claim
release, 빈 경계/turn ID 거부를 확인한다. 기존 Hermes binding과28개가16.221초에
통과했다(focused-final.log). Turn/content 검사를 생략한 변이2개도 각각 실패했다.
Manifest의 새 hook2개를 실제 등록해 총9개임을 검증한다.

Mac core958개(Python555+외부 적합성54+SDK61+native133+Node155)와 schema/기존 mock/
v7 local은58.475초에 통과했다(core.log). Python 공통 renderer도 notice-only에서
ACK를 만들지 않고 원문/token/ID 복구 지시를 보존하는 검사를 포함한다.

## 실제 고정 Hermes AIAgent

Prepared source tar를 새 임시 경로에 풀어 v0.22.5 exact tag와 tracked clean을
확인했다. Source archive SHA256은
680bc82a16d19740705868422283a79d3b029ba9246eca639725f053804b6c28이다.
새 dependency root는 source pyproject의 base requirement와 공식 uv override를
그대로 사용한다. 모델·사용자 설정·API 키 과금 경로는 사용하지 않았다.

scripts/probe-hermes-natural-context.py는 설치된 plugin/actual AIAgent/actual native
hook/tool registry와 local scripted HTTP provider를 실행했다. Warmup 뒤 실제 native
session에 FYI를 저장하고 idle 동안 provider request가 없음을 확인했다. 다음 자연
turn의 실제 provider 입력에서 full original/context marker를 읽은 뒤 native
Tool Hub가 xsm_ack를 호출했다. 다시 inbox에서 delivery가 억제되고 pending
admission이 없으며 unload가 끝난 것까지13개 checkpoint/6개 HTTP request로
통과했다(native-fifth/result.json). Model calls0이며 실제 LLM·사람 UI 증거는 아니다.

## 실패·영향 범위

기존 시험 dependency root는 ruamel/requests가 없어 native-first/second가 import
단계에서 실패했다. 단순 base requirements 설치는 Pillow/browser-harness 제약 충돌로
실패했으며 upstream uv override를 적용하자 새 격리 설치가 성공했다. Native source나
version을 바꾸지 않았다. Native-third는 macOS /var와 /private/var workspace 문자열
차이를 정확히 거부했다. Root를 canonicalize해 시험 인자를 고쳤다.

Native-fourth는 제 scripted fixture가 실제 Tool Hub의 queries 대신 tool_names를
보내 실패를 반복했다. 해당 프로브 PID 하나를 검증해 SIGINT로 중단했고 원시
요청3370개/약1.603GB와 실패를 그대로 보존했다. 실제 inference·과금은0이었다.
실제 tool schemas에 맞춰 queries/tool_call로 수정하고 max_iterations6, provider
request16개 guard, outer120초 제한을 추가했다. 성공 run에는 그 반복이 없다.

원시는 `deliverables/protocol-foundation/hermes-natural-context/`다. Dependency
설치/실패/해결·native source metadata와 package versions도 남겼다. 고정 source
e9f9e8c의 Linux 실제 hook도13개 checkpoint/6개 HTTP request로 통과했다.
전체958개와 schema/v7 검사는 Python3.11에서85.194초,3.14에서108.427초로
통과했다. 실행 보고서의 status=passed/startExit=0/stopExit=0을 확인했다.
근거는 `hermes-natural-context-linux/result.json`이다. Idle push/wake, busy/now, 실제 모델/UI,
다중 profile·메신저·원격/설치 전체 행렬과 원래 계획은 미완이다.
