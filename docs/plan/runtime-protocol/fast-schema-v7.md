# 빠른 gate의 공개 schema·독립 v7 검사 통합

상태: P2/P5의 부분 진척이다. 전체 계획은 미완이다.

기존120초 명령에 공개 JSON Schema validator와 독립 v7의 local 예제/결과·wire
변이를 연결했다. 전체 기존 core/native/SDK/Node/mock 목록은 유지한다. 새 wrapper
scripts/check-independent-v7.py는 공개 예제와 고의 오류만 실행하고 실제 server,
모델·UI·네트워크를 실행하지 않는다. 원 독립 Python3개 source는 바꾸지 않았다.

Canonical schema 검사는 request/output와22개 operation 및 action/error 정의와
예제·negative를 검사한다. 독립 v7은 예제132개, deliberate mutant188개와 validator
제거 감지1개를 같은 gate의 두 번째 phase에서 실행한다. 이 수를 기존 unittest
수에 합치거나 전체 native 인증으로 부르지 않는다.

첫 실행은 HOME 격리로 user-site의 jsonschema를 찾지 못해 실패했다(core.log).
제품 환경을 완화하지 않고 설치된 개발 library root만 격리 전에 확인해 validation
명령2개에 명시적으로 전달한다. Offline --validator-path도 같은2개 명령에만
적용한다. Ambient PYTHONPATH/키/네이티브 프로필은 넘기지 않는다. 개발 의존성은
requirements-protocol-dev.txt에 고정했고 제품 server/SDK dependency가 아니다.

Mac/Python3.14.6은935개 unittest+기존 독립 mock39/변이14+공개 schema 검사+
v7 예제132/mutant188/감지1을57.899초에 통과했다(core-final.log, exit0).
이후 추가한 dependency/credential 격리 검사를 포함한 gate focused5개는0.628초에
통과했다(focused.log). 최신 전체 unittest 수는936개이며 앞선 전체935개에 소급
합산하지 않는다. Parent 환경을 그대로 넘기는 source 변이는 의도한 격리 검사에서
실패했다(environment-mutant.log). 독립 작성자 검증과 부모 재검증은
[별도 v7 기록](independent-v7.md)에 유지한다.

원시는 `deliverables/protocol-foundation/fast-schema-v7/`다. Linux는 고정 source에서
전체936개와 dev validator 경로를 다시 실행해야 한다. 전체 native/UI/원격·메신저·
설치 행렬과 원래 계획은 미완이다.

## 고정 source Linux 검증

95484cfa79d0f546da8c0e6e872ef3d0f3b5f779의 archive SHA256은
9aea5e057d419236897d91197cba5057ae30d1616384f6b0970cc6f22643d321다.
Python3.11.2에서81.339초, Python3.14.10에서103.845초로936개 unittest와 기존
mock39/변이14, canonical schema, 독립 v7 예제132/mutant188/감지1을 모두 같은
120초 기한 안에 통과했다. Offline --validator-path /deps는 해당 validation2개
명령에만 전달했다. 두 환경에서 errors-fixture27개/frame29개도 새로 검증했다.
Model0/network none/cpu2/memory3g, 미실행 case0, 미실행 wire/schema0,
VM stopExit0이다. 원시는 `fast-schema-v7-linux/result.json`과 환경별 output이다.
후속 v7 action/default 추가 검사나 더 최신 source의 native 검증은 이 수에
소급 합산하지 않는다. 전체 원래 행렬은 미완이다.
