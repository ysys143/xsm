# Pi·OpenCode 구독 모델 시험과 관측 복구

상태: 실제 모델 정상 경로는 미완이다. Model0 시험의 성공으로 대체하지 않는다.

## 실제 구독 경로의 실패

scripts/probe-owned-subscription.py는 Pi1.4.0/OpenCode1.19.5의 기존 native
provider와 공개 operation.call을 사용한다. 새 HOME/XSM_HOME/native profile에서
정상 실행, 이전 turn의 token 기억, 독립 context, request replay와 선택적 native
xsm_send를 검사한다. Native runtime별 코드는 프로필 구성에만 있고 policy와
journal은 기존 공통 서비스를 사용한다. 모델은 live catalog의 direct
anthropic/claude-sonnet-5-5이며 기존 OAuth proxy를 사용했다.

2026-11-03 실제 시도는 다음과 같이 실패했다.

| 표본 | provider 시도 | 응답 관측 | 완료 검사 | 실패 |
|---|---:|---:|---:|---|
| pi-owned-subscription-first | 1 | HTTP400 1개 | 1/26 | 첫 결과 저장 검사 |
| opencode-owned-subscription-first | 2 | HTTP400 1개, 나머지 미관측 | 1/26 | 첫 결과 저장 검사 |

두 native 오류에는 공급자의 out of extra usage 응답이 있었다. Native provider
admission만 통과했고 첫 결과 검사가 실패했다. 이후24개 검사는 전제 미충족으로
실행하지 못했다. 원 요청은 unknown/result=None이며 답변이나 성공 결과를 만들지
않았다. 각 ownedChildrenExited=true를 확인했고 추가 inference 시도를 중단했다.
OpenCode의 미관측1건을 HTTP400이나 완료로 추정하지 않는다.

기존 성공 표본5개와 실패 표본2개의 relay 기록을 전수 대조했다
(subscription-response-observation-audit.json). 성공 표본은 시도/응답 수가 모두
일치했다. 불일치는 위 OpenCode 표본1개뿐이다. 원시 실패와 journal은 각 표본
폴더와 같은 이름의 log에 보존했다. 사용자 profile/권한/인증은 변경하지 않았다.

## 시험 도구 자체의 native model0 검증

실제 모델의 실패와 별개로 native CLI·plugin·공통 journal 경로를 검증하기 위해
provider만 명시적 scripted assistant로 바꾼 개발용 실행을 했다. 공개 CLI의
자동 fallback은 아니며 실행 결과도 explicit-fixture/modelCalls=0으로 구분했다.
변형한 실행 source와 fixture의 hash는 fixture-source-audit.json에 보존한다.

- pi-subscription-harness-model0-final:26/26개, fixture 요청5회.
- opencode-subscription-harness-model0-final:26/26개, fixture 요청8회.
- 두 표본 모두 정상/recall/독립 context, 같은 request의 비재실행, 실제 native
  xsm_send의 canonical note1개 읽기/ACK와 별도의 owned 회신 ACK를 확인했다.
  ownedChildrenExited=true이며 실제 inference는0회다.

초기 Pi model0도26개를 통과했다. 초기 OpenCode model0는22개 후 canonical
note 부재 검사에서 실패했다. Fixture가 도구 목록 없는 보조 요청에 tool call을
반환한 것이 원인이었다. Native API가 도구를 제공한 요청에서만 tool call을
반환하도록 수정한 v2도26개를 통과했다. 이 fixture에서 도구 목록 없는 보조
요청3회를 관찰했지만, 실제 실패 표본의 미관측 요청 종류를 소급 판정하지 않는다.
실패와 v2를 모두 보존했다. Model0를 실제 모델 완료의 증거로 세지 않는다.

## Relay 관측 수명 보완

Relay는 요청을 시작할 때 먼저 phase=started를 기록하고 실제 응답을 읽으면
phase=response를 기록한다. 응답 대기 중 관측자가 닫히면 같은 request에
phase=observer-closed/upstreamState=unknown을 남긴다. 이것은 upstream 취소나
업무 종료 영수증이 아니다. Transport 오류도 실제 응답이 없으면 unknown이다.
OpenClaw probe의 요청 수는 로그 줄 수 대신 독립 시도 counter를 사용하도록 했다.

응답은 이미 관측했지만 client write가 남은 경우 unknown을 덧붙이는 race도
검사했다. 수정 전 ['started','response','observer-closed']가 기록돼 실패했고,
응답 관측 시 active 집합에서 제거한 뒤5개 relay 검사가 통과했다.
시작 기록을 제거한 변이도 새 검사에서 실패했다. 원시는
subscription-observed-response-before.log, subscription-relay-lifecycle-final.log,
subscription-relay-missing-start-mutant.log다. Model-free core842개
(Python505+SDK52+native133+Node152)는 macOS에서88.215초에 통과했다
(subscription-observer-core-final.log). 독립 mock39/변이14는 별도 수치다.

1a384ec8dadd84222ca072c49845e41cd17279c2를 고정한 Linux에서도842개씩
Python3.11.2에서74.117초, Python3.14.10에서93.889초에 통과했다.
Archive SHA256은de29b4fca20be154d9d83a9d872debcb3714acff26518266fbec37d9cb6f0dfd다.
Network none/model0/cpu2/memory3g, 미실행 core0, VM stopExit=0이다.
원시는 subscription-observer-linux/ 아래다. 이 core는 실제 모델이나 새
native CLI 행렬의 성공 증거가 아니다.

모든 원시는 deliverables/protocol-foundation/ 아래에 있다. 실제 모델 정상 경로,
사람 UI·메신저·전체 행렬·p95 조건은 계속 미완이다. 2026-11-03 구현 담당자가
기록했으며 같은 담당자가 해당 구독 경로의 가용성을 확인한 뒤 새 profile/새
request로 실제 모델 표본을 다시 실행한다. 기존 unknown 작업을 자동 재실행하지
않는다. 모델·버전 변경이나 범위 제외에 대한 사용자 승인은 없다.
