# Worker 승인 발급 결과 계약

상태: P0/P2의 부분 진척이다. 전체 계획은 미완이다.

Grant 결과 schema는 text+grant 발급 snapshot, host question 대기, 기존 text-only
결과를 구분한다. 모델이 표시 문장을 파싱해 권한을 추정하지 않도록 structured
receipt를 사용한다. ID/runtime/cwd/options/asked_by/issued_at/expires_at/single_use는
발급 당시 정보이며 현재 유효성·미소비·runtime 기능 지원을 보장하지 않는다.
실제 소비의 scope/expiry/일회성 검사는 backend가 담당한다.

예제3개는 실제 격리 stdio의 발급/대기2개와 합성 legacy text1개다. 공개 예제에서는
cwd와 표시 text를 fixture용으로 정규화했다. 잘못된 구조10개를 거부했고, 경로형
ID를 허용한 schema 변이1개도 의도한 invalid-result failure로 검출했다(mutant.json).
공통 pending 정의는 question schema와 같아야 한다. 두 필수 JSON을 bundle 목록과
누락 거부 검사에 추가했다. 서버/SDK 의존성은 변경하지 않았다.

공개 `--suite grants --capture`는 lifecycle16개+발급8개, 총24개를 통과했다.
Frame30개를 schema checker로 검증했다(wire-first.json/schema-first.json).
답 저장 뒤 원 작업 retry가 있어야 발급하며 같은 호출의 replay가 같은 snapshot을
보존하고, 거부된 호출은 발급하지 않는지 확인했다. Producer metadata를 없애거나
replay의 ID를 바꾸는 wire 결함2종도 검사한다.

이 표본은 합성 host 응답을 사용하는 격리 protocol participant다. 실제 사람 승인,
worker 시작, full-access/trust-hooks의 실제 적용, remote pairing을 실행하지 않는다.
권한이 있는 OS 사용자/런타임의 실제 동작은 전체 계획의 별도 실행 조건이다.

원시는 deliverables/protocol-foundation/grant-schema/다. 최신 core와 고정 source
Linux 새 stdio/schema는 아래에서 확인했다. 남은 계약과 native/UI/
원격/설치/p95 전체 행렬도 미완이며 구현 담당 세션이 각 표면을 실행해 갱신한다.

Mac/Python3.14.6 core898개(Python519+외부 적합성38+SDK56+native133+Node152)는
74.697초에 통과했다(core.log, exit0). 독립 mock39/변이14는 별도 수치다.
정상 wire·결함2종·bundle 검사의4개도2.019초에 통과했다(focused.log).

## 고정 source Linux 실행

baf9c17371c1d777e4a0558c0207acf0e6f0ae85의 archive SHA256은
d8e416a98e95f9de46c7f600296443f133d0689384e27c89d216ab4ae4ba3d80다.
Python3.11.2에서89.472초, Python3.14.10에서113.382초로 core898개
(Python519+외부 적합성38+SDK56+native133+Node152)를 각각 통과했다.
두 환경에서 새 stdio24개/frame30개를 수집해 offline jsonschema4.26.0으로
검증했고, grant 예제3개/거부10개도 통과했다. 독립 mock39/변이14는 별도 수치다.

Model0/network none/cpu2/memory3g, 미실행 case0, 미실행 wire/schema0,
VM stopExit0이다. 원시는 grant-schema-linux/result.json과 환경별
output/protocol/wire/schema 파일이다. 고정 개발 의존성304개 파일의 SHA256도
같음을 확인했다(validator-audit.json). 실제 사람/worker/native/원격 인증은 아니다.
