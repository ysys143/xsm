# P11 원격 백엔드 공통 비교 계획 — A/B/C/D 기록 형식과 이 환경의 확보 조건

- 상태: **조사·비교 기록 형식 확정 단계**. P11 완료도, G11 통과도 아니다.
- 기준 revision: 이 저장소 커밋 `4fd7c9f` (branch main). 조사 중 제품 코드·테스트·git 추적 상태를 바꾸지 않았다.
- 이 문서가 정하는 것: A(기존 SSH 개선안) / B(자체 P2P) / C(공개 Reason 엔진) / D(VPN+SSH)를 같은 형식으로 적는 표, 이 머신에서 실제로 만들 수 있는 조건과 없는 조건의 구분, C에 대한 기존 증거의 항목화, D의 설치·경로 확인, G11 종료 조건 대비 미완 목록.
- 이 문서가 정하지 않는 것: 제품 백엔드(D12)의 선택, `xsm/remote.py`의 제품 변경, 후보의 우열.
- 이 환경의 두 물리 머신(아래 조사에서 실제로 사용):
  - A측: `Jaesolui-MacBookPro.local` (이 세션이 도는 머신). LAN `192.168.0.11`, 테일넷 `100.123.30.11`.
  - B측: `Jaesolui-Macmini.local` (SSH 너머 머신). LAN `192.168.0.64`, 테일넷 `100.77.24.16`.
  - 두 머신의 외부 주소는 모두 `210.113.21.16` (`curl https://ifconfig.me`를 양쪽에서 각각 실행해 확인).

## 0. 요약 판정

이 머신에서 **지금 바로 만들 수 있는 조건**은 LAN, 같은 NAT, 양방향 SSH다. 그 위에서 A(기존 SSH)와 D(VPN+SSH)는 이미 실물 경로가 있다. **만들 수 없는 조건**은 다른 NAT, UDP 차단, 자체 relay, 양방향 SSH 불가다. HTTPS 프록시는 SSH 경로에 한해 사용자 수준에서 재현했다. C(공개 Reason 엔진)는 이 머신에만 설치돼 있고 상대 머신에는 없어 **두 머신 왕복은 미확보**다. B(자체 P2P)는 이번에 구현물이 없어 **미착수**다.

한 가지 중요한 사실: 이 머신의 A는 **이미 테일넷 위에 얹혀 있다**. `~/.ssh/config`의 `Host jaesol-macmini`가 `HostName jaesol-macmini.tail13f006.ts.net`을 가리키므로, xsm의 원격 짝(`~/.xsm/config.json`의 `remotes[0].host = "jaesol-macmini"`)은 Tailscale 주소로 연결된다(`xsm/remote.py:180`이 `ssh -G`에서 `hostname`·`proxyjump`·`proxycommand`를 그대로 읽는다). 따라서 현재 상태의 A와 D는 같은 물리 경로를 쓰며, 둘을 **구분하는 표본은 아직 없다**. LAN 직접 주소(`192.168.0.64`)로도 SSH가 되므로, VPN 없이 LAN만 쓰는 A는 별도로 만들 수 있다.

## 1. 비교 기록 형식 (A/B/C/D 공통 필드)

같은 두 물리 머신, 같은 업무, 같은 과제로 네 후보를 적는다. 각 항목은 "무엇을 기록하는가"까지 고정한다.

