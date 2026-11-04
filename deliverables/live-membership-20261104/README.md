# 실제 가입·팀장 승인 경로 검증

2026-11-04~05 KST. 기본 메시지 왕복과 구분해 실제 모델의 가입 호출, 실제 사용자 선택,
프로젝트 멤버십, 팀장 연결, 새 가입 요청 전달을 확인했다.

실제 가입 경로 **6종**, 연결된 워커의 새 범위 전달 **5종**을 확인했다. 가입 작업에서
워커가 자기 사용자에게 여는 질문은 0건이었고, 새 프로젝트 요청을 두 번 호출해도
각 워커의 부모 요청·canonical 메시지는 한 건이었다. 부모의 실제 읽기·ACK도 확인했다.

## 실제 실행 범위

| 하네스 | 실제 경로 | 결과·근거 |
|---|---|---|
| Claude Code 팀장 | native MCP `xsm_join` → 실제 elicitation 폼 → 사용자 선택 → 가입·팀장 연결 | 4워커 그룹, 늦게 등록된 Hermes 폴더 추가, 새 Pi 대화의 팀장 연결을 각각 실제 적용. `actual-parent-decisions.json`, `actual-claude-tool-events.json` |
| Codex | 현재 실제 대화의 native 질문 → 원본 답변 읽기 → CLI 가입. 이후 연결된 워커의 CLI 재가입·부모 요청 | allow 적용, deny 미가입, 중단 뒤 “다시”에서 답변 복구. 재가입 exit 0, 새 요청 두 번은 같은 ID·exit 3. `codex-*.json`, `codex-*.log` |
| Pi | 실제 RPC 세션과 `gpt-6-luna`의 `xsm_join` | 새 대화의 승인 폴더 상속, 실제 팀장 연결 후 기존 가입 1회·새 scope 2회. 4 provider POST, 같은 요청 ID·부모 DM 1건·ACK, 로컬 질문 0. `native/pi-parent-final-19c7-actual-v1/result.json` |
| OpenCode | 실제 native session의 모델 `xsm_join` 3회 | 기존 가입은 already in, 새 scope 두 번은 같은 ID. 4 provider POST·부모 DM 1건·ACK·로컬 질문 0. `native/actual-model-join-opencode-a91c-v1/final-evidence.json` |
| OpenClaw | 실제 gateway/session의 모델 native tool 검색·호출 | 동일 3회 조건. 5 provider POST·부모 DM 1건·ACK·로컬 질문 0. `native/actual-model-join-openclaw-a91c-v1/final-evidence.json` |
| Hermes | 실제 native session resume 뒤 모델 tool 검색·호출 | 동일 3회 조건. 6 provider POST·부모 DM 1건·ACK·로컬 질문 0. `native/actual-model-join-hermes-a91c-v1/final-evidence.json` |

Native4의 실제 응답 모델 표기는 `gpt-6-luna`였다. Claude는 native assistant 기록의
`claude-opus-5-5`, Codex는 native turn_context의 `gpt-6.1-sol`을 관측했다. Codex의
raw provider 응답 모델명은 별도로 수집하지 않았다.

모델에게 시나리오와 호출 순서를 지정한 통합 시험이다. API 호출을 대신 만들어 주는
가짜 모델이나 성공 응답·동의 callback은 사용하지 않았다. 실제 UI를 통한 사용자의
선택은 직접 입력 또는 사용자가 명시한 값을 시험 제어기가 키로 전달했다. 제어기가
protocol 승인 응답이나 registry·parent 링크를 직접 만들어 성공시킨 검사는 아니다.
가입·팀장 연결의 변경은 실제 가입 operation으로만 진행했다.

Classic foreground와 native4의 headless worker 경로를 함께 시험했다. 모든 하네스의
독립적인 foreground 질문 UI나 자율 Orca 워커 생성까지 검증한 것은 아니다.
Codex의 worker CLI 작업과 시험 제어기의 부모 폼 전달 질문은 별도로 셌다.

## 발견하고 수정한 문제

1. 실제 Codex allow 뒤 turn_aborted·“다시”가 오면 latest_only가 답변을 숨겼다.
   정확한 질문·질문 ID의 답변을 보존하도록 독립적인 재개 단어만 건너뛴다.
   취소·수정 지시·다른 질문 답변, 만료·소비·다른 소유자 검사는 유지했다.
