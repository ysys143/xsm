# Factory native handoff 기능 표본

일반 factory 경로에서 실제 claim 응답 보류 뒤 **같은 native CID·새 PID 세대의 원문 회수, 실제 ACK/correlated reply, ACK 후 빈 inbox**를 관측했다. 전체 J05·릴리스 완료 판정은 아니다. 이번 조건은 사용자 새 승인 이벤트가 아닌 코디네이터의 추가 평가 조건이다.

현재 PATH의 CLI는 `codex-cli 0.164.0`, source는 `/private/tmp/xsm-p13-postqa-frozen-bukwksw6`이다. 성공한 Actor.start의 factory argv/env를 기반으로 사용했다. native 기본 지침을 model_instructions_file로 교체하지 않았고 feature/내장 도구를 disable하지 않았다. private 작업 폴더에 제품 skill만 설치했다. CODEX_* 전체 제거 없이 명시 thread 식별자/API 키 이름만 제거하고 나머지 정상 환경은 유지했다. 키 값을 조회·출력하지 않았다.

실제 thread.started와 MCP의 확인된 native ancestor PID/lstart/home으로 초기 등록 3회를 수행했다(최초 receiver·sender·성공 resume). 이는 허용된 setup이며 가짜 identity 생성과 구분한다. setup 전송은 sender 모델의 일반 xsm_ask 1건이고 coordinator의 수동 send/ACK/본문 중계/index 보정은 없다.

proxy는 실제 xsm_inbox claim 응답만 0 bytes 전달 상태로 보류했다. 최초 wrapper/MCP 종료 직후 첫 resume은 active writer로 거부됐다. 기존 자기 native PID 종료를 확인한 뒤 같은 CID를 다시 resume해 실제 ACK/reply를 얻었다. 이 첫 제어 실패와 추가 resume을 숨기지 않는다. 성공 resume 뒤 observer가 종료 직후 ancestor를 재조회하다 실패한 tail race도 평가기 오류로 남겼으며 native ACK/reply 원 출력은 정상 완료됐다.

native CLI 호출은 총 4회(최초 receiver 1, sender 1, native turn 시작 전 거부된 resume 1, 실제 resume 1), 실제 turn 시작/완료는 각각 3회다. coordinator resume은 2회, 추가 사람 입력은 0회다. 이전 두 tool-host 준비 실패를 제품 handoff 실패로 판정하지 않는다. 이번에는 tools/call이 실제 실행됐고 tool-host 실패는 0이다.

원 ID·receiver native endpoint·전체 digest/본문은 유지됐다. owner-dead 회수 뒤 claim token/세대가 바뀌었고 실제 xsm_ack가 원 요청을 확인했다. receiver의 xsm_send reply_to는 원 ID와 일치했고 sender의 질문 인덱스에 실제 회신 1건이 있다. ACK 뒤 실제 xsm_inbox 응답은 messages/claims 모두 빈 배열이다. 실제 token·ACK 값은 공개하지 않고 summary에는 hash/상태만 기록했다.

raw stdout/stderr·claim wire·state·등록 근거는 `/private/tmp/native-handoff-factory-cytvti8g`에 보존했다. frozen source hash는 유지됐다. profile config hash drift는 다시 관측됐으며 변경 주체는 미확정이다. 평가자의 profile/권한/allowedTools 편집 명령은 없고 이를 불변으로 과장하지 않는다. 기존 실패와 drift는 보존했다. 소유 process handle을 확인해 종료했으며 추가 native 실행 없이 종결했다.

[요약/계수](summary.json) · [조건](plan.json) · [hash/경로](manifest.json) · [controller](controller.py) · [proxy](proxy.py) · [resume observer](resume-observer.py)
