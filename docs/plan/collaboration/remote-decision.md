# P11 / D12 원격 backend 비교와 남은 실측

## 현재 사용자 결정 보완 (2026-10-29)

D12의 제품 요구사항은 [ADR-0021](../../adr/0021-cross-machine-network-and-membership.md)로 확정됐다. 자체 P2P 기본·선택적 Tailscale 경로·공개 relay 기본/자체 설정·계정 비필수·기기키/초대 가입·Reason식 동등 멤버 권한을 따른다. 별도 관리자 계층과 가입 때마다의 관리자 승인은 두지 않는다. 기존 VPN+SSH 시험체 D를 신규 제품의 필수 backend로 채택한 결정이 아니며, Tailscale 경로에서도 같은 P2P 프로토콜을 사용한다.

아래 비교 관측·이전 판단·미실행 환경은 당시 근거로 보존한다. 사용자 선택 확보는 P11/G11 비교나 P12 제품 구현·실측의 완료가 아니며 구현 goal은 일시정지 상태다. 구체 라이브러리·버전·relay 주소는 후속 구현 항목이다.

## 비교 당시의 관측 기록

- 관측 범위: 2026-10-28–29 KST. 2026-10-28 합성 transport/로컬 IPC 이후, 2026-10-29 A/B/D와 C의 실제 native 증거를 반영했다.
- 담당: P11 원격 비교 담당. 이번 갱신은 기존 보고서·JSON의 문서 통합이며 새 원격 실행이나 제품 변경은 없다.
- 비교 당시 상태: **같은 두 물리 머신·같은 과제에서 A/B/D 실제 native 9회, C 실제 native 6회 및 cached 회수 2회 성공. P11/G11 전체는 미완이고 D12는 사용자 미응답·미선택이었다.** 현재 제품 요구사항 결정은 위 보완 기록을 따른다. **P12 제품 구현·실측은 미완이다.**
- A/B/C/D는 [ADR-0021](../../adr/0021-cross-machine-network-and-membership.md)의 후보명이다. 과거 ADR-0007 토론의 같은 철자 선택지와 혼동하지 않는다.
- 범위: 제품코드·실제 사용자 팀·프로필·SSH/Tailscale·전역 XSM_HOME·업무 권한은 변경하지 않았다. 시험은 양쪽 고유 `/tmp`와 `deliverables/p11-live`의 증거에 한정했다. C의 두 controlled node 팀은 전체 P11 비교 요청의 범위 안에서 코디네이터가 자기완결 일시 fixture로 판단해 생성·가입·정리했다. 별도의 C 팀 생성/가입 명시 승인 응답은 없었다. 실제 사용자 팀·전역 권한과 D12 제품 선택은 별개다. 기존 계정 키·토큰 값은 조회하지 않았고 fixture capability는 메모리·기존 SSH stdin·private IPC로만 전달했다.

## 1. 당시 D12에 제출한 판단 (비교 이력)

**D(VPN+SSH) 우선 검토는 기존 연결을 재사용할 수 있다는 운영 가설이다. 설치·운영 비용의 실측 우위나 제품 채택 결론은 아니다.** 기존 Tailscale과 양방향 SSH의 도달성은 확인했으나 신규 onboarding·업데이트·회수 비용은 측정하지 않았다. A 시험체도 일반 LAN SSH carrier이며, 진단·재시도 개선을 비교한 표본은 아니다. 이번 작은 표본의 지연 수치로 D가 A보다 빠르거나 안정적이라고 판단하지 않는다.

