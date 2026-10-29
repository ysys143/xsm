# P11 C: engine별 UDP outbound 차단 아래 실제 relay native 왕복

두 실제 머신에서 UDP outbound deny를 각 own engine daemon에 유지한 채 **실제 peer Codex 1회·상관 reply/SHA 확인·양쪽 `link=relay` readback**을 확보했다. native 왕복은 **5725.957 ms**, 그중 native CLI 실행은 **5200.966 ms**였다. 이 결과는 해당 controlled-process 제한 셀의 증거다. 전역 firewall·다른 NAT·자체 relay·P12 제품 통합이나 D12 선택의 완료가 아니다.

- [결과 요약](udp-blocked-results-20261029.json) · [실제 engine/native readback](udp-blocked-native-readback-20261029.json)
- [양쪽 kernel preflight](udp-blocked-preflight-results-20261029.json) · [실행 전 계획과 준비 단계 보완](udp-blocked-plan-20261029.md)
- [hash/경로 manifest](udp-blocked-manifest-20261029.json)

## 제한과 실제 관측

local `Jaesolui-MacBookPro.local`, peer `Jaesolui-Macmini.local`(`jaesol-macmini`)에 다음 profile을 **private engine daemon Popen에만** 적용했다. create/join의 정상 daemon 재시작 뒤에도 같은 profile을 적용했다. SSH control·metadata CLI·native Codex는 이 network profile 밖에서 실행했다.

```text
(version 1) (allow default) (deny network-outbound (remote udp "*:*"))
```

| 확인 | local | peer |
|---|---|---|
| 정상 child loopback UDP | 17 bytes 전송·수신 | 17 bytes 전송·수신 |
| 같은 child의 UDP deny | errno 1, datagram 무수신 | errno 1, datagram 무수신 |
| 같은 profile의 TCP echo | child와 parent 모두 성공 확인 | child와 parent 모두 성공 확인 |
| 실제 native 왕복 뒤 상대 link | `relay` | `relay` |
| 같은 시점 member 수 / relay_connected | 2 / true | 2 / true |

preflight는 실제 kernel 제한 관측이다. engine 로그에는 UDP send EPERM 원문에 해당하는 분류가 관측되지 않았다(0건). 이를 engine의 실제 EPERM trace가 있다고 바꾸지 않는다. 제한 근거는 양쪽 preflight와 각 daemon의 정확한 `sandbox-exec -p` 실행 인자다. 그 조건 아래 요청·답을 실제 전달한 뒤 양쪽 상대 link가 `relay`였다. `relay_connected=true`만으로 통과시키지 않았다. 선택 relay URL·wire IP/port는 readback에 없어 unknown이다.

비 UDP 파일/IPC/로그인/OS 실행 권한 실패 및 sandbox_apply 거부를 우회하지 않았다. 명시 UDP send 계열의 거부만 의도한 조건으로 분류하도록 한정했고 미분류 permission log는 0건이었다. deny를 제거한 재실행 결과는 없다.

## 실제 과제와 경로

engine은 기존 고정 **0.12.10**, SHA-256 `6ac4bb4837469867edc2dba3cbbd6e4dd9fb18ad0389db69ff6ef21683317a44` 사본만 사용했다. signature 검증은 주장하지 않는다. 각 고유 tmp에 HOME/state/IPC/XDG·engine 사본을 가뒀고 두 controlled endpoint와 pull client만 등록했다. 실제 Reason CLI·계정·사용자 팀·전역 membership·프로필/MCP·제품코드·backend 기본값은 변경하지 않았다.

local adapter → local engine send → Reason network → peer engine inbox → 실제 peer Codex → peer engine의 reply_to send → local engine inbox 경로다. join capability는 메모리→기존 strict-hostkey SSH stdin→private IPC로만 전달했다. native 실행 trigger의 SSH 인자는 phase와 예상 body SHA뿐이며 요청/답 본문을 SSH로 우회 중계하지 않았다.

