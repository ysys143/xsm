# P11 C: 두 실제 머신의 private native 왕복

C의 독립 private fixture에서 실제 Codex 왕복 **6/6회**, daemon 재시작 뒤 기존 답 회수 **2/2회**를 확인했다. 최초 실행과 제어 경로 보강 후 재실행에 각각 first/followup/after-reconnect 3회가 있다. cached readback은 모델 호출에 포함하지 않았다. 이 결과의 통과 범위는 아래 두 머신·동일 과제의 C 비교체다. P11 전체 완료나 D12 backend 채택·배포는 확정하지 않는다.

- [전체 결과 JSON](C-native-roundtrip-20261029.json): phase별 응답, 시간, endpoint·conversation·메시지 ID hash, roster, 시작/종료 handle.
- [증거 manifest](C-native-evidence-manifest-20261029.json): 111개 파일의 경로·크기·SHA-256. peer 증거 58개는 SSH 회수 뒤 hash를 대조했다.
- [실행 전 고정 계획](C-private-plan-20261029.md), [보강 재실행 전 계획](C-private-guard-recheck-plan-20261029.md).

## 실제 실행 경로와 과제

local은 `Jaesolui-MacBookPro.local`, peer는 기존 SSH 별칭 `jaesol-macmini`의 `Jaesolui-Macmini.local`이다. 기존 SSH/Tailscale 신뢰 경로를 사용했다. SSH는 `BatchMode=yes`, `StrictHostKeyChecking=yes`, `UpdateHostKeys=no`로 고정했고 실행 중 사용자 개입은 0회였다. 기존 인증이 전제다.

local 현재 agent의 fixture pull adapter → local Reason engine `send` → 두 머신의 Reason network → peer engine `inbox` → 실제 peer `codex exec` → peer engine의 `reply_to` 답장 → local engine `inbox` 경로다. join 이후 SSH의 native 실행 trigger에는 phase와 예상 본문 hash만 전달한다. 수학 요청과 답은 C engine을 통과한다. 실제 Reason CLI/plugin/MCP의 일반 제품 통합까지 시험한 것은 아니다.

과제는 앞선 A/B/D와 같은 `2+2=5` 검토, marker는 `P11-QA-40c1afc34bbd43c4`다. 모든 실제 답에서 marker와 phase를 확인했고 `claim_valid=false`, `corrected_sum=4`, 짧은 반례가 나왔다. 출력 schema는 필드 타입만 정하며 정답을 const/enum으로 강제하지 않는다. 원시 native 출력·conversation ID·최소 수학 입력은 고유 tmp에 보존하고 공개 결과에는 수학 답과 ID hash만 기록했다.

실제 CLI는 `/opt/homebrew/bin/codex`, 매 호출의 version readback은 `codex-cli 0.163.0`이다. 이전 A/B/D의 ChatGPT 구독 인증 및 보정 flags를 재사용했다. auth 값은 조회·복사하지 않았고 API key 과금 경로는 사용하지 않았다. 모델은 CLI 기본값이며 별도 모델명을 단정하지 않는다.

보정 flags는 `--ignore-user-config --ignore-rules --ephemeral --skip-git-repo-check --sandbox read-only --json`, hooks/plugins/apps/shell_tool/shell_snapshot/remote_plugin 비활성화, `approval_policy="never"`, `project_doc_max_bytes=0`이다. instructions/schema/log/output 경로는 각 private phase 디렉터리로 지정했다. 실제 argv는 JSON 및 native helper에 남아 있다. 매 호출은 새 ephemeral conversation이며 followup은 이전 수학 결과만 입력으로 받았다. native resume/대화 기억 유지는 주장하지 않는다. 6개 conversation hash가 모두 다르고, CLI exit는 모두 0, 관측된 tool event는 모두 0이다.

## 측정값

| 단계 | 최초 실행 ms | 보강 재실행 ms | 실제 관측 |
|---|---:|---:|---|
| first native | 5766.252 | 6375.519 | 실제 JSON 답, 동일 request marker |
| followup native | 5028.281 | 5166.103 | 이전 수학 결과를 독립 재검토 |
| reconnect cached readback | 175.142 | 136.423 | local private daemon 재시작, 기존 답 ID·본문·endpoint 유지, 모델 재호출 0 |
| after-reconnect native | 6871.450 | 6877.705 | 재연결 후 새 요청·새 native conversation·답 수신 |

