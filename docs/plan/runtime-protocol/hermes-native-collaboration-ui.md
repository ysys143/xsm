# Hermes native UI의 보드 결정·문서 endorsement

상태: Mac·Linux에서 각각30개 검사가 통과했다. 실제 사용자·모델·메신저 UI와
전체 계획은 미완이다. UI 답은 명시적인 synthetic callback이며 host-user/human
기록을 실제 사용자의 승인으로 계산하지 않는다.

`probe-hermes-collaboration.py --native-ui`는 새 시험 프로필에서만
native_questions를 켠다. 실제 설치 plugin/AIAgent/Tool Hub가
search→원 작업→native clarify→동일 원 작업 재호출을 실행한다. 모델은
loopback scripted provider다. 답을 decision.response에 직접 넣거나 임의의
사용자 영수증을 만들지 않는다. 실제 clarify callback·post_tool_call hook·
공통 승인 저장 경로를 거친다. 기본 UI opt-in/사용자 설정은 변경하지 않았다.

## 실제 native 경로 검증

기존 협업21개 외에 다음9개 검사가 통과했다.

- 보드 결정1개와 human node의 결정 참조.
- Endorsement의 host-user 출처와 원문·parent·human/endorsed node.
- 같은 endorsement 재호출 시 UI와 노드가 추가되지 않음.
- Endorsed 본문 render.
- 거절한 후보에 human endorsement가 추가되지 않음.
- 실제 native synthetic UI callback3회.
- 답 영수증 저장 후, 원 작업 재호출 전 효과0개.
- 거절 기록의 실제 denied 상태와 not now 값.

마지막 경계는 provider가 실제 clarify 결과를 관측한 뒤 원 작업 재호출을
내보내기 직전, operator가 시험 정본만 읽어 확인했다. 모델 세션을 가장하거나
새 권한을 만들지 않는다. 보드/endorse 승인2개는 answered, 거절1개는 기존
decisions 계약대로 즉시 denied였다. 그 시점의 효과는 모두0개였다.
승인 영수증 저장과 효과 적용을 실제 native 흐름에서도 분리했다.

최종 Mac final-r3는30개/41 XSM 호출/9개 operation, native receipt88개와
scripted HTTP131개였다. 발급ID88개와 실제 native message ID88개가 모두
고유하고 일치했다. UI callback3개와 관측 snapshot3개, unload 뒤 도구 제거·
참여 종료를 확인했다. Source6개 snapshot/SHA manifest와 audit.json을 보존했다.

실제 native handler의 결과만 감싸 endorsement.via를 model로 바꾼 변이는
`native endorsement creates exact human child`에서 exit1이 됐다
(endorsement-via-r2). Canonical human node나 제품 소스는 변이하지 않았다.
UI 없는 기존 기본 경로와 OpenCode의 직접 도구 호출 모드도 유지하며, 공유
provider 변경 뒤 OpenCode21개/58HTTP가 다시 통과했다.

## 실패·정리와 기록의 한계

- first는 관측기 추가 전28개를 통과했다. 최종30개와 합산하지 않는다.
- final/endorsement-via는 Mac /var와 /private/var를 같은 형태로 정규화하지
  않은 관측기 assertion으로 실패했다. 실패한 handler가 연결을 끊자 native SDK가
  자동 재시도했다. 두 시험 controller의 실제 argv/PID를 대조한 뒤 SIGINT로
  plugin 정리를 수행하고, native 도구 제거·참여 종료를 확인한 뒤 SIGTERM으로
  남은 retry thread를 끝냈다(exit143). 사용자 프로세스는 종료하지 않았다.
- 두 실행은 각각23개 검사 후 중단됐고 요청 counter118개 중 gzip 본문은106개만
  남았다. 각각12개 본문이 누락됐다. 이미 유실된 본문을 재구성하지 않았으며
  이 두 표본을 정상 성공이나 변이 검출로 세지 않는다.
- 경로를 정규화한 final-r2도 거절 영수증까지 answered라고 잘못 기대해 검사에서
  실패했다. 실제 snapshots는 answered/answered/denied와 효과0개였고, 기존
  decisions.py의 negative-answer 계약을 확인해 검사를 바로잡았다. 제품 정책을
  바꾸지 않았다.
- 이후 관측기 예외는 HTTP400과 원시 오류/요청 로그로 남기고 시험을 실패로
  처리하도록 했다. 별도 synthetic HTTP 경계1건이400/로그1개를 확인했다. 이는
  native UI 시험이나 모델 결과가 아니다.

원시는 `deliverables/protocol-foundation/hermes-native-collaboration-ui/`다.
observer-path-incident.json에 두 실패의 PID·정리·누락 수를 보존했다.
실제 제품 engine은 바꾸지 않았으며 전체 core 재통과를 주장하지 않는다.
실제 사용자 UI fidelity·모델·메신저와 전체 runtime/기능 행렬은 별도 필수 조건이다.

## Linux 고정 source 대조

고정516fc17의 Linux arm64/Python3.14에서도30개/41 XSM 호출/9개 operation과
native receipt88개/HTTP131개가 통과했다. 실제 synthetic callback3회와
답 저장→원 작업 재호출 전 snapshot3개의 효과0개를 확인했다. Mac과 검사
이름30개와 native source commit이 같았다. Raw 발급/nativeID88개가 모두
고유하고 일치했으며 로그 누락/관측기 예외는 없었다. 도구 제거·참여 종료,
container exit0/VM stopExit0이었다. Network none/model0이다.
원시는 `hermes-native-collaboration-ui-linux/output/artifacts/`와 상위 result.json,
audit.json이다. 출처 변이는 Mac 표본이며 실제 사용자·모델·전체 UI 인증은 아니다.
