# ADR21 최종 validation

최신 통합 소스의 전체 회귀가 Python3.9·3.14에서 각각1933개 통과했다. 검사 뒤178개 동결 입력이 현재 작업 트리와 일치함을 확인했다. 제품 모듈53개·test모듈86개와 실제 release binary를 결속했다. 전역G13 또는 다른ADR63개 조건의 완료를 대신하지 않는다.

| 실행 | 결과 | 검사 시간 |
|---|---|---:|
| `/usr/bin/python3 -B -m unittest discover -s tests -q` | 1933개 OK, skip0 | 562.074초 |
| `/opt/homebrew/bin/python3.14 -B -m unittest discover -s tests -q` | 1933개 OK, skip0 | 374.32초 |

자체 relay 검사는 기존 실제 공식iroh-relay binary를 명시해 실행했다. 음성 테스트의 의도된 JSONDecodeError 출력과 기존 ResourceWarning은 원 로그에 보존했다. 이를 새로운 제품 실패나 경고 없는 실행으로 바꾸지 않았다. 이전1915개 실패와1918개 통과는 각 이전 소스의 이력이다.

추가 반례3개는 정상 코드에서 통과했다. 별도 private 소스 복사본에서 무제한 payload 캐시 복원, 만료 회신의 ACK 은폐 복원, 원문 소유자 확인 제거를 각각 주입하자 대응 검사가 모두 exit1로 실패했다. 최초 owner 변이 준비의 중복 문자열 assertion 실패와 범위 정정도 [반례 결과](red-results.json)에 기록했다. 저장소의 제품/검사 소스는 변이하지 않았다.

[전체 결과](summary.json) · [동결 입력](manifest.json) · [Python3.9 원 출력](py39.stderr) · [Python3.14 원 출력](py314.stderr).

## 과거 전체 색인의 최신성

전체 계획의 `audit-reason-plan.py --structure-only`는 exit1이다. ADR21 착수 전 완료 색인에서 조건29행과 카탈로그·결정·집계·통합의5항목이 현재 소스에 재결속되지 않았다. 이를 수정된 기능의 실패나 최신1933개 검사 실패로 바꾸지 않는다. 과거25개 proven을 현재 제품 전체의 완료 수로 사용하지 않으며 전역G13은 미완이다. [검사 원 출력](historical-ledger-audit.stdout)과 [영향 범위](historical-ledger-audit.json)를 보존했다.
