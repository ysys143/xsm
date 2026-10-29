A21-04의 self-vs-remote 동명 표본을 실제 두 Mac의 새 actor 2개로 완료했습니다. 양쪽 최초 표시 이름은 a1이며, 요청자가 본인과 원격 후보를 구분해 원격 Claude를 선택했습니다. 원 요청 `3ccb7bfcd0344f72`에 실제 원격 회신 `66daee02cedb4ec0`이 `reply_to`와 `outcome=succeeded`로 연결됐고, 양쪽 실제 MCP ACK 2건과 canonical `acknowledged`를 확인했습니다. 제3자 다중 동명 선택으로 확대하지 않습니다.

| 구분 | 요청자 | 검토자 |
|---|---|---|
| 기기 | jaesol-macmini | MacBook |
| runtime | Codex CLI 0.164.0 | Claude CLI 2.1.312 |
| 실제 관측 model | gpt-6.1-sol | claude-sonnet-5-5 |
| 표시 이름 | a1 | a1 |
| 실제 CID | `01a1883b-14d9-7e01-a89c-5c988b20489d` | `30e9cd91-c5b8-4016-ae18-e57d883115b2` |
| native PID | 62457 | 23031 |
| 실제 MCP PID | 62715 | 23245 |
| 실제 home | `/private/tmp/native-journey-samename-fifo-mini-xd79l1tx/codex-home` | `/Users/jaesolshin/.claude-3` |
| machine | `b42dc1a4b8a099113a904bdb23f8b2a76bc80eeb94731f738e26e8f09ce083f7` | `445313bf4701a59ef4cdce35db5acdad0a2cde861d28655316dfcccee9f4d2b1` |
| home_id | `bb12de996187d4a7e6c69612ff112eb3017183986028a055dde80e13f0829a90` | `1f3efe9ffb9cf15ba352aa22f67362777ae05495d0bb84b9b5b8268090817da7` |
| generation | `c6e9595173dbc3ec37f262f299d3d1db8ed56a0fe03365fe23eee0dbae47e724` | `9fe7930e4d25821a863bced432e60e4795e24afa8f597aebc90f987a4e652105` |

[actors 원본과 검사 결과](results.json)의 공개 handle은 실제 P2P packet에서 얻었습니다. 초기 등록은 실제 provider CID, 커널 PID·시작 시각, MCP 조상 및 Claude가 실제 보유한 socket으로만 구성했습니다. libproc ps shim과 기존 guard를 유지한 controlled native 표본이며, 무보정 onboarding 성공을 주장하지 않습니다. Book 전체 actor와 mini의 MCP·자기 hook에 기존 write/SSH guard를 유지했습니다. mini provider의 실제 `workspace-write`, `approval_policy=never`와 native argv를 확인했고, 새 allowedTools나 권한 규칙을 추가하지 않았습니다.

실제 발견 결과는 a1 2개입니다. self의 CID는 `01a1883b-14d9-7e01-a89c-5c988b20489d`이고 원격 a1의 CID는 `30e9cd91-c5b8-4016-ae18-e57d883115b2`입니다. 원격 후보는 `published`로 발견됐으며 사전 repository map은 0개입니다. requester의 실제 사용자 지시를 consent 결과가 그대로 보여 준 뒤 모델이 동일 candidate를 선택했습니다. 선택된 candidate와 packet의 원격 full handle 및 generation이 일치합니다. requester 자기공개 호출은 없었습니다.

선택된 완전한 target은 다음과 같습니다.

```text
net:445313bf4701a59ef4cdce35db5acdad0a2cde861d28655316dfcccee9f4d2b1:claude:1f3efe9ffb9cf15ba352aa22f67362777ae05495d0bb84b9b5b8268090817da7:30e9cd91-c5b8-4016-ae18-e57d883115b2
```

| 메시지 | ID | 수신한 실제 세션 | canonical ACK 시각 UTC |
|---|---|---|---|
| 원 요청 | `3ccb7bfcd0344f72` | Claude `30e9cd91-c5b8-4016-ae18-e57d883115b2` | 2026-10-29T15:16:14.908859+00:00 |
| 직접 회신 | `66daee02cedb4ec0` | Codex `01a1883b-14d9-7e01-a89c-5c988b20489d` | 2026-10-29T15:16:11.159123+00:00 |

요청 본문 SHA256은 `b268004cb9e0a4f2b2c5442a8a59992556d9feb2beba033a93c3c0caafdb865f`, 회신 본문 SHA256은 `d734106e260c9bb30fedaff23156b08932fa78af2eec2738ba32f4dc49c40e53`입니다. 양쪽 outbound/inbound packet과 수신 canonical 본문이 각각 일치했습니다. 양방향 실제 transport event의 payload hash와 TLS origin도 일치했고 `selected=direct`, relay off였습니다. SSH는 operator 준비·관측 경로로만 사용했습니다. 본인에게 원 요청이 배달된 handoff는 없습니다.

