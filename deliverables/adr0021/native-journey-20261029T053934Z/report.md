# ADR-0021 두 물리 Mac native workflow: 원질문 보존, 미완

2026-10-29 05:38–05:52 UTC에 실제 MacBook 요청자와 jaesol-macmini 검토 담당 a1을 실행했다. 요청자는 실제 MCP 발견 결과에서 원격 a1을 선택하고 핸드셰이크 요청을 전송했다. mini에는 동일 본문의 canonical 원본이 저장됐지만 실제 상관 회신과 소비 ACK는 없었다. `xsm_connect` 호출 반환을 핸드셰이크 완료로 판정하지 않는다. 2+2=5 검토와 수정안 2+2=4 재검토는 시작하지 못했다.

coordinator의 Opus 검토에서 전달된 F3, 즉 배달 당시 receiver generation에 admission이 묶여 같은 CID 재개 뒤 저장 메시지 소비가 막히는 결함 때문에 사용자가 새 재시도를 중단시켰다. 이 실험이 F3를 독립적으로 재현·수정했다고 주장하지 않는다. 원질문·기존 서비스 state/key를 보존했고 CID·질문 인덱스·본문·권한·ACK는 수동 보정하지 않았다.

## 동결 조건

현재 저장소의 Python `xsm/**/*.py` 52개를 파일별로 복사하고 복사 직전·직후 bytes 일치를 확인했다. 전체 저장소 상태의 원자적 동결이 아니다. native Rust 소스·다른 저장소 파일·사용자 profile을 고정한 결과로 해석하지 않는다.

- [source manifest](source-manifest.json) SHA-256: `e6669ed7f0270ca7f580858ccfa9b15aeffc7f6fc2e73ba1d628286aabb8d7d1`
- 복사 시점 `network.py`에는 coordinator가 알린 native observer TypeError 처리와 wake_safely callback 예외 출력 억제가 포함돼 있다. 이후 Opus 결함 수정본의 동결·실행은 이번 결과에 포함하지 않는다.
- engine 원본: `/private/tmp/adr21-install-0q83fzpr/state/network/bin/xsm-net`. release engine의 실제 SHA·크기는 manifest에 있다. Rust loopback relay 정책 변경 전 바이너리이며 이번 관측은 LAN direct다.
- 양쪽 private payload의 Python 52개 SHA가 manifest와 일치했다. [Book](book-final-observation.json), [mini](mini-final-observation.json).

## 실행·권한·인증 조건

각 호스트의 `/private/tmp`에 별도 work Git 저장소, XSM_HOME, 임시 CODEX_HOME, Unix socket, native runtime 복사본을 만들었다. 기존 전역 repo/profile/hooks/권한/SSH/Tailscale 설정을 변경하는 명령은 실행하지 않았다. SSH는 provisioning·실행 제어·관측용으로만 사용했다. 다른 actor에게 메시지 본문을 전달하는 wrapper 또는 SSH 본문 relay는 없었다.

기존 `/Users/jaesolshin/.codex-3/auth.json`을 임시 CODEX_HOME의 `auth.json` 심볼릭 링크로 참조했다. controller는 자격 증명 값을 읽거나 복사하지 않았다. 실제 provider DB와 rollout은 임시 CODEX_HOME 안에 생겼다. 기존 profile의 config.toml/hooks.json/settings.json/AGENTS.md SHA와 auth 파일의 metadata-only 전후 관측이 두 호스트 모두 동일했다. 기존 profile로 향하는 쓰기는 관측되지 않았다. API key 환경변수는 자식 환경에서 제거했고, API 과금 경로를 지정하지 않았다.

`codex exec --ignore-user-config --json --sandbox workspace-write`와 `approval_policy="never"`를 사용했다. dangerously flags와 임의 모델명 지정은 없었다. 임시 MCP override는 현재 동결본을 실행한다. 모델에게는 한국어 역할·산술 검토 업무 목표만 주었고 도구 호출 순서, 도구 이름, 예상 회신을 추가하지 않았다. 도구 목록과 제품 핸드셰이크 문구는 실행한 서버가 제공했다.

private node init/join과 양쪽 work 저장소의 peer/repository mapping은 operator 소유 setup이다. 이 mapping의 same-repository scope로 발견과 통신이 허용됐다. 네트워크 가입만으로 권한이 생긴 결과나 새로운 사용자 협업 동의를 취득한 결과가 아니다. 실제 xsm_connect 인자는 `candidate:adab7d5bbefff92baadb07edccd2b1a9bc0f82ea8337f5139ad03b13defc1e6b`였다. 실제 native가 발견 후보의 `candidate:<id>`를 선택해 서버의 원격 net 주소 재해석 경로를 실행했다.

초기 등록은 실제 thread.started CID, 실제 provider DB row/cwd, live native PID와 MCP ancestry가 맞는 경우에만 registry.upsert로 수행했다. 최초 Book의 등록 timing 경합 실패는 원본으로 보존했다. 재개 조건의 관측 proxy startup barrier는 초기 tools/list 전달만 잠깐 지연하며 도구 결과·본문·ACK를 바꾸지 않는다. 이 조건은 초기 등록을 갖춘 controlled native 평가이며 무보정 onboarding 성공으로 확대하지 않는다. MCP wire의 각 원래 bytes와 관측 SHA를 대조해 불일치 0건이었다.

