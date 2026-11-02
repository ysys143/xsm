# 기존 기능과 공개 프로토콜 전수표

초기 조사 기준은 `a1e4804`이며 기능 지원 인증이 아닌 진입점 대조표다.
`scripts/inventory-protocol-features.py --output <새 JSON 경로>`로 HOME/XSM_HOME을
격리해 parser와 공개 catalog를 직접 읽었다. 결과는 CLI 말단 명령 **73개**,
공개 operation **22개**(초기 21개에서 xsm_doc 추가), host method **11개**다. positional action의 여러 값은
별도 명령으로 중복 계산하지 않았다. 전체 옵션은 원시 JSON에 있다.

명령이 공개 operation과 겹친다는 사실만으로 CLI 공통화·native 실행·원격·
UI 호환이 확인된 것은 아니다. 아래 대응 미확정 항목은 이번 작업자가
2026-11-02에 기록했으며 범위 제외 승인이 없다. 공통 서비스 추출과
각 런타임 실제 행렬 검사에서 다시 확인해야 하는 **미완**이다.

## CLI 말단 명령 73개

| CLI | parser가 선언한 action/선택값 | 공개 인터페이스 대조 |
|---|---|---|
| `xsm network start` | — | 운영 CLI; 개별 operation 대응·권한 경계 미확정 |
| `xsm network stop` | — | 운영 CLI; 개별 operation 대응·권한 경계 미확정 |
| `xsm network status` | — | 운영 CLI; 개별 operation 대응·권한 경계 미확정 |
| `xsm network members` | — | 운영 CLI; 개별 operation 대응·권한 경계 미확정 |
| `xsm network address` | — | 운영 CLI; 개별 operation 대응·권한 경계 미확정 |
| `xsm network build` | — | 운영 CLI; 개별 operation 대응·권한 경계 미확정 |
| `xsm network requests` | — | 운영 CLI; 개별 operation 대응·권한 경계 미확정 |
| `xsm network export` | — | 운영 CLI; 개별 operation 대응·권한 경계 미확정 |
| `xsm network archive` | — | 운영 CLI; 개별 operation 대응·권한 경계 미확정 |
| `xsm network init` | — | 운영 CLI; 개별 operation 대응·권한 경계 미확정 |
| `xsm network invite` | — | 운영 CLI; 개별 operation 대응·권한 경계 미확정 |
| `xsm network join` | — | 운영 CLI; 개별 operation 대응·권한 경계 미확정 |
| `xsm network remove` | — | 운영 CLI; 개별 operation 대응·권한 경계 미확정 |
| `xsm network revoke-invite` | — | 운영 CLI; 개별 operation 대응·권한 경계 미확정 |
| `xsm network leave` | — | 운영 CLI; 개별 operation 대응·권한 경계 미확정 |
| `xsm network configure` | — | 운영 CLI; 개별 operation 대응·권한 경계 미확정 |
| `xsm network sessions` | — | 운영 CLI; 개별 operation 대응·권한 경계 미확정 |
| `xsm network map-repository` | — | 운영 CLI; 개별 operation 대응·권한 경계 미확정 |
| `xsm protocol serve` | — | 호스트 설치·진단/stdio 진입점; 모델 작업 아님 |
| `xsm protocol describe` | — | 호스트 설치·진단/stdio 진입점; 모델 작업 아님 |
| `xsm protocol install` | runtime: hermes, openclaw, opencode, pi | 호스트 설치·진단/stdio 진입점; 모델 작업 아님 |
| `xsm protocol uninstall` | runtime: hermes, openclaw, opencode, pi | 호스트 설치·진단/stdio 진입점; 모델 작업 아님 |
| `xsm protocol inspect` | runtime: hermes, openclaw, opencode, pi | 호스트 설치·진단/stdio 진입점; 모델 작업 아님 |
| `xsm list` | action: clear | 대응 미확정; 기존 CLI 경로 보존 필요 |
| `xsm who` | — | 대응 미확정; 기존 CLI 경로 보존 필요 |
| `xsm join` | — | xsm_join |
| `xsm leave` | — | 대응 미확정; 기존 CLI 경로 보존 필요 |
| `xsm team` | action: create, add, remove, lead, leave, list, show, mute | xsm_team |
| `xsm board` | action: show, set, log, sync, decisions, decide, mute | xsm_board |
| `xsm handover` | — | xsm_handover |
| `xsm owned` | action: create, run, status, retry, reconcile | xsm_owned |
| `xsm spawn` | runtime: claude, codex | 대응 미확정; 기존 CLI 경로 보존 필요 |
| `xsm workers` | action: list, read | 대응 미확정; 기존 CLI 경로 보존 필요 |
| `xsm reap` | — | 대응 미확정; 기존 CLI 경로 보존 필요 |
| `xsm stop` | — | 대응 미확정; 기존 CLI 경로 보존 필요 |
| `xsm attach` | — | 대응 미확정; 기존 CLI 경로 보존 필요 |
| `xsm worker-finish` | — | 대응 미확정; 기존 CLI 경로 보존 필요 |
| `xsm doc` | action: add, render, log, next, leaves, show | xsm_doc(add/render/log/next/leaves/show 공통 서비스); xsm_doc_endorse(사용자 endorsement) |
| `xsm remote` | action: add, accept, list, remove, sessions | 대응 미확정; 기존 CLI 경로 보존 필요 |
| `xsm mcp` | — | 대응 미확정; 기존 CLI 경로 보존 필요 |
| `xsm approvals` | — | 대응 미확정; 기존 CLI 경로 보존 필요 |
| `xsm approve` | — | xsm_approve와 이름 유사; terminal 사용자 답 경로와 동등하지 않음 |
| `xsm deny` | — | 사용자 decision.response; 모델 명령으로 대신할 수 없음 |
| `xsm link` | — | xsm_link |
| `xsm unlink` | — | 대응 미확정; 기존 CLI 경로 보존 필요 |
| `xsm reach` | — | xsm_reach |
| `xsm block` | — | 대응 미확정; 기존 CLI 경로 보존 필요 |
| `xsm unblock` | — | 대응 미확정; 기존 CLI 경로 보존 필요 |
| `xsm attempts` | action: list, show, clear | 대응 미확정; 기존 CLI 경로 보존 필요 |
| `xsm frameworks` | action: list, ignore, respect | 대응 미확정; 기존 CLI 경로 보존 필요 |
| `xsm projects` | — | 대응 미확정; 기존 CLI 경로 보존 필요 |
| `xsm homes` | action: list, add, remove | 대응 미확정; 기존 CLI 경로 보존 필요 |
| `xsm prune` | — | 대응 미확정; 기존 CLI 경로 보존 필요 |
| `xsm connect` | — | xsm_connect |
| `xsm ask` | — | xsm_ask |
| `xsm question-status` | — | xsm_question_status |
| `xsm decision-status` | — | xsm_decision_status |
| `xsm discover` | — | xsm_discover |
| `xsm publish` | — | xsm_publish |
| `xsm send` | — | xsm_send |
| `xsm inbox` | — | xsm_inbox |
| `xsm ack` | — | xsm_ack |
| `xsm files` | — | xsm_files |
| `xsm status` | — | 대응 미확정; 기존 CLI 경로 보존 필요 |
| `xsm ledger` | — | 대응 미확정; 기존 CLI 경로 보존 필요 |
| `xsm metrics` | — | 대응 미확정; 기존 CLI 경로 보존 필요 |
| `xsm otlp-export` | — | 대응 미확정; 기존 CLI 경로 보존 필요 |
| `xsm held` | action: list, show, drop, deliver | 대응 미확정; 기존 CLI 경로 보존 필요 |
| `xsm install` | — | 대응 미확정; 기존 CLI 경로 보존 필요 |
| `xsm uninstall` | — | 대응 미확정; 기존 CLI 경로 보존 필요 |
| `xsm doctor` | — | 대응 미확정; 기존 CLI 경로 보존 필요 |
| `xsm statusline` | — | 대응 미확정; 기존 CLI 경로 보존 필요 |
| `xsm selftest` | — | 대응 미확정; 기존 CLI 경로 보존 필요 |

