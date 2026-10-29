# ADR-0021 구현 작업 계약

사용자 goal은 `adr-0021 완주`다. ADR-0021의 전체 수용 조건과 ADR-0024 원격 여정을 유지한다. 기존 전체 구현 goal의 일시정지와 구별하며 이번 goal만 실행한다. 새 제품 구현·실측 결과는 이전 carrier 비교와 구분한다.

## 구현 분담과 경계

- `native/xsm-net/`: Rust iroh 전송 sidecar. 자체 P2P이며 Reason 엔진 바이너리를 사용하지 않는다. registry에서 확인한 iroh 1.4.1을 고정하고 Cargo.lock을 기록한다. Python의 기존 로컬·SSH 경로는 sidecar 없이 동작한다.
- `xsm/network_membership.py`: 서명 멤버십·초대·원자적 영속 저장. 기기키는 sidecar가 보유하고 Python은 sign/verify IPC를 사용한다. 기존 활성 멤버 누구나 변경할 수 있고 founder는 신뢰의 출발점이다.
- `xsm/network.py`와 기존 CLI/MCP/발견 통합: 사용자별 private Unix control socket, sidecar 수명·RPC, 멤버십 검증 뒤 원격 작업 전달. 네트워크 가입·공개·협업·파일 권한은 분리한다.

## Sidecar IPC v1

stdin/stdout은 UTF-8 JSONL이며 stdout은 프로토콜 전용이다. 외부 peer에게는 동일 ALPN `xsm/network/1`의 QUIC 양방향 stream으로 JSON 요청/응답을 전달한다. 원격 frame 상한은 8 MiB로, 기존 4 MiB 첨부 bundle의 base64와 metadata를 담는 전송 parser bound다. 본문·초대·키를 stderr/일반 로그에 쓰지 않는다.

프로세스: `xsm-net serve --state-dir PATH [--port PORT] [--relay off|URL] [--direct-address IP:PORT]`.

- 준비 출력: `{event:"ready", endpoint_id:PUBLIC_KEY, address:IROH_ENDPOINT_ADDRESS, requested_port:PORT, bound_addresses:[...], port_fallback:BOOL}`. private key는 private state 안에만 유지한다.
- 명령 `{id:ID, op:"request", peer:IROH_ENDPOINT_ADDRESS, body:JSON, timeout_ms:N}` → `{event:"response", id:ID, origin:AUTHENTICATED_ENDPOINT_ID, body:JSON}` 또는 `{event:"error", id:ID, code:STABLE_CODE}`.
- 수신 `{event:"request", request_id:ID, origin:AUTHENTICATED_ENDPOINT_ID, body:JSON}` → Python이 `{op:"respond", id:ID, body:JSON}`로 응답한다. origin은 TLS peer key에서만 얻는다.
- `{id:ID, op:"sign", data:BASE64}` → `{event:"result", id:ID, signature:HEX}`.
- `{id:ID, op:"verify", endpoint_id:PUBLIC_KEY, data:BASE64, signature:HEX}` → `{event:"result", id:ID, valid:BOOL}`.
- `{id:ID, op:"address"}` → `{event:"result", id:ID, address:IROH_ENDPOINT_ADDRESS}`. `{op:"shutdown"}`은 자기 프로세스만 종료한다.

기본 relay는 iroh의 공개 relay preset이며 URL을 지정하면 custom relay를 사용한다. `off`는 직접 연결 시험용이다. Tailscale은 도달 가능한 direct-address 후보를 더하며 멤버십을 부여하지 않는다. port 기본값은 0, 명시 port의 AddrInUse만 임의 port로 대체하고 실제 주소를 보고한다. 다른 오류를 성공으로 숨기지 않는다.

## Membership Python API

`MembershipStore(root, node_id, sign, verify, clock=time.time)`의 sign은 `bytes -> hex signature`, verify는 `(public_key, bytes, hex_signature) -> bool`다. 구현은 private 파일·잠금·원자적 교체로 동시 쓰기와 원 응답 유실을 처리한다.

- `initialize(name, machine_name)` → signed network state.
- `public_state()` → 비밀 없는 상태, `snapshot()` → 활성 멤버에게만 전송할 내부 상태.
- `issue_invite(reusable=True, lifetime_seconds=None)` → `{secret, invite, network_id}`. 일회용은 lifetime을 caller가 명시한다. 공개 목록은 secret을 반환하지 않는다.
- `redeem(secret, endpoint_id, machine_name)` → signed admission/state. reusable은 활성 멤버가 수락한다. 일회용은 issuer가 소비를 직렬화하고 응답 유실 뒤 같은 기기의 재시도는 idempotent하게 회수한다. issuer가 offline이면 성공으로 만들지 않는다.
- `merge(state)`는 network ID·서명·admission chain·입력 bound를 검증하고 결정적으로 병합한다.
- `is_active(endpoint_id)`, `members()`, `remove(endpoint_id)`, `revoke_invite(invite_hash)`, `leave()`를 제공한다. removed 기기의 연결은 거절하되 악의적 기존 멤버에 대한 강한 암호학적 회수 보장은 주장하지 않는다.
- `adopt(state)`는 신규 가입자가 verified state를 처음 영속화한다. 기존 network 전환은 검증된 새 상태가 준비된 뒤 적용하며 실패 시 이전 상태를 보존한다.

단계별 실제 결과와 미검증 환경을 기록한다. 필요한 제품 검사·native 왕복·두 머신 여정을 수행하되 동일 성공을 반복하거나 보고서마다 대규모 검증기를 만들지 않는다. 주요 구현 게이트는 사용자 지정 Opus 5.5로 독립 검토한다. 실제 사용자 설정·권한·배포·유료 자원 변경은 별도 실행 승인 경계를 따른다.
