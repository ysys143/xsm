# J03 일반 Codex TUI idle/busy/interrupted 실제 표본

같은 일반 TUI 하나에서 idle과 busy 질문은 추가 입력 없이 실제 수신·회신까지 성공했다. Esc로 중단한 뒤의 질문은 **실패**했다. native queue 보관은 성공했으나 daemon wake가 `not-loaded`였고, 60초 ask timeout과 후속 status 조회에서도 pending이었다. 종료 전 103초 관측 동안 receiver의 새 turn이나 답은 없었다. 전체 J03 통과로 세지 않는다.

## 고정 조건과 실제 endpoint

- 제품 제어/MCP 소스: `/private/tmp/xsm-p13-postqa-frozen-bukwksw6`, manifest 313개 시작·종료 해시 일치.
- 일반 TUI CLI: 실제 `codex --version` **0.164.0**. 기존 공유 daemon PID 9102의 실제 바이너리 version **0.165.0**. 공유 daemon은 이 평가 소유가 아니며 종료하지 않았다.
- 기존 `.codex-3` 프로필을 재사용했다. 공개 `codex login status`는 `Logged in using ChatGPT`였다. credential 값 조회/복사·새 로그인·API 과금 경로는 사용하지 않았다.
- 기존 설정을 정상 로딩하며, 호출 한정 `-c`로 xsm MCP만 고정본 command/args/cwd/env와 private XSM_HOME에 연결했다. 다른 MCP·도구·hooks·기본 지침을 비활성화하거나 교체하지 않았다. `--ignore-user-config`, hook trust bypass, allowedTools 보정은 없다. 전역 설정의 기존 danger-full-access 대신 이 호출은 workspace-write/approval never로 제한했다. 추가 trust·OS 권한·로그인 승인창은 없었다.
- PTY TUI wrapper PID **64952**, 실제 Codex PID **64954**, lstart **Thu Oct 29 05:59:56 2026**, SID **01a1844f-fe38-7ce2-b466-7bb38e5a4c60**. native `session_meta`의 originator는 codex-tui이며 cwd는 이 저장소다. PTY와 native rollout으로 실제 세션을 식별한 뒤 이 SID만 대상으로 삼았다.
- 실행용 worker 서비스를 만들지 않았다. 실제 일반 TUI 1개와 공개 질문을 보내는 실제 `codex exec --json` producer 3개다. producer별 SID/PID/lstart와 원 요청 ID는 [JSON](codex-state-native-results.json)에 기록했다.

## 상태별 첫 결과

| 상태·관측 근거 | 일반 송신 | 큐 / daemon wake | 실제 receiver 처리 | 실제 원 요청 결속 회신 | 회수 상태 |
|---|---|---|---|---|---|
| idle: 초기 task_complete + PTY 입력 대기 | native producer xsm_ask, next | 보관 성공 / not-loaded | 기본 TUI 큐가 새 UserMessage/turn 시작 | succeeded, 2+2=4·반례; queue→reply index 19.736초 | producer ask final, reply ACK |
| busy: 실제 55초 Python 대기 tool을 수행하는 turn 중 질문 보관 | 별도 native producer xsm_ask, next | 보관 성공 / not-loaded | 기존 task_complete 뒤 새 UserMessage 처리 | succeeded, 2+2=4·반례; queue→reply index 47.997초 | producer ask final, reply ACK |
| interrupted: 실제 90초 대기 tool 시작 후 Esc, turn_aborted(reason=interrupted), PTY Conversation interrupted | 별도 native producer xsm_ask, next | 보관 성공 / not-loaded | 추가 native UserMessage/turn 없음 | 없음 | ask pending/timeout, 이어 status pending/timeout |

busy의 queue 보관은 06:02:19 KST, 기존 task_complete는 06:03:01.666, 질문의 UserMessage는 06:03:01.900이었다. 실제 기존 turn 뒤 처리 순서를 확인했다.

interrupted는 06:06:36.747 KST에 turn_aborted가 기록됐다. 질문은 06:07:09에 큐에 저장됐다. 중단 전 시작한 background Python은 06:08:01에 완료됐지만, 이는 새 모델 turn이나 질문 수신이 아니다. 첫 실패를 그대로 보존했고 추가 TUI 입력·receiver inbox poll·재전송으로 성공시키지 않았다.

읽기 전용 SQLite 연결(`mode=ro`)로 실제 queue ID와 대상 SID만 조회했다. idle/busy 항목은 소비되어 없었고 interrupted 항목 **01a18456-9542-7293-b29a-6ba2d5e7ef85**는 종료 후에도 그대로 남았다. queue row를 생성·수정·삭제하지 않았다. fake queue/app-server/native 응답 주입은 0회다.

