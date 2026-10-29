# Message audit

Python 표준 라이브러리로 UTF-8 JSONL 메시지의 직접 응답 관계를 집계합니다.

```sh
python3 summarize.py input.jsonl
python3 summarize.py - < input.jsonl
python3 summarize.py --fail-on-unanswered input.jsonl
```

빈 줄과 같은 `id`·정규화된 `reply_to`의 중복은 무시합니다. `reply_to` 생략과
`null`은 모두 루트 요청입니다. 입력 전체를 읽은 뒤 대상을 연결하므로 응답이
대상보다 먼저 나와도 됩니다. 다른 필드는 집계에 사용하지 않습니다.

출력 JSON의 `request_count`는 루트 수입니다. `answered`와 `unanswered`는 직접
응답 유무에 따른 루트 id 목록이고, `orphan_replies`는 입력에 없는 대상을 가리킨
응답 자신의 id 목록입니다. 목록은 사전순으로 정렬됩니다. 기존 응답을 가리키는
응답은 고아가 아닙니다. 전달 확인이나 과제 완료 여부는 이 집계에 포함되지 않습니다.

정상 입력은 기본적으로 종료 코드 0과 JSON 하나를 출력합니다.
`--fail-on-unanswered`를 지정하면 JSON은 같고 미응답 요청이 있을 때 종료 코드가
3입니다. 미응답 요청이 없으면 고아 응답만 있더라도 종료 코드 0입니다.
잘못된 레코드나 충돌 중복은 옵션과 관계없이
물리 줄 번호를 stderr에 출력하고 종료 코드 2로 끝나며 성공 JSON을 출력하지 않습니다.
되돌리려면 이 작업에서 추가한 `summarize.py`와 `README.md`를 제거하면 됩니다.
