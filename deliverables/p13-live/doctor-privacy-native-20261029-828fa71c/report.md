# doctor privacy postfix 실제 CLI 1회

**새 privacy 고정본의 실제 doctor JSON 경로에서 입력 표식 7종의 stdout/stderr 누출은 0이었다.** queued/unknown 두 stuck 분기와 오류 집계가 모두 비어 있지 않았고, 진단 ID·상태·고정 오류 분류는 유지됐다. private ledger 5파일은 바이트 그대로다. 현재 사용자 runtime의 같은 PID 세대 생존과 같은 thread의 후속 실제 tool 실행도 확인했다. 이 한 표본의 통과이며 전체 계획/1700 회귀 결과를 선취하지 않는다.

[요약/구조·SHA·판정](summary.json) · [실행 코드](run.py) · [기록만 읽는 검사기](offlinecheck.py) · [조건](plan.json) · [manifest](manifest.json) · [기존 v3 보존 확인](prior-preservation.json)

## source와 실제 호출

coordinator의 [doctor-privacy-source-manifest](../doctor-privacy-source-manifest.json)에 결속한 `/private/tmp/xsm-doctor-privacy-frozen-47o6orah`을 cwd/PYTHONPATH로 직접 실행했다. 정확한 interpreter/argv와 source SHA는 summary에 있다. 명령은 `python -B -m xsm doctor --json` **1회**, Python 3.14.6, exit **0**, 약 **0.368초**다. 추가 sandbox·sitecustomize·서비스 대체·실패 관측기를 넣지 않았다. 기본 호출자 권한의 정상 읽기 진단이며 doctor source는 수정하지 않았다.

현재 CODEX_THREAD_ID를 native DB의 정확한 행 및 자기 rollout session_meta ID와 비교하고, 실제 tool 프로세스의 OS ancestor에서 Codex PID/lstart/home을 확인했다. 이 shared runtime의 사실만 fresh private XSM_HOME에 **1 home/1 session**으로 등록했다. 표시 이름이 native DB에서 null인 사실도 유지했다. 통신·승인·caller certainty·개별 thread 생존의 일반 보증을 만들기 위한 등록이 아니다.

## 실제로 채운 입력과 출력

fresh private state에서 실제 `ledger.queued`로 5건을 만들고, `ledger.unknown` 1건·`ledger.failed` 3건을 적용했다. 준비 단계에서 각 queued 시각을 약 600초 전으로 두었다. 원 body/preview, 임의 중첩 message·invite, endpoint private 필드와 허용 ref 필드 내부 dict, raw 오류 prefix/detail에 서로 다른 무작위 표식을 넣었다. 초대는 `invite.invalid`의 합성 표식이며 실제 초대·자격 증명이 아니다. ledger에 진단 입력을 저장했을 뿐 send/wake/권한 부여를 호출하지 않았다.

| 실제 JSON 출력 경로 | 관측 |
|---|---|
| stuck.undelivered | queued **1건**, age 약 **600.4초**, 원 ID/queued 상태 유지 |
| stuck.uncertain | unknown **1건**, 원 ID/unknown 상태 유지 |
| stuck.send_failures | `sandbox-blocked: 2`, `other: 1`; raw 오류 prefix/detail 미출력 |
| 각 진단 행 | `id/status/t/from/to`만, endpoint 값은 string만 유지 |
| decisions/error 집계 | 별도 합성 internal-error 입력 1건을 실제 소비, decisions_seen **1**, hook_errors_recent **1** |
| 선택 home/등록 session | **1 / 1**. doctor의 실제 unregistered 관측은 **1**이며 0으로 보정하지 않음 |

본문·nested·raw_error·unknown_error·known_detail·허용 필드의 nested 값·합성 invite **7종**을 stdout/stderr bytes와 직접 비교해 모두 없었다. doctor stdout **6605 bytes**, stderr **0 bytes**다. 본문을 지워서 통과시킨 것이 아니며 5개 ledger 파일의 준비 직후 사본과 진단 직후 파일이 byte-for-byte 같다.

실제 사용자 home 경로는 설치 진단 metadata로 stdout에 존재한다. 이것을 메시지 body/초대/raw-error 누출로 판정하지 않는다. 공개 보고에는 원 stdout이나 실제 home 경로/표식값을 복사하지 않고 구조·SHA·판정만 기록했다. 실제 credential 값을 열거나 비교하지 않았고 모든 미지의 비밀에 대한 전수 비누출을 주장하지 않는다.

## 생존·후속 tool·보존

doctor 전/후의 실제 native ancestor PID/lstart가 같고, 진단 후 **별도 실제 tool 호출**에서 같은 native thread의 환경/readonly DB와 같은 PID 세대를 다시 확인했다. 이는 외부 생존 증거다. 별도로 doctor 자체 출력에서도 setup의 settings=present, trust/process/home_match=observed를 읽었다. mcp/first_roundtrip은 unknown이며 실제 첫 통신 성공으로 바꾸지 않았다.

driver는 종료/깨우기 신호·메시지·로그인·권한 부여·전역/프로필 설정 쓰기·credential 파일 조회를 하지 않았다. doctor의 기존 정상 liveness/readback을 막는 sandbox나 observer는 없다. profile config/hooks/settings의 inode·크기·mtime·mode metadata도 전후 같다. access tracing observer를 설치하지 않았으므로 모든 file-open/RPC를 독립 계측했다는 주장은 하지 않는다.

coordinator frozen 315파일 및 current/frozen primary 135파일의 SHA는 일치한다. 원 v3 JSON/Markdown/verdict는 변경하지 않았고, 원 기록에 기재된 raw 5개의 SHA도 그대로임을 확인했다. 원 v3의 observer 실패·unknown·기존 privacy verdict는 과거 source의 증거로 유지한다. 제품/원 plan/원 ledger artifact 수정은 0이다.

raw stdout/stderr·native 관측·marker oracle·private ledger 전후 사본은 `/private/tmp/doctor-privacy-native-1qw1twk2`에 보존했다. root **0700**, stdout/stderr **0600**이다. 공개 manifest에는 비밀 없는 파일 역할·SHA만 넣고 실제 private 경로 색인은 root 내부에 보존했다. 추가 모델·native TUI·doctor 재실행은 모두 0이며, 이 postfix CLI 1회 결과로 종결했다.
