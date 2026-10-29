# G03 질문·비동기 인터페이스

- 상태: **passed — B03 로컬 계약**. Opus 1차 지적을 수정하고 코디네이터가 재현·영향 검사·최종 전체 회귀로 종결했다.
- 진입: G01/G02 passed. 기존 send의 wait는 전달 영수증 의미를 유지한다.
- 기준: spec P03, A16-01–05/07, ADR-0024의 A24-05/06 로컬 부분.

## 구현 계약

| 의미 축 | 실제 응답 필드 |
|---|---|
| 원 요청 | id, purpose; 내부 full native sender/target·본문·digest |
| 전달 관측 | delivery_evidence; send_evidence는 송신 시점 snapshot |
| 실제 답 | replies(원 reply_to와 양끝 native 신원 검증) |
| 부분/최종 | final, final_outcome; 명시 outcome 없는 답은 부분 회신 |
| 대기 종료 | wait_end_reason: reply/timeout/cancelled/client_closed/refused/error |
| 회수 | recover_at.cli 및 recover_at.mcp; 저장된 요청이 없으면 null |
| 핸드셰이크 | pending/reply_received/declined/completed; 최신 명시 succeeded만 완료 |

CLI `ask`, `question-status`, `connect`와 MCP `xsm_ask`, `xsm_question_status`, `xsm_connect`가 같은 questions 서비스를 쓴다. 구현 기본값은 비동기 wait=0이며 MCP의 명시 대기는 최대 60초와 실효 예산을 표시한다. 이는 구현 담당자가 정한 공개 계약이며 사용자에게 API 철자·숫자 승인을 받았다고 기록하지 않는다.

동일 ID 재호출은 본문/양끝/목적이 바뀌면 거절하고 새 전송을 하지 않는다. connect의 ID 재개는 저장된 목적·대상을 확인해 query/wait만 하므로 새 버전의 기본 핸드셰이크 문구로 옛 본문을 재생성하지 않는다.

## 수신·MCP 입력

- authenticated hook와 inbox 양쪽에서 답 인덱스를 기록한다. unchecked/provisional 발신자를 상관된 답으로 승격하지 않는다.
- 기다릴 때는 checked reply copy만 관찰한다. 일반 inbox 메시지를 claim/delete하지 않는다. 취소는 상대 task 취소나 재실행이 아니다.
- 현대 송신기는 질문에 실제로 결속된 회신만 별도 full-body cache로 남긴다. 옛 수신 훅이 일반 사본을 먼저 지워도 checked 수신 경로가 이를 인덱싱하고, 인덱스 저장 후 중복 cache만 제거한다. blocked/held 영수증을 우회하지 않는다. 송신 후 cache 실패를 미송신으로 보고하지 않는다.
- stdin reader는 하나이며 JSON 입력을 queue에 넣는다. 실제 서비스 호출은 한 실행 스레드에서 요청 ID로 분배한다. 양식 중 도구·ping·취소를 처리하고 caller context와 consent 보고 상태를 호출별로 저장·복원한다.
- tools/list는 static이며 inbox/status 도구를 숨기지 않는다. 원격 discovery, 첨부, 독립 wake 제어를 성공으로 꾸미지 않는다.

## 기능 표

| 기능 | CLI/MCP | 실제 효과/한계 |
|---|---|---|
| 실제 질문과 늦은 회신 | 같은 서비스/원 ID | 영수증만으로 답변 성공 아님 |
| reply_to/outcome | 기존 send와 양쪽 스키마 | outcome은 reply에만 허용; succeeded/failed를 구분 |
| priority | 같은 입력·target capability | Claude next/now 실제 UDS frame, Codex next; 미지원 now는 명시 거절 |
| wake | 독립 제어 미지원 | transport의 기존 wake 정책과 관측 evidence는 유지 |
| attachments | 미지원 명시 거절 | P06 소비 부분 미완 |
| sandbox 답장 | MCP 우선 | 공통 지침·수신 task context에서 CLI 실패를 선행 조건으로 안내하지 않음 |

## 실행 증거

