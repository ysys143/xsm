# ADR-0021 캐리어 결과와 수용 검사 잔여 요구

기존 결과 파일을 읽어 확인했다. 이 보고서를 작성하며 모델 호출이나 캐리어 실험을 반복하지 않았다. 제품 소스와 기존 상태·키·증거는 수정하지 않았다.

## 최신 캐리어 성공

같은 호스트의 실제 Python 제품 서비스 두 개와 Rust 엔진으로 초대·가입·양방향 ping을 수행한 표본이다. 임의 SDK endpoint나 평문 TCP로 P2P를 대체하지 않았다. 실제 모델 세션 및 서로 다른 NAT의 성공은 아니다.

| 조건 | 실제 왕복 | 선택 경로 | origin·양쪽 본문 digest | 시간 |
|---|---:|---|---|---|
| 기본 공개 relay, UDP 주소 발견 포트만 허용 | 2회 | 두 응답 모두 `relay` | 모두 일치 | 0.680초, 0.875초 |
| UDP 전면 차단과 HTTPS CONNECT proxy | 2회 | 두 응답 모두 `relay` | 모두 일치 | 0.853초, 0.700초 |

두 조건 모두 TCP 외부 목적지는 소유 loopback proxy가 제한했다. 기본 공개 relay 4곳과 사용자 추가 허용에 따른 SDK 기본 DoH 주소 3곳만 허용했다. 첫 조건도 proxy를 사용했으므로 proxy 없는 일반 인터넷 대조군은 아니다. UDP 전면 차단은 소유 프로세스에만 적용했고, IPv4·IPv6 loopback 및 공개 relay 목적지의 UDP 소켓 대조에서 모두 `PermissionError`, errno 1을 확인했다.

실제 선택된 relay는 `https://aps1-1.relay.n0.iroh.link./`다. path는 전역 연결 상태가 아니라 각 native response 이벤트의 `transport`에서 가져왔다. 소유 엔진 PID의 실제 TCP 연결과 proxy CONNECT의 출발 포트를 대조했고, relay tunnel 양방향 TLS 바이트가 있었다. 환경변수 설정만으로 proxy 사용을 판정하지 않았다.

- [최종 결과](results-final.json), [간단 재확인](summary-resumed.json)
- [공개 relay 표본](public-relay-final.json), [UDP 차단·proxy 표본](udp-blocked-https-proxy-final.json)
- passive 관측기는 ping의 요청·응답 digest와 native 이벤트를 기록했으며 본문이나 응답을 대체하지 않았다.

## 주소 캐시 수정과 현재 소스 대조

옛 표본에서는 두 서비스 모두 Python 캐시에 Relay가 없었지만 12초 뒤 실제 native 주소에는 Relay가 있었다. [별도 SDK 진단](controls-and-address-diagnostic-v2.json)은 조회가 캐시를 갱신한다는 사실을 명시했으며, 그 뒤 가입·ping을 실행하지 않았다. 이를 제품 성공 표본으로 합치지 않는다. 초기 IP allowlist 문법의 exit 65와 기존 실패 결과도 보존했다. DoH 거절만을 최초 실패의 직접 원인으로 단정하지 않는다.

성공은 수정 뒤 별도로 동결한 Python 52개 파일과 지정 release 바이너리에서 나왔다. [성공 동결 manifest](manifest-fixed.json)와 [원실패 manifest](manifest.json)는 별개다. binary SHA-256은 `c963e9d4e4ffda47dead354d7d66e2f71fea037932b51846422bdbacb5b39a7d`다.

확인 시점의 `xsm/network.py`, `xsm/network_transport.py`, `xsm/receive.py`와 지정 설치 바이너리는 성공 표본의 해시와 같았다. 현재 `Daemon.status()`는 354줄에서 `refresh_address()`를 호출하며, 364줄의 메서드는 369줄에서 실제 `address` IPC를 조회한다. invite는 766줄, synchronize는 957줄에서 갱신한다. `transport.relay_online`은 시작 snapshot이고 현재 경로 판정은 갱신된 주소와 실제 response path에 따른다. 저장소 전체 또는 이후 다른 바이너리까지 같은 검증을 했다는 뜻은 아니다.

## 정리 기록

최종 표본의 서비스 4개는 모두 exit 0, native 엔진 잔여와 control socket 잔여는 0이었다. 사용한 UDP 바인딩 8개는 모두 다시 bind할 수 있었고 proxy도 종료됐다. [중단 시 정리 기록](cleanup-paused.json)에서 기록된 소유 PID 잔여 0과 소유 proxy 포트 8개의 listener 잔여 0을 확인했다. 이번 재개에서는 프로세스나 네트워크를 새로 조회하지 않았다. 상태·키·평가 증거는 보존했다.

## 수용 검사 7개에서 아직 필요한 실제 근거

확정 기준은 [ADR 원문](../../../docs/adr/0021-cross-machine-network-and-membership.md)과 [수용 검사표](../../../docs/plan/reason-inspired-adrs/acceptance.md)의 A21-01부터 A21-07이다. 진행 문서의 오래된 미완 문구보다 개별 후속 실측의 범위와 결과를 우선 대조했다. 아래는 새 검사를 만드는 틀이 아니라 기존 자료에 대한 한 번의 잔여 정리다.

