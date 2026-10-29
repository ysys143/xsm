# A17-06 / A17-04 native 대화 수명 평가

**동명 새 CID가 원 대화의 미독을 받지 않았고, 같은 원 CID를 새 PID 세대로 재개해 원문 claim·상관 최종 회신을 수행했다.** 다만 양쪽 모델 모두 실제 `xsm_ack`를 호출하지 않았다. 선택 pair 권한 수명과 추출기 없는 하네스·기록 갱신 행렬도 미충족이므로 두 수용 조건 전체를 proven으로 표시하지 않는다.

[요약/조건별 판정](summary.json) · [실행 조건](plan.json) · [SHA/경로 manifest](manifest.json) · [실행 코드](run.py) · [기록 proxy](proxy.py) · [offline 검사기](offlinecheck.py) · [기존 증거 결속](existing-evidence.json)

## 원 요구와 기존 native 근거

원 [plan A17-06/A17-04](../../../docs/plan/reason-inspired-adrs/plan.json)과 [ADR-0017](../../../docs/adr/0017-directory-and-session-lifecycle.md)은 미독·승인 수명, 추출 불가와 기본 통신, 제목/계획·부분 기록·갱신을 구분한다. 이번 조건은 원 대화 정상 종료→동명 새 CID→원 CID resume의 누락 native 셀이다.

기존 [factory handoff](../native-handoff-factory-20261029-7091030d/report.md)의 실제 초기/검증 resume native stream과 client/server wire를 기존 manifest SHA와 대조했다. 같은 CID와 실제 xsm_ack 호출이 확인돼 기존 중단/회수 proof로 재사용한다. 그 표본의 최초 controller result에는 observer tail race가 남아 있으므로 그것만으로 성공을 추정하지 않았다. source와 강제 중단 조건도 이번 정상 종료 조건과 다르다. 과거 성공을 이번 ACK 성공으로 옮기지 않는다.

## 한 조건의 실제 trace

고정본 `/private/tmp/xsm-final-receipt-frozen-i3u9pms3`, `codex-cli 0.164.0`, 기존 `.codex-3` 구독 runtime의 정상 factory argv/env를 사용했다. 같은 private Git 작업폴더·XSM_HOME 아래에서 native 기본 지침/내장 도구를 유지했다. 실제 thread.started·provider DB CID/cwd와 소유 Codex ancestor PID/lstart/home을 확인한 등록만 수행했다.

동명은 실제 XSM registry의 표시 이름 `archivist`다. 두 native provider 제목은 null이었고 `registry:hook.name`, freshness unknown으로 관측됐다. 사용자 native `/rename` 제목 충돌을 시험한 것으로 확대하지 않는다. 이름을 신원으로 판정하지 않았으며 실제 전체 endpoint와 각 실행 세대를 대조했다.

| 단계 | 실제 신원 근거 | 원 요청/실제 도구 결과 |
|---|---|---|
| 원 archivist | CID SHA `93f3f06f…`; PID 96351, 09:22:39 KST | 미독을 열지 않고 native turn·CLI exit 0 정상 종료 |
| initiator 요청 | CID SHA `396b3527…`; PID 96773 | 실제 discover로 원 archivist 선택. 모델이 `wake=never`를 선택해 질문 1건을 원 full receiver의 MCP inbox에 pending 저장 |
| 동명 새 archivist | 다른 CID SHA `636208de…`; PID 2519, 09:24:34 KST | 실제 xsm_inbox: messages/claims 빈 배열, inbox_pending 0. 원 canonical은 pending/claim 없음 그대로 |
| 원 archivist resume | 원 CID SHA `93f3f06f…`; 새 PID 3953, 09:24:49 KST | 실제 xsm_inbox가 원 ID를 claim. 원 reply_to·outcome=succeeded 회신, sender의 실제 question-status는 final/succeeded |
| 처리 확인 한계 | 실제 xsm_ack 0회 | 요청·회신 canonical 모두 handoff-recorded/claim 보유. 뒤의 빈 inbox는 활성 claim 중 조회이며 ACK 후 중복 억제 증거가 아님 |