| 필드 | 기록 내용 | 판정 기준 |
|---|---|---|
| 설치 입력 | 사람이 입력한 설치 명령·URL·링크, 계정 생성 필요 여부, 설치가 건드린 파일(에이전트 설정·훅·서비스) | 명령 원문과 종료 코드. "설치됨"이 아니라 "무엇을 실행했는가" |
| 기존 전제 | 시작 전에 이미 있어야 하는 것(양방향 SSH, 사설 VPN, 공개 계정, 열려 있는 포트, 열린 세션) | 전제를 충족하지 않은 실행은 그 후보의 실패가 아니라 **미실행**으로 적는다 |
| 사람의 실제 조작 수 | 사람이 직접 누른/입력한 횟수와 종류(로그인·동의·훅 신뢰·포트 개방·초대 수락). 측정 못 했으면 "미측정" | 채팅 승인 1건과 브라우저 로그인 1건을 한 수로 합치지 않는다 |
| 에이전트 도구 호출 수 | 그 왕복에 실제로 들어간 도구 호출(예: `list_team`·`send_message`·`xsm_send`·`xsm_inbox`)의 이름과 횟수 | 호출 수는 왕복 성공의 증거가 아니다 |
| 첫 왕복 성공 여부 | 질문 본문이 상대 런타임에 **도달해 실제 답이 이쪽으로 돌아왔는지**. 전달 영수증만 있으면 "미완" | 영수증(`queued`·`delivered`)과 답 도착을 따로 적는다 |
| 경로·포트 | 실제로 성립한 경로(LAN/테일넷/릴레이/프록시/SSH)와 포트, 실패 뒤 대체한 포트 | "설정한 포트"가 아니라 "실제로 붙은 경로" |
| 재연결 | 데몬·세션·네트워크 재시작 뒤 같은 대상으로 다시 왕복되는지 | 자동 재접속 로그와 실제 재왕복을 구분 |
| 제거 | 중지·제거 뒤 남는 리스너·서비스·키·설정 항목 | 제거 후 소유 프로세스·`authorized_keys` 항목·설정 잔여를 실제로 확인 |
| 로그 공개 범위 | 설치·운영 로그에 남는 것(초대 링크, 계정·머신 이름, 경로, 키 지문, 세션 목록) | 로그 자체를 공개 산출물에 넣지 않고, 무엇이 남는지만 적는다 |

표의 열은 다음으로 고정한다.

**후보 | 설치 입력 | 사용자 개입 | 첫 왕복 증거 | 상태(가능/불가/미확보) | 이 환경에서 확인한 근거**

### 판정 규칙 (필수)

**자동 설정 로그만으로 연결 성공을 판정하지 않는다.** `doctor`의 "wired up", 설치 스크립트의 종료 코드 0, `paired …; both directions reach` 문구, `queued`·`delivered` 영수증, 데몬의 "registered"/"on relay" 로그는 **설정·전달 단계의 증거**일 뿐이다. 연결 성공은 별도로 (a) 상대 런타임이 본문을 읽고 (b) 답이 이쪽으로 돌아온 것까지 확인했을 때만 적는다. 이 규칙은 기존 조사가 이미 위반 사례를 기록해 둔 지점이기도 하다 — Reason이 `queued`를 반환했지만 데몬 로그에는 대상 스레드의 rollout을 찾지 못했다는 오류가 남았고, 26분 뒤에도 읽히지 않았다(`deliverables/xsm-reason-live-comparison-2026-10-23.md`, S6·J22).

## 2. 이 환경에서의 후보 실체

| 후보 | ADR-0021 정의 | 이 머신의 현재 실체 |
|---|---|---|
| A 기존 SSH 개선안 | 기존 SSH 설정·짝짓기·진단을 개선 | xsm의 강제 명령 SSH. `~/.xsm/config.json` `remotes[0]`(peer `Jaesolui-Macmini`, host `jaesol-macmini`, project `xsm`), `~/.xsm/remote/`에 xsm 전용 키와 수신기 사본. `xsm/remote.py` |
| B 자체 P2P | xsm 전용 선택적 P2P 엔진 | 없음. 구현물·spike 미착수 |
| C 공개 Reason 엔진 | 공개 엔진을 선택적 전송 백엔드로 연결 | `~/.reason/bin/reason-network` 0.12.10(이 머신에만). 데몬 실행 중, 팀 `Jaesol's network`에 다른 머신 0대 |
| D VPN+SSH | 사설 VPN 위에서 기존 SSH 사용 | Tailscale 1.105.110 설치·실행 중. A의 SSH 대상이 이미 테일넷 주소 |