2. Claude가 아직 결정하지 않았다는 가입 질문 표시 지시를 실행할 때, 원 지시가
   이미 답변인 것처럼 나타나 질문이 생성되지 않았다. 질문을 요청하거나 결정이
   없다고 명시한 문구는 승인·거절의 원 요청으로 소비하지 않도록 수정했다.
3. 팀장에게 연결된 실제 Codex 워커가 CLI로 이미 가입한 프로젝트에 다시 가입해도
   거부됐고, 새 가입도 자동 부모 요청으로 가지 않았다. CLI와 MCP/native의 가입
   상태·부모 전달을 공통 서비스로 묶었다. CLI leave도 동일한 부모 전달을 사용한다.
4. 종료된 워커를 고르는 경우 질문부터 보여주고 허용 후에야 실패했다. 실제 Claude
   MCP에서 질문 없이 종료 워커 오류가 나는 경로를 재실행해 확인했다.
5. 질문이 열린 동안 워커가 종료되는 경우에는 적용 시작 표시 전에 scope를 다시
   검증한다. 이 경쟁 조건은 production MCP 응답 처리 경로의 component 검사로
   확인했다. 폐기된 질문을 다시 묻거나 사용자가 답하지 않았다고 안내하지 않는다.
6. 폴더는 이미 가입했지만 새 대화의 팀장 연결만 필요한 경우, 폴더 재가입 질문이
   아니라 coordinator 선택 질문을 표시한다. 실제 새 Pi 대화에서 membership
   changed=false인 채 팀장 연결이 생기는 경로를 확인했다.

코드 커밋: `8b0345a`, `9b2d30c`, `cd6d6c0`, `4f827b9`.

## 사용자 선택과 적용

| 요청 | 실제 선택·발생 | 적용 |
|---|---|---|
| Codex join-live-codex-deny-80d26f | 사용자가 allow 선택. 시험 이름에 deny가 있어도 허용으로 처리 | 해당 폴더 가입. `codex-real-join-applied.json` |
| Codex join-live-reject-cfb2 | 사용자가 deny 선택 | 미가입. `codex-real-deny.json` |
| 첫 4워커 그룹 폼 | 제어기의 키 탐색이 Decline을 눌렀음 | 가입 0·부모 연결 0. 오류로 보존, 사용자 거절 시험으로 세지 않음 |
| 같은 범위의 새 그룹 질문 | 사용자 지시대로 제어기가 실제 폼에서 allow 입력 | 팀장+4워커 가입, 부모 연결 4건 |
| 늦은 Hermes 새 폴더 질문 | 사용자 allow를 실제 Claude 폼에 입력 | 새 폴더 가입·부모 연결 |
| 새 Pi 대화 팀장 선택 질문 | 사용자 allow를 실제 Claude 폼에 입력 | 기존 폴더 가입 유지·새 대화의 부모만 연결 |
| 후속 a91c 그룹 질문 | 사용자가 Claude 창에서 직접 allow 선택했다고 확인 | 대상 워커들이 이미 종료돼 가입 0. 원 기록 unknown/started를 수정·강제 재시도하지 않음 |

후속 a91c의 client allow는 앞선 Hermes 답변의 잘못된 재사용이 아니었다. 사용자의
직접 입력 확인을 반영했다. 종료된 대상에게 질문을 만든 점과 적용 시작 표시가
남는 점을 위 사전·답변 시점 검증으로 보완했다. 해당 과거 기록은 보존했다.

## 실패·시행 조건 보존

- 첫 Claude 지시는 가입 권한으로 적용되지 않았지만, 지시가 답변처럼 표시돼
  실제 질문을 만들지 못했다. 수정 전 native 반환과 수정 후 실제 폼을 구분했다.
- 키 조작 실패로 첫 MCP 폼이 Decline됐다. 가입·부모 연결 전수를 확인해 모두
  0건임을 기록하고, 거절 기록을 되살리지 않고 새 질문으로 재시험했다.