## 공개 operation 22개

| Operation | action 값 |
|---|---|
| `xsm_owned` | create, run, status, retry, reconcile |
| `xsm_files` | 별도 action enum 없음 |
| `xsm_decision_status` | 별도 action enum 없음 |
| `xsm_ask` | 별도 action enum 없음 |
| `xsm_question_status` | 별도 action enum 없음 |
| `xsm_discover` | 별도 action enum 없음 |
| `xsm_publish` | 별도 action enum 없음 |
| `xsm_connect` | 별도 action enum 없음 |
| `xsm_grant` | 별도 action enum 없음 |
| `xsm_send` | 별도 action enum 없음 |
| `xsm_team` | list, show, create, add, remove, lead, leave, mute, unmute |
| `xsm_handover` | hand_over, show |
| `xsm_board` | show, set, log, decisions, mute, unmute, sync |
| `xsm_ack` | 별도 action enum 없음 |
| `xsm_inbox` | 별도 action enum 없음 |
| `xsm_link` | 별도 action enum 없음 |
| `xsm_join` | 별도 action enum 없음 |
| `xsm_reach` | 별도 action enum 없음 |
| `xsm_doc` | add, render, log, next, leaves, show |
| `xsm_doc_endorse` | 별도 action enum 없음 |
| `xsm_approve` | 별도 action enum 없음 |
| `xsm_decide` | 별도 action enum 없음 |

## 호스트 메서드 11개

- `initialize`
- `operations/list`
- `session.open`
- `session.update`
- `session.close`
- `events.subscribe`
- `operation.call`
- `inbox.release`
- `delivery.report`
- `decision.response`
- `decision.abandon`

## 이미 드러난 차이와 후속 확인

- 초기 표에서 빠졌던 doc add/render/log/next/leaves/show는 xsm_doc으로 연결했다. endorsement는 별도 사용자 결정 경로로 유지한다. 실제 전체 런타임 행렬의 통과는 미완이다.
- spawn/stop/attach/reap/workers와 owned의 runtime 지원·생명주기는 전체 검증이 남았다. 현재 spawn parser는 Claude/Codex만 선언한다.
- 디렉터리·범위·승인·handover·files·owned 계열의 CLI orchestration 공통화와 결과 계약 전수 검증이 남았다.
- team/board/send/question은 공통 서비스로 이동했지만 실제 6개 런타임 전체 행렬 통과를 의미하지 않는다.
- 설치/제거·운영·사용자 답 수집 명령을 모델 도구에 그대로 노출할지 여부는 이 표에서 결정하지 않는다. 기존 기능 보존과 사용 주체별 권한 경계를 함께 확인한다.
