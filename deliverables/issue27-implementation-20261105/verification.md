# 승인 복구·프로필 승계 검증 결과

2026-11-05. 로컬 구현과 아래 필수 검증을 마쳤다. 게시·이슈 종료·push·병합·릴리즈는 하지 않았다.
사용자가 정한 이전 주소 전달 기간은 **승계 commit 후 24시간**이며, 만료가 원본 은퇴를 해제하지 않는다.

## 실행 결과

| 검사 | 실제 명령·근거 | 결과 |
|---|---|---|
| 승인·승계 수용 검사 | Python 3.14.6 `-B -m unittest tests.test_profile_migration tests.test_registry_profiles tests.test_migration_diagnostics tests.test_migration_network tests.test_native_permission_recovery -q`; [원시 출력](acceptance-77-completion.log) | 77개, 실패·오류·skip 0 |
| 정식 gate | 같은 Python으로 `-B scripts/check-protocol.py`; [원시 출력](protocol-gate-completion.log) | exit 0, 57.856초 / 120초 한도 |
| 전체 Python 탐색 | `-B full-discovery.py`; [목록](discovery-inventory.json), [결과](discovery-final.json), `discovery-group-0.log`부터 `7.log` | 148모듈·2,774개 전부 실행, 실패·오류 0, skip 3 |
| 정체 결함 반증 | `check-identity-regressions.py`; [결과](identity-regressions.json) | 변경 전 결함 2종 모두 assertion 실패로 검출 |
| 승인 결함 반증 | `check-permission-regressions.py`; [결과](permission-regressions.json) | 임시 복사본의 5결함 모두 검출 |
| 승계 결함 반증 | `check-migration-regressions.py`; [결과](migration-regressions.json) | 임시 복사본의 5결함 모두 검출 |
| 공개 명세·독립 소비자 | gate의 schema 및 independent-v7 단계 | migration 예제 5개·잘못된 예제 11개 판정; 독립 소비자 예제 137개·변이 193개 등 통과 |
| SDK | gate의 Python/Node stdio 시험 | 실제 공통 서버에 연결해 승계·원본 차단·전달·claim/ACK 검증; UI 응답은 합성 |
| 실제 Claude | [실측 결과](native-result.json), `native-a.terminal.log`, `native-b.terminal.log`, `native-*-observed-tools.json` | 아래 별도 기록 |

전체 탐색은 표준 unittest discovery가 찾은 모든 사례를 모듈 단위 8묶음으로 나눠
4프로세스까지 실행했다. 정식 제품 gate를 대체하는 검사기는 아니다. 최초 전수 실행은
735.238초·2,773개·실패 80건·오류 5건·skip 2건이었고,
[그 실패 목록](discovery-first-failures.json)과 원시 로그를 보존했다.
수정 뒤 전수 실행은 214.969초였다. 이후 거절·그룹 질문 검사를 강화한 묶음 1은
347개를 다시 실행해 통과했다. 마지막 home별 prune 추가 검사까지 포함한 77개도 별도로
통과했다. 사례 ID와 개수는 같으며, 재검사를 새 사례로 중복 계산하지 않는다.

## 승인 복구: 9작업·18사례

link, join, leave, reach, worker approve, grant, outside grant, remote pairing grant,
doc endorse 각각의 허용·거절을 검사했다. 답변 저장 전 무변경, 같은 MCP 재호출 뒤의
실제 효과·거절, 완료 결과 재사용, 중복 질문 방지를 확인했다. 기존 106개 검사에서
실패하던 16건은 [대응표](approval-failure-map.md)의 경로로 모두 실행된다.
정식 gate에 PersonDecision 81개·McpForms 25개와 추가 복구 27개가 포함된다.

복구 중단, deny를 allow로 해석, 다른 질문 캡처, 완료 receipt 재사용 중단,
정식 검사 누락을 각각 주입했다. 승계 검사의 변이는 home 키 누락, 원본 차단 누락,
24시간 검사 누락, 옛 allow 유지, 이관이 빠졌는데 완료하는 경우다.
결함은 임시 소스에만 넣었고 정상 검사 통과 후 각 변이의 실패를 확인했다.
현재 소스·검사 hash는 각 JSON에 남겼다. 이전 단계의 출력은 Git 이력에도 보존돼 있다.

## 이슈 #27 수용 기준 14항목

아래는 수용 검사 77개 및 정식 gate에서 실행한 경로다. 이름은 해당 test 파일에서 찾을 수 있다.

