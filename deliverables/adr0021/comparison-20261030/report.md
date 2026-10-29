# A21-03 최종 비교와 기록 범위 종결

2026-10-30에 기존 원결과에서 설치 전제·실제 시작/가입 단계·추가 사용자 개입·운영/제거를 다시 집계했다. 첫 집계 뒤 사용자 요청으로 기존 C와 동일한 own-process TCP22 deny에서 A·D의 최초 SSH 연결 음성검사를 각각 1회 추가했다. 새 모델·제품 서비스는 실행하지 않았다. 과거 native 15회·cached 회수 5회는 그대로 보존한다. 과거 B 비교체와 새 B 제품은 별도 행이며 결과를 합산하지 않는다. 새 B 최종 결과와 실제 운영 마찰을 반영해 A21-03의 비교 기록을 명시된 전제·관측 범위에서 종결한다. 지원 불가·미실행·미계측 한계는 유지하며 전역 G11/G12/G13 판정을 바꾸지 않는다.


## 최종 소스·회귀·실제 업무 결과

최종 root는 `/private/var/folders/hw/9m3g7fvn4_l3rp2y473km9sm0000gn/T/adr21-closure-final-1cnnq81i`, manifest SHA-256은 `ccc3f22a1d65a33ddc76b0ad1abc4966a65664a6e41777d52b70230cd4fd4011`이다. [최종 회귀 원자료](../legacy-native-recovery-20261030/final-validation/summary.json)와 두 stderr 마지막 결과를 읽었다. Python 3.9는 1936개 OK·skip 0·831.018초, 3.14는 1936개 OK·skip 0·534.329초다. 입력 178개·제품 Python 53개와 당시 작업 트리 일치는 원결과에 결속한다. [실행 보고](../legacy-native-recovery-20261030/final-validation/report.md), [3.9 원 로그](../legacy-native-recovery-20261030/final-validation/py39.stderr), [3.14 원 로그](../legacy-native-recovery-20261030/final-validation/py314.stderr)에 의도된 음성 출력·기존 ResourceWarning도 남아 있다.

같은 ccc3의 [마지막 delta Opus 검토](../legacy-native-recovery-20261030/final-surface-review/review-parsed.json)는 approved·findings 0이다. 공유 `handoff.old_p2p_copy_receipt`, pending_ids read-only notice, take_inbox_claims/poll_replies의 현재 권한 check 유지에 대한 정적 지정 범위 승인이다. 전체 회귀·실제 업무와 증거 종류를 구별한다. 이전 1933/1935개와 각 승인·실패는 당시 소스 이력으로 보존했다.

[Newton 최종 math 원결과](../native-journey-common-math-latest-retry1-20261029T155548Z/results.json)는 passed·17항목 모두 true다. 실제 논리 업무 질문 3개·회신 3개와 준비 handshake 1쌍, 실제 MCP/canonical ACK 총 8건을 확인했다. 원래 `9f11884127764cad`와 다른 원 ID, 재시도한 세 번째 ID·본문이 유지됐다. 재시작 뒤 기존 답 2개는 같은 reply ID로 실제 MCP에서 회수했고 최종 ccc3 코드에서도 보존된 3답을 readback했다. 이 최종 조회는 read-only이며 새 ask가 없다. 구 held bytes는 불변이고 양쪽 소유 cleanup 잔여 0이다.

업무 실행 manifest는 `942a5deca7ccb0ec89cfc92e71fa52495fa6ff92cdb16251125db99728bdf03f`, 최종 회수 manifest는 ccc3다. 업무 중 수신 수정·재접속을 거쳐 원문을 회복한 표본이며 처음부터 끝까지 변경 없는 ccc3에서 무보정 실행한 benchmark로 쓰지 않는다. 실패는 준비 정책 경로 1건, 실제 구 held 수신 차단, relay off/port 0 재시작 후 새 주소 hint 미학습을 분리 보존했다. 복구는 정상 status 주소·인증 ping의 주소 교환과 같은 실제 CID/MCP 재접속으로 했으며 새 human yes·held 사본 delivery·원문 보정·본문 중계는 없다.

## 새 B의 실제 복구 마찰과 actor 재개 집계

