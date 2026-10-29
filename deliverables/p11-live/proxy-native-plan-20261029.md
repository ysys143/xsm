# P11 CONNECT proxy 제한 셀: 실행 전 계획

UTC 2026-10-28T23:17:39.844328+00:00. 기존 P11 비교 범위의 자기완결 controlled fixture이며 D12 backend 선택이나 실제 사용자 팀 승인으로 해석하지 않는다.

Local `/private/tmp/p11-C-proxy-rxp7xnqr`, peer `/private/tmp/p11-C-proxy-5y3nciws`만 사용한다. engine 0.12.10의 SHA `6ac4bb4837469867edc2dba3cbbd6e4dd9fb18ad0389db69ff6ef21683317a44`를 고정한다. HOME/state/명시 IPC와 binary는 각 tmp에 한정한다.

각 머신의 owned stdlib HTTP CONNECT proxy는 127.0.0.1의 임시 port만 bind한다. 승인된 기존 Reason relay/list 및 iroh discovery host:443만 전달한다. TLS payload는 해독/로그하지 않고 CONNECT 목적지·방향별 byte/hash만 기록한다. MITM/인증서 검증 해제는 없다.

먼저 kernel profile에서 UDP와 proxy 이외 TCP를 실제 차단하고 proxy TCP 연결과 curl HTTPS CONNECT/TLS certificate verification을 확인한다. 양쪽 모두 성공한 뒤만 engine을 시작한다. profile은 각 own engine daemon Popen(정상 team restart 포함)에만, HTTP_PROXY/HTTPS_PROXY도 engine env에만 적용한다. SSH/native model에는 적용하지 않는다.

두 controlled endpoint만 create/join/register하고 capability는 메모리·기존 strict-hostkey SSH stdin·명시 IPC로만 보낸다. request body는 engine inbox/send로만 전달하며 SSH native trigger는 phase/hash만 보낸다. 기존 공개 수학 marker의 실제 구독 Codex first 1회만 허용한다. 동일 ID의 실제 답/SHA·native PID/CID hash·link·engine-phase CONNECT bytes가 있어야 proxy native 성공이다. env/relay_connected만으로 성공하지 않는다.

예상 network-egress deny 외 파일/IPC/login/OS/sandbox_apply 실패는 우회하지 않고 중단한다. 준비·전송 실패도 보존하고 모델 자동 재호출은 없다. 새 service/deps/binary download·자체 relay·다른 NAT·SSH 없는 onboarding·기업 인증 proxy·전역 proxy/firewall/계정/사용자 팀 변경은 없다. 정상 기존 서비스와 구독 runtime만 사용한다. 전체 20분 한도. 자기 engine/model/control/proxy를 정리하고 raw는 private tmp, 공개물은 proxy-native-*에만 둔다.

## 준비 문법 오류 보존 뒤 경로

최초 profile은 host 표현 제한으로 exit65였고 network/engine/model 전이었다. raw profile/실패/코드는 이전 tmp 및 preparation-failure JSON에 보존했다. 허용 범위를 넓히지 않고 sandbox가 요구하는 localhost 표기로 같은 proxy port만 예외로 삼는다. 새 local `/private/tmp/p11-C-proxy2-fu7ax6tg`, peer `/private/tmp/p11-C-proxy2-wmxd355_`에서 kernel/TLS preflight를 먼저 확인한다.
