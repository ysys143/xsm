# 공개 호스트 프로토콜 구현 기록

상태: **미완**. 전체 계획 완료·추가 런타임 지원·릴리즈를 주장하지 않는다.

## 확정 기준

- 공개 명세와 적합성 검사기로 독립 구현 가능해야 한다.
- 기존 기능 전체, macOS/Linux, 로컬 UI와 메신저 세션을 유지한다.
- 모델·외부 메신저 없는 핵심 검사 전체 120초 이내.
- 로컬 저장→실제 네이티브 입력 큐 수락 p95 1초 이내. 모델 응답과 외부 플랫폼 시간 제외.
- 승인·런타임 버전·지원 범위를 임의로 대체하지 않는다.

## 현재 구현

- `xsm protocol serve --stdio`: 버전 협상, 연결별 불투명 세션 핸들,
  프로필/대화 분리, 수명 락, 상태 갱신·종료, 세션별 이벤트 구독.
- 작업 처리 메서드 26개와 공개 스키마를 MCP 모듈 밖의 공통 서비스로 이동했다.
  일반 프로토콜은 MCP transport를 import/상속하지 않는다. CLI 전체 서비스 추출은 아직 미완이다.
- 일반 참여자 DM은 기존 정책과 정본 handoff 저장소를 사용한다.
  알려지지 않은 런타임을 Codex 전송으로 보내지 않는다.
- 수신 알림·네이티브 큐 보고·최종 소비 ACK 분리. FYI는 알림을 발생시키지 않는다.
- `user-decisions` 호스트 질문·응답 결속을 구현했다. 답 저장 뒤 원 작업을
  재호출해야 적용한다. Pi/OpenCode native UI fixture는 통과했으며, 실제 사용자
  응답 검증과 Hermes/OpenClaw UI 연결은 미완이다.
  UI 능력이 없는 호스트와 네이티브 transcript 복구 대체는 `-32004`로 거부한다.
- Python 3.9+ 클라이언트, 실행 가능한 Node 모듈과 TypeScript 타입,
  전송 fixture 및 실제 서버 subprocess 검사.
- Pi/OpenCode native 연결·설치·UI fixture, Hermes native pull 도구,
  OpenClaw의 guarded native context queue prototype이 있다. 런타임 전체 지원
  인증이나 모든 표면의 연결 완료를 뜻하지 않는다.
- 실험 명세·요청 스키마·README 연결. 안정된 호환성 보장은 아직 아니다.

## 단계별 판정

| 단계 | 상태 | 남은 조건 |
|---|---|---|
| P0 계약·현황 | 부분 구현 | 전체 기능별 normative 스키마, 독립 구현 적합성, 안정판 API 감사 |
| P1 공통 서비스 | 부분 구현 | CLI 추출, 일반 원격 신원, 네이티브 UI 연결, 비동기 작업 수명 |
| P2 SDK·검사기 | 부분 구현 | 독립 구현 적합성, 전체 오류/취소 계약 (Python↔Node 교차 시험 통과) |
| P3 Pi·OpenCode | 부분 구현 | 연결·수신·설치·UI·대화 수명 경로 검증. Native worker·자동 재접속·busy/now의 실제 우선순위 등 미완 |
| P4 Hermes·OpenClaw | 부분 구현 | Hermes pull 도구, OpenClaw native 도구/guarded queue prototype. Agent turn·idle wake·UI·설치·worker 미완 |
| P5 통합·배포 | 부분 검증 | Mac native SDK/CLI fixture 일부 통과. Linux, 30개 방향 조합, 동종 세션, 원격, 버전·플랫폼별 전체 native p95, 메신저, 전체 회귀 미완 |

## 초기 실제 검사

`python3 scripts/check-protocol.py`는 실행 전에 HOME/XSM_HOME/CODEX_HOME/
CLAUDE_CONFIG_DIR를 격리하고 API 자격 증명과 실행 중 세션 환경을 넘기지 않는다.
초기 표본에서는 핵심 121개 + Python 클라이언트 15개 + Node 클라이언트 20개가 통과했다.
Python 3.9에서 총 16.267초, Python 3.14에서 9.948초였다.
이 수치는 네이티브 큐 지연이나 전체 제품 회귀 결과가 아니다.

별도 복사본에서 잘못된 네이티브 경로, FYI 깨우기, 허위 사용자 답 허용
세 변이에 더해 종료 판정·알림 기아·차단 기본값의 세 변이를 넣었고,
총 6건에서 관련 검사가 모두 실패했다. 원본은 변경하지 않았다.
최종 검사와 변이의 원시 로그는 `deliverables/protocol-foundation/`에 있다.
추가로 기존 MCP·설치·handoff·네트워크 신원 관련 254개 검사가
Python 3.14에서 43.548초에 통과했다. 전체 제품 회귀는 아니다.

초기 실패도 기록한다. 핵심 초회 12개 중 3개 오류(공개 status 필드 오독,
종료된 세션 재등록), 다음 39개 중 1개 오류(정의되지 않은 원장 단계),
Python 3.9 SDK 타입 주석 import 실패를 수정했다.
별도 검토가 찾은 종료 판정·연속 요청 알림 기아·기본 15초 대기도 수정하고
회귀 검사를 추가했다.

## 확인된 선행 조건과 미실행 항목

Reason의 Hermes 통합은 다음 API를 요구한다:
`session_key`, `session_cwd`, `session_surface`, `session_supports_async_delivery`,
`is_interrupted`, `inject_message`.
Hermes v0.22.5의 `hermes_cli/plugins.py`에는 이 중 `session_key`,
`session_supports_async_delivery`, `is_interrupted` 정의가 없다.
이는 Reason 통합의 그대로 이식을 막는다. 안정판에 다른 구현 경로가 전혀
없다는 증거는 아니며, 미릴리즈 빌드로 자동 변경하지 않는다.