실제 회신 내용은 다음과 같습니다.

> 역할은 검토 담당 a1입니다. 협업 준비가 되었습니다. 이 세션은 xsm에 공개되어 있고, 작업 요청(task)과 질문(ask)을 받을 수 있습니다. 수신은 Claude 세션 인박스로 이루어지며, 결과는 reply와 outcome으로 회신합니다. 권한, 설정, 승인 요청은 처리하지 않고 사용자에게 넘깁니다.

persistent SDK의 실제 FIFO stdin은 열린 채 유지됐습니다. 이번에는 첫 `xsm_inbox(wait=60)`가 원 요청을 회수했고, 일반 계속 Goal이나 두 번째 모델 기동이 필요하지 않았습니다. native 종료 143은 회신과 ACK 완료 후 소유 PID 정리에서 발생했습니다. 이전 표본의 구버전 wake 보류와 원 요청 `b82e615ed4f74a0f`의 pending은 그대로 보존했습니다. 이번 표본에 보류 항목은 없었고, 이번 MCP 회수를 자동 wake 성공으로 보고하지 않습니다. 이전 pending을 새 CID로 재지정하거나 재전송하지 않았습니다.

`xsm_connect`가 회신을 반환할 때 `canonical-unavailable-or-mismatch` 진단과 빈 claims를 반환한 점도 원본에 남겼습니다. 실제 모델은 기존 pending 알림에 따라 MCP inbox로 같은 회신을 읽은 뒤 실제 토큰으로 ACK했습니다. 이 동결본에서 inbox 회복 경로가 완주됐다는 범위이며, 최신 소스에서 직접 answer claim 경계가 해소됐는지는 이 표본으로 판정하지 않습니다.

실행한 [source manifest](source-manifest.json)의 SHA256은 `f4172fc9f4c49433eb90fe44a54dad5631ede60249b60a5905e3524d794c62a4`입니다. Python 52개와 hooks/bin/skills 13개, 총 65개가 양쪽 실행 payload에서 일치했습니다. engine SHA256은 `c963e9d4e4ffda47dead354d7d66e2f71fea037932b51846422bdbacb5b39a7d`이며, 지정된 pre-loopback-policy release를 사용했습니다. relay 검증으로 확대하지 않습니다. 현재 작업 소스와는 아래 6개 경로가 달랐으며, 최신 소스의 전체 회귀로 보고하지 않습니다. 제품 소스는 수정하지 않았습니다.

- `skills/xsm/references/network.md`
- `xsm/network.py`
- `xsm/network_directory.py`
- `xsm/network_messages.py`
- `xsm/probe.py`
- `xsm/send.py`

[기존 global profile drift 범위](prior-global-profile-drift-scope.json)를 원본 그대로 보존했습니다. 대상은 `/Users/jaesolshin/.claude-3/.claude.json` 1개이며, 최초 before hash는 `535bf0cacb4f80a20c8ec6a50072fd7dbba89eb1cb2a5bef89f3d7ae735fba1d`이고 before 기록 시각은 `2026-10-29T09:30:34.877214+00:00`입니다. 최초 파일의 size/inode/mtime은 기록이 없었습니다. 변경 주체나 권한·auth 변경 여부를 입증하지 못했으며 임의 복구하지 않았습니다. 이번 표본의 [직전 baseline](book-global-before.json)과 [직후 관측](book-global-after.json)에서는 지정된 3개 파일의 hash 변화가 0개였습니다. 인증 값은 읽거나 복사하지 않았습니다.

검사는 `python3 -B analyze.py`로 보존 증거만 읽어 수행했고, 27개 비교가 모두 통과했습니다. 도구 목록에 실제 광고된 xsm_discover와 모델의 실제 호출, self/remote 식별, 선택 증거, 원문 대조, 상관 회신, 실제 MCP ACK, 이전 pending 보존 및 정리 결과를 확인했습니다. [원시 Book 증거](book-evidence/actor/native.jsonl), [원시 mini 증거](mini-evidence/actor/native.jsonl), [P2P Book 이벤트](book-evidence/raw/transport.jsonl), [P2P mini 이벤트](mini-evidence/raw/transport.jsonl)를 보존했습니다.

[Book 정리](book-cleanup.json)와 [mini 정리](mini-cleanup.json) 후 [Book PID 재확인](book-final-pid-check.json) 및 [mini PID 재확인](mini-final-pid-check.json)에서 native·MCP·controller·service·engine의 확인된 PID 9개가 모두 없었습니다. 두 private 서비스는 stop 반환 후 종료됐습니다. state/key와 평가 증거는 삭제하지 않았습니다. 실제 private roots는 [roots.json](roots.json)에 기록했습니다.
