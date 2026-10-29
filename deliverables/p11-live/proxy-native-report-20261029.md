# P11 HTTPS-proxy 제한 셀: local preflight 실패로 중단

**proxy 경유 native 성공은 미확보다.** owned-process 제한 profile에서 직접 UDP/TCP는 차단됐지만, 허용돼야 할 loopback proxy 접속도 실패했다. CONNECT·TLS tunnel이 성립하지 않아 engine 및 실제 Codex는 **0회**다. 예상 범위 밖 거부를 우회하거나 profile을 추가 완화하지 않고 종료했다. 이는 engine의 HTTP_PROXY 지원/미지원 판정이나 제품 결함 판정이 아니다.

[요약/원 계수](proxy-native-summary-20261029.json) · [최초 문법 실패](proxy-native-preparation-failure-20261029.json) · [실행 계획](proxy-native-plan-20261029.md) · [hash/경로 manifest](proxy-native-manifest-20261029.json)

## 준비와 실제 kernel 관측

local `Jaesolui-MacBookPro.local`, peer는 기존 strict-hostkey SSH로 확인한 `Jaesolui-Macmini.local`만 대상으로 삼았다. 두 controlled node의 고유 tmp를 준비했고, stdlib proxy는 local `127.0.0.1` 임시 port에만 bind했다. 승인된 기존 Reason relay/list·iroh discovery host의 443 CONNECT만 허용하도록 구성했다. TLS MITM·인증서 검증 해제·전역 proxy/firewall·새 서비스/VM/dependency는 없다.

| 단계 | 실제 결과 | 성공으로 세지 않은 것 |
|---|---|---|
| 최초 profile | sandbox-exec exit **65**: `host must be * or localhost in network address`; `127.0.0.1:port` 필터 표현 거부 | child 자체가 실행되지 않아 network deny 성공 아님 |
| 같은 의도의 localhost 표현 | profile이 Python child를 실행했고 직접 UDP/TCP 시도는 각각 **PermissionError errno 1**; datagram·TCP accept 없음 | proxy 예외까지 검증됐다는 뜻 아님 |
| 허용돼야 할 proxy TCP child | exit **1**, stdout 없음, stderr의 permission/sandbox_apply 표시 true | loopback proxy 허용 실패. 정확한 stack/origin은 원 stderr가 아닌 hash/표시만 남아 있어 확정하지 않음 |
| 같은 profile의 실제 HTTPS curl | exit **7**, CONNECT `000`, HTTP `000`; `Failed to connect to 127.0.0.1 port …` | TLS tunnel 미성립. verify 결과 `0`만으로 TLS 검증 성공이라 읽지 않음 |
| CONNECT proxy 기록 | **0건 / tunnel bytes 0** | env 설정·proxy listener 존재만으로 사용 성공 아님 |
| peer preflight / engine / native model | local 전제 실패로 **미실행 / 0 / 0** | 두 머신 조건·상관 reply/SHA·native PID/CID·link 성공 아님 |

첫 실패의 profile/실행 코드는 첫 tmp에 보존했다. 문법 표현만 sandbox가 요구하는 localhost로 수정했고 외부 TCP/UDP 예외를 추가하지 않았다. 두 번째 준비 조건에서도 proxy 접속이 실패했으므로 더 완화하거나 OS 권한 설정을 바꾸지 않았다. native 자동 반복은 0이다.

## 제한 profile과 검증 한계

proxy port를 제외한 TCP와 직접 UDP를 막기 위해 준비한 두 번째 profile은 다음 구조다. **이 profile은 작동하는 proxy 허용 예제로 제시하는 것이 아니다.**

```text
(version 1)
(allow default)
(deny network-outbound (remote udp "*:*"))
(deny network-outbound
  (require-all (remote tcp "*:*")
               (require-not (remote tcp "localhost:<owned-proxy-port>"))))
```

의도한 loopback 예외가 실제 허용으로 검증되지 않았다는 것이 준비 실패의 경계다. 왜 그 예외가 통하지 않았는지에 대한 원인은 확정하지 않았다. Python proxy-connect child의 stderr는 SHA와 permission/sandbox_apply 표시만 저장했고 원 stack text는 보존되지 않았다는 계측 한계도 남긴다. TLS curl의 원 stderr/stdout은 private tmp에 있다. 이 한계를 메우기 위한 새 실행은 하지 않았다.

HTTPS preflight는 curlrc를 무시하고 HTTPS만 허용했으며 기본 인증서 검증을 유지했다. CONNECT가 성립하지 않아 실제 certificate handshake 증거는 없다. HTTP_PROXY/HTTPS_PROXY는 시작되지 않은 engine의 private env로만 설정하도록 준비했으며 SSH/native CLI에 fixture proxy를 주입하지 않았다. 이 env 계획을 실제 engine/proxy 전달 성공으로 올리지 않는다.

## 왜 / owner / 재개 조건

- **왜 미완인가:** local의 proxy 허용·TLS tunnel preflight가 실패해 두 머신 engine/native 단계의 필수 전제가 충족되지 않았다. 기존 UDP-only 성공이나 일반 C 성공으로 이 셀을 채우지 않는다.
- **owner:** P11 평가 fixture의 process network-profile 준비 담당. 제품 xsm source나 Reason engine proxy capability가 확인된 결함이라고 배정하지 않는다.
- **재개 조건:** 별도로 검증된 owned-process profile이 직접 egress를 막으면서 loopback CONNECT proxy를 실제 허용하고, 양쪽 kernel/TLS preflight가 통과해야 한다. 현재 실행에서는 추가 profile·source 수정·모델 재시도를 하지 않았다.

SSH 없는 onboarding·기업 인증 proxy·자체 relay·다른 NAT·전역 네트워크 firewall로 범위를 확대하지 않았다. 기존 비교 범위의 일시 fixture이며 실제 사용자 Reason 팀·계정 변경이나 D12 backend 선택의 근거가 아니다. D12/UI 미응답과 전체 goal 미완 상태는 그대로다.

## raw 보존과 정리

| 단계 | local | peer |
|---|---|---|
| 문법 실패 | `/private/tmp/p11-C-proxy-rxp7xnqr` | `/private/tmp/p11-C-proxy-5y3nciws` |
| 허용 경로 preflight 실패 | `/private/tmp/p11-C-proxy2-fu7ax6tg` | `/private/tmp/p11-C-proxy2-wmxd355_` |

원 결과·preflight·profile·실행 코드·proxy snapshot·TLS stderr를 local tmp에 보존했다. peer는 고유 빈 준비 root만 만들었고 listener/engine/native를 시작하지 않았다. engine 0.12.10 SHA `6ac4bb4837469867edc2dba3cbbd6e4dd9fb18ad0389db69ff6ef21683317a44`를 확인한 local 사본은 실행 없이 정리했다. 기존 설치 binary는 유지했다. private team/capability/key는 생성되지 않았다.

두 local proxy는 모두 종료됐고 마지막 owned proxy의 stop 뒤 connect는 **61(refused)**였다. 양쪽 준비 root의 잔여 own process·engine copy·state/HOME는 없다. 기존 사용자 세션/서비스를 종료하지 않았고 auth 값을 조회·복사하지 않았다. 제품 1697 고정 source와 기존 UDP/기본 C 증거는 변경하지 않았다.

공개물은 `proxy-native-*` 코드·요약·hash/경로뿐이며 raw/state는 고유 private tmp에 둔다. 실패/미실행을 성공이나 범위 생략 승인으로 바꾸지 않고 이 표본으로 종결했다.