| 항목 | 최종 원자료의 횟수·관측 | 비교에 포함하는 비용과 경계 |
|---|---|---|
| 앞선 준비 실패 | [첫 표본](../native-journey-common-math-latest-20261029T154407Z/report.md)의 정책 경로 거절 1건·업무 질문/회신 0·reviewer만 기동 | 정상 retry1 집계와 별도. private root 이동 뒤 정책 이력 검증 실패를 성공으로 덮지 않음 |
| 실제 수신 결함 | [수정 전 retry1 기록](../native-journey-common-math-latest-retry1-20261029T155548Z/report.md)의 admitted/pending 원문 은폐·claims 0 | 원문 수신 대기·분류 코드 수정·검토·재접속을 포함. 최종 8ACK 성공으로 원실패를 삭제하지 않음 |
| Claude CLI | 1회, 같은 실제 CID 유지 | 성공 retry1 표본의 reviewer. 앞선 실패 표본의 별도 reviewer 기동은 이 1회에 합치지 않음 |
| Codex CLI | 5회: 최초 1회·같은 CID resume 4회 | 새 대화는 성공 표본 전체 2개. CLI 시작을 논리 업무 3개나 모델 답 수와 혼동하지 않음 |
| 일반 FIFO 계속 Goal | 6회 | 사용자 yes가 아닌 자동화의 일반 계속 지시이며 actor/작업 진행 마찰에 포함. 본문/답변 중계 0회 |
| 표준 MCP 재접속 | 2회 | native 대화 재생성과 구별. 최초 patched-MCP 관측 1건은 최종 2건 집계의 일부 |
| 네트워크 서비스 시작 | 최초 2회 + 계획 재시작 2회 + stable-port 복구 시작 2회 | 동일 키 서비스 수명·주소 hint 문제 복구 비용을 포함. 모델/actor 재개와 다른 단위 |
| 정상 주소 hint 교환 | 2회 | status의 실제 주소·인증 ping 사용. 수동 peer 파일 보정·새 권한 없음 |
| 가입 | invite 1회·join 1회 | 기존 SSH/구독 인증과 제공 source/binary 전제를 재사용한 operator 준비 |
| 실제 MCP ask | 4회·논리 업무 3개 | 세 번째 업무의 전송 전 거절 1회와 같은 ID/본문 재시도 포함. 실패를 빼고 3회 호출로 쓰지 않음 |
| 최종 정리 | 양쪽 소유 잔여 0 | 원문/held bytes/실패 증거는 보존. 실제 기존 사용자 서비스 제거와 구별 |
| 추가 human yes·본문/답변 중계 | 각각 0회 | operator source 수정·continue/resume·주소 교환이 없었다는 뜻은 아님 |

최종 횟수는 [results.json](../native-journey-common-math-latest-retry1-20261029T155548Z/results.json)의 counts를 따른다. 앞서 launch 파일 4건·관측 파일 2개에서 확인한 requester resume는 같은 CID 재개 4회로 최종 결속됐다. reviewer 일반 계속 1회·MCP 재접속 1건이라는 중간 관측은 최종 6회/2회의 부분 이력이며 두 값을 더하지 않는다. 현재 생존 프로세스를 새로 조회하거나 모델을 다시 실행하지 않았다.

## 같은 비교 전제와 집계 방법

네 후보 모두 기존 SSH 신뢰·Tailscale 접속·구독 인증이 있는 두 Mac에서 제공된 source/binary를 private 경로에 놓은 조건으로 비교한다. A가 Tailscale을 data plane으로 썼다는 뜻은 아니며, 기존 기반의 이용 가능성과 실제 필수 의존을 구별한다. 새 B의 두 Mac 업무는 Newton 최종 결과로 확인했고 최종 Python 53개 ccc3에서 원답 3개 readback까지 완료했다. 실행 중 source 수정과 최종 readback의 소스 결속은 위에서 분리했다.

- 제공 파일을 기기에 배치하는 준비, 그 뒤 서비스 시작·가입, 업무 요청/후속, 장애 뒤 원답 회수, 새 답, 정리를 각각 센다. 배치에 사용한 SSH를 곧바로 가입·업무 프로토콜의 필수 의존으로 해석하지 않는다.
- 사용자 추가 개입은 실행 중 새 로그인·신뢰 승인·권한 변경·추가 prompt가 있었는지다. 기존 인증을 최초 취득한 조작 수와 초기 업무 요청을 포함한 총 사용자 비용은 별도이며, 기존 기록의 0회로 추정하지 않는다.
- 서비스/driver 시작 수, API 호출 수, 설정된 파일/노드 수는 서로 다른 단위다. 전송 재시도·상태 polling·하네스 전체 도구 호출을 설치 단계와 합치지 않는다. 파일이 존재했다는 근거로 파일쓰기 횟수를 만들지 않는다.
- 미실행, 시험체 미구현, 현재 작업의 운영 경계 밖을 구별한다. 신규 설치·최초 인증·업데이트를 실행하지 않은 표본은 그 상태로 남긴다.

