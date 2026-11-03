# Operation 결과 계약 범위 — 2026-11-03

상태: 전체 결과 계약은 미완이다. 공개 catalog22개를 실제 encoding 선언과
개발 checker의 operation별 분기에 대조했다. Domain schema가 있는 operation 이름은22개다. Domain schema가 전혀 없는 operation 이름은0개이며,
team9개·board7개 action의 성공/대기 구조를 정의한다. 이 수는
완료율·독립 구현 인증·native 지원률이 아니다.

| Operation | 현재 result encoding | Domain 구조 정의와 남은 범위 |
|---|---|---|
| `xsm_owned` | JSON object | [owned-result.schema.json](../../protocol/owned-result.schema.json) — 생성/작업/목록/취소·복구 projection |
| `xsm_files` | JSON object | [file-result.schema.json](../../protocol/file-result.schema.json) — 파일 조회 구조 |
| `xsm_decision_status` | JSON object | [decision-status-result.schema.json](../../protocol/decision-status-result.schema.json) — lifecycle·취소·입력 승인 진단 |
| `xsm_ask` | JSON object | [question-result.schema.json](../../protocol/question-result.schema.json) — 단일/그룹 질문·회신 구조 |
| `xsm_question_status` | JSON object | [question-result.schema.json](../../protocol/question-result.schema.json) — 개별/그룹/소유 요청 목록 구조 |
| `xsm_discover` | JSON object | [discovery-result.schema.json](../../protocol/discovery-result.schema.json) — 후보/관측/부분 실패 구조 |
| `xsm_publish` | JSON object | [publication-result.schema.json](../../protocol/publication-result.schema.json) — 승인 대기·가시성·거부 |
| `xsm_connect` | JSON object | [question-result.schema.json](../../protocol/question-result.schema.json) — 호스트 승인 대기·선택 거부와 handshake 진행/완료 구조 |
| `xsm_grant` | text envelope + producer metadata | [grant-result.schema.json](../../protocol/grant-result.schema.json) — 발급 snapshot·대기·기존 텍스트 |
| `xsm_send` | text envelope + producer metadata | [send-result.schema.json](../../protocol/send-result.schema.json) — 단일/그룹 metadata와 첨부 오류 |
| `xsm_team` | 조회 JSON / 그 밖 text envelope | [team-result.schema.json](../../protocol/team-result.schema.json) — 9개 action의 조회/변경 snapshot·대기·기존 text |
| `xsm_handover` | text envelope + producer metadata | [handover-result.schema.json](../../protocol/handover-result.schema.json) — 승계 내역·수신 편지·대기·기존 text |
| `xsm_board` | 조회 JSON / 그 밖 text envelope | [board-result.schema.json](../../protocol/board-result.schema.json) — 7개 action의 조회/변경 snapshot·기존 text |
| `xsm_ack` | JSON object | [ack-result.schema.json](../../protocol/ack-result.schema.json) — 성공 ACK 구조 |
| `xsm_inbox` | JSON object | [inbox-result.schema.json](../../protocol/inbox-result.schema.json) — 원문/claim/item 구조 |
| `xsm_link` | text envelope + producer metadata | [scope-result.schema.json](../../protocol/scope-result.schema.json) — 프로젝트 연결/해제 snapshot·대기·기존 text |
| `xsm_join` | text envelope + producer metadata | [scope-result.schema.json](../../protocol/scope-result.schema.json) — 프로젝트 가입/탈퇴 snapshot·대기·기존 text |
| `xsm_reach` | text envelope + producer metadata | [scope-result.schema.json](../../protocol/scope-result.schema.json) — 세션 범위 부여/회수 snapshot·대기·기존 text |
| `xsm_doc` | JSON object | [doc-result.schema.json](../../protocol/doc-result.schema.json) — 6개 action 구조 |
| `xsm_doc_endorse` | text envelope + producer metadata | [endorsement-result.schema.json](../../protocol/endorsement-result.schema.json) — 생성 노드·원본 부모·승인 출처·대기·기존 text |
| `xsm_approve` | text envelope + producer metadata | [approval-result.schema.json](../../protocol/approval-result.schema.json) — 승인/거부 snapshot·대기·기존 text |
| `xsm_decide` | text envelope + producer metadata | [decision-result.schema.json](../../protocol/decision-result.schema.json) — 팀 기록/미기록 답·대기·기존 text |

공통 output schema는 JSON-RPC 성공/오류와 method별 큰 구조를 검사하며, 이
표의 미정의 operation을 의미적으로 검증하지 않는다. Text의 존재만으로
권한·원문 소비·업무 성공을 판정하지 않는다. 예를 들어 승인 작업의 pending
흐름과 decision/request 알림이 문서화돼 있어도 operation별 결과 계약 완료는 아니다.

Domain 구조가 있는 operation도 error 전체·native/remote 표면·실제 사용자
답 검증을 모두 인증한 것이 아니다. 공개 checker의 positive/negative fixture,
독립 participant와 전체 원래 계획의 조건은 별도 근거가 필요하다.

근거는 operations.schema.json의22개 정의, operation_schema.py의
JSON_RESULT_OPERATIONS/operation_returns_json, protocol.py의 결과 wrapper,
scripts/check-protocol-schema.py의 operation별 validator 분기다. 이번 표는 grant-result 산출물을 추가한 기준이며 고정 source와 실행은
[승인 발급 계약 검증](grant-schema.md)을 참조한다.
후속 구현 담당 세션이 새 결과 계약을 추가할 때 해당 operation/action과
실제 wire 검사 근거를 함께 갱신한다.

후속 [그룹 질문 복구](question-group-owner.md)는 ask/status/connect의 실제
공개 경로32개와 소유자·reply claim 결함 수정을 기록한다. 그 복구 커밋 자체는 normative schema를 추가하지 않았다. 이후
[질문 결과 계약](question-contract.md)이 세 operation의 구조를 정의해 본 표에 반영했다.

후속 [개별 worker 승인 결과 계약](approval-contract.md)은 `xsm_approve`의 구조와 합성 worker 요청의 실제 stdio 검사를 추가한다. 실제 사용자/native UI 검증은 별도 미완이다.

후속 [사용자 답 결과 계약](decision-contract.md)은 팀 기록과 팀 없는 답의 structured receipt를 추가한다.

후속 [범위 변경 결과 계약](scope-contract.md)은 link/join/reach의 결과와 실제 송신 정책의 적용·회수 경로를 검증한다.

후속 [문서 승인 결과 계약](endorsement-contract.md)은 endorsement node의 생성과 원본 결속·재시도·거부를 실제 stdio로 검증한다.

후속 [승계 결과 계약](handover-contract.md)은 팀/lead·미독 편지·새 DM 주소 승계와 결과 projection을 실제 stdio로 검증한다.

후속 [Owned 결과 계약](owned-contract.md)은 내부 journal 반환을 공개 projection으로 교체했다. 22개 이름에 schema가 있다는 수치로 전체 action·오류·native/독립 구현 인증 완료를 주장하지 않는다.

후속 [Team/board 전체 action](team-board-actions.md)은 catalog의9+7개 action을 모두 실제 stdio로 호출하고 action별 구조를 검증한다. 오류 전체와 native/UI/원격 의미 인증은 별도다.
