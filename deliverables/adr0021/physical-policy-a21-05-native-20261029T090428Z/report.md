# A21-05 실제 Codex 로컬 업무의 원격 장애 독립성

Book의 실제 Codex 두 대화가 로컬 질문과 직접 회신을 세 조건에서 완료했다. 기본 조건, 소유한 Mini 제품 서비스 중단 뒤, Book 엔진의 UDP 전체·TCP 443 링크 차단 뒤에 각각 새 업무 질문과 실제 회신이 생겼다. 세 원요청과 세 회신의 canonical 상태는 모두 `acknowledged`이며 실제 MCP 원문과 일치한다.

마지막 계속 지시 뒤에는 새 모델이나 실험을 시작하지 않았다. 완료된 실행·MCP 원문·현재 소유 PID를 읽어 대조하고 정리 기록을 보완했다. [종결 관측](closure-observation.json)의 기록된 현재 PID 잔여는 0개다.

## 실제 표본과 초기 등록

| 항목 | 작성자 | 검토 담당 a1 |
|---|---|---|
| 실제 대화 CID | `01a186f7-65d6-7262-bb0c-d6026c5b36fc` | `01a186f7-65c6-7591-8200-066e7eab9f16` |
| 관측 CLI | `codex-cli 0.164.0` | `codex-cli 0.164.0` |
| 실제 관측 모델 | `gpt-6.1-sol` | `gpt-6.1-sol` |
| private home | `actors/requester/codex-home` | `actors/reviewer/codex-home` |

두 대화는 Book의 같은 실제 Git 작업 폴더와 같은 private XSM_HOME을 사용했다. 작성자는 같은 CID로 두 번 재개해 총 native 실행 3회, 검토자는 실행 1회였다. 모델명은 실행 인자에 지정하지 않았고 기존 provider rollout의 `turn_context`에서 관측했다. 실제 모델 호출이며 FILE actor 시험체가 아니다.

controller의 등록은 실제 `thread.started` CID, 읽기 전용 provider DB의 같은 CID·cwd, 현재 live native PID·시작 시각, 실제 MCP 조상이 모두 맞는 경우에만 수행했다. 각 재개는 새 실행 디렉터리를 사용했고 startup barrier는 그 실행의 현재 PID·시작 시각이 일치해야 풀렸다. 네 native 실행의 barrier가 모두 등록 완료를 기록했다. 이전 PID의 등록 파일을 현재로 인정하지 않았다.

모델에는 최초 제안 검토, 실제 검토를 반영한 수정안, 새 경계조건 검토라는 업무 목표만 주었다. 경로별 tool 호출이나 회신 본문은 주입하지 않았다. 모델의 shell command 실행은 0회였고 실제 협업 도구를 사용했다. controller는 본문 전송·답변 중계·ACK·질문 인덱스 보정을 수행하지 않았다.

## 장애 순서와 실제 결과

먼저 Book↔Mini의 실제 Rust P2P ping을 양방향 수행했다. 두 방향 모두 `direct`였고 해당 native response의 TLS origin과 양쪽 본문 digest가 일치했다. [초기 P2P 관측](initial-p2p-observation.json)에 별도 보존했다.

| 조건 | 원질문 ID | 직접 회신 ID | 요청·회신 최종 상태 |
|---|---|---|---|
| 로컬 최초 제안 검토 | `1e8888b285c445b1` | `210d5d010eb04ff5` | 둘 다 acknowledged |
| 소유 Mini 서비스 중단 후 수정안 검토 | `f17045ef49904743` | `f3fefd835e364dcf` | 둘 다 acknowledged |
| Book 엔진 링크 차단 후 새 경계조건 검토 | `731fac330b77411a` | `fa74ba20300a47ef` | 둘 다 acknowledged |

Mini 서비스는 실제 stop과 PID·control socket 소멸을 확인한 뒤 두 번째 업무를 시작했다. 전역 SSH는 유지했으며 종료 뒤 증거 조회에도 기존 SSH를 사용했다. 세 번째 조건은 Book 네트워크 서비스만 중지·재시작했으며 두 모델의 공유 XSM_HOME, 원래 대화·질문·회신은 보존했다. 검토 담당은 같은 프로세스에서 세 업무를 회신했고 작성자는 같은 CID를 재개했다.

각 원질문은 실제 작성자의 `xsm_ask` 입력 `text`, 실제 검토자의 `xsm_inbox` 응답, 검토자의 `xsm_send`와 정확한 `reply_to`, 원요청·회신의 canonical 본문에 결속했다. 저장 원문은 모두 같았다. 실제 소비 ACK도 두 모델이 호출했다.

실제 MCP 호출 수는 작성자 discover 1·connect 1·ask 3·ack 4회, 검토자 inbox 5·send 4·ack 4회였다. 업무 3건 외에 준비 확인 1건이 포함되며 업무 표에는 준비 확인을 합산하지 않았다. 검토 담당의 마지막 추가 수신 대기는 목표 완료 뒤 소유 프로세스 정리로 끝냈다.

## 엔진 링크 차단의 정확한 범위

공개 n0 relay 서비스를 중단하거나 시스템 방화벽을 바꾸지 않았다. 소유 Book 엔진에만 다음 process-local profile을 적용했다.

```scheme
(version 1)
(allow default)
(deny network-outbound (remote udp "*:*"))
(deny network-outbound (remote tcp "*:443"))
```

