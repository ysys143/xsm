# Native UI 작업 경계를 위한 Python 호스트 보류

상태: Python 공통 SDK 수명 경로를 구현했다. Hermes UI 연결과 전체 계획은 미완이다.

## 구현과 검증

`XsmHost.call(..., wait_for_decision=False)`는 서버의 waiting-for-user를 반환하고
실제 present callback은 계속 유지한다. 답 저장만으로 원 작업을 자동 재실행하지
않는다. 외부 UI hold와 일반 대기자를 분리했으며 abandon_deferred는 hold를
명시적으로 해제한다. Callback/transport 정책은 공통 SDK와 서버에 남겼다.
Wire method·승인 source·runtime 이름별 엔진 분기는 추가하지 않았다.

실제 stdio 서버를 사용하는 기존21개+새4개 호스트 검사를 실행했다.
초회 새3개는 없는 SDK 인자로 실패했다(deferred-host-before.log).
구현 뒤24개가 통과했고, 추가한 해제 호출 취소 검사에서는 정리가 함께 취소돼
실패했다(deferred-abandon-cancel-before.log). 정리를 독립 task로 유지하고 close가
회수하도록 수정한 최종25개는 통과했다(deferred-host-final.log).

새 검사는 UI 대기 전 반환, 답 저장과 원 작업 적용의 분리, 다른 대기자의 취소,
명시적 해제/중복 해제/다른 질문 ID 거부, 보류 RPC 취소와 해제 호출자의 취소를
다룬다. 외부 hold guard를 제거한 변이는 일반 대기자 취소 검사에서 실패했다
(deferred-host-hold-mutant.log). 실제 protocol subprocess와 명시적 UI fixture이며
실제 사용자나 native UI 인증으로 계산하지 않는다.

Mac/Python3.14.6의 core846개(Python505+SDK56+native133+Node152)가88.346초에
통과했다(deferred-host-core.log). 독립 mock39/변이14는 별도 수치다.

e52b39b248c3a6f1e6723b5c23561811ea6c3047를 고정한 Linux core도846개씩
Python3.11.2에서74.499초, Python3.14.10에서92.673초에 통과했다.
Archive SHA256은d581338c51f8fe855c6683b028938df6dc9e0c4d2dbb1dc558ffb3b6ff60f4f6다.
Network none/model0/cpu2/memory3g, 미실행 core0, VM stopExit=0이다.
원시는 deferred-host-linux/result.json과 환경별 protocol.log에 있다.
이 core는 native UI·모델·메신저나 전체 runtime 행렬 인증이 아니다.

## Hermes native 관측의 추가 증거

고정 v0.22.5/bf0203a794a07aac3ff764972ab9087baa4e4f4e의 실제 clarify executor와
PluginContext.register_hook('post_tool_call')를 실행했다. Native callback의
fixture 답, hook1회, session_id/tool_call_id 일치, 원래 args와 실제 result
전달의4개 확인이 통과했다(hermes-clarify-post-hook/result.json).

Caller와 UI callback은 명시적 fixture다. Native middleware는 이 함수 경계
시험에서 우회했으며 실제 AIAgent·모델·사용자 UI나 XSM 질문 결속을 인증한 것이
아니다. Native source 파일별 hash도 원시에 보존했다. 이 시험의 내부 executor
import를 제품 plugin API로 사용하지 않는다. 실제 binding은 공개 hook을 받는다.

공개 hook은 tool_name/args/result와 실제 세션/도구 호출 발생의 관측 경로를
제공한다. 일반 registry가 live parent_agent/clarify_callback을 제공한다고
가정하지 않고 후속 native UI 결과를 연결할 후보가 생겼다. 그러나 질문/표시 ID와
실행 세대, 정확한 질문·선택지 표시, 취소/늦은 답/동일 문구의 다른 질문, 선택지
전체 표현을 아직 연결/검증하지 않았다. 모델이 전달한 답을 승격하지 않는다.

2026-11-03 구현 담당자가 기록했다. 같은 담당자가 위 binding과 native 사용자
입력 경로를 실행한 뒤 P4 UI를 재판정한다. 범위 제외나 대체 완료에 대한 사용자
승인은 없으며 기존 UI 미완 조건을 유지한다. 원시는 모두
deliverables/protocol-foundation/ 아래에 있다.
