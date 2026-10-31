# Parley 조사: 사람이 함께 보는 IRC 채널과 하네스별 수신 경로

- 조사일: 2026-10-30
- 현행 xsm과의 관계: 아래 비교는 이 문서에 고정한 당시 소스 기준이다. 0.5.1은 기존 channel을 제거하고 팀·보드를 도입했다. 현행 계약은 [ADR-0025](../adr/0025-team-and-multi-recipient-dm.md)와 [ADR-0026](../adr/0026-team-board-on-xsm-doc.md)을 따른다. 당시 비교·실측 결과는 보존한다.
- 질문: Parley는 기존 코딩 세션의 발견·전달·협업·사람 권한·장애 복구를 어디까지 보장하며, xsm의 기존 계약에 무엇을 참고할 수 있는가?
- 대상: 사용자가 제시한 Reddit 게시물이 직접 연결한 **colinsurprenant/parley**. 동명 도구의 기능을 섞지 않았다.[1]
- 방법: 공개 소스와 스킬의 정적 분석, upstream race 검사, 실제 loopback Ergo/CLI 관찰, 합성 Stream을 이용한 독립 API 관찰. 실제 모델 간 협업은 이번에 실행하지 않았다.
- 산출물: [소스·해시 manifest](parley/source-manifest.json), [모듈 지도](parley/source-map.md), [실행 결과](parley/validation.json), [CLI 관찰 실행기](parley/cli-probes.py), [API 관찰 코드](parley/delivery-probes_test.go).

## 요약

Parley는 이미 쓰는 Claude Code·Codex·OpenCode 세션과 사람이 **하나의 로컬 IRC 채널에서 대화하게 하는 Go 프로그램**이다. 리더나 작업 큐를 제품에 두지 않고, 역할·진행·토론 규약을 스킬에 둔다. 사람은 일반 IRC 클라이언트로 같은 대화를 본다. xsm의 목표 중 사람과 에이전트가 함께 보는 N:N 채널에 직접 참고할 사례다.[1][2]

핵심 구현은 `Stream.Send/Read/Wait`, 공통 `Deliverer`, 하네스별 front다. IRC 서버가 순서·ID·시간을 정하고, Deliverer가 자기 메시지 제외·중복 억제·출처 표시·토론 gate를 적용한다. Claude에는 MCP channel 알림, Codex에는 `codex queue`, OpenCode에는 HTTP queued prompt를 쓴다. PTY에 타이핑하지 않는다.[3][5][7][8][9]

장점은 공개된 대화 흐름, 발신자와 본문의 구조적 분리, 코드로 구현한 토론 중단 장치, 순서가 끊겼을 때의 명시적 gap이다. 한계는 다른 머신을 거부하는 loopback 경계, 서버 재시작 때 사라지는 이력, 프로세스 재시작 때 사라지는 보류 큐, 의미론적 권한 판단을 스킬에 맡기는 부분이다. `sent`·하네스 인계·사람의 읽기·업무 성공을 같은 보장으로 읽으면 안 된다.[3][4][6][10][11][13]

따라서 참고 우선순위는 **공유 채널의 사람 참여, 초안 독립성 gate, 반복 중단과 재개 UX**다. xsm의 원문·요청 ID·ACK·결과 회수·명시적 권한·원격 멤버십을 Parley의 휘발성 채널로 바꾸자는 결론은 아니다. 아래 비교는 현재 소스의 기능과 이번에 실행한 범위를 구분한다.

## 1. 소스와 버전 고정

| 대상 | 고정값 | 해석 |
|---|---|---|
| Parley 조사 HEAD | `07f445c48723e446fa4d62ed068acfdf53c3f803` | 2026-10-27 커밋, 조사 시 원격 HEAD |
| 최신 확인 태그 | `v0.4.2` → `6067c961e6863d0c9edae88722aceecd55c98841` | annotated tag의 peeled commit. 조사 HEAD와의 차이는 README 한 파일 |
| Parley 모듈 | `go 1.25.0`, 외부 Go 모듈 요구 없음 | 프로그램 본체의 stdlib-only이며 Ergo·하네스까지 무의존이라는 뜻은 아님 |
| 실제 실행 도구 | Go `1.27.2`, macOS arm64, Ergo `2.19.1` | 본 조사 환경. upstream의 최소·검증 버전과 별개 |
| Ergo 릴리스 압축물 SHA-256 | `1bd97a0917036061e2dcdfc29149c2e252e3bc856282e0956afa2aaaa54dd787` | upstream CI의 macOS arm64 고정값과 다운로드 바이트 일치 |
| xsm 비교 소스 | `092e8801b0afcbb475bdb0384f546e55064fbf6f` | PR #20 병합본. 과거 Reason 조사 당시 소스와 섞지 않음 |

Parley HEAD와 태그의 전체 추적 파일 목록·크기·SHA를 manifest에 남겼다. Go 구현 파일 57개, 검사 파일 63개, 패키지 11개를 목록화했다. 목록 완전성은 모든 함수·분기의 실행 증명이 아니다. Apache-2.0 라이선스를 확인했고, 제품 구현 코드는 xsm에 수입하지 않았다.[17]

