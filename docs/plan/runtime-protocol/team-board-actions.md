# Team·board 전체 action 결과 계약

상태: P0/P2의 부분 진척이다. 전체 계획은 미완이다.

Team의 list/show JSON 결과를 보존하고 create/add/remove/lead/leave/mute/unmute에
team_change snapshot을 추가했다. 이름·적용 뒤 members/lead·sync_notes와 필요 시
선택 member·caller의 DM muted 상태를 명시한다. Board의 log/decisions JSON을
보존하고 show/set/mute/unmute/sync에 board receipt를 추가했다. Set은 공개 node와
sync_notes, show는 기존 render text, mute/unmute는 change-notice 상태를 반환한다.
두 mute는 서로 다른 기능이다. Snapshot은 현재 roster나 원격 수신 완료 증거가 아니다.

Team/board schema에 각각 x-actionResults9개/7개를 정의했다. Catalog action enum과
예제 action 집합이 모두 같아야 하고 checker가 원 action의 결과 정의를 선택한다.
다른 action의 유효한 결과를 대신 인정하지 않는다. Muted의 값은 mute/unmute에
각각 true/false로 결속한다. Pending/legacy text는 별도로 구분하며 성공을 추정하지 않는다.

격리 stdio team-board-actions37개/frame42개를 실행했다. 실제 호출된 고유
operation/action 조합은16개다. Add/lead는 합성 host가 답했고, 변경 뒤 조회로
membership/lead를 대조했다. Set node를 log와 비교하고 show render를 실행했다.
Team12개 예제/거부12개, board10개 예제/거부19개를 검증했다. Receipt 제거,
잘못된 빈 membership, 다른 contribution body 등 wire 결함4종이 의도한 검사에서
실패했다. 내부 필드를 허용한 schema 변이2종도 검출했다(mutants.json).

Mac/Python3.14.6 core928개(Python535+외부 적합성52+SDK56+native133+Node152)는
84.435초에 통과했다(core.log, exit0). 여기에는 [Linux process generation 복구](owned-process-generation.md)의
새 검사6개가 포함된다. 독립 mock39/변이14는 별도 수치다. Linux는 후속 고정
source 검증이다. 원시는 `deliverables/protocol-foundation/team-board-actions/`다.

결과 구조가 없는 catalog action은 이 두 operation에서0개다. 이는 전체 오류,
실제 사용자/native 알림 UI, remote replication, 독립 구현 적합성 완료가 아니다.
원래 전체 계획의 조건은 유지한다.

## 후속 고정 source Linux 검증

20b70127505c5badb157e408b16fae6a63927fc0의 archive SHA256은
dc455f9dd6d8958ce91372ea995703026d993f2ce6cd842220df7ec412024d51다.
Python3.11.2에서92.007초, Python3.14.10에서119.422초로 core928개를 각각
통과했다. 새 process generation6개와 실제 OpenClaw retained-history 복구를
포함한다. 두 환경에서 team-board-actions37개/frame42개와 owned-fixture30개를
새로 실행하고 두 trace를 offline jsonschema4.26.0으로 검증했다.
Model0/network none/cpu2/memory3g, 미실행 case0, 미실행 wire/schema0,
VM stopExit0이다. 원시는 `team-board-actions-linux/result.json`과 환경별 output이다.
초기489e7ac의3.11 실패는 별도 보존되며 이 고정 source에서 재검증했다.
실제 사용자/native 전체 행렬과 전체 계획은 계속 미완이다.