- 실제 CLI: 요청 dd65874b71964a87는 timeout으로 반환된 뒤 같은 ID의 조회에서 P03-LIVE-ANSWER(final)를 회수했다.
- 실제 후보 기반 연결: candidate eb8eb81e…를 선택해 f06b2a8ffad0499c 핸드셰이크를 보냈다. 접수/timeout 시 pending, 실제 peer의 succeeded 회신 뒤 completed였다.
- 실제 Claude MCP: 1차는 old sender/hook 조합에서 native 채팅에는 답이 왔지만 query는 pending이었다. 수정 후 현대 CLI 송신을 지정한 재평가에서 ask 38899b81072f407d가 P03-MCP-V2-ANSWER를 반환했고 status에서도 같은 reply ID bcc9892412fb4355를 반환했다. 권한 거절/설정 변경 없음. 레거시 모든 조합의 보편 성공으로 확대하지 않는다.
- 실제 workspace-write Codex: 원 요청 f83479423d694988를 xsm_inbox MCP로 받고 첫 송신부터 xsm_send MCP로 5e3906ab76b94834를 보냈다. 부모가 같은 ID의 query에서 P03-SANDBOX-ANSWER를 회수했다. 셸 송신 시도 0. 평가 prompt에 MCP 경로를 명시한 조건이며, 최종 수신 안내문의 동일 기본 경로는 별도 경로 검사로 대조했다. clean install 기본 선택은 G10 종결 셀이다.
- 실제 Codex 평가의 처음 임시 MCP 설정은 비기본 CODEX_HOME을 빠뜨려 등록 거절됐다. factory installer와 같은 profile env를 명시한 설정에서 통과했다. 신원 가드를 우회하거나 다른 세션을 추정하지 않았다.
- 실제 현재 Codex의 MCP 양식은 G02에서 approval_policy=never의 unshown decline을 관측했다. 사용자 거부로 확정하거나 승인으로 적용하지 않는다. 이 조건에서는 비동기 ID/후속 회수 경로를 사용한다. 중첩 양식/입력 분배는 실제 OS stdio client fixture로 검증하고 실제 사람의 중첩 UI 조작 성공으로 세지 않는다.

기계 증거: `deliverables/b03-live/`. kernel UDS priority, 실제 OS stdio ping/cancel/late reply, nested form의 응답 순서·신원·consent 상태 격리, private index 소유권과 cache 실패는 tests/test_question_interfaces.py, test_mcp_wait_process.py, test_mcp_dispatch.py, test_questions.py에서 실행한다.

## 종결 범위

G03은 이 로컬 질문 계약과 지원/하향 동작의 게이트다. A16-03/04/05/07의 G04/G06/G07/G08/G10/G13 후속 셀, 원격과 모든 혼합 버전 조합을 통과로 세지 않는다. 설치/owned worker/claim-ack/원격은 원래 단계에 남는다.

## Opus 검토 1차와 수정 라운드

1차 판정은 수정 필요였다(`/tmp/b03-opus-review.log`). 클라이언트가 취소 응답을 버리면 자동 생성 ID를 잃는 문제를 고쳤다. `question-status`/`xsm_question_status`의 ID를 생략하면 자기 native conversation의 요청 목록만 반환한다. 목록 조회는 송신하지 않으며, model/user가 UUID를 미리 만들도록 의무화하지 않았다.

실제 OS stdio 검사에서는 자동 ID로 질문→ping→cancel→원 취소 응답 본문을 버림→ID 없는 새 RPC로 자기 요청 목록 회수→해당 ID로 늦은 답 조회를 실행한다. 다른 CID/home의 요청을 목록으로 노출하지 않는다.

낮은 심각도 지적도 반영했다. 수신 gate의 held/blocked/error는 송신 snapshot이 아니라 현재 원장·영수증에서 읽어 대기 종료 사유로 반환한다. 입력/ping/cancel pump는 계속 처리하되 무거운 회신 확인은 0.2초 간격·공유 probe 예산을 사용한다.

추가 통합 검사에서 원래 질문의 상대가 아닌 peer가 legacy ledger outcome만 종결하지 못하도록 실제 수신 경로를 맞췄다. 일반 peer 메시지는 도착하지만 질문의 답/종결로 승격하지 않는다. 이 가드를 제거하는 변이는 테스트를 실패시켰다.

IC02와 동일하게 질문 body digest에 공용 NFC/개행 정규형을 사용하고 원문은 따로 보존한다. 최초 전체 회귀의 스킬 길이 90줄 제한·구 0.4.14 도구 14개 fixture 지적은 지침을 reference로 줄이고 역사적 도구 목록을 고정해 수정했다. 관련 26개는 통과했다. 최종 전체 회귀는 별도 기록한다.

## 최종 판정

Python 3.14.6: Ran 1305 / OK (197.353s), Python 3.9.6: Ran 1305 / OK (221.689s). 로그 `/tmp/b03-close314.log`, `/tmp/b03-close39.log`. 두 실행 사이 제품·테스트 소스 hash 변경 0개를 대조했다. `deliverables/b03-live/closure.json`에 지적별 검사와 source hash를 결속했다. Opus의 첫 판정은 수정 필요였으며 이를 Opus 통과로 바꾸어 인용하지 않는다. 최종 기술 판정자는 코디네이터다. 후속 단계의 종결 셀과 전체 70개 완료는 별개다.
