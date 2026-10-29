# Reason Network 역공학과 xsm 반영 근거

> 후속 조사 반영: 두 바이너리의 시간 제한 없는 Ghidra 자동 분석을 완료하고, 배포 모듈 장애 주입·공개 E2E 7종을 수행했다. 관찰 범위와 미검증 실환경 경로는 [후속 실행](reason-network/followup-findings.md)·[잔여 의문](reason-network/residual-unknowns.json)에 구분한다.

- 조사일: 2026-10-24
- 문서 목적: Reason의 구현과 관찰된 동작을 xsm에 반영할 Proposed ADR의 근거로 남긴다.
- 질문: Reason에서 편했던 흐름과 내부 복구·권한·수명 계약을 어떻게 xsm의 기존 기능과 사용자 결정에 맞게 구현할 것인가?

## 요약

이 조사는 공개 엔진 36개 Rust 모듈과 2개 TypeScript 어댑터의 책임·주요 호출 경로, 설치 스크립트·테스트·배포 메타데이터를 대조했다. 설치된 비공개 CLI의 Mach-O 바이너리에서 network-command·ask-worker·엔진 클라이언트·가입·호스팅 relay의 JavaScript 6개 핵심 모듈과 인증·SDK 구현 2개를 추출해 분석했다. 워커·인증 원본 모듈은 격리 실행도 수행했다. 공개 소스가 없다는 사실과 배포물의 프로그램 텍스트를 읽을 수 있다는 사실을 구분한다. 서버측 로그인·호스팅 MCP 내부는 확보하지 못했다.[1][2][16]

후속 사용자 지시로 Ghidra 12.2·JDK 25를 설치하고 누락된 macOS ARM64 decompiler·Sleigh를 같은 버전 소스에서 빌드했다. CLI의 여섯 JS 영역은 Ghidra 메모리의 비실행 __bun 블록과 해시까지 일치했다. CLI 8개·엔진 12개의 선택 함수 의사코드를 확보했고, 엔진의 팀 밖 연결 거부 메시지·403 코드·길이 전달 및 PostToolUse 참조 경로를 대조했다. 초기 600초 시간 초과 뒤 시간 제한 없이 재실행했고, CLI 1,846.864초·엔진 685.915초에 기본 자동 분석·전체 함수 목록 추출·저장을 완료했다. 이는 프로그램 전체의 의미 동등성이나 서버 복원을 입증하지 않는다.[27][28]

이전 실제 비교는 CLI 0.2.557·엔진 0.12.10 표본이다. 현재 공개 엔진은 v0.12.11로 고정했고 두 버전의 결과를 섞지 않았다. 0.12.10은 195개, 0.12.11은 202개의 upstream 검사가 통과했다. 별도 상태 폴더와 합성 세션으로 최신 엔진의 로컬 IPC 14개와 MCP 5개 관찰을 수행했다. 이 성공이 물리 머신 간 연결이나 실제 하네스 전체의 성공을 뜻하지 않는다. 후속 E2E는 구버전 시험체 정정 뒤 309 통과·1 실패이며, 워커 15개·인증 12개·두 엔진의 알림 각 4개 관찰 조건도 대조했다.[19][20][21][24][29]

발견 전체는 [추적표](reason-network/README.md)의 R01–R43과 [coverage.json](reason-network/coverage.json)에 연결한다. 계약 단위로 0015–0023의 ADR 9개를 작성했다. 모두 Proposed이며 기존 Accepted 결정을 변경하지 않는다. 기존에 있던 N:N·수신 안내·재전송·원문 결정 기록을 새 기능처럼 취급하지 않는다.[17][18]

## 출처와 버전을 고정한 방법

| 대상 | 고정한 버전·식별자 | 확인 범위 |
|---|---|---|
| 이전 비교 및 설치 엔진 | v0.12.10, `72ca2b3fb36d6e3cbfa44aa82c68d27aafe5e690` | 이전 실제 통신, 이번 별도 소스 빌드·검사 |
| 공개 최신 엔진 | v0.12.11, `b3557ff454cd26a04c2a18804ba83ae5db8b119d` | 현재 소스·빌드·격리 IPC/MCP |
| 설치 Reason CLI | 0.2.557, SHA `00a94cc9c119a3ab40e7d8454cbf896f99f4cc59e53df721c3de8b8ab98dd7c9` | 도움말·정적 배포물·이전 실제 실행 |
| xsm | 0.4.20, `b29b39ce65c594e88e4b84684724fe02553ee2fc` | 현재 코드와 기존 ADR·원시 비교 증거 |
| 계정·호스팅 MCP 서버 | 내부 구현 미확보 | 공식 설명과 공개 엔진의 클라이언트 경계만 확인 |

