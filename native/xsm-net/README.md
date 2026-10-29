# xsm-net

ADR-0021의 선택적 Rust 전송 sidecar다. `iroh = "=1.4.1"`과 Cargo.lock으로 의존성을 고정한다. Python broker 없이 두 프로세스의 실제 암호화 QUIC stream을 시험한다. 네트워크 멤버십·가입·MCP/세션 권한은 Python broker가 판단한다.

## 빌드와 실행

모든 Cargo 명령은 이 디렉터리에서 실행한다. Rust 1.91 이상이 필요하다.

```sh
cd /Users/jaesolshin/Documents/GitHub/cross-session-messaging/native/xsm-net
cargo build --locked
target/debug/xsm-net serve --state-dir /path/to/private-state
target/debug/xsm-net serve --state-dir /path/to/private-state --port 4242 --relay off
target/debug/xsm-net serve --state-dir /path/to/private-state --relay https://relay.example.com --direct-address 100.64.0.7:0
```

기본 relay는 iroh의 공개 production relay map이다. `--relay URL`은 해당 HTTPS relay만 설정한다. URL에 사용자 정보·query·fragment를 허용하지 않는다. `off`는 relay를 사용하지 않는다. HTTP(S) proxy는 iroh의 `proxy_from_env()`를 통해 기존 환경 설정을 따른다. 자체 relay는 유효한 TLS 인증서가 필요하며 인증서 검증을 끄지 않는다.

`--port` 기본값은 0이다. 명시 포트의 필수 IPv4 bind가 `AddrInUse`로 실패한 경우에만 임의 포트로 재시도한다. IPv6는 선택적이다. 실제 bind 주소, 요청 포트, fallback 여부를 ready에 보고한다. `--direct-address IP:0`은 같은 주소 계열의 실제 bound UDP 포트로 치환하며, 해당 계열의 socket이 없으면 `direct_address_unbound_family`로 실패한다. 후보 주소 추가는 멤버십이나 권한을 부여하지 않는다.

`node.secret`은 32바이트 개인키이며 권한은 0600이다. 새 상태 디렉터리는 0700으로 생성한다. 기존 상태 디렉터리도 소유자 전용이어야 한다. 키와 lock의 symlink·hardlink·잘못된 소유자/권한을 거절한다. 키는 임시 0600 파일에 완전히 기록·fsync한 후, 프로세스 수명 동안 보유한 배타 lock 아래 원자적으로 게시하고 디렉터리를 fsync한다. 손상된 기존 키는 재생성하지 않는다. 키와 본문은 stdout/stderr 로그에 기록하지 않는다.

## JSONL IPC v1

stdout은 프로토콜 전용이며, stderr에는 본문·초대·개인키를 포함하지 않는 안정된 오류 코드만 쓴다. 주소는 iroh `EndpointAddr`의 JSON 객체이고 ID는 공개키 문자열이다. `id`는 원래 JSON 값을 그대로 회신한다.

| 입력 op | 출력 |
|---|---|
| 프로세스 시작 | `event:ready`, `endpoint_id`, `address`, `requested_port`, `bound_addresses`, `port_fallback`, `relay_mode`, `relay_online` |
| `request`, `id`, `peer`, `body`, 선택 `timeout_ms` | `event:response`, `id`, `origin`, `body`, 경로 필드; 실패 시 `event:error`, `id`, `code` |
| 원격 요청 수신 | `event:request`, `request_id`, `origin`, `body`, 경로 필드 |
| `respond`, `id:request_id`, `body` | 원격 stream 응답. 이후 아래 경로 진단 이벤트 |
| `sign`, `id`, `data:BASE64` | `event:result`, `id`, `signature:HEX` |
| `verify`, `id`, `endpoint_id`, `data:BASE64`, `signature:HEX` | `event:result`, `id`, `valid:BOOL` |
| `address`, `id` | `event:result`, `id`, 현재 `address` |
| `shutdown` 또는 stdin EOF | 자기 endpoint와 프로세스 종료 |

`origin`은 handshake가 끝난 실제 `Connection.remote_id()`에서만 가져온다. 본문에 포함된 origin/name/권한 주장은 전송 신원에 영향을 주지 않는다. 잘못된 서명·다른 키·변조 데이터는 `valid:false`다. 잘못된 base64는 `invalid_base64` 오류다.

### 경로 관측 계약 확장

2026-10-29 추가 지시에 따라 `request`/`response` 이벤트에 `path:direct|relay|unknown`을 추가했다. 실제 선택된 `Connection.paths()` 항목이 IP이면 `remote_address`, relay이면 `relay_url`을 추가한다. 해당 항목이 없으면 주소 필드도 없다. `transport`에는 같은 관측과 전체 활성 경로 목록이 있다. 전역 relay 연결 상태에서 본문의 경로를 추정하지 않는다. `fallback_reason:direct_path_not_selected`는 관측한 선택 상태이며 NAT·방화벽 실패 원인을 확정하는 정보가 아니다.

기존 `respond`에는 결과 이벤트가 없었으므로 다음 진단 이벤트를 추가했다. Broker는 이 이벤트를 업무 응답으로 처리하지 않고 진단으로 수용해야 한다.

```json
{"event":"path","direction":"incoming","request_id":"in-1","origin":"PUBLIC_KEY","phase":"response_written","path":"direct","remote_address":"IP:PORT","transport":{"path":"direct"}}
```

`response_written`은 QUIC stream에 응답을 기록한 뒤의 관측이며, 상대 애플리케이션 수신·업무 완료 증거가 아니다. 상대가 `STOP_SENDING`을 보내면 별도 `phase:response_stopped`, `code:peer_stopped` 진단을 보낸다. ready의 `relay_online`은 최대 3초 준비 대기 시점의 상태다. 이후 relay 주소는 `address`로 다시 조회한다.

