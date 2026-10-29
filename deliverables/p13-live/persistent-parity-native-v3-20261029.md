# 제6조건: 기존 unrestricted CLI ↔ native child MCP parity

네 업무질문의 실제 답변·수신 파일 읽기·명시 ACK와 쌍대 결과 일치를 확인했다. 모델 실행 구간은 279.146초이며 새 TUI 1명과 MCP sender child 1명만 실행했다. 기존 본인 native 세션이 CLI sender이므로 별도 CLI native launch는 없다. 원5조건/9 launch는 그대로 보존해 누계6조건/11 launch다. 자동 모델 재시도0, 추가 조건0.

원 수집기 최종 상태는 failure다. child exit0/turn.completed 뒤 `BoundActor.refresh`가 종료된 PID의 부모를 다시 조회해 `sender native ancestor mismatch`를 낸 종료 시점 assertion을 보존했다. 이를 성공으로 덮어쓰지 않았다. 별도 offline audit가 이미 존재하는 네 canonical request/reply, 실제 tool 원문, ACK 및 파일 bytes를 대조해 아래 업무 결과만 확인했다. 제품 결함 또는 전면 gate 완료로 확대하지 않는다.

## 실행 전제와 신원

- 실제 exec에 CODEX_SANDBOX/XSM_SANDBOXED 키가 없음을 확인했다. marker 제거·sandbox 변경·certainty 강제 없음.
- source는 `/private/tmp/xsm-doctor-privacy-frozen-47o6orah`. 315파일 전후 SHA 검증 및 CLI help/ask flags 검증. CLI 절대경로 wrapper는 이 source를 우선 로드한다.
- 실제 CLI `who --json`은 기존 CID `01a181b4-9f34-74c0-8d0f-6c1d69a6a10f`, home `.codex-3`, PID9102/lstart 및 live app-server를 반환했다. SQLite exact CID/cwd도 대조했다. 원 환경을 유지하고 private registry에 제품 self-adoption으로 등록했다.
- 수신 TUI CID `01a18564-4f25-7193-a08e-c73910fa3336`, native55127, proxy55344/server55439. 기존 trusted repo에서 Codex CLI0.164.0, read-only/approval never. 실제 initialize/tools/list 및 xsm_inbox(wait0) 성공, files v1 observed와 live PID 확인 뒤 CLI를 시작했다. proxy/server 시작 stderr는 빈 값.
- MCP child CID `01a18566-e00d-77c2-98df-9bc7db2b6559`, wrapper68656/native68679/MCP68888. CLI 두 답의 실제 읽기/ACK 뒤 시작했다. child 등록은 자기 wrapper 아래 native PID 계보에 속한 beacon만 사용했으며 TUI reader를 제외했다. 실제 실행 중 ps의 native68679→wrapper68656 관계를 확인했고 원 등록을 보존했다.
- 현재 repo cwd는 읽기 대상으로만 사용했다. 전역설정·trust·권한·제품·plan·ledger 수정, credential 복사 없음. own private state만 사용했다.

## 실제 4왕복

| 표면 | 원 request | 실제 reply | 원 reply_to | 결과/ACK |
|---|---|---|---|---|
| 기존 host CLI plain | 5c5aa35175e2447e | 60e6fcc7e0434456 | 5c5aa35175e2447e | reject / 4, 양쪽 명시 ACK |
| 기존 host CLI file | 375e2c9752304b98 | 7ba364ad883d4c23 | 375e2c9752304b98 | reject / 4, 실제 파일 읽기, 양쪽 명시 ACK |
| child MCP plain | 2d8c6753148b4eba | dd47307b81c44eb9 | 2d8c6753148b4eba | reject / 4, 양쪽 명시 ACK |
| child MCP file | aa1c99bcd11e4018 | a9f12c77eb524f65 | aa1c99bcd11e4018 | reject / 4, 실제 파일 읽기, 양쪽 명시 ACK |

각 표면의 질문 본문 bytes는 동일하다. 파일 bytes는 모두122이며 SHA256 `d339583fadf151657b5ed3f0606508d3ed52cdcafb98dc3740f23ab28acbd22b`다. 자료에만 있는 무작위 FILE 표식은 body에 포함하지 않았다. 수신자의 실제 xsm_files entry read2개에서 content bytes가 원자료와 일치하고, 각 답의 file SHA 및 FILE 표식 SHA도 일치했다. body 표식과 파일 표식을 혼동하지 않았다.

CLI manifest `fc4ef5383ec84293bd8df0b73fc2cec0`, storage `0946b54d8d9545478748dc3ddd83434b`; MCP manifest `71741b7f284844faac4691b3e82b378d`, storage `2646159076654cf58057bdf5e29b4d62`. 두 manifest는 version1/previous=null이며 owner는 각각 실제 host/child, 수신 사본 owner는 같은 TUI다. 별개의 표면 비교 자료이므로 버전 변경이나 previous 연결 실험이 아니다.

