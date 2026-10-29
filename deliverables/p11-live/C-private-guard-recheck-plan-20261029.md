# C private guard 재검증 계획 (재실행 전 고정)

원 전체 계획 `C-private-plan-20261029.md`의 endpoint·격리·두 controlled 노드·수학 과제·중단 기준을 그대로 적용한다. 제품 선택이나 권한 승인이 아니다.

첫 실행의 native 3회와 정리는 통과했다. 오류 처리에서 inbox 미도착만 재조회하고 native/OS 오류는 즉시 중단하도록 guard를 명확히 한 뒤 동일한 정상 경로를 새 private 팀에서 재실행한다. 첫 결과와 실행 source는 기존 tmp에 보존한다.

- 새 local root: `/private/tmp/p11-C-av3sz_4j`
- 새 peer root: `/private/tmp/p11-C-_n_rujrd`
- 이전 상태·capability는 재사용하지 않는다. 실제 Reason 사용자 팀·계정·프로필은 사용하지 않는다. Native Codex 인증 조건은 앞 비교와 같다.
- 추가 실제 모델 호출은 first/followup/after-reconnect 각 1회, 총 3회다. 기존 성공을 포함한 C 총 실행 수를 6회로 기록한다.
- OS·로그인·fixture 밖 권한 요구는 즉시 중단하고 자기 handle과 새 private state만 정리한다.
- D12 선택·제품 코드·backend 기본값은 변경하지 않는다.
