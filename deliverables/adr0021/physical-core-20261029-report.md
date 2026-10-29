# ADR-0021 두 물리 머신 physical core 검증 — 2026-10-29

두 물리 Mac의 실제 Python daemon과 Rust sidecar로 가입, 서명 멤버십, 양방향 P2P ping, 재시작 후 기기 신원 유지, 종료를 확인했다. 실제 agent 세션 발견·선택·질문·회신 여정의 결과로 해석하지 않는다.

## 실행 대상과 복사본

| 항목 | jaesol-macbookpro | jaesol-macmini |
|---|---|---|
| 실제 hostname | Jaesolui-MacBookPro.local | Jaesolui-Macmini.local |
| 아키텍처 / Python | arm64 / 3.14.6 | arm64 / 3.9.6 |
| 현재 Tailnet IPv4 | 100.123.30.11 | 100.77.24.16 |
| 관측 LAN IPv4 | 192.168.0.11 | 192.168.0.64 |
| private generation | `/private/tmp/xpc-q0b6vtol` | `/private/tmp/xpc-pnoh2tco` |

대상은 위 두 Mac으로 제한했다. Tailscale status는 양쪽에서 다시 조회하고 두 Mac만 추출했다. 양쪽 netcheck의 관측 공인 IPv4는 같았고 UDP 가능, 공인 IPv6 미관측이었다. 이는 현재 동일 LAN·동일 공인 IPv4 환경의 증거이며 다른 NAT 환경의 성공 증거가 아니다. 실제 공인 주소는 private raw에 보존했다.

저장소를 원격 동기화·merge·설치하지 않았다. 새 0700 임시 디렉터리로 Python 모듈 52개, 기존 arm64 debug binary, 관측용 helper 두 개를 복사했다. 55개 파일의 SHA-256 manifest는 양쪽에서 일치했다.

- manifest SHA-256: `7f174c8b63081d86ce33eae55eb8e4bdee24de31c64d803837e13054497e5ec7`
- native binary SHA-256: `35a4af3f5b298fa7ecb65bdc2eba7511af77c3350056f0d27ee24a4d4363242a`
- 각 호스트의 `payload/manifest.json`에 개별 소스 SHA가 있다. 복사본의 source/binary 일치는 [원결과](physical-core-20261029-results.json)의 양쪽 `verify` 기록으로 확인한다.

복사 시점 이후 병렬 작업이 `xsm/network_messages.py`, `xsm/network_transport.py`를 수정했다. 이번 실행은 동일 manifest의 동결된 복사본을 검증했다. transport의 뒤이은 변경은 설치 바이너리 탐색과 상태 조회 속성 추가였으며, 이번에 명시한 binary·RPC 경로와 분리된다. 실행 종료 시 저장소 전체가 같은 SHA였다고 주장하지 않는다. [후속 소스 대조](physical-core-20261029-privacy.json)에 파일별 결과를 보존했다.

## 실제 실행과 선택 경로

공개 CLI `python -B -m xsm network init/invite/join/members/status/stop`을 사용했다. ping은 각 호스트의 private Unix socket에 `network.call({op: ping, peer: public_address})`를 호출했다. 양쪽 서비스는 `python -B`와 해당 호스트의 private HOME/XSM_HOME/TMPDIR로 실행했다.

| 별도 실행 | 요청 설정 | 실제 바인딩 IPv4 | 관측된 실제 선택 경로 | 판정 |
|---|---|---|---|---|
| 기본 실행 | public relay preset, port 0 | Book `0.0.0.0:53927`, mini `0.0.0.0:56886` | 양방향 `direct`, 상대 `192.168.0.64:56886` / `192.168.0.11:53927` | 가입·양방향 LAN P2P 왕복 통과 |
| Tailnet 후보 실행 | relay off, 각자의 Tailnet `IP:0` | Book `0.0.0.0:58566`, mini `0.0.0.0:61032` | Tailnet `100.77.24.16:61032`, `100.123.30.11:58566`와 LAN 주소 사이 전환 | 왕복 통과, 전체 Tailnet 경유로 판정하지 않음 |

두 실행 모두 `requested_port=0`, `port_fallback=false`였다. IPv6 bind도 생성됐으며 실제 주소는 원결과의 ready에 있다. 기본 실행의 `relay_mode=public`과 `relay_online=false`를 구분한다. 이번 성공 경로는 LAN direct이며 공개 relay를 실제 경유한 성공이 아니다.

두 번째 실행은 Tailnet 후보만 존재한 경우보다 강한 증거를 남겼다. 실제 `last_transport.remote_address`에 상대 Tailnet IP가 기록됐다. 다만 후속 snapshot에는 LAN이 선택됐으므로 요청·응답 전체 또는 지속적인 Tailnet 강제 경유로 설명하지 않는다. [경로별 이벤트](physical-core-20261029-validation.json)의 `baseline_paths`와 `tail_candidate_paths`를 대조할 수 있다.

