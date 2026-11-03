# 질문·상태 조회·handshake 결과 계약

상태: P0/P2의 부분 진척이다. 전체 계획은 미완이다.

## 정의한 범위

question-result.schema.json은 xsm_ask, xsm_question_status, xsm_connect의
단일 질문·그룹 집계·거부/없는 그룹·소유 요청 목록·연결 선택 거부를 정의한다.
x-operationResults로 요청 operation에 맞는 정의를 고른다. 명세/스키마/예제를
public bundle의 REQUIRED에 추가했다. 독립 클라이언트가 내부 모듈을 import하지
않고 읽을 수 있으며, 서버/SDK에 jsonschema 의존성을 넣지 않았다.

Reply의 home_id와 remote machine, explicit claim, partial/final outcome,
wait budget 및 Gateway 원격 증거를 구분한다. Packet/file manifest 구조도
포함하며 공통 claim/file/material 정의는 다른 schema와 같아야 한다.
초기 send claim 뒤 중단된 기록의 send_evidence에는 id가 없을 수 있다.
소유자/범위/세대/권한을 schema가 인증한다는 뜻은 아니다.

개발 checker는 group counters/flattened replies/claim aggregate, reply-ID 중복,
terminal history와 handshake 상태, remote final packet의 request/scope/metadata,
file reference/manifest/request/body hash 결속도 확인한다. TLS·현재 native 세대·
전체 fingerprint/복사 bytes/quota/expiry는 Gateway/file runtime의 별도 검증이다.
전체 의미와 경계는 docs/protocol/question-results.md에 적었다.

## 증거

```sh
python3 -B scripts/check-protocol-schema.py \
  --wire-trace deliverables/protocol-foundation/question-group-owner/wire-final.json \
  --output deliverables/protocol-foundation/question-contract/schema-current.json
```

이전 실제 stdio source의42개 frame을 새 operation별 정의와 결속 검사로 통과시켰다.
예제22개는 실제 격리 stdio11개, 실제 local Gateway3개, 합성 구조8개다.
Gateway fixture는 private HOME/native homes/state와 명시적 합성 permission callback을
사용했고 실제 P2P/SSH/사용자 승인을 실행하지 않았다. Reverse file reply도 실제
Gateway/file API에서 만들었지만 물리 네트워크 표본으로 세지 않는다.
원시는 gateway-evidence.json과 gateway-collection.log에 있다.

잘못된 결과20개는 거부했다. Native handle/packet에 private home 필드를 허용하거나
그룹 aggregate 검사를 빼는 변이3종도 invalid-result 검사의 의도한 실패로 검출했다
(mutants.json). 일반 import/실행 실패를 검출로 세지 않았다.

Mac의 `python3 -B scripts/check-protocol.py`는881개
(Python508+외부 적합성32+SDK56+native133+Node152)를90.946초에 통과했다
(core.log, exit0). 독립 mock39/변이14는 별도 수치다. 이후 prose 명세도 REQUIRED에
넣은 최종 누락 거부 검사는 별도1개가0.090초에 통과했다. 개발 checker의 operation
목록/예제 목록 일치도 검사하며 최종 schema-current.json을 다시 통과시켰다.

## Linux 검증 준비와 남은 조건

같은 개발 validator를 Linux에서도 실행하도록 설치된 버전을 metadata로 조회해
jsonschema4.26.0, attrs25.4.0, jsonschema-specifications2025.9.1,
referencing0.37.0, rpds-py0.30.0, typing-extensions4.15.0을 고정했다.
Private VM share 아래3.11/3.14용 aarch64 target에 준비했고 package file SHA256을
linux-validator-deps.json에 보존했다. 격리 HOME/cache와 공개 PyPI를 사용했으며
사용자 Python/런타임/SDK 환경은 변경하지 않았다.

고정 source의 Linux core, 새 Linux stdio capture 및 offline schema 검증은
아래에서 확인했다. 실제 native/runtime/원격/사용자 UI/전체 설치
행렬과 나머지 operation 계약도 미완이다. 구현 담당 세션이 각 표면을 실행한 뒤
근거와 함께 갱신한다. 이 부분 계약을 전체 계획 완료로 대체하지 않는다.

## 고정 source Linux core와 schema 실행

d785f8ecd083ec543fdfef02dca4a230262ea17d의 archive SHA256은
27dae374066258bacb2d09ff84268a3b500d9eefb02de403d9483b2f44d7bb58다.
Python3.11.2에서83.571초, Python3.14.10에서106.231초로 core881개를
각각 통과했다. 각 환경에서 추가로 실제 stdio questions32개를 실행해 새로운
42개 frame을 수집했고, 고정 jsonschema4.26.0이 그 frame과 예제22개를
검증하며 잘못된 결과20개를 거부했다. 이전 Mac wire를 Linux 성공으로 복사한
것이 아니다. 독립 mock39/변이14는 core와 별도 수치다.

Source/core/추가 stdio/schema는 모두 model0/network none/cpu2/memory3g에서
실행했다. 미실행 case0, 미실행 wire/schema0, VM stopExit0이다. 원시는
question-contract-linux/result.json과 환경별 output의 protocol/wire/schema
파일이다. Schema 의존성 파일은 준비 전후 SHA256이 같음을 재확인했다
(linux-validator-audit.json). Production/runtime/SDK에는 의존성을 추가하지 않았다.

이 결과는 Linux의 Gateway 자체·물리 네트워크·실제 사람 승인·native queue
p95·전체 런타임/설치 행렬을 인증하지 않는다. 공개22개 operation 중 구조가
정의된 이름은11개(팀/보드는 일부 action), 미정의 이름도11개이며 전체 계획은
미완이다. Schema 내부55개 reference는 모두 같은 파일의 정의를 가리킨다.