원격 Git refs의 annotated tag와 peeled commit을 각각 확인했다. 검색 캐시에 나타난 예전 릴리스 번호로 최신 버전을 정하지 않았다. 두 소스 트리의 파일·SHA는 [manifest](reason-network/source-manifest.json)에 있다. Cargo.lock의 실제 버전은 iroh 1.4.1, rmcp 3.5.1, rusqlite 0.40.2다. DESIGN의 iroh 1.3 표기는 현재 잠금 파일과 다르므로 구현 의존성은 잠금 파일을 기준으로 했다.[2][24]

설치된 엔진은 공식 v0.12.10 macOS arm64 릴리스 아카이브의 체크섬을 검증한 뒤 내부 바이너리와 바이트 단위로 대조했다. 두 바이너리 SHA는 `6ac4bb4837469867edc2dba3cbbd6e4dd9fb18ad0389db69ff6ef21683317a44`로 같았다. 이는 설치물과 공식 배포물의 일치이며, 같은 소스에서의 완전한 재현 빌드 증명과는 다르다.[24]

공식 설명은 엔진만 MIT OR Apache-2.0이며 CLI는 공개 소스가 아니라고 구분한다. NOTICE는 tincan에서의 출처를 남긴다. 이 조사에서는 제3자 제품 코드를 xsm에 수입하지 않았다. 향후 코드 재사용은 배포물 분석과 별개로 라이선스·NOTICE·수정 이력을 보존해야 한다.[1][2]

## 전체 모듈과 주요 호출 경로

모듈별 역할과 주요 진입점은 [source-map.md](reason-network/source-map.md)에 있다. 파일 목록을 만들었다는 것만으로 모든 분기를 검증했다고 주장하지 않는다. 핵심 계약은 아래 경로를 실제 함수와 맞췄고, 실행 여부를 별도로 표시했다.

| 사용자 또는 에이전트 동작 | 실제 경로 | 확인 |
|---|---|---|
| MCP 도구 호출 | mcp의 clientInfo·호출 meta 해석, session_for, 등록 또는 기존 key 재사용, 로컬 Link 요청 | 소스와 합성 MCP |
| 상대 찾기 | directory.local_rows가 훅·프로세스·네이티브 레지스트리·git·doing을 결합하고 who가 필터·원격 presence를 합침 | 소스·기존 실제 목록·격리 목록 |
| 메시지 송신 | mail.send가 발신자·대상·그룹·루프를 검사하고 store에 보관한 뒤 deliver 또는 원격 outbox에 넣음 | 로컬 IPC와 upstream 검사 |
| 하네스에 전달 | deliver가 socket·CLI·hook·pull 경로를 선택하고 확인 또는 실패 뒤 미독·능력 상태를 갱신 | 소스와 이전 실제 통신 |
| 수신·대기 취소 | Inbox peek, polling·in_flight, Delivered 또는 StopWaiting, 미확인 메시지 회수 | 소스·격리 IPC |
| 사용자 결정 | ask가 about 원문을 찾아 표시하고 중복 대기를 합침. 응답 후 원 요청에 서명된 Approval 또는 늦은 답 전달 | 소스·서명/파서 검사. 실제 OS UI 경쟁은 미실행 |
| 다른 머신에 연결 | join_team·서명 상태 검증·iroh endpoint·활성 멤버 gate·presence·메시지와 ack | 소스·upstream 단위 검사·논리 머신 E2E. 새 물리 머신 시험은 미실행 |
| 설치·재시작 | setup 병합·백업·서비스, Link 재연결·재등록, paths/migrate의 이전 경로 호환 | 소스·설치 stand-in 검사·격리 데몬 재시작 |
| CLI 질문·serve | 배포물의 임시 ask 우편함·동기 답 회수, 발신자별 Claude 풀 또는 요청별 Codex exec, 복구 저널 | 배포물 정적 분석·원본 모듈 격리 실행·이전 실제 기록 |

로컬 IPC는 줄 단위 JSON이고 요청 ID와 Reply ID를 연결하며 등록 연결에는 이벤트를 보낸다. 긴 Inbox·Ask가 다른 요청을 막지 않도록 요청별 작업으로 처리한다. 네트워크는 길이 접두 JSON 프레임의 Hello·State·Presence·Msg·Ack와 고정 ALPN을 사용한다. 로컬 API와 네트워크 봉투를 같은 포맷으로 설명하면 안 된다.[3][15]