특정 상대 Tailnet IP만 허용하는 process-local sandbox profile은 이 Mac에서 컴파일되지 않았다. UDP 전부 차단 profile은 exit 0, literal-IP 허용 profile은 `host must be * or localhost in network address`, exit 65였다. 이 capability probe는 `/usr/bin/true`만 실행했고 Rust를 시작하지 않았다. 글로벌 방화벽·OS 설정·권한 변경은 하지 않았다. 강제 Tailnet-only 검증은 미확보로 남긴다.

## TLS origin·서명·SSH 역할

각 호스트의 Rust가 자기 private XSM에서 새 기기키를 생성했다. private key 값은 열거나 복사하거나 출력하지 않았다. key 파일 mode 0600, key root mode 0700을 metadata로 확인했다. 두 번째 시작에서 양쪽 `endpoint_id`가 각각 첫 시작과 같았고 public status는 active였으며 멤버십도 유지됐다.

초대는 Book의 공개 invite CLI가 만든 0600 private file에 있었다. 제어 프로그램은 이 파일을 SSH subprocess의 stdin으로 직접 연결했고, mini의 공개 join CLI는 `--ticket-stdin`으로 읽었다. 초대 값은 argv·로그·provider context에 넣지 않았다. 로컬 출력·audit·공개 결과 및 mini의 raw 출력 13개를 프로그램으로 검사해 초대 secret 일치 0건을 확인했다. native key 파일은 이 검사에서도 열지 않았다.

SSH는 파일 provisioning, private CLI/UDS 동작의 시작, 상태·진단 관측에 사용했다. 가입 후 ping의 본문 전달은 Rust QUIC/TLS 연결이 수행했다. 이를 다음 실제 기록으로 구분했다.

1. 발신 host의 실제 `Sidecar.request` 직전 JSON 본문 SHA와 상대 Rust `event:request`의 본문 SHA가 양방향 모두 일치했다. 실제 본문을 일반 로그에 쓰지 않고 digest만 남겼다.
2. 수신 이벤트의 `origin`은 상대 host의 ready `endpoint_id`와 양방향 모두 일치했다. Python 관측 helper는 원래 dispatch 검증을 먼저 실행하고 Rust가 제공한 origin을 기록했다. 본문의 이름이나 origin 주장을 신원으로 대체하지 않았다.
3. 공개 members에는 양쪽 기기의 active 서명 멤버십이 나타났고 재시작 이후에도 유지됐다. 검증은 실제 Rust sign/verify와 membership 저장·adoption 경로를 사용했다. fixture 서명·mock 네트워크는 사용하지 않았다.

관측 helper는 원래 request/dispatch의 결과를 대체하지 않는다. 별도 `observer.py`에서 호출 경계의 digest, TLS origin, `transport.last_transport`, PID, ready만 기록한다. 전달한 `xsm` 소스 파일은 수정하지 않았다. [실행 제어 코드](physical-core-20261029-run.py)에 해당 helper와 SSH stdin 연결이 있다.

## 종료와 private raw

두 단계의 소유 Python daemon 4개와 Rust sidecar 4개를 모두 공개 stop으로 종료했다. 같은 generation의 기록된 PID 잔여 0, control socket 잔여 0이다. 양쪽에서 실제 사용했던 IPv4/IPv6 UDP bind 8개를 다시 bind할 수 있음을 확인했다. 사용자 세션에 보낸 신호는 0이다. [최종 종료 검사](physical-core-20261029-validation.json)의 `cleanup`에 명령 결과가 있다.

private raw는 다음 0700 generation 아래에 보존했다. 개별 raw 파일은 0600이다. 새 key와 state도 각 호스트에만 남겨 두었으며 외부에 복사하지 않았다.

- Book: `/private/tmp/xpc-q0b6vtol/raw/` — transport event, 원 CLI stdout/stderr, 환경 관측, sandbox capability, 최종 cleanup.
- mini: `/private/tmp/xpc-pnoh2tco/raw/` — 해당 호스트 transport event와 원 CLI stdout/stderr.
- manifest·복사본: 각 generation의 `payload/`. state·key: 각 generation의 `state/`.

## 검증 범위

physical core의 두 머신 가입·왕복·TLS origin·서명 멤버십·키 지속·소유 서비스 종료는 통과했다. actual agent workflow, 다른 NAT, UDP 차단, HTTPS proxy, 공개·자체 relay 실제 경유, Tailnet-only 강제 경유는 이번 성공에 포함하지 않는다. 다른 NAT 및 강제 경로 후속 검증은 coordinator가 해당 환경 또는 허용 범위 내 process-local IP 제한 수단을 확보했을 때 다시 수행할 항목으로 남긴다. 새 유료 서버나 relay는 배포하지 않았다.