## 시작·설정·가입·개입 공통표

| 후보·표본 | 제공물과 설정 | 실제 시작·가입 단계 | 실행 중 사용자 추가 개입 | 근거와 미계측 |
|---|---|---|---|---|
| A: 기존 LAN SSH 비교체 | 기존 SSH client/server·host trust·구독 Codex, private driver source. LAN 주소 지정. 제품 xsm pairing은 사용하지 않음 | driver/SSH 시작 2회: 최초와 재연결. 제품 네트워크 생성·초대·가입 호출은 이 시험체에 없음 | 0회 | [ABD JSON](../../p11-live/native-carrier-roundtrip-20261029.json)의 A `handles` 2개·`closed_handles` 2개. 새 host key/sshd 설치·최초 로그인·설정파일 쓰기 횟수는 미계측 |
| B-spike: 과거 private TCP 비교체 | Python stdlib TCP/HMAC/journal source, bootstrap·제어는 기존 tailnet SSH. 실제 iroh/QUIC 제품이 아님 | driver 시작 2회, TCP 포트 49909→49941. 실제 멤버십 생성·초대·가입 API는 미구현 | 0회 | 같은 JSON의 B `handles` 2개. fixture HMAC는 메모리/기존 SSH stdin. phase별 실제 socket endpoint trace는 미수집. 새 B의 가입 단계로 대체하지 않음 |
| C: 고정 Reason 0.12.10 비교체, 독립 실행 2개 | 실행당 두 private root·설정파일, 동일 binary SHA `6ac4bb4837469867edc2dba3cbbd6e4dd9fb18ad0389db69ff6ef21683317a44`. 기존 구독 인증. 실제 Reason CLI/계정은 사용하지 않음 | 실행당 최초 daemon 시작 2회, create 후 local 재시작 1회, join 후 peer 재시작 1회, 회수용 local 재시작 1회: 합계 5회. 팀 생성 1회·link 발급 1회·가입 1회. 최초 pull client 등록 2회·회수 때 재등록 1회 | 0회 | [C JSON](../../p11-live/C-native-roundtrip-20261029.json)의 각 run에 create/join/client 결과와 local handle 3개·peer handle 2개. 두 실행 합계 daemon 시작 10회, 생성/초대/가입 각 2회, 등록 6회. 등록 6회 중 회수용 재등록 2회는 설치와 구별. 설정된 root/file은 각 실행 2개지만 실제 파일쓰기 호출 수는 미계측 |
| D: Tailscale 위 기존 SSH 비교체 | 이미 실행 중인 VPN·SSH·host trust·구독 Codex. 새 VPN 설치·로그인·정책 변경 없음 | driver/SSH 시작 2회: 최초와 재연결. 별도 P2P 가입 API 없음 | 0회 | ABD JSON의 D `handles` 2개. 기존 VPN/SSH의 최초 설치·인증 횟수와 시간을 측정한 표본은 아님 |
| B-product: 현재 제품의 두 Mac 준비·ping 표본 | 제공된 Python 53개와 release binary 사본 2개, private P2P 설정파일 2개. SSH 서버 대조용 pairing 행 2개는 별도이며 P2P 가입의 요구가 아님 | 최초 서비스 기동 2회·init 1회·invite 1회·join 1회: 합계 5개 시작/멤버십 API 단계. 이후 제한 전환용 Book 재시작은 별도 | interactive prompt 0회 | [SSH 제한 결과](../ssh-only-20261029T132950Z/results.json)의 `preparation_observations`에 각 수가 있음. 파일 배치 2개 노드와 설정파일 2개는 동작 횟수와 구별. clean install/build/최초 로그인은 미측정 |
| B-product: 최신 실제 모델·최종 ccc3 회수 표본 | 같은 두 Mac·제공 source/binary·기존 SSH/구독 인증. 성공 fixture 실제 대화 2개. 초기 정책 preflight 2개 정상 | 서비스 최초 2·계획 재시작 2·stable-port 복구 시작 2, invite 1·join 1, 정상 주소 교환 2. Claude CLI 1·Codex CLI 5(같은 CID resume 4), FIFO 계속 6·MCP 재접속 2 | 추가 human yes/권한 답 0. operator 수정·재개·주소 교환은 별도 비용 | [최종 results](../native-journey-common-math-latest-retry1-20261029T155548Z/results.json) passed/check17. MCP ask 4·논리 업무 3, 준비 포함 ACK 8·양쪽 cleanup 0. 총 clean 설치·최초 인증 시간/세부 파일쓰기 횟수는 미계측 |