- UI 원문을 읽는 Orca Computer Use는 Accessibility 권한이 없어 사용하지 못했다.
  OS 권한을 바꾸지 않고 terminal read/send로 실제 CLI 폼을 조작했다. 일부 redraw
  출력이 깨져 시험 TTY 너비를 조정했으며 원래 크기로 복원했다.
- Classic Claude 시험은 격리 설정을 사용해 native tool 실행 허용 창이 따로 나왔다.
  그 일회 실행 허용과 XSM 폼의 프로젝트 동의는 다른 단계로 기록했다. worker의
  가입 작업이 생성한 질문 수에는 시험 제어기의 UI 조작을 넣지 않았다.
- 초기 keeper의 30분 상한 중 원 Pi 대화는 모델 메시지를 저장하지 않은 채
  종료됐다. 없는 session 파일에 대한 resume이 새 ID를 반환한 시도는 종료하고
  원 ID로 위장하지 않았다. 새 Pi 대화에서 승인 폴더 상속을 확인한 뒤 실제로
  저장된 session 파일로 같은 새 UUID를 복구하고 팀장 연결을 새로 확인했다.
- native4의 공식 동일 UUID resume에서 새 process/protocol generation은 기록했고,
  가입·부모 관계를 합성하지 않았다. keeper 수명과 실제 모델 실행 시간은 구분했다.
- 기본 가입 시험과 새 scope의 승인 적용은 다르다. a91c와 Pi의 새 scope 19c7은
  최종적으로 미가입이다. 부모 수신·ACK를 가입 승인이나 작업 완료로 세지 않았다.

## 검사와 원시 자료

필수 승인 suite는 `required-approval-suite-release-check.log`의 **205건 OK**다.

```bash
python3 -B -m unittest tests.test_worker_project_flow tests.test_scope_service tests.test_openclaw_schema tests.test_xsm.SkillLayoutTest tests.test_mcp_dispatch tests.test_protocol_decisions tests.test_native_consent tests.test_user_answers tests.test_answer_binding tests.test_open_consent -q
python3 deliverables/live-membership-20261104/check-regressions.py
```

두 번째 명령은 정상 임시 복사본 검사 후, 관련 파일을 수정 전 커밋으로 바꿔
대응 검사가 실제 실패하는지 확인했다. **7/7 재현**이며 `regressions.json`과
`*-baseline-failure.log`에 있다. 원 작업 트리에는 이전 코드를 주입하지 않는다.

추가로 돌린 PersonDecision 레거시 검사는 **12건 실패**다. 같은 검사를 변경 전
`f606349`에서 실행하면 **17건 실패**였다. 남은 실패는 당시 검사에 있는 안내
문구·복구 경로·README 기대에서 발생했으며, 이번 필수 suite 통과와 합산하거나
전체 저장소 검사 통과로 표현하지 않는다. 원 출력은 `legacy-person-decisions-*.log`에 있다.

`actual-claude-tool-events.json`은 실제 Claude의 관련 tool 호출·결과를 추출한
것이며 unrelated 대화·thinking은 복사하지 않았다. `actual-parent-decisions.json`,
`actual-parent-delivery.json`, `actual-memberships.json`은 마지막 저장 상태다.
Native4 원시 caller 결과·입력·도구 반환은 `native/`에 보존한다. credential·개인
프로필은 복사하지 않는다. `native/`의 오래된 요약은 각 관측 시점 그대로 두며
최종 판단은 이 문서와 `results.json`으로 한다.

## 종료와 범위

별도로 띄운 native4/keeper/bridge/gateway는 모델 inflight 0을 확인한 뒤 종료했다. 이전 세대
42개 PID와 마지막 Pi 세대의 종료 근거를 구분했다. PID가 다른 프로세스에 재사용된
경우는 건드리지 않았다. 재사용한 Classic 대화는 남긴다. Claude 시험 대화는 격리 개발 설정에서 idle이며, Codex는 현재 대화다.

모든 가입·부모 권한 변경은 격리 XSM_HOME에서 수행했다. 기존 계정을 재사용한
Classic native 실행은 정상 대화 기록을 남긴다. 전역 설치·권한 설정·릴리즈는
하지 않았고 메신저·속도 행렬 시험도 하지 않았다.
