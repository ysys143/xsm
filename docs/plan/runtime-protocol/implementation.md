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
  재호출해야 적용한다. 네이티브 UI 연결과 실제 사용자 답 검증은 아직 미완이다.
  UI 능력이 없는 호스트와 네이티브 transcript 복구 대체는 `-32004`로 거부한다.
- Python 3.9+ 클라이언트, 실행 가능한 Node 모듈과 TypeScript 타입,
  전송 fixture 및 실제 서버 subprocess 검사.
- 실험 명세·요청 스키마·README 연결. 안정된 호환성 보장은 아직 아니다.

## 단계별 판정

| 단계 | 상태 | 남은 조건 |
|---|---|---|
| P0 계약·현황 | 부분 구현 | 전체 기능별 normative 스키마, 독립 구현 적합성, 안정판 API 감사 |
| P1 공통 서비스 | 부분 구현 | CLI 추출, 일반 원격 신원, 네이티브 UI 연결, 비동기 작업 수명 |
| P2 SDK·검사기 | 부분 구현 | 독립 구현 적합성, 전체 오류/취소 계약 (Python↔Node 교차 시험 통과) |
| P3 Pi·OpenCode | 부분 구현 | Pi RPC·SDK·수신 경로 검증. Pi 소유 설치·갱신·재개·제거 검증. Pi 워커·자동 재접속과 OpenCode는 미완 |
| P4 Hermes·OpenClaw | 미구현 | 안정판 API 결손 해소, 게이트웨이 시험 경계, 전체 기능 |
| P5 통합·배포 | 미실행 | Linux, 30개 방향 조합, 동종 세션, 원격, 네이티브 p95, 메신저, 전체 회귀 |

## 실제 검사

`python3 scripts/check-protocol.py`는 실행 전에 HOME/XSM_HOME/CODEX_HOME/
CLAUDE_CONFIG_DIR를 격리하고 API 자격 증명과 실행 중 세션 환경을 넘기지 않는다.
현재 핵심 121개 + Python 클라이언트 15개 + Node 클라이언트 20개가 통과했다.
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