C의 API 수는 보존된 실행 코드의 호출 위치를 실제 성공 결과와 연결해 재구성했다. 생성/가입이 요구한 정상 재시작과 회수용 재시작을 구별했다. 근거는 [실행 코드](../../p11-live/C-run-private.py)의 `run`, [Node 구현](../../p11-live/C-fixture-lib.py)의 create/capability/join/register 및 각 run의 private_create/private_join/private_clients/cleanup/phase 결과다. 이 집계는 에이전트 전체 tool 호출 수 또는 최초 onboarding의 클릭 수가 아니다. 별도 C 팀 명시 승인 응답이 없었다는 당시 코디네이터의 범위 판단 기록도 원보고서에 보존한다.

## 과제와 측정 경계를 구별한 실제 업무·후속·회수

기본 업무는 marker `P11-QA-40c1afc34bbd43c4`의 `2+2=5` 검토다. 과거 네 후보의 실제 답은 claim_valid=false·corrected_sum=4와 짧은 반례였고 schema가 정답 값을 강제하지 않았다.

| 후보 | 첫 답 ms | 후속 답 ms | 보존 답 회수 ms | 재연결 뒤 새 답 ms | native / 별도 회수 |
|---|---:|---:|---:|---:|---:|
| A | 6137.471 | 6712.996 | 10.001 | 5409.321 | 3 / 1 |
| B-spike | 5816.222 | 7377.910 | 19.796 | 5657.270 | 3 / 1 |
| C 최초 | 5766.252 | 5028.281 | 175.142 | 6871.450 | 3 / 1 |
| C 보강 | 6375.519 | 5166.103 | 136.423 | 6877.705 | 3 / 1 |
| D | 4971.326 | 6304.035 | 12.623 | 6277.135 | 3 / 1 |
| B-product 최신 | 아래 별도 초 단위 표 | 아래 별도 초 단위 표 | 같은 ID 회수 확인·단독 소요 미계측 | 아래 별도 초 단위 표 | 논리 업무 3+준비 1쌍, 과거 집계와 별도 |


새 B의 `observed_same_host_seconds`는 Mini에서 request 생성→reply 수신을 같은 호스트 시계로 관측한 전체 경과다. 본문 경로는 두 물리 Mac의 실제 Rust/TLS이며 같은 호스트 peer 시험이라는 뜻이 아니다.

| 새 B 단계 | 원요청 / 회신 ID | 실제 JSON의 claim_valid / corrected_sum | 관측 초 |
|---|---|---|---:|
| 최초 `2+2=5` 검토 | `9f11884127764cad` / `e51fbbb4ce884a99` | false / 4 | 1298.9484422206879 |
| 수정안 검토 | `958971a5c24e4fe4` / `18ea96f2ea894fa5` | true / 4 | 110.46094274520874 |
| 재연결 뒤 새 짧은 검토 | `e1ce6790c1734665` / `ac9c995fc5a842df` | true / 2 | 81.29840421676636 |

최초 주제 `2+2=5`만 과거와 정확히 같다. 후속은 수정안, 마지막은 다른 짧은 검토 과제여서 같은 입력의 반복 benchmark가 아니다. 기존 답 2개를 재시작 뒤 원래 reply ID·본문으로 회수했고 최종 코드에서 3개 모두 재조회했다. cached 회수의 단독 시작/끝 소요는 원자료에 없어 미계측이다. 세 관측 초에는 소스 수정·수신 대기·일반 계속 Goal·resume·주소 교환이 포함되며 이 비용을 빼거나 순수 프로토콜 지연으로 변환하지 않았다. 과거 ms 표와 새 B 초 표는 순위표가 아니다.

