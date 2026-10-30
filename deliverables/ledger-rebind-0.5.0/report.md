# 0.5.0 릴리스 소스의 완료 색인 재결속 (2026-10-30)

문서 재구성 커밋 `1e85bc1`과 0.5.0 버전 매니페스트를 합친 릴리스 소스를 동결해 두 Python 전체 회귀를 돌렸다. 이전 재결속([ledger-rebind-20261030](../ledger-rebind-20261030/report.md)) 뒤 바뀐 검사 입력은 계획 경로를 적은 `tests/test_crash_boundaries.py`의 주석, 플러그인 매니페스트 세 개의 버전, README 두 개다.

| 실행 | 검사 수 | 결과 | 시간 |
|---|---:|---|---:|
| `/usr/bin/python3 -B -m unittest discover -s tests -q` | 1941 | OK, exit 0, skip 0 | 744.400초 |
| `/opt/homebrew/bin/python3.14 -B -m unittest discover -s tests -q` | 1941 | OK, exit 0, skip 0 | 471.973초 |

[요약](summary.json) · [입력 manifest](manifest.json) · [동결 기록](freeze.json) · [3.9 로그](py39.stderr) · [3.14 로그](py314.stderr)

계획 폴더가 `docs/plan/collaboration/`으로 옮겨졌다. 감사 스크립트(`scripts/audit-collaboration-plan.py`)는 기록에 남은 옛 경로(`docs/plan/reason-inspired-adrs/`)를 현재 위치로 대응시켜 읽고, 과거 동결본 안에서는 옛 경로를 그대로 읽는다. 재생성한 색인은 재구성 전과 조건별 판정·증거 항목·환경 상태가 모두 같다: proven 4, partial 95, missing 0. `--self-test`는 색인 변이 72개를, 재결속 변이 시험은 11개를 검출했다.

전체 계획 완료나 전역 G13을 뜻하지 않는다.