원 ID·receiver·identity·전체 digest·message/body는 동명 새 대화 전후와 resume 뒤 동일했다. 새 대화는 과거 canonical이나 상태파일을 직접 읽지 않았고, 원문 재송신·본문 중계·ID 재작성·수동 metadata/ACK/인덱스 보정은 없다. `2+2=5` 주장에 대한 실제 회신은 표준 정수 산술의 결과 4와 4≠5를 근거로 했다. 이번 quiet 요청을 native queue, typed fallback, wake 성공으로 세지 않는다.

## 미확인 승인 수명과 ACK

새 private fixture에는 실제 사용자 consent로 승인된 선택 pair가 없었다. product `collaboration.create`는 실제 affirmative verdict를 요구한다. 임의 verdict를 만들거나 권한 저장소를 쓰지 않았다. 같은 private Git의 기존 기본 scope에서 통신한 것이므로 **새 CID의 선택 pair 권한 비상속/권한 거절은 실측하지 못했다**. 단순히 pair 파일이 없다는 사실을 native 권한 음성으로 세지 않는다. 이 셀은 코디네이터가 실제 승인된 정확한 pair를 확보한 뒤 별도 평가할 미완 항목이다.

resume 모델은 “수신 측 기록 완료”라고 보고했지만 실제 wire에 xsm_ack 호출이 없으며 canonical ACK도 없다. sender 역시 반환된 회신 claim을 ACK하지 않았다. 원문 두 건과 각 claim을 private state에 그대로 보존했다. 제품 안내는 읽은 뒤 명시 ACK를 요구한다([messaging.md](../../../skills/xsm/references/messaging.md)); 이번 표본에서는 그 동작을 모델이 수행하지 않았다. 라우팅/원문 보존 결함으로 단정할 근거는 없고 모델 보고와 실제 처리 상태의 불일치를 남긴다. 종료한 owner 뒤 실제 재회수는 추가 모델 없이 미실행으로 유지한다.

## A17-04 범위

실제 discover에서 native 제목이 없고 summary/todo도 unknown인 상태에서도 질문 저장·resume 수신·최종 회신이 진행됐다. activity는 실제 task_started에서 busy로 추출됐으므로 **추출기를 제거했거나 미지원 하네스였다는 증거는 아니다**. partial metadata의 기본 통신 표본으로만 결속한다. 실제 제목/계획 변경, 잘린 기록·재작성·TTL 갱신 native 행렬은 이번에 실행하지 않았으며 A17-04 전체 미완이다. 기존 B03 native unknown 표본은 SHA로 연결했고 같은 표본을 추가 모델로 반복하지 않았다.

## 계수·검사·보존

- 고유 native conversation 3개, CLI 호출/시작·완료 turn 각각 4회. 같은 CID resume 1회는 의도한 재개이며 자동 모델 재시도는 0이다.
- 실제 등록 setup 4회는 최초 3개 CID 등록과 원 CID 새 PID 세대 갱신 1회다. MCP tools/call 9회, RPC error 0, 실제 ACK 0이다.
- `offlinecheck.py` 기본 실행은 raw 대조와 SHA/구조 검사의 성공(exit 0)만 뜻한다. `--require-complete`는 ACK·선택 pair·추출기/갱신 증거가 없으므로 **exit 1**이 정상이다. raw의 ACK 부재를 전체 성공으로 승격하지 않는다.
- 초기 검사기는 JSON이 아닌 xsm_send 응답과 question 저장 형식을 잘못 가정해 회신을 false-negative로 분류했다. 실제 요청/wire와 question-status final을 대조하도록 평가기만 수정했다. ACK 부재는 파서 문제가 아니라 실제 기록이다. product/raw는 고치지 않았다.
- profile config.toml hash drift가 관측됐고 변경 주체는 미확정이다. 평가기/모델의 profile·auth·권한 편집 명령은 없으며 profile 불변을 주장하지 않는다.
- source 315파일의 manifest SHA가 일치한다. 소유 wrapper/native/proxy/MCP PID와 lstart로 종료를 확인했으며 잔여 소유 process는 0이다. product/ledger/plan 및 제3자 세션은 수정·종료하지 않았다.

raw native 출력·MCP wire·claim/state·현재 실제 rollout은 `/private/tmp/session-lifetime-native-oj91jnav`에 보존했다. 공개물에는 token/ACK 원값이나 인증값을 복사하지 않고 경로·상태·SHA만 남겼다. 추가 native 조건이나 자동 재시도 없이 이 부분 판정으로 종결했다.