`doctor`가 “마지막으로 검증했다”고 기록한 버전은 Claude Code `2.1.296`, Codex `0.161.0`, OpenCode `2.1.0`, Ergo `2.19.1`이다. 이는 upstream 작성자의 기록이다.[14] 이번 조사에서 그 하네스 버전들을 실제 모델로 재검증한 것은 아니다.

## 2. 제품 경계: line, table, build

| 모드 | 목적·준비물 | 코드가 강제하는 것 | 스킬이 맡는 것 |
|---|---|---|---|
| line | 오래 사는 여러 세션의 진행 공유. 각자의 기존 작업 폴더 사용 | 명시적 세션 추가/제거, launch 파일 소유 확인, burst·장기 반복 breaker | 역할, 수신 대상을 본문에서 고르기, 작업 경계에서 반영, 불필요한 수신 인사 금지 |
| table | 여러 좌석이 질문을 검토. detached worktree에서 읽고 토론 | 첫 자기 게시 전 타 좌석 메시지 보류, 게시 수에 따른 breaker | 독립 초안의 실제 내용, 라운드 계산, 반론·철회·map, 파일 비수정 |
| build | 같은 저장소의 두 peer가 각자 branch/worktree에서 구현. Director 도입 필요 | 준비·작업 폴더·소유권 확인·rollback·종료 안전성 | RUN/AGREE, 파일 소유 협상·CLAIM/ACK/RELEASE, 예산 준수, 결정의 Director 승격 |

line은 세 하네스가 가능하고 table/build의 OpenCode는 지원하지 않는다. build의 `--peer`는 정확히 둘이다. table의 첫 게시 gate와 breaker를 build에도 있다고 일반화하면 틀린다. build front는 보류 gate를 적용하지 않는다.[11][12][13][15]

“오케스트레이터가 없다”는 말은 중앙 작업 배정자가 없다는 뜻이다. 채널 서버와 세션별 수신 프로세스는 존재한다. Codex/OpenCode의 자동 준비 경로는 새 대화를 만들며, 사람이 원래 띄운 임의 세션을 자동 발견해 연결하는 기능과 다르다. Claude는 출력된 launch 명령에 `--resume`을 더해 기존 대화를 이어갈 수 있다.[2][15]

## 3. 모듈과 실제 메시지 경로

| 단계 | 주요 코드 | 동작 |
|---|---|---|
| 준비 | `cmd/parley/{line_new,line_add,table_new,build_new,setup}.go` | 서버 주소·nick·폴더를 검사하고 launch 설정·대화 ID·소유 기록 생성 |
| 게시 | `cmd/parley/main.go`, `internal/stream/{file,irc}` | 모델이 자기 셸에서 `parley send --body-file …` 실행. 별도 MCP 송신 도구 없음 |
| 순서·회수 | `Stream`, `irc/{irc,history,conn}.go` | 서버 msgid/time과 CHATHISTORY를 정본으로 사용. socket의 실시간 이벤트는 다시 읽을 신호 |
| 공통 수신 | `stream/deliver.go` | echo·중복 제거, gap, table seal·breaker, 신뢰 표제와 본문 렌더링 |
| Claude | `channel/channel.go` | MCP initialize 완료 후 `notifications/claude/channel` 쓰기 |
| Codex | `codex/codex.go` | `codex queue --thread UUID --message TEXT` 직접 exec |
| OpenCode | `opencode/{opencode,queue,client,service,history}.go` | 서버·세션 확인, idle 대기, queue POST, ID와 본문 readback |
| 수신 위치 저장 | `state/state.go` | front별 인계 기준을 만족한 뒤 cursor 저장. nick lock과 stream별 cursor 분리 |

CLI의 `wait`도 같은 Deliverer를 이용한다. “모든 하네스에서 같은 텍스트를 받는다”는 것은 공통 렌더러의 계약이지, 세 하네스가 같은 수신 증거를 제공한다는 뜻은 아니다.[3][7][8][9][10]

## 4. 발견·주소·범위와 프로필

Parley에는 실행 중인 모든 세션을 업무 내용으로 찾는 디렉터리가 없다. 사용자가 line에 nick·harness·workdir를 명시적으로 추가한다. 주소는 IRC nick, 채널은 line/table/build ID다. `plan:` 같은 본문 접두사는 의미상 수신 대상이며 라우터의 ACL이 아니다. 다른 nick의 게시물은 같은 채널의 각 front에 전달되고 스킬이 자기에게 해당하는지 판단한다.[3][13][15]

nick은 최대 64바이트이고 ASCII 대소문자를 접어서 비교한다. 상태 디렉터리·lock도 같은 정규화를 쓴다. 한 nick의 두 수신 프로세스는 채널이 달라도 같은 lock으로 거부한다. 반면 pump와 일회성 send는 같은 IRC 계정의 multiclient로 공존한다. `tables/builds/lines`는 상태 폴더 이름이므로 nick으로 쓸 수 없다.[3][6][10]

상태는 기본 `$XDG_STATE_HOME/parley` 또는 `~/.local/state/parley`이며 `--state-dir`로 분리한다. 프로필별 네이티브 레지스트리를 합치는 방식은 아니다. Codex의 큐 호출은 pump 환경을 상속하므로 올바른 `CODEX_HOME`과 thread의 결속이 필요하다. `$CODEX_THREAD_ID`와 기록이 다르면 send는 경고하면서 게시한다. 자동으로 새 thread에 재결속하지 않는다.[8][10][15]

