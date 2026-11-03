# Hermes AIAgent의 보드·문서·첨부 native 경로

상태: Mac·Linux에서 각각21개 검사가 통과했다. 실제 모델·사용자 UI와 전체
기능 행렬은 미완이다. 결정·endorsement의 실제 UI 검증은 이번 표본에 포함하지 않았다.

`probe-hermes-collaboration.py`는 고정 v0.22.5의 clean source와 실제 AIAgent,
설치 plugin, native Tool Hub의 search/call을 실행한다. Registry 직접 호출을
에이전트 실행으로 대신하지 않는다. 격리 HOME/HERMES_HOME/XSM_HOME과 git
저장소에서 모델만 명시적인 loopback scripted provider로 바꾼다. 공급자 자동
fallback은 없으며 실제 모델 호출0이다. API 키·사용자 프로필을 읽거나 바꾸지 않는다.

OpenCode와 `probe_native_collaboration_cases.py`의 같은 동작 검사를 공유한다.
Runtime별 호출과 원시 반환 형식은 분리한다. Hermes는 실제 native tool message의
이름·tool_call_id와 결과를 확인한다. OpenCode의 가짜 receipt 형식으로 바꾸지 않는다.
ScriptedTools의 lazy 모드는 실제 search 뒤 tool_call을 사용하며 기본 direct
모드는 유지한다. 공유 변경 후 OpenCode 정상21개와 parent 제거 변이가 각각
정상 통과/의도한 실패임을 확인했다.

## Mac 실행 결과

팀 create/list/show·보드 set/log/filter/predecessor·문서6개 action과 author/ref,
wip/limit/없는 parent·node·render, 바이너리 파일 송수신/크기/SHA/명시적 ACK와
owner 거부21개가 통과했다. 실제 XSM 호출29개/7개 operation, discovery를
포함한 native Tool Hub receipt58개와 scripted HTTP89개였다. Provider 발급 ID58개와
실제 native message ID58개의 고유성·일치를 독립 대조했다. XSM 호출29개는
같은 실제 native session이었다. 예상 오류는 parent·node·타 세션 storage3개다.

최초 실행은14개 검사 뒤 reference 서버 명령의 protocol 인자를 두 번 붙인
하네스 오류로 실패했다. 파일 검증은 미실행이었다. 명령을 고친 두 번째 실행은
21개를 통과했다. 최종 실행은 같은21개와 unload 뒤 native 도구 제거·참여 종료
검사까지 통과했다. 첫 실패와 모든 후속 실행을 보존했다.

## 검사 자체의 결함 검출

실제 native registry의 기존 handler를 호출한 뒤 결과만 바꾸는 임시 in-memory
wrapper를 사용했다. 제품·native source나 원본 노드를 변경하지 않았다.

| 변이 | 실패 검사 |
|---|---|
| board-parent | native board links observed predecessor |
| doc-candidate | native wip does not allocate or hide hypothesis |
| file-content | native binary attachment preserves bytes |

세 표본 모두 exit1/pluginUnloaded=true였다. 원시는
`deliverables/protocol-foundation/hermes-native-collaboration/`의 first/second/final과
각 변이 폴더다. 실제 turn 전체·native 메시지·gzip 요청, source5개/SHA manifest와
audit.json을 보존했다. 제품 engine은 바꾸지 않았다. 이번 test-only 변경으로
전체 core를 다시 통과했다고 표시하지 않는다. 다른 operation/action, UI·모델·
메신저·전체 runtime 행렬은 별도 증거가 필요하다.

## Linux 고정 source와 원시 대조

고정ecaf9f6의 Linux arm64/Python3.14에서도21개/29 XSM 호출/7개 operation,
native receipt58개와 HTTP89개가 통과했다. Mac과 native source commit 및
검사 이름21개가 같았다. 실제 turn에서 추린 native receipt ID58개가 모두
고유하고 provider 발급ID58개와 정확히 일치했다. 같은 native session과
예상 오류3개를 별도 대조해 audit.json에 남겼다. Plugin unload 뒤 도구 제거와
참여 종료를 확인했으며 container exit0/VM stopExit0이었다. Network none/model0
표본이다. 원시는 `hermes-native-collaboration-linux/output/artifacts/`와
상위 result.json이다. 변이3개는 Mac의 별도 표본이다.

## 기존 native API probe의 stale 기대값 수정

`probe-hermes-tools.py --installed --auto-reconnect`의 기존 기대값21은 현재
등록22개와 달랐다. 실제 실행이 그 assertion에서 실패함을 먼저 확인하고22로
고쳤다. 후속 Mac13개가 통과했다. 실제 설치 snapshot의 lease/제거, backend
재연결·세대 교체·옛 claim 거부, workspace 신원/전환, finalize/resume, UI 없는
승인 거부와 unload도 포함한다. stderr의 EOF·옛 claim·없는 UI 오류는 각 주입/
거부 검사에서 관찰한 예상 결과다. 실제 agent 시험과 API caller fixture는
구분하며 이 추가13개를 AIAgent21개에 합쳐 표시하지 않는다.
원시는 `hermes-tools-current-count-before`/`hermes-tools-current-count-final`이다.
이 두 줄 수정은 ecaf9f6의 Linux AIAgent 시험 이후이며 Linux API probe의 새
실행으로 소급하지 않는다.