## 3. 후보 비교표

값이 비어 있거나 "미측정"인 칸은 이번 조사에서 채우지 못한 것이다. 미확보 칸을 성공으로 메우지 않는다.

| 후보 | 설치 입력 | 사용자 개입 | 첫 왕복 증거 | 상태 | 이 환경에서 확인한 근거 |
|---|---|---|---|---|---|
| A 기존 SSH (LAN 직접) | 상대에서 `xsm remote add <host> --project <name>` 1회. 양쪽에 xsm 설치 전제 | 짝짓기 1회(터미널 또는 `xsm_grant remote`). 로그인·가입 없음 | 이번 세션 신규 왕복 **미실행**. 과거 실사용 증거는 테일넷 경로로 존재(아래 행) | **가능**(조건 확보) / 왕복 재실행 **미완** | LAN TCP·UDP 왕복 확인(4절). `ssh jaesolshin@192.168.0.64 hostname` → `Jaesolui-Macmini.local`. `xsm remote add`가 요구하는 양방향 SSH 성립(`xsm/remote.py:275-285`의 ping-back) |
| A 기존 SSH (현재 설정 = 테일넷 경유) | 위와 같음. 단 `~/.ssh/config`의 HostName이 `jaesol-macmini.tail13f006.ts.net` | 위와 같음 | **있음(과거 실행 기록)**. macmini→macbookpro 방향 `send` op가 실제로 served됨 | **가능** | `~/.xsm/otel-spans.jsonl`: `xsm.remote.serve` 250건(peer `Jaesolui-Macmini`), op별 `send` 97·`status` 147·`sessions` 15·`ping` 1·`ping-back` 2. `xsm.result.status`가 `delivered`/`queued`. `~/.xsm/remote/inbound-*.json` 수신 영수증 36개. macmini 원장에 `to.runtime=="remote"` 85행 |
| B 자체 P2P | 미정(설계 전) | 미정 | **미실행** | **미착수** | 구현물 없음. P11 spec 2항의 "최소 spike"가 아직 없다 |
| C 공개 Reason 엔진 | 공식 한 줄 설치 + 브라우저 로그인·가입(이 머신에서는 완료 상태) | 계정 가입·훅 신뢰 승인(기존 조사에서 사용자 1건 확인) | **미확보**. 상대 머신에 엔진이 없어 두 머신 왕복 불가 | **미확보**(단일 머신 증거만) | `~/.reason/bin/reason-network doctor` → "team Jaesol's network with 0 other machine(s)". macmini에 `~/.reason` 없음(`ssh jaesol-macmini 'ls ~/.reason'` → No such file). 단일 머신 증거는 5절 |
| D VPN+SSH | Tailscale 앱 설치·계정 로그인. SSH는 A와 동일 | Tailscale 로그인(완료 상태). SSH 짝짓기는 A와 동일 | A(테일넷 경유) 행과 같은 물리 경로. **A와 분리된 표본 없음** | **가능**하나 A와 **미구분** | `/Applications/Tailscale.app`, 버전 1.105.110(dev), `tailscale status` → macmini `active; direct 192.168.0.64:41641`. `tailscale ping jaesol-macmini` → `via 192.168.0.64:41641 in 47ms` |

## 4. 조건별 확보/미확보 (이 머신 기준)

A21-01·A21-03이 요구하는 물리 조건을 이 머신에서 실제로 만들 수 있는지 갈랐다. **만들 수 없는 것은 "미확보"**로 적고, 무엇이 필요한지 함께 적는다.

