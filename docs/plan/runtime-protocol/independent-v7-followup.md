# V7 독립 참여자: action/default 후속

상태: P2의 부분 진척이다. 전체 계획은 미완이다.

원래cf01 제출과 부모 재실행은 [v7 원본 기록](independent-v7.md)에 보존했다.
같은 독립 작성자에게 backend/SDK 접근 없이 새 공개 입력595d784를 전달했다.
공개64개 파일의 manifest SHA256은
51280af9448961c367d94ea384981d0abdf843f2f857445f0222ad239efca89b다.
명시적 action, catalog/result default와 status의 request_id 조건을 소비하도록
작성자가 자신의 v7 파일4개를 수정했다. 원 코드3개 hash와 제출 결과는 기존
commit/raw 디렉터리에 유지한다.

Consumer는 원 arguments를 요구하고 선언된 기본값만 사용한다. 두 default 선언이
충돌하면 거부한다. Owned create/run/task/listing과 handover show/applied/pending을
구분하고 status는 원 request_id 유무와 일치해야 한다. 예제의 explicit action을
덮어쓰지 않는다. 일부 status 예제의 원 request_id는 공개 입력에 없으므로
validation-only context를 만들고 inferred_context에 표시했다. 이를 원래 request
또는 실제 wire의 근거로 사용하지 않는다.

부모는 제출 뒤3개 Python hash가 작성자 최종 hash와 같은 것을 확인했다. 새 frozen
server에서 수정 없이 parent-results-595로 재실행해 exit0을 확인했다. 독립3개
시나리오, 공개19개 suite/584개 검사, RPC751회, operation22개/action30개의
미실행0개를 확인했다. 예제132개·기존 mutant188개 외에 action/default 양성17개,
음성23개, annotation 보존42개, 구현 변이 검출2개가 통과했다. 공개 checker로
742개 observation도 별도 검증했다. 합성 예제/negative를 실제 실행 수로 합치지 않는다.

작성자의 초기 후처리 감사 오류1건은 결과에 보존했다. 정상 검증과 별도이며 최종
실패0건이다. 자체 작성 시나리오와 공개 검사기가 작성한 반복 lifecycle도 구분한다.
원시는 `deliverables/protocol-foundation/independent-v7-followup/`의 agent-results 및
parent-results-595, parent-replay.log, parent-schema.log다. 실제 native 모델/UI/
Linux·외부 메신저·물리 원격·설치 행렬은 미완이다.

빠른 local wrapper도 action_fixtures를 실행하도록 연결했다. 최신 Mac gate의
관련 결과는 [native probe observer 기록](native-probe-observer.md)에 별도로 남긴다.
Frozen595d784 밖의 새 public native-execution summary나 실제 native probe를
이 후속 검증으로 소급 인증하지 않는다.
