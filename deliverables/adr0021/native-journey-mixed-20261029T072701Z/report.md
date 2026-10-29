# Claude와 Codex 실제 혼합 표본: 기동 확인, 업무 왕복 미완

Book의 실제 Claude 구독 런타임과 mini의 실제 Codex 구독 런타임을 서로 다른 home/runtime으로 실행했다. Claude가 실제 MCP 공개 도구를 호출했지만 등록자 확인이 막혀 공개되지 않았다. 원격 후보 선택·상관 핸드셰이크·질문/후속 회신은 0건이다. 완주 또는 실제 업무 왕복 성공으로 보고하지 않는다.

## 실제 실행과 인증

| 항목 | Book Claude 검토자 | mini Codex 요청자 |
|---|---|---|
| CLI | `2.1.312 (Claude Code)` | `codex-cli 0.164.0` |
| 실제 관측 모델 | `claude-sonnet-5-5` | `gpt-6.1-sol` |
| 실제 home | `/Users/jaesolshin/.claude-3` | 새 private CODEX_HOME에서 `.codex-3/auth.json` 참조 |
| 실제 CID | `28e3361e-d092-4c85-bb8f-4f3b1a95cb03` | `01a186a0-e033-74a1-a1c5-4e9c4ec88b1a` |
| 권한 조건 | 기존 auto, 새 allow 규칙 0개 | workspace-write, approval_policy=never |
| 결과 | MCP 연결 후 공개 호출 2회 거절 | 실제 MCP 발견 2회, 원격 공개 a1 없음 |

모델명은 Claude의 system.init과 Codex의 실제 provider turn_context에서 관측했다. 임의 모델명이나 위험 flag를 지정하지 않았다. Book의 `.claude-3`은 CLI auth status에서 claude.ai 구독 로그인과 firstParty를 확인했고 실제 init의 apiKeySource는 none이었다. mini의 `.claude-3`은 현재 허용 조건에서 로그인 상태를 확인하지 못해 역할을 바꿨다. 인증 값은 읽거나 복사하지 않았고 새 로그인·자격 증명 변경도 하지 않았다.

첫 Claude 실행 `cf45057f-5a23-4100-8585-4a57b3539de2`는 관측 proxy를 통해 MCP를 시작하다 failed 상태가 됐다. 원본을 attempt1에 보존했다. 같은 쓰기 보호와 기존 권한을 유지한 직접 MCP preflight는 initialize/tools/list에 정상 응답했다. 이 조건 차이만 반영한 두 번째 실제 Claude 실행에서 MCP connected와 실제 공개 도구 호출을 관측했다. 같은 잘못된 기동 조건을 계속 반복하지 않았다.

기존 실제 Claude home을 쓰면서 전역 profile에 쓰지 않도록 `--no-session-persistence`와 private process-local 쓰기 보호를 적용했다. 기존 MCP allow/deny 규칙을 추가하거나 완화하지 않았다. native lifecycle hook은 실제 사용자 업무 프롬프트를 제품 경로로 기록했고, controller가 consent 답변이나 공개 상태를 작성하지 않았다. 두 실제 프롬프트와 그 hook 기록은 raw에 남아 있다.

## 정확한 실패 경계

임시 OS 쓰기 보호 profile은 사용자 home 아래 쓰기만 거부하도록 만들었다. 그러나 이 sandbox에서 `/bin/ps`를 실행하면 exit 71과 다음 실제 오류가 났다.

```text
sandbox-exec: execvp() of '/bin/ps' failed: Operation not permitted
```

같은 조건의 Python subprocess에서도 ps 실행이 PermissionError로 거절됐다. 이 때문에 실제 SessionStart pointer에는 PID가 있으나 lstart가 null이었고, xsm MCP의 호출자 조상 확인이 성립하지 않았다. 실제 xsm_publish는 두 번 모두 다음 오류를 반환했다.

```text
this session is not registered: no hook record for it
```

이것은 이번 평가용 OS 보호 조건에서 관측한 실행 거부다. Claude의 기존 도구 승인 목록 자체가 공개 도구를 거부했다고 일반화하지 않는다. 실제 Claude 결과의 permission_denials는 빈 배열이었다. 공개 도구 호출은 노출됐지만 제품의 등록자 확인에서 멈췄으며, 공개 동의 적용 단계에는 도달하지 않았다.