native 측정 경계는 send부터 local inbox의 답 검증까지다. SSH 제어 trigger와 구독 모델 추론을 포함한다. cached 측정은 daemon stop/start·register·보존 답 조회를 포함한다. 각 실행의 단일 표본이고 앞선 carrier의 cached 측정 경계와도 달라 성능 순위로 사용하지 않는다.

각 native 왕복 뒤 양쪽 `team` readback은 member 2명, 상대 `link="direct"`, `relay_connected=true`였다. relay 연결 유지가 수학 본문의 relay 경유 증거는 아니다. 선택된 relay URL은 readback에 없어 unknown이다. wire IP/port는 수집하지 않아 unknown이며 `direct`만으로 물리 LAN과 overlay를 구별하지 않는다.

cached readback 직후 local은 relay 미연결·상대 link 없음이었다. 이 단계는 저장된 inbox 회수 증거다. 이어진 새 native 왕복 뒤 양쪽 direct readback을 확인했다. 다른 NAT·UDP 차단·proxy·강제 relay 환경은 실행하지 않았다.

## 격리와 membership

실행 근거는 기존 사용자의 전체 P11 비교·격리 비교 요청이다. 코디네이터가 그 범위 안에서 두 controlled node만 쓰는 자기완결 일시 fixture라고 판단해 C 팀 생성·가입·client 등록을 실행했다. 별도의 C 팀 생성/가입 명시 승인 응답은 없었다. 이 판단을 새 사용자 승인 이벤트로 기록하지 않으며 실제 사용자 팀·전역 권한 및 D12 제품 선택과 구분한다.

engine은 양쪽 모두 고정 `0.12.10`, 매 시작 SHA-256은 `6ac4bb4837469867edc2dba3cbbd6e4dd9fb18ad0389db69ff6ef21683317a44`다. signature 검증 여부는 unknown이다. `probe_engine.py`, 고정 upstream의 IPC/paths/config/migration/team 구현 및 binary help를 확인하고 명시 Unix socket의 JSONL 규약을 사용했다. 고정 source 11개와 hash/URL은 JSON·manifest에 있다.

| 실행 | local root | peer root |
|---|---|---|
| 최초 | `/private/tmp/p11-C-a33f52rq` | `/private/tmp/p11-C-q27ngmzj` |
| 제어 보강 재실행 | `/private/tmp/p11-C-av3sz_4j` | `/private/tmp/p11-C-_n_rujrd` |

각 root는 본인 UID/0700이다. engine HOME/state/XDG/IPC와 실행 사본을 root 아래로 고정했다. IPC는 `<root>/state/network.sock`이고 fallback이 생기지 않는 길이다. `lan=false`, `tray=false`, `reason=false`, `auto_update=false`, `share_unmanaged=false`, `share_paths=false`와 NO_SERVICE/NO_TRAY/NO_MDNS를 적용했다. engine의 Codex/Claude 발견 경로도 빈 private 디렉터리다. 실제 Codex 호출에만 기존 구독 CODEX_HOME을 지정했고 그 호출의 HOME도 private이다.

각 실행에서 별도 팀을 만들고 `link(new=false)` capability를 Python 메모리 → 기존 SSH stdin → peer private IPC로 전달했다. argv·파일·원시 engine log·공개 출력에 capability를 쓰지 않았다. engine log는 줄 hash·크기·안전한 분류만 보존한다. 공개 항목은 capability/team/endpoint hash와 상태다. 자체 engine이 만든 private key/state는 종료 뒤 제거했다. 알려진 ticket 형식 검사에서 보존된 비상태 파일과 공개 C 산출물의 일치 수는 0이었다.

membership readback의 endpoint 집합은 각 실행의 두 controlled endpoint와 정확히 일치했다. 두 fixture pull client만 등록했고 실제 작업 session·제3자·실제 Jaesol’s network를 편입하지 않았다. fixture node는 로그인 proof 없는 `verified=false`, `has_proof=false`다. 실제 사용자 identity 검증 성공으로 해석하지 않는다.

