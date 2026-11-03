# 팀·보드 조회 공개 계약 검증

상태: P0/P2의 부분 진척이다. 전체 계획은 미완이다.

## 계약과 구현

`team-result.schema.json`은 xsm_team list/show의 공개 label projection을,
`board-result.schema.json`은 xsm_board log/decisions를 정의한다. 요청 action으로
정의를 선택한다. 서버와 SDK에 jsonschema 의존성을 추가하지 않았다.
Public bundle의 REQUIRED에 스키마와 예제를 넣어 누락된 설치는 거부한다.

보드 노드의 parser가 보존하는 추가 string metadata는 허용한다. 무결성 검사나
작성자 인증을 구조 스키마로 대체하지 않는다. 결정 조회의 persisted record와
쓰기 직후 transient node/sync_notes를 구분한다. 조회의 읽음 처리 의미는 바꾸지
않았다. 상세 의미는 docs/protocol/output-contract.md를 따른다.

공개 stdio 검사기에 collaboration suite를 추가했다. Lifecycle16개와 팀·보드
검사12개다. 임시 HOME/XSM_HOME/native homes와 임시 작업 폴더에서 동작하며,
xsm 내부 모듈 import나 저장소 파일 직접 조회 없이 공개 요청만 사용한다.
팀 생성/list/show, 빈 board 조회, set/log/filter, synthetic host answer와
명시적 retry를 거친 결정 및 human node 참조를 확인한다.

## 실행 증거

```sh
python3 -B scripts/conform-host-protocol.py --suite collaboration --capture \
  --output deliverables/protocol-foundation/board-contract/wire-final.json \
  --command /absolute/path/to/xsm/bin/xsm protocol serve --stdio
python3 -B scripts/check-protocol-schema.py \
  --wire-trace deliverables/protocol-foundation/board-contract/wire-final.json \
  --output deliverables/protocol-foundation/board-contract/schema-final.json
```

Stdio28개 검사를 통과했고 프레임36개(질문 알림1개 포함)가 스키마에 맞았다.
보드 예제4개 통과·잘못된 구조15개 거부를 확인했다. 부모 배열과 결정 via
제약을 각각 없앤 임시 스키마 변이2개도 checker가 검출했다.
팀 예제3개와 거부9개는 이전 계약을 계속 검사한다.

실제 서버 앞의 결함 proxy가 부모 연결을 지우거나 결정 via를 model로 바꿀 때
각각 `board update links observed predecessor`와
`retry persists host sourced board decision`에서 실패함을 unittest로 확인했다.
원본 서버나 사용자의 상태는 변이하지 않았다.

## 실패와 수정

초회 suite 등록 위치가 세션 생성보다 앞서 UnboundLocalError가 났다
(wire.json). 등록을 실행 단계로 옮겼고, 실행 시작 전 실패에도 activeCheck를
포함하도록 보완했다. Candidate launch가 실패한 경우 임시 stderr를 닫는 검사도
추가했다. 첫 정상 stdio27개 표본은 wire-r2.json에 남겼다.

결함 proxy의 이전 request/response 루프는 응답 뒤 notification을 다음 요청까지
읽지 않았다. 첫 unittest84개 실행과 상태 조회를 추가한 재실행 모두 결함 주입
검사1개가 Empty timeout으로 실패했다. 이는 의도한 결함 검출로 세지 않는다.
Proxy stdout reader가 알림을 즉시 전달하고 응답을 별도 queue에 넣도록 고쳤다.
동시 출력은 lock으로 직렬화한다. 두 표적 결함 검사는 이후2개 모두 통과했다.

## 전체 핵심 회귀 검사

`python3 -B scripts/check-protocol.py`는 macOS/Python3.14.6에서100.880초에
통과했다(core.log, exit0). Python522+Python SDK56+native133+Node152로
총863개다. 독립 mock39개와 변이14개는 별도 수치다. 이번에 추가한 정상
collaboration·두 wire 결함·launch 실패 처리와 bundle 누락 거부도 core에 포함된다.
초기84개 focused 실행의 실패를 이 최종 결과로 지우거나 성공으로 계산하지 않는다.

## 원격 수신 기록 필드 보완

후속 board_sync.receive 감사에서 수신 기록에 from_machine을 붙이는 경로를
확인했다. 기존 원격 수신 fixture가 실제로 저장한 기록1개를 초기 스키마가
additionalProperties 오류로 거부함을 재현했다(remote-record-before.json).
재현 driver 초회는 fixture 초기화 전 import한 모듈을 재사용해 빈 목록을 읽고
assertion에서 실패했다. 이를 정상 표본으로 세지 않았고, 초기화 후 import와
record 수1개 확인을 거쳐 재현했다. 시험은 합성 원격 입력의 로컬 수신 경로다.

옵션 from_machine을 계약에 포함했고 다른 머신의 증언과 로컬 승인을 문서에서
구분했다. 실제 저장 기록1개와 전체 wire36개가 보완된 스키마를 통과했다.
필드를 다시 제거한 변이도 검출했다(remote-record-after.json).
보드 예제는5개·거부16개로 늘었다(schema-remote-final.json).
이는 물리 네트워크 수신이나 원격 승인 신뢰 검증 성공을 뜻하지 않는다.
진행 중 Linux batch는 보완 전5239fe0에 고정되어 이 스키마 변경의 Linux
인증으로 소급하지 않는다. 서버/core 실행 코드는 이 보완에서 바꾸지 않았다.

## 남은 필수 조건

이 표본은 macOS의 실제 stdio 서버와 synthetic host answer다. 사용자 UI·모델·
원격 board sync·native runtime 행렬 성공으로 세지 않는다. Linux의 이번 source,
다른 operation 결과 계약, 독립 구현의 전체 적합성과 승인된 전체 행렬은 미완이다.
구현 담당 세션이 이 계약을 포함한 고정 source의 Linux/core와 나머지 표면을
실행한 뒤 갱신한다. 범위를 생략하거나 전체 계획을 완료한 것으로 판정하지 않는다.
