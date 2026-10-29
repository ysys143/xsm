# ADR-0021 bounded local self-hosted relay 검증

실제 xsm 제품의 기존 CLI와 두 Python daemon·Rust sidecar가 직접 빌드한 공식 `iroh-relay 1.4.1` 프로세스를 경유했다. 최종 debug와 release 모두 가입, 멤버 목록, 양방향 RPC, 재시작 후 기기 신원 유지·RPC를 통과했다. 각 프로필의 실제 `last_transport` snapshot 6개가 모두 자체 relay를 선택했다.

이는 같은 호스트의 localhost HTTP 개발 relay 검증이다. 두 물리 머신의 relay 경유, 공개 HTTPS 자체 relay 배포, 다른 NAT, 실제 agent 여정 또는 ADR-0021 전체 완료를 뜻하지 않는다. 앞선 두 물리 머신의 LAN core 결과는 [별도 보고서](physical-core-20261029-report.md)에 있다. 공개 custom URL 시험을 self-host 성공으로 계산하지 않았다.

## 수정한 제품 결함

수정 범위는 위임받은 `native/xsm-net/src/transport.rs`와 관련 새 테스트 두 파일이다. Python core, membership 서명 검증, 다른 담당 native 파일은 수정하지 않았다.

1. Python configure는 loopback HTTP를 허용했지만 Rust는 HTTPS만 허용했다. Rust가 Python과 같은 세 literal host `localhost`, `127.0.0.1`, `[::1]`에 HTTP를 허용하게 했다. 외부 HTTP, 숫자·인코딩 alias, 사용자 정보, query, fragment 거절은 유지한다. URL 파서가 `127.1` 등을 loopback으로 정규화해 허용 범위를 넓히지 않도록 원래 authority를 확인한다.
2. 준비 단계의 3초 제한 전에 home relay 선택이 끝나지 않으면 공개 주소에서 명시한 custom relay URL이 빠졌다. 실제 release 검사에서 relay 접속은 있었지만 초대 주소가 IP 후보만 포함해 UDP 차단 중 가입이 timeout됐다. `Transport.address()`가 명시한 custom URL을 초기 라우팅 후보로 보존하게 했다. 후보가 있다는 사실을 연결 성공으로 취급하지 않으며 `relay_online`이나 실제 경로 진단 값을 성공으로 바꾸지 않는다.

두 결함은 수정 전 각각 실패를 재현했다. 수정 후 native URL/주소/실제 JSONL 검사 5개와 기존 numeric 검사 1개가 debug·release 각각 통과했다. 원실패 로그와 중간 실행도 private raw에 보존했다.

HTTPS 서버 인증을 끄는 API·옵션은 추가하지 않았다. 이번 outer relay hop은 localhost HTTP라 HTTPS 서버 인증서 검증 자체의 시험은 아니다. HTTPS 경로의 CA/TLS 설정은 기존대로이며, 내부 iroh QUIC/TLS 기기 인증과 실제 서명 멤버십을 사용했다.

## 공식 source와 자체 프로세스

현재 native lockfile과 같은 `iroh-relay 1.4.1` 공식 crate를 사용했다. archive checksum을 대조한 뒤 source를 private tmp로 복사해 `server` feature로 빌드했다. Cargo home/cache/target도 private tmp에 격리했으며 전역 Cargo 설정·cache에 쓰지 않았다.

