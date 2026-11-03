# Hermes native 질문 bridge

상태: 실험적 opt-in 구현. Native AIAgent의 model0와 합성 UI callback은 통과했다.
실제 모델·사람 UI·Telegram/Discord 질문·전체 계획은 미완이다.

## 구현

Native PluginContext.get_config('native_questions', False)가 True일 때만 bridge를
만든다. 기본 pull 동작과 UI 미지원 거부는 유지하며 설치기나 사용자 설정을
변경하지 않는다. post_tool_call hook은 native clarify만 관측한다.

Python SDK의 보류 호출로 모델 도구를 UI 대기 중 막지 않는다. Native 표시 ID와
nonce heading, canonical 본문/선택지 legend를 반환하고 실제 clarify 결과를 받는다.
Protocol displayed는 canonical 본문이며 bridge는 native 렌더 전체를 비교한다.
선택값은 index label로 매핑하고 값2개와 이전/다음 navigation으로 Native4개
선택지 한도를 지킨다. Canonical 값은 자르지 않는다. Native callback의 값을
서버에 저장한 뒤에도 원 작업의 동일 인자 재호출 전에는 적용하지 않는다.

Profile은 native 공개 home resolver와 등록 시 고정한 profile이 같아야 한다.
SID/host 실행 세대/표시 nonce와 native turn/API request/tool call/index를 결속한다.
동일 occurrence 재사용은 막되 다른 native turn의 동일 provider call ID는 구별한다.
한 batch에서 같은 질문을 반복해 다른 답을 주면 하나를 고르지 않고 표시 nonce를
갱신한다. Timeout/미제공/빈 응답은 답으로 만들지 않고 표시를 포기한다.

## 검사와 실패 보존

- 실제 stdio 서버를 사용한 Hermes binding 검사24개가 통과했다. 다른 활성 SID,
  profile, reset 뒤 늦은 답, 변경된 본문/선택지, receipt 재사용, 취소·UI 미제공,
  자유 입력·긴 canonical 값의 전체 페이지·canonical Other 입력을 검사했다.
- 초기 pagination 검사는 입력 options의 공백이 그대로 남는다고 잘못 기대해
  실패했다. 기존 xsm_decide가 strip한 서버 canonical 값을 비교하도록 수정했다.
  Domain 정규화나 bridge 코드를 바꿔 입력을 억지로 보존하지 않았다.
- 중복 질문의 상충 답을 첫 답으로 고르는 결함과, 다른 native turn의 같은 call
  ID를 잘못 막는 결함을 각각 재현했다. 두 검사 모두 수정 전 실패했고 수정 뒤
  통과했다(hermes-native-question-occurrences-before.log).
- 본문/선택지 seal, receipt guard, profile fence를 제거한 source 변이3개를
  검출했다(hermes-native-question-mutants.json). 원본은 변이하지 않았다.

hermes-native-question-tests-first/final/occurrences/complete/current.log를 구분해
보존했다. 최종 core858개(Python517+SDK56+native133+Node152)는 macOS에서
98.582초에 통과했다(hermes-native-question-core-shipping.log).
독립 mock39/변이14는 별도 수치다.

## 실제 고정 Native SDK와 AIAgent

v0.22.5/bf0203a794a07aac3ff764972ab9087baa4e4f4e의 native registry/clarify executor/
hook와 XSM stdio를 연결한6개 확인이 통과했다(hermes-native-question-bridge).
Caller와 callback은 fixture이며 clarify 함수 경계 시험은 native middleware를
우회했으므로 실제 agent/사용자 인증으로 계산하지 않는다.

이어 실제 AIAgent, managed 설치·discovery와 native middleware를 거친 model0
루프를 실행했다. tool_search→tool_call→clarify→tool_call 재호출과 최종 응답,
UI callback1회,4개 도구 작업, 선택값 적용의4개 확인이 통과했다.
최종 표본은 hermes-native-question-agent-shipping이다. Source hash와 tool 결과를
보존했으며 plugin unload도 완료했다. Callback은 합성이고 실제 inference는0회다.

초기 agent 시험은 fixture가 deferred native 도구 발견을 처리하지 못해 실패했다.
반복 fixture 오류를 확인한 뒤 정확한 시험 PID에 SIGINT를 보냈다. 그 실행의
정리 호출 이름도 잘못돼 unloadFailure가 있었으며 성공으로 쓰지 않는다.
종료 뒤 해당 protocol session이 ended임을 별도로 확인했다. v2도 native discovery
미처리로 실패했고 unload는 완료했다. v3/v4는 discovery를 처리해 통과했다.
이 실패와 중단 기록을 모두 보존했다.

```sh
/isolated/hermes/bin/python -B scripts/probe-hermes-native-questions.py \
  --native-source /isolated/hermes-source --output /tmp/new-native-question-proof
```

위 도구는 실제 SDK와 명시적 scripted provider/UI callback만 사용한다. Native
인증 정보나 실제 model API는 사용하지 않는다. 모든 원시는
deliverables/protocol-foundation/ 아래에 있다. 실제 사용자 표시·선택지 fidelity,
메신저 UI와 실제 모델 협력, 전체 기능/OS/세션 수명 행렬은 별도 필수 조건으로
남아 있다. 2026-11-03 구현 담당자가 기록했으며 같은 담당자가 실제 native UI
표면에서 이를 실행한 뒤 판정한다. 범위 제외나 대체 완료의 사용자 승인은 없다.