### 유한 입력과 자원 한도

원격 stream은 ALPN `xsm/network/1`을 사용한다. frame은 4바이트 big-endian 길이, UTF-8 JSON 본문, FIN 순서다. JSON 본문 상한은 정확히 8 MiB이며 할당 전에 길이를 검증한다. 큰 길이·잘린 frame·뒤따르는 데이터·잘못된 JSON을 거절한다. IPC line은 12 MiB로 제한하고 초과 입력을 newline까지 버린 뒤 다음 명령을 처리한다.

발신 요청은 기본 30초, 최대 120초다. 수신 stream도 최대 120초다. 발신 32개·수신 32개를 별도로 제한하며 총 연결은 64개, 인증된 기기키별 연결 4개·수신 stream 4개를 허용한다. handshake 대기는 10초, 유휴 연결은 15초로 제한한다. stdout을 읽지 않는 controller가 종료를 영구 차단하지 않도록 write/runtime 종료 대기를 제한한다.

## 실제 검증

2026-10-29 macOS arm64의 동일 호스트에서 실행했다. 테스트용 상태와 키는 임시 디렉터리만 사용했다. Python broker/SSH/평문 TCP를 전송 대체물로 사용하지 않았다.

```sh
cargo check
cargo build --locked
cargo test --locked --all-targets
cargo test --locked --all-targets -- --include-ignored
cargo test --locked --test sidecar live_public_and_custom_relay_encrypted_streams -- --ignored --nocapture
python3 tests/mutation_check.py
cargo clippy --locked --all-targets -- -D warnings
cargo fmt --all -- --check
```

`tests/sidecar.rs`의 로컬 검사 17개는 실제 바이너리/QUIC 경로에서 다음을 검증한다.

- 두 sidecar의 요청·응답과 역방향 왕복, TLS origin 및 본문 origin 위조 격리, direct 주소·수신 응답 경로 진단.
- 서명 검증, 데이터 변조·다른 키·위조 서명 거절, 재시작 ID/서명 유지, 키 파일 0600.
- 실제 UDP 포트 충돌과 fallback 후 왕복, custom/off 설정, `IP:0`의 bound 포트 치환.
- 초과 원격 요청/응답 길이의 조기 거절, 정확히 8 MiB인 요청/응답 왕복, 잘린/다중/잘못된 frame 거절.
- 부분 JSONL 입력 중 병렬 응답 완료, 초과 IPC line 복구, timeout·잘못된 peer·없는 응답 ID.
- stdout을 읽지 않을 때 종료, 수신 stream 정체 중 발신 유지, 동일 기기의 여러 연결에 걸친 stream 한도.
- 중복 키 사용 lock, symlink·잘못된 권한·손상 키 거절, 정상 연결 대조군이 있는 잘못된 예상 기기키 거절.

인터넷 검사 1개는 기본 공개 relay와 명시 custom URL `https://aps1-1.relay.n0.iroh.link.` 각각에서 실제 암호화 요청·응답에 성공했다. 상대 endpoint의 IP transport 자체를 제거하여 direct UDP를 사용할 수 없게 했고, 실제 선택 경로 `relay`와 relay URL을 검증했다. 이 custom 표본은 공개 relay를 custom map으로 지정한 시험이며 자체 운영 서버를 설치한 표본은 아니다. 인터넷 검사는 기본 suite에서 명시적으로 제외되므로 위 `--ignored` 명령으로 별도 실행했다.

최종 `cargo test --locked --all-targets -- --include-ignored` 결과는 `18 passed; 0 failed; 0 ignored`이며 12.19초에 완료됐다. `cargo build --locked`, Clippy `-D warnings`, format 검사도 통과했다.

변이 검사 9개도 모두 결함을 검출했다. TLS origin 위조, frame bound 제거, 재시작 키 변경, 서명 검증 무력화, fallback 제거, JSONL 취소 결함, `IP:0` 치환 제거, 잘못된 기기키 대조군 변경, 기기별 stream 한도 무력화를 각각 실제 Rust 검사 실패로 확인하고 원본을 복원했다. Python 스크립트는 Cargo 실행과 소스의 임시 변이/복원만 수행한다.

미검증 환경은 두 물리 머신·서로 다른 NAT·UDP 차단 네트워크·실제 HTTPS proxy·자체 운영 relay·IPv6 자체가 없는 호스트다. 이번 검사로 ADR-0021 전체 수용 조건이나 Python 멤버십/세션 여정 완료를 주장하지 않는다. 해당 통합·환경 실측은 전체 ADR 완료의 남은 항목이다.

별도 Codex task의 읽기 전용 병렬 검토에서 발견한 키 저장·부분 JSONL·종료·자원 한도·경로 진단 결함을 반영했다. 계획서의 Opus 5.5 지정 독립 검토 게이트는 이 담당 작업에서 실행하지 않았다.

## API 근거

- [iroh 1.4.1 crate](https://docs.rs/crate/iroh/1.4.1): 공개 registry에서 받은 실제 crate 소스로 compile했다.
- [완료된 Connection의 TLS peer ID와 paths](https://docs.rs/iroh/1.4.1/iroh/endpoint/struct.Connection.html): origin과 경로 관측의 근거.
- [Builder의 bind/proxy 설정](https://docs.rs/iroh/1.4.1/iroh/endpoint/struct.Builder.html): 포트 충돌 오류와 optional IPv6, proxy 환경 설정.
- [RelayMode](https://docs.rs/iroh/1.4.1/iroh/enum.RelayMode.html): production/default, custom, disabled 구분.
