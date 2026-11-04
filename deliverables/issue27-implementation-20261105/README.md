# 승인 복구·이슈 #27 구현 기록

전체 목표는 진행 중이다. 현재 근거는 home별 등록·caller 식별과 승인 복구의 자동 검사다.
명시적 승계·fencing·24시간 전달·상태 이관 및 실제 두 home 시험은 아직 검증되지 않았다.

## 1단계: home별 정체

등록 저장 키에 canonical home을 포함하고 이전 파일을 실제 기록된 home으로만 이관한다.
home을 지정하지 않은 중복 native ID 조회는 어느 한쪽을 고르지 않는다. hook·CLI·MCP,
protocol 소유권, 종료·정리와 handover·worker·team 조회가 정확한 home을 사용한다.
MCP가 자기 home의 기존 등록보다 다른 home의 사본을 먼저 보고 거부하던 문제도 고쳤다.

`identity-consumers-final.log`: 다음 명령의 342개 검사 OK, exit 0.

```bash
python3 -B -m unittest tests.test_xsm tests.test_registry_profiles tests.test_mcp_identity tests.test_worker_project_flow tests.test_handover_service -q
```

`tests/test_registry_profiles.py`의 13개 검사는 별도 임시 상태에서 실행했다. 자동 검사기는
고정 fixture PID·native 답변 등의 합성 자료를 사용하며 실제 사용자 UI·native 모델
시험으로 세지 않는다. strict no-wake 제품 발신 경로에서 정확한 송수신 endpoint와
canonical 원문 저장도 확인했다.

`check-identity-regressions.py`는 임시 복사본의 제품 코드만 수정 전 `66a263c`로 돌려
등록 충돌과 MCP home 선택의 두 결함을 주입한다. 현재 코드의 13개 검사는 통과하고,
두 이전 결함은 각각 AssertionError로 검출했다. `identity-regressions.json`에 대상
소스·검사의 hash를 보존했다. 원 작업 트리는 변경하지 않는다.

테스트 smell 검사에서 지적은 없었고, 새 검사 파일의 5회 프로파일 결과는 wall 약
0.6초·CPU 약 0.4초, WAITING/OVER/FLAKY 없이 예산 내 통과였다.

## 실패와 수정된 시험 조건

- 최초 새 검사에서는 등록 수·호출자·메타데이터 혼입의 실제 결함을 확인했다.
- `identity-consumers.log`, `identity-consumers-fixed.log`에는 기존 fixture가 옛
  파일명을 사용하거나 실제 profile 환경을 지정하지 않아 난 실패를 보존했다.
  해당 fixture를 새 저장 API와 명시된 home으로 이관했다. 동작 assertion은 유지했다.
- 새 발신 검사의 첫 시도는 저수준 API에 문자열 wake 값을 넣어 거부됐다. API의 실제
  boolean 인자로 고쳤다. 이 오류를 제품 발신 결함으로 세지 않는다.
- 반증 검사기의 첫 임시 복사본에는 integrations 카탈로그가 빠져 import가 실패했다.
  성공이나 결함 검출로 세지 않았고, 필요한 카탈로그를 포함한 뒤 정상/결함을 검사했다.
- 테스트 프로파일러의 첫 호출은 `{file}` 자리표시자가 없어 실행되지 않았다.
  올바른 명령으로 실행한 결과만 위 수치로 보고했다.

별도 모델 호출·외부 수신자 연락·사용자 프로필 변경·push·릴리즈는 실행하지 않았다.

## 2단계: 승인 복구와 정식 검사 편입

기존 실패 16건을 [대응표](approval-failure-map.md)로 연결했다. 안내만 검사하던
위치에서 같은 MCP의 native 답변 복구와 실제 도메인 효과·재시도 결과까지 확인한다.
CLI 자체의 승인 검사는 그대로 실행한다. 별도 제품 경로 검사는 9작업·허용/거절
18사례와 추가 회귀를 포함한 27개이며 `permission-positive.log`에 있다.
가짜 native 완료 이벤트·기록을 쓰는 격리 통합 검사이며 실제 UI 시험으로 세지 않는다.

변경 전 숨겨졌던 실제 결함 두 가지를 수정했다.

- 폼 cancel 이후 새 native 답변을 받아들이지 못했다. 답 없는 닫힘만 복구하고,
  닫기 전 답이나 실제 거절·철회·만료된 질문은 재사용하지 않는다. 이전 응답은 이력으로 보존한다.
- 범위 밖 grant는 outside_scope 옵션이 빠져 실제 worker 권한으로 소비할 수 없었다.
  질문과 생성 grant에 해당 범위를 함께 넣고 한 번만 소비되는지 검사했다.

`permission-recovery-fixed.log`는 관련 356개 OK다. 이후 추가한 질문·결과 검사는
별도 receipts/positive 로그에 구분했다. `protocol-gate-first.log`는 누락 묶음을 포함한
정식 gate의 첫 측정이며 exit 0, 66.464초였다. 마지막 추가 회귀 검사 전 측정이므로
전체 목표의 최종 source 검증으로 재사용하지 않는다.

`check-permission-regressions.py`는 native 복구 중단·거절을 허용으로 해석·잘못된
질문 캡처·완료 결과 재사용 중단·gate 누락의 5결함을 임시 복사본에 넣는다.
다섯 검사 모두 AssertionError로 검출했다. 현재 source와 테스트 hash는
`permission-regressions.json`에 있다. 첫 거절 변이는 앞선 방어 분기 때문에 실제
결함 경로에 도달하지 않아 통과했다. 이를 4/5 실패 기록으로 보존하고, 실제 decoder의
거절 해석을 뒤집는 변이로 고쳤다. 검사를 완화해서 검출한 것이 아니다.

`permission-oracle-review.log`에는 테스트 이관 사유를 포함한 보호 검사 결과가 있다.
새 통합 검사 27개는 5회 프로파일에서 파일 단위 10초 예산 내에 통과했고
WAITING/OVER/FLAKY 지적이 없다. 이 예산은 native UI/모델 실행 시간 제한이 아니다.
