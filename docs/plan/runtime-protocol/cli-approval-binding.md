# CLI worker 승인 스냅샷 결속

상태: P1/P2의 부분 진척이다. 전체 계획은 미완이다.

CLI approve는 요청 ID와 사용자 답만 보존하고 최종 workers.answer는 같은 ID의
현재 request를 다시 읽었다. 표시와 저장 사이 input/worker scope/summary가
바뀌어도 승인됐다. 수정 전3개 test method에서5개 assertion 실패를 확인했다
(before.log). 이 표본은 임시 기록만 쓰고 실제 명령·모델을 실행하지 않았다.

CLI는 invocation/worker/display fingerprint를 표시 전에 고정한다. 보존 질문에
worker_approval binding을 붙이고 backend의 request lock 안에서 같은 fingerprint를
다시 검사한 뒤 승인한다. 현재 pending request가 없으면 사용자에게 묻지 않고
나중에 생성된 request를 승인하는 경로로 진행하지 않는다. 기존 MCP fingerprint의
기본값과 기존 answer API 호출 의미는 유지한다. Deny의 narrowing도 유지한다.

실제 consent 경로를 연결한 추가 검사는 legacy unbound approve ask가 새 binding으로
업그레이드되는 것을 발견했다(legacy-before.log,1 != 2). Worker approval에 한해
그 unbound 재사용을 금지했다. 이전 기록을 지우지 않고 새 scope를 별도 질문으로
보존한다. 명시적 folder command의 기존 consent 경로는 바꾸지 않았다.

새4개 test method는 input/worker/display 변경3종, 불변 요청의 성공, 같은 ID의
새 input에 따른 binding 변경, 실제 CLI→consent 저장 경로의 legacy 분리를 검사한다.
기존 answer binding/worker approval/MCP 경로를 포함한 focused62개가4.303초에
통과했다(focused.log). Mac core935개가54.641초에 통과했다(core.log, exit0).
독립 mock39/변이14는 별도 수치다. 원시는
`deliverables/protocol-foundation/cli-approval-binding/`다.

실제 사용자/native permission UI와 원래 전체 runtime 행렬은 미완이다. Linux는
후속 고정 source 재실행이다. 이 복구가 전체 P1이나 원래 계획의 완료는 아니다.

## 고정 source Linux 검증

4d92d14feafd78e7c0f7531c4752fcfa01ec2e4f의 archive SHA256은
ffca6c75185d156d24c2fcf367238eaeab2eb5651c71a06586678a135245579c다.
Python3.11.2에서78.294초, Python3.14.10에서102.161초로 core935개를 각각
통과했다. 새 CLI4개와 실제 consent 저장 경로, 기존 native/approval 검사를 포함한다.
두 환경에서 새 errors-fixture27개/frame29개와 offline jsonschema4.26.0 검증도
통과했다. Model0/network none/cpu2/memory3g, 미실행 case0,
미실행 wire/schema0, VM stopExit0이다. 원시는 `cli-approval-binding-linux/result.json`과
환경별 output이다. 실제 사람/native UI와 전체 계획은 미완이다.
