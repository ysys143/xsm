# SSH 전용 조건의 현재 서버 프로토콜 실측

두 물리 Mac의 기존 관리자 SSH로 현재 동결 `xsm.remote.serve(peer_literal, {"op":"ping"})`를 실행해 양방향 성공했다. 같은 소유 프로세스에서 UDP 전체·TCP 443 송신을 차단해도 SSH TCP 22와 서버 ping은 성공했다. 새 B 제품은 정상 가입·ping 뒤 같은 Book 엔진 제약에서 ping이 실패했다. 새 모델 호출은 0회다.

## 실행 조건과 범위

Book은 `Jaesolui-MacBookPro.local`, Mini는 `Jaesolui-Macmini.local`이며 양쪽 `/usr/bin/python3`는 3.9.6이다. 기존 무암호 SSH를 `BatchMode=yes`, `StrictHostKeyChecking=yes`, `UpdateHostKeys=no`, `ControlMaster=no`로 사용했다. 각 새 privateRoot의 SSH state에는 유효한 `remotes` pairing 행만 준비했다. 현재 서버 프로토콜을 기존 관리자 shell에서 실행한 표본이다. 전용 xsm key 생성·forced-command 설치·authorized_keys 변경이나 `remote.call`의 전용 키 경로를 실행하지 않았다. peer literal은 trusted 관리자 명령의 인자이며 key의 forced-command 결속을 입증하지 않는다.

privateRoot는 양쪽 모두 `/private/tmp/ssh-only-gc1ns9ed`다. source 53개와 같은 release Rust binary를 복사했고 양쪽 SHA를 대조했다. 설치된 사용자 런타임이나 실제 profile을 바꾸지 않았다. pair 설정 외에 프로토콜이 만든 policy cache·trace·빈 state 디렉터리는 privateRoot 안에만 남았다. 새 B membership은 별도 `p2p-state`에 만들었다.

## 커널 대조와 실제 왕복

```scheme
(version 1)
(allow default)
(deny network-outbound (remote udp "*:*"))
(deny network-outbound (remote tcp "*:443"))
```

| 조건 | 무제한 대조, 두 Mac | 제한 대조, 두 Mac |
|---|---|---|
| 소유 loopback UDP IPv4 송수신 | 실제 수신 성공 | errno 1로 거절 |
| 소유 loopback UDP IPv6 송수신 | 실제 수신 성공 | errno 1로 거절 |
| 상대 Mac Tailscale 주소의 TCP 22 | 연결 성공 | 연결 성공 |
| 공개 relay IPv4 `5.223.65.62:443` | 연결 성공 | errno 1로 거절 |

relay는 실제 DNS로 확인한 `aps1-1.relay.n0.iroh.link`다. 제한 probe 프로세스는 같은 PID에서 SSH client로 exec했다. Book의 probe/SSH PID는 40855, Mini의 probe/SSH PID는 83760이다. Mini 측 실행을 기다린 Book의 외부 control SSH PID와 혼동하지 않았다.

| 관측 | 결과 | 실행 경계 포함 시간 |
|---|---|---:|
| 제한 Book → Mini SSH 서버 ping | `ok=true`, Mini hostname | 0.401초 |
| 제한 Mini → Book SSH 서버 ping | `ok=true`, Book hostname | 1.066초 |
| 새 B 정상 membership 가입 | 실제 두 노드 활성 | 0.435초 |
| 가입 뒤 Book → Mini 첫 명시적 P2P ping | 성공 | 0.177초 |
| Book 엔진 제한 후 P2P ping, 1회 | `operation-failed` | 30.092초 |
| 같은 조건 Book → Mini SSH 서버 ping, 1회 | 성공 | 0.427초 |

Book의 제한 socket probe PID 41076과 제품 status의 실제 engine PID가 같았다. 같은 PID가 Rust engine으로 exec됐으며 같은 기기 endpoint ID와 membership network ID가 유지됐다. P2P는 private control RPC를 통해 실제 엔진에 요청했고 응답 불가를 관측했다. 단순히 실행하지 않은 경로를 지원 불가로 적지 않았다. 무제한과 제한의 직접 원결과·시간·프로필·PID는 [결과 JSON](results.json)에 있다.