| 조건 | 상태 | 확인한 근거 / 미확보 이유 |
|---|---|---|
| LAN | **가능** | 두 머신이 같은 `192.168.0.0/16`. `ping 192.168.0.1` 정상. 사용자 수준 TCP/UDP 왕복 시험에서 macmini→macbookpro `lan-tcp OK ACK from 192.168.0.64`, `lan-udp OK UDP-ACK` |
| 같은 NAT | **가능** | 양쪽 `curl https://ifconfig.me` = `210.113.21.16`(동일). 두 머신이 같은 게이트웨이 `192.168.0.1` 뒤 |
| 양방향 SSH (가능 조건) | **가능** | macbookpro→macmini `ssh -o BatchMode=yes jaesol-macmini hostname` → `Jaesolui-Macmini.local`(exit 0). macmini→macbookpro `ssh jaesol-macbookpro` → `Jaesolui-MacBookPro.local`(exit 0). 포트 22 양쪽 LISTEN |
| 양방향 SSH **불가** | **미확보** | 한쪽 sshd 중지·방화벽 차단이 필요하다. `sudo -n true` → "a password is required", `pfctl -s info` → "Permission denied". 루트 또는 다른 네트워크가 필요하며 이번 조사 범위 밖 |
| 서로 다른 NAT | **미확보** | 두 머신이 같은 LAN·같은 공인 IP다. 다른 회선(휴대폰 핫스팟·별도 사업장·VM)이 필요하고 이 머신 네트워크를 바꾸는 사용자 조작이 선행돼야 한다 |
| UDP 차단 | **미확보** | `pfctl` 권한 없음(위와 같음). 커널 방화벽 없이 특정 UDP만 막을 사용자 수준 수단이 없다. 다만 현재 UDP는 열려 있다 — `tailscale netcheck` → `UDP: true`, `MappingVariesByDestIP: false`, 포트매핑 없음. `nc -u -z -w 2 1.1.1.1 53` → 성공 |
| HTTPS 프록시 | **부분 확보** | 사용자 수준 CONNECT 프록시를 `127.0.0.1:47888`에 띄워 시험: `HTTPS_PROXY=http://127.0.0.1:47888 curl https://api.github.com` → `code=200 via=127.0.0.1:47888`. 같은 프록시로 `ssh -o ProxyCommand='python3 …proxycmd.py %h %p' jaesol-macmini` → `ssh-over-connect-proxy-ok`. **QUIC/UDP 기반(B·C)을 프록시가 막거나 우회하는 조건은 재현하지 못했다** |
| 자체 relay | **미확보** | Reason은 `reason-network relay <URL>`로 자체 iroh relay를 지정할 수 있다(`relay --help` 확인). 그러나 실제로 돌릴 iroh relay 서버가 없고(`cargo`·`rustc`는 있음, relay 바이너리 없음), 컨테이너 런타임도 꺼져 있다(`docker info` → "Cannot connect to the Docker daemon", `colima status` → "not running"). 현재는 Reason 기본 relay 4개(`~/.reason/network/relays.json`: sfo1·iad1·fra1·sin1)만 쓰인다 |

추가로 확인한 환경 사실 두 가지.

- 이 셸에는 `NODE_EXTRA_CA_CERTS`가 설정돼 있고(`~/.cctrace/server-policy-ca/…pem`), Reason CLI가 이를 이유로 거부한 기록이 데몬 로그에 여러 번 남아 있다. 반면 시스템 프록시는 꺼져 있다(`networksetup -getwebproxy Wi-Fi` → Enabled: No; `scutil --proxy`에 프록시 항목 없음). 즉 이 머신은 "프록시 환경 변수는 있으나 실제 시스템 프록시는 없음" 상태다.
- xsm은 프록시 명령을 `XSM_SSH`로 받지 못한다. `XSM_SSH`는 실행 파일 경로로 쓰이고(`xsm/remote.py:187`), 그 값에 옵션 문자열을 넣으면 `cannot run ssh: [Errno 2] No such file or directory: 'ssh -o ProxyCommand=…'`로 실패한다. 프록시를 쓰려면 `~/.ssh/config`에 `ProxyCommand`/`ProxyJump`를 두어야 한다(`xsm/remote.py:180`이 `ssh -G`에서 그 키를 읽는다). 이번 조사에서 사용자의 SSH 설정은 수정하지 않았다.