## 참여·자격·업무 권한

Reason의 새 저장소 참여가 부드러웠던 이유는 이미 승인한 팀 가입 안에서 등록 세션을 바로 고르기 때문이다. 머신 가입의 넓은 범위를 앞서 선택한 비용이 있다. default accept·폴더 제외·share_paths·share_unmanaged를 함께 봐야 한다. 특히 로컬 자기 세션을 발견하는 경로와 다른 머신에 presence로 공개하는 경로의 범위는 다르다.[7][14][18]

머신 키 인증, 초대 소지, 계정 이름 증명, 멤버십, 작업 접근 권한은 서로 다른 사실이다. Reason은 계정 증명을 로컬 공개키로 확인하며 만료된 증명도 이름 소유 판정에서는 별도로 취급한다. 현재 verified 표시의 만료와 멤버십을 혼동하지 않는다. any-member 초대·제명은 신뢰하는 팀 모델이며 악의적인 기존 멤버까지 제어하는 기업 관리 모델로 확대하지 않는다.[14]

xsm의 프로젝트·폴더 연결·세션 도달 허용은 같은 목적을 다른 범위 단위로 표현한다. 실제 승인 누락은 범위 검사의 정당성과 별개의 수집·복구 실패다. 0015는 의도·확인·적용·보관 요청 전송을 결속하고 기본 연결 수명은 미결로 남긴다. 기존 사용자 결정은 쉬운 연결·한쪽 의사 표현·불필요한 핑퐁 방지를 이미 요구한다.[17][18]

## 에이전트 인터페이스와 업무 디렉터리

Reason MCP는 도구 사용 지침을 skill 원문에서 제공하고, 실제 Claude inbox가 확인된 환경에서 수신함 도구를 숨긴다. Codex라는 이유만으로 숨기지는 않는다. 반면 send_message에는 wake/FYI 인자가 없고 항상 wake=true다. 도구 수가 적다는 사실과 모든 협업 의도를 표현한다는 사실은 다르다.[4]

업무 디렉터리는 repo/branch·busy/idle 지속 시간·doing·수신 등급을 표시한다. doing은 제목과 현재 할 일에서 추출하고 변경분을 읽는다. 실제 업무 선택의 편의는 관찰했지만 요약 정확도·공개 범위 적절성은 전수 검증하지 않았다. xsm은 이미 이름으로 보낼 수 있고 native 이름·홈·ref를 보존한다. 추가할 가치는 업무 선택 정보와 신선도·능력 표시다.[7][8][17][18]

Reason의 질문 명령은 실제 답까지 한 호출에 돌려줬다. 배포물은 임시 ask 우편함과 회신 상관관계로 이를 구현한다. ID 이외에 발신 주소로도 답을 고르는 대체 경로가 있어, xsm의 엄격한 request/reply 결속을 약화시키며 복사할 이유는 없다. xsm의 전달 영수증과 task outcome을 보존하면서 목적별 인터페이스를 추가하는 제안이 0016이다.[16][17][18]

## 대화·이름·홈과 워커의 수명

Reason은 네이티브 대화 ID가 있는 세션의 이름을 기억 기간 동안 보존하고, proc 기반 주소는 재시작한 다른 프로세스에 이름과 미독을 넘길 수 있다. 사람의 우편함은 별도 수명이다. 다른 머신에 나타난 같은 대화가 이전 머신의 미독까지 이동시키는 것은 아니다. 이름 지속성·프로세스 지속성·대화 지속성을 나눠야 한다.[6][11]

clientInfo는 상속 환경보다 우선하고 공유 MCP는 매 호출 sessionId/threadId 등을 사용한다. 그런데 파일 루트는 별도로 프로세스 cwd에서 구한다. 합성 MCP에서는 B 호출의 B 폴더가 식별됐음에도 B의 정상 첨부가 A 루트 기준으로 거절되는 불일치를 재현했다. 이 구성에서의 오류는 확인했지만 실제 하네스의 공유 프로세스 배치와 정보 유출까지 확인한 것은 아니다.[4][9][21]

CLI serve의 Claude는 발신자별 warm 프로세스와 직렬 큐·유휴 회수를 사용한다. Codex는 요청마다 새 exec다. Claude 기본 실행의 strict MCP·훅 비활성화는 이전 기본 serve가 Reason 도구를 찾지 못한 표본과 부합한다. 후속 원본 모듈 실행에서 이 동작과 6명이 모두 작업 중일 때 새 발신자 워커가 즉시 회수되는 조건을 확인했다. 같은 주소의 재사용을 독립 검토 격리나 같은 대화 기억 보장으로 취급하지 않는다.[16][18][29]