## 개입·도구·전달 분리 계수

- controller의 endpoint 수동 등록 **0회**. 실제 설치 hook/MCP가 native endpoint를 등록했고 controller는 관측만 했다.
- controller PTY 초기 역할 입력 **1회**, busy 상태 준비 입력 **1회**, interrupted 상태 준비 입력 **1회**, Esc **1회**. 실제 사용자 클릭·명령·승인 **0회**. 각 질문을 보낸 뒤 receiver에 후속 입력 **0회**다. PTY terminal capability 응답은 화면 에뮬레이션이며 모델 응답이 아니다.
- producer는 상태별 skill/guide 읽기 shell **2회**, MCP **2회**였다. idle/busy는 ask+ACK, interrupted는 ask+question_status다. 질문은 각각 **1회**이며 자동 모델 재시도·질문 재전송은 없다.
- receiver 초기 준비는 기존 다른 MCP `reason-network.check_inbox/list_team` **2회**였다. xsm inbox 수동 poll은 아니며 idle 성공 근거로 세지 않았다.
- receiver의 실제 xsm 회신 MCP는 idle/busy 각각 `xsm_send` **1회**, interrupted **0회**다. 두 회신 모두 서로 다른 실제 producer의 원 요청 ID와 정확히 결속됐다.
- idle에서 receiver가 기존 설치 xsm 0.4.20 guide를 읽고 sandbox shell 송신을 **1회** 잘못 시도했다. exit 2/sandbox refusal 뒤 스스로 고정본 xsm_send MCP로 전환했다. 실패도 원 표본에 보존했다. busy는 같은 TUI 문맥에서 MCP로 바로 회신했다. 기존 안내와 다른 MCP가 함께 노출된 정상 프로필 조건이며 factory-only 비교가 아니다.
- native queue 제출은 task 3개+reply 2개로 **5회**, daemon wake도 **5회 모두 not-loaded**였다. receiver 자동 큐 처리 성공은 **2회**다. daemon wake 성공을 주장하지 않는다. producer reply readback/ACK 성공과 receiver 자동 입력 활성화를 구분했다.

## 실패 범위와 인계

이번 반례는 **정상 실행 중인 일반 TUI 0.164.0 + 기존 공유 daemon 0.165.0 + .codex-3 한 프로필**에서, Esc 중단 후 queue 보관은 됐으나 wake가 not-loaded이고 자동 질문 처리가 재개되지 않은 것이다. TUI SID가 해당 shared daemon에 hosted되지 않는 경로와 제품 wake의 결합을 조사할 근거다. version mismatch가 원인이라고 단정하거나 다른 CLI/daemon 조합으로 확대하지 않는다. idle/busy 성공이 interrupted 실패를 메우지 않는다.

제품 소스는 동결했다. 원 요청/queue/state와 원 timeout을 보존했으며 수정·강제 wake·자동 재시도는 하지 않았다. 후속 소유자는 coordinator다. 재개 조건은 보존된 실제 SID/queue ID와 private 상태를 기준으로 TUI hosting/wake 경로를 조사하고, 수정·새 조건의 재실험을 별도로 승인된 작업으로 구분하는 것이다. 수동 prompt/poll 성공을 이 셀의 자동 wake 성공으로 다시 표기하지 않는다.

## 종료·증거

관측 약 10분 13초에 cleanup까지 마쳤다. 자기 TUI 및 종료 직전 관측한 하위 native/MCP/code-host 프로세스가 모두 없어졌고 producer 3개도 종료됐다. private 폴더를 열린 파일로 보유한 프로세스도 없었다. 기존 daemon PID 9102와 실제 사용자/peer 세션은 유지했다. config.toml/hooks.json/settings.json은 전후 해시가 같고, 고정본 소스도 불변이다.

raw PTY/native rollout/producer stdout·stderr/state는 `/private/tmp/p13-codex-state-native-dv1ahfwm`에 보존했다. 공개 산출물에는 credential·claim token·원시 개인 본문을 복사하지 않았다.

- [PTY 하네스](codex-state-native-eval.py), [실제 producer](codex-state-native-producer.py), [읽기 전용 audit](codex-state-native-audit.py)
- [상태별 결과·PID/SID·도구 계수](codex-state-native-results.json)
- [산출물·private 증거 manifest](codex-state-native-manifest.json)