근거: [고정 안정판](https://github.com/NousResearch/hermes-agent/blob/v0.22.5/hermes_cli/plugins.py),
[Reason 고정 통합](https://github.com/reason-machines/reason-network/tree/bcf045cf7eadcbff25965fd6b12afeb88ab819ea/integrations/hermes).

현재 머신에서 실행 파일은 Pi만 발견했다. OpenCode/Hermes/OpenClaw 설치,
실제 로그인·네이티브 모델 실행, Linux, 메신저 계정 연결과 발송은 수행하지 않았다.
사용자 설정·권한·실제 프로필은 수정하지 않았다. 네이티브 인증과 30개 조합은
선행 연결부가 미구현이므로 전제 미충족이다.

후속 책임은 구현 담당 세션에 있다. P0/P1의 미결 계약을 구현하고 안정판
연결 경로를 확정한 뒤 P3/P4를 실행하고, 실제 호스트가 준비된 경우에만
P5 수치를 수집한다. 미릴리즈 API 도입 또는 지원 범위 변경은 사용자 결정이
필요하다. 해당 변경은 승인되지 않았으며 전체 작업은 미완이다.

## 조사 작업의 한계

네 후보 전체의 상세 API 감사는 끝내지 못했다. 조사 워커는 추가 조사를
중단한 뒤 종료했으며, 그 워커의 완료 보고나 감사 문서는 수신하지 못했다.
이 문서의 Hermes 정의 유무는 담당 세션이 직접 조회한 고정 소스와
`deliverables/protocol-foundation/hermes-stable-api.json`에 한정한다.
이 근거만으로 안정판의 모든 대체 연결 방법이 불가능하다고 판정하지 않는다.

## 로컬 체크포인트와 교차 구현 시험

- `021c672`: 실험적 호스트 프로토콜·두 클라이언트·기본 검사 첫 커밋.
- Python과 Node가 각기 다른 실제 서버 프로세스에 연결해 공유 정본 저장소로
  요청과 회신을 주고받고 양쪽 소비 ACK를 남기는 검사를 추가했다.
- 핵심 121개 + Python 16개 + Node 20개: Python 3.9에서 16.900초,
  Python 3.14에서 9.603초에 통과했다. 로그는
  `deliverables/protocol-foundation/{py39,py314}-cross-language.log`에 있다.
- 초회에는 왕복 후 Node 시험 피어가 stdin을 계속 열어 종료 기한을 넘겼다.
  시험 피어가 stdin을 pause하도록 고쳤으며 제품의 대기 기한은 늘리지 않았다.
- 이 시험은 두 SDK의 상호운용이다. 제3자의 독립 명세 구현, 실제 네이티브
  하네스, Linux나 외부 메신저 인증으로 확대 해석하지 않는다.

## 공통 서비스 추출

- `xsm/operations.py`는 정책·승인·팀·보드·파일·워커 작업의 공통 서비스를 소유한다.
- `xsm/operation_schema.py`는 두 transport가 함께 쓰는 작업 목록과 응답 해석을 소유한다.
- 이동한 26개 메서드의 AST 본문은 이전 커밋과 모두 동일했다. 비교 결과는
  `deliverables/protocol-foundation/service-move-comparison.json`에 있다.
- 초기 확대 검사 343개 중 워커 경로 5건이 `threading` import 누락으로 실패했다.
  이를 수정하고 아키텍처 경계 검사를 추가한 뒤 344개가 57.038초에 통과했다.
  실패와 수정 후 로그를 모두 보존했다.

## 호스트 사용자 질문과 참여 세대

- 공통 서비스 추출은 `d1a7126`으로 커밋했다.
- `user-decisions`를 명시한 호스트만 `decision/request`와 전용 응답 경로를 사용한다.
  질문 ID·일회용 challenge·표시 원문·선택지·소유자·참여 세대·유효 시간을 검사한다.
- 응답은 `host-user`로 보관하며 `native-user` transcript 증거로 부르지 않는다.
  답 저장만으로 효과를 적용하지 않는다. 동일 원 작업 재호출에서 다시 검증한다.
- 같은 프로세스에서 닫았다가 여는 세션에도 새 참여 세대를 부여한다.
  이전 승인과 claim 토큰이 새 실행에 상속되지 않는 것을 검사했다.
- Python/Node 전용 `XsmHostClient`를 추가했다. 일반 request 경로는 호스트
  클라이언트에서도 직접 decision.response를 호출할 수 없다.
- 팀 보드에 출처 보존, 권한 확대 1회 적용, 거부 시 무변경, 늦은 답·다른
  세션·다른 표시·응답 ID 재사용·이전 세대 거부의 경로를 실행했다.
- 핵심 135개 + Python 클라이언트 17개 + Node 클라이언트 21개가 통과했다.
  Python 3.9.6 전체 28.344초, Python 3.14.6 전체 15.268초였다.
  각 Node 시험 서버도 해당 검사기의 Python 실행 파일을 사용하도록 고정했다.
- 추가 기존 승인·보드·소비자·MCP 회귀 258개가 20.421초에 통과했다.
  잘못된 검사 모듈명과, 공통 서비스로 이동한 기존 설명 주석의 허용 경로가
  낡아 발생한 최초 실패는 원시 로그에 남겼다. 검사의 금지 문구 규칙은 유지했다.
- 잘못된 표시를 허용, 응답 ID 재사용을 허용, 참여 세대를 재사용하는 세 변이는
  각각 관련 검사를 실패시켰다. `host-decisions-mutations.json`을 참조한다.
- 소형 호스트를 사용한 callback 시험이며 실제 하네스 UI를 사람에게 보여준
  인증이 아니다. P3/P4/P5의 네이티브·Linux·외부 메신저 조건은 여전히 미완이다.

## 다음 네이티브 연결의 준비 근거

Pi 1.4.0의 공식 npm 패키지와 고정 태그 API를 조회했다. Node 최소 버전은
22.19.0이며, 확장에 세션 생명주기·custom message·사용자 UI가 있다.
의존성은 사용자 프로필 밖의 임시 폴더와 별도 HOME/npm cache에 설치하며
설치 스크립트·audit·fund 호출은 끈다. 모델·로그인·유료 API는 호출하지 않는다.
조회 및 설치 상태는 `deliverables/protocol-foundation/pi-140-*.json`과 로그에
기록한다. 이는 Pi 연결부 구현이나 네이티브 지원 완료 증거가 아니다.

## 공통 호스트 조정과 Pi 실험 연결

- Node 공통 호스트는 질문별 기다림, 하나만 취소/모두 취소, 표시 포기,
  연결 종료, 네이티브 큐 거절 뒤 인수 해제를 관리한다. 네이티브 연결부에
  승인·정본 저장 정책을 복제하지 않는다. Python 저수준 호스트 API도
  표시 포기를 지원한다.
- `decision.abandon`은 표시만 포기한다. 미응답을 승인·거부로 바꾸지 않는다.
  `inbox.release`는 현재 소비자의 인수를 ACK 없이 돌려놓는다.
- 일반 프로토콜의 단순 inbox 조회가 legacy delivered 영수증을 쓰던 반례를
  검사로 재현했다. 이제 Native context admission(`admitted`, 자기 claim 토큰
  필수) 또는 명시적 소비 ACK 전에는 성공 영수증을 쓰지 않는다.
- canonical ACK가 커밋된 뒤 영수증 미러가 실패해도, sender의 대기·재전송은
  이미 소비된 원문을 다시 보냈다고 판단하지 않는다.
- `integrations/pi/xsm.mjs`는 Pi 1.4.0의 세션·메시지 이벤트, UI와 도구 등록만
  연결한다. 기본 이름은 시간형 UUID 앞부분 대신 정본 endpoint 이름을 쓰고,
  프로필 경로는 realpath로 정규화해 별칭 경로로 신원을 분리하지 않는다.
- 실제 Pi RPC에서 도구 21개 등록, 선택 질문 왕복, native message_start,
  명시적 ACK를 실행했다. SDK의 실제 nested-tool 실행·검증 커널에서도
  inbox 성공, 미지원 대기의 실제 tool error, 질문·답 경로를 실행했다.
- SDK 커널 시험은 명시적인 issuing-assistant fixture를 쓴다. 모델 생성
  응답이나 사람의 승인으로 부르지 않는다. 최초 시험은 이 fixture가 없어
  커널이 정상 거절했고, 해당 실패도 로그에 보존했다.
- 큐 성공은 sendMessage 호출 반환으로 단정하지 않고 native message_start
  관측 뒤에 보고한다. 소비 ACK는 이를 이유로 자동 생성하지 않는다.
- native p95 측정은 macOS의 모델 미구성 Pi 1.4.0에 한정한다. 각 표본은
  실제 메시지 진입 뒤 명시적 ACK까지 확인한다. 런타임 버전·플랫폼·Python·
  코드 해시를 결과에 기록하며 실패/중단 원시 로그는 계속 남긴다.
- Linux, 실제 모델 회신, 물리적 TUI, native worker, 자동 재접속,
  설치·업데이트 소유권, 다른 런타임 및 30개 방향 조합은 여전히 미완이다.
- Linux 환경의 읽기 전용 사전 점검에서는 Docker CLI와 Colima가 발견됐지만
  Docker engine은 연결되지 않았다. VM·전역 Docker context는 변경하지 않았다.

## 호스트 조정 최종 로컬 검사

현재 묶음은 핵심 142개 + Python 클라이언트 18개 + Node 클라이언트/호스트
28개, 총 188개이다. Python 3.9.6에서 33.994초, Python 3.14.6에서
20.897초에 통과했다. `host-coordination-current.json`과 버전별 로그가 근거다.
원문을 읽기만 해도 runtime_reached가 true였던 반례와, canonical ACK 뒤
미러 영수증이 없으면 대기가 계속되던 반례는 각각 변이 검사로 재검출했다.

최신 Pi 실행은 `pi-native-admitted/result.json`에 있다. Pi 1.4.0·macOS·
Python 3.14.6에서 100회를 모두 완료했고 p95 상한은 약 0.429초였다.
결과의 sourceSha256으로 실제 실행한 코드와 대조한다. SDK 커널 검사는
`pi-sdk-admitted.json`에 있으며 모델 호출은 0회이다.
이 수치는 다른 버전·Linux·실제 모델·실제 사람의 TUI 응답으로 확대하지 않는다.

## Pi 소유 설치와 native 수명 검증

- runtime snapshot에 공유 Node/Python 클라이언트와 integrations 자산을 포함한다.
- `protocol install/uninstall/inspect pi --home`을 추가했다. 보호된 준비/완료
  소유 기록과 dir-fd 기반 no-follow/CAS로 자기 로더만 갱신·제거한다.
- 임의 파일·사용자 편집·로더/상위 폴더 symlink, 준비 후 경로 교체와 늦은
  사용자 편집, 최종 소유 기록 저장 중단을 실제 파일 경로로 검사했다.
- 기존 설정 bytes/mode, 다른 확장과 사용자 loader mode는 유지한다.
  손상된 소유 기록은 변경을 거부하고 snapshot 정리에서도 보수적으로 보존한다.
- Node 호스트의 bare snapshot-root argv도 정리기의 사용 중 참조로 인식한다.
- 설치 전용 12개 검사와 기존 설치 관련 70개 회귀가 통과했다. 최신 수치와
  버전별 core gate는 `host-install-checks.json`에 기록한다.
- native autoload 최초 시험은 `.mjs`가 자동 발견되지 않아 실패했다.
  `.js` 로더로 수정한 뒤 실제 -e 없는 경로가 도구 21개와 native 질문을 로드했다.
- 그 다음 실패는 `/var`와 `/private/var`의 동등 경로를 문자 비교한 검사기 문제였다.
  realpath로 대조하고 pinned Python과 실행 중 snapshot의 실제 origin을 검증했다.
- native 수명 하네스는 기존 대화, 문맥 fixture, 아직 반영되지 않은 설치, 같은
  대화 재개, 실행 중 old snapshot 보존, 새 snapshot 재개와 세대 교체,
  제거 뒤 기존 문맥/다른 설정 보존을 확인했다.
- 최초 하네스는 bash 진행 이벤트를 response로 오인했고, 다음에는 Pi가
  assistant 없는 세션을 아직 파일로 저장하지 않아 중단됐다. 각각 response
  타입 대조와 public SessionManager의 명시적 assistant fixture로 수정했다.
  이는 모델 생성 답이나 실제 사람 입력으로 부르지 않는다.
- native 실행 결과와 모든 실패는 `deliverables/protocol-foundation/`의
  `pi-installed-*`, `pi-install-lifecycle-*`, `host-install-*.log`에 구분해 남겼다.
- Linux, 다른 세 런타임, 자동 재접속과 모든 native worker/remote/메신저
  수용 조건은 그대로 미완이다. 전체 계획이나 Pi 전체 인증을 완료하지 않았다.

### Pi 설치 경로의 최신 증거

핵심 검사 154개 + Python 클라이언트 18개 + Node 클라이언트/호스트 28개로
현재 빠른 검사는 총 200개이다. Python 3.9에서 37.754초, 3.14에서
27.015초에 통과했다. 설치 관련 기존 70개 회귀는 별도 실행에서 통과했다.

실제 프로필 autoload와 snapshot interpreter를 검증한 100회 실행은
`pi-installed-100/result.json`에 있다. macOS·Pi 1.4.0·Python 3.9.6에서
모두 완료했고, send 시작→native message_start 관측의 p95 상한은 약
0.506초였다. `.mjs` 직접 로드 표본과 설치된 `.js` 로더 표본을 합치지 않는다.

`pi-install-lifecycle-prune/result.json`은 여섯 native 수명 시나리오를
통과했다. 실제 live actor가 쓰는 old snapshot은 정리에서 남고, old actor를
종료한 뒤에는 정리 가능함도 확인했다. 프로세스 사용 사실은 이 시험의
등록 PID와 실제 protocol_root만 관측했으며 타 사용자 argv를 수집하지 않았다.

설치 자산 누락, directory guard 제거, 늦은 사용자 편집을 덮는 세 변이는
모두 관련 검사를 실패시켰다. helper와 설치 단계의 실패 기록은 보존했다.
이 단계의 설치는 전부 격리 HOME/프로필에서만 실행했다. 실제 사용자
프로필·trust·권한·전역 Python pin·Docker context는 수정하지 않았다.

## OpenCode 서버 연결 1차 구현

- OpenCode 1.19.5의 서버 플러그인에서 native 대화별로 공통 호스트를 연다.
  실제 도구 context의 sessionID/directory에 결속한다. 동시 호출은 opening을
  공유하고 삭제/재개는 세대를 교체한다.
- 스키마 21개를 공통 서버에서 읽고 native SDK의 Zod로 변환한다.
  optional/required를 유지하며 native 프로필에서 SDK를 import한다.
- noReply 저장 뒤 같은 대화/메시지/본문/메타데이터를 다시 읽어야 admitted를
  보고한다. Busy 상태의 중복 wake를 피하고 소비 ACK는 별도로 둔다.
- 명시적 OpenCode 프로필 설치·갱신·제거는 Pi와 같은 소유권/CAS 경로를 쓴다.
  전체 OpenCode 수명 인증은 미완이다.
- 첫 native 초기화는 SDK path 조회로 재진입해 멈췄다. 경로를 먼저 확정했다.
  다음에는 import 전용 SDK export를 require.resolve로 읽을 수 없어 실패했다.
  native loader에서 공개 import로 tool.schema를 전달하도록 수정했다.
- 첫 하네스는 shell인 bin/xsm을 Python으로 실행해 설치 전에 실패했다.
  명시적 Python boot 경로로 수정했다. 설치 snapshot의 native 도구 21개와
  메시지 5건 진입을 확인했다. 실패한 SDK 초기화와 서버 로그는 보존한다.
- 새 검사기의 첫 실패는 optional인 text를 required라고 가정하고 registry의
  lock 파일까지 JSON으로 읽은 오류였다. 다음 실패는 인계한 claim을 일반
  inbox가 다시 반환한다고 가정한 오류였다. 실제 native 본문의 ACK 토큰으로
  고쳤다. 설치 검사에서는 /var와 /private/var를 realpath로 대조하도록 고쳤다.
- TUI 질문은 아직 구현하지 않았다. user-decisions를 광고하지 않고 필요한
  작업을 거부한다. 전체 계획의 미완 조건으로 유지한다.

### OpenCode 수신 시험의 실패와 보완

최초 100회 native 시험은 81회 관측 뒤 실패했다. 완료 표본에도 1초를 넘는
지연이 있어 p95 수용 기준의 통과로 쓰지 않는다. 소비 ACK 없이 쌓인 표본이며
기본 대화 목록 조회의 범위와 모델 미구성 provider의 재시도도 섞였다.
`opencode-native-100/result.json`과 서버 로그를 보존한다.

조사 과정에서 임의 UUID를 native 메시지 ID로 쓰던 문제를 발견했다.
OpenCode가 정렬 가능한 ID를 발급하도록 바꾸고 별도의 임의 admission metadata로
본문 진입을 확인한다. 하네스의 조회 범위도 명시했다. Native ID를 임의로
넘기면 callback 검사가 실패한다.

응답하지 않는 provider 대신 loopback에서 명시적 assistant fixture의 tool-call
패킷만 반환하는 하네스를 추가했다. 실제 모델 추론이나 API 과금은 없다.
native 실행 커널이 xsm_ack를 실행하고 반환한 acked가 정확히 한 건인지 확인한다.
5회 실행이 모두 통과했다. 이는 실제 모델의 작업 성공이나 사람의 응답이 아니다.
100회 idle 시작 표본과 전체 수용 조건은 별도로 확인해야 한다.

수신 내용 검증을 제거하는 변이와 native 대화 ID를 하나로 공유하는 변이는
각각 새 검사를 실패시켰다. `opencode-binding-mutations.json`이 근거다.

### OpenCode 최신 로컬 검증

빠른 검사는 핵심 155개 + Python 클라이언트 18개 + Node 클라이언트/호스트
32개, 총 205개이다. `scripts/check-protocol.py`가 Python 3.9.6에서 42.690초,
3.14.6에서 27.619초에 통과했다. `opencode-checks.json`과 두 버전의
`*-opencode-final.log`가 근거다. 두 실행 모두 120초 기준 안이다.

`opencode-native-ack-100/result.json`의 native 시험은 100회를 모두 완료했다.
OpenCode 1.19.5·macOS·Python 3.9.6의 설치된 snapshot을 사용했다.
각 표본 시작 전 idle을 확인했고 native 기록에 본문이 들어간 뒤 관측한
지연의 p95 상한은 약 0.379초였다. 각 표본의 ID와 native xsm_ack 도구의
acked 반환 ID가 일치한다. 100건 모두 native ACK를 완료했다.

실제 실행 origin이 설치된 snapshot인지, 기록한 sourceSha256이 현재 실행
소스와 같은지도 대조했다. ACK를 발생시킨 assistant는 loopback fixture이다.
모델 추론·API 과금·사람의 UI 응답은 없다. 이 표본과 소비 ACK가 없던 최초
81건 실패 표본은 provider와 소비 조건이 다르므로 같은 조건의 성능 전후
비교로 쓰지 않는다. 실패 기록은 그대로 남긴다.

이 수치는 해당 native 서버의 idle 입력 진입 검사이다. Busy/now 개입,
TUI 승인, Linux, 전체 설치 수명, 자동 재접속, native worker, 원격/메신저,
다른 런타임과의 방향 조합 등 전체 계획의 미완 조건은 유지한다.

## OpenCode native 질문 표시와 프로토콜 결속

`question-ui.mjs`에 고정 버전의 DialogSelect/DialogPrompt callback을 추가했다.
표시 원문과 질문 ID를 고정하고 native 대화 전환·만료·취소·종료를 검사한다.
이미 열린 다른 dialog를 덮지 않으며, 대체된 질문의 늦은 callback도 새 dialog를
지우거나 답을 승인하지 않는다. 서버 binding은 명시적 present callback을 주입한
경우에만 user-decisions를 광고하고 실제 도구의 대화 ID를 전달한다.

새 renderer 검사 6개와 서버 callback 결속 1개가 통과했다. 대화 전환 검사를
없애거나 선택지 외 값을 허용한 변이는 각각 관련 검사를 실패시켰다.
`opencode-ui-mutations.json`에 기록했다.

격리 PTY의 실제 OpenCode 1.19.5 TUI에서 질문·선택지·Scope 렌더링과 Enter/Escape
callback을 확인했다. `probe-opencode-question-ui.py`는 실제 프로토콜 질문을
받아 native TUI에 표시하고 실제 callback을 신뢰 호스트 SDK로 회신한다.
Enter는 답을 저장할 때 answered, 원 작업 재호출 뒤 applied가 된다.
Escape는 dismissed이며 원 작업을 재호출해도 적용하지 않는다. 출처는 host-user이고
native-user transcript로 바꾸지 않는다. 두 사례의 원시 화면·event·결과는
`opencode-tui-protocol-choose`, `opencode-tui-protocol-cancel`에 남긴다.

초기 TUI 하네스는 공급자가 비어 초기 설정 화면이 나타났으며, 관측 코드에
없는 SDK 내부 필드 접근도 있었다. 공급자는 loopback fixture로 한정하고 공개
native route/session만 관측하도록 수정했다. 초기 두 실행은 SIGTERM 후 waitpid가
끝나지 않아 시험이 소유한 TUI PID만 종료했다. 이후 종료 대기와 강제 종료에
기한을 두었다. 실패한 화면·결과도 각 opencode-tui-* 경로에 보존했다.

이 결과의 응답은 자동 키 입력 fixture이다. 실제 사람의 답, 모델 추론,
제품용 서버–TUI IPC나 자동 설치를 인증하지 않는다. 기본 설치의 UI 연결은
아직 미완이며 전체 계획의 수용 조건으로 유지한다.

빠른 검사 묶음은 핵심 155개 + Python 클라이언트 18개 + Node 39개, 총 212개다.
`scripts/check-protocol.py`는 Python 3.9.6에서 42.314초, 3.14.6에서 27.888초에
통과했다. 두 버전 모두 120초 기준 안이다. 두 native TUI 사례의 sourceSha256과
현재 renderer/하네스 파일도 대조해 일치함을 확인했다. 원시 로그는
`py39-opencode-ui-first.log`, `py314-opencode-ui-final.log`에 남긴다.

## OpenCode 서버–TUI 직접 연결

`ui-channel.mjs`와 `tui.mjs`로 native API의 빈 ignored/synthetic 부분과
메타데이터를 이용하는 연결을 구현했다. 별도 listener나 중앙 daemon은 없다.
서버는 질문별 일회용 값으로 TUI 한 곳을 선택하고, 실제 renderer callback의
표시 확인이 온 뒤에만 답을 받는다. 다른 대화·일회용 값·UI instance, 표시 전
답, 늦은 callback과 일반 텍스트에 섞은 제어 부분은 적용하지 않는다.
호스트 핸들과 원래 protocol challenge는 전송하지 않는다.

현재 기본 설치는 UI 모드를 활성화하거나 native TUI config에 companion을
등록하지 않는다. 개발 로더의 nativeUi 옵션으로 직접 연결 경로를 시험했다.
소유권을 보존하는 기본 설치의 미완 항목은
[opencode-ui-install.md](opencode-ui-install.md)에 기록했다.

실제 OpenCode 1.19.5·macOS의 native 실행 커널에서 xsm_decide를 호출해 TUI의
Enter와 Escape가 직접 서버로 회신됨을 확인했다. 질문을 옮기는 Python relay는
쓰지 않는다. Enter는 host-user 답과 원 작업 재호출 뒤 applied, Escape는
dismissed이며 적용이 없다. 두 실행 모두 제어 프레임 5개를 관측했다.
도구 실행 후 모델 요청까지 읽어 모든 제어 프레임과 일회용 값이 제외된 것을
확인했다. `opencode-native-ui-render-choose`, `opencode-native-ui-render-cancel`의
결과·원시 화면·native 기록·assistant-fixture 요청과 sourceSha256이 근거다.
실제 사람이나 모델 추론을 시험했다고 부르지 않는다.

빠른 묶음은 핵심 156개 + Python 클라이언트 18개 + Node 45개, 총 219개다.
`scripts/check-protocol.py`는 Python 3.9.6에서 38.894초, 3.14.6에서 24.529초에
통과했다. 두 실행 모두 120초 안이다. `*-native-ui-complete-assets.log`에 남긴다.

대화 결속·일회용 값·render 확인을 각각 제거한 세 변이는 새 검사를 실패시켰다.
snapshot 설치는 UI 관련 세 모듈도 필수 자산으로 검사하며 누락된 경우 프로필
생성 전에 거부한다. 이 자산 guard를 뺀 변이도 실패했다. 첫 자산 변이 시도는
테스트 setup의 모듈 재로딩 때문에 주입되지 않았으므로 성공 증거로 쓰지 않는다.
setup 뒤 주입한 결과와 초기 무효 시도 로그를 모두 보존했다.

## OpenCode 기본 UI 설치와 snapshot 수명

기본 프로필 설치가 서버 UI 모드를 켜고 immutable snapshot의 TUI URI를 native
설정에 등록한다. JSONC를 재직렬화하지 않고 자기 URI만 편집하며 댓글·후행
쉼표·다른 plugin·사용자 mode를 유지한다. 설정 원문을 소유 manifest에 복사하지
않고 URI 삽입 fragment와 hash만 기록한다. 무변경 파일은 제거 뒤 원래 bytes를
복구하고, 사용자가 추가한 데이터가 있으면 자기 URI만 제거한다.

서버 로더와 UI 설정을 먼저 검사하고 준비 journal을 남긴 뒤 CAS/no-follow로
변경한다. 중단된 갱신을 반복해도 실제 old UI URI의 root 참조를 잃지 않는다.
제거 중단도 재실행으로 복구하며 사용자 편집을 backup으로 덮지 않는다.
실제 로더/설정의 사용자 snapshot 참조도 정리에서 보존한다.

서버 JS와 TUI는 별도 참여자 대신 실제 PID·시작 세대·소스 root의 component
수명 기록을 쓴다. 등록과 정리는 같은 snapshot 잠금을 사용한다. 시작 시각은
C locale/UTC이며 시간대가 없는 과거 수명 기록은 PID가 살아 있으면 보존한다.
정리기는 그 수명 기록에 있는 PID만 조회한다.

기본 설치에서 실제 native 도구→TUI→서버의 Enter/Escape가 모두 통과했다.
개발 로더와 Python 질문 relay를 사용하지 않았고 추가 observer는 읽기만 한다.
서버와 UI가 설치된 snapshot을 사용한 것과 실제 UI PID의 수명 기록을 확인했다.
결과는 `opencode-installed-ui-release-{choose,cancel}/result.json`에 있다.
자동 assistant/키 입력 fixture이며 실제 모델 추론·사람의 응답이 아니다.

최신 빠른 검사는 핵심 180개 + Python 18개 + Node 45개, 총 243개이다.
Python 3.9.6에서 43.324초, 3.14.6에서 28.600초에 통과했다. 두 실행 모두
120초 안이며, 별도 기존 설치 회귀 104개도 65.389초에 통과했다.
CAS·사용자 설정 보존·활성 component 보존·정리 잠금의 네 변이도 검출했다.
Native 갱신·같은 대화 재개·제거·old UI 실제 정리의 전체 수명 시험은 여전히
미완이다. 세부 기준은 [opencode-ui-install.md](opencode-ui-install.md)를 따른다.

## 확인된 공통 PID 시각 호환 항목

macOS·Python 3.9.6의 자기 PID 표본에서 `ps lstart`는 UTC와 Asia/Seoul에 따라
다른 문자열을 반환했다. 그 표본에서는 동일 PID의 기록을 UTC로 만든 뒤
Asia/Seoul에서 `identity._state_of`로 읽으면 live에서 stale/lstart_changed로
바뀌었다. `legacy-clock-audit.json`이 재현과 AST 호출 목록의 근거다.

기존 공통 lstart 호출은 12개 파일의 22곳이다. 등록·수신 claim·승인 세대·
worker·설치 수명 경로가 포함되며, 22개의 독립 결함이라는 뜻은 아니다.
새 component 수명은 UTC로 고정했지만 공통 identity 자체는 바꾸지 않았다.
기존 기록을 무효화하지 않는 이행과 각 경로의 호환 검증이 P1 미완 항목이다.

## OpenCode native 설치 수명과 경로 별칭 잠금

`probe-opencode-install-lifecycle.py`로 설치 전 대화→설치→재개→갱신→이전 UI만
남은 상태의 보존→정상 종료 후 실제 정리→새 UI 재개→제거/재시작을 검증했다.
기본 조건과 설치 후 사용자 plugin/로더 편집 조건이 각각 8단계를 통과했다.
사용자 편집 로더의 설치는 거부해 파일을 보존했고, 제거 뒤 추가한 plugin이
실제 TUI에서 로드됐다. API 입력은 noReply fixture이며 모델 추론은 없다.

이전 UI만 남은 단계에는 이전 root를 참조하는 다른 설정이 없었고 활성
component도 해당 UI 하나였다. UI 정상 종료 뒤 실제 정리기가 이전 root를
삭제했다. UI pin을 제거한 native 변이는 4단계에서 잘못 정리해 실패했다.
이는 UI와 backend가 모두 살아 있어 잘못된 구현도 통과하는 검사를 피한다.

실제 두 프로세스 검사에서 상위 디렉터리 symlink 별칭이 기존 잠금을 우회함을
재현했다. `_target_lock`의 14개 직접 사용은 install/setup/host/component 네
파일에 있다. 상위 경로만 정규화하고 마지막 symlink는 경로 이름으로 잠근다.
기존 방식과 마지막 symlink까지 해석하는 두 변이는 각각 관련 검사를 실패시켰다.

초기 native 시험은 준비 시간 관측과 의존성 설치 대기에서 실패했다. 고정된
실제 SDK의 package/lock 정보를 함께 준비해 native 재설치를 분리했고, 같은
서버 PID에서 준비를 관측한다. `$schema`는 native 자체가 xsm 설치 전에 추가해
설치 직전 bytes를 기준으로 삼았다. Python 3.9 하네스의 newline 인자 실패도
보존했다. 초기 실패를 완료 표본으로 합치지 않는다.

정상 결과는 `opencode-lifecycle-final`, `opencode-lifecycle-user-edit-fixed`에,
의도적 실패는 `opencode-lifecycle-final-no-ui-pin`에 남긴다. 모델·사람의 실제
응답·Linux 인증이나 다른 런타임의 완료로 확대하지 않는다. 공통 PID 시각
호환 항목과 상위 전체 계획은 계속 미완이다.

최신 빠른 묶음은 핵심 182개 + Python 클라이언트 18개 + Node 45개, 총 245개다.
Python 3.9.6에서 43.295초, 3.14.6에서 27.866초에 통과했다.
`py39-lock-lifecycle-complete.log`, `py314-lock-lifecycle-complete.log`가 근거다.
설치와 setup 경로의 별도 회귀 117개는 64.868초에 통과했다
(`lifecycle-install-setup-regression.log`).

## Python 공통 호스트와 Hermes 안정판 API 연결

`clients/python/xsm_host.py`에 공통 비동기 참여 수명·알림·질문/원 작업 재호출·
관측 뒤 수락 보고·실패 후 claim release·명시적 ACK 경로를 추가했다.
Native callback이 없으면 pull-only이며 events나 user-decisions를 광고하지 않는다.
Python SDK를 package로도 제공해 같은 프로세스의 snapshot별 import를 분리한다.
Runtime snapshot은 Python integration 파일도 포함한다.

다른 호출이 아직 같은 질문의 RPC를 마무리하는 동안 취소가 표시를 포기하는
경합을 Python과 기존 JS 양쪽에서 재현했다. 응답 대기자 등록과 취소 판단을
직렬화해 수정했고 일반 작업을 coalesce하지 않는다. JS 호스트를 사용하는
Pi/OpenCode도 영향 범위라 실제 SDK/TUI 경로를 다시 검사한다.

Hermes v0.22.5에는 PluginContext.session_key 메서드가 없지만 별도
plugin_session.session_key와 session_context.async_delivery_supported가 있었다.
on_session_end는 매 turn 종료이며 finalize/delete와 구분해야 한다.
Native inject True는 TUI 큐 수락과 gateway 예약의 의미가 다르다. Classic CLI는
키 검사 전 현재 큐를 사용한다. ask_choice도 동기 slash 문맥에만 연결된다.
이 경로들을 동일한 native admission/UI로 간주하지 않았다.

`integrations/hermes/xsm.py`는 실제 dispatcher의 session_id와 task-local ID를
비교하고 native workspace를 사용한다. 공통 스키마의 native 도구 21개를
등록하며 finalize/resume에서 주소 보존·참여 세대 교체를 처리한다. 현재는
pull-only이며 자동 주입과 사용자 UI를 만들지 않는다.

실제 고정 SDK의 PluginContext·registry.dispatch·hook dispatcher에서 6개 검사가
통과했다. 도구 등록·세션/폴더 분리·전송/pull/ACK·불일치 거부·turn/finalize 구분·
UI 미연결 거부를 포함한다. Native caller는 fixture이며 실제 agent turn이나
CLI/TUI/메신저 시험으로 세지 않는다. 최초 서로 다른 비 git 폴더 전송은
정책이 거부했으며 fixture를 같은 저장소의 두 폴더로 고쳐 우회하지 않았다.

`hermes-native-tools-current/result.json`과 실패 로그를 남겼다. Native source는
고정 v0.22.5, SDK 환경은 별도 Python 3.14이며 실제 사용자 홈·설정·API 키를
사용하지 않았다. Hermes 설치/수명·native 주입·UI·worker·자동 workspace 전환과
전체 계획은 미완이다. [API 경계](../../protocol/hermes.md)를 따른다.

최신 빠른 묶음은 핵심 182개 + Python client/host 28개 + Node 46개,
총 256개다. Python 3.9.6에서 53.701초, 3.14.6에서 34.456초에 통과했다.
`py39-hermes-sdk-complete.log`, `py314-hermes-sdk-complete.log`가 근거다.
Python의 native 수락 False guard와 snapshot SDK namespace를 제거한 변이는
각각 관련 검사를 실패시켰다(`python-host-mutations.json`).

JS 변경 뒤 실제 Pi 1.4.0 SDK 질문/도구 경로와 설치된 OpenCode 1.19.5의
TUI 선택·취소를 다시 통과했다. Pi는 issuing assistant/UI fixture, OpenCode는
loopback assistant/키 입력 fixture이며 실제 모델·사람 시험으로 쓰지 않는다.
`pi-host-waiter-final.json`, `opencode-host-waiter-{final,cancel}/result.json`에 남긴다.

## Hermes native validator 호환

실제 v0.22.5 validator의 15개 검사가 경고 없이 통과했다. 최초 검사는 기록용
context의 register_tool이 핸들을 반환하지 않는 것을 오류로 취급해 실패했고,
private session 모듈 import도 지적했다. Optional 반환은 native 계약에 맡기고
dispatcher의 세션 ID와 기존 참여의 workspace를 사용하도록 수정했다.
실제 SDK 도구 검사 6개도 다시 통과했다. Native caller ID는 모델 인자가 아니다.

`hermes-validator-first.log`, `hermes-validator-final.log`,
`hermes-public-api-final/result.json`에 구분해 남긴다. Validator 통과를 실제
agent/자동 주입/UI/설치 수명 완료로 해석하지 않는다. 상위 전체 계획은 미완이다.

후속 `probe-hermes-tools.py --discover`는 격리 프로필의 native discovery로 실제
활성화했다. 직접 register 호출을 대체하고 기존 6개 경로와 unload의 도구 제거·
참여 종료까지 총 7개 검사가 통과했다(`hermes-discovery-unload/result.json`).
실제 agent turn과 제품 설치기·자동 주입·UI의 미완 상태는 유지한다.

## Hermes workspace 전환과 finalize 경쟁

Native session-start hook에서 workspace가 바뀌면 기존 참여를 닫고 같은 주소의
새 세대로 전환한다. 도구 호출만으로의 전환과 이전 폴더의 늦은 호출은 거부한다.
실제 v0.22.5 discovery 검사 8개가 통과했다
(`hermes-finalize-native/result.json`). Native caller는 여전히 fixture다.

SDK 연결 생성 중 finalize가 항목을 먼저 제거하는 순서를 제어된 검사로
재현했고 수정 전 `KeyError`로 실패했다. 연결과 종료의 락을 공유한 뒤
Python 3.9/3.14에서 통과했다. `hermes-finalize-race-{red,green-py39,green-py314}.log`
에 기록했다. 빠른 묶음에 이 검사를 포함한 총 257개(핵심 183, Python 28,
Node 46)가 Python 3.9.6에서 55.579초에 통과했다
(`hermes-finalize-gate-py39.log`). 전체 계획과 실제 agent·UI·메신저 검증은 미완이다.

## OpenClaw 고정 소스 API 조사

공식 2026.10.9 package와 같은 Git tag의 소스를 격리 폴더에서 조사했다.
전역 Node 24.19.0은 engines 조건을 충족하지 않아, 공식 checksum을 확인한
Node 24.22.2를 임시 폴더에서 실행했다. 사용자 전역 환경은 바꾸지 않았다.
동기 plugin 등록, sessionId와 route key의 구분, 최종 효과의 권한 guard,
native system-event 큐의 용량·거부·ACK 경계를 확인했다.
[구현 경계와 원문 근거](../../protocol/openclaw.md)에 남긴다.
파일 해시는 `openclaw-stable-api.json`에 있다. Native host·loader·도구 실행은
아직 하지 않았으며 OpenClaw 연결부 및 P4/P5는 미완이다.

## Node 호스트의 선택적 수신과 거부 처리

OpenClaw 연결 준비 중 Node 공통 호스트가 수신 callback 없이도 events를
광고하는 것과 callback의 명시적 false를 admitted로 보고하는 것을 확인했다.
두 경로를 실제 프로토콜 subprocess 검사에서 수정 전 실패로 재현했다.
최초 false 검사에는 잘못된 priority가 있어 fixture를 wake=never로 고친 뒤
다시 실패를 확인했다. 두 실패 로그를 모두 보존했다.

이제 deliver가 없으면 pull-only로 참여하고 events를 구독하지 않는다.
naturalBoundary는 claim을 가져오기 전에 거부하며 도구의 inbox/ACK는 동작한다.
false 반환은 수락 거부로 처리하고 claim을 ACK 없이 반환한다. 수신과 UI는
독립적이며 pull-only host의 질문 응답·원 작업 재호출도 실제 서버에서 통과했다.

공통 259개(핵심 183, Python 28, Node 48)가 Python 3.9에서 57.004초,
3.14에서 36.710초에 통과했다. TypeScript 컴파일 검사도 통과했다.
`node-pull-gate-{py39,py314}.log`, `node-pull-types.log`,
`node-pull-ui-final.log`가 근거다.
수정 후 실제 Pi 1.4.0 SDK와 설치된 OpenCode 1.19.5의 native TUI 선택·적용
경로도 통과했다(`pi-node-pull-final.json`, `opencode-node-pull-final/result.json`).
두 native 시험은 assistant/UI fixture이며 모델이나 사람의 인증으로 세지 않는다.
OpenClaw 자체의 연결·loader·실제 큐 경로는 여전히 미완이다.

## OpenClaw 실험 도구 연결

`integrations/openclaw/`에 공통 스키마의 동기 catalog, native manifest,
대화별 XsmHost 연결부를 추가했다. 실제 native caller context의 sessionId를
conversation으로 사용하고, route/workspace 변경과 오래된 factory를 거부한다.
Session-end·plugin cleanup에서 epoch를 무효화하고 pending open을 정리한다.
Native 수신·UI를 광고하지 않는 pull-only이며 version 2 continuation은 미완이다.
Immutable snapshot에 세 파일이 포함되는 것도 설치 검사에 추가했다.

Fixture API + 실제 서버 subprocess 검사 4개가 DM/pull/ACK, 동일 route의
대화 분리, 동시 open, 종료/resume, 늦은 도구 거부, 취소·UI 부재·plugin 폐기를
확인했다. 최초 realpath/activity 필드 오독으로 2개 실패한 로그도 보존했다.
Epoch 검사 제거·route를 conversation으로 사용·catalog drift의 세 변이는
모두 검사를 실패시켰다(`openclaw-binding-mutations.json`).

고정 native 패키지는 별도 HOME/npm cache에 install script 없이 설치했다.
실제 2026.10.9 로더는 native conversation-access 권한 없는 agent_end hook을
거부했다. 이 권한을 자동으로 켜지 않고 명시적 허용이 있는 경우에만 turn
hook과 busy/idle 갱신을 사용한다. 기본 native 상태 관찰은 미완이다.

`probe-openclaw-loader.mjs`는 실제 고정 로더에서 21개 도구를 경고 없이
등록하고 metadata가 참여를 만들지 않음을 확인했다
(`openclaw-native-loader-current.json`). Host 내부 loader import는 probe에만
있고 제품은 공개 plugin API만 사용한다. Native 도구 execute·unload·one-shot
CLI·gateway 수명은 아직 검증하지 않았다.

최신 코드의 공통 264개(핵심 184, Python 28, Node 52)가 Python 3.14.6에서
35.452초에 통과했다(`openclaw-binding-current-py314.log`). 직전 코드의
Python 3.9.6 묶음은 53.946초에 통과했고, 이후 one-shot 도구별 조기 종료를
제거해 CLI 종료 시점의 native cleanup 검증을 미완으로 유지했다.
실제 native agent·주입·질문 UI·제품 설치기·worker·Linux·메신저와 전체 계획은
미완이며, 이 결과를 OpenClaw 전체 지원 완료로 세지 않는다.

## OpenClaw native 도구 실행과 폐기

실제 native resolvePluginTools 경로로 최초 실행했을 때 capture된 JS의
import.meta.url이 존재하지 않는 bin/xsm을 가리켜 ENOENT로 실패했다.
기본 명령을 native API의 원본 source에서 계산하도록 수정했다. 설치 loader가
명시적으로 넘기는 pinned command는 그대로 사용한다.

고정 2026.10.9 SDK의 실제 tool resolver·execute, 공개 global session hook,
registry disposal을 사용한 후속 probe가 통과했다. Context는 명시적 caller
fixture다. 같은 route의 두 UUID 분리·DM/pull/ACK·미연결 UI 거부·session-end·
이전 도구 거부·주소 보존/세대 교체 resume·폐기 후 전 참여 종료를 확인했다.
`openclaw-native-tools-first.log`, `openclaw-native-tools-expanded.json`에
실패와 성공을 구분했다. Host 내부 resolver/disposal import는 probe에만 있다.

공통 264개는 수정 후 Python 3.9.6에서 57.203초에 통과했다
(`openclaw-capture-fix-py39.log`). Native agent turn·모델·실제 사용자 UI·수신
주입·owned 설치·one-shot CLI·gateway·Linux·메신저와 전체 계획은 미완이다.

## OpenClaw 수신 admission의 native 저장소 실험

Route-only next-turn API는 metadata의 expectedSessionId를 검증하지 않았다.
Native 저장소의 대화를 교체한 뒤 이전 대화 ID metadata가 든 요청을 보냈을
때 교체된 대화의 queue에 수락됨을 재현했다. 자동 수신에는 연결하지 않았다.

Public patchSessionEntry의 최종 guard는 이미 교체된 대화의 준비된 쓰기를
거부했다. Guard를 제거한 변이는 실제 native SDK 검사를 실패시켰다.
추가 교체 실험은 같은 프로세스/별도 프로세스 × guard 유무의 4건이다.
같은 프로세스에서는 native 직렬화로 교체가 기다렸고, 별도 프로세스에서는
교체 후 native SQLite 상태 변경 검사가 쓰기를 거부했다. 뒤의 두 건은 사용자
guard 0회이므로 사용자 guard의 성공으로 세지 않는다.

`scripts/probe-openclaw-session-guard.mjs`, `openclaw-session-guard-final.json`,
`openclaw-session-guard-mutation.json`에 재현 경로와 수치를 남긴다.
원본 코드·사용자 native 프로필은 바꾸지 않았다. 이는 native SDK 저장소
fixture이며 자동 수신·실제 agent/reset UI와 전체 계획 완료 증거는 아니다.

## OpenClaw guarded context queue 연결

공개 native SessionEntry의 xsm queue를 공개 runtime.patchSessionEntry와 최종
assertCommitAllowed로 갱신한다. Binding 수명, native sessionId/lifecycleRevision,
취소, store, 등록 당시와 현재 prompt-injection 정책을 결속한다. Queue의 실제
본문·ID·metadata를 관찰한 뒤 공통 Node host가 admitted를 보고한다. Node
host pump는 native background context에서 시작하며 소비 ACK는 별도다.

같은 원문 묶음의 대기 중 injection은 재사용하며 타 plugin의 queue를 보존한다.
Native 한도 32개/최종 본문 32768 UTF-16 단위 초과는 거부하고 정본 claim을
반환한다. 큰 payload 분할, idle wake, 기본 표면의 FYI 경계, busy/now 전체
동작은 미완이다. Conversation-access 권한이 있는 agent-end 경계는 FYI를
옮기며, 실제 사용자 권한을 자동으로 켜지 않는다.

제어된 native seam 검사 8개를 빠른 묶음에 포함했다. 최종 guard·용량·수락
관찰·본문 관찰·등록 정책 거부를 제거한 다섯 변이를 모두 검출했다
(`openclaw-queue-complete-mutations.json`). 등록 정책 false가 빈 runtime 설정에
의해 무시되는 경로도 수정했다. 실제 SDK의 거부 fixture는 자동 queue 주입 없이
pull/ACK를 유지했고, 거부 확인을 제거한 native 변이는 실패했다
(`openclaw-native-queue-denied.json`, `openclaw-native-policy-mutant.json`).

최신 공통 272개(핵심 184, Python 28, Node 60)가 Python 3.14.6에서
37.623초에 통과했다(`openclaw-queue-policy-final-py314.log`).
Mac arm64 / Node 24.22.2 / protocol Python 3.14.6에서 실제 native queue 수락,
prompt 소비 helper, 명시적 ACK를 100/100 완료했다. Sender execute 직전부터
queue 관찰까지 p95 상한은 401.576ms이며 정본 저장 시간도 포함한다
(`openclaw-native-queue-100-current.json`). SDK caller와 prompt 소비는 fixture다.
모델·실제 native agent turn·idle wake를 실행하거나 인증한 결과가 아니다.

중간 강화 실행은 0/100에서 실패했다. `<sample=0>`이 안전 렌더링에서 보호
인코딩됐는데 raw 문자열로 비교한 fixture 오류였다. 실패 저장소의 원문 SHA-256
일치를 대조한 뒤 ASCII 표식으로 바꿨다. 실패 결과와 이전 100개, 재실행 100개를
섞지 않고 보존했다(`openclaw-native-queue-100-final.json`,
`openclaw-queue-failed-sample-analysis.json`). Native guard·실제 body 확인은
완화하지 않았다. OpenClaw의 owned 설치·큰 payload·wake·UI·worker와 P0–P5
전체 완료 기준은 여전히 미완이다.

## OpenClaw 큰 본문의 native 분할

단일 native entry의 한도를 넘는 본문을 Unicode 경계에서 분할하고, 끝 표식으로
native trim에 의한 공백 유실을 막았다. ACK는 마지막 별도 조각에 둔다.
모든 조각의 공간을 한 native patch에서 예약하며, 대기 중 묶음을 재사용하고
기존 묶음이 불완전하거나 수락 관찰에서 하나라도 빠지면 거부한다. Native 한도
32개 조각을 넘는 배치는 정본을 유지한 채 거부하며, 다중 turn/file 전환은 미완이다.

제어된 seam 검사 14개와 변이 9개가 통과했다. 변이는 최종 guard, 등록 거부,
실제 body 확인, 모든 조각 확인, 전체 공간 예약, surrogate 경계, trim 방지,
중복 억제, binding 수명을 제거해 각각 실패를 확인했다
(`openclaw-fragment-mutations.json`). 공통 278개는 Python 3.9.6에서 37.938초에
통과했다(`openclaw-fragments-final-py39.log`). 앞선 Python 3.14 표본 277개에는
후속 surrogate 경계 강제 검사 1개가 아직 없었으며 최신 278개와 구분한다.

실제 2026.10.9 SDK의 약 8만 UTF-16 길이 본문 100개가 모두 4개 조각으로
수락·prompt helper 소비됐고 명시적 ACK도 100개 완료됐다. Mac arm64 / Node
24.22.2 / protocol Python 3.14.6의 p95 상한은 701.295ms로 1초 기준을 통과했다
(`openclaw-native-large-100.json`). 총 조각 수는 400개다. SDK caller와 prompt
소비는 fixture이며 모델·실제 agent turn·wake 인증은 아니다.
일반 본문·주입 거부도 실제 SDK에서 재검사했다
(`openclaw-fragments-short.json`, `openclaw-fragments-denied.json`). Owned 설치,
worker·wake·UI·한도를 넘는 스트리밍과 전체 계획은 계속 미완이다.

## Inbox 건수 제한과 SDK 연속 읽기

공통 receive/service에 `xsm_inbox.limit`(정수 1–100)을 추가했다. CLI는
`inbox --limit`, MCP와 protocol은 같은 필드를 사용한다. 한 번 반환하는 렌더된
메시지·notice 수를 제한하며, 선택하지 않은 원문과 소비 ACK는 유지한다.
생략하면 기존 동작이다. OpenClaw 정적 catalog도 공통 스키마에서 재생성했다.
Inbox 설명은 특정 하네스 대신 등록된 대화와 native 수신 능력을 기준으로 바꿨다.

Python/Node 호스트는 `inbox_batch_size`/`inboxBatchSize`로 자동 수신을 제한한다.
한 번의 coalesced tick에서 5개 원문을 2·2·1로 가져오고 명시적으로 ACK하는
실제 서버 검사가 통과했다. Notice만 있는 가득 찬 배치가 반복되던 경로도
수정 전 실패로 재현하고, 원문 인수가 없으면 중지하도록 수정했다.
Runtime binding의 기본 배치 크기는 아직 바꾸지 않았다. Native queue 용량
재시도, 바이트 예산, transient notice 뒤의 공정한 진행은 미완이다.

초기 검사에서 protocol.validate가 numeric minimum/maximum을 무시하는 문제가
발견됐다. 전수 범위는 기존 wait 필드 4개와 새 inbox limit이었다. 범위를 적용하고
큰 Python 정수를 float로 변환하면서 OverflowError가 나는 경로도 수정했다.
MCP에서는 명시적 null·bool·범위 밖 값이 무제한 읽기로 바뀌지 않게 거부한다.
첫 core 실패와 소유 worker의 name이 fixture 인자명과 겹친 검사 오류를 원시
로그에 구분했다. Native SDK에서도 limit=1 도구 호출·DM/pull/ACK·수명을
통과했다(`inbox-batch-native-sdk.json`). Native caller는 여전히 fixture다.

TypeScript 컴파일과 CLI/MCP 19개 검사가 통과했다
(`inbox-batch-types-current.log`, `inbox-batch-cli-mcp-final.log`). 최신 공통 285개
(핵심 187, Python 30, Node 68)가 Python 3.14.6에서 36.216초에 통과했다
(`inbox-batch-complete-py314.log`). 직전 3.9.6 표본 283개/58.012초에는 후속
notice-only 비진행 검사 두 개가 아직 없었으므로 구분한다.
건수 제한 전달, CLI 전달, 두 SDK의 연속 읽기/비진행 중지, 숫자 범위/큰 정수,
MCP null 처리를 제거한 9개 변이는 모두 실패했다
(`inbox-batch-verified-mutations.json`). 첫 변이 하네스는 치환 위치가 두 곳이라
4개 실행 뒤 중단됐고, 이 실패와 부분 로그도 보존했다. 이 시점의 Python 3.14 UI 취소 검사에는
`CancelledError exception in shielded future` 경고가 남았으며, 아래 후속 수정으로
해결했다. Notice-only pack에 빈 ACK 안내를 붙이는 코드 경로는 Pi/OpenCode/
OpenClaw 세 연결부에서 확인했고, 아래 후속 수정에서 해결했다.

## Python 마지막 질문 대기자의 취소

마지막 대기자를 취소할 때 질문 Future에 CancelledError를 예외로 저장하고
있었다. Python 3.14 shield가 이를 오류로 기록하는 경로를 실제 서버 subprocess
검사에서 event-loop exception handler로 포착했고, 수정 전 실패를 확인했다
(`python-question-cancel-red.log`). Future.cancel로 실제 취소 처리하도록 바꿨다.
로그를 숨기는 예외 handler를 제품에 추가하지 않았다.

호스트 조정 검사 13개가 Python 3.9.6에서 10.858초, 3.14.6에서 6.277초에
경고 없이 통과했다(`python-question-cancel-green-{py39,py314}.log`). 다른 대기자
유지, 마지막 취소 후 서버 질문 pending/무응답, 새로운 질문 표시와 재시도를
포함한다. 공통 286개(핵심 187, Python 31, Node 68)가 Python 3.14.6에서
36.404초에 통과했다(`python-question-cancel-gate.log`).
이는 SDK 취소 경고의 해결이며 전체 P2나 native UI 인증 완료를 뜻하지 않는다.

## Claim-free native notice와 Pi idle 수락

Claim 없는 notice에도 세 연결부가 빈 token 배열의 ACK를 안내하고 있었다.
공통 Node SDK의 renderInboxPacket/inboxAcknowledgement로 렌더링을 통합해
실제 claim이 있는 경우에만 안내한다. OpenClaw의 큰 notice도 빈 ACK 조각을
붙이지 않으며 원래 본문과 framing을 유지한다. 수정 전 notice 검사 실패는
`native-notice-ack-red.log`에 보존했다.

실제 Pi 1.4.0 SDK notice 검사에서 추가 결함을 재현했다. Idle/non-waking
custom append는 app message_start를 내지만 extension message_start를 내지 않아,
native branch에 저장된 notice를 수락으로 관찰하지 못했다. 같은 native 세션의
현재 branch에서 custom type·delivery ID·전체 본문을 확인하도록 수정했다.
가짜 native event를 만들어 성공시키지 않는다.

`pi-native-notice-first.json`은 실패, `pi-native-notice-final.json`은 claim-free
notice와 뒤이은 정상 본문·native ACK 성공이다. OpenClaw 고정 SDK도 실제 queue,
prompt 소비 helper, 원문의 pending 유지와 정상 ACK를 통과했다
(`openclaw-native-notice.json`). OpenCode notice 경로는 실제 protocol 서버와
native API fixture에서 검사했고, 실제 1.19.5 SDK의 정상 전달 회귀 5회도 통과했다
(`opencode-native-notice-regression/result.json`). 모델과 사람의 동작은 fixture다.

공통 291개(핵심 187, Python 31, Node 73)가 Python 3.14.6에서 38.273초에
통과했다(`native-notice-gate-py314.log`). TypeScript 컴파일도 통과했다
(`native-notice-types.log`). 이는 notice 렌더링과 관찰 경로의 수정이며 native
default 배치·용량 retry·바이트 예산·실제 agent/UI와 전체 계획은 미완이다.

## Native 용량 거부의 자동 재시도

Python/Node SDK에 native callback 전용 RetryAdmission을 추가했다. 확실한
일시 거부는 claim을 반환한 뒤 기본 250ms(Node)/0.25초(Python) 후 새 token으로
다시 인수한다. 지연은 양수·최대 60초이며 대기는 RPC/UI를 막지 않는다.
종료·연결 실패는 대기를 취소한다. 일반 오류·권한 거부·원문 자체의 한도 초과는
자동 재시도하지 않는다. Direct natural boundary의 재시도는 아직 미완이다.

원문 인수 후 실패→같은 ID/새 token으로 재인수→명시적 ACK, 대기 중 종료 후
추가 인수 없음의 경로를 두 SDK의 실제 protocol subprocess에서 확인했다.
이전 일반 메시지가 다른 reader에 의해 소비된 사이 FYI만 남은 경우, 기존
notification을 근거로 FYI를 깨우던 경로도 수정 전 실패로 재현했다. 재시도에서
실제로 인수한 packet의 items.wake와 claims를 기준으로 wake를 결정한다.
Notice-only packet 역시 모델을 깨우지 않는다.

OpenClaw는 native queue가 꽉 찬 경우 patch를 게시하지 않고 guard를 재확인한
뒤 typed retry를 반환한다. Native API 밖에서 오류를 만들어 오류 직렬화에
분류가 소실되지 않게 한다. 실제 고정 SDK에서 32개 fixture 항목을 채운 다음
원문을 보냈다. 정본 previous_claim으로 인수 반환을 확인한 뒤 fixture 항목만
비웠으며, 새 메시지 없이 원문이 재인수·수락·prompt 소비·ACK됐다
(`openclaw-native-capacity-retry-first.json`). SDK retry 처리를 제거한 변이에서는
인수 반환 후 회복이 없어 실패했다(`native-retry-sdk-mutant.json`).

공통 297개(핵심 187, Python 34, Node 76)가 Python 3.14.6에서 41.191초에
통과했다(`native-retry-complete-gate.log`). TypeScript 컴파일도 통과했다
(`native-retry-types-final.log`). SDK의 FYI race 실패/성공 로그는
`native-retry-fyi-{node,python}-red.log`, `native-retry-{node,python}-final.log`에 있다.
Python 3.9.6의 호스트 조정 검사 16개도 14.887초에 통과했다
(`native-retry-python-final-py39.log`).
Native SDK caller와 소비는 fixture이며 모델·실제 agent turn 인증이 아니다.
FYI 경계 재시도, 바이트 예산, binding 기본 배치, 전체 P0–P5 기준은 미완이다.

## FYI 경계의 background retry

Direct natural boundary의 typed refusal도 백그라운드로 예약한다. 호출자는 실제
수락이 아직 없다는 RetryAdmission을 받고, 세 native hook은 이 예약된 오류만
처리해 현재 turn을 진행시킨다. 일반 오류를 숨기지 않는다. 완료 직후 새 신호가
들어오는 경우도 delivery task의 종료 시 pending flag를 다시 확인해 작업을
놓치지 않게 한다. 종료는 초기 지연과 반복 대기를 모두 취소한다.

실제 서버에서 FYI 거부→새 token 재인수→wake=False 유지→명시적 ACK와 초기
대기 중 종료를 두 SDK에서 검사했다. 수정 전에는 다음 수락이 없어 실패했다
(`fyi-boundary-{node,python}-red.log`). Wake metadata 누락을 active로 간주하던
fallback도 제거했고, 두 SDK에서 이를 되살린 변이는 실패했다
(`fyi-boundary-metadata-mutants.json`).

실제 OpenClaw 고정 SDK의 native agent_end hook에서도 32개 fixture queue를
사용해 FYI claim 반환 후 공간 확보만으로 수락·prompt helper 소비·ACK와 수명
정리를 통과했다(`openclaw-native-fyi-capacity-first.json`). Background 예약을
제거하면 hook은 반환하지만 이후 수락이 없어 실패했다
(`fyi-boundary-sdk-mutant.json`). 실제 사용자 구성·권한은 바꾸지 않았다.
Pi SDK notice/정상 ACK 회귀도 통과했다(`fyi-boundary-pi-regression.json`).

공통 303개(핵심 187, Python 37, Node 79)가 Python 3.14.6에서 43.299초에
통과했다(`fyi-boundary-complete-gate.log`). Python 3.9.6의 호스트 조정 19개는
17.725초에 통과했다(`fyi-boundary-complete-py39.log`). TypeScript 컴파일도
통과했다(`fyi-boundary-types.log`). Native caller/hook과 소비는 fixture다.
바이트 예산·native 기본 배치·권한 없는 표면의 FYI 경계·전체 agent/UI·P0–P5
완료 기준은 계속 미완이다.

## Inbox 바이트 예산·cursor와 OpenClaw 기본 배치

공통 receive/service·CLI·MCP·protocol에 max_bytes와 after_id를 추가했다.
UTF-8 렌더 본문과 join separator를 측정한다. 첫 항목 자체가 크면 단독으로
반환하며 원문은 자르지 않는다. 다음 원문이 예산을 넘으면 claim을 반환한다.
batch_limited/next_after로 이어 읽고, notice-only 앞 배치도 cursor를 전진시켜
뒤의 유효 원문을 읽는다. 대화 밖의 cursor나 사라진 cursor는 거부한다.

두 SDK에 inboxMaxBytes/inbox_max_bytes와 cursor 연속 읽기를 연결했다.
Native 경계에서 성공한 제한 배치의 나머지도 background로 진행한다.
OpenClaw 구현 기본값은 16개/512 KiB다. 이는 사용자 지정 기준이 아니라
native 최대 조각 수를 고려한 구현 값이다. 큰 원문 32개를 소비 없이 먼저 보낸
실제 SDK fixture는 2개씩 16묶음/96조각으로 모두 수락·소비·ACK했고 중복은
없었다(`openclaw-byte-burst-first.json`). 이 시험의 시간은 고의적인 소비 지연을
포함하므로 정상 상태 p95 인증으로 쓰지 않는다.

일반 100표본 재검사는 100초 외부 제한에서 수락 99/ACK 98로 종료됐다
(`openclaw-byte-default-100.json`). 미완으로 보존했으며, 종료 후 두 backend PID가
없음을 확인했다(`openclaw-byte-timeout-process-audit.json`). 첫 지연 약 0.38초에서
후반 약 1.33초로 증가했고, 소스에서 handoff 소유권 조회/전환이 누적 큰 JSON을
반복 파싱하는 것을 확인했다. 파일 세대가 같은 파싱 결과만 재사용하는 bounded
cache를 추가했다. Dev/inode/size/mtime_ns/ctime_ns/mode/uid/gid를 재확인하며,
소유권·token·lease·정책 검사는 생략하지 않는다. 반환 객체는 사본이며 자체
쓰기에서 무효화한다. 한도는 원본 파일 크기 합계 64 MiB와 최대 256개다.

Cache 검사 6개가 mtime 복원/in-place 수정, 별도 프로세스 claim 교체, 쓰기
실패, ACK 멱등성, 객체 분리와 메모리 예산 eviction을 확인했다. Python 3.9.6도
6개 통과했다(`handoff-cache-{final,py39}.log`). Byte/cursor 변이 6개와 cache 변이
4개를 모두 검출했다(`inbox-byte-mutations.json`, `handoff-cache-mutations.json`).
초기 cache eviction 검사는 한 record보다 작은 예산을 잘못 잡아 실패했고,
실제 파일 크기를 기준으로 fixture를 고쳤다. Legacy 읽기의 receipt 순서 변경도
회귀가 찾아 수정했으며 바이트 예산이 없는 기존 순서를 유지한다.

최신 공통 317개(핵심 197, Python 39, Node 81)가 Python 3.14.6에서
49.932초에 통과했다(`inbox-byte-budget-final-gate.log`). CLI/MCP 20개와 TypeScript
컴파일도 통과했다(`inbox-byte-cli-mcp-final.log`, `inbox-byte-budget-types.log`).
수정 후 같은 큰 원문의 실제 native SDK 100/100 수락·소비·ACK가 완료됐고 p95
상한은 519.369ms로 1초 기준을 통과했다(`openclaw-byte-cache-100.json`).
Mac arm64/Node 24.22.2/protocol Python 3.14.6이며 caller와 prompt 소비는 fixture다.
첫 oversized 원문 자체가 native 32조각을 넘는 전송, 다른 binding 기본 배치,
권한 없는 표면의 FYI 경계·실제 agent/UI·Linux·전체 P0–P5는 미완이다.

## Pi/OpenCode native 기본 배치

두 receiving binding에도 16개/512 KiB UTF-8 기본값을 연결했다. 전체 배치를
한 번에 넘기던 경로를 공통 SDK의 제한 읽기·cursor·retry로 진행한다.
Pi 실제 SDK는 30만 자 원문 3개를 native branch의 서로 다른 입력 3개로
수락하고 native 도구로 ACK 3개를 보냈다(`pi-default-budget-batch.json`).
OpenCode는 실제 protocol 서버와 native API fixture에서 같은 backlog를
입력 3개로 나누고 wake가 없음을 확인했다. 두 binding에서 기본 예산을
제거한 변이는 모두 실패했다(`native-default-budget-mutants.json`).

새 Pi owned profile의 자동 발견/snapshot 실행에서 native 수락 100/100을
완료했다. Mac/Pi 1.4.0/protocol Python 3.14.6의 p95 상한은 431.056ms다
(`pi-batch-defaults-native-100/result.json`). OpenCode 1.19.5 실제 SDK는 수락과
scripted assistant의 native ACK를 100/100 완료했고 p95 상한은 349.474ms다
(`opencode-batch-defaults-native-100/result.json`). Pi의 수락 표본과 OpenCode의
ACK 표본은 구분한다. 모델과 사람을 실행한 인증은 아니다.

공통 318개(핵심 197, Python 39, Node 82)가 Python 3.14.6에서 48.810초에
통과했다(`native-batch-defaults-final-gate.log`). Pi notice/정상 ACK 회귀와
OpenCode 정상 5회 회귀도 별도 통과했다. Native 모델 협업·Linux·원격·worker·
UI의 전체 수용 조건과 P0–P5는 미완이며, 새 릴리즈나 전체 runtime 지원을
선언하지 않는다.


## Hermes 설치용 고정 백엔드 진입점

`register(context, *, command=None, env=None)`가 설치 로더에서 지정한 명령과
환경을 `HermesBinding`에 전달한다. 기존 `register(context)` 호출은 유지한다.
새 검사 2개는 변경 전 실패했고 변경 후 통과했다. 격리 환경의 표식으로
operations/list 등록 과정과 실제 xsm_inbox 호출의 두 백엔드 프로세스가
지정 명령·환경을 사용한 것을 확인했다. 실패한 백엔드 등록은 coordinator
스레드를 종료한다. Python 3.9.6의 Hermes 검사 3개도 통과했다.

Python 3.14.6의 공통 검사 320개(핵심 199, Python 39, Node 82)가 48.880초에
통과했다(`hermes-pinned-registration-gate.log`). Hermes 0.22.5 실제 플러그인
발견·등록·도구 호출·수명주기 회귀 8개도 통과했다
(`hermes-pinned-register-native/result.json`). Native 호출자는 fixture이며
모델·사람 UI·push 수락을 실행한 인증은 아니다. Hermes 소유권 기반 설치·
업데이트·제거와 활성화 상태 보고는 아직 미구현이다. 전체 P0–P5도 미완이다.
