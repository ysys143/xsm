# 송신 결과 공개 계약 검증

상태: P0/P2의 부분 진척이다. 전체 계획은 미완이다.

## 변경과 의미

xsm_send의 단일/그룹 producer result, file/inline materials 및 첨부 준비 오류를
공개 스키마로 정의했다. Public bundle의 필수 산출물에 스키마와 예제를 추가했다.
개발 checker가 실제 성공 응답뿐 아니라 error.data.attachment_error도 검사한다.
서버나 SDK 실행 코드는 바꾸지 않았다.

원격 구현의 기존 status 문자열 전달을 보존하므로 임의 enum으로 좁히지 않는다.
Known status를 별도 annotation에 설명했고 모르는 status는 성공으로 승격하지
않는다. 저장·runtime 도달·정본 ACK·업무 완료를 구분한다. 소비된 원문의 재송신
거부는 원래 ACK를 취소하지 않는다. 그룹 ID와 각 수신 원문 ID도 구분한다.

첨부 오류의 body_sent=false는 frozen manifest까지 없다는 뜻이 아니다.
File reference의 ID/path와 manifest ID의 일치를 schema 외 semantic 검사로
확인한다. Inline fallback에는 가짜 file reference를 만들지 않는다.
전체 의미는 docs/protocol/output-contract.md를 따른다.

## 실행 증거

```sh
python3 -B scripts/conform-host-protocol.py --suite sending --capture \
  --output deliverables/protocol-foundation/send-contract/wire-r2.json \
  --command /absolute/path/to/xsm/bin/xsm protocol serve --stdio
python3 -B scripts/check-protocol-schema.py \
  --wire-trace deliverables/protocol-foundation/send-contract/wire-r2.json \
  --output deliverables/protocol-foundation/send-contract/schema-final.json
```

실제 공개 stdio 서버가 lifecycle16개+송신14개, 총30개 검사를 통과했다.
단일 stored/refused, admission 후 원문 claim 보존, 명시적 ACK 뒤 재송신 거부,
그룹 부분 성공과 각 수신자 ACK 분리, 파일 준비 오류와 frozen 재시도/수신 사본
readback, 명시적 inline fallback을 확인했다. 관측 프레임42개가 checker를
통과했고 그중 xsm_send7개(첨부 오류1개 포함)를 관측했다.

구조 예제6개와 attachment-error 예제1개를 통과했고 잘못된 send 구조15개와
오류 구조2개를 거부했다. Send 필수 metadata를 빼거나 body_sent 제약을 없앤
임시 스키마 변이2개도 검출했다(schema-mutants.json).

Wire proxy가 저장을 native 도달로 오인하거나 그룹 수신 ID를 재사용하거나
첨부 오류에 body_sent=true를 넣는 결함3종을 각각 의도한 검사에서 검출했다.
정상+결함 unittest4개는4.260초에 통과했다. 실제 peer/runtime나 저장 원문은
변이하지 않았다. 임시 HOME/XSM_HOME/native homes와 임시 작업 폴더를 사용했다.

## 최초 실패

초회는 ACK 뒤 resend가 delivered를 돌려줄 것으로 잘못 예상해19개 통과 뒤
실패했다(wire-first.json). 기존 resend guard는 이미 delivered인 원문을 refused로
막고 evidence.ack=true를 유지한다. 원문은 다시 보내지지 않았다. 서버를 바꾸지
않고 기대를 기존 의미에 맞춘 뒤 전체 suite30개를 통과했다. 초회 wire24개가
구조 검사를 통과한 사실(schema-first.json)은 초회 suite 성공을 뜻하지 않는다.

## macOS 전체 핵심 검사와 wire 변이

`python3 -B scripts/check-protocol.py`가 macOS/Python3.14.6에서870개
(Python529+SDK56+native133+Node152)를107.777초에 통과했다(core.log, exit0).
독립 mock39/변이14는 별도 수치다. 이번 정상/결함4개와 bundle 필수 산출물
검사도 이 core에 포함된다.

실제 성공 wire의 reference ID/path를 다른 valid-shape ID로 바꿨을 때 frozen
manifest 결속 검사에서, 실제 error의 body_sent를 true로 바꿨을 때 const
검사에서 CLI checker가 exit1로 실패했다(wire-mutants.json 및 각 log/wire).
두 실패의 이유도 확인해 일반 실행 실패를 검출로 세지 않았다.

## 남은 필수 조건

이 표본은 로컬 일반 protocol participant와 정본 저장/소비 경로다. Native wake,
실제 입력 큐 p95, 사람 UI, 실제 모델, 물리 원격/P2P/SSH, 메신저, 설치 행렬의
검증을 대신하지 않는다. 이번 source의 Linux/core와 다른 operation 결과 계약,
독립 구현의 전체 적합성은 미완이다. 구현 담당 세션이 각 표면을 실행하고
근거에 따라 갱신한다. 승인된 전체 계획의 조건을 생략하지 않는다.
