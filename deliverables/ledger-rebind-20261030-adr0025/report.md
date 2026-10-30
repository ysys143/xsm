# ADR-0025/0026 문서 변경 뒤 완료 색인 재결속 (2026-10-30)

README·README_ko에 DM 정의와 channel 제거 예정 표시를 넣으면서 0.5.0 재결속([ledger-rebind-0.5.0](../ledger-rebind-0.5.0/report.md))의 동결 입력 두 개가 바뀌었다. 감사는 이를 감지해 fixture/process 증명 11칸을 partial로 내렸다(설계대로의 동작). 현재 소스를 다시 동결해 두 Python 전체 회귀를 돌리고 원장을 다시 묶었다.

| 실행 | 검사 수 | 결과 | 시간 |
|---|---:|---|---:|
| `/usr/bin/python3 -B -m unittest discover -s tests -q` | 1941 | OK, exit 0, skip 0 | 744.067초 |
| `/opt/homebrew/bin/python3.14 -B -m unittest discover -s tests -q` | 1941 | OK, exit 0, skip 0 | 468.868초 |

[요약](summary.json) · [입력 manifest](manifest.json) · [동결 기록](freeze.json) · [3.9 로그](py39.stderr) · [3.14 로그](py314.stderr)

재생성한 색인은 재결속 전과 조건별 판정·증거 항목이 같다: proven 4, partial 95, missing 0. 제품 코드와 테스트는 바뀌지 않았다. 전체 계획 완료나 전역 G13을 뜻하지 않는다.