- crate SHA-256: `7e5589e7c1475700686603a970275687f760df853bc6525c7eb1347aa31d7230`
- upstream commit: `d6c6963b9602d1b8dd2ba53b6519e7eb19cc7940`
- 실행 version 출력: `iroh-relay 1.4.1`
- 공식 [`README`](https://github.com/n0-computer/iroh/blob/d6c6963b9602d1b8dd2ba53b6519e7eb19cc7940/iroh-relay/README.md)의 개발 모드를 사용했다. [`server` 구현](https://github.com/n0-computer/iroh/blob/d6c6963b9602d1b8dd2ba53b6519e7eb19cc7940/iroh-relay/src/server.rs)은 HTTP/HTTPS를 지원한다.

relay는 `--dev --config-path`로 `127.0.0.1`의 고유 고포트에만 bind했다. metrics와 QUIC address discovery를 껐고 도메인·인증서·ACME·유료 서버·공개 relay 배포를 만들지 않았다. 공식 relay의 실제 listener·PID·로그와 제품 상태를 함께 기록했다.

## SDK 선행 검사와 제품 검사의 차이

| 항목 | SDK 선행 검사 | 최종 제품 검사 |
|---|---|---|
| relay | 소유한 공식 relay 프로세스 | 같은 공식 binary로 실행마다 새 소유 프로세스 |
| 클라이언트 | 별도 iroh SDK probe | 기존 xsm CLI + 실제 Python daemon 두 개 + Rust sidecar |
| 직접 UDP 제거 | `clear_ip_transports()`, UDP bind 0 | 제품은 UDP socket을 생성함 |
| relay 강제 | IP transport 자체 제거 | 자기 sidecar에만 sandbox UDP egress 차단 |
| 실제 선택 경로 | 양쪽 connection path가 relay, IP path 없음 | 각 프로필 `last_transport` 6개 모두 relay |
| 가입·멤버십 | 제품 검사 아님 | 실제 init/invite/join/members, native sign/verify |

현재 제품 CLI에 IP transport 자체를 제거하는 설정은 추가하지 않았다. 따라서 **UDP bind 0 endpoint는 SDK에서만 검증했다. 제품에서도 강제 relay 왕복은 가능하지만, 검증한 방식은 UDP socket을 유지한 process-local egress 차단**이다.

사용한 profile은 `(version 1)(allow default)(deny network-outbound (remote udp "*:*"))`다. 새 소유 UDP probe의 무제한 대조군은 loopback datagram을 전달했고, 같은 profile을 적용한 대조군은 PermissionError로 차단됐다. 이 profile을 별도 wrapper를 통해 자기 Rust sidecar에만 적용했다. 실제 Python 서비스나 시스템 방화벽·사용자 세션의 설정은 바꾸지 않았다.

## 제품 경로의 실제 결과

실행한 공개 CLI는 `configure --relay http://127.0.0.1:PORT`, `init`, `invite`, `join --ticket-stdin`, `members`, `status`, `stop`이다. 초대는 private file에서 stdin으로만 전달했다. ping은 기존 private control RPC를 사용했으며 Python broker의 TLS origin 대조와 서명 멤버십 경로를 그대로 거쳤다.

| 최종 프로필 | live 제품 검사 | 실제 relay snapshot | 재시작 후 키·멤버십·왕복 | 정리 |
|---|---|---|---|---|
| debug | 1개 통과, 15.200초 | 6/6 relay | 통과 | 소유 PID 0, relay listener 닫힘 |
| release | 1개 통과, 14.526초 | 6/6 relay | 통과 | 소유 PID 0, relay listener 닫힘 |

두 실행 모두 Python source SHA가 실행 전후 같았다. 모든 왕복을 임의의 SDK endpoint로 대체하지 않고 실제 제품 daemon과 sidecar로 수행했다. 초기 `relay_online=false`를 실패 판정이나 성공 증거로 사용하지 않았다. 이는 준비 단계 snapshot이며 실제 본문 왕복과 선택 경로를 검사했다.

## 재빌드·기본 탐색 증거

| binary | 수정 전 SHA-256 | 최종 SHA-256 |
|---|---|---|
| debug | `35a4af3f5b298fa7ecb65bdc2eba7511af77c3350056f0d27ee24a4d4363242a` | `74a4b6825f27aff929b12b8a7819a3eb07e52798066eca4acd8c376782ccbc20` |
| release | `c963e9d4e4ffda47dead354d7d66e2f71fea037932b51846422bdbacb5b39a7d` | `f17f03fafcdf3a31e374d6cbc0ccbbbd8000ba6a7eba5d9b44605e742c409aed` |

debug 기본 프로필과 최적화된 release를 따로 재빌드·검사했다. 새 private XSM에서 `XSM_NET_BINARY` 없이 탐색하면 최종 repository release binary를 선택함도 확인했다. 실제 사용자 프로필의 설치 binary를 교체하거나 배포하지 않았다. live 강제 경로 검사에서는 기존 `XSM_NET_BINARY` 기능으로 각 재빌드 profile의 private 복사본과 sandbox wrapper를 지정했다.

`Cargo.toml`, `Cargo.lock`, 기존 `tests/numeric.rs`의 SHA는 수정 전후 동일하다. 현재 `iroh = 1.4.1` 고정과 `serde_json`의 `float_roundtrip` feature를 보존했으며 numeric 회귀 검사도 양쪽 프로필에서 통과했다.

## 증거와 범위

- [최종 제품 결과와 SHA manifest](physical-core-selfhost-20261029-product-results.json)
- [최초 SDK-only 결과](physical-core-selfhost-20261029-results.json): 그 파일의 product blocked 판정은 수정 전 `35a4...` binary에 대한 역사적 결과다. 최종 제품 결과와 혼합하지 않는다.
- [공식 source provenance](physical-core-selfhost-20261029-provenance.json)
- 새 Rust 검사: `native/xsm-net/tests/relay_url_policy.rs`
- 새 제품 검사: `tests/test_network_selfhost.py`, 명시한 공식 relay binary가 있을 때만 실행하며 자동 설치·다운로드하지 않는다.
- private raw: `/private/tmp/xsm-selfrelay-4qh_rrfo/raw/` — 원실패, 중간 실패, 최종 debug/release, 공식 relay stderr, SHA 대조. root/raw는 0700, 개별 raw는 0600이다.

남은 범위는 두 물리 머신의 자체 relay 경유, 공인 HTTPS 자체 relay 운영, 서로 다른 NAT·UDP 차단·프록시 환경 및 actual agent workflow다. 이번 bounded local 제품 self-host 통과를 이 환경들의 성공이나 ADR-0021 전체 완료로 확대하지 않는다. 사용자 프로필·계정·기존 키·전역 설정·다른 담당 core source·plan·ledger는 변경하지 않았으며 commit/push도 하지 않았다.
