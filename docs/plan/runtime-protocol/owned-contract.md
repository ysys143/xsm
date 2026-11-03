# Owned 공개 결과 계약과 내부 기록 노출 복구

상태: P0/P2의 부분 진척이다. 전체 계획은 미완이다.

Owned 모델 frontend는 create의 worker record와 run/status의 journal을 그대로
반환하고 있었다. 격리 MCP의 두 재현 검사는 수정 전 실패했다(before.log).
create는 home/owner/parent_native, run은 owner/sender/events/reservation/send_token을
직접 반환했다. Worker/context/result/cancellation에도 내부 신원·프로세스·토큰이
포함될 수 있는 경로다. 진단용 CLI/backend 기록과 그 위의 정본 실행 처리는 유지했다.

공통 owned_service.public_result를 모델 직렬화 전에 연결했다. 생성·작업·목록,
worker/context/result/send_evidence/cancellation/capacity/recover_at의 필드를
각각 명시한다. Native profile home, owner/sender, 예약·전송 토큰, child/process,
provider descriptor를 반환하지 않는다. 실제 inbox ACK claim은 별도 기존 계약이다.
관련 MCP 검사12개가 수정 후 통과했다(interfaces-after.log).

공개 schema는 생성/작업 snapshot/목록/not-found·refused/transient unknown을
구분한다. Queued는 persisted=true/accepted=false/slot_occupied=false이며,
reply-ready 상태는 result/reply ID, reply-stored·sent는 해당 transport evidence를
요구한다. Side effects exactly once를 주장하지 않는다. Schema/예제를 필수
bundle과 누락 거부 검사에 연결했다.

`owned-fixture`는 합성 native executor/publisher와 실제 stdio/journal을 쓴다.
일반 서버는 모델0 선언이 없어 create 전에 검사에서 거부된다. 합성 fixture만
격리 capacity marker를 읽어 queue/cancel 뒤 별도 요청의 실행을 허용한다.
Stdio30개/frame31개, 예제8개·잘못된 결과15개를 검증했다. Status/refused,
caller history, queue/cancel, result/retry/reconcile를 실행했지만 native 실행이나
실제 회신 발송을 인증한 것은 아니다. Profile 누출·result body 제거 결함도 검사한다.

첫 fixture는 catalog에 없는 protocol-fixture runtime을 요청해 create 전에
거부됐다(wire-invalid-fixture-runtime.json). 이후 catalog의 codex와 명시적
model0 candidate marker를 사용하고 실행기/발송기는 합성으로 고정했다.
원시는 `deliverables/protocol-foundation/owned-contract/`다.

22개 operation 이름 모두 domain schema가 생겼지만 team/board의 남은 action,
전체 오류·native/독립 구현 적합성·메신저·설치 등 원래 계획은 미완이다.

Mac/Python3.14.6 core920개(Python529+외부 적합성50+SDK56+native133+Node152)는
78.582초에 통과했다(core.log, exit0). Internal profile 누출·result body 제거의
wire 결함2종과 일반 서버의 fixture 실행 거부도 통과했다. Internal journal
필드 허용 schema 변이를 검출했다(mutant.json). 독립 mock39/변이14는 별도다.
Linux는 후속 고정 source 검증이다.

초기 Linux source489e7ac의3.11 core는 별도 OpenClaw process generation 비교에서
실패했고 wire/schema는 전제 미충족이다.3.14는920개/117.256초와 wire/schema를
통과했다. 실패 원인·영향 범위와 후속 검증은 [프로세스 세대 복구](owned-process-generation.md)를
따른다. 이 초기 Linux batch 전체는 통과로 표시하지 않는다.

## 후속 고정 source Linux 검증

20b70127505c5badb157e408b16fae6a63927fc0의 archive SHA256은
dc455f9dd6d8958ce91372ea995703026d993f2ce6cd842220df7ec412024d51다.
Python3.11.2에서92.007초, Python3.14.10에서119.422초로 core928개를 각각
통과했다. 새 process generation6개와 실제 OpenClaw retained-history 복구를
포함한다. 두 환경에서 team-board-actions37개/frame42개와 owned-fixture30개를
새로 실행하고 두 trace를 offline jsonschema4.26.0으로 검증했다.
Model0/network none/cpu2/memory3g, 미실행 case0, 미실행 wire/schema0,
VM stopExit0이다. 원시는 `team-board-actions-linux/result.json`과 환경별 output이다.
초기489e7ac의3.11 실패는 별도 보존되며 이 고정 source에서 재검증했다.
실제 사용자/native 전체 행렬과 전체 계획은 계속 미완이다.
