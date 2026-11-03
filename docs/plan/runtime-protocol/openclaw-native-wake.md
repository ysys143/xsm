# OpenClaw 제품 native wake 연결

상태: opt-in 구현과 Linux 실제 설치 plugin/model0 기본·reset 경로 검증이다.
전체 P4·원래 계획은 미완이다.

`native-wake.mjs`는 context queue commit 뒤 등록 plugin의 background scope에서
native work-admission lease를 사용한다. SID/revision/설정/epoch를 다시 확인하며
native signal과 host/plugin 종료 signal을 실행까지 전달한다. SDK revision 인수만
신뢰하지 않는다. Actual native config가 기본 모델·별칭을 해석하고, 세션 override는
그대로 전달한다. Subscription-auth dispatch를 선택할 수 있는 native 경로를 유지한다.
이 표본은 localhost 합성 provider이고 실제 과금 모델을 부르지 않았다.

Wake run은 inter_session/tainted input과 일반 wake notice를 사용하며 원문은
untrusted context queue에 있다. 같은 batch의 진행 중·최근 실행을 중복 시작하지
않고, 완료 cache는256개로 제한하며 active 실행은 제거하지 않는다. 실패는 원문을
ACK하지 않고 명시적 복구 대상으로 남긴다. Native 오류의 임의 상세는 로그에
내보내지 않는다. Cancel/close는 실제 제출 signal을 취소하고 수명 정리를 기다린다.

`natural-context.mjs`는 native agent_turn_prepare에서 SDK naturalBoundary를 실행해
FYI를 stage한다. AsyncLocalStorage가 지연된 inbox 응답을 원래 경계에 결속한다.
실제 llm_input의 host/run/전체 nonce prompt를 관측하기 전에는 admission을 만들지
않는다. Cancel은 SDK의 claim 반환 경로를 사용하며 canonical 원문을 지우지 않는다.
Default nativeWake=false에서는 기존 queue 경로를 유지한다.

## 실제 경로

`probe-openclaw-native-wake.py`는 host_install의 실제 설치본과 native gateway/
agent/hooks/Tool Hub를 사용한다. Native tool_search/tool_call의 실제 schema로
xsm_inbox를 찾고 실행했으며 실제 result.details의 inbox 계약을 확인했다.
그 뒤 별도 XSM 참여자의 저장만으로 백그라운드 native turn이 시작됐고 실제 user
prompt에서 원문을 읽어 exact native ACK했다. SDK admitted 보고와 ACK는 별개다.

FYI idle300ms 관측에 provider 호출이 없었다. 첫 실제 자연 턴의 user prompt에
원문/nonce context가 포함됐고 llm_input admission 보고와 명시적 ACK를 확인했다.
이 기본 경로는12개/25.759초를 통과했다. 실제 사람 UI·외부 메신저는 부르지 않았다.

Reset 표본은 실제 wake가 provider HTTP에 도달한 지점에서 응답을 막고 실제
sessions.reset을 호출했다. 이 native 경로는 SID를 유지하고 revision을 교체했다.
항상 SID가 바뀐다는 fixture 가정을 실패로 보존하고 수정했다. 기존 참여가 종료되고
원문은 미ACK로 남았다. 다음 명시적 자연 턴에서 같은 주소/새 protocol generation이
원문을 읽고 ACK했다.18개/27.631초, gatewayStopped=true/VM stopExit=0이다.
다른 SID로 바뀌는 reset 분기는 코드에 있지만 이 표본에서는 실행되지 않았다.

## 회귀·실패 기록

제어된 seam 검사는 background/native lease 순서, native default/override 전달,
중복 시작 방지, 설정/세대 변경, reset/host 취소와 오류 상세 비노출을 확인했다.
Context 검사는 host/run/전체 원문·취소·늦은 RPC 응답·빈 inbox를 확인한다.
Revision/content guard를 각각 제거한 변이는 의도한 assertion으로 실패했다.
기존 context queue/binding 및 설치/schema39개도 통과했다. 신규9개를 포함한
Mac core972개/schema/v7은60.292초였다. 새 native 코드는 Linux 실험에 overlay와
source SHA로 보존했으며 pristine3313a6e 실행으로 표시하지 않는다.

첫 native 실행은 도구가 inline이라고 가정해 fixture가 실패했다. Native Tool Hub의
실제 queries/id/args schema를 확인해 fixture만 수정했다. 두 번째는 ordinary
wake는 통과했지만 기존 agent_end 경계가 FYI를 너무 늦게 넣어 첫 자연 턴 소비를
실패했다. 위 두 단계 인계로 고친 뒤12개가 통과했다. Reset 첫 표본의 회전 가정
실패와 교정된18개 결과도 덮어쓰지 않는다. Parent gateway에만 먼저 SIGTERM을
보내 정상 plugin dispose를 거친 최종 경로에는 임의 process-group 종료로 인한
protocol EOF 진단이 없다. 실패 시에는 소유 group만 강제 정리한다.

후속 live policy guard는 conversation access가 철회되면 session metadata를 읽기
전부터 준비를 중단한다. Inbox await 뒤 hook 반환 직전과 llm_input admission 직전에도
같은 queue target fence/host/epoch/설정을 재확인한다. 이 조건은 제어된41개
binding/queue/wake/context 검사에 포함했으며 이 수정의 고정 Linux 실행과 전체
core 후속 결과는 별도로 기록한다.

원시는 `deliverables/protocol-foundation/openclaw-native-wake*`에 있다. Mac native,
실제 구독 모델/서비스/UI, capacity/fragment·재연결·실패 전체, configuration reload와
100표본 p95 및 전체 조합은 미완이며 기존 Linux 승인 실패도 해결로 표시하지 않는다.