이 profile은 해당 client/engine의 송신만 제한한다. SSH는 기존 Tailscale 주소를 쓰므로 Tailscale daemon과 실제 underlay는 sandbox 밖이다. TCP 22 외의 모든 TCP를 차단한 것도 아니다. 따라서 평가한 xsm 경로에 대한 own-process SSH-only 조건이며, 물리 네트워크 전체가 SSH만 허용한다고 주장하지 않는다. P2P 정상 시 선택 경로는 별도 캡처하지 않았으므로 광고된 direct/relay 후보를 실제 선택 경로로 해석하지 않았다.

## A21-03 비교 입력과 이전 native 근거

새 B의 준비는 기존 빌드 복사, 두 private 서비스 설정·기동, init/invite/join 각 1회였다. 초기 서비스 기동 2회와 membership API 3회, 합계 5개의 제품 API 단계다. 프로세스 제한 전환을 위한 자기 Book 서비스 재시작은 별도다. 실행 중 사용자 prompt 개입은 0회였고 기존 SSH·Tailscale 인증은 전제였다. 최초 설치/build나 최초 로그인에 드는 개입은 측정하지 않았다. 초대 secret은 memory/SSH stdin과 private 제품 초대 파일에만 있었으며 공개 보고서에는 없다. SSH는 B의 준비·관측용이고, B ping 본문을 SSH로 중계하지 않았다. 이 평가 helper의 SSH 사용을 새 B 제품의 필수 의존성으로 해석하지 않는다.

기존 [P11 A/B/D native 동일 수학 과제](../../p11-live/native-carrier-roundtrip-20261029.md)와 [P11 C native 동일 과제](../../p11-live/C-native-roundtrip-20261029.md)는 별도 원자료로 보존했고 SHA를 [source manifest](source-manifest.json)에 연결했다. P11 B는 private TCP 비교체로, 새 iroh 제품 B와 다르다. 당시 실제 CLI는 Codex 0.163.0이며 새 ephemeral conversation을 썼다.

현재 제품 B의 native 근거는 [두 물리 Mac의 Codex 0.164.0 동일 CID 재개](../native-journey-20261029T060853Z-fresh164-v2/report.md)와 그 source manifest에 연결했다. 같은 세 요청·회신의 ACK와 원문 회복은 그 표본의 실행 증거이고, 이번 측정에서 모델을 다시 실행하지 않았다. 해당 native 표본의 준비·최초 답변 시간은 재측정하지 않았으며 이번 0.177초는 LLM 최초 답변 시간이 아니다. 연결한 native 표본은 그 당시 동결 코드와 이전 Rust 빌드에 해당하며 이번 현재 빌드에서 native 업무를 다시 실행한 것은 아니다. 버전·하네스·측정 경계가 달라 성능 순위를 매기지 않는다. 실제 혼합 Claude/Codex의 미완 표본도 성공 표본으로 합치지 않았다.

A21-01의 두 물리 Mac·현재 SSH 서버 프로토콜·소유 프로세스 제한 조건을 관측했다. A21-03의 비교 갱신에 필요한 제한된 준비·개입·프로토콜 응답 자료이며, 새 B 전체 초기 설치/native 업무를 다시 측정한 결과나 전체 ADR 완료 판정이 아니다. 비교 문서의 기존 본문은 수정하지 않았다.

## 보존과 정리

열거한 authorized_keys·SSH config·known_hosts·기본 key 파일의 inode/size/mtime/mode는 두 호스트 모두 전후 같았다. evaluator가 private key 값이나 authorized_keys 내용을 열지 않았다. 서비스 3개 실행분 중 최초 Book은 제한 전환 전 정상 stop했고, 마지막 Book PID 41075/engine 41076과 Mini PID 83816/engine 83817도 정상 stop했다. 마지막 control socket·기록 PID 잔여는 0이다. 원본 state/key와 raw 증거는 양쪽 privateRoot에 그대로 보존했다. 다른 서비스·사용자 profile·전역 SSH·방화벽·relay·proxy 설정은 바꾸지 않았다.