반대 근거도 있다. D는 VPN 계정·접근 정책·클라이언트 운영에 의존한다. 관측한 양쪽 Tailscale은 `1.105.110, unstable/dev` track이며 이를 안정판 운용 결과로 쓰지 않는다. 현행 xsm의 양방향 SSH 요구도 없애지 못한다. 초기 조사에서 두 머신의 같은 LAN·동일 외부 egress를 확인했고 최신 native 시험은 NAT/egress를 다시 측정하지 않았다. 다른 NAT와 UDP 차단 환경의 성공은 아직 증명하지 못했다. Tailscale의 direct/DERP fallback은 [공식 연결 유형 문서](https://tailscale.com/docs/reference/connection-types)에 있는 기능이지 이번 실측의 성공 셀이 아니다.

C는 고정 standalone 엔진 `0.12.10`의 사본을 양쪽 private HOME/state/IPC에 가둬 실제 native 6회와 cached 회수 2회를 마쳤다. 초기 조사의 peer binary·두 머신 표본 부재는 해소됐다. 본문 요청·회신은 Reason engine을 통과하지만 매 native 실행의 trigger는 기존 SSH였고, phase와 예상 본문 SHA만 전달했다. 엔진만으로 일반 Codex 유휴 세션을 깨우는 표본은 아니다. 이 결과는 [C 실제 보고서](../../../deliverables/p11-live/C-native-roundtrip-20261029.md)와 [JSON](../../../deliverables/p11-live/C-native-roundtrip-20261029.json)에 있다. 실제 Reason CLI/plugin/MCP 통합, SSH 없는 onboarding, xsm의 origin·업무 권한·대화 신원을 엔진 멤버십과 연결하는 제품 계약은 남아 있다.

B는 최소 시험체를 확보했지만 지금 채택할 근거는 부족하다. 직접 TCP·임시 인증·중복 방지·복구는 관측했으나, 암호화·실제 가입/제명·NAT traversal·relay·업데이트 경로가 없다. 이번 시험체가 쓰는 임시 HMAC 인증은 격리 fixture의 검사용이며, 폐기된 로컬 pair/HMAC 정책을 복원하거나 제품 인증안을 정한 것이 아니다.

[A/B/D 실제 보고서](../../../deliverables/p11-live/native-carrier-roundtrip-20261029.md)의 native 9회와 C의 6회는 모두 실제 peer Codex가 같은 수학 과제를 검토한 답이다. 기본 비교의 합계는 native 15회이며 cached 회수는 A/B/D 각 1회와 C 2회, 합계 5회로 별도 집계한다. 기존 D 우선 검토 의견은 운영 전제 재사용에 대한 제안으로 유지하며 이 작은 지연 표본으로 후보의 성능 순위를 정하지 않는다. [G11 판정 초안](records/gates/G11-remote-comparison-draft.md)은 비교체 성공과 남은 수용 증거를 분리한다. G11은 D12 선택 자체를 통과 근거로 요구하지 않으며, D12 미응답과 별개로 미실행 환경·설치/운영 비교의 부족이 남아 있다.

### 후속 제한 환경: C의 UDP outbound 차단과 relay

기본 비교와 별도인 [추가 C 표본](../../../deliverables/p11-live/udp-blocked-report-20261029.md)은 양쪽 own engine daemon에만 커널 UDP outbound deny를 유지하고 실제 peer Codex 1회·상관 회신·전체 본문 SHA를 확인했다. 응답 뒤 양쪽 상대의 `link=relay`를 확인했으며 native 왕복은 5725.957ms였다. 양쪽 UDP 정상/차단 및 같은 제한의 TCP 성공 preflight와 실제 daemon argv가 제한 근거다. engine 자체 UDP EPERM 로그는 관측하지 못했고 선택 relay URL·wire IP/port도 unknown이다. 이 추가분까지 실제 native 호출은 16회이고 cached 5회는 그대로다. 기본 비교표의 15회와 혼합해 성능 순위를 만들지 않는다.

본문은 engine을 통과하고 native 실행 trigger는 SSH였다는 경계가 이 표본에도 적용된다. 준비 script의 파일명 오류와 session directory 전파 전 send 거부는 모델 호출 0회인 별도 실패로 보존했다. 실제 native는 attempt1/success1이며 제한을 푼 재실행은 없다. [오프라인 증거 검사](../../../deliverables/p11-live/udp-blocked-evidence-check-20261029.json)는 원 결과·hash·상관관계와 relay_connected-only 반례를 대조했다.

이 결과는 C의 controlled-process UDP 제약 셀이다. A/B/D의 같은 조건, 네트워크 전체 firewall, 다른 NAT·HTTPS proxy·자체 relay·SSH 불가 및 P12 제품 여정은 미검증이다. 앞선 Opus 검토는 기본 15회 자료에 대한 1회이며 이 추가 표본을 독립 모델이 재검증했다고 쓰지 않는다.

### 후속 제한 환경: bootstrap 뒤 SSH 없는 data-plane

[새 C 조건](../../../deliverables/p11-live/no-ssh-v2-summary.md)은 초기 준비·team join·양쪽 who=2 뒤 bootstrap SSH를 종료했다. 동일한 own-process TCP:22 deny 아래 실제 양쪽 socket EPERM·비multiplex SSH exit255를 확인한 뒤, engine 요청→peer 자율 pull→실제 구독 Codex1회→engine reply를 완료했다. 측정6.984564초 동안 양쪽 fixture의 SSH spawn은0회다. 초기 준비와 사후 raw 회수에는 SSH를 사용했으므로 SSH 없는 신규 설치/onboarding의 성공이 아니다. 네트워크 전체 SSH 단절이나 다른 후보의 성공으로도 확대하지 않는다.

원 조건은 sandbox 안에서 setuid ps 실행이 거부돼 data-plane에 미도달했다. 원 실패는 [별도 기록](../../../deliverables/p11-live/no-ssh-native-summary.md)에 남겼고, 새 조건은 같은 network profile과 비승격 libproc의 실제 kernel PID/start 관측을 사용했다. 모델·권한을 추가 허용하지 않았다. native1회·실제 request/reply ID와 SHA·CID/PID·원 실패 보존·잔여0을 [검증27항목](../../../deliverables/p11-live/no-ssh-v2-results.json)과 manifest에 결속했다.

기본 native15회, UDP-deny relay1회, 이번 SSH 없는 data-plane1회로 C를 포함한 누적 native는17회다. cached5회는 그대로이며 서로 다른 시간 경계의 수치를 성능 순위로 쓰지 않는다. 앞선 Opus 검토는 기본15회 자료에 대한 것으로 이 후속을 독립 모델이 검증했다고 주장하지 않는다. 이후 HTTPS CONNECT proxy는 아래 별도 조건에서 native1회를 확인했으며, 두 조건을 한 시험으로 합치지 않는다.

### 후속 제한 환경: C의 실제 CONNECT proxy 왕복

[explicit-allow 새 조건](../../../deliverables/p11-live/proxy-variant-report-20261029.md)은 양쪽 engine daemon의 직접 UDP/다른 TCP를 막고 각 own loopback CONNECT proxy만 허용했다. 양쪽 kernel/TLS preflight, 실제 request/reply SHA·reply_to, native1회와 양쪽 link=relay, 과제 구간의 양방향 relay tunnel byte 증가를 확인했다. 실제 왕복8840.102ms, native CLI8005.028ms이며 단일 표본의 추론/제어/carrier 시간을 포함한다. TLS 검증 해제·MITM·전역 proxy/firewall 변경은 없었다. SSH 제어 trigger는 이 proxy 조건에서 계속 사용했으므로 앞의 자율 no-SSH 조건과 합쳐 하나의 무SSH proxy 시험으로 만들지 않는다.

반대 증거도 있다. native reply 직후 snapshot에서 local/peer CONNECT2225/2299건 중 allowlist 거부2179/2249건과 nonCONNECT 거부3건씩을 관측했다. numeric DNS resolver 목적지 거부와 engine의 내부 재연결은 모델 재시도0과 별개다. CPU나 영구 busyloop를 측정한 것은 아니며 이를 원인으로 단정하지 않는다. [오프라인 audit](../../../deliverables/p11-live/proxy-variant-audit.py)는 실제 peer 파일29개·reply상관·relay/bytes·잔여0을 대조했다.

원 proxy 문법/허용 경로 실패는 별도 보존했다. 이 추가는 C의 owned-process CONNECT 제한 조건이며 기업 인증/HTTPS-inspection proxy, 다른 후보, 네트워크 전체 제한이나 P12 제품 통합의 성공이 아니다. 기본15+UDP1+자율no-SSH1+proxy1의 누적 native는18회이고 cached5회는 그대로다. 이전 Opus 검토의 범위를 이 추가 표본에 소급 확대하지 않는다.

## 2. 현재 환경: 추정과 기존 문서의 전제를 교정

`~/.agents/skills/machine-sync/SKILL.md`와 [P11 사전 계획](../../../deliverables/reason-inspired-adrs-prep/P11-remote-comparison-plan.md)을 읽고, 현재 hostname을 확인한 뒤 반대편 `jaesol-macmini`만 조사 대상으로 삼았다. 최초 접속에는 요청한 `ssh -oBatchMode=yes -oConnectTimeout=5`를 썼고, 이후 시험에는 `StrictHostKeyChecking=yes`, `UpdateHostKeys=no`를 더했다.

아래 버전·HEAD·registry 표본은 초기 읽기 전용 조사 시점의 기록이다. 현재 제품 revision이나 이후 native 표본의 실행 CLI와 혼합하지 않는다. 최신 native 표본의 CLI는 네 후보 모두 peer `/opt/homebrew/bin/codex`의 `codex-cli 0.163.0`이며 기존 `.codex-3` ChatGPT 구독 인증을 사용했다.

| 항목 | 현재 로컬 | 실제 peer | 의미 |
|---|---|---|---|
| `hostname` | `Jaesolui-MacBookPro.local` | `Jaesolui-Macmini.local` | 같은 호스트의 두 프로세스로 대체하지 않았다 |
| SSH 별칭 | 현재 호스트는 `jaesol-macbookpro` 측 | 대상은 `jaesol-macmini` | hostname 확인 전에 방향을 고정하지 않았다 |
| 시스템 Python | `/usr/bin/python3` 3.9.6 | `/usr/bin/python3` 3.9.6 | 공통 spike는 이 Python으로 실행 |
| 기본 발견 Python | `/opt/homebrew/bin/python3` 3.14.6 | `/usr/bin/python3` 3.9.6 | 비대화형 PATH가 같다고 가정하지 않는다 |
| Claude CLI | `~/.local/bin/claude`, 2.1.312 | `~/.local/bin/claude`, 2.1.312 | `--version` 실행 결과 |
| Codex CLI | NVM Node v24.19.0의 `codex`, 0.164.0 | `/opt/homebrew/bin/codex`, 0.163.0 | CLI 버전과 실행 중 app-server 버전을 섞지 않는다 |
| Codex daemon 프로필 바이너리 | `.codex-3`의 0.165.0 실행 확인 | `.codex-3` 0.165.0, `.codex` 0.162.1 실행 확인 | 실제 경로의 `--version`도 별도 실행 |
| 설치 xsm | 0.4.20, `~/.xsm/runtime/2389da782089/bin/xsm` | 동일 출력 | 설치 runtime은 현재 B03 작업 트리와 별개다 |
| Tailscale | 1.105.110, unstable/dev | 1.105.110, unstable/dev | 현재 연결 재사용. track 변경·업데이트 안 함 |
| Tailscale CLI 경로 | `/usr/local/bin/tailscale` | `/opt/homebrew/bin/tailscale` | peer SSH shell에서 bare `tailscale`은 PATH에 없어 exit 127. 설치 부재와 구분 |
| 현재 작업 저장소 | `~/Documents/GitHub/cross-session-messaging` | 같은 경로 없음 | peer에 같은 checkout이 있다고 가정하면 안 된다 |
| 현재 작업 HEAD/status | `main`, `4fd7c9f550dd5bafa8e754701ab1f0802c74b064`, 기존 미커밋 변경 다수 | 해당 경로는 없음 | source 동결 중이며 복사·fetch·checkout·merge하지 않았다 |
| 별도 xsm 저장소 | `~/Documents/GitHub/xsm` | 동일 경로 존재 | 두 저장소의 git common dir로 실제 checkout 확인 |
| 별도 xsm HEAD/status | `main`, `b29b39ce65c594e88e4b84684724fe02553ee2fc`, clean | 동일 HEAD, clean | 이것을 B03 수정본의 배포 증거로 쓰지 않는다 |

Git 상태 조회에는 `GIT_OPTIONAL_LOCKS=0`을 적용했다. `xsm --version`의 runtime fingerprint가 같다는 사실만으로 해당 runtime이 어느 checkout의 어느 미커밋 변경을 포함한다고 추정하지 않는다.

### 실제 경로와 live 세션

- 순방향 SSH의 실제 연결 정보는 `100.123.30.11 → 100.77.24.16:22`였다. `ssh -G`의 hostname은 `jaesol-macmini.tail13f006.ts.net`이다. 역방향 `ssh ... jaesol-macbookpro hostname`도 exit 0, `Jaesolui-MacBookPro.local`이었다.
- Tailscale `status --json`에서 양쪽 backend는 Running이었다. MacBookPro에서 관측한 peer direct endpoint는 `192.168.0.18:41641`, Macmini에서 본 반대편은 `192.168.0.11:41641`이었다. Macmini `ipconfig getifaddr en1`로 `.18`도 확인했다. 과거 계획의 Macmini `.64`는 현재 실측에 재사용하지 않았다.
- 두 머신에서 각각 외부 egress를 조회해 해시만 비교했고 일치했다. 원 IP 값은 기록하지 않았다. 현재 같은 LAN·동일 외부 egress 조건의 증거이며, NAT 종류나 다른 NAT의 도달성 증거는 아니다.
- 초기 조사에서는 peer의 Claude/Codex 프로세스는 확인했으나 `~/Documents/GitHub/xsm` registry pointer는 양쪽 0개였고 이 과제 수신 세션을 확보하지 못했다. 이후 전체 비교 요청에 대한 코디네이터 범위 판단으로 구성한 private adapter와 실제 ephemeral Codex 호출로 A/B/D 9회·C 6회를 실행했다. 이는 기존 제품 registry 세션의 loaded 상태를 확인했다는 뜻은 아니다.
- 로컬 B03 작업 폴더에는 `.claude-3`의 native 세션 `fe03b7fc…`, PID 41106이 있었다. PID 시작 시각, native session ID 일치, native socket 존재를 확인했다. 기존 조사에서 알던 `bf3…`/`29eb…` 세션을 현재 live라고 재사용하지 않았다.
- 양쪽 remote binding의 실제 필드는 `local_project=xsm`, `remote_project=xsm`이었다. 이 `xsm` scope는 현재 저장소가 아니다. 로컬 root는 `~/Documents/GitHub/claude-code-trace`, peer root는 `~/orca/workspaces/claude-code-trace/desktop-p0-implementation`이었다. 후자는 현재 존재하지 않았고 그 root에 맞는 live native Claude 세션도 없었다. 다른 live 세션을 임의 편입하거나 scope를 고치지 않았다.
- live 확인은 registry/native session metadata·PID·시작 시각·socket 존재까지만 사용했다. transcript 본문, 로그인 파일, private key, token, invite 값은 조회하지 않았다. 초기 프로세스 수집은 출력 길이 제한이 있어 사용하지 않았고, 전체 `ps` 결과를 메모리에서 필터하는 수집으로 다시 확인했다.

## 3. A/B/C/D 공통 비교표

설치 입력·사람 개입·첫 왕복·운영/제거를 같은 칸에 적었다. 아래는 최신 native 표본이며 과거 합성 표본은 뒤에 역사로 분리했다. 기존 상태를 재사용한 것을 신규 설치 성공이나 사람 개입 0회의 onboarding으로 계산하지 않는다. driver/daemon handle 수는 확인된 실행 절차이며 전체 에이전트 도구 호출 수를 뜻하지 않는다. 후자의 동일 형식 집계는 미확정이다.

| 후보 | 설치 입력·기존 전제 | 사람/도구 개입 | 이번 왕복 증거 | 인증·권한 경계 | 운영·제거와 한계 |
|---|---|---|---|---|---|
| A: 기존 SSH 개선 | 기존 SSH client/server·host key/키 접근과 peer 구독 Codex. LAN `.18:22`로 hostname override. 제품 xsm pairing은 사용하지 않음 | 실행 중 사용자 조작 0; 신규 SSH/구독 인증 설정 조작 수 미측정. SSH driver 시작·재연결 2회 | **실제 native 3회 + cached 회수 1회**. first/followup/재연결 뒤 새 답. LAN 직접 SSH 경로 기록 | 기존 SSH 인증 재사용. xsm forced-command origin·project/업무 권한 통합은 별도 미검증 | 소유 driver/SSH/native handle 종료. 실제 SSH 키·authorized_keys·sshd 유지; 운영 backend 제거 시험은 미실행 |
| B: 자체 P2P 최소 spike | Python stdlib의 기존 private TCP/HMAC/journal 구조. Iroh/QUIC 아님. bootstrap·제어는 tailnet SSH(`100.123.30.11 → 100.77.24.16:22`) | 실행 중 사용자 조작 0; SSH 제어 driver 2회. 새 공개 listener·가입 권한·deps 없음 | **실제 native 3회 + cached 회수 1회**. 설계상 private `192.168.0.18:49909` 및 재시작 뒤 `49941` TCP. phase별 socket endpoint trace는 없음 | fixture 비밀은 메모리/기존 SSH stdin. ID 충돌 거부. payload 암호화 없음; production 데이터 없음 | 두 포트 stop 뒤 connect 61, 소유 driver/native 종료. NAT traversal/relay/실제 멤버 관리·키 회수는 미구현 |
| C: 공개 Reason 엔진 | 고정 0.12.10 binary를 양쪽 고유 tmp에 stage. private HOME/state/socket, 두 controlled node만의 팀. 실제 Reason CLI/계정은 사용하지 않음 | 실행 중 사용자 조작 0. 도구가 두 독립 실행의 private create/join/register·재시작·정리를 수행. 기존 SSH·구독 인증 전제 | **실제 native 6회 + cached 회수 2회**. 두 실행 각각 first/followup/local daemon 재시작 뒤 새 답. 본문은 engine, native trigger는 SSH. 각 native 왕복 뒤 양쪽 `link=direct` | 전체 비교 요청에 대한 코디네이터 판단으로 실행한 일시 fixture membership. 별도 C 팀 명시 승인 응답 없음. 실제 사용자 팀·권한 불변. `verified=false`, `has_proof=false`; xsm 업무 권한 성공 아님 | 소유 daemon handle 10개·native 6개·SSH control 2개 종료, 양쪽 private state/HOME/키/engine 사본 제거. 실제 서비스 유지. 선택 relay URL·wire IP/port unknown |
| D: VPN+기존 SSH | 이미 실행 중인 Tailscale와 SSH, peer 구독 Codex. 신규 설치/로그인/정책 변경 없음 | 실행 중 사용자 조작 0; 최초 VPN/SSH/구독 설정 조작 수 미측정. SSH driver 시작·재연결 2회 | **실제 native 3회 + cached 회수 1회**. tailnet 주소의 SSH, 현재 underlay의 LAN direct endpoint 관측 | VPN 머신 접근과 xsm project/사용자 승인은 별개. VPN 접속만으로 scope를 열지 않음 | 소유 driver/SSH/native 종료. Tailscale·ACL·로그인·키 유지. DERP 강제 전환·VPN 제거 미실행 |

이번 A는 LAN 직접 SSH, D는 Tailscale IP SSH로 분리했다. 현재 운영 설정의 A는 이미 테일넷 별칭을 쓰므로, **운영 A와 D는 중첩되는 구성**이라는 기존 지적은 여전히 맞다. 분리한 carrier 안에서 실제 native 과제를 실행했으며 제품 xsm 권한/발견/첨부 통합의 성공으로 확대하지 않는다.

### 최신 실제 native 측정: 성능 순위로 사용 금지

같은 `request_id=P11-QA-40c1afc34bbd43c4`와 `2+2=5` 과제에 대해 native 답은 모두 `claim_valid=false`, `corrected_sum=4`와 짧은 반례였다. CLI는 네 후보 모두 peer `/opt/homebrew/bin/codex`의 `codex-cli 0.163.0`이다. 각 호출은 새 ephemeral conversation이며 followup에는 직전의 최소 수학 결과만 전달했다. native resume 시험은 아니다.

| 후보 / 실행 | native 횟수 | first ms | followup ms | reconnect cached ms | after-reconnect native ms |
|---|---:|---:|---:|---:|---:|
| A LAN SSH | 3 | 6137.471 | 6712.996 | 10.001 | 5409.321 |
| B private TCP | 3 | 5816.222 | 7377.910 | 19.796 | 5657.270 |
| C 최초 private 실행 | 3 | 5766.252 | 5028.281 | 175.142 | 6871.450 |
| C 제어 보강 재실행 | 3 | 6375.519 | 5166.103 | 136.423 | 6877.705 |
| D Tailscale SSH | 3 | 4971.326 | 6304.035 | 12.623 | 6277.135 |

단일 표본이며 CLI 기동·구독 추론·carrier 왕복·제어 비용을 포함한다. C의 cached는 local daemon stop/start/register 뒤 보존된 local inbox를 읽은 값이며 이 시점에는 peer가 offline으로 보였다. A/B/D는 carrier를 다시 연결한 뒤 peer 보존 답을 회수했으므로 네트워크 복구의 같은 척도가 아니다. C는 SSH control과 peer daemon을 유지했다. cached 5건은 기존 답을 모델 재호출 없이 회수했으며 native 15건에 더하지 않는다. 실제 답·conversation·PID/시작/종료·reply_to·경로와 보정 flags는 [A/B/D JSON](../../../deliverables/p11-live/native-carrier-roundtrip-20261029.json) 및 [C JSON](../../../deliverables/p11-live/C-native-roundtrip-20261029.json)을 따른다. hooks/plugins/apps/shell 등의 비활성화는 invocation에만 적용했고 tool event는 0이었다.

C는 매 native 왕복 뒤 양쪽 `link=direct`, `relay_connected=true`였다. 후자는 relay에 연결돼 있다는 상태이며 본문의 relay 경유 증거는 아니다. 선택 relay URL·wire IP/port는 unknown이며 physical LAN과 overlay를 이 값만으로 구별하지 않는다. cached 조회 직후 local의 link/relay는 아직 미연결이었으므로 이 단계는 저장 inbox 회수로만 센다.

B의 bootstrap·제어 경로는 tailnet SSH였고, 수학 본문을 TCP로 주고받도록 만든 driver와 bind/종료 기록이 있다. 각 phase의 실제 socket endpoint/packet trace는 보존하지 않아 경로 지정과 phase별 독립 관측을 구분한다. C의 후속 입력은 직전 실제 답에서 검증한 `claim_valid`·`corrected_sum` 두 필드만 가져왔다(`C-run-private.py`의 `request`와 호출부). 자유문장 반례나 native 대화 기억을 전달한 시험이 아니므로, 모든 답이 false/4이면 다음 요청 hash도 같다.

### 역사: 2026-10-28 합성 transport 표본

같은 요청 ID·본문 digest·`reply_to`·peer hostname을 검증했다. 반환 hostname은 모두 `Jaesolui-Macmini.local`이다.

| 후보 | 시작 준비 시간 ms | 표본 수 | 첫 RPC ms | RPC p50 ms | RPC max ms | 연결 수명 |
|---|---:|---:|---:|---:|---:|---|
| A LAN SSH | 432.373 | 5 | 16.543 | 16.372 | 16.747 | SSH stdio 연결 재사용 |
| D Tailscale SSH | 514.774 | 5 | 15.777 | 17.956 | 19.648 | SSH stdio 연결 재사용 |
| B 최소 직접 TCP | 472.705 | 5 | 31.514 | 31.514 | 33.133 | 요청마다 새 TCP 연결, 시작 시간에는 SSH bootstrap 포함 |

B 재시작 준비 시간은 453.188 ms였다. 연결 수명이 다르고 표본이 작아 처리량·NAT 성능·보편적 지연 우열을 비교할 수 없다. 설치 시간, 사람 대기 시간, LLM 추론 시간은 이 값에 없다. 이 과거 표본은 실제 두 머신의 합성 요청/응답이며 **실제 에이전트 업무 왕복은 아니다**. 최신 native 횟수나 완료 판정에는 합산하지 않는다. 당시 B 포트 52767→52768도 최신 native 시험의 49909→49941과 구분한다.

첫 실행에서 A/D는 성공했고 B는 EOF 처리 오류로 timeout이 났다. 수신 `makefile()`을 닫지 않아 응답 유실 시험의 EOF가 전달되지 않은 시험체 결함이었다. 원 실행 결과를 `...-first.json`으로 보존하고, 시험체만 수정해 재실행했다. 이를 B의 네트워크 미지원으로 분류하지 않는다. 첫 실패의 peer `/tmp/p11-b-2ry91vrs`도 소유자·파일 범위를 확인한 뒤 정리했다.

## 4. Reason 실체·고정 근거와 기존 증거

| 구분 | 확인 결과 | 사용 범위 |
|---|---|---|
| 현재 공개 엔진 binary | `~/.reason/bin/reason-network`, 0.12.10, 15,266,656 bytes | `--version`, `--help`, 격리 IPC 실행 |
| binary SHA-256 | `6ac4bb4837469867edc2dba3cbbd6e4dd9fb18ad0389db69ff6ef21683317a44` | 기존 release 대조 값과 일치(조사 기록은 저장소 밖 보관) |
| 비공개 Reason CLI | `~/.local/bin/reason` → `~/Library/Application Support/Reason/CLI/versions/0.2.557/reason` | 파일 위치만 확인. 비교 엔진이나 새 실행 의존으로 쓰지 않음 |
| peer binary / 초기 조사 | 당시 조사 범위에서 기존 실행 경로를 발견하지 못함 | 과거 표본. 현재 peer 부재 판정으로 사용하지 않음 |
| peer staging / 후속 private 실행 | 먼저 고정 binary byte/hash·`--version`·`--help`를 검증하고 제거. 이후 두 고유 tmp fixture에서 같은 SHA의 엔진 실행 | staging만으로 native 성공을 세지 않음. 후속 실제 native 6회·cached 2회와 정리 readback을 별도 집계 |
| 현재 재실행 가능한 probe | 공개 엔진용 probe 스크립트(저장소 밖 조사 기록) | 새 다운로드·의존성 설치 없이 고정 로컬 엔진에 사용 |
| 기존 정적 분석 소스 기준 | v0.12.11, `b3557ff454cd26a04c2a18804ba83ae5db8b119d` | [Reason 비교 노트](../../references/reason.md). 실행한 0.12.10과 혼합하지 않음 |
| C private 실행의 규약·격리 검토 | v0.12.10의 proto/paths/config/net/relays/teamops/migration 등 11개 source | [C JSON](../../../deliverables/p11-live/C-native-roundtrip-20261029.json)의 `source_protocol_evidence`와 [manifest](../../../deliverables/p11-live/C-native-evidence-manifest-20261029.json). signature 검증은 unknown |

[공개 저장소](https://github.com/reason-machines/reason-network)는 엔진과 MIT OR Apache-2.0 라이선스를 공개한다. 실제 포함 시 LICENSE/NOTICE·고정 버전·업데이트 주체 확인이 필요하다. 이번에 라이선스가 확정된 새 종속성을 제품에 추가한 것은 아니다.

초기 로컬 IPC 14개는 등록/이름 충돌, caller 표시, queued와 명시 ACK의 분리, peek, FYI, 그룹 송신 거부, 승인 프레임 본문 주입, 원 요청 ID 오류 응답, wait 취소, pair loop 제한, 재시작 후 같은 대화 이름·미독 보존을 확인했다. 그 표본에서는 `network_team_created=false`, `native_llm_sessions_used=false`, `daemon_stopped=true`였다. 단일 호스트 검사이므로 최신 C native 6회와 합산하지 않는다.

### C fixture 실행 범위 판단과 D12의 구분

사용자의 기존 전체 P11 비교·격리 비교 실행 요청은 있었지만, 별도의 C 팀 생성/가입 명시 승인 응답은 없었다. 코디네이터는 그 전체 요청의 범위 안에서 두 controlled node만 쓰는 자기완결 일시 fixture라고 판단해 engine 생성·client 등록·private create/join과 수학 marker 과제를 실행했다. 이는 요청 범위에 대한 코디네이터의 판단이며 새 사용자 승인 이벤트가 아니다. 초기 제한이 보호한 실제 사용자 팀·전역 권한은 그대로 유지했고, D12의 backend·종속성·배포 선택은 별도로 남아 있다.

각 실행에서 양쪽 UID-private root에 HOME/state/명시 IPC socket을 고정했다. 기존 Jaesol’s network·현재 `.reason` 상태·실제 Reason CLI/계정·전역 team membership·프로필/MCP·실제 업무 session은 사용하거나 변경하지 않았다. engine 원본 binary 사본과 기존 Codex 구독 인증만 사용했다. roster endpoint 집합은 두 controlled node와 일치했고 `verified=false`, `has_proof=false`였다. 이 roster는 실제 사용자 identity나 xsm 업무 승인을 증명하지 않는다.

capability는 Python 메모리와 기존 SSH stdin 및 private IPC에서만 전달하고 공개 항목은 hash/상태로 제한했다. 각 실행 종료 뒤 자체 state/HOME/키·binary 사본을 제거했다. 이 격리와 정리는 [고정 계획](../../../deliverables/p11-live/C-private-plan-20261029.md), [보강 계획](../../../deliverables/p11-live/C-private-guard-recheck-plan-20261029.md), [실제 보고서](../../../deliverables/p11-live/C-native-roundtrip-20261029.md)에 기록돼 있다.

과거 자료는 [2026-10-23 평가](../../../deliverables/reason-network-evaluation-2026-10-23.md), [실제 비교](../../../deliverables/xsm-reason-live-comparison-2026-10-23.md), [적대적 교차 검토](../../../deliverables/adversarial-cross-review-2026-10-23.md)에 남아 있다.

- J01 설치 약 56.94초, J20 standalone 설치/초기화 약 4.43초는 **과거 표본**이다. 이번에 설치하지 않았고 신규 onboarding 시간으로 재사용하지 않는다.
- J02 로그인/가입 사용자 수행, J06 훅 신뢰 채팅 승인 1회가 있었다. 실제 클릭 수는 미측정이다.
- J07/J08/J09의 Claude·Codex/교차 ACK는 단일 머신 표본이며 이번 두 머신의 성공으로 바꾸지 않는다.
- J21 실제 회신 송신 거부, J22 일반 Codex 유휴 수신 실패, J23 목록 누락, J24 홈별 queue 차이는 반대 증거로 유지한다. 새 버전 경로가 같은 실패를 고쳤다고 추정하지 않는다.
- J16 재연결·J13~J15 격리 왕복은 최신 C의 두 물리 머신 private native 표본을 대신하지 않는다. 최신 표본도 일반 사용자 onboarding·운영 제거·제품 권한 수용 전체를 대신하지 않는다.
- 과거 A/D의 xsm 수신/원장 기록은 현재의 runtime revision·scope·실제 상대 회신을 입증하는 새 trace가 아니다. `queued`/`delivered`도 실제 reply와 구분한다.

## 5. 7개 물리 조건별 지원 불가·미실행·미확보

| 조건 | A 기존 SSH | B 이번 최소 spike | C 고정 Reason | D VPN+SSH | 남은 환경/판정 |
|---|---|---|---|---|---|
| LAN | 실제 native 3회·cached 1회. `192.168.0.11 → 192.168.0.18:22` 직접 SSH | 실제 native 3회·cached 1회. private `.18:49909/49941` 직접 TCP | 같은 두 머신에서 실제 native 6회·cached 2회. 매 native 뒤 `link=direct`; wire IP/port 미수집 | 실제 native 3회·cached 1회. tailnet SSH와 현재 LAN direct underlay 관측 | 네 후보의 native 표본 확보. C의 물리 LAN 경유와 overlay 구별은 unknown |
| 같은 NAT | 초기 동일 LAN·egress 관측, 최신은 현재 LAN 경로. 별도 NAT 전환 시험 없음 | 현재 같은 private LAN에서 수행 | 같은 두 머신·현재 망에서 수행, NAT/egress 재측정 없음 | 현재 LAN underlay의 tailnet 경로에서 수행 | 초기 물리조건 관측과 최신 native를 구분. NAT 종류·포트 매핑·NAT별 성능 성공 셀로 승격하지 않음 |
| 다른 NAT | 미실행 | NAT traversal 미구현, 환경 미확보 | 소스 기능과 별개로 실측 미실행 | 문서상 direct/relay 기능과 별개로 실측 미실행 | 다른 회선·사업장/승인된 VM 필요. 같은 호스트 fake로 대체 금지 |
| UDP 차단 | 같은 조건 미실행 | 같은 조건 미실행 | own daemon의 kernel UDP outbound deny 아래 실제 native1회·양쪽 link=relay | 같은 조건 미실행 | C의 process 한정 제한을 검증. 네트워크 전체 firewall·다른 후보는 미검증 |
| HTTPS proxy | 같은 고정 조건 미실행 | 같은 고정 조건 미실행; 최소 spike proxy 미구현 | 양쪽 own engine 직접 egress 제한·loopback CONNECT/TLS 아래 native1회/relay/SHA 일치 | 같은 고정 조건 미실행 | C의 process 한정 CONNECT만 확인. 기업 인증·TLS inspection·전역 제약·다른 후보는 미검증 |
| 자체 relay | SSH bastion은 relay 후보와 별도 계약. 강제 relay 미실행 | relay 미구현 | 정상 기존 서비스의 `relay_connected=true`만 관측. 본문 relay 경유·강제 relay·자체 relay 미실행 | 자체 DERP/강제 relay 운영 시험 미실행 | 서버·강제 경로 조건 미확보. 새 유료 VM/relay 배포나 네트워크 정책 변경은 승인 범위 밖 |
| 양방향 SSH 불가 | 기존 양방향 SSH 계약. 같은 조건의 실제 higher-level 요청 미실행 | 기존 bootstrap은 SSH 의존; SSH 없는 data-plane의 실제 native 표본 없음 | bootstrap 후 own controller/helper/engine/native의 TCP22 deny 아래 자율 native1회·상관 회신 성공. 측정 SSH0 | 같은 조건의 실제 VPN+SSH 요청 미실행 | C는 process 한정 제한과 준비 후 data-plane만 검증. 무SSH 신규 설치/전역 단절/다른 후보는 미검증 |

B의 NAT/relay 미구현은 **이번 Python 시험체의 한계**이며 자체 P2P 후보 전체의 지원 불가 판정이 아니다. C peer staging 및 private membership 전제는 후속 시험에서 확보됐다. C의 process 한정 UDP 차단/relay 표본 외에 다른 NAT·proxy·자체 relay·SSH 불가 및 다른 후보의 UDP 차단은 미실행이며, 제한 환경의 장비 부재를 후보 실패나 성공으로 기록하지 않는다.

## 6. P11 남은 실측과 P12 전달 경계

완료된 비교체 범위는 네 후보의 같은 수학 과제 first/followup/재연결 뒤 새 native 답, cached 회수, C peer binary/private membership 준비와 자기 프로세스 정리다. 기존 제품 registry 세션이나 legacy pairing을 편입하지 않았다. 이 완료 범위는 남은 실환경·제품 통합의 생략 승인이 아니다. 아래 owner가 조건 확보 시 다시 확인하며 확보 전에는 미완으로 남긴다.

| 남은 작업 | owner / 다시 볼 시점·조건 | 필요한 실제 증거 | 현재 상태 |
|---|---|---|---|
| peer 제품 runtime·실제 업무 경로 준비 | 코디네이터/P12 통합 담당. D12와 P12 진입 게이트 충족 뒤 | 고정 제품 source manifest·peer runtime readback 및 발견→선택→핸드셰이크→협업 | private carrier 비교에서 제품 runtime을 배포하지 않음. legacy xsm pairing 재사용 안 함 |
| B의 안전한 전송·가입 | P11 시험 담당. 승인된 비교 범위·격리 조건 확보 시 | 암호화, 실제 머신 신원, SSH 비의존 bootstrap, 키 회수, NAT/relay | private native·재시작 회수는 확보. 나머지는 최소 TCP 시험체의 미구현 영역이며 제품 채택/새 종속성은 D12와 별개 확인 |
| 다른 NAT·다른 후보 UDP 차단·proxy·자체 relay·SSH 불가 | 실환경 담당/사용자. 별도 장비·권한 확보 시 | 조건별 실제 bind/경로/포트·실패·대체 trace | 장비·조건 미확보로 미실행. 현재 direct 성공을 복제하지 않음 |
| 설치 마찰과 실제 사람 조작 수 | P11 담당. 각 후보의 승인된 clean 환경 실행 시 | 로그인/동의/가입/훅 신뢰를 구분한 조작 수와 실패·복구 | 기존 상태 재사용이므로 이번 신규 onboarding 미측정 |
| 운영·업데이트·키 회수·제거·로컬 유지 | P11/P12 담당. 승인된 격리 운영 조건 확보 시 | 업데이트/회수 실패·복구, 원격 중단 중 제품 로컬 왕복, 소유 설정/권한 잔여 readback | carrier 재연결·cached 회수·자기 프로세스/리스너 정리는 확보. 운영 SSH/VPN 제거와 제품 로컬 유지·키 회수 전체는 미실행 |
| 라이선스·공급·운영 비용 비교 | P11 비교 담당·공급 검증 담당. 후보별 고정 공급 경로와 운영 절차 확보 시 | 출처/라이선스/업데이트 소유자, 실제 운영 비용과 미확정 항목 | Reason의 기존 라이선스 자료와 binary pin은 있음. 네 후보의 제품 공급·운영 비용 비교 전체는 미완 |
| 초대/제명/전환·origin·업무 권한 | D12 뒤 P12 통합/검증 담당 | A21-02/04/06, 새 origin 증거와 xsm 권한 분리 | fixture 인증 성공을 이 계약의 성공으로 세지 않음 |
| 고정 UDP/IPv6/fallback | P11/P12 실환경 담당. 고정 버전과 격리 포트 조건 확보 시 | A21-07 실제 점유·IPv6 부재·주소 변경 및 선택된 포트 | 기존 0.12.11 분석과 별도로 0.12.10 private 실행은 확보. wire UDP 포트·IPv6 부재·점유/대체 조건은 미실행 |
| 독립 검토와 G11 판정 | 코디네이터/독립 검증 담당. 부족 셀 보완 뒤 | A21-03 및 G11 설치·개입·첫 왕복·경로·운영/제거의 동일 기준 대조 | [판정 초안](records/gates/G11-remote-comparison-draft.md)은 partial 제안. 이 문서로 passed를 확정하지 않음 |
| D12 사용자 선택 | 사용자. 비교 결과와 반대 증거 검토 뒤 | backend·종속성·relay·멤버 관리·공개 범위에 대한 실제 응답 | 미응답·미선택. private C 시험에 대한 코디네이터 범위 판단을 D12 응답으로 해석하지 않음 |

D12의 선택, 새 종속성, relay 운영자, 제품 멤버 관리 권한, 공개 범위는 사용자가 정한다. 선택 후에도 엔진의 팀 accept·TCP ACK·SSH exit 0이 xsm의 사용자 승인이나 실제 상대 회신을 대신하지 않는다. P12 진입은 [execution.md](execution.md)의 G04/05/06/07/09/10/11 및 D12 전제를 별도로 만족해야 한다. 이번 갱신은 로컬 gate 판정을 바꾸지 않으며, D12 미선택 및 G11 미완으로 P12는 전제 미충족이다.

## 7. 재현·증거·정리

### 역사: 최초 읽기 전용 조사·합성 시험 명령

```sh
hostname
ssh -oBatchMode=yes -oConnectTimeout=5 jaesol-macmini /usr/bin/python3 -
# stdin의 읽기 전용 probe: hostname/버전/선택 repo status/native metadata.
# git 조회는 GIT_OPTIONAL_LOCKS=0, 프로필을 시작하는 명령은 사용하지 않음.

/usr/bin/python3 <저장소 밖 조사 기록>/probe_engine.py \
  --engine /Users/jaesolshin/.reason/bin/reason-network \
  --output /tmp/p11-reason-ipc-20261028.json

/usr/bin/python3 /tmp/p11-transport-comparison-20261028.py
```

| 근거 | 위치 / 결과 |
|---|---|
| 두 머신 transport 시험 코드 | `/tmp/p11-transport-comparison-20261028.py` |
| 코드 SHA-256 | `c503e1ef9d6620a6dd39bde27bda9107501182ad50174c2b272e0470da4bdf89` |
| 최초 실패 보존 | `/tmp/p11-transport-comparison-20261028-first.json`: A/D 성공, B timeout |
| 수정 후 결과 | `/tmp/p11-transport-comparison-20261028.json`: A/D/B 3개 fixture 성공 |
| 고정 엔진 IPC | `/tmp/p11-reason-ipc-20261028.json`: 14/14, 팀 생성 없음, 실제 LLM 세션 없음, daemon 종료 |
| 임시 리스너 종료 | peer 52767·52768 connect code 61, 격리 Reason socket code 61 |
| 임시 상태 정리 | B 재실행 fixture와 최초 실패 fixture 제거. 로컬 `/private/tmp/rn-ipc-q8auf9vv` 제거. 코드·결과 JSON은 보존 |

### 최신 native 증거와 정리

| 근거 | 위치 / 결과 |
|---|---|
| A/B/D native 보고서·JSON·manifest | [보고서](../../../deliverables/p11-live/native-carrier-roundtrip-20261029.md), [JSON](../../../deliverables/p11-live/native-carrier-roundtrip-20261029.json), [manifest](../../../deliverables/p11-live/native-carrier-manifest-20261029.json): native 9회, cached 3회. 그 보고서의 C staging/미실행 판정은 당시 범위이며 후속 C 결과로 보완됨 |
| A/B/D 코드·원시 증거 | local `/tmp/p11-native-r292609m`, peer `/tmp/p11-native-2nemv2of`. driver SHA-256 `37c7f02d2d717c91683d61de6f44afd43e80aa4eda49673567b43c0e8fe1ab6a` |
| A/B/D 시작·종료 | peer driver 6개·native handle 9개 종료, local SSH exit 0, 추가 tmp-bound 프로세스 0. B 49909/49941 stop 뒤 connect 61 |
| C native 보고서·JSON·manifest | [보고서](../../../deliverables/p11-live/C-native-roundtrip-20261029.md), [JSON](../../../deliverables/p11-live/C-native-roundtrip-20261029.json), [manifest](../../../deliverables/p11-live/C-native-evidence-manifest-20261029.json): native 6회, cached 2회. ID 공개는 hash/상태로 제한 |
| C 최초 코드·원시 증거 | local `/private/tmp/p11-C-a33f52rq`, peer `/private/tmp/p11-C-q27ngmzj` |
| C 보강 재실행 코드·원시 증거 | local `/private/tmp/p11-C-av3sz_4j`, peer `/private/tmp/p11-C-_n_rujrd`. 공개 C source는 이 실행과 byte 일치; 최초 실행 source는 tmp `executed-code`에 별도 보존 |
| C 시작·종료 | daemon handle 10개·native 6개·SSH control 2개 종료. own IPC connect 61, private state/HOME/키/engine 사본 제거, 최종 잔여 프로세스 0. 기존 서비스 stop 없음 |
| C 기록 검사 | [검사 결과](../../../deliverables/p11-live/C-evidence-check-20261029.json): Python 3.9.6/3.14.6 각각 파일 hash 111개·native 결과 6개·변이 거절 3개. 새 모델 호출 0이며 물리 환경 추가 실행 증거가 아님 |

`/tmp` 증거는 재부팅 등으로 소실될 수 있다. 최신 보고서/JSON/manifest는 `deliverables/p11-live`에 있고 과거 합성·초기 실패도 역사로 보존했다. C의 일시 fixture create/join은 전체 비교 요청에 대한 코디네이터 판단으로 실행했으며 별도 명시 승인 응답을 받은 것으로 기록하지 않는다. 실제 사용자 팀 가입·전역 권한 확대·backend 확정은 하지 않았고 기존 SSH/Tailscale/Reason 서비스·프로필·제품 scope를 유지했다.