새 버전 native 수신 hook이 실제 실행됐다는 관측은 없으므로 자동 wake 성공은 주장하지 않는다. 계획한 수신 경로는 MCP pull이었으나 mini의 실제 inbox 소비까지 도달하지 못했다.

## 실제 actor와 원질문

| 항목 | 관측값 |
|---|---|
| Book 요청자 CID | `01a1862f-2822-7113-8cd2-e930587f1100` |
| mini a1 CID | `01a1862d-c1f7-73d2-b616-f34d78d81772` |
| 원질문 ID | `ed42ef075aff4b47` |
| 질문 purpose | `handshake` |
| mini canonical 상태 | `pending` |
| 실제 상관 회신 / 소비 ACK | 0건 / 없음 |
| 산술 검토 질문 전송 | 0건 |
| 양쪽 실제 관측 model ID | `gpt-6.1-sol` |

모델 ID는 각 실제 provider rollout의 turn_context에서 읽었다. 모델명을 지정하거나 출력에서 추정하지 않았다. 원질문 본문과 수신 canonical 본문은 bytes가 같은 문자열이었다. [결과 JSON](results.json)의 `original_request`와 양쪽 `preserved-evidence.json`에 본문·원래 질문 index·gateway packet·handoff를 보존했다. 실제 receipt body는 확보하지 못했으며 저장 원문만으로 실제 수신·읽음·업무 회신을 주장하지 않는다.

Book은 최초 실패를 포함해 실제 xsm_discover 2회, xsm_connect 1회, xsm_question_status 6회를 호출했다. mini는 native tool negotiation 단계에서 막혀 xsm 업무 도구 호출 0회다. 실제 메시지 전송 후 경로 관측은 양쪽 모두 LAN direct였다. Book의 상대 주소는 `192.168.0.64:60431`, mini의 상대 주소는 `192.168.0.11:52889`였다. 실제 deliver의 발신 본문 SHA와 mini의 Rust 수신 본문 SHA 및 TLS origin 대조는 결과 JSON의 `p2p_deliver_evidence`에 있다. 서로 다른 NAT·공개 relay·Tailnet 강제 경유의 검증으로 해석하지 않는다.

## 실패 조건 분리

1. 최초 Book은 thread.started 후 허용된 초기 등록을 관측하기 전에 discover를 호출해 `no hook record`로 정상 종료했다. 실패 raw를 `book-evidence/initial-unregistered`에 보존했다. 네트워크 setup을 마치고 launch 직후 등록을 관측하는 조건으로 요청자 한 번을 새로 시작했다. 같은 잘못된 조건을 반복하지 않았다.
2. mini의 기존 실제 CLI는 `codex-cli 0.163.0`이었다. xsm initialize와 tools/list 응답은 정상인데 `timed out negotiating with the code-mode host`가 4번 발생했다. 해당 actor를 종료했고 원본은 `mini-evidence/code-host-first-attempt`에 보존했다.
3. 관측된 feature `code_mode_host`의 실행 한정 disable override로 같은 CID를 재개했으나 `code-mode host is disabled`가 발생해 멈췄다. 이것은 도구 협상 호환성 조건이며 permission/sandbox 완화가 아니다. 원본은 `mini-evidence/disabled-host-resume`에 있다.
4. 실제 Book의 0.164.0 executable과 인접 `codex-code-mode-host`를 mini private/tmp에 복사했다. 글로벌 설치는 하지 않았다. 동일 reviewer CID의 이 runtime 재개는 F3 중단 지시가 도착하기 직전에 시작돼 있었으며 소유 PID 19576을 즉시 TERM했다. 이후 재시도는 0회다. 0.164.0 재개 모델은 연결이 복구됐지만 협업 도구가 보이지 않는다고 응답했으며, 실제 xsm 업무 도구 성공은 입증하지 못했다. [runtime metadata](mini-private-native-runtime.json).

## 보존과 정리

모든 시도의 기록된 actor/native/MCP proxy/server PID를 PID+lstart로 대조했다. 양쪽 actor 관련 잔여는 0개다. 사용자가 F3 수정 후 원질문을 회복할 수 있도록 Python service와 Rust engine은 종료하지 않았다.

| 호스트 | private root | 보존 Python / Rust PID |
|---|---|---|
| Book | `/private/tmp/xnj-book-pgg7eseo` | `17188` / `17209` |
| mini | `/private/tmp/xnj-mini-gl2ut38t` | `94209` / `94211` |

각 호스트의 node.secret는 원래 호스트 private state에만 보존했다. 값은 열거나 복사하지 않았고 mode 0600, 부모 mode 0700의 metadata만 확인했다. 초대의 secret은 argv·보고서·모델 문맥에 넣지 않았다. private 초대 파일을 SSH stdin으로 join에 전달했다.

현재 결과는 미완이다. 같은 원질문을 회복하려면 coordinator의 generation/admission 수정본을 새 manifest로 동결하고, 보존한 state/key에서 service/MCP를 재시작한 뒤 같은 실제 CID를 재개해야 한다. 사용자의 새 재시도 금지 지시 이후 이 단계는 실행하지 않았다. 이 보고서의 profile·wire·원문·PID 대조는 [분석 코드](analyze.py), [증거 보존 코드](preserve.py), [최종 관측 코드](final-observe.py)와 [전체 결과](results.json)로 확인한다.
