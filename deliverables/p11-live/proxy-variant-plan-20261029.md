# CONNECT proxy explicit-allow variant: 실행 전 계획

UTC 2026-10-28T23:31:13.867943+00:00. 원 require-not 실패와 코드는 변경하지 않는다. 코디네이터의 proxy-profile-preflight.json에서 관측된 explicit-allow 표현을 새 owned-test 조건으로 사용한다. D12 채택·실제 사용자 팀·전역 권한 승인으로 해석하지 않는다.

Local `/private/tmp/p11-C-proxyvar-2_vbmwuu`, peer `/private/tmp/p11-C-proxyvar-2y_s3rzs`. 각 loopback stdlib CONNECT proxy의 정확한 port만 allow하고 나머지 TCP/UDP를 deny하는 profile을 engine daemon에만 적용한다. HTTP_PROXY/HTTPS_PROXY도 engine env에만 설정한다. SSH/native Codex는 밖에 둔다. 기본 C0.12.10 SHA `6ac4bb4837469867edc2dba3cbbd6e4dd9fb18ad0389db69ff6ef21683317a44`만 사용한다.

먼저 양쪽 kernel에서 직접 UDP·외부 TCP·다른 loopback TCP errno1 및 무수신, 정확한 proxy port 연결, 인증서 검증을 유지한 HTTPS CONNECT TLS tunnel을 확인한다. 둘 다 통과해야 engine/team/native를 시작한다. API/UI/파일/로그인/sandbox_apply 권한 실패는 우회하지 않고 중단한다. 예상 network-egress deny만 의도 조건이다. TLS MITM/검증해제·직접 egress 허용·프로필/전역 firewall 변경은 없다.

두 controlled endpoint만 private HOME/state/IPC로 create/join/register한다. ticket은 Python memory→기존 strict-hostkey SSH stdin→private IPC로만 전달한다. 공개 수학 marker 동일, 실제 subscribed peer Codex 최대1회, 자동 모델 재시도0. 본문은 engine/proxy로 전달하고 SSH trigger는 phase/hash만 보낸다. CONNECT 목적지·bytes/hash와 실제 request/reply SHA/상관ID·native PID/CID hash·link readback이 있어야 proxy native 성공으로 센다. env/relay_connected만으로 성공하지 않는다.

정상 기존 Reason/iroh 서비스와 구독 runtime만 사용한다. 자체 relay/다른 NAT/기업 인증 proxy/SSH 없는 onboarding/P12/D12/전역 네트워크 성공으로 확대하지 않는다. 원 실패도 보존하고 자기 engine/native/proxy/control만 종료하며 PID 잔여0을 확인한다. 20분 한도. raw는 private tmp, 공개물은 proxy-variant-* 코드/요약/manifest다.
