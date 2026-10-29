# J03 interrupted wake=not-loaded: 포착 증거 기반 진단

`not-loaded`는 **일반 TUI 프로세스가 죽었다는 판정이 아니라, home별 control endpoint가 `thread/queue/start`를 거절했다는 분류**다. idle/busy에서도 같은 거절이 있었지만 TUI의 기본 큐 처리가 진행됐다. Esc 이후에는 그 처리가 재개되지 않아 pending이 남았다. 당시 control socket 응답자를 기존 daemon PID 9102에 직접 결속한 증거는 없어, “0.165 daemon이 0.164 TUI를 제어했다/버전 차이가 원인이다”까지 단정할 수 없다.

## 1. 정확히 어느 endpoint에 무엇을 보냈는가

고정본 `adapters.to_codex()`는 먼저 `_to_codex()`로 일반 CLI `codex queue --thread <SID> --message <본문>`을 호출한다. 그 출력의 queue ID를 얻은 다음 별개 경로인 `wake_codex()`를 호출한다. queue 성공과 wake 성공은 독립적이다.

`codex_daemon.socket_path(home)`과 `start_queued()`가 선택하는 주소는 다음과 같다.

- home: `/Users/jaesolshin/.codex-3`
- 논리적 Unix socket: `/Users/jaesolshin/.codex-3/app-server-control/app-server-control.sock`
- 실제 connect 인자: 위 경로의 `os.path.realpath()` 결과. 당시 realpath 문자열·inode를 별도로 포착하지 않아 물리적 socket 대상은 확정하지 못한다.
- transport: AF_UNIX socket 위 WebSocket `GET /rpc`, JSON-RPC.
- 순서: `initialize`(`experimentalApi: true`) → `initialized` → `thread/queue/start`.
- interrupted params: `threadId=01a1844f-fe38-7ce2-b466-7bb38e5a4c60`, `queuedSubmissionId=01a18456-9542-7293-b29a-6ba2d5e7ef85`.

이 함수는 receiver PID·PTY·MCP PID를 인자로 받지 않는다. home으로 control socket을 고른 뒤 SID와 queue ID를 전달한다. 대상 TUI가 실제 어느 server에 hosted됐는지를 먼저 매핑하는 분기는 없다.

고정본 `codex_daemon.py:75–80`에서 RPC error message에 `resume the thread before starting a queued message`가 포함될 때만 `not-loaded`가 나온다. 따라서 정상 고정본 경로와 포착 결과를 결합하면, socket 없음·connect timeout·WebSocket handshake 실패·initialize 실패가 아니라 **queue/start의 서버 오류 응답**에 해당한다. 이들은 각각 `unavailable`로 분류된다. wake 비활성화나 queue ID 파싱 실패라면 `skipped`다.

근거: 고정본 `xsm/adapters.py:124–165,168–197`, `xsm/codex_daemon.py:32–80,225–248`. 모델 요청의 HTTP/WebSocket endpoint 및 xsm MCP stdio는 이 AF_UNIX `/rpc`와 별개다. producer stderr의 모델 transport HTTP 426 진단도 queue/start의 `not-loaded`와 같은 오류로 합치지 않는다.

## 2. 0.164 TUI와 0.165 daemon을 구분한 사실

| 관측 대상 | 확보한 증거 | 확정하지 못한 것 |
|---|---|---|
| 평가 TUI | wrapper PID 64952(node), 자식 native PID 64954, lstart 2026-10-29 05:59:56 KST. session_meta originator=codex-tui, CLI 0.164.0, 실제 SID/cwd 일치 | native 내부 server의 제어 endpoint 주소·hosting 방식 |
| TUI 하위 도구 | 종료 직전 process tree에서 xsm MCP Python PID 65151과 code-mode host 등이 native 64954의 자식 | 이 사실만으로 standalone hosting인지, 별도 연결이 전혀 없는지 확정 불가 |
| 기존 daemon | 포착 기록에 PID 9102, lstart 2026-10-28 05:55:24 KST, `.codex-3/packages/app-server-daemon/releases/0.165.0-…/bin/codex`, 실제 version 조회 0.165.0 | **해당 control socket의 당시 peer PID가 9102였는지**. socket 소유/peer와 version 응답을 연결한 캡처 없음 |

TUI 호출 argv에는 `--no-daemon`·`--remote`·hook trust bypass가 없다. 일반 프로필을 로딩했고 xsm MCP/env만 호출 한정으로 고정본/private state에 연결했다. 그러나 일반 호출이라는 사실이 이 TUI가 기존 0.165 daemon에 hosted됐음을 보장하지는 않는다.

PTY에 `1 warning · f2 to view`는 남았지만 warning 내용은 열지 않았고, 포착 PTY에는 daemon/version mismatch/fallback 설명이 없다. **버전 불일치로 local server fallback했다는 설명은 가설**이다. 앞선 요약의 “CLI 0.164 + 기존 daemon 0.165 조합”은 공존 조건이며 응답자 귀속이나 인과의 증명이 아니다.

## 3. 큐 소비 성공과 queue/start 실패의 연결