기존 `.reason` state/계정/키/실제 Reason CLI/전역 membership/프로필/MCP 및 전역 XSM_HOME은 사용·변경하지 않았다. 기존 engine 원본 binary만 읽어 사본으로 실행했다. global profile 원문 비교는 하지 않았다. native helper의 settings metadata 비교는 private HOME 범위이며 global profile 불변을 입증하는 검사로 쓰지 않는다.

필수 외부 서비스 범위는 실행 전 계획에 고정했다. engine의 정상 기존 relay 목록/iroh discovery와 기존 구독 Codex 접속만 사용했다. 새 유료 서비스·VM·relay 배포·방화벽/TCC·hostkey 변경은 없었다. OS 권한·로그인 우회도 없었으며 own engine 로그의 permission 오류 분류는 0건이다.

## 시작 확인, 제어 보강과 정리

각 daemon/native/SSH control의 PID와 시작 시각 또는 ready 뒤 생존을 기록했다. create/join이 요구하는 자기 daemon 정상 재시작은 exit 0, controlled reconnect/final cleanup의 자기 handle 종료는 -15로 구분했다. 첫 계획 6번의 peer/client reconnect 표현과 달리 실제 재시작 대상은 local private daemon이었다. peer daemon과 기존 답을 유지한 상태로 회수와 새 왕복을 확인했다.

최초 성공 후 permission guard를 register/send/inbox/process 진입점까지 적용하고, polling은 요청이 아직 inbox에 없는 `native-receive`에만 허용했다. native/OS 실패를 반복 시도로 성공 처리하지 않는다. [제어 검사 5건](C-control-guard-test.json)은 실패 주입 검사이며 engine/model 호출 0이다. 보강된 정확한 코드를 새 두 root에서 실행해 추가 native 3회를 검증했다. 최초 실행 source는 tmp `executed-code`와 별도 hash manifest로 보존했다.

정리 결과는 daemon handle 10개 종료, native 6개 종료, SSH control 2개 exit 0이다. 양쪽 own IPC는 stop 뒤 연결 거절(`connect_ex=61`)이고 private state/HOME/키와 binary 사본이 제거됐다. 기존 서비스 stop 명령은 실행하지 않았다. 후속 SSH-stdin process scan에서 양쪽 두 root에 속한 잔여 프로세스는 0이다. 앞선 수집기 argv가 자신의 PID를 root 문자열로 잡은 오탐은 별도로 보존하고, observer를 제외한 최종 검사로 해소했다.

## 파일과 재검사

- [C-fixture-lib.py](C-fixture-lib.py), [C-peer-agent.py](C-peer-agent.py), [C-run-private.py](C-run-private.py), [C-native-base.py](C-native-base.py): 보강 재실행의 정확한 source. 실행기는 이미 종료·정리된 고유 root를 가리키는 실행 기록이다. 다시 실행하려면 새 private root와 사전 staging이 필요하다.
- [C-check-evidence.py](C-check-evidence.py): 모델/engine을 실행하지 않는 기록 검사. 원시 증거가 보존된 tmp 경로 및 manifest hash를 검사한다.
- [오프라인 검사 결과](C-evidence-check-20261029.json): `python3 deliverables/p11-live/C-check-evidence.py --self-test` 결과. synthetic native 성공 표시, 단계 삭제, cached 모델 재실행 변이 3개를 거절했다.

제품코드·기존 matrix 문서·backend 기본 선택은 변경하지 않았다. 미확보 환경과 일반 제품 통합의 증거는 이 fixture 성공으로 승격하지 않았다.

원 결과 JSON의 `approved subscription runtime`이라는 설명은 기존 구독 인증 재사용을 가리킨 당시 표현이다. 별도 C 팀 생성/가입에 대한 사용자 명시 승인 이벤트의 증거로 쓰지 않는다. 전체 비교 요청에 따라 일시 fixture를 실행할 수 있다는 코디네이터 판단과 D12 사용자 선택은 별개다. 원 native 응답·측정값·JSON은 수정하지 않았다.
