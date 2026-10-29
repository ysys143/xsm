# A16-08 독립 검토 격리 최종 보완

독립 검토 기억 격리 판정: 통과. 실제 actor resume 1턴 + child 3턴 = 4턴, 자동 모델 재시도 0회.

## 실제 세 결과

| 요청 | independent | native CID | 실제 답 | 상태 |
|---|---|---|---|---|
| normal-first | False | `01a1851b-a59f-70a0-bffe-638d08be027a` | `review-secret-32ab1af896d542ef922b89a30244cced` | result-ready |
| independent-review | True | `01a1851b-c62c-7f32-a439-5c3ff6dd9fa4` | `UNKNOWN` | result-ready |
| normal-followup | False | `01a1851b-a59f-70a0-bffe-638d08be027a` | `review-secret-32ab1af896d542ef922b89a30244cced` | result-ready |

동일 private XSM state·동일 worker·같은 실제 sender CID와 work를 사용했다. independent 검토에는 표식을 재제공하지 않았고 실제 답은 UNKNOWN이었다. normal 후속도 표식을 재제공하지 않았으며 원래 native CID에서 자기 표식을 기억했다. 세 child 모두 도구/파일 호출 없이 실제 turn.completed와 outcome=succeeded를 남겼다.

## 신원과 최초 harness 중단

actor A CID `01a1850e-0d38-79f1-b0d7-2becfe1fa5a9`를 정상 resume했다. registry.me의 fresh native PID는 `37120`로 과거 `9651`와 다르며, actor bridge의 실제 부모 PID와 일치한다. 런처 PID `37119`와 native PID를 같다고 비교한 최초 harness 검사가 잘못 중단했다. 이 오류 기록(results.json)은 고치거나 숨기지 않았다. actor를 재실행하지 않고 실제로 갱신된 신원으로 아직 시작하지 않은 child 3개만 실행했다. child 요청/본문/결과/ACK/registry를 수동 보정하지 않았다.

## 공개 표면과 회신 한계

공개 CLI는 --fresh를 지원하며 실제 help probe가 exit 0이었다. 세 child는 공개 workers.run_owned(... independent=True)를 사용했고 executor/reply callback override는 없다. shell/MCP만으로 세 턴을 실행한 것으로 확대하지 않는다. actor가 먼저 종료돼 기본 reply 전송은 성립하지 않았으며 세 요청은 result-ready다. 기억 격리와 실제 native 답은 확인했지만 부모 수신·ACK는 증명하지 않는다.

## profile drift 및 source/current binding

이전 global profile drift를 그대로 보존한다. 이번 actor resume 구간에서도 config.toml hash가 달랐다. harness/기록된 native 도구에 profile 직접 쓰기는 없으나 변경 주체·키와 권한 의미 동일성은 확인하지 못했다. 프로필을 immutable하다고 주장하지 않으며 복구/설정/권한/credential 변경을 시도하지 않았다. child 구간 전후 hash는 check.json에 별도 기록했다.

고정본 manifest 315개와 source/current 파일 hash·선택 함수 AST를 대조했다. 아래 함수 비교를 현재 전체 통합 revision의 실제 재실행으로 확대하지 않는다.

| 파일/함수 | AST 동일 |
|---|---|
| xsm/workers.py/run_owned | True |
| xsm/workers.py/_owned_argv | True |
| xsm/workers.py/_execute_owned | True |
| xsm/workers.py/_owned_native_result | True |
| xsm/workers.py/_reply_owned | True |
| xsm/workers.py/submit_owned | True |
| xsm/owned_requests.py/submit | True |
| xsm/owned_requests.py/reserve | True |
| xsm/owned_requests.py/save_result | True |
| xsm/registry.py/me | True |
| xsm/registry.py/upsert | True |
| xsm/cli.py/cmd_owned | True |
| xsm/mcp.py/owned | True |

## raw·SHA·종결

raw/에는 실제 actor/child stdout·stderr, CLI help를 원본 바이트 그대로 복사했다. check.json의 files에 정확한 경로·SHA256·크기, rows에 세 실제 결과·CID·argv·PID·lstart·상태가 있다. journal/전송 정본은 private 원본 경로/hash에 결속했다. 실행 PID는 제품 기본 executor의 Popen PID이며 내부 native PID와 동일하다고 가정하지 않는다.

체커의 기억·신원·기본 argv·턴 수 검사는 모두 통과했다. native execution 잔존 세대도 없었다. profile drift와 result-ready 회신 한계는 남긴다. 이전 capacity/retirement/4busy 성공은 반복하지 않았고, 이 최종 보완 뒤 추가 실험은 하지 않았다.