## 5. C(공개 Reason 엔진) — 기존 증거의 항목화

새 조사가 아니라 이미 있는 자료를 위 형식의 항목으로 옮긴다. 출처는 `docs/references/reason-network/`(README·coverage·source-manifest·ghidra-native), `deliverables/reason-network-research-2026-10-23.md`, `deliverables/reason-network-evaluation-2026-10-23.md`(+`/evidence.json`), `deliverables/xsm-reason-live-comparison-2026-10-23.md`(+`/evidence.json`), `deliverables/adversarial-cross-review-2026-10-23.md`(+`/`).

| 비교 항목 | 기존 증거에서 옮긴 값 | 출처 |
|---|---|---|
| 설치 입력 | `curl -fsSL https://reasonmachines.com/install.sh \| bash -s -- network` 1회(약 56.94초, 종료 코드 0). 계정 없는 경로는 `--no-setup`으로 별도 설치(J20, 약 4.43초) | evaluation J01·J20 |
| 기존 전제 | Reason 계정·네트워크 가입, 브라우저 로그인. Codex 훅 5종 신뢰. 공개 엔진은 MIT OR Apache-2.0, 설치·로그인 CLI는 비공개 | research 요약·현재 공개 상태, evaluation J02·J06 |
| 사람의 실제 조작 수 | 로그인·가입 1건(사용자 수행, 클릭 수 미측정) + 훅 신뢰 승인 1건(채팅 승인 후 에이전트가 TUI 조작). `human_click_count: "not measured"`, `confirmed_human_ui_intervention_stages: 1`, `confirmed_chat_authorization_count: 1` | evaluation `user_intervention` |
| 에이전트 도구 호출 수 | 왕복당 `list_team`·`send_message`·`check_inbox` 실제 호출(J09). `list_team` 단독 약 7.25초(J04)·19.38초(J05) | evaluation J04·J05·J09 |
| 첫 왕복 성공 여부 | **단일 머신에서는 성공**: CLI→Claude 약 4.25초(J07), CLI→Codex 약 11.77초(J08), Codex→Claude ACK·reply_to 일치 약 28.41초(J09). **두 물리 머신은 미확보** | evaluation J07–J09 |
| 경로·포트 | 엔진 0.12.10, 기본 relay 사용(현재 `relays.json` 4개). iroh 기반 QUIC·LAN mDNS·NAT 통과·HTTPS relay. 고정 UDP 포트·대체 포트 진단은 0.12.11에서 확인 | research 통신 구조, ADR-0021, R42 |
| 재연결 | 데몬 재시작 후 두 serve 프로세스 재연결 로그, Codex ACK 재수신(J16). 오프라인 재접속·만료·키 교체는 A21-02 소관으로 남음 | evaluation J16 |
| 제거 | 격리 엔진 경로를 별도 설치·초기화(J20). 설치가 건드린 파일: `config.toml`·`hooks.json`에 서버·훅 추가, `default_tools_approval_mode = "approve"` 기록. **xsm 제거·마이그레이션은 수행하지 않음** | research 설치가 변경하는 범위, evaluation J19 |
| 로그 공개 범위 | 원본 설치 로그에 로그인 연결 정보·초대 링크가 포함될 수 있어 공개 산출물에서 제외하고 개인명·임시 경로를 치환했다 | evaluation "평가 조건과 증거" |
| 알려진 실패·한계(반대 증거) | J10·J11(serve Claude의 MCP 부재·CLI 승인 거부), J17(여러 Codex 홈 중 `.codex-3`만 설정), J18(작업 폴더 표시 불일치), J21(자동 승인 분류기 송신 거부), J22(일반 Codex 유휴 수신 실패: 스레드 rollout 미발견), J23(CLI 목록 누락). 적대적 검토의 판정: 주소·스레드가 있어도 대상 Codex 홈 바인딩이 보존되지 않는다, 큐 등록 성공이 실제 도달을 보장하지 않는다 | evaluation J10–J23, adversarial "xsm 관점에서 Reason" |