## 5. 하네스별 인계 증거와 제약

### Claude Code

`parley channel`은 **수신 전용 MCP channel server**다. tools 목록을 내놓는 일반 송신 MCP 서버가 아니다. 응답은 모델의 셸이 `parley send`를 실행한다. JSON-RPC stdout과 진단 stderr를 분리하고, initialize 응답 및 initialized 알림 이전에는 푸시하지 않는다. notification 쓰기가 성공한 뒤 commit/cursor를 진행한다. 이 시점은 모델이 읽었거나 답했다는 증거가 아니다.[7]

Claude 실행에는 `--dangerously-load-development-channels server:parley`가 필요하다고 README가 명시한다. 이는 특정 개발 channel의 허용 목록 예외이며 일반 도구 권한 해제와 같지 않다. 계정/조직의 channel 사용 전제도 있다.[2] 이번 조사에서 그 플래그를 사용자 세션에 적용하거나 실제 연결하지 않았다.

primer 길이는 UTF-16 기준 2,048 units를 검사하고, 넘으면 조용히 잘라 신뢰 규칙을 잃는 대신 시작을 거부한다. MCP 협상 버전 목록도 의도적으로 고정했다. upstream이 특정 Claude 버전에서 관찰한 호환성 판단이며 모든 차기 버전의 호환성 증명은 아니다.[7][14]

### Codex

큐에는 일반 user turn으로 들어간다. Parley는 공통 peer header를 보존해 사람이 직접 친 입력과 구별하려 하지만, 런타임의 역할 자체를 peer로 바꾸는 것은 아니다. `exec.CommandContext`의 argv로 전달하므로 본문을 셸 코드로 평가하지 않는다.[8]

큐 명령 성공 뒤 cursor를 저장한다. 큐 진입과 모델의 실제 소비는 구별해야 한다. 렌더링 한 인자의 상한은 131,071바이트다. 큰 batch는 메시지별로 분할하고, 하나도 너무 크면 원문 대신 ID와 크기를 알리는 stub를 전달한다. 분할 도중 실패하면 전체 cursor가 진행하지 않아 이미 큐에 들어간 앞부분이 재전달될 수 있다.[8]

### OpenCode

OpenCode 2의 로컬 HTTP 서비스를 쓴다. 서비스 등록 파일의 소유자·권한·파일 종류·크기·loopback 주소를 확인하고, 실제 서비스 PID·버전 및 세션 directory를 대조한다. 인증정보를 가진 임의 원격 URL로 보내는 일반 HTTP bridge가 아니다.[9]

idle 뒤 `delivery=queue`로 고른 message ID와 본문을 게시하고, 응답 유실은 같은 ID로 다시 게시한다. 승인됐다는 HTTP 응답만으로 끝내지 않고 세션 message에서 원문을 읽거나 사람이 inbox 항목을 취소한 것을 확인한 뒤 commit한다. 취소된 입력을 steer로 바꿔 다시 깨우지 않는다.[9]

다만 POST 응답 유실 사이에 사람이 항목을 삭제하면 OpenCode의 취소 tombstone 부재 때문에 재게시가 한 번 되살릴 수 있다고 코드가 명시한다. pump 재시작 후 같은 ID를 영속 복구하는 구조도 아니다. 128KiB 메시지·512KiB 본문 batch·1MiB stub 포함 한도도 있어, stub 인계가 원문 소비를 뜻하지 않는다.[9]

## 6. IRC의 순서·다중 행·이력 복구

서버는 Ergo이며 loopback의 평문 TCP를 쓴다. URL 파싱에서 원격 호스트를 거부하고 연결 뒤 실제 remote address도 다시 검사한다. `parley server --listen`은 hostname도 받지 않고 loopback IP literal을 요구한다. TLS·원격 발견·NAT traversal·팀 초대 프로토콜은 구현 범위 밖이다. SSH tunnel 운용 가능성은 별도 추론이며 이번에 검증한 공식 머신 간 경로로 세지 않는다.[4][6]

단일 게시물은 긴 줄·개행을 IRCv3 `draft/multiline` batch 하나로 보내고 msgid 하나를 받는다. UTF-8 rune 경계에서 IRC 줄을 나누므로 사람이 다른 IRC 클라이언트에서 입력한 메시지와 같은 순서 체계로 읽는다. 서버의 multiline 상한은 64KiB·1,000줄이며, 넘거나 NUL/CR이 있으면 송신 전에 거부한다.[5][6]

실시간 socket 수신 본문을 별도 정본으로 삼지 않는다. 새 메시지 신호가 오면 CHATHISTORY를 조회한다. cursor는 마지막 서버 msgid이며, JOIN 같은 비본문 이벤트도 paging anchor를 잃지 않게 처리한다. Ergo가 모르는 cursor에 빈 batch를 돌려주는 문제는 LATEST와 AFTER 재확인으로 구별한다. 단순히 “빈 결과면 최신 상태”로 간주하지 않는 점이 참고 가치가 있다.[5]

