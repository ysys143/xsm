# 그룹 질문의 소유자 거부와 reply claim 집계 복구

상태: P1/P2의 결함 수정과 공개 경로 검증이다. 전체 계획과 질문 결과 schema는 미완이다.

## 발견 범위와 수정

질문 결과 계약 조사 중 question_groups.wait_for가 다른 대화/없는 그룹의 결과에
없는 waiting_on을 읽는 결함을 찾았다. 외부 소유자의 자식 ID도 거부 전에 poll했다.
공통 question_service.status를 쓰는 CLI·MCP·protocol이 같은 경로를 탔다.
허용되지 않은 본문 노출이나 ACK를 관측한 표본은 아니며, 잘못된 poll 시도와
내부 오류를 실제 regression으로 확인했다.

그룹 레코드의 native 소유자를 자식 poll 전에 검사한다. 없거나 외부 소유자면
기존 scoped not-found/refused 결과를 반환한다. Poll 중 그룹이 사라진 경우도
terminal 상태를 먼저 보고 빠져나온다. 소유자의 terminal transport 결과는
늦은 답을 읽을 수 있어야 하므로 public status만으로 poll을 막지 않는다.

추가 stdio 경로에서는 MCP/protocol 공통 출력이 이미 자식별로 claim한 그룹을
단일 질문처럼 다시 처리해 root claims를 비우는 결함을 찾았다. 수신자 row의
claim과 정본 원문은 남아 있었지만 root aggregate를 쓰는 소비자가 ACK token을
받지 못했다. CLI는 한 번만 claim하는 별도 경로였다. Group에서는 두 번째
single 처리만 건너뛰고 기존 root claim의 출력 추적은 유지했다.

## 실패 재현과 집중 검증

초기 소유자 regression4개는 failures5/errors2로 실패했다(before.log).
외부/없는 그룹 poll, service/CLI/model 경로 및 실제 Connection 경로를 포함한다.
수정 뒤 관련71개가13.692초에 통과했다(focused.log).

MCP/protocol root claim regression2개도 수정 전 각각 실패했다(claims-before.log).
첫 공개 stdio 실행은21개 통과 뒤 root claims=[]를 검출했다(wire-first.json).
Recipient row에는 실제 claim이 있었고 root에는 잘못된 group-ID 결속 진단이 있었다.
이를 고친 뒤 소유자의 terminal 결과 뒤 늦은 답 처리 검사까지 포함한74개가
15.121초에 통과했다(focused-final.log).

두 번째 stdio 실행은30개 통과 뒤 시험 driver가 xsm_connect에 지원하지 않는
wake 인자를 보내 구조 검사에서 거부됐다(wire-r2.json). 서버 API는 넓히지 않고
시험에서 인자를 뺐다. 뒤 handshake2개는 이 실패 표본에서 전제 미충족이다.

새 public-suite unittest의 집계식이 None을 합산해 첫3개 실행과 이어진 core도
TypeError로 실패했다(conformance-tests.log/core.log). 선행 시험 실패 뒤 core를
실행한 표본도 미완으로 보존했다. 일부 병렬 작업은 중단됐고 후속 독립 v5/v6
두 묶음은 미실행이었다. 집계를 boolean으로 고친 뒤3개는3.359초에 통과했다
(conformance-tests-r2.log). 실패한 실행을 삭제하거나 성공 수치에 합치지 않았다.

## 공개 stdio 결과

```sh
python3 -B scripts/conform-host-protocol.py --suite questions --capture \
  --output deliverables/protocol-foundation/question-group-owner/wire-final.json \
  --command /absolute/path/to/xsm/bin/xsm protocol serve --stdio
python3 -B scripts/check-protocol-schema.py \
  --wire-trace deliverables/protocol-foundation/question-group-owner/wire-final.json \
  --output deliverables/protocol-foundation/question-group-owner/schema-final.json
```

Lifecycle16개+질문16개 총32개가 통과했다. Generic frame42개와 이미 정의된
inbox/send/ACK 등 구조는 schema checker를 통과했다. 질문 자체의 domain
schema가 완성됐다는 뜻은 아니다. 외부 그룹을 내부 오류로 바꾸거나 ACK 뒤
답 이력을 지우는 wire 결함2종도 각각 의도한 검사에서 검출했다.

질문/그룹 상태 조회·부분/최종 답·직접 claim ACK·이력 보존·없어진 요청·소유자별
ID 목록·timeout 원문 보존·선택한 peer의 handshake 완료를 공개 요청만으로
확인했다. Native homes나 사용자 설정을 바꾸지 않는 격리 HOME/XSM_HOME/native
homes·임시 작업 폴더를 썼고 실제 모델/사람 UI/메신저/물리 원격은 사용하지 않았다.

## 남은 조건

이번 변경의 두 OS core 조건은 아래 고정 source에서 확인했다.
Ask/status/connect normative 결과 schema와 독립 구현의 전체 적합성, 실제
native/runtime/p95/UI/remote/설치 행렬은 미완이다. 구현 담당 세션이 각 근거를
추가 실행해 갱신한다. 승인된 전체 계획을 이 부분 결과로 축소하지 않는다.

## macOS 전체 핵심 검사

수정한 집계식으로 `python3 -B scripts/check-protocol.py`를 재실행해881개
(Python508+외부 적합성32+SDK56+native133+Node152)가91.310초에 통과했다
(core-r2.log, exit0). 독립 mock39/변이14는 별도 수치다. 이 최종 실행은
최초 core의 미실행/실패 수치와 합산하지 않았다. 전체 계획은 여전히 미완이다.

## 고정 source Linux 핵심 검사

2ad7a23e4fa38da1e14886042415b3c8cbc5faa2을 두 환경에 동일하게 넣었다.
Source archive SHA256은
06779a1bb83f779e08d24739d128038cb3b9a54799f85adafbd0d1bdcafd38e2다.
Python3.11.2에서83.346초, Python3.14.10에서104.917초로 각각881개
(Python508+외부 적합성32+SDK56+native133+Node152)를 통과했다. 독립
mock39/변이14는 별도 수치다. Model0/network none/cpu2/memory3g,
미실행 case0, VM stopExit0이다. 원시는 question-group-owner-linux의
result.json과 환경별 output/protocol.log다. Native runtime/UI/물리 원격/전체
계획 인증으로 확대하지 않는다.