쓰기 보호를 제거하거나 새로운 allowedTools·전역 rules·위험 flag를 넣어 우회하지 않았다. ps 대신 가짜 조상·시작 시각을 주입하거나 controller가 MCP 호출자의 신원을 대신 작성하지도 않았다. 실제 원문·ACK·질문 index·동의 답변 보정은 0건이다.

남은 필수 평가 범위는 전역 profile 쓰기 0 및 기존 구독 인증을 유지하면서 정상적인 MCP 호출자 확인용 ps 실행도 가능한 배치를 검증하는 것이다. 그 조건이 확보된 뒤 실제 공개 지시의 적용, 공개 후보 선택과 상관 회신, 업무 질문과 후속 회신을 평가해야 한다. 이번 결과에는 그 경로의 성공 증거가 없다.

## 공개 후보와 P2P 조건

두 호스트에 새 private network를 만들고 실제 release engine으로 init/join을 수행했다. 각 호스트의 work는 별도 Git 저장소이며 repository map은 만들지 않았다. 공개 후보 선택을 사전 same-repository scope로 바꾸지 않았다. 공개 파일 0개, 질문 0개, collaboration grant 0개였다.

Codex는 실제 MCP xsm_discover를 두 번 호출했고 공개 a1을 찾지 못했다. 모델이 추가로 실행한 PATH의 전역 `xsm` CLI는 기존 0.4.20 설치본이었다. 그 CLI의 network 미지원·SSH 목록 없음 진단을 현재 동결 MCP/P2P 서비스의 장애 증거로 쓰지 않는다. 현재 동결 서버는 별도 private 경로에서 실행됐으며 이 차이를 raw와 CLI 경로로 구분했다.

SSH는 provisioning·기동·관측과 private 초대 stdin 전달에만 썼다. controller가 다른 모델에게 업무 본문을 전달하지 않았다. 이번 표본은 실제 P2P 가입 및 발견 metadata까지 진행했으며 업무 본문 전송은 0건이므로 업무 본문 carrier의 성공을 주장하지 않는다.

## 동결본·쓰기·이전 표본 보존

최신 Python 52개와 hooks/bin/skills 13개, 총 65개를 새로 복사했다. source manifest SHA-256은 `f4172fc9f4c49433eb90fe44a54dad5631ede60249b60a5905e3524d794c62a4`다. R1 network/probe와 생성 지침 원본 동기화를 포함한 복사 시점의 파일별 SHA를 기록했고 양쪽 payload가 모두 일치했다. 제품 소스는 수정하지 않았다.

사용한 engine은 지정 release `/private/tmp/adr21-install-0q83fzpr/state/network/bin/xsm-net`의 복사본이다. 현재 Rust loopback relay 정책 수정 전 바이너리이며 이번 설정은 relay off였다. 새 state/key는 새 private root에만 남겼다.

실제로 사용한 Book Claude profile 및 mini Codex profile의 보존된 설정 SHA·auth metadata baseline은 전후 동일했다. API key 값이나 실제 auth 값을 controller가 읽거나 복사하지 않았다. 새 permission allow 항목은 0개다. 기존 native-journey 표본과 옛 pending 질문의 state/key는 이번 평가에서 쓰지 않았고 변경하지 않았다.

모든 소유 actor/MCP와 양쪽 network service/engine을 정리했다. 공개 stop exit는 양쪽 0, 강제 신호는 0, 확인된 소유 PID 잔여는 0개다. 원본 raw, 새 state/key와 평가 증거는 보존했다. 커밋·외부 게시·기존 사용자 profile 또는 권한 변경은 하지 않았다.

private roots:

- Book: `/private/tmp/native-journey-mixed-book-cqzkttta`
- mini: `/private/tmp/native-journey-mixed-mini-z2hfqmak`

최초 Claude 실제 init 결과는 시작 후 약 13분에 수집했다. 전체 혼합 업무 결과를 15분 안에 얻는 목표는 충족하지 못했고, 이후 기동 경계 진단과 독립 Codex 확인·증거 보존을 마쳤다.

근거는 [결과 JSON](results.json), [source manifest](source-manifest.json), [직접 MCP preflight](direct-mcp-preflight.json), [Claude 실제 events](claude-direct-native-events.json), [Book 증거](book-evidence/mixed-evidence.json), [mini 증거](mini-evidence/mixed-evidence.json), [Book 종료](book-cleanup.json), [mini 종료](mini-cleanup.json)에 있다. raw의 오류·모델·도구 원문은 수정하지 않았다. 설명·보고 본문은 지정한 CJK 정규식으로 검사했다.