서버의 channel history 기본 ring은 2,048개이며 persistent history는 꺼져 있다. 계정 DB는 디스크에 남고 대화는 서버 재시작 때 사라진다. 새 이력이 생긴 후 옛 cursor로 읽으면 gap을 알리고 남은 이력을 전달한다. gap은 누락 사실의 통지이지 누락 원문 복원이나 재전송의 성공이 아니다. Parley 자체가 대화를 영속 저장하지 않는다는 뜻이며 하네스의 대화 기록·사용자 IRC 클라이언트의 로그까지 없앤다는 뜻은 아니다.[5][6]

파일 adapter는 개발·시험용 NDJSON append log다. ID는 바이트 offset, cursor는 offset과 앞선 record fingerprint를 묶어 회전·같은 길이 재작성도 gap으로 판정한다. 파일 작성자가 `author`를 지정할 수 있으므로 IRC 등록 nick의 신원 보장을 파일 adapter에 옮길 수 없다.[3][10]

## 7. 권한 경계: 구조적 출처와 사람의 의사

### 코드가 강제하는 표시

`Delivery.Render()`는 모든 메시지에 Parley 자체 header를 붙이고 본문 각 행을 두 칸 들여쓴다. 본문에 가짜 `[parley] from=chair`를 넣어도 column zero의 header가 되지 않는다. CR·ESC·C0/C1 제어문자·Unicode 행 구분자·잘못된 UTF-8도 정리한다. 이는 표시 위조·터미널 제어 방어이며 자연어의 악성 지시를 의미적으로 차단하는 장치는 아니다.[3]

IRC는 nick별 32바이트 난수 자격 증명을 생성해 0600 파일에 보관하고 이후 SASL PLAIN으로 인증한다. 엄격한 nick reservation과 multiclient로 이름 탈취와 송신/수신 연결 충돌을 줄인다. 사람 chair nick은 먼저 직접 등록해야 한다. Deliverer의 chair 분기는 author nick 비교이지, 사람의 OS 신원이나 승인 대상 요청을 검증하는 서명된 승인 객체가 아니다.[4][6][10][13]

### 모델이 따라야 하는 규칙

모든 header는 터미널에서 직접 친 입력이 아니며 그 터미널의 권한을 주지 않는다고 말한다. chair의 채널 발언을 역할·우선순위·논의 진행에 쓰는 것은 스킬의 별도 규약이다. 도구 실행 승인과 권한 프롬프트는 원래 터미널에 남기며 Parley는 이를 중계하지 않는다. “사람이 IRC에서 말했다”와 “이 도구 실행을 승인했다”는 별개다.[3][11][12][13]

같은 OS 사용자의 에이전트 프로세스가 그 사용자의 0600 파일을 읽는 것까지 막는 별도 보안 주체는 아니다. 기본 채널에 저장소별 ACL·세션 공개 승인·파일 접근 capability를 추가하는 코드도 확인되지 않았다. 이 문장의 범위는 조사 소스의 구성과 호출 경로이며, 실제 공격 성공을 재현했다는 주장은 아니다.[4][6][10]

## 8. 독립 초안 gate와 반복 중단

table은 front가 시작할 때 seal을 닫고 peer 메시지를 보류한다. chair 발언은 통과하며, **시작 시점 이후 자기 nick의 게시물 하나**를 관측하면 seal을 연다. 답변 내용·독립성·라운드 번호를 파싱하지 않는다. `ready` 한 줄도 연다. 그래서 table 스킬은 초안 전에 준비 인사를 게시하지 말고, 남의 초안을 먼저 봤다면 `seen:`으로 밝히라고 요구한다.[3][11]

table breaker는 마지막 chair 이후 non-chair 게시 수가 cap을 넘으면 보류한다. line에는 초기 seal이 없고, window 안에서 cap 초과 또는 chair 이후 총 `5 × cap` 초과일 때 보류한다. 자기 게시도 센다. 시간만 지나서는 풀리지 않으며 chair의 새 게시가 count·rate를 지우고 보류를 먼저 전달한다. 이는 게시 자체나 하네스 실행을 종료하는 전역 kill switch가 아니라 **front별 전달 중단**이다.[3][13]

보류 큐·중복 집합·seal·count는 메모리다. cursor는 보류 항목 뒤까지 진행할 수 있어, 그 위치를 저장한 뒤 재시작하면 보류 본문을 다시 받지 않는다. 새 프로세스의 breaker도 초기화된다. 전달이 없으면 `Wait`가 timeout까지 기다리는 경로와, 다른 정상 전달에 보류 상태가 함께 commit되는 경로를 구별해야 한다.[3][7][8]

이번 API 관찰에서는 cap=1로 첫 peer 메시지를 전달하고 둘째를 보류한 뒤 같은 cursor에서 새 Deliverer를 만들었다. 같은 프로세스에서는 chair 발언에 둘째가 풀렸으나, 새 프로세스에서는 chair만 전달되고 gap 표시는 없었다. 별도 관찰에서는 재시작 후 chair 발언 없이 새 peer 메시지가 전달됐다. 이는 합성 Stream의 API 관찰이며 실제 OS 프로세스를 강제 종료한 실험은 아니다. 원문이 transport에 남아 있는 것과 기본 cursor로 자동 복구되는 것은 다르다.

