# P11 explicit-allow CONNECT proxy variant

**두 controlled 머신에서 engine 직접 egress를 차단하고 owned loopback CONNECT proxy를 경유한 실제 native 왕복 1회를 확인했다.** 양쪽 kernel/TLS preflight, engine-phase CONNECT bytes, 실제 request/reply SHA·reply_to·native PID/CID, 양쪽 `link=relay`를 함께 대조했다. 원 proxy 준비 실패는 그대로 보존했다. 성공 범위는 이 owned-engine 제한 조건이며 전역 네트워크·기업 인증 proxy·SSH 없는 onboarding·P12/D12 성공이 아니다.

[요약/실제 계수](proxy-variant-summary-20261029.json) · [실행 전 계획](proxy-variant-plan-20261029.md) · [hash/경로 manifest](proxy-variant-manifest-20261029.json) · [읽기 전용 audit](proxy-variant-audit.py)

## 제한과 양쪽 실제 preflight

코디네이터가 실측한 `proxy-profile-preflight.json`의 explicit-allow 표현을 사용했다. profile은 각 **own engine daemon Popen에만** 적용하며 team 생성/가입의 정상 daemon 재시작 뒤에도 유지했다. HTTP_PROXY/HTTPS_PROXY도 engine env에만 설정했다. SSH control·native Codex는 이 network profile 밖이다.

```text
(version 1)(allow default)
(deny network-outbound(remote tcp "*:*") )
(deny network-outbound(remote udp "*:*") )
(allow network-outbound(remote tcp "localhost:<owned-proxy-port>"))
```

| 실제 child 확인 | local | peer |
|---|---|---|
| proxy bind / port | 127.0.0.1:54630 | 127.0.0.1:56868 |
| 직접 UDP / 다른 loopback TCP | 각각 errno 1, 무수신/무접속 | 각각 errno 1, 무수신/무접속 |
| 외부 TCP(reasonmachines.com의 실제 IPv4:443) | errno 1 | errno 1 |
| 정확한 loopback proxy port | 연결 성공 | 연결 성공 |
| 같은 profile의 HTTPS CONNECT/TLS | curl exit 0, CONNECT 200, verify 0, HTTP 200 | 동일 |

TLS preflight는 시스템 curl의 기본 certificate verification을 유지했다. curlrc 무시·HTTPS 한정·인증서 검증 해제 없음이며 proxy는 TLS bytes를 해독하지 않았다. proxy 자체는 stdlib이며 loopback만 listen했다. 실제 child PID/start/stdout/stderr와 profile은 private raw에 보존했다. libproc를 제한 child 안에서 호출하지 않았고 controller ps는 profile 밖에서 실행했다.

## 실제 engine·본문·native 증거

기존 engine **0.12.10**, SHA `6ac4bb4837469867edc2dba3cbbd6e4dd9fb18ad0389db69ff6ef21683317a44` 사본만 사용했다. 각 private HOME/state/IPC에 두 controlled endpoint를 생성·가입하고, 실제 engine who 목록에 두 fixture pull session이 보이는지 확인했다. 실제 Reason CLI·계정·사용자 팀·전역 membership/profile/MCP는 사용/변경하지 않았다. engine 원본 binary와 원 C/UDP 결과는 변경하지 않았다.

요청은 local engine send→network/proxy→peer engine inbox→실제 subscribed Codex stdin으로 전달됐다. 답은 peer engine reply_to send→network/proxy→local engine inbox로 돌아왔다. SSH는 기존 strict-hostkey 제어와 capability 전달에만 사용했다. native 실행 trigger는 phase·body hash뿐이며 수학 본문/답을 SSH로 우회 중계하지 않았다. ticket은 메모리·기존 SSH stdin·명시 private IPC에서만 전달하고 공개에는 hash/상태만 남겼다.

같은 공개 marker `P11-QA-40c1afc34bbd43c4`의 `2+2=5` 검토를 실제 peer Codex **attempt 1 / success 1**로 실행했다. actual CLI는 **codex-cli 0.163.0**, PID **81439**, 기록된 시작 시각 `Thu Oct 29 08:32:58 2026`이다. 실제 CID는 summary의 hash와 private native result/stdout의 thread.started ID로 대응한다. CLI exit 0·tool event 0, 모델 자동 재시도 0이었다. 답은 같은 marker/phase의 `claim_valid=false`, `corrected_sum=4`와 짧은 반례다. schema는 타입만 정하고 정답을 강제하지 않았다.

native input SHA=peer가 받은 body SHA=local 원 요청 SHA, native JSON 답 SHA=local 수신 body SHA, 원 request ID와 reply_to·reply ID가 모두 일치했다. 양쪽 상대 link readback은 **relay**였다. `relay_connected=true`나 env 설정만으로 성공시키지 않았다. native 실제 왕복은 **8840.102 ms**, native CLI는 **8005.028 ms**이며 추론·제어·carrier를 포함하는 단일 표본이다.

## CONNECT 관측과 한계

다음은 native reply 직후, final cleanup 전 snapshot 기준이다. 전체 per-connection 기록·bytes/hash는 private raw에 있고 공개 요약은 집계다.

| 관측 | local proxy | peer proxy |
|---|---:|---:|
| CONNECT 요청(해당 snapshot, preflight 포함) | 2225 | 2299 |
| 양방향 bytes가 있는 engine-phase 허용 tunnel | 45 | 49 |
| 과제 전후 relay tunnel byte 증가: upstream / downstream | 7991 / 49677 | 1592 / 1348 |
| fixture 목적지 allowlist의 CONNECT 거부 | 2179 | 2249 |
| CONNECT 이외 method 거부 | 3 | 3 |

