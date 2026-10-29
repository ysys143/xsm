# A18-02/J05 native handoff 중단 표본: claim 이전 실패

필수 claim 중단·동일 conversation resume·회수/ACK/reply 표본은 **미확보**다. 자동 반복 없이 최초 실행을 보존했다. 제품 handoff 결함으로 판정하지 않는다.

실제 구독 Codex `0.163.0`을 고정본 `/private/tmp/xsm-p13-local-frozen-dn7tom1y`와 private XSM_HOME·read-only sandbox로 1회 시작했다. 입력은 제품 skill/guide/tool description과 자연 목표뿐이며 내부 ref·명령 순서는 주지 않았다. MCP initialize와 tools/list(20개, inbox/ack 포함)는 실제 성공했다. 이후 native router의 `timed out negotiating with the code-mode host` 오류가 3회 기록됐고 `tools/call`은 0회였다. 100초의 자연 등록 관찰 예산이 만료돼 소유 CLI/MCP만 종료했다. native stdout은 thread.started/turn.started까지이며 backend 내부 모델 요청 횟수는 알 수 없다.

| 항목 | 관측 |
|---|---|
| native CLI 호출 / 완료 turn | 1 / 0 |
| coordinator 재호출·same-CID resume / 추가 사람 입력 | 0 / 0 |
| sender 호출 / 실제 xsm_inbox·claim·ACK·correlated reply | 모두 0 |
| receiver native ID | 실제 thread.started ID hash는 summary.json; xsm consumer identity/generation은 미성립 |
| 원 요청 ID / ACK 후 동일 작업 억제 확인 | 요청 생성 전이므로 없음 / 미실행 |
| proxy fault / 합성 tool 결과·identity·ACK·index 보정 | fault 미도달 / 모두 없음 |

관측된 사전 실패는 native tool host 경로다. xsm claim/회수 경로가 실행되지 않아 A18-02/J05 통과·실패의 제품 근거로 확대하지 않는다. 추가 native 호출이나 다른 CLI로의 자동 재시도는 하지 않았다.

원 로그·MCP client/server wire·private state는 `/private/tmp/native-handoff-evidence-zz3nvwnv`에 이동했고 원 파일 14개의 byte/SHA-256을 대조했다. 원 로그를 다시 쓰지 않았고 공개 deliverables에는 이 요약, script, hash/경로 manifest만 남겼다. 원 실행 script 사본도 tmp의 executed-code에 보존한다. claim token·실제 ACK 값은 공개 보고서에 복사하지 않았다. 원 script는 최초 경로에 결속된 실행 기록이며 재실행한 것이 아니다.

소유 CLI/proxy/MCP server의 PID·시작 시각을 대조해 정리했고 잔여 소유 프로세스는 0이다. 고정 source와 기존 profile 설정 hash는 전후 일치했다. auth 값·전역 설정·권한 규칙·기존 사용자 파일은 변경하거나 복사하지 않았다.

[요약 JSON](summary.json) · [원 파일 이동/hash manifest](manifest.json) · [controller](run.py) · [투명 proxy](proxy.py)