과거 합계는 native 15회·cached 5회다. 각 native 호출은 Codex 0.163의 새 ephemeral 대화였고 후속에 직전 수학 결과를 명시적으로 제공했다. 새 B의 기존 Codex 0.164 동일 CID 재개·MCP 원문/ACK 여정과 하네스가 다르다. [기존 제품 업무](../native-journey-20261029T060853Z-fresh164-v2/report.md)는 요청/회신 3쌍과 중단 뒤 같은 ID 회복의 증거이며 위 시간 칸을 채우는 동일 경계의 새 실행은 아니다.

과거 A/B/D의 회수는 carrier를 다시 연결한 뒤 peer의 저장 답을 받는 경계다. C는 local daemon stop/start·register 뒤 오프라인 local inbox에서 같은 reply ID·본문을 회수한 경계다. C의 peer daemon·SSH control은 유지했다. 첫 답/후속 시간에는 CLI 기동·구독 추론·carrier·제어가 포함된다. 새 B는 handshake·3업무·question-status 원답 조회·MCP 원문 회복/ACK·서비스 재시작과 위 세 전체 경과를 구분했고 단독 측정되지 않은 부분은 미계측으로 남겼다. 이 자료로 성능 우위나 공통 회복 속도 순위를 산출하지 않았다.


## A·D 최초 SSH의 실제 음성검사

[실제 명령·결과](ssh-deny-results.json), [A 원 stderr](ssh-deny-a.stderr), [D 원 stderr](ssh-deny-d.stderr)를 보존했다. C no-SSH의 보존된 `PROFILE`과 같은 바이트인 `(version 1) (allow default) (deny network-outbound (remote tcp "*:22"))`를 `/private/tmp`의 0700 폴더·0600 파일에 저장해 각 자식 프로세스에만 적용했다. profile SHA-256은 `f0ab59f5498e4b1a0a29582836bc03716dacc71f5d5878a33223fea65f55f2ee`다.

두 호출 모두 실제 `/usr/bin/sandbox-exec -f <private-profile> /usr/bin/ssh`로 실행했다. `-F /dev/null -S none -oControlMaster=no -oControlPath=none -oControlPersist=no -oProxyCommand=none -oProxyJump=none -oBatchMode=yes -oStrictHostKeyChecking=yes -oUpdateHostKeys=no -oCanonicalizeHostname=no -oConnectTimeout=4 -oConnectionAttempts=1 -p 22 -T <기록된-IP> true`를 사용했다. 주소별 전체 argv는 JSON에 있으며 원격 `true`까지 도달하지 않았다. 원격 셸·모델·키 설치는 실행되지 않았다.

| 후보 | 실제 목적지 | 실제 결과 | 관측 시간 | 정리 |
|---|---|---|---:|---|
| A | `192.168.0.18:22` | exit 255, `Operation not permitted`, stdout 0바이트 | 0.013323초 | 소유 PID 6652 잔여 0 |
| D | `100.77.24.16:22` | exit 255, `Operation not permitted`, stdout 0바이트 | 0.011098초 | 소유 PID 6653 잔여 0 |

이는 Book의 소유 프로세스에서 각 주소로 가는 최초 carrier 연결이 거절된 실제 음성 결과다. 물리 두 호스트의 SSH를 전역 중단하거나 Mini의 역방향을 새로 실행한 것은 아니다. 기록된 과거 주소를 썼으며 제한 전 현재 도달성·로그인 성공은 다시 측정하지 않았다. 모델 0회이며 SSH config/known_hosts/authorized_keys/id_ed25519의 inode·size·mtime·mode는 전후 동일했다. 키·인증 값은 읽지 않았고 기존 서비스·전역 정책은 변경하지 않았다. 이 제한에서 업무 시작 불가를 실제 최초 연결 실패로 기록하며 설치 로그나 구조 추정으로 대체하지 않는다.

## 배치 뒤 SSH 의존과 신규 설치의 구분