허용 tunnel에는 실제 Reason relay 호스트, signed relay-list, dns.iroh.link가 있다. 과제 전후 relay bytes 증가는 양쪽 모두 양수였다. 이 bytes에는 background/control traffic도 섞여 있으므로 순수 수학 payload의 packet 계측이나 성능 순위로 읽지 않는다. 그러나 직접 UDP/다른 TCP가 제한된 engine에서 상관 reply가 돌아왔고 실제 proxy relay traffic·link readback을 함께 관측했다.

추가 거부도 숨기지 않는다. numeric resolver `1.1.1.1/8.8.8.8/9.9.9.9:443`로 향한 CONNECT는 fixture host allowlist가 HTTP 403으로 거부했고 upstream bytes는 0이었다. CONNECT 이외 요청도 HTTP 405로 거부했다. engine 내부 반복 연결 시도는 위 계수에 포함되며 **모델 재호출과 다르다**. 목적지 허용 집합을 넓혀 재실행하지 않았다. 따라서 임의 DNS 경로나 범용/기업 proxy 호환성을 주장하지 않는다.

proxy는 TLS MITM·헤더/본문/인증서 변경을 하지 않았다. 정상 native TLS를 그대로 tunnel했다. 직접 egress 허용, 전역 proxy/firewall, 계정/키/hostkey 변경, 새 서비스/유료 API/새 binary download는 없었다. 정상 기존 engine 서비스·기존 구독 인증만 사용했고 auth 값을 조회·복사하지 않았다.

## 보존·정리·판정 범위

- local raw: `/private/tmp/p11-C-proxyvar-2_vbmwuu`
- peer raw: `/private/tmp/p11-C-proxyvar-2y_s3rzs`
- peer 비상태 증거 29개는 local `peer-evidence/`로 SSH 회수해 SHA를 대조했다. raw/state·native 출력·CONNECT 기록은 tmp에만 두고 공개물은 요약·코드·hash/경로다.
- daemon handle은 양쪽 2개씩이며 초기 정상 team restart exit 0, 마지막 자기 handle stop -15를 구분했다. native CLI는 exit 0, SSH control은 exit 0이다. IPC와 양쪽 proxy port는 stop 뒤 connect 61(refused)였다.
- private engine key/state/HOME·binary 사본을 정리했고 controller/engine/native/proxy의 기록된 PID·세대를 다시 확인했다. 잔여 known process는 0이다. 기존 사용자 세션/서비스는 중지하지 않았다.

기존 require-not proxy 실패와 UDP/기본 C 증거를 덮지 않았고 제품 1697 source도 수정하지 않았다. 이는 기존 P11 비교 범위의 새 owned-test variant이며 새 backend 선택·실제 사용자 팀 승인·전역 정책 해제로 해석하지 않는다. 원 실패의 미확보 판정도 그대로 유지한다.

## CONNECT 반복과 engine 관측창의 추가 진단

기존 raw만 대조했다. 본문 표의 CONNECT **2225/2299에는 preflight TLS CONNECT가 각각 1건 포함**돼 engine-phase만은 **2224/2298건**이다. 그중 numeric resolver allowlist 거부는 **2179/2249건**, 양방향 bytes가 있는 허용 engine tunnel은 **45/49건**이다. 다음 시각은 UTC 2026-10-28의 기록된 **요청 시작 시각** 기준이다.

| proxy | 첫 engine 요청 시작 | reply 직후 snapshot의 마지막 요청 시작 | 시작 시각 사이 관측폭 |
|---|---|---|---:|
| local | 23:32:29.928 | 23:33:06.796 | 36.869초 |
| peer | 23:32:30.439 | 23:32:51.741 | 21.302초 |

**이 마지막 요청 시각은 측정 종료 시각이 아니다.** snapshot/connection의 종료 timestamp가 raw 형식에 없어 전체 engine 측정창의 정확한 종료·총 길이는 확정할 수 없다. peer cleanup 기록에는 23:33:08.925의 더 늦은 요청도 있다. 따라서 위 길이는 해당 snapshot에서 확인되는 요청 시작 시각의 범위이며 전체 가동 시간/지속 부하로 추정하지 않는다.

numeric resolver 403 거부 반복은 local **36.171초에 2179건**, peer **15.961초에 2249건**이고 해당 목적지로 전달한 upstream bytes는 0이다. 이와 별도로 허용 relay CONNECT는 **41/42건**, 암호화된 누적 upstream/downstream bytes는 local **68144/205340**, peer **56232/213211**이다. 과제 구간 relay bytes 증가도 각각 **7991/49677**, **1592/1348**로 확인된다. 허용 relay traffic과 거부된 resolver 반복을 한 종류의 성공 CONNECT로 합치지 않는다. bytes에는 handshake·background/control이 포함된다.

이 계수는 engine-phase의 연결/재연결성 네트워크 시도이며 실제 native 모델 호출 **1회·모델 자동 재시도 0회**와 별개다. 반복 수가 많다는 반대 증거는 남기되, 내부 호출별 원인·CPU 사용량·영구 busy loop·장기 지속 여부는 측정하지 않아 확정하지 않는다. 새 engine/model/source/프로필 변경·조건 완화 없이 이 읽기 대조로 보고서를 종결했다.