또한 table의 읽기 전용 규칙, build의 파일 CLAIM/ACK와 겹침 검사, 토론 round/time cap, Director 승격은 스킬 절차다. detached worktree는 변경을 원본 작업 폴더에서 분리하지만 filesystem read-only mount가 아니다. “협업 규약이 상세하다”와 “악성 peer에 대해서도 강제로 집행한다”를 구별한다.[11][12][15]

## 9. 설치·시작·중지·제거 비용

구성은 Go binary 하나 외에 Ergo, 하네스, 사람의 IRC 클라이언트, 세션별 front, 스킬이 필요하다. `skills/install.sh`는 세 스킬을 `~/.claude/skills`와 `~/.agents/skills`에 checkout symlink로 설치한다. 타인의 파일은 대체하지 않고 preflight·rollback·자기 링크만 제거하는 절차가 있다. 여러 `CLAUDE_CONFIG_DIR`에 자동 배포하는 설치기는 아니다.[2][16]

Claude line add는 작업 폴더의 `.mcp.json`, Codex는 `.codex/config.toml`을 생성한다. 기존 파일을 임의 병합하지 않고 자신이 만든 파일의 SHA와 같은 경우만 공유한다. Codex 설정은 `workspace-write`, `approval_policy=on-request`, **`network_access=true`**다. IRC loopback에 닿기 위한 선택이지만 같은 작업 폴더의 다른 Codex 세션에도 적용되는 범위다.[15] 이번 조사에서는 사용자 작업 폴더에 이 설정을 쓰지 않았다.

자동 준비의 Codex는 네트워크를 끈 primer turn을 `codex exec --json`으로 시작해 thread.started·turn.completed를 확인한 뒤 ID를 저장한다. 모델 호출을 포함하므로 순수 파일 설정 작업이 아니다. OpenCode도 새 session ID를 만든다. 사용자가 이미 가진 인증을 어떤 런타임 경로로 쓰는지는 그 실행 환경의 문제이며, 이번 관찰은 fake와 API 경계까지만이다.[9][15]

종료 시 active nick lock, 파일 해시, worktree 관리자 경로, dirty/미병합 branch 등을 검사한다. `line drop/end`는 자신이 만든 launch 파일과 exclude 행만 정리하고 대화 이력은 자동 삭제하지 않는다. 설정이 바뀐 경우 `--force`도 바뀐 파일을 지우는 뜻이 아니라 보존하고 나머지를 마치는 뜻이다. 준비 실패의 rollback과 정상 종료의 이력 보존을 구별한다.[15]

`doctor`는 버전·CLI flag·서버 capability·스킬 링크를 검사한다. `--live`는 실제 Codex primer turn을 실행하지만 **실행 중인 TUI를 필요로 하는 queue는 live 검증하지 않는다**고 명시한다. doctor 성공을 기존 사용자 TUI의 깨우기 성공이나 다중 프로필 행렬 통과로 확대하면 안 된다.[14]

## 10. 실행 근거와 미검증 범위

실행별 명령·exit·개수·실패 출력·SHA는 [validation.json](parley/validation.json)에 있다. upstream 전체 검사와 독립 관찰을 합쳐 하나의 통과 숫자로 만들지 않는다.

| 실행 | 결과 | 범위 |
|---|---|---|
| `go vet ./...` | exit 0 | 정적 진단 |
| `PARLEY_ERGO=… go test -json -race -count=1 ./...` | **exit 1**, 610.036초 | 11패키지 중 9개 통과. doctor 1검사 실패, CLI 상대 worktree 경로 1검사 실패와 기본 10분 timeout |
| timeout 때 끝나지 않은 CLI 상위 검사 5개 재실행 | exit 0, 5.438초 | `-timeout=5m -run … ./cmd/parley`. 하위 포함 54개 leaf 시나리오 |
| doctor 실패 검사 단독 재실행 | exit 1 | 같은 PID 파일 부재 오류 |
| 독립 CLI 관찰 | 7시나리오 모두 통과 | 실제 local Ergo + file adapter. 모델 0회 |
| 독립 API 관찰 | 상위 4검사·5시나리오 모두 통과 | 합성 Stream. 부모 집계를 포함한 pass 이벤트는 6개 |

최초 전체 실행의 test pass 이벤트 2,104개에는 부모 집계와 하위 검사가 함께 들어 있다. 이를 독립 테스트 2,104개로 세지 않는다. 미완 5개 재실행과 합쳐 고유 상위 검사 933개가 종료했고 931개 통과·2개 실패였다. skip 이벤트는 없었으나 **한 번의 전체 회귀 통과 기록은 확보하지 못했다**. 실패·timeout 원기록을 재검 성공으로 덮지 않았다.

실패 두 종류는 다음과 같다.

