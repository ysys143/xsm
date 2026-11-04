# 승인 복구·이슈 #27 구현 기록

전체 목표는 진행 중이다. 현재 근거는 첫 단계인 home별 등록·caller 식별에 대한 것이다.
승인 복구 18사례, 명시적 승계·fencing·24시간 전달·상태 이관 및 실제 두 home 시험은
아직 이 기록으로 검증되지 않았다.

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