## 전달 증거·취소·재시도·보존

store는 메시지 ID로 중복 저장을 방지하고, 우편함·원격 outbox·세션 이름을 보관한다. mail은 전달 중인 메시지의 중복 노출을 일정 시간 억제하고 확인이 없으면 회수한다. Link는 재접속·재등록을 수행하지만 확인 불명인 임의 요청을 조용히 재실행하는 보장과는 다르다.[5][10][11]

격리 IPC에서 peek 후 미독 유지, Delivered 확인 후 미독 해소, StopWaiting 후 빈 대기 종료, FYI의 wake=false 저장, 데몬 재시작 뒤 이름·미독 보존을 확인했다. 이는 로컬 프로토콜의 관측이다. FYI가 실제 모델의 다음 자연 시점에서 소비됐다는 증거는 아니다. 기존 실제 FYI 표본은 나중에도 unread로 남았다.[20][18]

Reason의 실제 Codex 송신은 native queue 성공 전에 낙관적인 문구를 반환했고 약 26분 뒤에도 미독이었다. 같은 스레드의 xsm은 분석·회신에 성공했다. 대상 CODEX_HOME 누락은 공개 경로와 맞는 원인 후보지만 실제 데몬 환경을 확보하지 않아 단일 원인으로 확정하지 않는다. 상태 표현은 능력 예측과 이번 시도의 증거를 구분해야 한다.[9][10][18]

serve 배포물은 업무 요청을 저널에 넣은 뒤 ack하고, 답을 저장한 뒤 송신을 재시도하며 재시작 시 보관 답을 재사용한다. 후속 격리 프로세스 종료·재시작에서 이미 저장된 답의 재송신과 새 모델 실행 생략을 확인했다. 가짜 업무 부작용 뒤 답 저장 전 종료 조건에서는 부작용이 두 번 발생했다. 메시지 중복 제거가 업무의 exactly-once를 입증하지는 않는다.[16][29]

xsm에도 수신 영수증·unknown 조정·동일 ID 재전송·본문 대조·typed outcome이 있다. 0018은 이를 제거하지 않고 실제 증거·대기 취소·복구·보존의 일관성을 제안한다. Reason의 SQLite를 사용한다는 이유만으로 xsm 저장 형식을 바꾸는 결정을 내리지 않았다.[17]

## 자료와 사람의 판단

첨부는 작은 텍스트 사본을 본문과 함께 전달한다. 수신 측이 만든 로컬 디렉터리·파일명 검사·양쪽 용량 검사·보류 중 보존·정리를 갖고, files 능력이 없는 상대에는 가능한 본문 대체 또는 명시적 미지원을 반환한다. 0019는 이 자료 운반을 xsm의 공동 문서 이력·정본과 구분한다.[13][17]

ask는 사용자가 실제로 본 요청과 질문을 원 요청 ID·답·시각에 결속한다. 같은 질문은 기존 창을 기다리고 늦은 답을 회수한다. 머신 서명은 그 머신이 답을 기록했다는 증거이며 같은 uid의 모든 프로그램에 대한 방어가 아니다. 미응답·명시적 거부·창 닫기·표시 실패를 구분할 필요가 있다.[12][14]

notify는 사람의 주의가 필요한 경우의 별도 선택이다. 빈도와 오래된 알림을 조절하고 승인창은 키보드 포커스를 빼앗지 않게 만든다. 격리 시험에서는 OS 명령 완료 전에 표시 성공을 응답하고 나중에 실패해도 빈도 제한을 소모했다. 시스템 호출 접수·OS 호출 성공·사람 확인은 서로 다른 증거다. xsm도 elicitation·사용자 결정 원문·worker 승인이 이미 있으므로 0020은 공통 출처·대기·중복·복구 계약을 제안한다.[12][17][29]

## 원격·오용 제어·설치

Reason의 iroh P2P는 VPN을 설치해 일반 네트워크를 연결하는 방식이 아니다. LAN·NAT·릴레이·프록시와 자체 릴레이 경로를 관리하고 멤버십을 검사한다. 0.12.11의 고정 UDP 포트·대체 포트 진단도 검토했다. 0021은 SSH 개선·선택적 P2P·공개 Reason 백엔드 재사용·사설 VPN을 같은 수용 검사로 대조하도록 제안한다. 핵심 로컬 경로의 필수 데몬 비의존과 기존 SSH 결정은 아직 유효하다.[15][24][17]

