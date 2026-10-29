# 완료 색인의 현재 소스 재결속 (2026-10-30)

이전 색인의 proven 25건은 doctor-privacy v2(1697) 소스에 묶여 있었다. 그 뒤 ADR21 통합으로 제품 모듈 15개가 바뀌어, 색인을 다시 계산하면 25건이 모두 partial이 되고 구조 감사는 색인 오류 34건으로 실패했다.

## 실행

현재 HEAD `5773ca2`의 추적 파일 184개(제품 Python 53개·검사 모듈 87개)와 엔진 `f17f03fa…`를 동결해 두 Python 전체 회귀를 돌렸다.

| 실행 | 검사 수 | 결과 | 시간 |
|---|---:|---|---:|
| `/usr/bin/python3 -B -m unittest discover -s tests -q` | 1941 | OK, exit 0, skip 0 | 809.826초 |
| `/opt/homebrew/bin/python3.14 -B -m unittest discover -s tests -q` | 1941 | OK, exit 0, skip 0 | 530.990초 |

같은 절차의 첫 실행(`aef2e76`)은 두 Python 모두 1941개 중 6개가 실패했다. Orca 터미널에서 실행해 `test_owned_interfaces`가 상속된 pane 표식을 지우지 않은 기존 격리 결함이 드러난 것이다. `3cbdd59`가 형제 검사와 같은 방식으로 고쳤고, Orca 환경에서 수정 전 실패(failures 1, errors 5)와 수정 후 7개 통과를 확인했다. 원 실패 로그는 보존하지 않았다.

[요약](summary.json) · [입력 manifest](manifest.json) · [동결 기록](freeze.json) · [3.9 로그](py39.stderr) · [3.14 로그](py314.stderr)

## 결속 규칙

- 이 회귀는 구체 반례가 있는 fixture/process 셀만 다시 묶는다: A18-03, A18-07, A22-06, A23-02, 공유 MCP 격리 fixture(A17-02, A19-02, A23-03).
- 이전 소스에서 실행한 native/UI/physical 증거는 현재 소스의 증명으로 옮기지 않는다. 21건의 이전 proven은 native 수준 때문에 partial로 남는다.
- ADR21 실측 E3/E4/E6/E10/E13/E15와 최종 Opus 검토는 범위 한정 partial 증거로 등록했다. 모두 이후 receive/handoff 변경 전 소스다.
- `scripts/audit-reason-plan.py`는 이 회귀의 입력에서 제외한다. 어떤 검사도 이 파일을 읽지 않으며, 감사 자신은 `--self-test`와 `--predicate-self-test`로 검사한다.

## 결과

| 항목 | 이전 색인 | 재결속 후 |
|---|---|---|
| proven | 25 | 4 (A18-03, A18-07, A22-06, A23-02) |
| partial | 71 | 95 |
| missing | 3 (A21-04/06/07) | 0 |
| 구조 감사 | 색인 오류 34건, exit 1 | exit 0 |
| 환경 | physical-native-peer·different-NAT·self-hosted-relay missing | 각 partial |

- `--self-test`: 색인 변이 72개 검출.
- 새 재결속 변이 11개 검출: 한 Python만, skip, 실패 exit, 검사 수 불일치, 로그 SHA, manifest bytes, 다른 엔진, 전체 완료 주장, 실행 뒤 소스 변경, 조건 의존 파일 변경, 구체 반례 소실.
- `--predicate-self-test` 전체 실행은 기존 `directory-extraction-closure-audit.json` 원 predicate에서 멈춘다. 이번 변경 전 스크립트(`1e0159e`)도 같은 지점에서 멈추므로 기존 문제이며, 이번에 고치지 않았다. 새 변이 11개는 그 블록만 따로 실행해 확인했다.

전체 감사는 109개 blocker로 exit 1이다. 전체 계획 완료나 전역 G13을 뜻하지 않는다.