측정 wrapper는 같은 PID에서 실제 소켓 대조를 수행한 뒤 그 PID를 Rust 엔진으로 exec했다. 대조 PID 93797과 제품 status의 재시작 엔진 PID가 같음을 확인했다. sandbox는 exec 뒤에도 해당 프로세스에 적용된다. Rust 함수 내부에 새 관측 코드를 넣은 실험은 아니다.

| 실제 소켓 대조 | 기본 엔진 PID 89664 | 차단 엔진 PID 93797 |
|---|---|---|
| 소유 loopback 수신자로 UDP 송신 | 허용 | errno 1로 거절 |
| 기본 공개 relay의 IPv4 TCP 443 연결 | 허용 | errno 1로 거절 |
| 별도 소유 loopback TCP 포트 연결 | 허용 | 허용 |

UDP profile은 전체 UDP를 대상으로 하며 이 표의 실제 대조는 IPv4 소켓이다. TCP 전체나 모델의 provider 연결을 차단한 것이 아니다. 두 Codex·MCP는 이 엔진 sandbox의 자식이 아니며 계속 실제 로컬 회신을 수행했다. Book 네트워크 기기 신원도 재시작 전후 같았다. 이를 n0 자체 장애나 다른 NAT의 검증으로 확대하지 않는다.

## 동결본, 발견한 CLI 결함, 시간

요청 당시 52개로 알려졌던 Python 파일은 실행 준비 시 53개였으며 모두 동결했다. native 엔진 SHA는 [manifest](manifest.json)에 있고 source auth 값은 열거나 복사하지 않았다. 두 private Codex home은 기존 인증을 symlink로 참조했다. 원 인증 파일의 metadata와 원 profile의 config/hooks/settings/AGENTS 해시는 전후 같았다. API 키 환경변수와 모델명 override는 사용하지 않았다.

첫 네트워크 준비 중 동결된 `network.py`의 CLI `command`가 1153줄에서 지역 변수 `call`을 만들고 1218줄에서 모듈 RPC `call`을 참조해 `UnboundLocalError`가 났다. 실제 모델을 시작하기 전 init/status/stop에서 관측했고 [실패 원본](results-cli-preflight-failed.json)을 보존했다. 제품은 수정하지 않았다. 이후 준비·가입·중지는 이미 존재하는 private 제품 control RPC를 사용했고 이 변경은 operator setup helper에만 한정했다. [준비 API 기록](setup-api-note.json)에 명시했다. 현재 source에서는 해당 지역 변수 할당이 없음을 정적으로 확인했지만 CLI나 모델을 재실행하지 않았다.

실제 성공 실행은 2026-10-29 09:21:56–09:24:13 UTC, 137.414초였다. 준비·CLI 결함 분리 시간이 별도였으므로 첫 실제 모델 결과는 요청한 15분 목표보다 늦었다. 기본 업무 완료는 09:23:10, Mini 중단 조건은 09:23:36, 엔진 링크 차단 조건은 09:24:12 UTC에 관측했다.

실행 뒤 현재 source와 달라진 파일은 `network.py`, `network_messages.py`, `network_recovery.py`다. 이 결과는 manifest의 성공 동결본에 결속하며 현재 저장소 전체 회귀를 대신하지 않는다. 로컬 메시징 원문·ACK·인덱스를 고쳐 성공으로 만들지 않았다. 기존 actor raw의 오류 이벤트와 stderr의 502 표시는 모두 0이었다. 별도로 보고된 provider 502를 이 완료 표본의 actor 실패로 합치지 않았다.

## 정리와 증거

Mini 서비스, Book 재시작 전 서비스, 최종 Book 서비스의 소유 PID·control socket 잔여는 0이고 실제 UDP 바인딩 6개를 다시 bind할 수 있었다. 최초 actor 정리 직후의 짧은 관측에는 종료 중인 검토 PID가 남았으나, 후속 현재 PID 대조에서는 실제 actor·MCP·private 작업 폴더의 code-mode host 잔여가 모두 0이었다. 그 기록을 덮어쓰지 않고 [최종 정리](final-owned-cleanup.json)와 [계속 지시 뒤 관측](closure-observation.json)을 별도로 남겼다.

원본 state·key·실제 provider DB·원문·MCP 증거는 private 폴더에 보존했다. 인증 파일이나 symlink는 actor 증거 압축에 포함하지 않았다. 사용자 profile·권한·전역 proxy·SSH·n0 relay를 변경하지 않았다.

- [완료 요약과 원문·ACK·CID 대조](summary.json)
- [원 실행 결과와 단계별 socket 대조](results.json)
- [실제 actor/MCP 원문 묶음](actual-actor-evidence.tar.gz)
- [읽기 전용 분석 코드](helper-analyze.py), [실행 제어](helper-run.py), [실제 actor와 초기 등록](helper-actors.py), [동일 바이트 MCP 관측·barrier](helper-proxy.py)

이번 지시의 실제 로컬 장애 독립성 여정은 완료됐다. 별도 제품 제거 검증이나 전 세계 relay 장애를 포함한 A21-05 전체 환경의 종결 판정은 만들지 않았다. 보고서와 업무 목표는 한자·가나 범위 검사를 거쳤으며 raw 모델·서버 증거는 수정하지 않았다.