본문·목록·오류의 예약 표시 위조를 렌더링에서 막고 반복·속도·그룹 제한을 둔다. 격리 IPC에서도 가짜 승인 프레임이 본문에서 권위를 얻지 못함과 쌍별 한도를 관측했다. 정상 검토에 적절한 한도인지 검증한 것은 아니다. 0022는 관계 토폴로지를 제한하는 대신 권위·권한·행동을 각각 검사하며 Reason의 그룹 금지를 그대로 채택하지 않는다.[10][20]

setup은 백업·병합·원자적 교체·설정 권한 유지와 설치 소유자를 다룬다. 신규 MCP·훅 등록이 이미 떠 있는 세션에 즉시 적용된다는 보장은 없다. 하네스별 버전·프로필·호스트 정책을 실제로 실행해야 한다. 0023은 설치 성공과 첫 실제 왕복을 분리하며 위험한 옵션의 묵시적 허용을 제안하지 않는다.[16][17][18][22]

가입 클라이언트는 로그인·엔진 가입·하네스 설정의 완료 단계를 구분하고, poll 식별자와 lock으로 기존 흐름을 이어받는다. 원래 대기가 끝나도 별도 finisher가 가입을 마무리할 수 있다. 계정 서버의 팀 등록 실패와 이미 성립한 네트워크의 사용을 분리하는 경로도 있다. 이 장애 복구는 정적으로 확인했고 인증 구현 모듈은 가짜 HTTP·자격 저장 경로에서 실행했다. 실제 가입 재시험은 하지 않았다. pending 파일의 flow 교체 조건에서는 이전 결과를 저장하는 틈도 관측해, xsm에는 저장 직전 요청 결속 재검사를 제안한다.[16][29]

업데이트에서는 standalone 엔진과 CLI가 핀한 엔진을 구분하고 기존 개발자 팀 서명 유지 검사가 있다. 상태 이동은 이전 경로·소켓을 연결해 실행 중인 세션과 공존한다. 체크섬·서명·배포처 신뢰는 서로 다른 증거다. 자동 업데이트의 기본값을 xsm에 그대로 옮기는 결정은 하지 않았다.[16]

## xsm 구현으로 잇는 순서

9개 ADR은 기능별 감상 목록보다 되돌리기 어려운 계약 단위로 묶었다. 구현 순서는 아래처럼 제안한다. 채택과 기본값은 사용자 결정이며, 기존 Accepted ADR의 효력은 유지한다.

| 순서 | 연결할 ADR | xsm에서 바꿀 실제 경로 | 성공을 판단할 증거 |
|---|---|---|---|
| 1 | 0015·0020 | 연결 의도·자격 해석 → 사용자 판단 수집 → 같은 요청 적용·보관 송신 | 기존 비동기 승인 표본이 연결 적용까지 이어짐. 사용자가 project·ref를 외우거나 같은 승인을 반복하지 않음 |
| 2 | 0017·0016·0018·0023 | 호출자 홈·대화·폴더를 보존한 디렉터리와 질문·회신, 전달 단계·재접속·설치 능력 진단 | 같은 저장소·새 저장소·일반 Codex 다중 홈에서 실제 왕복. FYI의 후속 소비와 과부하·회신 복구를 별도 확인 |
| 3 | 0019·0022 | 업무 자료 사본·첨부 루트와 동료 입력의 권위·오용 제어 | 정상 N:N 검토는 유지하고 위조 권위·루프·잘못된 호출자 자료만 구별 |
| 4 | 0021 | 기존 SSH와 선택적 P2P의 도달·멤버십·릴레이 진단 비교 | 허가된 물리 머신에서 직접·릴레이·오프라인·제명 후 재접속의 같은 수용 검사 |

Reason에서 가장 크게 가져올 것은 연결 의도를 실제 참여로 이어 주는 흐름, 호출자가 따로 외우지 않는 문맥 결속, 요청·답의 복구 책임, 현재 관측에 맞는 능력 표현이다. xsm에 이미 있는 이름·N:N·영수증·사용자 원문 기록을 새로 발명하거나 부모 전용 통신으로 바꾸는 계획은 아니다. 풀 상한·그룹 금지·데몬 필수화·자동 업데이트 같은 선택은 좋은 흐름과 별도로 판단한다.[17][18][29]

## 실행 결과와 한계

