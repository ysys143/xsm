# 문서 작업 공개 계약 검증

상태: P0/P2의 부분 진척이다. 전체 계획은 미완이다.

## 변경과 의미

xsm_doc의6개 action에 대한 result schema와 예제7개를 추가했다. 요청 action을
x-actionResults로 매핑한다. add/show는 node, log/leaves는 nodes 배열,
render는 text와 nodes 개수, next는 생성 순서의 후보 view와 설명 text다.
공통 inbox pending 진단도 허용한다. Public bundle은 스키마/예제를 필수로 요구한다.

Board/document node 구조는 같으며 개발 checker가 두 정의의 차이를 거부한다.
Next는 할당을 하지 않고 wip 선언으로 후보를 숨기지 않는다. Limit는 표시 prefix만
줄이고 전체 total은 보존한다. Timestamp가 같은 노드는 ID로 정렬한다. Author
표시는 무결성/실제 사용자 endorsement 증명이 아니다. 기존 서버 코드는 바꾸지
않고 계약·공개 검사·회귀 검사를 추가했다.

## 실행 증거

```sh
python3 -B scripts/conform-host-protocol.py --suite documents --capture \
  --output deliverables/protocol-foundation/doc-contract/wire-first.json \
  --command /absolute/path/to/xsm/bin/xsm protocol serve --stdio
python3 -B scripts/check-protocol-schema.py \
  --wire-trace deliverables/protocol-foundation/doc-contract/wire-first.json \
  --output deliverables/protocol-foundation/doc-contract/schema-first.json
```

실제 stdio 서버는 lifecycle16개+문서12개, 총28개를 통과했다. 프레임32개가
스키마에 맞았고6개 action을 모두 관측했다. 노드 추가/조회/그래프/렌더/후보와
존재하지 않는 parent/node 거부를 포함한다. 임시 HOME/XSM_HOME/native homes,
임시 작업 폴더에서 실행했으며 native 모델이나 실제 사용자 UI는 호출하지 않았다.

문서 예제7개는 통과하고 잘못된 구조14개는 거부했다. Assigns와 total 제약을
없앤 임시 스키마 변이2개를 checker가 검출했다(schema-mutants.json).
실제 서버 앞 wire proxy가 wip 후보를 숨기거나 limit 뒤 total을 줄이는 결함은
각각 해당 검사에서 실패했다. 정상 경로와 이 두 결함의 unittest3개는2.067초에
통과했다. 원본 서버나 저장 노드를 변이하지 않았다.

## macOS 핵심 회귀

`python3 -B scripts/check-protocol.py`는 macOS/Python3.14.6에서866개
(Python525+SDK56+native133+Node152)를103.779초에 통과했다(core.log, exit0).
독립 mock39/변이14는 별도 수치다. 작성자 검사를 agent label뿐 아니라 현재
세션 ref 포함까지 보강한 뒤 public suite28개와 frame32개를 다시 통과했다
(wire-final.json/schema-final.json). 서버·SDK 실행 코드는 이 보강에서 바꾸지 않았다.

## 남은 필수 조건

이 실행은 공개 stdio 서버의 문서 경로이며 native runtime/실제 사용자 endorsement/
원격 doc/메신저/설치 행렬 인증이 아니다. Linux의 이번 source, 남은 operation
결과 계약과 독립 구현의 전체 적합성도 미완이다. 구현 담당 세션이 각 표면을
실행하고 근거를 확인한 뒤 갱신한다. 승인된 전체 계획의 조건을 생략하지 않는다.
