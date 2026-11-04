# 변경 전 실패 16건의 대응 검사

변경 전 표본은 `66a263c`의 106개 검사·실패 16건이다. 과거 로그를 덮어쓰지 않는다.
아래 기존 메서드 이름은 추적을 위해 유지했다. MCP 뒤 CLI로 옮기는 전제는 같은 MCP의
native 답변 복구로 이관했고, CLI 자체의 답변·일회 적용 검사는 유지했다.

| 기존 실패 | 새 검증 |
|---|---|
| PersonDecision: Claude question tool 안내 | AskUserQuestion을 원 질문 밖에 명시하며 질문 원문을 보존 |
| PersonDecision: declined form | 미표시 가능 decline과 실제 거절을 구분하고 같은 MCP 복구를 안내 |
| PersonDecision: link form fallback | Codex native 기록 형식의 실제 판독 후 MCP에서 link 적용·결과 재사용 |
| PersonDecision: remote pairing folder | 원격 grant가 caller 폴더에 결속되고 실제로 한 번만 소비됨 |
| PersonDecision: terminal wording | README 직접 사용 예시 하나의 예외를 갱신하고 나머지 떠넘기기 금지 검사 유지 |
| PersonDecision: other tools [join] | cancel → native 답 → 같은 MCP에서 가입 상태 확인 |
| PersonDecision: other tools [leave] | native 답 → 같은 MCP에서 탈퇴 상태 확인 |
| PersonDecision: other tools [reach] | cancel → native 답 → 정확한 reach 생성 |
| PersonDecision: other tools [approve] | cancel → native 답 → worker 요청이 실제 approved 상태 |
| PersonDecision: other tools [grant] | cancel → native 답 → FULL ACCESS 질문 범위와 grant 생성 |
| PersonDecision: other tools [grant outside scope] | cancel → native 답 → 폴더 범위 및 grant 생성; 별도 검사는 outside_scope 소비까지 확인 |
| PersonDecision: other tools [endorse] | native 답 → endorse 노드 하나만 생성 |
| McpForms: known-client decline | 실제 거절은 닫힘, cancel은 native 복구 안내, 멤버십 무변경 |
| McpForms: automatic reviewer | 자동 리뷰를 사용자 허용으로 쓰지 않고 native 복구 안내 |
| McpForms: relative reach | 원 질문에 절대 경로를 유지하고 같은 MCP 복구로 안내 |
| McpForms: shell-equivalent hint | CLI 전환 대신 같은 MCP 재시도·정확한 질문·원 폴더를 검증 |

`test_native_permission_recovery.py`는 이와 별도로 9작업의 허용·거절 18사례를 검증한다.
원 질문과 효과, 적용 전 무변경, 적용 후 권한 상태, 결과 재사용을 함께 검사한다.
폼 닫기 복구(Claude/Codex), 오래된 답, 명시 거절, 질문 불일치, 거절 경쟁, 실제 사용
가능한 outside grant, 미표시 decline, 자동 reviewer의 새 native 답변까지 포함해 총 27개다.

제품 결함은 cancel 이후 native 답이 무시되는 것과 outside grant의 부족한 옵션이었다.
두 결함은 변경 전 실패 출력도 `cancel-recovery-red.log`, `outside-grant-red.log`로 보존했다.
또한 native 답변 기록 도중 생긴 실제 거절을 덮어쓰지 않도록 locked response 경로를 검사한다.
