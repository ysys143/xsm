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
| P3 Pi·OpenCode | 미구현 | 실제 기존 세션·사용자 UI·워커·재개·설치 전부 |
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