이 항목화는 C의 두 물리 머신 왕복이 **아직 없다**는 사실을 바꾸지 않는다. 위 값은 모두 단일 머신 또는 격리 경로의 증거다.

## 6. D(VPN+SSH) — 설치와 경로 확인

- **Tailscale 설치됨·실행 중**: `/Applications/Tailscale.app`(1.105.110-td75f04c92, "unstable" track), 시스템 확장 `io.tailscale.ipn.macsys.network-extension` 실행 중, `tailscale status --json` → `BackendState: Running`, `TUN: true`. 테일넷 `tail13f006.ts.net`, 계정 `ysys143`. 노드: `jaesol-macbookpro`(이 머신, 100.123.30.11), `jaesol-macmini`(100.77.24.16, `active; direct 192.168.0.64:41641`), `s26-ultra`(offline).
- **경로는 LAN 직결**: `tailscale ping jaesol-macmini` → `via 192.168.0.64:41641 in 47ms`. relay는 `tok`(Tokyo DERP, `netcheck` 41.5ms)로 잡혀 있으나 실제 통신은 같은 LAN 주소로 직결된다. 즉 이 환경의 D는 "VPN이 다른 NAT를 뚫은" 사례가 아니라 **같은 LAN 위의 사설망**이다.
- **machine-sync 스킬이 쓰는 경로**: `~/.agents/skills/machine-sync/SKILL.md`가 "SSH: 양방향 무암호. 별칭은 MagicDNS 라벨(`ssh jaesol-macbookpro`)"로 적고, `ssh -o BatchMode=yes <별칭> hostname`을 연결 생존 판정으로 쓴다. 별칭은 `~/.ssh/config`에서 `HostName jaesol-macmini.tail13f006.ts.net`로 풀리므로 **machine-sync의 경로도 Tailscale(MagicDNS) 위**다. 도구 `repo-drift`·`ts-peer-setup`은 `~/.agents/bin/`에 있고 `~/.local/bin/`에서 심볼릭 링크로 노출된다.
- **주의(스킬에 기록된 제약)**: "Tailscale SSH 서버는 샌드박스 Tailscale GUI 빌드에서 돌지 않는다" → macOS 내장 원격 로그인(포트 22)을 테일넷 주소로 쓴다. 포트가 테일넷 안에서만 열린다.

## 7. G11 종료 조건 대비 미완 목록

G11 종료 조건(`docs/plan/reason-inspired-adrs/execution.md:124`): "A/B/C/D 동일 과제의 설치·사용자 개입·첫 왕복·경로·운영/제거 근거. 물리 환경별 지원 불가·실패·미실행 구분. 사용자 선택용 비교 결과가 준비됨. D12의 선택 자체는 통과 근거에 포함하지 않음". 항목별로 지금 무엇이 없는지 적는다.

