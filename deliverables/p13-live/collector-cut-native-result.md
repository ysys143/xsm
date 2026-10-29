# A15-03 collector cut native — preflight 부분 결과

판정: **partial — 실제 수집 단절/unknown/같은 ID 회수는 검증하지 못했다.** 모델0의 실제 native app-server API initialize→thread/start→MCP tools 조회까지 진행했다. 실제 caller의 provider DB CID/cwd와 native ancestry를 최초 등록 시점에 함께 확정하지 못해 권한 도구 호출 전에 멈췄다. 나중에 DB 행이 보였지만 종료된 actor의 관측을 소급해 보충하거나 재기동하지 않았다.

실제 proxy에서 native MCP initialize와 tools/list를 보존했고 native가 광고한 elicitation capability를 그대로 기록했다. capability/threadId/PID/home/응답/본문을 rewrite하지 않았다. **elicitation/create는 관측되지 않았고 drop fault도 실행되지 않았다.** 따라서 native client 거절, collector 부재, collector 단절을 어느 것도 성공/실패로 꾸며 구분하지 않았다. preflight만 성공했다는 범위다.

첫 CLI 시도는 app-server에서 지원하지 않는 --ignore-user-config 때문에 initialize 전에 exit2였다. 원 실패를 private 하위 디렉터리에 보존하고 그 인자만 수동 정정했다. CLI launch attempt2, 실제 API thread1, model turn0, 새 모델 child0, 자동재시도0이다. 모든 실제 API 프로세스는 stdin 종료 후 끝났고 성공 조건을 얻으려 반복하지 않았다.

source 검토에서 ask_client의 EOF/OSError는 abandon_display 뒤 전파되고, abandon_display는 display를 not-requested로 돌리지만 그 자체로 status=unknown을 만들지 않는다. public_status에는 일반 recover_at 필드도 없다. 이는 source상 관찰이며 실제 단절 실행 결과로 보고하지 않는다. fake callback/긍정 응답/yes/token/consent는 만들지 않았다. 실제 권한 요청도 발행하지 않았으므로 grant0은 단순 무동작이지 요청된 fake-approval 음성 검증의 증거가 아니다.

**전역 profile metadata 불변도 주장할 수 없다.** 실제 API 시도 전후 config/settings metadata 차이가 관측됐다. 기록된 파일명·stat 전후값은 JSON에 있고 작성 주체는 미확정이다. driver의 직접 설정/권한 편집은 없었으나 native 시작 또는 동시 writer를 단정하지 않는다. key/auth 원문을 열거나 비교하거나 설정을 되돌려 차이를 숨기지 않았다. 정책 값 불변은 미입증이다.

[JSON](collector-cut-native-result.json)에 실제 argv/경로·fault 미실행·preflight 상태·source SHA·private raw SHA·metadata drift·미확보 acceptance를 분리했다. raw는 `/private/tmp/collector-cut-native-aurzj351`에 보존했다. 제품·plan·ledger·기존 artifact는 변경하지 않았고, 추가 모델/승인/UI/실험으로 미확보를 메우지 않았다.