| 실행 | 실제 결과 | 입증하지 않는 것 |
|---|---|---|
| 0.12.10 upstream 검사 | 193 unit + 2 install = 195 통과 | 실제 모든 하네스·물리 머신 동작 |
| 0.12.11 upstream 검사 | 200 unit + 2 install = 202 통과 | 별도 E2E의 통과를 대신하지 않음 |
| 격리 IPC | 14개 관찰 조건 충족 | 네이티브 모델이 이해·실행했다는 보장 |
| 합성 공유 MCP | 5개 관찰 조건 충족. 첨부 루트 불일치를 의도한 조건에서 확인 | 모든 MCP 구성의 오류·정보 유출 |
| Ghidra 후속 분석 | 초기 선택 C 20개·JS 6개 메모리 해시 일치. 이후 두 대상의 기본 자동 분석·전체 함수 목록·저장 완료 | native 의미 동등성·전체 기능 실행 성공 |
| 공개 E2E 7종 | 최초 306 통과·4 실패. 구버전 시험체 정정 후 suite별 309 통과·1 실패 | 한 호스트의 논리 머신·가짜 하네스이며 실제 물리 원격·모델 검증 아님 |
| 원본 CLI 모듈 격리 실행 | 워커 15개·인증 12개 관찰 조건 충족. 과부하·요청 결속의 조건부 결함 포함 | 전체 CLI·실제 계정 서비스 검증 |
| 알림 장벽·실패 주입 | 공식 0.12.10과 debug 0.12.11에서 각각 4개 관찰 조건 충족 | 실제 사람이 보았음 |
| 이전 실제 공존 비교 | 같은 저장소 양쪽 성공, Reason 새 저장소 왕복, xsm 일반 Codex 성공·Reason 실패 | xsm 연결 후 구간, 원격·장시간 안정성 우열 |

최초 offline 빌드 준비는 cliclack 캐시 부재로 exit 101이었다. 의존성을 받아 최신 전체 검사를 통과했고 baseline도 별도 검사했다. 실패 기록을 성공으로 덮지 않았다.[19]

물리 머신·서로 다른 NAT 환경, 전체 OS 승인 UI 경쟁, 실제 자식 모델을 포함한 CLI 통합 장애 복구, 하네스별 실제 공유 MCP 배치는 아직 실행하지 않았다. 원본 모듈의 일부 장애 지점·재기동은 후속 격리 실행으로 대조했다. 수행 주체는 이번 조사 코디네이터(2026-10-24)이며, 현재 작업은 ADR 작성이다. 이 항목들은 해당 ADR의 수용 검사로 남고 미완 실환경 경로로 표시한다. 향후 검사를 생략해도 된다는 사용자 승인을 받은 것은 아니다. 원격 검증에는 허가된 시험 머신·팀과 런타임 구성이 필요하다. 연결 후 비교가 미완인 이전 S5도 유지했다. 공개 E2E의 알림 로그 실패도 두 번 재현한 그대로 보존했고, 후속 파일에는 기대한 내용이 생겼음을 대조했다.[18][23][29]

새로 실행한 데몬·MCP는 별도 상태 폴더의 합성 세션만 사용했고 종료를 확인했다. xsm 제품 코드·실제 팀 연결·권한 규칙은 변경하지 않았다. 기존 평가 기록의 오류나 실패도 지우지 않았다. 전체 사용자 홈의 바이트 불변을 검증했다고 주장하지 않는다.

## REAP·REA의 적용 가능성

사용자가 제시한 REAP는 프롬프트 모음이다. 기능별 호출·자료 흐름 추적, 동작 명세와 재구현 비교, 버전 차이, 미확인 항목 감사가 이번 조사에 맞는다. REA는 JavaScript 관계 분석과 네이티브 도구 연결을 제공한다. 처음 검토할 때 없던 Ghidra는 후속 지시에 따라 설치해 직접 headless 분석에 사용했다. REA·Hopper 설치나 새 MCP 등록은 하지 않았다. 실제 native 결과와 도구 한계는 [후속 분석](reason-network/ghidra-native.md)에 분리했다.[25][26][27]

## 출처

