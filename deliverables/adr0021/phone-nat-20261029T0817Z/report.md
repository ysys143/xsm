# 서로 다른 NAT의 실제 Mac·Android P2P 왕복

실제 S26 Ultra와 MacBook의 IPv4 공인 IP가 서로 다른 구간에서 제품 서비스의 양방향 ping이 성공했다. 각 요청·응답의 본문 SHA와 Rust TLS origin을 대조했고 두 응답 모두 공개 HTTPS relay를 선택했다. 실제 모델 호출은 0회이며 실제 agent 업무 왕복으로 주장하지 않는다.

## 조건과 결과

초기 가입과 baseline ping은 같은 NAT의 Wi-Fi 표본이다. 이를 다른 NAT 가입 성공으로 세지 않았다. 첫 모바일 전환 관측 뒤 실행 시점에 같은 IP로 돌아온 사실을 확인해 결과를 분리했다. 두 번째 전환 후 실제 IPv4가 서로 다른 것을 ping 직전·직후에 확인한 구간만 이번 성공으로 판정했다. native reflexive IPv4도 휴대폰의 외부 조회 값과 일치했다. 원 IP는 private raw에 보존하고 결과 JSON에는 해시만 기록했다.

| 방향 | 요청·응답 SHA | TLS origin | 실제 경로 |
|---|---|---|---|
| Mac → 휴대폰 | 상대 native 이벤트와 일치 | 상대 기기키 일치 | 공개 relay |
| 휴대폰 → Mac | 상대 native 이벤트와 일치 | 상대 기기키 일치 | 공개 relay |

관측 relay는 `https://aps1-1.relay.n0.iroh.link./`다. Mac의 소유 엔진에는 UDP 전체 및 TCP22/8022 outbound deny를 적용했다. 같은 profile의 IPv4·IPv6 UDP와 휴대폰 SSH 연결은 실제 errno1이었고, 제한 없는 대조에서는 성공했다. 전역 방화벽·다른 세션·Tailscale 설정을 바꾸지 않았다.

Tailscale과 SSH는 파일 준비·명령 기동·관측에 사용했다. 업무 data plane은 실제 Rust response의 공개 relay였으며 Tailscale 주소나 SSH가 선택된 경로가 아니다. 두 기기의 Tailscale 앱을 끄거나 제거한 시험이라고 확대하지 않는다.

## 주소 전환과 신원 유지

Wi-Fi baseline부터 모바일 왕복까지 두 서비스·엔진 PID, endpoint key와 network ID가 같았다. 휴대폰 reflexive IPv4는 변경 후 값으로 갱신됐다. membership은 양쪽 active였고 재가입·키 교체·원 상태 보정을 하지 않았다. 이는 실행 중 주소 변경과 기존 기기 신원 유지의 근거이며 agent CID의 네트워크 이동 시험은 아니다.

Android 엔진은 같은 고정 Cargo.lock과 제품 소스의 실제 native target이다. Mac과 Android 바이너리 SHA는 별도로 기록했다. 임시 Termux 도구 체인을 사용했고 전역 Rust 패키지는 설치하지 않았다. Python 및 의존성 설치는 별도 준비 변경이다. ELF·빌드 출처는 `/private/tmp/xsm-phone-cross-52bfe12o/raw/phone-android-artifact-provenance.json`에 보존했다.

인증서 검증 해제·MITM·새 계정 로그인은 없었다. controller는 private key 값을 읽거나 복사하지 않았다. 초대는 private 파일을 SSH stdin으로 전달했으며 모델 context·일반 로그에 비밀을 출력하지 않았다.

## 분석 오류와 원본 보존

Sidecar.request 반환은 transport가 없는 정규화 결과여서 최초 분석은 path=None assertion으로 실패했다. 트래픽을 다시 보내거나 원 이벤트를 바꾸지 않았다. 같은 응답 SHA와 origin의 실제 native response 이벤트에 있는 transport로 분석을 바로잡았다. 성공 근거는 이 원 이벤트다. 초기 같은 NAT 표본도 별도 파일로 보존했다.

## 종료와 자료

두 소유 서비스는 공개 stop exit0으로 끝났고 기록된 소유 PID·control socket 잔여는 0이다. 사용자 SSH 서버와 Tailscale은 유지했다. 사용자 세션에 보낸 신호는 0이며 원 state/key와 raw 이벤트는 private generation에 보존했다. 시험이 끝났으므로 휴대폰 Wi-Fi를 다시 켜도 된다고 알렸다.

- [결과·소스 SHA·정리 증거](results.json)
- [controller](control.py), [수동 관측 observer](observer.py), [node helper](node.py), [분석·보존 코드](archive.py)
- private raw: `/private/tmp/adr21-phone-state-ap7vms90/`
- Mac: `/private/tmp/xsm-phone-mac-uwvoh_vm/`
- Phone: `/data/data/com.termux/files/usr/tmp/xsm-adr21-k4pe34iu/`

초기 가입은 같은 NAT에서 했다. 이번 다른 NAT 구간은 기존 membership의 왕복과 주소 전환이며, 다른 NAT에서 새 기기의 최초 가입 성공으로 확대하지 않는다. ADR21 전체 완료·자동 wake·실제 모델 업무 성공의 근거도 아니다.
