# 표준 오류 계약과 unknown method 분류 복구

상태: P0/P2의 부분 진척이다. 전체 계획은 미완이다.

[공개 오류 계약](../../protocol/error-contract.md)에9개 code와 retry/unknown outcome,
취소 경계를 정리했다. Error schema는 code/message/optional data를 정의하고
예제9개가 모든 code를 포함해야 한다. Error data의 도메인별 전체 의미를 인증한
것은 아니다. File/send attachment failure는 기존 별도 domain 검사를 유지한다.
세 필수 산출물을 bundle과 누락 거부 검사에 연결했다.

새 오류 검사에서 초기화 후 unknown method를 session 없이 보내면 -32601이
아닌 -32001을 반환했다. Method allowlist 검사보다 bound lookup이 먼저였기
때문이다. 수정 전 단위 검사1개와 실제 stdio가 실패했다(method-before.log,
wire-unknown-method-before.json). 초기화 뒤 method 이름을 먼저 검사하도록
바꿨고 알려진 method의 session 검사와 초기화 전 -32002 우선순위는 보존했다.

Actual stdio errors-fixture27개/frame29개에서9개 code를 모두 관측했다. 고의로
실제 문서 node를 쓴 뒤 RuntimeError를 발생시켰다. -32603의 message는 고정이며
다음 log에는 node가 정확히1개 남았다. Error를 no-effect/rollback이나 자동
재시도로 취급하지 않는다. 실제 모델/native/UI를 실행하지 않았다.

예제9개·거부6개를 검사했다. Stack 필드 허용 schema 변이는 기존 invalid guard가
검출했다(mutant.json). 일반 production candidate는 fixture marker가 없어 주입
시나리오 전에 거부된다. 최초 fixture는 잘못된 class 이름으로 initialize 전에
실패했다(wire-invalid-fixture.json). 성공 수치에 포함하지 않고 보존했다.

Mac core930개(Python536+외부 적합성53+SDK56+native133+Node152)는86.030초에
통과했다(core.log, exit0). 이후 추가한 production candidate 거부 검사와 method
복구 검사2개는 별도0.440초에 통과했다(focused.log). 최신 source의 전체 검사 수는
931개지만 이 Mac 전체 실행을931개로 소급 표기하지 않는다. 독립 mock39/변이14는
별도다. Linux는 후속 고정 source 검증이다.
원시는 `deliverables/protocol-foundation/error-contract/`다.

전체 operation별 error.data, 실제 취소/UI/native/메신저/원격·설치·독립 적합성
행렬과 원래 전체 계획은 미완이다.

초기 Linux sourcecf01df5의3.11은931개/94.911초와 오류 stdio/schema를
통과했다.3.14는 큰 Python 그룹의120초 예산 초과로 실패했고 해당 wire/schema는
전제 미충족이다. 두 환경은 실행됐고 VM stopExit0이다. 이 batch 전체는 failed다.
[Core 그룹 분할](core-partition.md)은 시험 누락/예산 증가 없이 critical path를
분할하며 후속 고정 source에서 Linux를 재검증한다.