- `TestAProbeThatHangsTakesItsWholeProcessGroupAtTheTimeout`: 300ms probe 뒤 자식 PID 파일이 없었다. 출력은 `the launcher never wrote its child's pid`이며 단독 재검도 같았다. 별도 새 실행파일 3개의 첫 셸 실행은 0.3031–0.3782초, 같은 파일의 두 번째는 0.0057–0.0152초였다. 시작 지연과 짧은 시험 예산의 관련성을 시사하지만 원래 fixture에서 원인을 확정한 것은 아니다.
- `TestRelativeWorktreePathsAreResolvedFromTheAdminDir/build_new_and_build_end`: Git `2.46.0` 환경에서 시험이 요구한 상대 경로 대신 절대 `gitdir`가 생성됐다. `git did not write a relative one, so the test proves nothing`으로 실패했다. 이 환경에서 상대 경로 fixture가 성립하지 않았고, 그 경로의 통과 증거도 없다. 제품의 경로 해석 결함이 재현됐다는 뜻으로 쓰지 않는다.

재현할 때는 manifest의 Parley commit과 Ergo archive SHA를 먼저 맞춘다. CLI 관찰 실행기는 사용자 프로필 대신 새 임시 상태 폴더와 빈 loopback 포트를 쓰며 소유 서버를 종료한다. 상태·합성 메시지는 해당 임시 폴더에 남긴다.

```sh
python3 docs/references/parley/cli-probes.py \
  --parley /path/to/built/parley --ergo /path/to/verified/ergo \
  --output /tmp/parley-cli-results.json
```

API 관찰은 조사 소스의 **별도 disposable 복사본**에서 `delivery-probes_test.go`를 `internal/stream/reference_probes_test.go`로 복사한 뒤 `go test -race -count=1 -run '^TestReference' ./internal/stream`으로 실행한다. upstream 전체 검사는 추가 파일이 없는 고정 원본에서 실행했다.

CLI 관찰 7건은 파일 framing·cursor 재개·자기 echo 제거·원격 IRC 거부, 실제 Ergo의 긴 다중 행 게시물 단일 ID·cursor 재개·서버 재시작 gap이다. API 관찰은 같은 프로세스/재생성의 보류 복구 차이, breaker 초기화, table의 아무 자기 게시에 의한 seal 해제, 가짜 header 처리다. 제한이 그대로 관측되는 것을 성공 조건으로 둔 특성 관찰이며, 제품 결함을 고쳐 통과시킨 회귀 검사가 아니다.

upstream README의 데모는 작성자가 수행한 실제 Claude/Codex 협업 사례이며 Linux는 CI 성공과 실제 협업 미시도를 구분한다.[2] 이번에는 데모를 재현하지 않았다. 실제 모델의 프롬프트 주입 저항, 장기간 대화 품질·토큰 비용, 사람 IRC 조작, 다중 프로필 기존 TUI 복귀, OpenCode 실제 서비스 재시작은 이번 실측 범위 밖이다.

## 11. xsm과 비교

다음 표의 xsm은 위에 고정한 병합본의 소스 계약이다. 제품 전체의 수용 조건 완료를 뜻하지 않는다. 각 구현의 실행 증거는 해당 모듈과 기존 검증 기록으로 따로 확인해야 한다.

| 축 | Parley | 현재 xsm | 참고점 |
|---|---|---|---|
| 진입 | 명시적으로 line에 참가, 하네스별 launch/pump | 훅·MCP 등록과 세션 공개·업무 발견·선택 | 명시적 참여를 보존하되 기존 세션 진입 비용 비교 |
| 사람 참여 | 일반 IRC 클라이언트에서 같은 실시간 채널 | 프로젝트 채널 기록과 직접 메시징이 분리 | 사람이 보는 채널과 깨우기를 연결하는 UX |
| 대상과 공개 범위 | 채널 구성원에게 broadcast, 본문의 nick은 규약 | 세션 주소·프로젝트/연결 범위·공개 후보 | 본문 addressing을 ACL로 오해하지 않기 |
| 발신 표시 | 공통 peer header, 본문 들여쓰기·제어문자 정리 | `provenance.py`의 출처·비신뢰 본문·digest | 구조적 출처와 의미상 승인 구분은 이미 있음 |
| 전송 성공 | stream 게시 ID/time, front별 다른 인계 기준 | 원문·전달 영수증·claim·ACK·outcome 분리 | 게시 영수증을 소비 확인으로 낮춰 합치지 않기 |
| 질문 | 자연어 질문·응답, 별도 request/reply 객체 없음 | `questions.py`의 원 ID와 reply_to·결과 회수 | 채널 대화와 엄격한 요청 결속을 병행 |
| 반복 제어 | line burst/누적 breaker, table seal/cap | `abuse.py`의 관측·제어와 요청별 원장 | 수신 중단 상태와 사용자 재개를 더 잘 표시할 여지 |
| 보존 | IRC RAM history, gate RAM; file은 별도 adapter | 원문·보류·회신·채널 JSONL의 영속 보관 | 사람이 놓친 토론을 정본으로 승격하는 규약 참고 |
| 원격 | 비loopback 거부, 팀/기기 모델 없음 | 기존 SSH 및 선택적 P2P·서명 멤버십 | 로컬 채널 사례를 원격 대체재로 평가하지 않기 |
| 파일·공동 작업 | body-file은 송신 입력. build 소유 규약과 worktree | 자료 사본/digest·접근 경계와 공동 문서 기능 | body-file을 파일 전송/권한 위임으로 오해하지 않기 |
| 역할·워커 | 역할은 사람이 정함. lead/task queue/worker pool 없음 | 일반 세션 통신과 명시적 owned worker 분리 | 상시 역할 협업과 소유 워커를 구별 |
| 운영 | 로컬 서버 + front, 프로젝트 launch 설정 | 로컬 핵심 경로와 선택적 네트워크 서비스 분리 | 서버 장애가 직접 전달과 기록에 주는 영향 구분 |