과제는 기존 C와 같은 공개 marker `P11-QA-40c1afc34bbd43c4`의 `2+2=5` 검토다. 실제 답은 같은 marker/phase와 `claim_valid=false`, `corrected_sum=4`였다. schema는 타입만 제한하며 정답을 강제하지 않았다. 실제 `/opt/homebrew/bin/codex`는 **codex-cli 0.163.0**, native exit 0·tool event 0이었다. 기존 ChatGPT 구독 profile만 사용하고 auth 값을 조회·복사하지 않았다. 이전 C와 같은 ephemeral/read-only·user config/rules 무시·hooks/plugins/apps/shell 비활성화 invocation이며 native resume 표본은 아니다.

native conversation·요청 engine ID·reply engine ID는 hash로 남겼다. peer가 실제 받은 body SHA, local의 원 요청 SHA, native JSON 답 SHA, local inbox의 답 SHA 및 reply_to가 맞았다. native 실행은 전체 준비 과정에서 **attempt 1 / success 1**, 모델 자동 재호출 0이다. 값은 CLI 기동·구독 추론·carrier/제어 비용을 포함한 단일 표본이며 성능 순위가 아니다.

## 먼저 실패한 준비/전송 기록

| 표본 | 실제 결과 | 모델 호출 | 보존 |
|---|---|---:|---|
| 최초 부트스트랩 | peer 평가 script가 옛 module filename을 참조해 control EOF. peer daemon/team 이전 실패 | 0 | [bootstrap JSON](udp-blocked-bootstrap-20261029.json), 첫 tmp의 실행 코드 |
| 첫 두 engine 전송 | machine roster/link는 relay였으나 peer pull session이 아직 발신 directory에 없어 send 거부 | 0 | [첫 send 실패 JSON](udp-blocked-first-send-failure-20261029.json), 별도 tmp |
| 준비 readback 보완 뒤 native 표본 | 양쪽 실제 who 목록에서 두 controlled session을 확인하고 첫 native 과제 왕복 | 1 | 실제 readback/원시 native 자료·manifest |

첫 send 거부의 보존 SHA는 고정 v0.12.10 `daemon/directory.rs`의 `no session called … (sessions without Reason Network can't receive).` 오류문과 일치했다. 파일명 및 session 준비 확인은 평가 fixture의 보완이다. 실패를 정상으로 덮거나 UDP 제한을 완화하지 않았으며 두 앞선 표본을 native 성공에 합산하지 않았다.

## raw 증거와 정리

| 단계 | local private root | peer private root |
|---|---|---|
| 최초 부트스트랩 | `/private/tmp/p11-C-udp-s3mrn30l` | `/private/tmp/p11-C-udp-tih25w67` |
| 첫 send 거부 | `/private/tmp/p11-C-udp2-sjkpra10` | `/private/tmp/p11-C-udp2-cysgvtr5` |
| native relay 왕복 | `/private/tmp/p11-C-udp3-mnbiv37u` | `/private/tmp/p11-C-udp3-a6yz6nss` |

native 원 출력·입력·결과·실제 실행 코드와 hash 로그는 위 고유 tmp에 있다. peer 비상태 증거 29개는 local 성공 root의 `peer-evidence/`로 SSH 회수해 hash를 대조했다. ticket·private key·raw state는 공개 artifact에 복사하지 않았다.

각 own daemon의 시작 PID/시각·동일 profile과 종료를 기록했다. 성공 표본의 daemon handle은 양쪽 2개씩, native handle은 1개이며 모두 종료됐다. 앞선 실패 단계도 포함해 양쪽 세 root씩의 최종 잔여 own process는 0이다. IPC는 stop 뒤 connect 61, private state/HOME/키·engine 사본은 제거됐다. 초기 peer에 stage만 됐던 binary도 checksum/UID를 확인하고 정리했다. 기존 사용자 서비스는 종료하지 않았다.

이 작업은 기존 전체 P11 비교 범위의 자기완결 일시 fixture와 owned-process 제한 실험이다. 별도의 실제 사용자 팀 가입이나 D12 제품 채택을 추론하지 않는다. 기존 C 보고서·remote-decision/G11 초안·제품 소스는 수정하지 않았다.

재검사는 JSON/manifest와 실제 원시 native 결과를 대조하는 offline 검사다. 새 모델 호출이나 전체 제품 테스트를 실행하지 않았다.