| 상태 | queue/start 분류 | 실제 native 관측 | 읽기 전용 queue readback |
|---|---|---|---|
| idle | not-loaded | 기존 turn 완료 후 질문 UserMessage/새 turn, 원 요청 결속 succeeded 회신. queue→reply index 19.736초 | 해당 queue ID 없음 |
| busy | not-loaded | 06:02:19 보관. 기존 task_complete 06:03:01.666 뒤 질문 UserMessage 06:03:01.900. 회신 47.997초 | 해당 queue ID 없음 |
| interrupted | not-loaded | Esc의 turn_aborted 06:06:36.747 뒤 06:07:09 질문 보관. ask 60초 timeout·status pending. 103초 관측 동안 새 질문 UserMessage/turn 없음 | 같은 SID/queue ID의 원 row 유지 |

즉 `not-loaded`는 interrupted에만 새로 생긴 오류가 아니다. **세 상태 모두 명시적 queue/start는 성공하지 않았고**, idle/busy의 native 큐 소비가 그 제어 실패를 가렸다. 포착 로그는 실제 큐 소비를 증명하지만 내부 poll 주기나 poll 구현을 직접 계측한 것은 아니다. Esc 후 일반 큐 처리가 멈춘 관측은 코드 주석의 과거 Interrupted 동작 설명과 부합하나, 0.164 내부 원인까지 확인한 것은 아니다.

중단 전 Python background tool이 06:08:01에 완료된 event는 새 질문 수신·모델 turn 재개가 아니다. 수동 inbox poll·추가 prompt로 pending을 해소하지 않았다.

## 4. supported API와 진단 공백

현재 근거로 **기존 TUI의 정확한 host endpoint를 찾아 그 TUI를 안전하게 깨우는 supported API가 확보됐다고 말할 수 없다.**

- 포착된 공개 `codex queue --help`는 thread를 지정한 큐 저장을 지원한다. 이 경로는 이미 정확한 실제 SID로 사용했고 저장 자체는 성공했다.
- 앞서 포착한 CLI help의 `--remote`는 주어진 주소로 접속하는 옵션의 존재만 보여준다. 현재 local TUI의 endpoint 발견·ownership 검증·Esc 후 재개가 지원됨을 입증하지 않는다.
- 현재 제품의 `thread/queue/start`와 `thread/loaded/list`는 `experimentalApi: true`를 요구하는 제어 경로다. 모듈 주석의 측정 근거는 0.158/0.159이며 0.164/0.165의 지원 계약을 대신하지 않는다.
- `loaded_threads()`는 **동일한 home control socket**에 묻는다. 이 결과가 있어도 다른 host의 TUI endpoint를 발견하는 API는 아니다. 이번 own SID에 대한 당시 loaded/list RPC 원문도 포착하지 않았다.
- `initialize.clientInfo.version`은 xsm 버전이지 Codex CLI/daemon 버전 협상이 아니다. 초기화 응답은 error 여부만 검사하며 peer version·PID는 기록하지 않는다.
- adapter는 메모리에 `wake`와 `wake_detail`을 모두 보존하지만, 확보된 ledger/결과에는 `wake.detail="not-loaded"`만 남았다. 서버 원문·error code·initialize 응답·socket peer·물리 경로가 없어 정확한 응답자와 rejection context를 복원할 수 없다. 허용된 두 모듈만으로 이 진단 손실이 어느 상위 wrapper에서 일어났는지도 확정하지 않는다.

## 5. 구분해 남기는 판단

**하네스 조건:** 기존 프로필/기본 도구를 유지한 정상 PTY TUI이며 native CLI 버전이 기존 daemon과 달랐다. 평가가 도구나 기본 지침을 제거해 host를 깨뜨린 증거는 없다. 미확인 warning·hosting 경로는 별도 미확인이다.

**진단 공백:** 실제 socket peer PID/version, TUI host 주소, raw RPC error와 initialize 응답을 포착하지 못했다. 따라서 PID 9102 응답 단정이나 version mismatch 원인 단정은 불가하다.

**실제 제품 경로의 한계:** 현재 구현은 home별 control socket 하나를 선택하며 실제 TUI host로 재라우팅하지 않는다. 이 표본에서 그 경로의 wake는 실패했고 interrupted 자동 회신 요구를 충족하지 못했다. 다만 RPC 오류를 `not-loaded`로 매핑한 코드가 잘못됐다는 증거, SID/queue ID 오선택 증거, 큐 저장 실패 증거는 없다. 정확한 root cause를 확정한 소스 버그와 관측된 기능 실패를 구분한다.

추가 모델/TUI/CLI 실행, socket 접속, 새 thread/resume/turn-start, TTY 입력, 프로필·제품 소스 수정은 하지 않았다. 이미 확보한 own SID/PID/경로의 포착 자료만 읽었으며 이 문서 한 파일만 추가했다.

증거: [기존 결과](codex-state-native-results.json), [기존 manifest](codex-state-native-manifest.json), private root `/private/tmp/p13-codex-state-native-dv1ahfwm`의 `control.json`, `owned-process-tree-before-stop.json`, `receiver.pty`, `receiver-rollout.jsonl`, own producer 로그, `queue-readback.json`, own task ledger. 신규 런타임 조회로 과거 증거를 대체하지 않았다.