| ID | 확인한 효과 | 검사 근거 |
|---|---|---|
| 1 | A/B/A 등록, 정확한 발신자·수신자 유지 | RegistryProfiles의 repeated registration, exact sender/recipient; 실제 Claude 두 home |
| 2 | home 없는 모호한 조회에서 임의 선택 금지 | RegistryProfiles의 lookup without home, default profile isolation |
| 3 | legacy 이관·home별 종료·prune 독립 | RegistryProfiles의 legacy pointer, SessionEnd와 실제 housekeeping prune |
| 4 | 거절 시 자리·메시지 무변경 | ProfileMigration의 permission required: native 완료 형식의 deny 후 source 원문 보존·target not-found |
| 5 | 원본 재등록·발신·claim·옛 ACK·오래된 종료 차단 | ProfileMigration의 source cannot reclaim, unread claim, retired CLI, old execution/exit; 실제 Claude 원본 MCP 거부 |
| 6 | 같은 home resume·일반 handover 유지 | RegistryProfiles resume; gate의 handover/service 전체 묶음 |
| 7 | 24시간 경계·시계 역행·만료 후 은퇴 유지 | ProfileMigration의 expires at 24 hours, expiry then rollback |
| 8 | 병행 배달·재시도·공지의 유실·중복 효과 방지 | native delivery wait/transfer, replay; MigrationNetwork의 accepted original/duplicate ACK |
| 9 | DM·held·peer 질문·그룹 상태 보존 | unread original, held remains held, question effect crash; 실제 2수신자 그룹 생성→승계→늦은 답 조회 |
| 10 | 옛 human allow·claim을 새 권한으로 사용하지 않음 | pending user permission fresh ID/no answer, unknown application inspect, old claim denied |
| 11 | 팀·보드·coordinator·worker 대기 요청 유지 | team/board effect crash, worker link/project request; worker 로컬 재질문·중복 요청 금지 |
| 12 | 실패 기록·따라잡기 조회 권한·epoch 분리 | MigrationDiagnostics 7개: unresolved body 비공개, known endpoint, caller request ID, later epoch 차단 |
| 13 | home·실행 세대·은퇴·전달 만료·후임 unknown 구분 | MigrationDiagnostics doctor 및 pointer cleanup; 원본 주소 보존 |
| 14 | 중단 후 재개·거짓 완료 차단·gate 편입 | fenced/effect crash, missing successor copy; ProtocolGate inventory, 승계 반증 5종 |

## 실제 Claude 관측

- Claude Code **2.1.318**, 실제 응답 모델 `claude-sonnet-5-5`였다.
- 같은 native ID `f55ac2bc-7ee6-4e96-9ced-9b5b6fb0e775`의 transcript를 격리 A→B로
  복사하고 B에서 실제 resume했다. 두 프로세스는 다른 home·ref·PID·소켓을 유지했다.
- B의 실제 `xsm_migrate` 호출이 연 MCP 폼에 사용자가 답한 **allow**를 그대로 입력했다.
  journal은 committed이며 전달 기간은 정확히 86,400초다. 합성 허용으로 실측을 대신하지 않았다.
- 살아 있던 A의 실제 `xsm_send`는 은퇴 사유로 거부됐다. 모델 없는 SDK peer가 옛 A ref로
  보낸 메시지는 B에 저장됐고, B가 실제 훅의 token을 사용해 `xsm_ack`로 확인했다.
- 두 Claude 프로세스는 `/exit`로 종료했다. 실제 Claude/Codex 설정 파일 hash는 실행 전후 같았다.
  기존 구독 OAuth를 값 출력 없이 자식 프로세스에만 주입했고 API 키는 사용하지 않았다.
  시험 home에 처음 복사했던 불필요한 credential 파일도 제거했다.
- 첫 실행은 상속된 CHILD_SESSION 표식 때문에 transcript 저장이 꺼져 중단했다.
  이 표본을 승계 성공으로 세지 않는다. 런처에서 상속 표식을 제거한 뒤 위 시험을 했다.
- B의 모델은 “폼이 없었다”고 잘못 설명했다. 실제 터미널과 사용자 응답은 폼의 존재를
  증명한다. 도구 대기 중 client가 띄운 폼은 모델의 transcript와 다르므로, 안내에도
  도구 성공만으로 “폼이 없었다”고 말하지 않도록 반영했다.

Pi/OpenCode/OpenClaw/Hermes의 실제 모델·메신저 시험은 새로 실행하지 않았다.
공통 protocol과 각 native binding의 격리 fixture·SDK·카탈로그·소유권 검사는 gate에서
실행했다. 과거 6종 가입 실측과 cctrace의 별도 관찰은 이번 코드의 새 실측으로 표시하지 않는다.

## 실행하지 않은 조건부 검사

| 사례 | 이유와 현재 상태 | 다시 실행할 조건 |
|---|---|---|
| 과거 capacity raw replay | 원래 임시 폴더는 있지만 필수 원시 표본 3개 중 0개가 남았다. **원시 재생 미완** | 원래 세 로그와 request index 복구 |
| 과거 supplied native log replay | coordinator의 비공개 원시 로그가 없다. **재생 미완** | 지정 원시 로그 제공 |
| 기존 self-hosted relay 통합 검사 | official relay binary가 없으며 명시적 local opt-in을 요구한다. **이 조건의 재시험 미완** | 해당 바이너리와 opt-in 준비 |

작성자는 이 구현 세션이며, 기록일은 2026-11-05다. 위 skip은 성공으로 세지 않는다.
승인 18사례·승계 14기준·실제 Claude 필수 시험에는 skip이 없다. 전체 저장소에
조건부 검사까지 모두 실행됐다고 주장하지 않는다.

## 보존한 오류와 반영 경계

P2P ACK 증거 이관·전역 중복 reservation·native generation 누락, refused ID의 새 발급으로
owned reply ID가 달라진 결함을 실제 경로 검사에서 찾아 수정했다. 옛 null-ID 기대값,
22개 도구 기대값, home을 생략한 caller fixture, 카탈로그를 빠뜨린 설치 복사본도 이관했다.
전체 탐색 병렬 실행기의 첫 시도는 multiprocessing 재진입 방지가 없어 중복 실행됐다.
그 프로세스와 자식만 종료하고 `__main__` guard를 추가했다. `runner-first-*`는 성공 근거가 아니다.

테스트 변경 사유와 skip 추가는 [보호 검사 결과](oracle-current.json)에 명시했다.
사용자 설정·권한·운영 세션은 수정하지 않았고 외부 게시도 하지 않았다.