1. **B가 아예 없다.** P11 spec 2항이 요구하는 자체 P2P 최소 spike(인증·경로·복구)를 만들지 않았다. 비교표의 B행은 채울 값이 없는 상태다.
2. **동일 과제 왕복을 네 후보 모두에서 실행하지 않았다.** A조차 이번 세션에서 새 왕복을 돌리지 않았고, `xsm remote sessions Jaesolui-Macmini`가 "no live sessions in the paired project on Jaesolui-Macmini"를 반환했다(짝 프로젝트 `xsm`에 살아 있는 세션 없음). 같은 과제·같은 두 머신·같은 조건의 표본이 아직 0건이다.
3. **C의 두 머신 왕복이 없다.** 상대 머신에 Reason 엔진이 설치돼 있지 않다(`~/.reason` 없음). 두 머신 비교의 전제 미충족.
4. **A와 D가 구분되지 않는다.** 현재 A의 SSH 대상이 테일넷 주소라 D와 물리 경로가 같다. VPN을 끈 LAN-only A와 VPN 위 D를 나란히 돌린 표본이 필요하다.
5. **물리 조건 4개가 미확보다.** 다른 NAT, UDP 차단, 자체 relay, 양방향 SSH 불가. 각각 필요한 것(별도 회선·루트 권한·relay 서버·sshd 없는 상대)이 이번 조사에서 확인됐고, 확보 전에는 해당 셀을 미완으로 남긴다.
6. **HTTPS 프록시는 부분 확보에 그친다.** SSH 경로는 사용자 수준 CONNECT 프록시로 통과를 확인했지만, QUIC 기반 B·C가 프록시 환경에서 어떻게 되는지는 재현하지 못했다.
7. **사람 개입 수가 미측정이다.** 네 후보 각각의 클릭·입력 횟수를 세지 않았다(기존 C 자료도 `human_click_count: "not measured"`).
8. **재연결·제거 근거가 후보별로 없다.** C에는 데몬 재시작 증거가 있으나 제거 후 잔여(리스너·서비스·키) 확인은 없고, A·D·B에는 재연결·제거 표본 자체가 없다. A21-05(원격 중단 중 로컬 왕복 유지, 중지·제거 후 소유 서비스 대조)는 P12 소관이지만 P11 비교표에도 같은 칸이 필요하다.
9. **경로·포트 실측이 후보별로 없다.** 실제로 붙은 경로와 포트, 대체 포트를 네 후보에서 같은 방법으로 기록하지 않았다.
10. **A21-03이 요구하는 "사람/독립 검토"가 없다.** 비교 결과에 대한 독립 검토 기록이 아직 없다.
11. **로그 공개 범위가 후보별로 정리되지 않았다.** C만 무엇이 로그에 남는지 알려져 있고, A·D·B의 설치·운영 로그 잔여 항목은 정리하지 않았다.

## 8. 이번 조사에서 하지 않은 것

- `xsm/remote.py`를 포함한 제품 코드·테스트를 수정하지 않았다. 새 테스트도 만들지 않았다.
- 백엔드를 확정하지 않았다. D12 선택은 사용자 몫이며 이 문서는 그 근거를 준비하지도 못했다(7절).
- 다른 세션·에이전트에 메시지를 보내지 않았다. 원격 왕복은 실행하지 않았다.
- 사용자의 `~/.ssh/config`, Tailscale 설정, Reason 설정, xsm 짝(`remotes[0]`)을 바꾸지 않았다.
- 프록시 spike는 `127.0.0.1:47888`의 임시 프로세스로만 돌렸고, 조사 뒤 남기지 않았다(`/tmp/xsm-p11-proxy*.py` 및 수신 시험용 포트는 임시).

## 9. 미확보·미측정 요약 (한 표)

| 항목 | 상태 | 다시 볼 조건 |
|---|---|---|
| 다른 NAT | 미확보 | 별도 회선·원격 사업장·VM 확보 시 |
| UDP 차단 | 미확보 | 루트 권한 또는 커널 방화벽을 다룰 수 있는 대상 머신 확보 시 |
| 자체 relay | 미확보 | iroh relay 서버(또는 컨테이너 런타임) 준비 시 |
| 양방향 SSH 불가 | 미확보 | sshd 없는 상대 또는 차단 권한 확보 시 |
| HTTPS 프록시 (QUIC 경로) | 미확보 | UDP를 막는 프록시 또는 MITM 프록시 환경 확보 시 |
| C 두 머신 왕복 | 미확보 | 상대 머신에 Reason 엔진 설치·같은 팀 가입 시 |
| B 최소 spike | 미착수 | P11 spec 2항에 따라 격리 시험체 작성 시 |
| A/B/C/D 동일 과제 왕복 | 미실행 | 양쪽에 짝 프로젝트의 살아 있는 세션을 두고 같은 과제로 실행 시 |
| 사람 개입 수 | 미측정 | 각 후보 실행 시 클릭·입력 횟수 기록 시 |
| 독립 검토 | 없음 | 비교 결과 확정 뒤 검증 담당 배정 시 |

