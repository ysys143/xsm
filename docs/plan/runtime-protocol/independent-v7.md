# 공개 입력만 받은 v7 독립 참여자

상태: P2의 부분 진척이다. 전체 계획은 미완이다.

사용자가 앞서 승인한 독립 에이전트 실행으로 새 v7 참여자를 작성했다. 입력은
고정cf01df596367768b35a4f7fe060e3d70e78f8eb9의 공개 문서/schema/검사기64개와
운영자 실행 경로였다. 부모 대화는 전달하지 않았고 backend/SDK/이전 참여자
소스 읽기를 금지했다. 실행 파일은 API 호출만 허용했다. 이 지시는 파일시스템
sandbox가 아니며 독립 작성자의 입력 경계 준수 보고와 공개 manifest를 구분한다.

입력 manifest SHA256은2cbb4244c05811a7abcb83869fcde8aa5b340e80cfb375320752a81743368098,
운영자가 동결한 source archive SHA256은
f5493aa7d94f5b389fc80f749f5b15ca2f5eed98cb7d453ca266ff7e2235b535다.
부모는 public packet을 git show로 만들고 archive를 임시 경로에 풀었다.
일반 server와 명시적 model0 owned/error fixture를 분리했다. 실제 모델·계정·
사용자 설정·외부 메시지는 실행하지 않았다.

산출물은 examples/independent-participant/의 participant_v7.py, verify_v7.py,
local_v7_fixtures.py, README-v7.md다. 독립 작성자가 제출한 Python3개 SHA256을
부모 재실행 전에 대조했고 모두 같았다. Backend import 없이 stdlib transport와
주입된 개발용 JSON Schema validator로 공개 결과를 소비한다.

부모가 수정 없이 verify_v7.py를 새 parent-results-cf01 디렉터리로 재실행해 exit0을
확인했다. 정상 독립 시나리오1개와 owned/error 합성 시나리오2개, 공개 예제·fragment
132개, deliberate mutant188개와 validator 제거 감지1개가 통과했다. 공개 검사기
19개 suite의584개 검사도 자체 transport/consumer로 통과했다. 반복 lifecycle을
고유 요구로 합산하지 않으며 이584개를 독립 작성 시나리오 수로 부르지 않는다.

RPC751회에서 operation22개·선언 action30개·wire method16개의 결과를 소비했다.
Missing operation/action은0개다. 부모는 동결된 공개 schema checker로19개 report의
observation742개를 별도로 교차 검증했고 exit0/passed를 확인했다. 원시 challenge는
host 전용0700 결과 디렉터리에 보존하며 모델 결과에 노출하지 않는다.

원시는 `deliverables/protocol-foundation/independent-v7/`다. 작성자의 a–e 초기
실패와 f 최종 결과를 보존했다. 부모 결과는 parent-results-cf01 및 parent-replay.log,
parent-schema.log에 따로 남겼다. 작성자 초기 실패는 validator 입력/fragment·fixture
인자 문제이며 최종0실패와 섞지 않는다.

독립 구현이 지적한 명세 부족은 README의11/실제16 method 수 차이, owned run의
명시적 nonempty work_context 조건 표기, owned/handover의 action별 결과 선택이다.
이 피드백은 후속 공개 계약에서 반영하며 현재 기록만으로 해결됐다고 하지 않는다.
실제 native 모델/UI/lifecycle, Linux 독립 구현, 물리 원격·메신저·설치 전수와
원래 전체 계획은 미완이다. 이 독립 검증을 native 인증으로 승격하지 않는다.

후속 공개 action/default 소비와 부모 재실행은 [별도 기록](independent-v7-followup.md)에
추가했다. 원래cf01 source/hash/실패 증거는 유지하며 후속 수치를 합치지 않는다.
