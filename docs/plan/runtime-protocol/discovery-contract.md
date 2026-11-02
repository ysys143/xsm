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
별도 수치다. 실행한 core는 macOS/Python3.14.6이며 이 변경의 Linux 실행이나
전체 런타임 인증을 대신하지 않는다.

원시 파일은 모두 deliverables/protocol-foundation/ 아래에 있다. Native profile과
사용자 설정은 변경하지 않았다. 원격 예제는 구조 fixture이며 실제 원격 전달
성공으로 계산하지 않는다. 원격 발견·전체 런타임·다른 operation의 결과 계약과
전체 지원 판정은 승인된 전체 계획의 남은 필수 조건이다.