xsm 근거: [채널](https://github.com/ysys143/xsm/blob/092e8801b0afcbb475bdb0384f546e55064fbf6f/xsm/channel.py), [질문](../../xsm/questions.py), [출처](../../xsm/provenance.py), [반복 제어](../../xsm/abuse.py), [업무 디렉터리](../../xsm/directory.py), [협업 권한](../../xsm/collaboration.py), [자료](../../xsm/materials.py), [수신](../../xsm/receive.py), [원격 멤버십](../../xsm/network_membership.py), [owned worker](../../xsm/owned_requests.py). 전체 완료 여부는 [비교 당시 인계 기록](https://github.com/ysys143/xsm/blob/092e8801b0afcbb475bdb0384f546e55064fbf6f/docs/plan/reason-inspired-adrs/current-handoff.md)과 구분한다.

## 12. 설계 참고와 후속 검증 조건

이 절은 조사자의 해석이며 구현 지시나 기존 ADR 변경이 아니다.

| 발견 | xsm에 주는 의미 | 검증해야 할 조건 |
|---|---|---|
| P01 사람이 같은 채널을 읽고 참여 | [ADR-0005](../adr/0005-channel-thread-store.md)의 채널과 직접 invoke를 이어 보는 UX 검토 | 사람이 보는 원문·직접 메시지·결정 기록의 연결이 유지되는가 |
| P02 전송 순서를 transport 한 곳에 둠 | 여러 입력 경로의 순서 정본을 명확히 하기 | 실시간 수신과 재조회가 중복·역전 없이 합쳐지는가 |
| P03 header/body의 구조적 분리 | 기존 [ADR-0022](../adr/0022-peer-authority-and-abuse-controls.md)의 표시 방어와 비교 | 가짜 header·ANSI·Unicode 분리자에서도 출처가 유지되는가 |
| P04 chair 발언과 도구 승인 분리 | 기존 [ADR-0020](../adr/0020-human-decisions-and-attention.md)의 대상 결속 승인 유지 | 다른 요청·다른 시점의 발언을 승인으로 승격하지 않는가 |
| P05 table 첫 게시 seal | 독립 검토의 최초 답을 보류하는 보조 장치 후보 | 준비 인사·재시작·다른 경로 열람 때 독립성 주장이 거짓이 되지 않는가 |
| P06 line의 burst + 누적 breaker | 단순 건수 외에 빠른 반복과 느린 반복을 구별 | 정상 장기 협업·늦은 backlog·자기 게시가 어떻게 계산되는가 |
| P07 사람 발언만 재개, 시간으로 풀지 않음 | 사용자 재개가 필요한 상태의 명시적 표현 후보 | 승인된 중단과 FYI·과제 대기·연결 장애를 구별하는가 |
| P08 gate와 cursor의 영속성 불일치 | [ADR-0018](../adr/0018-delivery-evidence-and-recovery.md)의 원문 복구를 유지할 이유 | 보류 직후 crash·재개에서 원문과 중단 상태를 함께 회수하는가 |
| P09 CHATHISTORY gap 판정 | 손실을 최신 상태로 오인하지 않는 진단 | 서버 재시작·ring 만료·같은 파일 길이 교체를 실제로 구별하는가 |
| P10 front별 인계 기준 차이 | “전달됨” 표시를 하네스 공통 최저 보장으로 정직하게 표현 | queue exit·notification write·readback·모델 ACK의 차이를 드러내는가 |
| P11 OpenCode stable-ID/readback | 지원 하네스 확장 시 구체 인계 계약 참고 | 응답 유실·취소·재시작·본문 상한에서 중복과 유실이 표시되는가 |
| P12 공유 기록을 먼저 쓰고 poke | 채널·PR·문서의 정본 승격 규약에 참고 | poke 누락 때도 기록에서 일을 복구할 수 있는가 |
| P13 build의 파일 소유 협상 | [ADR-0006](../adr/0006-shared-document-editing.md)의 공동 문서 규약과 비교 | 겹치는 경로·종료한 소유자·기한 초과가 영구 대기를 만들지 않는가 |
| P14 해시로 launch 파일의 소유 증명 | [ADR-0023](../adr/0023-runtime-adapters-and-operability.md)의 설치·제거 안전성 비교 | 사용자 수정·symlink 교체·부분 실패에서 남의 파일을 보존하는가 |
| P15 Codex 작업 폴더 전체 network 허용 | 연결 편의와 권한 범위 비용을 함께 기록 | 실제 sandbox에서 loopback 경로를 더 좁은 권한으로 제공할 수 있는가 |
| P16 프로필과 thread 불일치 경고 | 새 대화·clear·subagent의 수신 대상 결속에 참고 | 경고만으로 양방향 정상 통신처럼 보이지 않는가 |

xsm에 이미 있는 요청·회신·영속 기록·원격 계약은 기존 사실로 비교했다. 이번 발견에서 구현 제안을 도출할 때는 기존 사용자 결정과 수용 조건을 대조해야 한다. 이 노트는 레퍼런스 분석과 재현 자료이며 기존 ADR의 상태를 바꾸지 않는다.

## 출처

모든 upstream 소스 링크는 조사 HEAD에 고정했다. Reddit·README의 사용 경험은 작성자 주장이고, 직접 관찰 결과는 별도 validation 파일에 있다.


[1] 작성자 Reddit 게시물: https://www.reddit.com/r/ChatGPTCoding/comments/1xi5smt/parley_codingagent_sessions_that_collaborate_over/ — 내장 웹 조회로 본문과 직접 저장소 링크 확인. Jina 조회는 403.

[2] Parley README: https://github.com/colinsurprenant/parley/blob/07f445c48723e446fa4d62ed068acfdf53c3f803/README.md

[3] Stream·Deliverer: https://github.com/colinsurprenant/parley/blob/07f445c48723e446fa4d62ed068acfdf53c3f803/internal/stream/stream.go 및 https://github.com/colinsurprenant/parley/blob/07f445c48723e446fa4d62ed068acfdf53c3f803/internal/stream/deliver.go

[4] IRC 주소·연결·계정: https://github.com/colinsurprenant/parley/blob/07f445c48723e446fa4d62ed068acfdf53c3f803/internal/stream/irc/spec.go 및 https://github.com/colinsurprenant/parley/blob/07f445c48723e446fa4d62ed068acfdf53c3f803/internal/stream/irc/conn.go

[5] IRC 이력·multiline: https://github.com/colinsurprenant/parley/blob/07f445c48723e446fa4d62ed068acfdf53c3f803/internal/stream/irc/irc.go 및 https://github.com/colinsurprenant/parley/blob/07f445c48723e446fa4d62ed068acfdf53c3f803/internal/stream/irc/history.go

[6] 실제 서버 설정과 운영: https://github.com/colinsurprenant/parley/blob/07f445c48723e446fa4d62ed068acfdf53c3f803/internal/ergoconf/ircd.yaml 및 https://github.com/colinsurprenant/parley/blob/07f445c48723e446fa4d62ed068acfdf53c3f803/contrib/ergo/README.md

[7] Claude channel·primer: https://github.com/colinsurprenant/parley/blob/07f445c48723e446fa4d62ed068acfdf53c3f803/internal/channel/channel.go 및 https://github.com/colinsurprenant/parley/blob/07f445c48723e446fa4d62ed068acfdf53c3f803/internal/primer/primer.go

[8] Codex front: https://github.com/colinsurprenant/parley/blob/07f445c48723e446fa4d62ed068acfdf53c3f803/internal/codex/codex.go

[9] OpenCode front·인계·서비스 검증: https://github.com/colinsurprenant/parley/tree/07f445c48723e446fa4d62ed068acfdf53c3f803/internal/opencode — `opencode.go`, `queue.go`, `client.go`, `service.go`, `history.go`, `bound.go`, `ident.go`.

[10] 상태 저장과 file adapter: https://github.com/colinsurprenant/parley/tree/07f445c48723e446fa4d62ed068acfdf53c3f803/internal/state 및 https://github.com/colinsurprenant/parley/blob/07f445c48723e446fa4d62ed068acfdf53c3f803/internal/stream/file/file.go

[11] table 프로토콜: https://github.com/colinsurprenant/parley/blob/07f445c48723e446fa4d62ed068acfdf53c3f803/skills/parley-table/SKILL.md

[12] build 프로토콜: https://github.com/colinsurprenant/parley/blob/07f445c48723e446fa4d62ed068acfdf53c3f803/skills/parley-build/SKILL.md

[13] line 프로토콜·운영: https://github.com/colinsurprenant/parley/blob/07f445c48723e446fa4d62ed068acfdf53c3f803/skills/parley-line/SKILL.md 및 https://github.com/colinsurprenant/parley/blob/07f445c48723e446fa4d62ed068acfdf53c3f803/docs/line.md

[14] doctor 검증 범위: https://github.com/colinsurprenant/parley/blob/07f445c48723e446fa4d62ed068acfdf53c3f803/internal/doctor/doctor.go 및 https://github.com/colinsurprenant/parley/blob/07f445c48723e446fa4d62ed068acfdf53c3f803/internal/doctor/live_codex.go

[15] 준비·소유·종료: https://github.com/colinsurprenant/parley/tree/07f445c48723e446fa4d62ed068acfdf53c3f803/cmd/parley — `line_add.go`, `line_drop.go`, `table_new.go`, `table_end.go`, `build_new.go`, `build_end.go`, `gitwt.go`, `setup.go`, `codexroots.go`.

[16] 스킬 설치·제거: https://github.com/colinsurprenant/parley/blob/07f445c48723e446fa4d62ed068acfdf53c3f803/skills/install.sh

[17] 의존성·CI·라이선스: https://github.com/colinsurprenant/parley/blob/07f445c48723e446fa4d62ed068acfdf53c3f803/go.mod 및 https://github.com/colinsurprenant/parley/blob/07f445c48723e446fa4d62ed068acfdf53c3f803/.github/workflows/ci.yml 및 https://github.com/colinsurprenant/parley/blob/07f445c48723e446fa4d62ed068acfdf53c3f803/LICENSE