## digest 대조

기존 `envelope.request_digest(record.identity)`로 네 요청과 네 답의 digest를 재계산해 모두 원 canonical digest와 일치함을 확인했다. 실제 ask 응답의 verified digest도 각 canonical 요청에 일치했다. plain 두 결과의 파싱된 JSON은 동일하고 file 두 결과의 파싱된 JSON도 동일하다.

전체 요청 digest는 request ID·실제 sender endpoint·manifest binding이 다르므로 표면 사이에서 서로 다르다. 이를 제품 계약 변경이나 불일치로 판정하지 않는다. 동일 body의 raw/기존 semantic SHA와 동일 file content SHA, 두 manifest 자체 digest, 각 원 요청과 reply_to 결속을 따로 검사했다. 상세 SHA와 entry/owner는 audit JSON에 기록했다.

## 기능표: 이번 native 표본과 기존 fixture 구분

| 기능 | CLI / MCP 이번 관측 | 범위/다른 셀 |
|---|---|---|
| priority | 둘 다 next | Codex now 거절은 기존 `test_question_interfaces.py::test_codex_now_priority_and_nonreply_outcome_are_not_silently_ignored` fixture. 이번 native now/Claude 효과 미실행 |
| wake | 둘 다 auto, idle queue의 실제 수신·답 관측 | ledger wake step은 false/not-loaded 보존. queue pickup을 즉시 TUI wake/UI 사람이 봄으로 승격하지 않음. never/now는 이번 native 미실행 |
| files | CLI OS권한 원자료 읽기 / MCP caller-inline, 각각 실제 xsm_files entry read | unknown cap/remote/oversize 등은 기존 fixture 근거만 유지, 이번 native 확장 없음 |
| reply/outcome | 실제 reply_to + succeeded 네 건, 실제 읽은 뒤 request/reply 명시 ACK | 취소/expired/실패 outcome native는 이번 미실행 |
| digest | body/content 동일, canonical 8개 재계산 일치 | endpoint/ID가 달라 full digest는 동일하지 않음 |

이 표면 지정 실험은 A16-01/A19-01의 같은 입력·실제 답·파일 비교 native 표본을 보충한다. A16-03 기능표는 위 관측 셀만 보충하며 전체 기능표/요구조건 종결 판정이나 ledger credit 변경은 하지 않았다. 자연 cold join·formal handshake 성공도 주장하지 않는다(ask의 handshake는 not-started).

## 수량·마찰·종료

- TUI rollout task 시작/완료5/5(초기 준비+업무4). 수신 MCP 호출17: inbox5, ACK4, files4(list2/read2), send4.
- child provider stream은 MCP ask2+ACK2, shell4, 도구 오류0, exit0. native rollout task 이벤트는 시작2/완료1이며 마지막 task_started는 첫 task_complete 직후 기록됐다. 이를 숨기거나 모델 turn1로 축약하지 않는다. 별도 evaluator 재시작은 없으며 마지막 이벤트의 추가 완료/모델 실행 여부는 단정하지 않는다.
- CLI는 기존 본인 세션에서 실제 두 답을 읽은 뒤 별도 CLI ACK를 명시 실행했다. 이는 허용된 host sender 동작이며 다른 actor의 ACK/index를 controller가 보정한 것이 아니다. 상대 body 중계·native meta/capability 조작 없음.
- 수집기 post-exit assertion은 원 실패로 보존한다. 별도 offline checker는 재모델/제품 통신 없이 실제8개 acknowledged canonical record와4개 reply/2개 사본을 대조했다.
- 소유 wrapper/native/proxy/MCP PID의 기록된 generation 모두 종료, private MCP beacon0 확인. 기존 본인 PID9102는 살아 있으며 종료하지 않았다. 기존 전역 세션 조작0.
- frozen315 및 기록한 현재 제품 경로 hash 불변, profile config/hooks/settings guard 동일. 사용자 repo 전체 파일 inventory는 없으므로 전체 파일 불변까지 증명하지 않는다. 실행된 actor 명령에서 사용자 repo 파일 쓰기는 관측되지 않았다.

raw/state는 `/private/tmp/persistent-parity-v3-host-9xxw5alo`에 보존했다. 초기 PID/단계는 실행 중 result.json에 기록했다. `.py/.json/.manifest.json`은 원 실행, `.audit.py/.audit.json/.audit-manifest.json`은 별도 offline 대조와 SHA다. 앞선5조건·원 실패·preflight 산출물은 수정하지 않았다.
