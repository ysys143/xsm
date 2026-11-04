# 승인 복구와 이슈 #27: 변경 전 조사 자료

제품 source는 `66a263c`다. 이 폴더의 자료는 수정 후 통과 증거가 아니다.

- `baseline-tests.json`, `baseline-tests.log`: 격리 홈에서 PersonDecisionTest와
  test_mcp_forms를 함께 실행했다. 106개 테스트·실패 16건·오류 0건, exit 1이다.
  기존 12건과 MCP form의 옛 CLI 안내 기대 4건을 구분한다.
- `registry-collision.json`: 임시 A/B home과 고정 fixture PID로 실제 registry 함수를
  호출했다. A → B → A가 같은 등록 파일을 덮어쓰며 B의 caller가 A로 잡히는 것을
  재현했다. 실제 native 하네스·소켓 배달 시험이나 모델 호출은 아니다.
- `registry-collision-path-label-error.json`: 첫 프로브의 오류를 보존했다.
  canonical 임시 경로와 비정규화 경로를 비교해 A/B 표기가 잘못됐다. 이 파일의
  home 표기와 wrong_sender 판정은 유효하지 않다. 수정 프로브와 합산하지 않는다.
- `registry-call-sites.json`: AST로 찾은 직접 registry lookup/path 호출 33곳,
  11개 파일이다. sid를 독자 키로 쓰는 모든 경로의 전수 목록이라는 뜻은 아니다.

테스트와 프로브는 임시 HOME·XSM_HOME에서 실행했다. 모델·API 키·실제 수신자·전역
설정 변경을 사용하지 않았다. 임시 홈의 fixture 상태는 실행 종료 때 정리했다.

계획은 [승계 설계](../../docs/plan/runtime-protocol/session-profile-migration.md)와
[승인 복구](../../docs/plan/runtime-protocol/approval-recovery-test-alignment.md)에 있다.