| 번호 | 이미 확보된 근거 | 아직 실제 근거가 없는 요구 |
|---|---|---|
| A21-01 | 두 물리 Mac의 LAN·동일 NAT direct, Tailnet 주소 사용과 LAN 전환. 이번 동일 호스트의 공개 relay·UDP 차단·proxy 왕복. 별도 동일 호스트 자체 relay 제품 왕복. | 서로 다른 NAT의 완료 결과, 두 물리 기기의 UDP 차단·proxy·자체 relay 경유, 현재 제품의 SSH 전용 환경 왕복. 폰 승인·SSH 가능은 준비 근거이고 다른 NAT의 P2P 성공은 아니다. 해당 실측은 main/Hilbert 진행 범위다. |
| A21-02 | 서명 멤버십·격리 반례 검사와 실제 두 Mac의 가입·멤버 조회·키 지속. | 제3자·제명·위조 이름·잘못된 팀·만료/회수·오프라인 재접속의 전체 반례를 두 물리 기기에 결속한 결과표. 가입 응답 유실·전환 실패·이전 소속 보존·복귀 실패, 최초 기기 중단 뒤 다른 활성 기기의 초대·추가·제명, 오프라인 정책 수신·키 교체의 실제 근거. 비최초 기기끼리 ping하는 근거가 초대·제명 근거를 대신하지는 않는다. 계정 로그인을 새로 요구하는 뜻도 아니다. |
| A21-03 | 과거 A/B/C/D 비교와 부분 판정 초안, 새 B 제품의 설치·물리 전송 자료. | 새 B 제품까지 같은 업무·조건으로 묶은 설치 단계·사용자 개입·첫 왕복 비교와 양방향 SSH 불가 조건, 운영·제거 비교의 미완 셀. 옛 초안의 D12 미선택 문구를 현재 backend 미결로 다시 세지 않는다. |
| A21-04 | 실제 두 Mac의 발견·선택 요청과 상대 canonical 원문 보존. 실제 모델 대신 native 파일 시험체를 사용한 제품 통합 검사는 별도 존재. | 다른 home/runtime·동명 후보에서 질문·후속·직접 회신·소비 확인까지 완료한 실제 모델 여정. 기존 native 보고서는 상관 회신·소비 ACK가 없으며 후속 재실행의 완료 보고서는 아직 확인되지 않았다. Newton 담당이다. |
| A21-05 | 실제 서비스·엔진 종료와 listener/UDP 포트 해제, 엔진 종료 뒤 같은 신원 복구, 이번 proxy 정리 기록. | 원격 서비스와 relay를 각각 끊은 동안 실제 로컬 질문·응답이 유지된다는 실측, 제거 뒤 소유 서비스·listener 확인. idle 종료·복구 검사만으로 실제 업무 중 독립성을 종결하지 않는다. |
| A21-06 | 공개 또는 검증된 저장소 매핑만 후보가 되는 격리 검사, 공개·제외·제명·협업 철회·매핑 변경의 제품 통합 검사. | 두 물리 기기에서 가입 전후 공개·제외·비공개 세션·자료/실행 권한의 경계를 대조한 실제 기록과 사람/독립 검토. 비공개 CLI·호스팅 MCP의 관찰 범위 및 검증하지 못한 경계도 명시해야 한다. |
| A21-07 | 실제 엔진의 고정 포트 충돌 대체 검사, 두 Mac의 바인딩과 Tailnet/LAN 경로 전환, 주소 캐시 결함 및 수정 뒤 실제 IPC·relay 왕복. | IPv6를 실제 사용할 수 없는 호스트에서의 실행, 실행 중 주소 변경 뒤 같은 신원·세션을 유지하는 바인딩/재접속 진단 대조. 공인 IPv6 미관측은 IPv6 socket 사용 불가와 다르다. 별도 프로세스의 IPv6 소켓 고장 주입은 실제 IPv6 부재 호스트를 대신하지 않는다. |

수용 종결에는 각 실제 근거와 G11·G12·G13 판정을 함께 대조해야 한다. 이 문서는 게이트 상태를 바꾸지 않는다.

관련 결과: [두 물리 Mac 코어](../physical-core-20261029-report.md), [동일 호스트 자체 relay 제품](../physical-core-selfhost-20261029-report.md), [코어 복구 근거](../core-review-closure.md), [기존 실제 모델 여정의 미완 결과](../native-journey-20261029T053934Z/report.md), [G11 비교 초안](../../../docs/plan/reason-inspired-adrs/gates/G11-remote-comparison-draft.md).

## 별도 요청된 A21-07 첫 시도

위 7개 잔여 정리 뒤, 사용자 추가 요청으로 소유한 비SIP 엔진의 IPv6 소켓 고장 주입을 한 번 시도했다. 라이브러리 컴파일·적재는 확인했지만 소켓 차단 호출은 관측되지 않았고 제품 서비스가 준비 전에 exit 4로 끝났다. 실제 IPv4 bind·가입·ping·포트 대체는 미실행이다. 이 실패를 캐리어 성공이나 실제 IPv6 부재 호스트의 근거로 합치지 않는다. [별도 첫 결과](../carrier-ipv6-fault-20261029T071008Z/report.md)에 소스·바이너리·정리 기록을 보존했다.
