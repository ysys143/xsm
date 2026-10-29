<!-- 독립 비평 원문의 주장과 판정은 유지하고 링크 목적지만 정리함. -->
Reason에 대한 가장 강한 기소는 **네트워크 주소로 상대를 찾았다는 사실과, 그 상대가 쓰던 런타임 세션에 실제로 도달했다는 사실 사이를 충분히 드러내지 못한다**는 것이다. 같은 Codex 스레드에서 xsm 요청은 처리됐지만, Reason은 “세션에 큐 등록됨”이라고 응답한 뒤 실제 큐 등록에 실패했고, 정리 직전까지 약 26분 동안 미독·무응답으로 남았다. 데몬·신원·주소 체계가 추가됐어도 마지막 전달은 런타임의 홈·스레드·훅에 의존한다. 기존 세션으로 계속 일하려는 사용자에게 가장 중요한 이 경계가 친숙한 주소와 낙관적인 결과 문구 뒤에 가려진다. 이는 xsm의 직접 협업 목표를 기준으로 한 독립 비평이며, 어느 개발자나 관계자의 공식 견해도 아니다.

분석한 공개 엔진은 태그 `v0.12.10`, 커밋 `72ca2b3fb36d6e3cbfa44aa82c68d27aafe5e690`과 일치했다. 실행 증거의 버전은 Reason CLI `0.2.557`, 엔진 `0.12.10`, xsm `0.4.20`이다. 아래 `E`는 [evidence.json](/Users/jaesolshin/Documents/GitHub/cross-session-messaging/deliverables/xsm-reason-live-comparison-2026-10-23/evidence.json), `W`는 [reason-workflow-facts.json](/Users/jaesolshin/Documents/GitHub/cross-session-messaging/deliverables/adversarial-cross-review-2026-10-23/reason-workflow-facts.json)을 뜻한다.

**공격 1 — 사람과 세션의 주소는 찾았지만, 그 세션의 런타임 홈까지 보존하지 못한다.**