| 후보 | 파일 배치 뒤 가입·업무의 실제 SSH 경계 | 무SSH 신규 설치·최초 인증 |
|---|---|---|
| A | 기록된 LAN `192.168.0.18:22`에 최초 SSH 1회가 실제 own-process deny 아래 exit 255·EPERM. 모델 미기동 | 미실행. A21-03에 신규 OS 인증 전수를 추가하지 않음 |
| B-spike | 본문은 private TCP, bootstrap·native driver 제어는 SSH 유지. SSH를 차단한 native 업무 표본 없음 | 미실행 |
| C | 기본 6회는 본문이 engine을 통과하고 native trigger는 SSH. 후속 [no-SSH 표본](../../p11-live/no-ssh-v2-summary.md)은 준비·join 뒤 SSH 종료, 소유 프로세스 TCP22 deny·실제 socket 거절 상태에서 자율 native 1회·본문 결속 성공 | 배치·가입 준비와 사후 회수는 SSH였으므로 미실행 |
| B-product | 기기키·초대 가입과 QUIC body는 실제 제품 경로. [혼합 모델 표본](../native-journey-mixed-proc-20261029T084031Z/report.md)은 Book native 자식 전체·Mini MCP/hook 업무 tool 경계의 TCP22/8022 deny와 실제 P2P 본문/첨부/회신을 확인. Mini native 부모 전체 일괄 차단과는 구별 | 제공 파일 배치 이전부터 SSH 없이 설치한 표본은 없음. 가입 자체의 초대 전달에 SSH를 쓴 준비와 제품 가입 프로토콜의 의존을 구별 |
| D | 기록된 tailnet `100.77.24.16:22`에 최초 SSH 1회가 실제 own-process deny 아래 exit 255·EPERM. 모델 미기동 | 미실행. 기존 VPN/SSH 인증을 재사용한 공통 전제와 구별 |

추가 C no-SSH/UDP 차단/proxy native는 기본 15회에 합치지 않는다. A/D가 이 비교 구성에서 SSH를 쓰는 사실은 모든 대체 구성의 지원 불가를 실측했다는 뜻이 아니다. B-spike의 NAT/relay 미구현도 새 B 제품의 지원 판정으로 옮기지 않는다.

## 운영·업데이트·제거: 실제 소유 구성요소만 비교

| 후보 | 실제 재연결·운영 | 확인된 소유 종료·제거 | 미실행·운영 경계 |
|---|---|---|---|
| A | SSH driver 종료/재시작 뒤 기존 답 회수·새 native 답 | driver 2개·native 3개 종료, 추가 tmp 귀속 프로세스 0. 비밀 아닌 코드/증거는 보존 | 소유 driver source 교체·업데이트·롤백 미실행. 기존 SSH 키·sshd는 소유 비교체가 아니므로 제거 대상 아님 |
| B-spike | driver/TCP listener 재시작 뒤 기존 답 회수·새 native 답 | driver 2개·native 3개 종료, 포트 49909/49941 connect_ex=61 | 소유 코드 업데이트·롤백 미실행. 제품 멤버 제명·키 회수는 이 spike에 미구현 |
| C | 생성/가입의 정상 daemon 재시작 및 회수용 local 재시작. 보존 답 ID·본문·endpoint 유지 | 두 실행 합계 daemon handle 10개·native 6개·SSH control 2개 종료. IPC 연결 거절, 각 private state/HOME/키·복사 binary 제거, 잔여 프로세스 0 | auto_update=false는 설정일 뿐 업데이트 성공이 아님. 고정 binary 교체/실패 롤백 미실행. 사용자 Reason 서비스/팀은 사용·제거 대상 아님 |
| D | SSH driver 재연결·보존 답 회수·새 native 답 | driver 2개·native 3개 종료. 소유 listener 서비스 새로 설치하지 않음 | 소유 driver 업데이트 미실행. 전역 Tailscale/SSH 삭제·가입 철회는 범위 밖이며 비교 종결의 새 의무가 아님 |
| B-product | 실제 서비스/엔진 stop·같은 키 재시작, 주소 전환, 실제 로컬 장애 독립성, 최종 소스의 신규키 가입·옛키 제명은 별도 보고에 존재 | [현재 SSH 제한 표본](../ssh-only-20261029T132950Z/report.md)은 서비스 실행분 3개의 정리·최종 PID/socket 잔여 0. [이전 private 설치](../installation-check.json)는 release 빌드·기본 탐색·시작·중지 | [실제 private 설치·제거](../uninstall-20261030/report.md)는 같은 root의 home A/B 설치→공유 서비스→A 제거 시 같은 PID/B 보존→명시적 stop→B 제거를 완료. 최종 PID/socket 0·UDP 2개 재bind. runtime/key/원문 보존은 의도된 계약. 실제 버전 교체/실패 롤백 비교는 미실행이며 이를 모든 후보의 새 필수 실험으로 추가하지 않음 |

