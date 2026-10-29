# native 하네스 도구 노출 진단

0.163 원 CID의 0.164 재개는 회복 성공이 아니다. 원 CID는 보존했고 tool metadata를 보정하지 않았다. 별도로 처음부터 0.164에서 만든 fresh micro CID `01a18640-7405-7e50-9683-01c2b69cc1c3`에서 실제 `xsm_discover` 1회 호출과 `status=ok`를 확인했다. 이는 업무 여정과 분리한 도구 노출 표본이다.

## 서버 응답과 모델 노출의 차이

mini의 0.163 최초 실행, `--disable code_mode_host`를 붙인 동일 CID 재개, disable 없이 0.164로 재개한 세 조건 모두 실제 MCP initialize가 성공했고 tools/list에 정확히 같은 20개 schema를 반환했다. Book의 성공 조건도 같은 schema였다. 정규화 JSON SHA-256은 `0026feecc6aea956c859f8eb63a7d35dc1316d40614486dfdc3aa7c5c0d9cd05`다. 동결 서버에는 `xsm_who`가 없어 micro 검증은 제공된 읽기 전용 `xsm_discover`로 했다.

0.163 최초 실행의 최종 raw stderr에는 host 협상 timeout 5회가 있다. 중간 관측과 최초 중단 보고 시점의 4회보다 마지막 1회가 더 기록됐다. 당시 실패 원본은 그대로 유지했다. disable 조건에서도 MCP tools/list는 유지됐지만 실제 exec의 결과는 `code-mode host is disabled`였다. 이 flag가 서버의 MCP 목록을 삭제했다는 증거는 없다.

0.164 재개 인자에는 disable이 없다. 같은 임시 CODEX_HOME의 config.toml은 없었으며 두 CLI에서 읽은 현재 default는 code_mode_host=true였다. 그러나 실제 모델이 실행한 `ALL_TOOLS`의 비앱 전체 목록은 14개 builtin뿐이었고 xsm은 0개였다. 해당 출력은 잘리지 않았다. 따라서 마지막 모델의 “협업 도구가 없다”는 말만 근거로 삼은 것이 아니다. xsm의 프로세스·MCP 응답은 정상인데 code-mode inventory에 local xsm이 들어가지 않은 경계가 관측됐다. generic list_mcp_resources는 도구 목록 조회와 다르며 xsm 회복을 입증하지 않는다.

## 저장된 metadata

원 CID의 실제 provider rollout은 0.163 session_meta를 유지하며 world_state 1회, turn_context 3회를 담았다. 뒤의 0.164 재개에서도 새 additional_tools/world_state가 추가되지 않았다. 이 world_state에는 top_level_tools가 없고 model 값이 문자열이었다. 대조한 처음부터 0.164인 Book CID에는 additional_tools 1개와 top_level_tools가 들어 있는 world_state가 있었다. SQLite thread_dynamic_tools는 0행이었다.

이 차이는 버전·재개 metadata 불일치 가능성을 뒷받침하지만 정확한 내부 원인을 증명하지 않는다. 실제 provider 요청의 전체 도구 schema를 가로채지 않았고, fresh 대조는 새 임시 CODEX_HOME도 사용했으므로 오직 CID 재개 하나만 바꾼 인과 실험이 아니다.

## 허용된 독립 micro 1회

mini private 0.164 executable과 인접 host를 사용했고 resume·feature disable·모델명 지정은 없었다. 별도 XSM_HOME, 임시 CODEX_HOME, work 디렉터리에서 실제 thread.started/provider DB/live PID/MCP ancestry로 초기 등록했다. 목표에는 허용된 검증 도구 이름을 명시했다. 원 업무 질문·inbox·ACK·본문을 참조하지 않았다.

실제 client wire에 xsm_discover tools/call 1회, server wire에 status=ok와 self 후보 1개 응답이 있으며 native event도 동일 MCP 호출을 기록했다. 질문·메시지·ACK 호출 0회, profile 해시/인증 metadata 전후 동일, 소유 actor/MCP 잔여 0개였다. [micro 결과](micro-results.json), [raw](micro-evidence/actor/native.jsonl), [실행 인자](micro-launch.json).

현재 판단은 fresh 0.164 조건의 도구 노출 경로가 동작한다는 것까지다. 구 0.163 CID의 업그레이드 재개 성공, 원질문 회복, 전체 native 업무 성공을 주장하지 않는다. 후속 전체 여정은 수정 소스의 새 freeze와 양쪽 fresh 0.164 CID로 별도 수행하고, 동일 CID 재개 평가는 처음부터 0.164로 생성한 대화만 대상으로 한다.

실행 인자는 각 원본 actor-owner.json, 원 provider의 도구 호출/metadata는 [mini](mini-rollout-tool-metadata.json)와 [Book](book-rollout-tool-metadata.json), 실제 모델 목록의 이름 전수는 [노출 목록](mini-model-visible-tool-names.json), flag/default·도구 output은 [추가 근거](mini-exposure-output-evidence.json)에 있다. 원본 report·raw는 바꾸지 않았다.
