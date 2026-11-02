# Hermes Telegram 실제 연결 표본 — 2026-11-02

사용자가 새로 발급하고 지정한 시험 봇과 개인 대화만 사용했다. 자격 증명과
원시 대상 ID는 저장소 밖의 전용 시험 프로필에 남겼고 결과에는 대상 hash만
기록했다. 일반 사용자 Hermes/Codex/Claude 프로필이나 OpenCodeX 공유 설정은
변경하지 않았다. 봇 token은 결과·명령 인자·로그에 넣지 않는다.

## 고정 입력과 환경

Hermes v0.22.5의 peeled commit bf0203a794a07aac3ff764972ab9087baa4e4f4e을 사용했다.
Telegram dependency는 그 pyproject의 python-telegram-bot[webhooks]==22.8이다.
처음 freeze/requirements를 일반 pip resolver로 설치하려던 두 시도는 upstream의
Pillow override를 반영하지 못해 실패했다. 소스의 원래 [tool.uv] override와
uv.lock을 적용하는 uv sync --frozen --extra telegram --no-dev로 별도 환경을
준비했다. 런타임·모델을 다른 버전으로 바꾼 것이 아니다.

프로필은 Library/Application Support/xsm-tests/hermes-telegram이며 디렉터리700,
.env600이다. HOME은 그 안 runtime-home, HERMES_HOME은 시험 프로필,
XSM_HOME은 전용 xsm-state로 설정하고 부모의 모델 API key 환경을 상속하지
않는다. 프로젝트에 bot token 사본을 만들지 않는다.

## 실제 transport

getMe로 새 bot identity와 token 인증을 확인하고 webhook이 설정되지 않았음을
확인했다. 사용자에게 고유 /start 명령을 요청해 개인 대화·sender 일치와 nonce를
대조했다. getUpdates 조회에서는 offset을 전진시키지 않았다.

scripts/probe-hermes-telegram-live.py는 실제 pinned TelegramAdapter의 connect,
message dispatcher, send, disconnect를 실행했다. pending update를 버리지 않고,
지정한 사용자만 허용하며 typing/startup ping/status indicator를 비활성화했다.
확인 명령을 실제 native inbound로 받고 고정 진단 메시지 1건을 보내는 데 성공했다.
연결 종료까지 7.787초였다. 결과는 hermes-telegram-live-first/result.json/log에 있다.
이 표본은 model 0, 실제 gateway runner와 xsm 전달은 아직 검증하지 않은 transport
시험으로 명시했다.

## 실제 Hermes agent와 gateway

기존 구독 프록시의 연결/모델 정보는 읽기 전용으로 확인했다. 별도 native AIAgent는
local proxy의 chat-completions 경로로 확인 문구를 반환했다. tool0, max iteration1,
context/memory/background review 없이 수행했다. 모델 설정은 live catalog에서
확인한 anthropic/claude-sonnet-5-5다. 이 첫 표본은 실제 served-model 값까지
기록하지 않았으므로 model identity 전수 인증으로 쓰지 않는다.

실제 GatewayRunner는 같은 전용 프로필의 session store·권한·Telegram adapter와
모델 설정을 사용했다. 첫 실행은 사용자 메시지 대기 시간 안에 기대 회신을
관측하지 못해 timeout/정상 stop이었다. 두 번째는 보존된 대기 메시지로 실제 세션
1개·모델 API call1·tool0을 기록했고, assistant history와 delivery obligation에
확인 nonce가 남았다. delivery state는 delivered였다. native BasePlatformAdapter는
성공한 SendResult에 대해 mark_delivered를 기록한다.

두 번째 시험기의 send() wrapper는 실제 전송의 모든 native 경로를 관측하지 못해
별도 timeout으로 끝났다. 이를 제품 실패나 시험기 통과로 바꾸지 않는다.
hermes-telegram-gateway-native-audit.json은 실제 session/model/delivery DB를
read-only로 읽은 별도 증거이며 메시지·사용자 ID·token 원문을 포함하지 않는다.
hermes-telegram-gateway-first/second의 실패·종료 기록도 그대로 보존했다.

## 아직 통과하지 않은 기준

이 표본은 xsm P2P 원문→실제 Hermes 입력 큐→모델 문맥→명시적 ACK 경로를
검증하지 않았다. 실제 user decision UI·worker·재개·p95 100회·다른 런타임과
30방향·Discord·Linux Telegram gateway도 미완이다. 새로운 봇이 만들어졌거나
확인 문구가 도착했다는 사실만으로 이 기준을 완료 처리하지 않는다.

## 실제 native xsm 도구와 FYI 왕복

전용 프로필에만 xsm installer를 적용하고 plugin/toolset을 명시적으로 활성화했다.
기존 config는 같은 private 프로필에 백업했다. 일반 사용자 프로필과 공유 프록시는
변경하지 않았다. 소유 snapshot은 57154f82f91a이며 실제 profile에 연결됐다.

실제 Hermes agent는 도구를 세 개의 검색/호출 bridge로 접어 노출한다. 최상위에
xsm_inbox가 있어야 한다던 초기 assertion은 모델 호출 전에 실패했다. Native
검색을 사용한 후속 호출은 실제 xsm_inbox를 찾았으나 terminal cwd가 없는 문맥을
거부했다. profile의 native terminal.cwd를 실제 작업 디렉터리로 제공한 세 번째
표본은 tool_search→xsm_inbox를 실제 호출하고 정상 확인 문구를 반환했다. Gateway
프로세스 cwd를 caller로 위장하거나 바인딩의 identity 검사를 제거하지 않았다.
실행들은 hermes-native-xsm-tools-probe[-v2,-v3].log에 분리돼 있다.

같은 실제 agent 대화의 다음 turn에서, 별도 protocol sender가 같은 격리 xsm state에
FYI task를 저장했다. 원문은 native 읽기 전에 unacknowledged였다. 실제 model이
xsm_inbox→xsm_ack→xsm_send(reply/outcome=succeeded)를 호출했고 sender도 실제
reply를 읽고 ACK했다. 최초 표본은 이 데이터 왕복 7개 항목은 통과했지만 이후
출력 제한/continuation과 provider thinking 옵션 오류를 남겼다. 그 결과를 깨끗한
모델 턴 성공으로 계산하지 않는다.

두 번째 표본은 같은 model/provider/runtime에서 max output을 256→1536으로
보완하고 새 request ID/nonce로 실행했다. 기존 7개에 completed=true/failed=false를
더한 8개 검사가 통과했다(hermes-native-xsm-roundtrip-second/result.json/log).
최종 turn의 API calls는4, 종료는 text_response(finish_reason=stop)였다. 중간의
실패한 tool_describe 시도도 trace에 남겼다. requested model은 live catalog의
anthropic/claude-sonnet-5-5이며 served_model은 응답에 없어 null로 기록했다.
모델명을 확인했다고 실제 served identity까지 증명한 것으로 확대하지 않는다.

이 왕복은 실제 native agent/model/tool이지만 Telegram send는 하지 않았으며
wake=never/pull이다. Telegram gateway의 agent→platform 전달 표본과 합쳐 하나의
xsm→Telegram end-to-end로 주장하지 않는다. Native push/idle p95, actual UI와
다른 runtime/platform/worker/remote matrix의 미완 기준도 그대로 남아 있다.