private state·key·증거 보존과 제거는 표본별 지시가 다르다. C의 기존 지시로 지운 자체 fixture 상태와 새 B의 보존 대상 키/증거를 같은 정리 정책으로 강제하지 않는다. 새 B 제거 결과 `completed=true`를 확인했다. 공개 CLI 16개는 최초 home 설치 2개·설정/가입·상태/정리와 별도 canonical 보존용 설치/제거 2개를 포함하며, 명령 시간 합계 5.647초는 전체 설치 시간이 아니다. 모델 0회·추가 prompt 0회, canonical 원문 bytes와 pending 상태를 보존한 별도 handoff API fixture를 실제 모델로 부르지 않는다. 본 작업에서는 실제 전역 서비스·권한을 바꾸지 않았고 중복 설치·제거 실험도 하지 않았다.

## 원문에 따른 필수 범위와 별도 미계측 범위

[A21-03](../../../docs/plan/reason-inspired-adrs/acceptance.md)의 원문은 “양방향 SSH가 불가능한 환경을 포함해 A/B/C/D의 설치 단계와 사용자 개입을 비교한다”이며, 설정 로그만으로 연결 성공을 판정하지 말라고 한다. [P11](../../../docs/plan/reason-inspired-adrs/spec.md)의 1번은 설치 입력·기존 전제·사람 조작·도구 호출·첫 왕복·재연결·제거·로그 공개 범위를 같은 형식으로 기록하도록 하고, 3·4번은 환경별 실제 경로·왕복과 미확보 셀을 구별하도록 한다. 5번은 “설치 마찰과 운영·업데이트·키 회수·라이선스 비용을 비교한다”다.

따라서 업데이트·키 회수·라이선스 비교 항목은 유지한다. 이 문구가 모든 후보의 실제 버전 업그레이드/실패 롤백이나 새 OS·새 계정의 최초 인증 전수 실행을 명시하는 것은 아니다. [P10](../../../docs/plan/reason-inspired-adrs/spec.md)의 4번은 구 reader·설정·원문을 보존한 실제 업그레이드, 검증 절은 A23의 clean/기존·홈·세션·plugin/direct·snapshot/dev 행렬을 별도로 다룬다. 이를 A21-03의 추가 필수 실측 행렬로 옮기지 않는다. 공통 전제에서 실제 첫 연결/업무가 가능한지는 그대로 확인해야 하며, 업데이트 기능 지원·고정 공급물·설정만으로 업데이트 실행 성공을 만들지도 않는다.

## 운영·업데이트·키 회수·라이선스의 후보별 경계

| 후보 | 업데이트·운영의 확인 범위 | 키 회수·라이선스·비용의 근거와 한계 |
|---|---|---|
| A | 실제 기존 `/usr/bin/ssh`와 자기 driver를 사용. 자기 driver 재연결·정리는 실행, source 교체·실패 롤백은 미실행 | 기존 SSH 인증 재사용. 키 교체/취소·OS SSH 업데이트는 실행하지 않음. SSH 공급물의 라이선스/업데이트 운영비를 새로 검증하거나 시간으로 측정한 로그는 없음 |
| B-spike | private TCP/HMAC 비교체에는 NAT/relay·제품 멤버십·업데이트 관리가 미구현. 자기 driver·listener 종료는 실행 | fixture 비밀은 메모리/SSH stdin이며 제품 기기키 회수와 다름. 이 비교체를 제품 공급·라이선스/유지보수 비용으로 계상할 실제 로그 없음 |
| C | 고정 Reason 0.12.10 binary와 private IPC. auto_update=false·정상 daemon 재시작/소유 제거는 확인. 공개 소스의 updater 설명은 이 고정 실행에서 업데이트한 증거가 아님 | [기존 라이선스 조사](../../../docs/references/reason-network.md)는 엔진 MIT OR Apache-2.0·NOTICE와 비공개 CLI를 구별한다. 이번 실제 표본은 엔진만 사용, 구독/로그인 proof 없음. 재배포 검증 비용·업데이트 시간·서명 검증 성공·운영 금액은 미계측/미확인 |
| D | 기존 Tailscale 1.105.110 unstable/dev와 SSH 재사용. 자기 driver 정리만 실행, VPN/SSH 업데이트·계정 철회는 미실행 | VPN 인증/정책·SSH 키 운영은 기존 사용자 구성이다. 실제 계정 요금·라이선스 계약·설치/업데이트 인력 비용은 측정하지 않았고 전역 VPN 제거는 비교 의무가 아님 |
| B-product | 실제 private CLI 설치·소유 제거·재시작·키 교체 증거가 있음. [Cargo.toml](../../../native/xsm-net/Cargo.toml)은 iroh =1.4.1과 로컬 locked build의 공급 경계를 표시. 소유 버전 교체 시간은 미계측 | xsm 저장소의 [LICENSE](../../../LICENSE)는 MIT다. 종속성 전체 라이선스/NOTICE 완비·제품 서명 검증까지 입증한 것은 아님. 공개 relay 이용 표본을 영구 비용·SLA 보장으로 해석하지 않음. 자체 relay는 private 개발 프로세스이며 외부 운영 비용 미계측 |