[1] [Reason Network 공식 공개 범위·FAQ](https://reasonmachines.com/network).

[2] 고정 엔진 [Cargo.toml](https://github.com/reason-machines/reason-network/blob/b3557ff454cd26a04c2a18804ba83ae5db8b119d/Cargo.toml), [Cargo.lock](https://github.com/reason-machines/reason-network/blob/b3557ff454cd26a04c2a18804ba83ae5db8b119d/Cargo.lock), [NOTICE](https://github.com/reason-machines/reason-network/blob/b3557ff454cd26a04c2a18804ba83ae5db8b119d/NOTICE).

[3] 로컬 프로토콜 [proto.rs](https://github.com/reason-machines/reason-network/blob/b3557ff454cd26a04c2a18804ba83ae5db8b119d/src/proto.rs), [daemon/mod.rs](https://github.com/reason-machines/reason-network/blob/b3557ff454cd26a04c2a18804ba83ae5db8b119d/src/daemon/mod.rs).

[4] [MCP 구현](https://github.com/reason-machines/reason-network/blob/b3557ff454cd26a04c2a18804ba83ae5db8b119d/src/mcp.rs).

[5] [클라이언트·재접속](https://github.com/reason-machines/reason-network/blob/b3557ff454cd26a04c2a18804ba83ae5db8b119d/src/client.rs).

[6] [세션·이름 수명](https://github.com/reason-machines/reason-network/blob/b3557ff454cd26a04c2a18804ba83ae5db8b119d/src/daemon/sessions.rs).

[7] [디렉터리](https://github.com/reason-machines/reason-network/blob/b3557ff454cd26a04c2a18804ba83ae5db8b119d/src/daemon/directory.rs), [기본 정책](https://github.com/reason-machines/reason-network/blob/b3557ff454cd26a04c2a18804ba83ae5db8b119d/src/config.rs).

[8] [doing 추출](https://github.com/reason-machines/reason-network/blob/b3557ff454cd26a04c2a18804ba83ae5db8b119d/src/doing.rs).

[9] [발신자 식별](https://github.com/reason-machines/reason-network/blob/b3557ff454cd26a04c2a18804ba83ae5db8b119d/src/agent.rs), [Codex 턴](https://github.com/reason-machines/reason-network/blob/b3557ff454cd26a04c2a18804ba83ae5db8b119d/src/codex.rs), [훅](https://github.com/reason-machines/reason-network/blob/b3557ff454cd26a04c2a18804ba83ae5db8b119d/src/hook.rs).

[10] [송수신·오용 제한](https://github.com/reason-machines/reason-network/blob/b3557ff454cd26a04c2a18804ba83ae5db8b119d/src/daemon/mail.rs), [프레임 렌더링](https://github.com/reason-machines/reason-network/blob/b3557ff454cd26a04c2a18804ba83ae5db8b119d/src/render.rs).

[11] [우편함·outbox·세션 저장소](https://github.com/reason-machines/reason-network/blob/b3557ff454cd26a04c2a18804ba83ae5db8b119d/src/store.rs).

[12] [사용자 질문](https://github.com/reason-machines/reason-network/blob/b3557ff454cd26a04c2a18804ba83ae5db8b119d/src/daemon/ask.rs), [알림](https://github.com/reason-machines/reason-network/blob/b3557ff454cd26a04c2a18804ba83ae5db8b119d/src/daemon/notify.rs).

[13] [첨부 검증·보존·구버전 대체](https://github.com/reason-machines/reason-network/blob/b3557ff454cd26a04c2a18804ba83ae5db8b119d/src/files.rs).

[14] [멤버십](https://github.com/reason-machines/reason-network/blob/b3557ff454cd26a04c2a18804ba83ae5db8b119d/src/team.rs), [계정 증명](https://github.com/reason-machines/reason-network/blob/b3557ff454cd26a04c2a18804ba83ae5db8b119d/src/proof.rs), [가입·제명](https://github.com/reason-machines/reason-network/blob/b3557ff454cd26a04c2a18804ba83ae5db8b119d/src/daemon/teamops.rs).

[15] [P2P·릴레이](https://github.com/reason-machines/reason-network/blob/b3557ff454cd26a04c2a18804ba83ae5db8b119d/src/net.rs), [릴레이 목록 검증](https://github.com/reason-machines/reason-network/blob/b3557ff454cd26a04c2a18804ba83ae5db8b119d/src/relays.rs).

[16] [설치](https://github.com/reason-machines/reason-network/blob/b3557ff454cd26a04c2a18804ba83ae5db8b119d/src/setup.rs), [경로 이동](https://github.com/reason-machines/reason-network/blob/b3557ff454cd26a04c2a18804ba83ae5db8b119d/src/paths.rs), [업데이트](https://github.com/reason-machines/reason-network/blob/b3557ff454cd26a04c2a18804ba83ae5db8b119d/src/daemon/update.rs), [CLI 배포물 분석](reason-network/cli-analysis.md).

[17] 현재 xsm [모듈](../../xsm/), [의도](../../INTENT.md), [기존 ADR](../adr/README.md). 고정 코드 식별자는 [xsm b29b39c](https://github.com/ysys143/xsm/tree/b29b39ce65c594e88e4b84684724fe02553ee2fc)이며 상세 코드 대응은 [coverage.json](reason-network/coverage.json).

[18] 이전 [실사용 근거](../../deliverables/reason-workflow-experience/evidence.json), [공존 비교 근거](../../deliverables/xsm-reason-live-comparison-2026-10-23/evidence.json), [설치 평가](../../deliverables/reason-network-evaluation-2026-10-23.md), [양방향 비평 검증](../../deliverables/adversarial-cross-review-2026-10-23/verification.json). 분석한 엔진 식별자는 [v0.12.10](https://github.com/reason-machines/reason-network/tree/72ca2b3fb36d6e3cbfa44aa82c68d27aafe5e690)이며 실행 결과의 출처는 앞의 로컬 기록이다.

[19] 이번 [빌드·upstream 검사 결과](reason-network/test-results.json). 검사 대상은 [고정 upstream 코드](https://github.com/reason-machines/reason-network/tree/b3557ff454cd26a04c2a18804ba83ae5db8b119d)이며 실제 종료 코드·통과 수는 로컬 실행 기록에서 확인한다.

[20] 이번 [격리 IPC 관측](reason-network/ipc-probes.json), [재현 스크립트](reason-network/probe_engine.py). 관측한 API의 정의는 [proto.rs](https://github.com/reason-machines/reason-network/blob/b3557ff454cd26a04c2a18804ba83ae5db8b119d/src/proto.rs)다.

[21] 이번 [합성 MCP 관측](reason-network/mcp-probes.json), [재현 스크립트](reason-network/probe_mcp.py). 관측 대상은 [mcp.rs](https://github.com/reason-machines/reason-network/blob/b3557ff454cd26a04c2a18804ba83ae5db8b119d/src/mcp.rs)이며 실제 하네스의 배치 검증과 구분한다.

[22] [공식 에이전트 설치 안내](https://reasonmachines.com/network/skill.md).

[23] upstream [E2E 스크립트](https://github.com/reason-machines/reason-network/tree/b3557ff454cd26a04c2a18804ba83ae5db8b119d/tests/e2e). 실행 suite 7종과 proofs.py 도우미 1개를 구분했다. 7종 모두 수행한 결과는 [후속 기록](reason-network/e2e-results.json)에 있다.

[24] [버전 차이](reason-network/version-delta.md), [소스 manifest](reason-network/source-manifest.json), [설치 엔진과 공식 배포물 대조](reason-network/installed-engine-release-check.json), [고정 두 버전의 upstream 차이](https://github.com/reason-machines/reason-network/compare/72ca2b3fb36d6e3cbfa44aa82c68d27aafe5e690...b3557ff454cd26a04c2a18804ba83ae5db8b119d).

[25] [REAP 원본 프롬프트](https://github.com/JoasASantos/REA-Prompts).

[26] [REA 공식 저장소](https://github.com/morluto/rea), [조사 워크플로](https://github.com/morluto/rea/blob/main/docs/mcp-prompts.md). 소개 계기는 [사용자가 제시한 글](https://discuss.pytorch.kr/t/reap-rea-55-rea/12255)이며 기술 판단은 원본 문서와 대조했다.

[27] [Ghidra 후속 분석](reason-network/ghidra-native.md), [설치·복구 기록](reason-network/ghidra-install.json), [native 근거](reason-network/ghidra-native-evidence.json), [수집 검증](reason-network/ghidra-validation.json), [수집 스크립트](reason-network/NativeEvidence.java). 도구 식별자는 [Ghidra 12.2 공식 release](https://github.com/NationalSecurityAgency/ghidra/releases/tag/Ghidra_12.2_build)이며 대상 코드는 [Reason 엔진 0.12.10](https://github.com/reason-machines/reason-network/tree/72ca2b3fb36d6e3cbfa44aa82c68d27aafe5e690)과 기존 SHA의 CLI 0.2.557이다.


[28] [시간 제한 없는 Ghidra 전체 자동 분석 메타데이터](reason-network/full-native-analysis.json).

[29] [원본 모듈·알림·공개 E2E 후속 실행](reason-network/followup-findings.md), [워커](reason-network/worker-probes.json), [인증](reason-network/auth-probes.json), [E2E](reason-network/e2e-results.json).
