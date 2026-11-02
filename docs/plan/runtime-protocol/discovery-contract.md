# 공개 발견 결과 계약 검증

상태: P0/P2의 발견 결과 계약을 추가한 부분 진척이다. 전체 계획은 미완이다.

## 변경

- docs/protocol/discovery-result.schema.json에 xsm_discover의 성공 결과를 정의했다.
  로컬 후보와 authenticated-member 원격 후보를 구분하며 원격 handle의
  generation, 관측 출처/신선도, 부분 실패와 공통 inbox 진단 필드를 포함한다.
- 빈 결과·로컬/원격 혼합·부분 실패의 구조 예제3개를 추가했다.
- 공개 stdio 검사기에 discovery suite를 추가했다. 기존 lifecycle16개와
  발견8개를 검사하며 실제 Git 임시 저장소와 참여자2개를 사용한다.
- 개발용 JSON Schema 검사기가 실제 wire의 xsm_discover 응답도 검증한다.
  서버나 SDK에 JSON Schema 라이브러리 의존성을 추가하지 않았다.

## 실행 증거

`python3 -B scripts/conform-host-protocol.py --suite discovery --capture
--output <report> --command <isolated launcher> protocol serve --stdio`가
24개 검사를 통과했다. discovery-wire-first.json은 실제 stdio 응답23개를
포함하며 그중 발견 결과는4개다. 대상은 이 체크아웃의 서버이며 native runtime,
모델 또는 물리 원격 참여자가 아니다.

`python3 -B scripts/check-protocol-schema.py --wire-trace <report>
--output <validation>`가 실제 응답과 예제를 통과시켰고 발견 결과의 잘못된
구조16개를 거부했다(discovery-schema-final.json). 초안은 공통 inbox_pending
필드를 빠뜨려 실제 응답 검증에 실패했다. discovery-schema-first.log에 보존했고,
공통 inbox 진단 필드4개를 추가한 뒤 같은 wire를 재검증했다.

공개 응답에 비공개 home을 넣는 결함과 관측 source를 지우는 결함은 각각
privacy/provenance 검사에서 실패했다. 정상 서버와 두 결함 검사의 unittest
3개는 통과했다(discovery-conformance-tests.log). 스키마의 비공개 필드 금지와
remote generation 필수를 각각 제거한 변이2개도 검사기가 검출했다
(discovery-schema-mutants.json). 원본 스키마를 변이하지 않고 임시 복사본을 썼다.

기존 NetworkDirectoryTest의 실제 임시 registry/Git/native metadata 파일로
published/same_repository/두 조건 모두의 원격 후보3개도 생성해 스키마를
검증했다(discovery-remote-metadata-fixture.json). Todo의 실제 배열과 출처,
repository mapping도 포함한다. Broker의 machine_name/origin_assurance 표시는
이 시험에서 명시적 fixture로 추가했으며 네트워크 인증 시험으로 세지 않는다.

`python3 scripts/check-protocol.py`는834개(Python497+SDK52+native133+Node152)를
82.957초에 통과했다(discovery-contract-core.log). 독립 mock39/변이14개는
별도 수치다. 실행한 core는 macOS/Python3.14.6이다.

6e9af13b540aa96c5e42408f47b2051ad676493e를 고정한 Linux에서도 같은834개를
Python3.11.2에서68.216초, Python3.14.10에서86.147초로 통과했다.
Source archive SHA256은
2d1938fda6a3f88ef1e816fb6cb2555dded5920ebdf581285a6c24d30fcfd043이다.
두 core 모두 network none/model0/cpu2/memory3g이며 미실행 core0,
VM stopExit=0이다(discovery-contract-linux/result.json 및 환경별 protocol.log).
이는 공개 stdio 발견 검사를 포함한 core이며 native runtime 전체 행렬이나
실제 원격/메신저 검증을 대신하지 않는다.

원시 파일은 모두 deliverables/protocol-foundation/ 아래에 있다. Native profile과
사용자 설정은 변경하지 않았다. 원격 예제는 구조 fixture이며 실제 원격 전달
성공으로 계산하지 않는다. 원격 발견·전체 런타임·다른 operation의 결과 계약과
전체 지원 판정은 승인된 전체 계획의 남은 필수 조건이다.

## 배포 누락과 입력 길이 계약 보완

후속 감사에서 발견 스키마/예제2개가 필수 bundle 목록에 빠진 것을 재현했다.
각 파일을 임시 bundle에서 제거해도 describe용 bundle 생성이 성공했다.
또한 공개 operation 입력의 minLength는 xsm_doc.doc 한 필드에 선언돼 있었으나
서버 validator가 검사하지 않아 빈 경로가 service 호출까지 도달했다.
이는 문서 작업이 성공했다는 뜻이 아니라 구조 검사가 service 전에 작동하지
않았다는 뜻이다. 변경 전 검사2개에서 assertion3건이 실패했다
(protocol-contract-guards-before.log).

두 필수 산출물을 REQUIRED에 넣고 문자열 minLength/maxLength를 service 호출
전에 검사하도록 수정했다. 재현 검사2개는 통과했다
(protocol-contract-guards-after.log). 문자 수는 UTF-8 byte가 아닌 Unicode
문자 수로 세며 한글·비 BMP 문자·결합 문자 경계도 검사했다.

새 core837개(Python500+SDK52+native133+Node152)가 macOS/Python3.14.6에서
82.289초에 통과했다(protocol-contract-guards-core.log). 독립 mock39/변이14는
별도 수치다. 앞 절의834개 Linux 증거는 이 후속 source의 검증으로 소급하지 않는다.
