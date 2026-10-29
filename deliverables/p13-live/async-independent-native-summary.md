# A16-02 실제 native 연속 표본

**기능 연속 증거는 성립했다.** 발신자가 질문을 한 번 보내 pending ID를 받은 뒤, 별도 CSV/검증 파일 작업을 완료했다. 실제 peer 회신 보관은 그 완료 관측보다 **4.328107초 뒤**였고, 발신자는 원 질문 ID의 상태 조회로 실제 final reply를 회수·ACK했다. 질문 대기를 마친 후 별도 작업을 한 표본이 아니다.

다만 종료 시 aggregate `profile/settings/auth metadata unchanged` 검사는 **false**였다. 경로별 before/after를 저장하지 않은 하네스 진단 공백 때문에 원인을 확정하지 못했다. 기능 흐름과 보호 입력 진단을 분리하며, 모든 실행 조건이 깨끗했다고 선언하지 않는다. 원 결과·목표는 보존했고 같은 조건을 재실행하지 않았다.

## 실행 조건과 원 목표

고정본은 `/private/tmp/xsm-final-receipt-frozen-i3u9pms3`, 현재 `final-source-manifest.json`의 315개 파일을 시작·종료에 대조해 일치를 확인했다. 제품 source1697 수정·회귀 재실행은 없다.

고유 private Git 저장소 `/private/tmp/p13-async-independent-6qwbi2sn/project`, private XSM_HOME을 사용했다. 고정본 `skills/xsm`을 저장소 `.agents/skills/xsm`에 그대로 복사했다. 두 native 모두 실제로 이 SKILL·messaging·guide를 읽었다. 기존 정상 factory `codex exec --ignore-user-config --json`, workspace-write/approval never와 단일 xsm MCP를 사용했고 두 actor 모두 기존 `.codex-3` 구독 프로필이다. credential 값 조회·복사·API 키 경로·allowedTools/권한 보정·프로필 편집은 하지 않았다.

reviewer의 원 목표:

> 이 private 저장소의 산술 검토 담당 a1입니다. xsm으로 동료의 검토 질문 하나를 받아 원문을 읽고 독립적으로 검산한 결과를 원래 동료에게 회신하세요. 동료의 질문을 처리할 때까지 대기하고, 회신과 읽은 메시지의 확인을 마친 뒤 결과를 보고하세요. 다른 세션·폴더·권한·설정은 바꾸지 마세요.

sender의 원 목표:

> xsm의 동료 검토 담당 a1에게 1부터 200000까지 정수 중 7 또는 11의 배수인 수를 중복 없이 더한 합을 독립 검토해 달라고 질문하세요. 그 답을 기다리는 동안 별도의 작업으로 1부터 8192까지의 정수와 제곱을 n,square 헤더의 data/squares.csv에 저장하고, 데이터 행수·제곱합·그 CSV 파일의 SHA-256을 data/squares-summary.json에 보관하세요. 별도 파일 작업을 끝낸 뒤 처음 질문의 실제 최종 회신을 회수해 답과 파일 검증 결과를 함께 보고하세요. 같은 검토를 새 질문으로 중복시키지 말고 읽은 메시지는 확인을 마치세요. 다른 폴더·권한·설정은 바꾸지 마세요.

목표에는 내부 ref/SID·CLI 순서·특정 tool 인자가 없다. 아래의 ask wait=0/status wait=50/inbox/ACK 선택은 agent가 제품 안내를 읽고 실제로 선택한 것이다.

## 실제 chronology (KST)

| 시각 | 증거 |
|---|---|
| 09:04:44.166371 | 원 요청 `64c5307e235d4032` canonical 보관 |
| 09:04:44.345035 | sender의 ask 결과 pending 반환 관측. 질문 송신은 총 1회 |
| 09:04:49.004~49.013 | 별도 CSV·summary 파일의 실제 mtime |
| **09:04:49.109945** | 실제 파일 작업 command exit 0 완료 관측·파일 내용 존재 확인 |
| 09:04:52.125842 | sender가 **같은 ID**로 question-status 시작 |
| 09:04:53.338802 | reviewer의 실제 reply_to/outcome 송신 tool 시작 관측 |
| **09:04:53.438052** | 실제 회신 `a0d6a4549fb1427f` canonical 보관 |
| 09:04:53.655426 | 해당 reply가 발신자 질문 index에 도착 |
| 09:04:53.885358 | 같은 ID 조회가 final/succeeded 본문을 반환한 것을 관측 |
| 이후 | reviewer는 원 요청, sender는 실제 회신을 각각 ACK |

native stdout에는 item 순서가 있고, 관측 시각은 controller가 각 native event를 처음 읽은 시각이다. 짧은 파일 작업의 item.started/item.completed는 같은 읽기 주기에 관측됐으므로 정확한 작업 시작 wall time으로 과장하지 않는다. 파일 mtime·command 성공·본문 보관 시각을 함께 대조한 보수적 완료 기준에서도 실제 reply 전 4.328107초 여유가 있다. 상태 조회는 파일 작업 **후**, reply 도착 **전** 시작해 실제 답을 기다려 반환했다.

