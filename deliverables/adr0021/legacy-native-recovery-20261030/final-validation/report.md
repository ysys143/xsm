# ADR21 마지막 통합 소스 전체 회귀

미독 표시·MCP 원문 회수·답 조회까지 구형 사본 영수증을 같은 기준으로 재검증한 최종 소스다. 두 Python이 각각1936개 OK/skip0이며, 검사 뒤178개 입력의 현재 작업 트리 SHA 일치를 확인했다.

| 실행 | 검사 수 | 결과 | 시간 |
|---|---:|---|---:|
| `/usr/bin/python3 -B -m unittest discover -s tests -q` | 1936 | OK, exit0, skip0 | 831.018초 |
| `/opt/homebrew/bin/python3.14 -B -m unittest discover -s tests -q` | 1936 | OK, exit0, skip0 | 534.329초 |

source manifest SHA-256: `ccc3f22a1d65a33ddc76b0ad1abc4966a65664a6e41777d52b70230cd4fd4011`. 변경은 receive.py/handoff.py 및 해당 회귀 검사에 한정한다. 이전1933/1935개 결과와 실패는 각각 당시 소스의 이력으로 보존했다. 의도한 음성 검사 출력과 기존 ResourceWarning도 원 로그에 남겼다.

[요약](summary.json) · [입력 manifest](manifest.json) · [3.9 원 로그](py39.stderr) · [3.14 원 로그](py314.stderr). 같은 소스의 [4개 변이 검출](../final-red-results.json)과 [실제 Opus5.5 마지막 delta 검토](../final-surface-review/review-parsed.json)를 연결한다. 이 결과는 전역G13·다른63개 조건 완료를 뜻하지 않는다.
