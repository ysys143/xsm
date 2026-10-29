# doctor privacy 전체 회귀 — 단일 시험 홈 결속 수정

결과: **제품 가드를 유지하고 SafetyTest 한 메서드의 fixture만 수정했다.** 외부 CLAUDE_CONFIG_DIR를 명시한 원 테스트 red, 수정 green, 결속 제거 변이 red를 두 Python에서 확인했다. 다른 검사와 full 회귀는 실행하지 않았다.

## 원인과 영향

`SafetyTest.test_a_parent_goodbye_reaps_once_its_process_is_gone`은 Claude 포인터를 self.tmp에 등록했지만 SessionEnd의 홈을 명시하지 않았다. 상속된 CLAUDE_CONFIG_DIR가 다른 홈이면 `registry.mark_ended`의 정상 홈 가드가 종료를 거절해 ended=None을 반환한다. `reap_detached(None)`이 orphans→registry.records→identity.lstart→probe.command로 들어가면 공용 subprocess 모듈의 Popen mock이 None을 반환한다. 실제 관측 오류는 **AttributeError: 'NoneType' object has no attribute 'communicate'**다.

제품의 잘못된 홈 종료 거절을 약화시키지 않았다. 이 실패는 doctor privacy projection이 아니라 시험의 환경 결속 문제다.

수정은 해당 메서드의 기존 SessionEnd/Popen mock 구간에 `mock.patch.dict(os.environ, {"CLAUDE_CONFIG_DIR": self.tmp})`를 추가한 것뿐이다. 원래 reap --after-pid 명령 1회 assertion과 Popen mock은 유지했다. AST에서 이 메서드를 제외한 파일 전체가 같음을 대조했고, 모든 제품 xsm 파일의 수정 전후 SHA도 같다. 새 테스트/공통fixture/다른 제품 source는 추가하거나 수정하지 않았다.

## 기존 실패 보존

기존 전체 회귀는 각1700개 중 errors=1 실패였으며 이를 성공으로 고쳐 기록하지 않았다. 원 로그는 그대로 있다.

| Python | 원 full 회귀 로그 | SHA-256 |
|---|---|---|
| 3.9.6 | `/tmp/p13-doctor-privacy39.log` | `21ff46126d25b4d243245c10359bb338fd82f52fa419920c9e8ee400e434df9a` |
| 3.14.6 | `/tmp/p13-doctor-privacy314.log` | `3dc03f678d148bef2e29ecbbd5323ac64320b697e5fa915d21a4bd925b6f5d6d` |

## 한 테스트의 검증

| 단계 | Python3.9.6 | Python3.14.6 |
|---|---|---|
| 원 테스트, 외부 home 명시 | 1 test / errors=1 | 같음 |
| 수정, 동일 외부 home 상속 | 1 test / OK | 같음 |
| 새 결속만 제거한 private mutant | 1 test / errors=1 | 같음 |

변이의 테스트 파일 bytes는 원래 파일과 정확히 같고 오류도 같은 NoneType.communicate 경로다. 실제 workspace의 수정을 제거했다가 되돌리는 방식은 쓰지 않았다.

두 interpreter에서 실행한 selector는 동일하다.

```text
/usr/bin/python3 -B -m unittest tests.test_workers.SafetyTest.test_a_parent_goodbye_reaps_once_its_process_is_gone -v
/opt/homebrew/bin/python3 -B -m unittest tests.test_workers.SafetyTest.test_a_parent_goodbye_reaps_once_its_process_is_gone -v
```

red/green/mutant 모두 subprocess 환경의 CLAUDE_CONFIG_DIR를 **등록 홈과 다른 private scratch 홈**으로 명시했다. green만 테스트 내부에서 등록 홈 self.tmp를 결속한다. 실제 계정 홈을 바꾸지 않았다. [JSON](doctor-privacy-test-isolation-fix.json)에 각 명령의 cwd/env override·exit·출력 파일/SHA·source SHA와 작은 diff를 수록했다. 원 테스트와 새 실행 원문은 private evidence root에 보존했다.

제품 source와 기존 증거·plan/ledger는 수정하지 않았다. 새 모델·실제 reaper 실행·다른 검사·full 재실행은0이다. 이번 결과는 **이 한 테스트의 두 Python 환경 격리 검증**이며 전체 회귀 통과나 새 freeze 결과가 아니다.

## 현재 파일 SHA

- `tests/test_workers.py`: `edd42948d03acc04e020ef9bf54e76632ac586b001f07ead6800194a694e9619`