- **행동과 부담:** 사용자는 `~/.codex-3`에서 이미 사용하던 `cmp-codex`에게 일을 보낸다. Reason 주소는 `user/cross-session-messaging-codex-4`였다. `E.codex_same_session_binding`은 두 이름이 같은 스레드 `01a16866-7dc1-7260-afe0-be7d8d3bba5f`를 가리킴을 기록한다. Reason 데몬 오류에도 바로 그 스레드 ID가 나온다. 다른 세션을 잘못 비교한 사례가 아니다.
- **근거와 판정:** `E.reason_daemon_error_excerpt`에는 `no rollout found for thread id …; falling back to hooks`가 있다. `E.recorded_results["s6-reason-final-before-cleanup.json"]`에서는 요청 나이 `1566.196`초, `request_read_at:null`, `reply_count:0`이다. 공개 엔진은 대상 ID로 `codex queue`를 만들지만, 실행 시 대상별 `CODEX_HOME`을 지정하지 않는다. [명령 구성](https://github.com/reason-machines/reason-network/blob/72ca2b3fb36d6e3cbfa44aa82c68d27aafe5e690/src/daemon/mail.rs#L343), [프로세스 실행](https://github.com/reason-machines/reason-network/blob/72ca2b3fb36d6e3cbfa44aa82c68d27aafe5e690/src/daemon/mail.rs#L510).
- **xsm의 부담 배치:** xsm은 대상 레코드의 `home`을 전달하고, 큐 명령 환경에 `CODEX_HOME`을 설정한다. [send.py:237](/Users/jaesolshin/Documents/GitHub/cross-session-messaging/xsm/send.py:237), [adapters.py:172](/Users/jaesolshin/Documents/GitHub/cross-session-messaging/xsm/adapters.py:172). 같은 표본에서 xsm은 수신·과제 처리에 성공했고, 수신 세션의 CLI 회신이 샌드박스에 막히자 MCP로 회신했다. MCP 발신 당시에는 `sent-unconfirmed`였고, 이후 발신자가 실제 답을 읽었다. 근거는 `E.codex_native_events[6..9]`와 `calls[label="S3-and-S6-XSM-replies"]`다.
- **Reason의 합당한 반론:** 훅과 `check_inbox`라는 대체 경로가 있고, 메시지도 유실되지 않았다. 맞다. 그러나 추가 사용자 입력이 없던 관측 구간에서 유휴 수신은 회복되지 않았다. **이 표본의 전달 실패는 사실**, 홈 환경 누락이 원인이라는 설명은 코드와 잘 맞는 **추론**이다. 실제 데몬 환경을 확보하지 않았으므로 단일 원인으로 확정하지 않는다.

**공격 2 — “큐 등록됐다”는 결과가 큐 등록의 성공보다 먼저 나온다.**

- **행동과 부담:** 에이전트가 Reason 송신 결과를 읽고 상대가 처리할 것이라 판단해 다른 작업으로 넘어간다. S6의 결과는 “Codex 세션에 큐 등록됐으며 현재 턴 이후 또는 유휴 상태라면 지금 실행된다”는 뜻이었다. 실제 큐 등록은 실패했다.
- **근거와 판정:** 공개 엔진은 비동기 `send_with()`를 시작하고 즉시 `pushed`와 해당 문구를 반환한다. 큐 명령 성공 여부는 나중에 판정한다. 실패하면 로그를 남기고 `push_failed=true`, 전달 등급을 `Turn`으로 바꾼다. [선반환 경로](https://github.com/reason-machines/reason-network/blob/72ca2b3fb36d6e3cbfa44aa82c68d27aafe5e690/src/daemon/mail.rs#L384), [후속 실패 처리](https://github.com/reason-machines/reason-network/blob/72ca2b3fb36d6e3cbfa44aa82c68d27aafe5e690/src/daemon/mail.rs#L529). **반환 문구가 확보한 근거보다 강하다는 것은 소스와 실행 증거가 함께 뒷받침한다.**
- **xsm의 부담 배치:** xsm은 큐 등록과 수신 측 인계 기록을 구분하고, 영수증이 없으면 `sent-unconfirmed`를 반환한다. [send.py:248](/Users/jaesolshin/Documents/GitHub/cross-session-messaging/xsm/send.py:248). 이것은 상태 이름이 많아서 낫다는 주장이 아니다. 이 사례에서 호출자가 기다려도 되는지 판단할 근거가 달랐다는 뜻이다. xsm의 `delivered`도 모델의 이해·실행·사용자 승인·과제 성공을 증명하지 않는다.
- **Reason의 합당한 반론:** 내부 상태가 `delivered`가 아니라 `pushed`이고, 후속 호출에는 낮아진 전달 등급이 반영된다. 그러나 사용자에게 나온 자연어는 이미 큐 등록을 기정사실로 표현했다. 또한 공개 엔진은 CLI 성공 직후 메시지를 `read`로 표시하므로, 이 표시는 모델이 읽었다는 뜻으로도 사용할 수 없다. [mail.rs:535](https://github.com/reason-machines/reason-network/blob/72ca2b3fb36d6e3cbfa44aa82c68d27aafe5e690/src/daemon/mail.rs#L535). 최초 호출자에게 해당 메시지의 후속 실패가 자동 통지됐는지는 **미검증**이다.

**공격 3 — 같은 형태의 주소가 대화·프로세스·우편함이라는 서로 다른 수명을 가리킨다.**

- **행동과 부담:** 사용자가 다음 날 대화를 재개하거나, 다른 머신에서 같은 대화를 이어가거나, 같은 주소의 headless 에이전트에게 후속 질문을 보낸다. 이때 주소만 보고 이전 문맥과 미독 메시지가 유지된다고 판단할 수 없다.
- **근거와 판정:** 엔진은 식별 가능한 대화의 이름을 보존하지만, 기본적으로 마지막 관측 후 하루가 지나면 세션과 미독 메시지를 잊는다. 다른 머신에 나타난 같은 대화는 새 세션이며, 대기 메시지는 이전 머신에 남는다. 반대로 대화 ID가 없는 `proc:<pid>` 세션은 새 프로세스가 같은 이름과 미독 메시지를 물려받을 수 있다. 사람의 `listen` 우편함은 계속 보존된다. [수명 규칙](https://github.com/reason-machines/reason-network/blob/72ca2b3fb36d6e3cbfa44aa82c68d27aafe5e690/DESIGN.md#L59), [미독 삭제 구현](https://github.com/reason-machines/reason-network/blob/72ca2b3fb36d6e3cbfa44aa82c68d27aafe5e690/src/store.rs#L525).
- **xsm의 부담 배치:** xsm은 이미 종료된 대상에 보내기를 거부하고 재개 안내를 돌려준다. [send.py:171](/Users/jaesolshin/Documents/GitHub/cross-session-messaging/xsm/send.py:171). 기존 런타임의 대화와 실행 상태를 직접 상대하는 방식이다. 그 대신 Reason처럼 주소별 오프라인 우편함을 제공하는 이점은 줄어든다. xsm 역시 머신 간 대화 이동이나 무기한 문맥 보존을 보장한다고 주장할 수 없다.
- **Reason의 합당한 반론:** 이는 다른 대화에 과거 메시지를 잘못 넘기지 않기 위한 명시적인 설계다. 실제로 재접속 순서가 바뀌어도 원래 대화가 이름과 메시지를 되찾는 테스트가 있다. [재접속 테스트](https://github.com/reason-machines/reason-network/blob/72ca2b3fb36d6e3cbfa44aa82c68d27aafe5e690/src/daemon/sessions.rs#L700). 반론은 타당하다. 따라서 **오배송 결함이라는 공격은 성립하지 않는다.** 남는 공격은 범용 주소의 수명 계약이 런타임마다 다르다는 제품 비용이다.

비공개 CLI의 `network serve`는 실제로 존재하며 로컬 Claude/Codex 수신 에이전트 실행도 확인된 사실이다. [인터페이스:16](/Users/jaesolshin/Documents/GitHub/cross-session-messaging/deliverables/adversarial-cross-review-2026-10-23/reason-cli-interface.txt:16). 다만 같은 serve 주소의 후속 요청이 같은 네이티브 런타임 대화를 재사용하는지까지는 지정 자료로 확인되지 않는다. `W`의 두 rollout은 `baseline` 자료이므로 serve의 문맥 단절 증거로 사용할 수 없다. 반대로 공개 엔진에는 CLI의 일회성 `ask-*` 세션과 지속 우편함을 구분하는 테스트가 있다. [sessions.rs:834](https://github.com/reason-machines/reason-network/blob/72ca2b3fb36d6e3cbfa44aa82c68d27aafe5e690/src/daemon/sessions.rs#L834).

**공격 4 — 현재 작업의 협업 범위를 정하는 일이 머신의 네트워크 편입과 제외 관리로 바뀐다.**

- **행동과 부담:** 한 컴퓨터에서 회사 저장소와 개인 저장소를 번갈아 사용하는 사람이 네트워크에 가입한다. 이후 Reason이 연결된 세션의 저장소·브랜치·상태·작업 설명이 팀 디렉터리에 나타나는 범위를 관리해야 한다. 대화 제목과 진행 중 작업은 에이전트가 별도로 보고하지 않아도 추출된다. [doing.rs:29](https://github.com/reason-machines/reason-network/blob/72ca2b3fb36d6e3cbfa44aa82c68d27aafe5e690/src/doing.rs#L29).
- **근거와 판정:** 기본 수신 정책은 팀 내 `Accept`, 폴더 제외 규칙은 비어 있다. `share_paths=false`는 전체 경로 공유를 줄이고, `share_unmanaged=false`는 Reason이 없는 Claude 세션의 공유를 제한한다. 이를 모든 세션의 무조건 공개로 과장하면 안 된다. 그러나 등록된 세션의 공개 범위를 줄이는 폴더 규칙은 현재 `off`이며, 해당 폴더 세션을 네트워크에서 제외한다. [기본값](https://github.com/reason-machines/reason-network/blob/72ca2b3fb36d6e3cbfa44aa82c68d27aafe5e690/src/config.rs#L56), [폴더 규칙](https://github.com/reason-machines/reason-network/blob/72ca2b3fb36d6e3cbfa44aa82c68d27aafe5e690/src/config.rs#L24). 이는 **침해 증거가 아니라 협업 범위를 배치한 방식의 차이**다.
- **xsm의 부담 배치와 반대 증거:** xsm은 같은 저장소의 동료에게 기본적으로 열리고, 다른 저장소 연결을 별도로 관리한다. 부모·자식만 허용하는 철학이 아니다. [INTENT.md:5](/Users/jaesolshin/Documents/GitHub/cross-session-messaging/INTENT.md:5), [config.py:350](/Users/jaesolshin/Documents/GitHub/cross-session-messaging/xsm/config.py:350). 그러나 이번 S5에서는 그 경계가 명백한 사용성 실패가 됐다. 실제 사용자가 연결을 허용했는데 승인 텍스트가 기록되지 않았고, 정상 재실행과 `--reply` 대체 모두 실패했다. `E.approval_ingestion`과 `recorded_results["xsm-approval-explicit-reply1.json"]`이 근거다. Reason은 추가 폴더 연결 없이 gamma와 실제 왕복했다.
- **Reason의 합당한 반론:** 네트워크 가입 자체가 팀 협업에 대한 선택이며, 저장소마다 연결을 반복하지 않는 것이 장점이다. 이번 S5가 그 반론을 지지한다. 따라서 공격은 “승인을 우회했다”가 아니다. **편리한 기본 연결의 대가로 현재 작업과 공유 대상의 경계를 사용자가 따로 관리한다**는 것이다.

계정의 `verified`는 사람과 머신의 신원에 관한 표시이며, 특정 과제에 대한 사용자 승인과 다르다. [team.rs:218](https://github.com/reason-machines/reason-network/blob/72ca2b3fb36d6e3cbfa44aa82c68d27aafe5e690/src/team.rs#L218). Reason은 별도로 `ask_user`의 실제 사람 응답을 서명하고, 수신자는 `from`과 `about`을 대조하도록 한다. 이것을 에이전트의 “승인받았다”는 문장과 같은 것으로 취급해서는 안 된다. [승인 검증 테스트](https://github.com/reason-machines/reason-network/blob/72ca2b3fb36d6e3cbfa44aa82c68d27aafe5e690/src/daemon/mail.rs#L1148).

**공격 5 — 연결된 에이전트가 선택할 수 있는 협업 방식은 인터페이스마다 다르다.**

- **행동과 부담:** 에이전트가 여러 동료에게 같은 검토를 요청하거나, 지금 깨우지 않고 다음 작업 때 참고할 정보를 남기려 한다. 그룹 주소는 있지만 에이전트의 그룹 송신은 거부된다. MCP `send_message`에는 FYI 인자가 없고 항상 `wake:true`를 보낸다. [그룹 거부](https://github.com/reason-machines/reason-network/blob/72ca2b3fb36d6e3cbfa44aa82c68d27aafe5e690/src/daemon/mail.rs#L160), [MCP 송신](https://github.com/reason-machines/reason-network/blob/72ca2b3fb36d6e3cbfa44aa82c68d27aafe5e690/src/mcp.rs#L169).
- **근거와 판정:** CLI에는 실제 `--fyi`가 있다. `W["logs/fyi-observation.json"]`에서 82.08초 동안 새 턴이 없었고, 저장 기록은 `wake:0`, `read_at:null`이었다. 즉 **FYI가 없는 것이 아니라, 에이전트의 기본 MCP 인터페이스에서 표현할 수 없는 것**이다. 그룹 검토는 개별 송신과 응답 취합으로 풀어야 한다.
- **xsm의 부담 배치:** xsm도 현재 `xsm_send`는 단일 대상이고, `kind=note`가 무기상 전달을 보장하지 않는다. 다만 공유 기록을 남기는 `xsm_post`와 읽는 `xsm_channel` 경로가 코드에 별도로 있다. [mcp.py:377](/Users/jaesolshin/Documents/GitHub/cross-session-messaging/xsm/mcp.py:377). 이는 xsm의 N:N 기능 전체가 검증됐다는 뜻이 아니다. 이번에 확인된 것은 두 도구 모두 동료 간 직접 검토와 회신에 성공했다는 사실이다.
- **Reason의 합당한 반론:** 그룹 거부는 소음과 무분별한 방송을 줄이며, 개별 송신으로 N:N 관계를 만들 수 있다. 맞다. 따라서 “Reason은 N:N 소통이 불가능하다”는 공격은 철회한다. 남는 것은 **같은 협업 의도를 실행하려면 MCP·CLI·개별 송신 사이의 기능 차이를 에이전트가 알아야 한다**는 비용이다.

**공격 6 — 세션 식별은 호출별인데, 첨부 파일의 작업 폴더는 MCP 프로세스 기준이다.**

- **행동과 부담:** 저장소 A에서 시작한 MCP 프로세스를 저장소 B의 대화도 공유한다고 하자. B의 에이전트가 B의 정상적인 소스 파일을 첨부한다. 호출자 세션은 B로 식별돼도 파일 읽기는 A 기준으로 제한될 수 있다.
- **근거와 판정:** 설계는 Codex·opencode·Cursor의 한 MCP 프로세스가 여러 세션을 처리해야 한다고 명시한다. [DESIGN.md:118](https://github.com/reason-machines/reason-network/blob/72ca2b3fb36d6e3cbfa44aa82c68d27aafe5e690/DESIGN.md#L118). 그런데 `send_message`는 호출별 세션 키를 구한 뒤에도 그 키를 `agent_files()`에 넘기지 않는다. 파일 루트는 `agent::cwd()`에서 다시 구한다. 그 함수는 `CLAUDE_PROJECT_DIR` 또는 프로세스 현재 디렉터리를 사용한다. [mcp.rs:160](https://github.com/reason-machines/reason-network/blob/72ca2b3fb36d6e3cbfa44aa82c68d27aafe5e690/src/mcp.rs#L160), [파일 루트](https://github.com/reason-machines/reason-network/blob/72ca2b3fb36d6e3cbfa44aa82c68d27aafe5e690/src/mcp.rs#L403), [agent.rs:197](https://github.com/reason-machines/reason-network/blob/72ca2b3fb36d6e3cbfa44aa82c68d27aafe5e690/src/agent.rs#L197). 루트 밖 파일은 거부된다. [files.rs:70](https://github.com/reason-machines/reason-network/blob/72ca2b3fb36d6e3cbfa44aa82c68d27aafe5e690/src/files.rs#L70).
- **xsm의 부담 배치:** xsm의 핵심 메시징은 텍스트와 경로를 보내고, 수신 런타임이 자기 권한으로 자료를 읽는 방식이다. 같은 머신에서는 경로를 그대로 쓸 수 있지만 원격 파일 복사 문제는 별도로 남는다. Reason의 작은 텍스트 파일 전송은 이 점에서 실제 추가 기능이다. xsm도 호출자 메타데이터가 없으면 최신 세션 레코드를 고르는 대체 경로가 있으므로 문맥 식별이 완전하다고 주장할 수 없다. [mcp.py:332](/Users/jaesolshin/Documents/GitHub/cross-session-messaging/xsm/mcp.py:332).
- **Reason의 합당한 반론:** 파일 제한은 에이전트가 읽지 못할 자료를 MCP가 대신 반출하는 일을 막기 위한 것이다. 크기·숨김 파일·프로젝트 제한 자체는 합리적이다. 그러나 **의도적인 파일 제한과 호출자의 작업 폴더를 잘못 선택하는 문제는 구분해야 한다.** 서로 다른 저장소가 실제로 한 MCP 프로세스를 공유하는 실행은 이번에 재현하지 않았다. 따라서 이는 소스에서 도출한 **조건부 결함 후보**이며, 실제 오전송이나 정보 유출로 판정하지 않는다.

확정 가능한 것과 선택의 대가는 다음처럼 구분된다.

| 구분 | 판정 |
|---|---|
| 실행으로 확인된 실패 | 동일 Codex 스레드의 Reason 요청이 큐 등록 실패 후 관측 종료까지 미독·무응답으로 남았다. |
| 소스와 실행이 일치하는 문제 | 실제 큐 등록 성공 전에 성공을 전제하는 결과 문구를 반환한다. |
| 조건부 결함 후보 | 공유 MCP 프로세스에서 호출자별 파일 루트가 분리되지 않는 경로다. 실제 해당 실행 구성은 미검증이다. |
| 제품 선택의 대가 | 하루 단위 세션 만료, 프로세스 주소의 인계, 머신 단위 참여와 폴더 제외, 그룹 송신 제한, MCP의 FYI 부재다. |

공개 엔진은 **MIT OR Apache-2.0**이며 계정 없이 단독 실행하는 경로가 있다. 로그인·클라우드가 모든 통신에 필수라는 공격은 성립하지 않는다. [라이선스](https://github.com/reason-machines/reason-network/blob/72ca2b3fb36d6e3cbfa44aa82c68d27aafe5e690/README.md#L125), [단독 실행](https://github.com/reason-machines/reason-network/blob/72ca2b3fb36d6e3cbfa44aa82c68d27aafe5e690/DESIGN.md#L416). 비공개 CLI는 인터페이스 스냅샷과 실행 결과까지만 평가했다. `serve` 내부의 대화 재사용, 재시작 복구, 실행 권한 처리는 소스로 검증하지 못했다. 두 도구 모두 같은 uid의 악성 소프트웨어를 막는 보안 경계로 평가하지 않았다.

공격을 철회하거나 줄일 조건은 다음과 같다.

| 공격 | 필요한 확인 |
|---|---|
| 1 | 같은 다중 홈 구성에서 주소·스레드·대상 홈을 대조하고, 추가 사용자 입력 없이 큐 등록과 실제 응답이 회복됨을 확인한다. 홈 누락이 원인이 아니면 그 원인 추론은 철회한다. |
| 2 | 최초 결과가 실제 큐 등록 여부와 일치하고, 이후 실패도 같은 메시지 ID로 발신자에게 관측됨을 확인한다. |
| 3 | 주소가 보장하는 대상과 만료·이동 조건을 일반 조회·송신 결과만으로 판단할 수 있으면 “수명 차이를 숨긴다”는 공격을 줄인다. serve의 문맥 지속성은 네이티브 세션 ID와 후속 기억으로 별도 검증한다. |
| 4 | 기존 세션을 유지하면서 참여·메타데이터 공유 범위를 사용자가 의도한 작업별로 통제할 수 있음을 확인하면 경계 관리 부담에 대한 공격을 줄인다. |
| 5 | 실제 에이전트 인터페이스에서 무기상 전달과 승인된 복수 대상 협업을 표현할 수 있으면 인터페이스 불균형 공격을 철회한다. |
| 6 | 서로 다른 작업 폴더가 프로세스를 공유하지 않거나, 공유하더라도 파일 루트가 호출자 세션의 폴더로 결정됨을 확인하면 철회한다. |

우선순위는 세 가지다.

1. **대상 런타임 바인딩 검증:** 주소·스레드 ID뿐 아니라 대상 홈·전달 경로까지 연결해 다중 홈과 기존 유휴 세션에서 검증한다. 공격 1과 6이 대상이다.
2. **송신 결과를 실제 증거와 일치시키기:** 실행 예정, 큐 등록 성공, 런타임 인계, 과제 응답을 구분하고 비동기 실패를 메시지 ID로 추적할 수 있게 한다. 공격 2가 대상이다.
3. **기존 세션에서 주소와 협업 방식의 계약 명확화:** 주소 수명·문맥 지속성·공유 범위·FYI·그룹 제한을 실제 도구 인터페이스에서 판단할 수 있는지 점검한다. 공격 3~5가 대상이다.

검증에서는 pinned 커밋·태그를 직접 대조했고, JSON의 동일 스레드 바인딩과 오류의 스레드 ID 일치, 요청 수신 주소와 최종 미독 기록의 일치를 확인했다. xsm에 불리한 승인 수집 실패와 Reason의 저장소 간 왕복 성공을 포함했으며, 같은 저장소에서의 양쪽 성공도 제외하지 않았다. 한 머신의 공존 표본이고 일부 송신은 사전 허용됐으므로 범용 안정성·보안성·속도 우열은 판정하지 않았다.

지정 코드·인터페이스·원시 증거와 관련 테스트 정의만 읽었다. 다른 비평가나 설명 보고서는 읽지 않았고, 위임·네트워크 접근·MCP 호출·메시지 송신·워커 실행·설치·권한 변경·파일 수정은 하지 않았다. 테스트 정의는 정적으로 대조했으며 실행하지 않았다. 공격 6건, 각 반론과 철회 조건, 우선순위 3건을 작성했고 산출물은 이 응답에만 남겼다.