## 원 ID·별도 작업·회신 검산

- 요청 ID: `64c5307e235d4032`, 실제 reply ID: `a0d6a4549fb1427f`, reply_to는 원 요청 ID와 일치한다.
- sender는 ask **1회**, 같은 ID status **1회**, 실제 reply ACK **1회**다. ledger resend는 0이다. reviewer는 inbox(wait=50) **1회**, 실제 reply send **1회**, 원 요청 ACK **1회**다.
- peer의 독립 검산 답은 **4,415,515,592**다. 실제 native 계산 tool 출력과 회신의 포함배제 설명을 보존했고, offline 전수 합산도 일치했다.
- 별도 작업은 실제 native shell이 만든 **8,192행/108,971 bytes CSV**다. 모든 행이 n=1..8192와 n²인지 다시 확인했다. 제곱합은 **183,285,493,760**이다.
- CSV SHA-256: `92d49c5b02ac6f0375aac1a9828660aa26ba063413501fd30d1bde86fec0d2a7`. agent가 만든 summary의 행수·합·SHA가 실제 파일과 모두 일치한다.
- 질문과 회신 모두 정상 native route로 보관됐고 최종 canonical state는 acknowledged다. 전달 영수증을 답으로 세지 않았으며 실제 endpoint-bound reply 본문과 명시 outcome=succeeded를 회수했다.

## setup·개입·actor 계수

| 구분 | 실제 값 |
|---|---:|
| fixture Git/skill/MCP 준비 | actor 호출 전, 모델 작업과 분리 |
| 실제 endpoint 초기 등록·역할 이름 setup | 2회: thread.started + 실제 MCP ancestor PID/home/cwd로만 등록, reviewer 이름 a1 |
| native actor 실행 | 2회: sender/reviewer 각 1회, 각 exit 0 |
| 각 actor MCP / shell | 각 3회 / 3회. shell은 제품 안내 읽기 2회 + 실제 계산/파일 작업 1회 |
| tool 오류·잘못된 shell 송신 | 0회 |
| controller 본문 relay / ACK / index 수정 | 0 / 0 / 0 |
| 추가 사용자 prompt·클릭·승인 | 0 |
| 조건 자동 재실행·새 actor/model retry | 0 |

실제 reviewer SID는 `01a184f8-f8af-7483-9bc9-6c8da826cda9`, sender SID는 `01a184f8-fdd2-7f40-ace6-afe75bab00fb`다. 역할 이름 외 native endpoint는 실제값이다. 내부 ID를 native 목표에 미리 제공하지 않았다.

## 보호 입력 진단과 잔여

고정본 소스 해시는 전후 동일하다. 반면 기존 공용 하네스의 aggregate profile/settings/auth guard는 false였다. 해당 guard는 `.codex`와 `.codex-3`의 설정 hash 및 auth **metadata만** 비교하나 before/after 경로별 값을 저장하지 않았다. 따라서 이 결과만으로 변경된 경로나 변경 주체를 특정할 수 없다.

포착된 두 actor의 shell은 private skill 읽기와 실제 계산/CSV 생성뿐이며 프로필 편집 명령은 없다. 사후 자기 `.codex-3` stat 관측에서는 config.toml의 mtime이 actor 종료 뒤였고 hooks/auth mtime은 actor 구간 밖이었다. 이 사후 값은 누락된 비교 전후 쌍이 아니므로 aggregate false의 원인이라고 단정하지 않는다. credential 내용은 읽지 않았다.

이 진단은 source 결함으로 재현된 것이 아니며 source 수정 근거로 삼지 않는다. 보호 입력 불변까지 요구하는 최종 조건 판정은 coordinator의 외부 변경 기록 대조가 남아 있다. 원 guard false를 숨기거나 재실행으로 덮지 않았다.

소유 reviewer PID 66849/MCP 66966, sender PID 67201/MCP 67329가 모두 종료됐고 같은 generation의 잔여는 0이다. user/peer의 기존 세션을 종료하지 않았다. 원 raw와 private 파일은 보존했다.

## 증거

- [실행 script](async-independent-native-run.py), [원 결과/원 목표](async-independent-native-results.json)
- [offline audit script](async-independent-native-audit.py), [24개 기능 검사·chronology](async-independent-native-audit.json)
- [source/raw/file manifest](async-independent-native-manifest.json)
- private raw: `/private/tmp/p13-async-independent-6qwbi2sn`의 native JSONL/stderr, controller 관측시각, canonical/index/ledger와 실제 CSV/summary.

기존 3라운드·기억·용량·전체 회귀를 반복하지 않았다. 이번 한 연속 셀의 기능 증거와 보호 입력 진단만 보고한다.