실행 없는 업데이트 항목은 미실행, 숫자 로그 없는 비용은 미계측으로 남긴다. 이 공개가 모든 실제 업데이트를 대신했다거나 라이선스 배포 승인이 났다는 뜻은 아니다. 반대로 실제 업데이트를 네 후보에 모두 실행하거나 신규 OS 인증을 전수 수행해야만 A21-03이 닫힌다는 새 조건도 만들지 않는다.

## 기록 범위 종결과 남긴 한계

새 B의 최종 math 17항목 통과·원 ID/본문 유지·재시작 뒤 cached 원답 회수·ccc3에서 3답 readback·8ACK·최종 정리와 실제 준비/복구 횟수로 앞서 대기하던 두 비교 셀을 닫았다. A21-03의 기록 정리는 기존 인증·제공물과 명시된 실환경 조건에서 종결한다. 사용자 전역 G11/G12/G13·다른 63조건의 판정은 바꾸지 않는다.

과거의 실제 미지원·미실행 환경, 모든 후보의 운영/업데이트/키 회수/라이선스 비용 중 숫자 없는 부분, 순수 네트워크 지연·최초 bootstrap의 세부 시작·사람 판단 대기·provider 내부 스케줄링은 그대로 미계측이다. 각 후보에 새 OS 인증·실제 업데이트 전수 행렬을 추가하지 않았다. 기존 운영·업데이트·라이선스 비교 자체도 삭제하지 않았다. 실제 수신·정책·주소 실패와 소스 변화는 역사로 남기고 전체 최초 설치나 무보정 자동 wake의 성공으로 확대하지 않는다.

## 원자료와 이번 기록 확인

- [ABD 원보고](../../p11-live/native-carrier-roundtrip-20261029.md), [원 JSON](../../p11-live/native-carrier-roundtrip-20261029.json), [원 manifest](../../p11-live/native-carrier-manifest-20261029.json)
- [C 원보고](../../p11-live/C-native-roundtrip-20261029.md), [원 JSON](../../p11-live/C-native-roundtrip-20261029.json), [원 manifest](../../p11-live/C-native-evidence-manifest-20261029.json)
- [기존 공통 비교](../../../docs/plan/reason-inspired-adrs/remote-decision.md), [기존 G11 부분 판정](../../../docs/plan/reason-inspired-adrs/gates/G11-remote-comparison-draft.md)
- [최종 math 원결과](../native-journey-common-math-latest-retry1-20261029T155548Z/results.json), [최종 회귀 요약](../legacy-native-recovery-20261030/final-validation/summary.json)
- [이번 집계 JSON](summary.json): 원파일 SHA-256·실제 phase/복구 횟수·관측 시간·종결 범위·미계측 한계. 원파일은 수정하지 않았다.

이번 집계는 로컬 표준 라이브러리 JSON 읽기로 ABD `results[].handles/phases`, C `runs[].private_create/private_join/private_clients/cleanup/phases`, 새 B `preparation_observations`를 확인했다. 그 뒤 사용자 요청의 최초 SSH 음성검사 2회를 추가했으며 새 모델·새 P2P 업무·계정/전역 권한 변경은 0회다. 별도 대규모 검사기는 신설하지 않았다.
