# Hermes Telegram 실제 사용자 질문 표본 — 2026-11-03

상태: 승인된 개인 대화의 native 질문·실제 선택·XSM 적용을 확인했다.
Standalone TelegramAdapter와 실제 AIAgent 경로이며 GatewayRunner의 session routing,
실제 모델 inference, Discord·다른 UI 전체 지원은 미완이다.

## 경로와 승인 경계

사용자가 지정한 기존 시험 프로필과 test-target.json의 개인 대화만 사용했다.
Profile700/.env600/target600을 확인했고 chat와 sender가 일치했다. Native getMe로
저장된 bot username과 일치하고 webhook이 없음을 확인했다. 실제 대상 ID는
기존 private 프로필에만 두고 결과에는 fingerprint만 남겼다.

새 임시 HOME/HERMES_HOME/XSM_HOME에서 native0.22.5와 managed xsm plugin을
실행했다. Telegram extra는 같은 source의 uv.lock으로 별도 임시 env에 frozen
설치했다. 기존 config와 공유 proxy/일반 사용자 profile은 바꾸지 않았다.

Credential은 승인된 .env를 한 zsh 프로세스에서 source하고 지정 변수만 export했다.
값을 명령 인자·출력·로그에 넣거나 저장소에 복사하지 않았다. Native HTTP 로그를
비활성화했고, scripted provider 입력에 실제 token이 없다는 검사도 수행했다.
새 env 준비와 실제 사용에는 apikey-env의 프로세스 한정 주입 절차를 적용했다.

Native TelegramAdapter의 공개 authorization check는 지정 user와 private chat만
허용했다. Native send_clarify가 보낸 카드의 버튼 callback을 native clarify queue가
받고, AIAgent의 clarify 결과→post_tool_call→XSM decision.response로 연결했다.
이 대화의 'Telegram에서 선택했어' 응답은 상태 확인일 뿐 답으로 사용하지 않았다.

## 실제 결과

- Native 질문 카드1건, native 응답1건, 예상 밖 입력0건.
- 사용자가 Telegram에서 선택한 값은 blue였다. Native bridge가 이를 받아
  decision을 host-user source와 native occurrence 기반 source_id로 저장했다.
- 원 작업의 동일 인자 재호출 뒤 decision status=applied를 확인했다. 답 저장만으로
  원 작업을 자동 적용하지 않았다. 임시 색상 결정이며 프로젝트 권한은 바꾸지 않았다.
- 실제 AIAgent의 tool_search→tool_call→clarify→tool_call 재호출과 최종 응답의
  4개 확인을 통과했다. Scripted provider 요청7회, 실제 inference는0회다.
- Plugin unload, adapter disconnect, transport thread 종료를 확인했고 protocol
  participant1개 모두 ended였다. 시험 연결을 켜 둔 상태로 완료 처리하지 않았다.

원시는 deliverables/protocol-foundation/hermes-telegram-question-user/의
result.json, telegram-ui.json, native-tool-results.json, decision-audit.json,
source-audit.json에 있다. Product/base-probe source hash는6c1dd78과 일치했다.
실제 human callback으로 바꾼 실험 driver/helper의 별도 hash도 보존했다.
재현 코드는 같은 deliverables의 probe-hermes-telegram-question-user.py와
native_telegram_question_transport.py다. 실제 credential은 이 폴더에 없다.

## 표본의 한계

모델은 scripted provider였고 실제 Native SDK AIAgent를 사용했다. UI callback은
합성 응답이 아니라 실제 Telegram 사용자 선택이었다. 이를 실제 모델 성공이나
GatewayRunner 전체 UI/session/권한/queue 인증으로 확대하지 않는다. 과거 실제
Telegram gateway/model/XSM FYI 왕복과 합쳐 하나의 동시 실행 표본으로도 쓰지 않는다.

이번 표본은 단일 사용자·단일 질문·두 선택지의 macOS 실행이다. 실제 GatewayRunner
UI, 다른 profile/session의 실전 분리, 취소·늦은 reply의 실제 플랫폼 동작, 여러
선택지/긴 본문 표시 fidelity, Discord·Linux·전체 행렬·p95 조건은 남아 있다.
구현 담당 세션이 해당 표면을 추가 실행한 뒤 다시 판정하며 전체 목표는 미완이다.
