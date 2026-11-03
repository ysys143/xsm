# 공개 호스트 프로토콜 구현 기록

상태: **미완**. 전체 계획 완료·추가 런타임 지원·릴리즈를 주장하지 않는다.
완료 범위는 [승인된 원래 계획](plan.md)의 전체 조건을 따른다.

## 확정 기준

- 공개 명세와 적합성 검사기로 독립 구현 가능해야 한다.
- 기존 기능 전체, macOS/Linux, 로컬 UI와 메신저 세션을 유지한다.
- 모델·외부 메신저 없는 핵심 검사 전체 120초 이내.
- 로컬 저장→실제 네이티브 입력 큐 수락 p95 1초 이내. 모델 응답과 외부 플랫폼 시간 제외.
- 승인·런타임 버전·지원 범위를 임의로 대체하지 않는다.

## 현재 구현

- `xsm protocol serve --stdio`: 버전 협상, 연결별 불투명 세션 핸들,
  프로필/대화 분리, 수명 락, 상태 갱신·종료, 세션별 이벤트 구독.
- 초기 작업 처리 메서드 26개와 공개 스키마를 MCP 모듈 밖의 공통 서비스로 이동했다.
  일반 프로토콜은 MCP transport를 import/상속하지 않는다. CLI 전체 서비스 추출은 아직 미완이다.
- CLI와 모델 frontend가 팀·보드·send·질문/handshake·doc·handover·owned dispatch와
  프로젝트 join/leave/link/reach의 공통 서비스를 사용한다. Inbox/ACK 정본 처리도
  기존 receive를 공유한다. 각 frontend의 caller 확인·실제 답 수집·출력은 유지한다.
- 일반 참여자 DM은 기존 정책과 정본 handoff 저장소를 사용한다.
  알려지지 않은 런타임을 Codex 전송으로 보내지 않는다.
- 수신 알림·네이티브 큐 보고·최종 소비 ACK 분리. FYI는 알림을 발생시키지 않는다.
- `user-decisions` 호스트 질문·응답 결속을 구현했다. 답 저장 뒤 원 작업을
  재호출해야 적용한다. Pi/OpenCode native UI fixture는 통과했으며, 실제 사용자
  응답 검증과 Hermes/OpenClaw UI 연결은 미완이다.
  UI 능력이 없는 호스트와 네이티브 transcript 복구 대체는 `-32004`로 거부한다.
  Python coordinator는 [명시적 UI 보류/해제](deferred-host-ui.md)를 지원하지만
  Hermes native 질문 결속과 사람 UI 검증을 완료한 것은 아니다.
  후속 [Hermes opt-in 질문 bridge](hermes-native-questions.md)는 native AIAgent의
  model0/합성 callback까지 연결했다. 실제 사람·모델·메신저 UI 전체 행렬은 미완이다.
  별도 [Telegram 실제 사용자 선택](hermes-telegram-ui-live.md)은 standalone
  adapter/AIAgent 단일 질문에서 확인했다. GatewayRunner 전체 UI는 미완이다.
- Python 3.9+ 클라이언트, 실행 가능한 Node 모듈과 TypeScript 타입,
  전송 fixture 및 실제 서버 subprocess 검사.
- Pi/OpenCode native 연결·설치·UI fixture, Hermes native 도구·격리 설치·대화별 복구,
  OpenClaw의 guarded native context queue prototype이 있다. 런타임 전체 지원
  인증이나 모든 표면의 연결 완료를 뜻하지 않는다.
- 실험 명세·요청 스키마·README 연결. 안정된 호환성 보장은 아직 아니다.
- Pi/OpenCode의 실제 구독 모델 정상 경로는 quota 거부로 미완이다.
  [실제 실패와 별도 model0 검증](pi-opencode-subscription-model.md)을 구분하고
  관측자 종료 시 미관측 요청을 unknown으로 남기는 relay 검사를 보강했다.
- 발견 결과의 로컬/원격 후보·관측·부분 실패 스키마와 공개 stdio discovery
  suite를 추가했다. [발견 계약 검증](discovery-contract.md)의 표본이며 전체
  operation 결과 계약이나 물리 원격 행렬 완료를 뜻하지 않는다.
- 고정 native provider catalog에 Hermes/OpenCode/Pi/OpenClaw owned 실행을 연결했다.
  Claude/Codex legacy 경로와 공통 journal·동시성·범위 정책을 공유하며 native
  binding/control, 실행 중 취소와 보존 출력 readback을 구현했다. OpenClaw는
  별도 native host 수명과 frontend 종료 뒤 조회·gateway 재시작 후 run별 history
  회수에 model0 및 macOS 실제 구독 모델 증거가 있다. 답변 없는 종료의 execution
  lease 정리는 model0 증거다. [실제 모델 표본](openclaw-subscription-model.md)을 구분한다.
  [Native worker 경계](native-worker-boundary.md), [OpenClaw 상세](openclaw-owned-session.md),
  [Linux 검증](linux-validation.md)의 source별 범위를 따른다. Classic spawn/pane는
  여전히 Claude/Codex이며 worker 전체 UI/실제 모델/원격 행렬 인증은 미완이다.
- Hermes의 실제 native agent와 macOS Telegram 개인 대화에서 pull→명시적 ACK→
  reply→Telegram 전달을 확인했다. [별도 기록](hermes-telegram-live.md)의 표본이며
  native push/UI/worker나 전체 메신저 지원 완료를 뜻하지 않는다.

## 팀 조회 결과 계약 — 2026-11-03

`xsm_team list/show`의 공개 projection 스키마와 예시를 추가했다. 요청 action으로
정의를 선택하며 라벨과 내부 멤버 레코드를 구분한다. 정본 Connection dispatch에서
빈 목록→create→목록→상세 4개 응답을 관측했고 checker가 모두 검증했다.
예시 3개 통과·잘못된 구조 9개 거부를 확인했다. running 타입과 내부 home 필드
허용 변이 2개도 checker가 검출했다. `python3 -B -m unittest tests.test_protocol`은
58개를 9.854초에 통과했다. 원시는
`deliverables/protocol-foundation/team-contract/`에 있다. 이는 stdio 또는 native
행렬 인증이 아니며 보드 조회와 나머지 결과 계약은 미완이다.

## 보드 조회·공개 stdio 협업 계약 — 2026-11-03

[보드 계약 검증](board-contract.md)에 xsm_board log/decisions의 스키마와
공개 collaboration suite를 기록했다. Stdio28개 검사와 실제 프레임36개 검증,
보드 예제4개·거부15개 및 schema 변이2개를 확인했다. Mac core863개는
100.880초에 통과했다. 질문은 synthetic host
fixture이며 실제 사람·native UI 인증이 아니다. 팀/보드 조회의 공개 요청 경로를
함께 검사하지만 나머지 operation 계약과 전체 계획은 미완이다. 후속 원격
수신 fixture가 드러낸 from_machine 누락을 보완했고 보드 예제5개·거부16개를
확인했다. 합성 원격 입력의 로컬 수신이며 물리 원격 표본은 아니다.
보완 전 고정5239fe0의 Linux core863개도3.11에서84.129초,3.14에서
105.672초에 통과했고 VM 종료를 확인했다. 후속 스키마의 Linux 개발
validator 실행으로 소급하지 않는다.

## 문서 작업 공개 계약 — 2026-11-03

[문서 계약 검증](doc-contract.md)에6개 xsm_doc action의 result schema와
공개 documents suite를 기록했다. Stdio28개·프레임32개·예제7개 통과와
거부14개를 확인했다. Wip 후보 은폐와 limit total 변조를 검사하며, 실제
사람 endorsement나 native runtime 전체 행렬을 뜻하지 않는다. Mac core866개는
103.779초에 통과했고 작성자의 실제 session ref 검사도 공개 경로에서 확인했다.
고정891dae3의 Linux core866개도3.11에서87.832초,3.14에서109.868초에
통과했으며 격리 VM 종료를 확인했다.

## 송신 결과 공개 계약 — 2026-11-03

[송신 계약 검증](send-contract.md)에 단일/그룹 producer metadata와
file/inline material, 첨부 오류의 계약을 추가했다. 공개 stdio30개와 frame42개를
검증했고 구조 예제6개·거부15개 및 오류 예제1개·거부2개를 확인했다. 저장을
runtime 도달로 오인하는 등 wire 결함3종을 검출했다. ACK 후 resend 기대가
틀린 최초 실패는 보존했고 기존 서버 의미를 유지했다. Native/remote/UI/전체
계획 완료를 뜻하지 않는다. Mac core870개가107.777초에 통과했고
실제 wire의 manifest 결속/오류 body_sent 변이2개도 검사기가 거부했다.
고정00ad234의 Linux core870개도3.11에서88.334초,3.14에서112.987초에
통과했으며 격리 VM 종료를 확인했다.

[결과 계약 범위 전수표](result-contract-coverage.md)는 공개22개 operation 중
domain schema가 있는 operation14개(그중 team/board는 일부 action)와
미정의8개를 구분한다.
이는 완료율이나 native 지원률이 아니다.

## 핵심 검사 적합성 묶음 분리 — 2026-11-03

[핵심 검사 병렬화](core-conformance-parallel.md)는 외부 stdio 적합성을 별도
격리 프로세스로 실행한다. 전체 MODULES와 SDK/Node/독립 participant를 유지하며
공통120초 deadline도 바꾸지 않았다. 누락/offset 충돌 변이2개를 회귀 검사가
검출했고 Mac core871개는88.867초에 통과했다. 통계적 성능이나 native p95
측정이 아니다. 고정e5fec62의 Linux core871개도3.11에서82.197초,
3.14에서102.236초에 통과했고 VM 종료를 확인했다. 원래 전체 계획의
나머지 조건은 계속 미완이다.

## 그룹 질문 소유자·claim 복구 — 2026-11-03

[그룹 질문 복구](question-group-owner.md)는 외부 그룹의 자식을 poll한 뒤
waiting_on 내부 오류가 나던 공통 경로와, MCP/protocol 출력이 그룹 reply claim을
다시 단일 질문으로 처리해 root aggregate를 비우던 경로를 수정했다. 기존 CLI
및 단일 질문 의미를 유지하며 늦은 답·정본 ACK·이력 보존을 검사한다.
Public questions suite32개와 frame42개를 확인했다. 실패한 재현/시험 driver
표본도 보존했다. Mac core881개는91.310초에 통과했다. Ask/status/connect의
normative 결과 schema는 계속 미완이다. 고정2ad7a23의 Linux core881개도
3.11에서83.346초,3.14에서104.917초에 통과했고 VM 종료를 확인했다.

## 질문·회신 결과 계약 — 2026-11-03

[질문 계약 검증](question-contract.md)은 ask/status/connect의 단일/그룹/목록/
선택 거부와 원격 Gateway·file 증거를 정의한다. 실제 stdio42개 frame, 예제22개와
거부20개를 확인했다. Private 경로 필드 금지 및 집계 결속을 약화한 변이3개도
검출했다. Mac core881개는90.946초에 통과했다. 구조와 내부 결속의 검증이며
실제 원격/사용자 승인/native 지원 인증은 별도다. 고정d785f8e의 Linux
core881개도3.11에서83.571초,3.14에서106.231초에 통과했다. 각 환경의
새 stdio42개 frame을 offline 개발 validator로 검증했고 VM 종료를 확인했다.

## 공개·선택 호스트 UI 승인 — 2026-11-03

[호스트 승인 연결](selection-host-ui.md)은 publish/범위 밖 connect를 공통
user-decisions/MCP elicitation에 연결했다. 답 저장과 적용을 분리하며, permission
효과만 journal하고 handshake는 live 조회한다. 표시 이름/no-op 철회로 거부를
새 승인으로 바꾸지 않고, 실제 철회 뒤 재공개는 새 승인이 필요하다. 합성 host
stdio28개/frame46개와 Mac core893개(96.634초)를 확인했다. Publication 결과
schema6개 예제/거부8개도 추가했다. 고정9b81010의 Linux core893개도
3.11에서86.354초,3.14에서111.113초에 통과했고 새46개 frame의 offline schema
검증 및 VM 종료를 확인했다. 실제 사람/native/remote 전체 인증은 별도다.

## 사람 결정 상태 결과 계약 — 2026-11-03

[결정 상태 계약](decision-status-contract.md)은 목록·상세·취소 거부와 기존 입력
승인 진단을 정의한다. Stdio45개/frame58개, 예제27개와 잘못된 결과16개 거부를
확인했다. 사람이 봤다고 잘못 주장하거나 관측 없는 applied를 허용하는 변이2개도
검출했다. Mac core893개는94.949초에 통과했다. 사람·native·전체 원격 인증은
아니며 원래 전체 계획은 계속 미완이다. 고정66ba4cc의 Linux core893개도
3.11에서86.700초,3.14에서109.477초에 통과했고, 새58개 frame의 offline schema
검증과 VM 종료를 확인했다.

## Worker grant producer metadata — 2026-11-03

[승인 발급 metadata](grant-producer.md)는 표시 문장 대신 구조화된 발급 정보를
제공하고 적용 결과 재조회에서도 같은 ID를 보존한다. Grant ID가 다른 상태 파일을
.used로 이동시킬 수 있던 결함도 재현해 파일 작업 전 형식 검증으로 막았다.
Mac core895개가75.611초에 통과했다. 결과 schema와 실제 worker 전체 인증은
아직 미완이다. 고정e93fac1의 Linux core895개도3.11에서88.522초,
3.14에서110.004초에 통과했고 VM 종료를 확인했다.

## Worker grant 결과 계약 — 2026-11-03

[발급 결과 계약](grant-schema.md)은 발급 snapshot/host question/기존 text-only를
정의한다. Stdio24개/frame30개, 예제3개/거부10개 및 schema 변이1개를 확인했다.
Mac core898개가74.697초에 통과했다. Structured snapshot은 실제 worker 실행이나
현재 유효성을 인증하지 않는다. 고정baf9c17의 Linux core898개도
3.11에서89.472초,3.14에서113.382초에 통과했고 새30개 frame의 schema 검증과
VM 종료를 확인했다. 전체 계획은 계속 미완이다.

## Worker 개별 승인 요청 결속 — 2026-11-03

[개별 요청 결속](worker-approval-binding.md)은 id 없는 호출의 cache/질문 대상을
미리 고정하고 request+worker fingerprint를 반영 잠금 안에서 검증한다. 같은 요약의
다른 요청이나 변경 input에 이전 답을 쓰지 않는다. 요청 id의 경로 해석도 막았으며
답변 snapshot metadata를 추가했다. 명시적 host deny의 worker 전달도 보완했고
최종 관련129개/11.792초와 Mac core906개/78.316초를 확인했다. 실제 native worker
실행 및 approve 결과 schema와 전체 계획은 미완이다. 고정fd5229d의 Linux
core906개도3.11에서89.581초,3.14에서112.965초에 통과했고 VM 종료를 확인했다.

## 단계별 판정

| 단계 | 상태 | 남은 조건 |
|---|---|---|
| P0 계약·현황 | 부분 구현 | Operation별 오류 data·취소 의미 계약, 독립 구현 적합성, 안정판 API 감사. Catalog22개와 team9/board7 action의 성공 결과 구조는 정의 |
| P1 공통 서비스 | 부분 구현 | 남은 CLI 추출·전체 작업 수명/오류 계약. Owned native provider/control은 연결했으나 classic/TUI 등 실행 모드 전체는 미완. 일반 참여자 실제 QUIC 표본과 전체 runtime 행렬을 구분 |
| P2 SDK·검사기 | 부분 구현 | 독립 구현의 전체 계약 적합성·전체 오류/취소 계약. Python↔Node 교차 시험 및 고정 공개 입력에 대한 독립 구현 표본은 통과 |
| P3 Pi·OpenCode | 부분 구현 | 연결·수신·설치·대화 수명·자동 재접속과 owned worker 정상/취소/readback의 native 증거가 있음. 실제 사용자 UI·classic/TUI worker와 전체 실행 모드·busy/now 우선순위 등 미완 |
| P4 Hermes·OpenClaw | 부분 구현 | Hermes macOS 실제 agent/Telegram pull과 native owned admission/generation 취소 증거. OpenClaw macOS 실제 구독 모델의 owned/recovery/plugin 송신과 Linux/model0 증거. Native push/idle wake·전체 UI/모델/작업 모드와 진행 중 restart lineage는 미완 |
| P5 통합·배포 | 부분 검증 | Mac/Linux core와 source별 native 표본 통과. 최근 Linux cold batch의 receiver stale 1건은 재현·원인 미확정.30방향·동종·물리 원격·전체 p95·UI/실제 모델/메신저·설치/rollback 전체 행렬 미완. Telegram 단일 승인 개인 대화와 Discord 미실행을 구분 |

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

## 초기 확인의 선행 조건과 당시 미실행 항목

Reason의 Hermes 통합은 다음 API를 요구한다:
`session_key`, `session_cwd`, `session_surface`, `session_supports_async_delivery`,
`is_interrupted`, `inject_message`.
Hermes v0.22.5의 `hermes_cli/plugins.py`에는 이 중 `session_key`,
`session_supports_async_delivery`, `is_interrupted` 정의가 없다.
이는 Reason 통합의 그대로 이식을 막는다. 안정판에 다른 구현 경로가 전혀
없다는 증거는 아니며, 미릴리즈 빌드로 자동 변경하지 않는다.

근거: [고정 안정판](https://github.com/NousResearch/hermes-agent/blob/v0.22.5/hermes_cli/plugins.py),
[Reason 고정 통합](https://github.com/reason-machines/reason-network/tree/bcf045cf7eadcbff25965fd6b12afeb88ab819ea/integrations/hermes).

초기 조사 당시 이 머신에서 실행 파일은 Pi만 발견했다. OpenCode/Hermes/OpenClaw 설치,
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


## Hermes 소유권 기반 디렉터리 설치

Hermes의 두 파일 플러그인을 `protocol install/inspect/uninstall hermes`에
연결했다. 파일별 write-ahead 해시, no-follow 디렉터리 접근, 수정 보존,
중단된 설치 복구와 업그레이드 중 이전 실제 loader 스냅샷의 prune 방지를
검사한다. 설정·활성화 목록·권한과 디렉터리의 다른 파일은 유지한다.

공통 검사 325개(핵심 204, Python 39, Node 82)가 Python 3.14.6에서
49.746초에 통과했다(`hermes-owned-install-gate.log`). 이후 추가한 업그레이드
복구·중간 디렉터리 symlink 검사 2개를 포함한 설치 검사 27개는 Python
3.9.6과 3.14.6에서 통과했다(`hermes-owned-install-tests-final.log`).
소유권 해시 검사를 제거한 변이는 사용자 편집 보존
검사에 실패했다(`hermes-install-ownership-mutant.json`). 실제 Hermes 0.22.5의
설치 스냅샷 발견·호출·수명·제거 9개도 통과했다
(`hermes-owned-install-native-canonical/result.json`). 최초 native 실행은
경로 alias 비교 때문에 실패했으며 로그를 보존했다.

활성화는 operator opt-in이며 실제 설정의 활성화 상태 판독, 실행 중 Hermes
컴포넌트의 스냅샷 lease, native push/UI/worker/agent와 Linux 검증은 미완이다.
전체 P0–P5를 완료로 판정하지 않는다.

## Hermes 로드 수명과 snapshot lease

설치된 Hermes 플러그인이 세션 없이 로드만 된 상태에서도 이전 스냅샷을
보존하도록 `hermes-plugin` lease를 연결했다. 고정 Python의 자식 프로세스가
native 부모 PID·UTC/C 시작 시각과 실제 snapshot root를 확인한다. 등록 실패나
native unload에서 coordinator를 닫은 다음 자신의 정확한 lease만 해제한다.
해제 시 부모가 다르거나 내용이 수정된 기록은 보존한다.

실제 Hermes 0.22.5의 설치 프로브 11개가 통과했다
(`hermes-component-lease-native/result.json`). Native discovery 직후 소유
설치 파일을 제거해도 같은 snapshot의 도구 호출·세션 수명은 유지됐고,
unload 뒤 lease 파일은 남지 않았다. Lease 확보를 무력화한 변이는 native
검사에 실패했다(`hermes-component-lease-mutant/result.json`). 별도 prune
검사는 설치 loader와 세션 없이도 살아 있는 Hermes lease가 이전 snapshot을
보존하는 것을 확인한다. Python 3.9.6 관련 검사 38개도 통과했다
(`hermes-component-lease-python39.log`).

공통 329개(핵심 208, Python 39, Node 82)는 Python 3.14.6에서 51.959초에
통과했다(`hermes-component-lease-gate.log`). 현재 활성화 설정 판독·native
push/UI/worker/실제 agent·Linux와 전체 P0–P5는 미완이다. Native 실행은
명시적 caller fixture이며 모델이나 사람의 UI 응답을 시험하지 않았다.

## 외부 stdio 수명 적합성 검사

`scripts/conform-host-protocol.py`는 xsm/SDK import와 정본 저장소 직접 조회
없이 후보 executable의 stdio만 검사한다. 새 격리 홈과 작업 폴더에서 두
후보 프로세스를 실행하고 초기화·descriptor·불투명 신원·프로필 분리·
connection-local handle·단일 live owner·close/reopen·EOF 소유권 해제의
16개 계약을 확인한다. 실제 서버의 최종 결과는
`blackbox-lifecycle-server-final.json`이며 16개 모두 통과했다. 첫 실행은
shell launcher를 Python source로 넘겨 실패했으며 그 결과도 보존했다.

xsm을 import하지 않는 stdlib 최소 수명 fixture에서도 16개가 통과했다.
고정 세대·다른 pipe의 handle 허용·수명 락 제거 변이는 각각 해당 검사에서
실패한다. 부모의 가짜 credential이 후보에게 전달되면 fixture가 거부한다.
검사기 자체 검사 4개는 Python 3.9.6과 `-O`에서도 통과했다. 동일 작성자의
불완전한 fixture이므로 제3자의 전체 독립 구현 인증으로 보지 않는다.

공통 333개(핵심 212, Python 39, Node 82)는 Python 3.14.6에서 51.461초에
통과했다(`external-conformance-gate.log`). 공개 사용법과 정확한 16개 계약은
`docs/protocol/conformance.md`에 기록했다. 전체 normative method/result/error
schema, operations·delivery·decision 적합성, 독립 작성자의 전체 구현과
P0/P2 및 P1/P3–P5의 나머지는 여전히 미완이다.

## 외부 전달·claim 복구 계약 검사

외부 검사기에 `--suite messaging`을 추가했다. 기본 수명 16개에 원문·Unicode
보존, 타 소비자 ACK 거부, admission의 claim 결속, 큐 보고와 소비 구분,
claim 해제·재획득·토큰 교체, 이전 세대 토큰 거부, admitted 원문 복구,
명시적 ACK와 소비 후 inbox 제거의 13개를 더해 29개를 검사한다. 실제
서버가 모두 통과했다(`blackbox-messaging-final.json`). 최초 검사는 타 소비자
ACK의 결과를 빈 배열로 오독해 실패했다. 실제 계약인 -32602 거부를 검사하도록
고쳤으며 최초 결과도 보존했다(`blackbox-messaging-first.json`).

실제 서버를 경유하는 test proxy가 admission 시 자동 소비, claim 토큰 재사용,
타 소비자 ACK 성공 응답의 3개 결함을 주입하면 각각 검사에 실패한다. 특히
자동 소비는 acknowledged=false 응답을 유지해도 재접속 뒤 원문 유실로
검출된다. 모델·native queue를 실행한 검사는 아니며 내부 저장소를 읽지 않는다.

공통 337개(핵심 216, Python 39, Node 82)가 Python 3.14.6에서 54.504초에
통과했다(`blackbox-messaging-gate.log`). 검사기 8개는 Python 3.9.6 -O에서도
통과했다(`blackbox-messaging-optimized.log`). 이후 소비 후 검사를 claims뿐
아니라 messages도 비었는지로 강화했고, 최종 검사기 8개와 실제 서버 29개를
다시 통과했다(`blackbox-messaging-final-tests.log`, `blackbox-messaging-final.json`).
전체 normative schema·decision/operation 적합성·독립 구현과 P0–P5의 남은
수용 조건은 미완이다.

## 공개 요청 메서드 스키마와 서버 경계

기존 요청 스키마는 11개 메서드 중 5개만 params 정의에 연결되어 있었다.
초기화·작업 목록·세션 갱신/종료·이벤트 구독·작업 호출의 6개를 추가해
모든 메서드를 연결하고 구조 예제 11개를 제공한다. delivery.report의
알 수 없는 필드도 닫았다. 서버는 REQUEST_FIELDS로 메서드별 허용 필드를
공통 검사하며, 반복 초기화·미초기화 오류의 우선순위는 유지한다.

변경 전 unknown 필드가 붙은 session.close가 실제로 참여를 닫는 것을
재현했다(`request-fields-red.log`). 수정 후에는 상태 변경 전에 -32602로
거부한다. 공개 스키마의 메서드·필드 표와 실제 서버 표가 일치하는지도
stdlib 검사에서 확인한다. 관련 Python 3.9.6 검사 42개가 통과했다.

개발용 `scripts/check-protocol-schema.py`는 이미 설치된 jsonschema 4.26.0의
Draft 2020-12 검증기로 정상 11개와 오류 41개를 대조했다
(`request-schema-validation.json`). operation.call 결속을 지운 격리 사본에서는
검사기가 실패했다(`request-schema-binding-mutant.json`). 외부 검증 패키지는
서버·SDK·빠른 gate의 의존성으로 추가하지 않았다.

공통 340개(핵심 219, Python 39, Node 82)는 Python 3.14.6에서 54.986초에
통과했다(`request-schema-gate.log`). 요청 구조와 실행 시 의미 검증의 차이는
`docs/protocol/request-contract.md`에 기록했다. 전체 작업별 인자/결과·응답·
알림 스키마, 독립 전체 구현과 P0–P5의 남은 조건은 미완이다.

## 공개 응답·알림 구조와 실제 wire 대조

`output.schema.json`은 성공/오류 응답과 events/available·decision/request의
구조를 정의한다. x-methodResults로 11개 메서드의 결과 정의를 연결하며
응답 ID와 원 요청 메서드를 대조해 검증한다. operation.call의 작업별 결과는
현재 임의 JSON으로 남아 있어 전체 작업별 결과 계약 완료를 뜻하지 않는다.
결정 결과의 status도 구조만 검사하며 사용자 응답·효과 적용 의미는 별도다.

구조 예제 14개(11개 결과·오류·알림 2종)와 오류 구조 9개를 표준 검증기로
대조했다. 실제 stdio events suite는 수명·전달 29개에 알림 결속·원문 유지·
명시적 ACK 3개를 추가해 32개를 통과했다. 실제 frame 38개는 9개 메서드의
정상 응답과 events/available 알림 1개를 포함하며 전부 스키마에 맞았다
(`output-schema-events-wire.json`, `output-schema-final-validation.json`).
사용자 질문 알림과 decision.response/abandon 정상 결과는 이 실행에서
예제로만 검증했다. Native UI나 실제 모델의 소비를 실행한 인증은 아니다.

Challenge 필수 조건을 제거하거나 admission에서 acknowledged=true를 허용한
격리 스키마 변이는 모두 검출됐다(`output-schema-mutants.json`). 최초 공통
검사와 Python 3.9 검사는 시험 proxy가 유휴 알림을 읽지 못해 실패했다
(`output-schema-gate.log`, `output-schema-python39.log`). 정상 경로는 실제 서버에
직접 연결하고 proxy는 결함 주입에만 쓰도록 고쳤다. 수정 후 Python 3.9.6의
관련 검사 13개가 통과했다(`output-schema-python39-final.log`).

공통 342개(핵심 221, Python 39, Node 82)는 Python 3.14.6에서 55.092초에
통과했다(`output-schema-gate-final.log`). 공개 사용법·표본 범위는
`docs/protocol/output-contract.md`에 있다. 전체 작업별 스키마·결정 의미의
외부 적합성·독립 전체 구현과 P0–P5의 나머지는 미완이다.

## 외부 호스트 결정 의미 검사

`--suite decisions`는 수명 16개와 호스트 질문 결속 19개를 stdio로 검사한다.
다른 호스트·challenge·표시 원문·선택지 거부, 거부 뒤 pending 유지,
host-user 출처의 답 저장과 원 작업 재호출 전 미적용, 같은 응답 재전달의
멱등성·덮어쓰기 거부, 적용된 답의 출처 ID 재사용 거부, abandon의 미응답
유지·새 표시 재시도, 종료 뒤 늦은 답과 새 세대의 이전 답 상속 거부를
확인했다. 실제 서버가 35개 모두 통과했다(`decisions-wire-final.json`).

질문 알림 4개를 포함한 실제 frame 45개가 출력 스키마를 통과했다
(`decisions-output-final-validation.json`). 앞선 이벤트 표본 38개와 합치면
frame 83개에서 11개 메서드의 정상 결과와 알림 2종을 모두 실제 관측했다
(`combined-output-validation.json`). 스키마 검사기에 반복 --wire-trace를
지원한다. 이는 dummy 색상 질문에 대한 명시적 호스트 답 fixture이며,
사람 UI·native-user 증거·실제 권한/가입 효과 인증으로 부르지 않는다.

표시 원문 검사를 우회하거나 답 저장 직후 원 작업을 자동 적용하는 시험
서버 결함을 넣으면 각각 해당 검사에 실패한다. Python 3.9.6 -O의 검사기
검사 12개도 통과했다(`decisions-conformance-optimized-final.log`). 공통
345개(핵심 224, Python 39, Node 82)는 Python 3.14.6에서 57.185초에 통과했다
(`decisions-conformance-gate.log`). 만료·decline/cancel·모든 domain 효과의
외부 검증, 실제 native UI·독립 전체 구현과 P0–P5 나머지는 미완이다.

## Hermes native injection 경로 실험

실제 0.22.5 PluginContext와 TUI injection/queue 함수 본문으로 독립 프로브를
추가했다(`scripts/probe-hermes-injection.py`). Native method binding은 그대로
사용하고 세션 행·busy 상태·서버 namespace는 fixture다. 두 임시 프로필에만
허용/거부 설정을 준비했으며 모델 drain을 guard로 막았다. 고정 tag와 tracked
소스 일치 및 관련 7개 파일 해시를 기록한다. 최종 9개 검사가 통과했다
(`hermes-native-injection-source-verified/result.json`).

Keyed busy queue 원문·기존 입력·transport 보존과 정책 거부 뒤 무변경을
확인했다. 동시에 True가 gateway 예약, CLI의 키 검증 없는 현재 REPL 주입,
이미 in-flight인 중복으로도 나올 수 있음을 구분했다. 서로 다른 프로필의
fixture 행에 같은 키를 두면 matcher가 첫 행을 선택한다. 실제 운영 중복 키
발생 증거로 확대하지 않으며, 이 API가 profile/generation 결속을 보장한다는
증거도 얻지 못했다. 키 비교·정책 거부를 각각 제거한 변이는 기대한 검사에서
실패했다(`hermes-injection-mutant-ignore-{key,policy}/result.json`).

이번 변경은 프로브와 문서이며 제품 pull 동작·native 소스·사용자 프로필은
바꾸지 않았다. 공통 gate는 이번에 재실행하지 않았다. Native 함수 9개 검사와
명시적 변이 2개의 결과만 새 증거다. 자동 주입에는 native SID/home/generation과
route의 결속, 실제 context/queue 관측, gateway 예약과 실제 수락의 분리가 남는다.
Idle wake·실제 UI/agent·메신저·Linux와 전체 P0–P5도 미완이다.

## Hermes 다음 native 호출에서 backend 재등록

Hermes native 세션이 살아 있는데 프로토콜 backend만 종료되면 이후 호출도
기존 실패 host에 갇혔다. 다음 정상 도구/session-start 진입에서 실패 host를
정리하고 같은 native SID/profile/workspace의 새 참여를 여는 경로를 추가했다.
Workspace 검증과 기존 lifecycle lock 안에서 교체하며 실패한 작업 자체는
자동 재전송하지 않는다. 유휴 중 선제 재접속이나 전체 runtime 복구 완료는 아니다.

실제 backend에 claim을 남긴 뒤 강제 종료한 검사는 변경 전 실패했다
(`hermes-recover-red.log`). 수정 후 같은 주소·다른 PID/세대에서 같은 원문을
새 claim으로 회수하고 이전 token의 ACK를 -32602로 거부한 뒤 새 token으로
ACK했다. 최초 수정 검사는 올바르게 거부된 오류의 문구를 잘못 예상해
실패했다(`hermes-recover-python39.log`, `hermes-recover-python39-final.log`).
공개 오류 코드로 수정한 Python 3.9.6 검사 5개는 통과했다
(`hermes-recovery-python39-verified.log`). 제어된 SDK 검사도 실패한 전송의
재실행 없이 다음 inbox 호출만 새 host에서 수행함을 확인한다.

실제 Hermes 0.22.5의 설치 snapshot discovery/registry.dispatch에서도 충돌 복구를
포함한 12개 검사가 통과했다(`hermes-recovery-native/result.json`). 프로브는
부모 PID를 검증한 자체 backend만 종료하며 사용자 프로세스는 대상으로 하지
않는다. 공통 347개(핵심 226, Python 39, Node 82)는 Python 3.14.6에서
58.712초에 통과했다(`hermes-recovery-gate.log`). Native agent/UI·자동 idle
재접속·push·worker·Linux와 P0–P5의 나머지는 미완이다.

## SDK 수신 실패와 claim 정리 오류 분리

두 공통 SDK의 수신 경로에서 native callback이 실패한 뒤 inbox.release도
실패하면 정리 오류가 원래 실패를 덮어썼다. 백엔드 종료와 native 거부가
겹치면 원래 RetryAdmission/취소의 종류도 잃었다. 두 SDK 모두 해제를 시도하되
그 실패를 진단 callback에 별도 보고하고 원래 예외를 그대로 전달한다.
성공한 release나 ACK를 만들지 않으며 기존 lease/세대 복구 규칙을 따른다.

제어된 callback/transport 검사는 native 일반 거부·일시 거부·취소의 세 경우에
동일한 원래 예외 객체가 반환되고, 해제 실패가 별도 보고되며, inbox 읽기와
release 외의 ACK/재실행 호출이 없는지 확인한다. 수정 전 Python과 Node 검사가
모두 실패했다(`release-primary-{python,node}-red.log`). 수정 후 Python 3.9.6
관련 3개와 Node 관련 2개가 통과했다(`release-primary-{python,node}-green.log`).

공통 349개(핵심 226, Python 40, Node 83)는 Python 3.14.6에서 59.541초에
통과했다(`release-primary-gate.log`). 이 검사는 SDK 오류 경로이며 native 모델
소비·사람 UI·전체 재접속·Linux와 P0–P5 나머지 완료를 증명하지 않는다.

## 설치본의 공개 계약 bundle

불변 runtime 스냅샷에 공개 스키마·예제·문서와 외부 적합성/스키마 검사기를
포함했다. `xsm protocol describe`는 설치본 자체의 protocol version, 11개 wire
메서드, 현재 작업 descriptor, 각 자산의 UTF-8 본문과 SHA-256을 JSON으로
반환한다. 이 CLI action을 새 wire 메서드로 세지 않는다. 누락된 필수 자산과
symlink/outside 자산은 부분 성공으로 내보내지 않는다. 표준 스키마 검사기의
jsonschema는 계속 별도 개발 의존성이며 stdlib checker는 독립 실행한다.

변경 전 설치 snapshot에는 request.schema.json부터 없어서 실패했다
(`installed-contract-red.log`). 수정 후 시험 복사 체크아웃을 제거하고 설치본
CLI에서 모든 본문/해시와 11개 메서드·21개 작업을 확인했다. 설치본의 stdlib
checker가 같은 설치본 서버의 수명 계약 16개를 모두 통과했다.

공통 CLI 초기화는 계약 조회에도 상태 폴더 생성과 housekeeping을 시도했다.
새 읽기 전용 검사는 이를 재현했다(`contract-readonly-red.log`). Describe를
상태 초기화·prune·telemetry 이전에 반환시켜 새 HOME/XSM_HOME이 생성되지
않게 했다. Python 3.9.6 설치 관련 검사 31개가 통과했다
(`contract-readonly-python39.log`). 최종 두 스크립트 포함 상태의 공통
353개(핵심 230, Python 40, Node 83)는 Python 3.14.6에서 65.321초에 통과했다
(`installed-contract-gate-final.log`).

공개 자산 제공은 전체 normative operation 결과·독립 전체 구현 인증을
대체하지 않는다. Native UI/push/worker·자동 재접속·Linux·원격·전체 방향
조합을 포함한 P0–P5의 남은 수용 조건은 미완이다.

## 공개 작업 인자의 구조 스키마

21개 작업의 operation.call params를 `operations.schema.json`으로 고정하고,
작업당 구조 검증 전용 예제를 하나씩 제공한다. 서버 TOOL schema에서 생성해
알 수 없는 인자의 재귀적 거부, 필수 arguments, protocol wait=0과 비어 있지
않은 answer_request 거부를 명시한다. MCP/CLI 대기 기본값은 바꾸지 않는다.
실행 코드와 다른 catalog는 protocol describe가 내보내지 않는다.

개발용 generator는 작업을 실행하지 않고 정적 자산만 갱신한다. 표준
jsonschema 검증기는 정상 예제 21개를 수락하고 오류 입력 73개를 거부했다
(`operation-schema-final-validation.json`). 추가 인자를 허용하거나 blocking
wait 제한을 지운 격리 스키마 변이는 각각 검출됐다
(`operation-schema-mutants.json`). 실제 bundle export도 다른 catalog를 거부했다
(`operation-schema-stale-export.json`). Stdlib 검사에서는 committed catalog와
runtime 생성 결과가 같고 원래 TOOL 객체가 변하지 않는 것을 확인한다.

Python 3.9.6 관련 36개는 통과했다(`operation-schema-python39.log`). 공통
354개(핵심 231, Python 40, Node 83)는 Python 3.14.6에서 65.580초에 통과했다
(`operation-schema-gate.log`). 공개 사용법·범위는 operations-contract.md에 있다.
이는 구조적 입력 계약이며 모든 domain 필수 조건·권한·native 지원을
증명하지 않는다. 작업별 결과·독립 전체 구현과 P0–P5의 남은 수용 조건은 미완이다.

## OpenCode 다음 native 진입의 backend 복구

OpenCode의 session map이 transport 실패 host를 계속 반환하던 경로를 수정했다.
다음 도구/chat 경계와 제목·상태 갱신에서 실패 host를 정리하고 동일 native
대화를 새 세대로 등록한다. 복구 Promise를 공유해 동시 진입의 중복 등록을
막으며 이전 UI 질문을 닫는다. 실패한 도구 호출 자체를 자동 재실행하지 않는다.

실제 protocol server/API fixture에서 원문 claim 뒤 backend를 종료하는 검사는
변경 전 실패했다(`opencode-backend-recovery-red.log`). 수정 후 관련 8개가
통과했다(`opencode-backend-recovery-green.log`). 동시 도구 호출 두 개에서
같은 ref·다른 PID/세대, 원문 보존·token 교체·이전 token 거부·새 ACK를 확인했다.

실제 OpenCode 1.19.5도 자체 process group의 backend만 종료한 뒤 실제 noReply
chat 경계로 복구했다. 첫 프로브는 HTTP 경로를 잘못 사용해 실패했으며 로그를
보존했다(`opencode-backend-recovery-native/result.json`). 고정 SDK의 /message
경로로 수정한 5회 smoke 뒤 100/100 native 수락·native ACK를 완료했고 macOS/
protocol Python 3.14.6 p95 상한은 347.275ms다
(`opencode-backend-recovery-native-100/result.json`). Native 강제 종료 시 미소비
원문을 남기지는 않았으므로 그 복구는 앞의 API fixture와 구분한다. Provider는
scripted assistant fixture이며 모델 추론이나 사람 UI 인증이 아니다.

공통 355개(핵심 231, Python 40, Node 84)는 Python 3.14.6에서 59.428초에
통과했다(`opencode-backend-recovery-gate.log`). 유휴 중 자동 재접속·Pi/다른
runtime의 복구·worker·Linux·원격·전체 방향 조합과 P0–P5 나머지는 미완이다.

## Pi 다음 native 진입의 backend 복구

Pi의 도구·명령·chat/status 경계에서 닫히거나 실패한 host를 재등록하는 경로를
추가했다. 대화/workspace와 세션 epoch를 비동기 확인 뒤 다시 검사하고, 실제
작업은 그 호출이 확인한 host로 보낸다. 복구 Promise를 공유하고 native 세션
시작/종료는 이전 복구를 무효화한다. Backend open 및 초기 상태 갱신 중 종료가
겹쳐도 새 host를 닫는다. 실패한 작업을 자동 재실행하지 않는다.

제어된 API/backend 검사 4개가 통과했고 등록 수명 검사를 무력화한 변이는
실패했다(`pi-recovery-lifecycle-verified.log`, `pi-recovery-epoch-mutant-verified.log`).
실제 Pi 1.4.0 SDK도 claim을 남긴 backend를 종료한 뒤 같은 주소의 새 세대·
원문 회수·이전 claim 거부·native 도구 ACK를 통과했다
(`pi-sdk-recovery-verified.json`). 이전 연결 본문의 같은 SDK 시험은 EOF로
실패했다(`pi-backend-recovery-baseline.json`). 정상 batch 회귀도 별도 통과했다
(`pi-backend-batch-verified.json`).

추가 shutdown 상태 갱신 경계를 보완한 최종 코드의 설치 snapshot에서 다시
RPC 수신 100/100개와 RPC 명령 ACK 100/100개를 확인했다. macOS/protocol Python
3.14.6 p95 상한은 421.134ms다(`pi-backend-recovery-verified-100/result.json`).
`pi-backend-recovery-ack-audit.json`은 정본 ACK 100개와 현재 코드 해시 일치를
대조한다. SDK 도구 ACK와 RPC 명령 ACK, 모델 소비를 구분한다. Native UI
프로토콜은 fixture 답으로 확인했으며 사람의 응답 인증은 아니다. 앞선 중간
코드의 100개 표본도 보존하고 최종 판정에는 최종 해시 표본을 사용한다.

공통 359개(핵심 231, Python 40, Node 88)는 Python 3.14.6에서 57.057초에
통과했다(`pi-backend-recovery-gate-final.log`). 최초 등록 실패 재시도·자동 idle
재접속·실제 모델/사람 UI·worker·Linux·전체 방향 조합과 P0–P5 나머지는 미완이다.

## Pi 최초 등록 실패의 다음 진입 재시도

Native session_start에서 확인한 대화/workspace의 참여 의도를 backend host와
분리했다. 최초 open/state update 실패 뒤 다음 정상 native 진입은 등록과
미완료 도구 등록을 재시도한다. 열린 host의 초기 상태 갱신이 실패하면
정리하고, shutdown 뒤에는 다시 등록하지 않는다. 최초 등록 시도도 같은
공유 Promise와 epoch로 관리한다.

수정 전 open/state 실패 검사는 재시도하지 못했다(`pi-bootstrap-red.log`).
수정 후 해당 경우와 shutdown을 포함한 제어 수명 7개가 통과했다
(`pi-bootstrap-final-tests.log`). 실제 Pi 1.4.0 설치본도 첫 serve를 임시 wrapper로
실패시킨 뒤 다음 /xsm 명령에서 등록했다. 도구 21개, native 선택 프로토콜,
수신/RPC 명령 ACK 5회가 통과했다(`pi-bootstrap-native-verified/result.json`).
모델·사람 UI 증거가 아니며 5회 smoke를 100개 p95 기준으로 쓰지 않는다.

프로브 초회는 설치 명령을 가로막아 실패했고, 두 번째는 설치 후 제거되는
환경 변수 때문에 실패 주입이 적용되지 않아 표식 검사에서 실패했다.
`pi-bootstrap-native.log`, `pi-bootstrap-native-fixed.log`를 보존했다. 최종 주입은
오직 native serve 첫 실행에만 적용되는 임시 wrapper를 사용한다.

공통 362개(핵심 231, Python 40, Node 91)는 Python 3.14.6에서 58.794초에
통과했다(`pi-bootstrap-gate.log`). 자동 유휴 재접속·실제 모델/사람 UI·worker·
Linux·원격·전체 방향 조합과 P0–P5 나머지는 미완이다.

## OpenCode 참여 초기 갱신 실패의 정리

Host를 연 뒤 최초 상태/제목 갱신이 실패하면 session map의 Promise는 지워도
backend 참여는 남아 다음 등록을 막았다. 등록 후처리 실패 시 host를 닫고
원래 오류를 유지하도록 수정했다. Cleanup 오류는 별도 진단으로 분리한다.
수정 전 실제 protocol/API fixture 검사는 열린 host를 확인하고 실패했다
(`opencode-initial-update-red.log`). 수정 후 관련 9개가 통과했고, 종료 기록과
같은 ref·새 generation의 재등록을 확인했다(`opencode-initial-update-green.log`).

실제 OpenCode 1.19.5도 임시 wrapper로 첫 session.update만 거부한 뒤 종료된
참여를 확인하고 다음 chat 경계에서 재등록했다. Native 수락·native tool ACK
5회가 완료됐다(`opencode-initial-update-native/result.json`). Receiver 검색은
ended_at을 확인해 종료된 행을 live로 판독하지 않도록 고쳤다. 이 결과는
scripted assistant fixture이며 모델/사람 UI나 100개 p95 기준의 인증이 아니다.

공통 363개(핵심 231, Python 40, Node 92)는 Python 3.14.6에서 58.657초에
통과했다(`opencode-initial-update-gate.log`). Plugin 자체 최초 descriptor 조회
실패·자동 idle 재접속·worker·Linux·원격·전체 방향 조합과 P0–P5는 미완이다.

## SDK host 초기화 계약과 정리 오류

두 SDK의 XsmHost.open에서 초기화 실패 뒤 client.close도 실패하면 정리 오류가
원래 오류/취소를 덮어썼다. Close를 시도한 뒤 그 실패를 별도 진단으로 보고하고
원래 예외를 유지하도록 수정했다. Close 실패까지 자원 회수가 보장된 것으로
보고하지 않는다. 실제 프로세스·정본 참여·lease 복구는 별도 근거가 필요하다.

Claim lease 검증도 두 언어를 맞췄다. 유한한 양수 숫자만 허용하며 boolean,
문자열, NaN/무한대와 Python에서 유한한 native 수치로 변환할 수 없는 큰 정수를
거부한다. Python capability 목록도 배열인지 확인한다. 정상 서버의 120초
기본값이나 실제 claim lease를 바꾸지는 않았다.

수정 전 Python/Node 검사는 모두 실패했다(`sdk-initialize-{python,node}-red.log`).
수정 후 Python 3.9.6 관련 5개와 Node 관련 4개가 통과했다
(`sdk-initialize-{python,node}-green.log`). 잘못된 lease의 초기화 거부와 정리
시도·진단, 원래 취소/등록 오류 유지 경로를 확인한다. 공통 367개(핵심 231,
Python 42, Node 94)는 Python 3.14.6에서 58.621초에 통과했다
(`sdk-initialize-gate.log`). 이 결과는 SDK host 초기화 경로이며 전체 native
초기화/재접속·모델/사람 UI·worker·Linux와 P0–P5 나머지는 미완이다.

## 기본 client의 버전 협상과 실패 정리

두 기본 client는 initialize result의 protocolVersion을 확인하지 않고 연결을
성공으로 반환했다. 버전 불일치·누락·비 object 결과를 TransportError로 거부한다.
접속 실패 시 close 오류는 stderr 진단으로 분리해 원래 오류를 유지한다.
Close 실패 자체를 자원 회수 성공으로 보고하지 않는다.

시험 서버는 xsm을 import하지 않는 독립 echo peer다. 잘못된 세 형태의 실제
stdio 응답을 거부하고 peer 종료를 확인한다. Close가 실제 process를 회수한 뒤
추가 오류를 던지는 subclass에서도 원래 협상 오류와 정리 진단이 구분된다.
Node 수정 전 검사는 실패했다(`version-negotiation-node-red.log`). Python 새
검사는 처음 배치가 잘못돼 수집되지 않았다. 위치를 고쳐 이전 client의 격리
사본을 실행했고 실제 실패를 확인했다
(`version-negotiation-python-baseline-verified.log`). 처음 Python red 로그의
14개 통과를 새 검사 검증으로 세지 않는다.

수정 후 Python 3.9.6 기본 client 검사 16개가 통과했다
(`version-negotiation-python-final.log`). Node 검사도 통과했다
(`version-negotiation-node-green.log`). 공통 371개(핵심 231, Python 44, Node 96)는
Python 3.14.6에서 58.769초에 통과했다(`version-negotiation-gate.log`). 협상
검증은 안정판 호환성 보증이나 모든 SDK 오류/취소 계약 완료가 아니다.
자동 재접속·native 모델/사람 UI·worker·Linux와 P0–P5 나머지는 미완이다.

## Pi 등록 참여의 자동 transport 복구

Pi host의 TransportError와 중단된 transport를 관측하면 입력 없는 재접속을
예약한다. 최초 대기는 250ms, 실패 시 두 배로 늘리되 최대 5초로 제한했다.
같은 native 대화/workspace와 epoch를 검증하며 공유 ensure 경로를 사용한다.
Native 작업은 재실행하지 않는다. 일반 native 오류는 제외하고 shutdown이나
세션 전환은 예약을 취소한다. 최초 host 생성 전 오류에는 아직 적용하지 않는다.

제어 수명 11개가 통과했다(`pi-auto-reconnect-verified.log`). 자동 복구를 끄거나
backoff를 제거한 변이는 각각 실패했다
(`pi-reconnect-{auto,backoff}-mutant-verified.log`). 처음 fixture 수정은 옵션 이름을
가려 기존 초기 실패 검사가 실패했으며 그 로그도 보존했다
(`pi-auto-reconnect-first.log`).

실제 Pi 1.4.0 설치본에서 native 명령 전 자동 재등록을 관측한 뒤 100/100 native
수락·RPC 명령 ACK를 완료했다. macOS/protocol Python 3.14.6 p95 상한은
433.341ms다(`pi-auto-reconnect-native-100/result.json`). 정본 ACK 100개와 현재
코드 해시 일치도 확인했다(`pi-auto-reconnect-ack-audit.json`). 모델/사람 UI가
실행한 소비가 아니라 명시적 native fixture의 결과다.

공통 375개(핵심 231, Python 44, Node 100)는 Python 3.14.6에서 58.748초에
통과했다(`pi-auto-reconnect-gate.log`). Pi의 설치 업데이트/제거와 겹친 runtime
보존은 component lease 추가 검증이 남아 있다. 다른 runtime 자동 복구·최초
생성 전 실패·worker·Linux·원격·전체 방향 조합과 P0–P5 나머지는 미완이다.

## Pi 실행 코드의 snapshot 수명

Pi에 pi-extension component lease를 연결했다. 등록 backend와 별도로 native
PID/시작 시각이 old runtime을 보존한다. Native new/resume/fork는 코드를 다시
로드하지 않으므로 lease를 유지하고 quit/reload 뒤 해제한다. Shared Node helper를
clients/typescript로 옮기고 OpenCode의 기존 모듈 경로는 re-export로 보존했다.
설치 자산 검사에도 shared helper를 포함했다.

제어 수명 12개는 모든 전환 모드와 reload 해제를 통과했다
(`pi-component-lifecycle-all-transitions.log`). Lease 없는 변이는 실패했다
(`pi-component-lease-mutant.log`). Python prune 검사는 protocol backend가 없어도
Pi lease가 old root를 보존하고 native PID가 죽으면 회수되는 것을 확인한다.
Python 3.9.6 관련 40개도 통과했다(`pi-component-python39.log`).

실제 Pi 1.4.0은 새 snapshot 게시/prune 뒤 old root를 유지하고 quit 뒤 회수했다.
수신/RPC 명령 ACK 100개, 현재 구현 해시 일치와 macOS/protocol Python 3.14.6
p95 상한 432.114ms를 확인했다(`pi-component-upgrade-native-100/result.json`,
`pi-component-upgrade-ack-audit.json`). 별도 업데이트 후 binding 제거의 5회 표본도
old root 유지·수신/ACK·quit 뒤 회수가 통과했다
(`pi-component-remove-native/result.json`). 실제 유지 단계에는 protocol backend도
살아 있었으므로 backend 독립 보존의 원인은 Python 단독 검사와 구분한다.

공통 377개(핵심 232, Python 44, Node 101)는 Python 3.14.6에서 59.067초에
통과했다(`pi-component-gate.log`). OpenCode 1.19.5 실제 native 수락/ACK 5회도
회귀 통과했다(`shared-component-opencode-native/result.json`). 모든 답/소비는
fixture이며 모델·사람 UI 인증이 아니다. 자동 복구의 다른 runtime·worker·
Linux·원격·전체 방향 조합을 포함한 P0–P5 나머지는 미완이다.

## OpenCode 등록 참여의 자동 transport 복구

등록 host의 transport 실패를 세션별 timer가 복구한다. 250ms부터 실패 시
두 배, 최대 5초까지 기다리고 native 작업을 자동 재실행하지 않는다. 세션별
intent/epoch로 삭제·dispose 뒤 시도를 막고 기존 open Promise를 공유한다.

관련 13개 검사가 통과했다(`opencode-auto-reconnect-all-tests.log`). 입력 없는
재등록, 삭제/dispose의 timer 취소와 증가하는 backoff를 실제 protocol server/API
fixture에서 확인했다. Scheduler를 끈 변이는 실패했다
(`opencode-auto-reconnect-disabled-mutant.log`). 최초 취소 검사는 강제 종료된
backend가 ended_at을 기록한다고 잘못 예상해 실패했다
(`opencode-auto-reconnect-tests.log`, `opencode-auto-reconnect-verified.log`).
수정 후 새 backend open 횟수/PID가 변하지 않음을 직접 대조했다.

실제 OpenCode 1.19.5도 초기 host 갱신 완료 후 backend를 종료하고 명시적 native
chat/tool 전에 새 세대를 관측했다. 복구 뒤 100/100 native 수락·native tool ACK를
완료했고 macOS/protocol Python 3.14.6 p95 상한은 353.919ms다
(`opencode-auto-reconnect-native-100/result.json`). 현재 연결 코드의 해시 일치도
확인했다. Outage 전 구간 지연이나 실제 모델/사람 소비를 인증하지 않는다.

공통 381개(핵심 232, Python 44, Node 105)는 Python 3.14.6에서 60.723초에
통과했다(`opencode-auto-reconnect-gate-verified.log`). Descriptor 최초 조회와
모든 초기 생성 전 실패·Hermes/OpenClaw 자동 재접속·worker·Linux·원격·전체
방향 조합과 P0–P5의 나머지는 미완이다.

## OpenCode native directory 검증

새 참여 등록에서 native session.get의 directory를 plugin directory와 비교한다.
고정 SDK의 Session 타입은 이 필드를 필수로 제공하지만 기존 연결은 ID만
검사했다. Native directory가 기존 절대 경로이고 realpath가 plugin과 같은지
확인하며, 다른/누락/빈 값/상대/없는 경로는 host open 전에 거부한다. 확인할 수
없을 때 plugin cwd를 대신 신원으로 사용하지 않는다. 재접속도 동일 경로다.

변경 전 workspace 거부 검사는 실패했다(`opencode-workspace-red.log`). 변경 후
관련 18개에서 정상 경로와 거부 5종, 거부 뒤 미등록을 확인했다
(`opencode-workspace-green.log`). 실제 OpenCode 1.19.5는 입력 없는 재접속 뒤
100/100 native 수락·native ACK를 통과했다. macOS/protocol Python 3.14.6 p95
상한은 343.080ms다(`opencode-workspace-native-100/result.json`). 실행 연결 코드와
현재 해시의 일치도 확인했다. 모델/사람 UI 소비의 인증은 아니다.

공통 386개(핵심 232, Python 44, Node 110)는 Python 3.14.6에서 62.647초에
통과했다(`opencode-workspace-gate.log`). 이는 새 등록의 작업 폴더 결속이며
전체 다중 프로젝트/원격/방향 행렬이나 P0–P5 전체 완료가 아니다.

## Hermes 등록 참여의 자동 broker 복구

세션별 monitor로 registered transport의 실패를 복구한다. 250ms 확인/초기 대기,
실패 시 두 배·최대 5초로 제한하고 마지막 hook 상태를 복원한다. Native SID와
검증된 cwd를 유지하며 SDK/native 작업이나 inbox 읽기·ACK를 자동 반복하지 않는다.
Workspace 전환·finalize/delete/reset은 monitor를 취소하고 unload는 진행 중
backend open도 취소한 뒤 host와 loop/thread, component lease를 정리한다.

Python 3.9.6 관련 8개에서 실제 backend 종료·자동 등록·마지막 상태 복원·
finalize 취소, 미완료 open의 unload 취소, 증가하는 backoff를 확인했다
(`hermes-auto-reconnect-final-tests.log`). Monitor를 끈 변이는 실패했다
(`hermes-auto-reconnect-disabled-mutant.log`). 실제 Hermes 0.22.5 registry는
native dispatch 전 새 PID/세대와 상태를 관측했고 원문 보존·old claim 거부·
새 ACK를 포함한 13개가 통과했다(`hermes-auto-reconnect-native-final/result.json`).
현재 구현의 해시 일치도 확인했다. Native agent/model·UI 실행의 증거는 아니다.

공통 389개(핵심 235, Python 44, Node 110)는 Python 3.14.6에서 65.631초에
통과했다(`hermes-auto-reconnect-gate-final.log`). Pull-only이므로 native queue
수락 지연이나 모델 소비를 인증하지 않는다. Native push/UI·초기 생성 전 실패·
handshake 응답 기한/대화별 등록 동시성 확대·worker·Linux·메신저·원격과
전체 P0–P5 나머지는 미완이다.

## Hermes 대화별 등록 동시성

기존 coordinator의 공통 host_lock은 한 backend 등록이 늦으면 다른 대화도
막았다. SID별 잠금으로 등록/복구/finalize를 직렬화하고 대화 간에는 진행되게
했다. 종료 전후를 open 경계에서 확인해 종료 중 완성된 host도 반환하지 않고
닫는다. Unload는 미완료 open 취소 뒤 잠금을 정리한다.

변경 전 느린 등록과 빠른 대화 검사는 timeout으로 실패했다
(`hermes-conversation-lock-red.log`). 수정 후 이미 열린 대화와 다른 새 대화가
느린 등록 중 진행됐다. Finalize의 기존 기대(열린 host 반환)는 강화된 종료
동작과 달라 확대 검사에서 실패했고, host 닫힘 및 호출자의 종료 오류를
검사하도록 맞췄다. Python 3.9.6 관련 9개가 통과했다
(`hermes-conversation-lock-final-tests.log`). 이전 실패 로그도 보존한다.

실제 Hermes 0.22.5의 직접 PluginContext/registry.dispatch fixture는 session.open을
marker로 막은 대화와 별도로 기존 대화가 완료되는 것을 확인했다
(`hermes-conversation-isolation-native/result.json`). 전체 8개 검사가 통과했고 현재
구현 해시도 대조했다. 별도 설치/autoload 자동 복구 13개도 회귀 통과했다
(`hermes-conversation-lock-native/result.json`). Agent/model·UI·메신저 동시성을
실행한 인증은 아니다.

공통 390개(핵심 236, Python 44, Node 110)는 Python 3.14.6에서 65.863초에
통과했다(`hermes-conversation-lock-gate-final.log`). Handshake 응답 기한·native
push/UI·worker·Linux·메신저·원격·전체 방향 조합과 P0–P5는 미완이다.


## Linux arm64 공통 gate

별도 Colima VM과 Docker endpoint에서 공통 390개(핵심 236, Python 44, Node 110)가
Python 3.11.2/Node 24.22.2에서 70.270초에 통과했다
(`linux-tracked-core-fixed/result.json`, `environment.json`, `protocol.log`). 소스는
c460a6937730ea489aa32e2863cf0506934bdae6의 변경 없는 추적 파일이며 archive hash와
image ID를 기록한다. Container 네트워크는 none, 자원은 2 CPU/3 GiB로 제한했다.

처음 VM은 Unix socket 경로가 길어 실패했고 짧은 격리 경로로 옮겼다. Release
archive는 tests를 제외해 첫 container 실행에서 import 준비가 실패했다. 그 18개
loader 오류를 실제 검사 실패 수로 세지 않는다. 다음 묶음은 /var→/private/var
변환으로 guest bind path가 없어 실행 전 실패했다. 둘 다 로그를 보존하고 추적
파일/경로 표기를 고쳐 전체 gate를 실행했다. 기존 출력 덮어쓰기도 거부했다.

재사용 Dockerfile/runner와 상세 기준은 linux-validation.md에 남겼다. 사용자 기본
VM/전역 context는 유지했고 자체 VM도 종료 후 Stopped로 확인했다. Linux native
에이전트/모델/UI/큐 p95·다른 Python/아키텍처·전체 방향/원격/메신저/worker와
P0–P5의 나머지는 미완이다.

## OpenCode native Linux arm64

프로브의 Linux=x64 고정 선택을 OS/architecture별 pinned package 선택으로
바꿨다. 실제 optionalDependencies와 Mac 설치본 SDK/plugin 버전을 확인했고
지원하지 않는 플랫폼은 거부한다. Mapping 2개 검사와 x64 fallback 변이 검출을
추가했다(`native-platform-x64-fallback-mutant.json`).

Linux arm64의 OpenCode binary·SDK·plugin 1.19.5를 별도 container에서 준비했다.
처음 network-none 검사는 plugin bootstrap의 dependency 대기에서 timeout으로
실패했고 표본은 0개였다(`linux-opencode-native-stage.json`). 고정 버전의
Config/Npm source와 대조해 node_modules뿐 아니라 준비된 package manifest/lock도
시험 profile에 넣었다. Offline smoke 5회 뒤 최종 native 수락/ACK 100/100개가
완료됐고 복구 후 p95 상한은 277.750ms다
(`linux-opencode-native-100/output/native/result.json`). 명시적 native 진입 전
자동 재등록과 현재 연결 코드 hash도 확인했다. SDK/provider는 scripted fixture이며
모델 추론·사람 UI·메신저 인증은 아니다. Package lock과 archive hash/dirty 상태를
보존했고 실패 표본도 남겼다.

공통 392개(핵심 238, Python 44, Node 110)는 Mac/Python 3.14.6에서 64.046초,
Linux arm64/Python 3.11.2에서 70.194초에 통과했다. 상세 자원/버전·원시 경로는
linux-validation.md에 기록했다. 테스트 VM은 종료 후 Stopped이며 기본 context와
기본 VM은 유지했다. 다른 Linux native 런타임·x86_64·원격/방향/메신저/worker와
P0–P5의 나머지 수용 조건은 미완이다.


## Pi native Linux arm64

고정 Pi 1.4.0을 Linux arm64/Node 24.22.2/Python 3.11.2에서 실행했다. Dependency
준비와 network-none 검사를 분리하고 package lock/archive hash를 보존했다.
제품과 프로브 수정 없이 설치 자동 발견·입력 없는 backend 재접속·snapshot
업데이트/binding 제거 중 old root 보존·quit 뒤 회수가 통과했다. Native 수락과
RPC 명령 ACK 100/100개가 완료됐고 p95 상한은 215.806ms다
(`linux-pi-native-100/output/native/result.json`).

Native stdout의 ACK 100개와 정확한 수신 ID 집합, 현재 구현 hash를 대조했다
(`linux-pi-native-100/ack-audit.json`). 실제 SDK nested-tool kernel도 claim을 남긴
충돌 뒤 원문 회수·이전 token 거부·새 도구 ACK를 통과했다
(`linux-pi-sdk/sdk-recovery.json`). 큰 FYI 3개와 도구 ACK 3개의 회귀도 통과했다
(`linux-pi-sdk/sdk-batch.json`). RPC 명령 ACK·도구 ACK·모델 소비를 구분한다.
모델 호출은 0회이며 assistant/UI는 fixture다.

이번 소스는 68e75f6의 변경 없는 추적 파일이다. 코드 수정이 없어 공통 gate를
새로 실행한 것으로 보고하지 않는다. 테스트 VM은 Stopped로 확인했고 기본
context/기본 VM은 유지했다. Hermes/OpenClaw Linux·worker·실제 모델/사람 UI·
원격/메신저·전체 방향 및 P0–P5 나머지는 미완이다.

## Initialize 협상 응답 기한

Python/Node SDK와 native host의 초기 협상에 기본 10초 응답 기한을 추가했다.
Python `initialize_timeout`(초), Node `initializeTimeout`(ms)으로 유한한 양수의
기한을 전달한다. Node의 timer overflow 범위도 거부한다. 응답 없는 peer는
`TransportError`로 실패하고 기존 close 경로로 회수한다. 이 기한은 일반
operation·session.open·operations/list 전체의 기한이나 사용자 질문 제한이
아니다. 해당 나머지 setup/작업 기한과 P0–P5는 여전히 미완이다.

무응답 subprocess fixture, 종료 회수, invalid value spawn 전 거부, native
host 옵션 전달 검사를 추가했다. 초기 Python red는 옵션 부재로 실패했다
(`initialize-timeout-python-red.log`). 전체 최종 검사 결과는 아래 기록한다.

`python3 -B scripts/check-protocol.py`가 401개(핵심 238/Python 47/Node 116)를
66.503초에 통과했다(`initialize-timeout-core-gate.log`, macOS arm64,
Python 3.14.6). 초기 기한을 무력화한 Python·Node 임시 변이도 외부 watchdog
오류로 실패했다(`initialize-timeout-disabled-mutant.log`,
`initialize-timeout-node-disabled-mutant.log`). 즉 timeout 설정의 존재만
검사한 결과가 아니다. 이 SDK 변경의 Linux 검증은 아직 미실행이다.

이어 변경 없는 `1c90ac7`의 Linux arm64/Python 3.11.2에서도 동일한
401개가 71.523초에 통과했다
(`linux-initialize-timeout-core/result.json`). 위 Linux 미실행 기록의
후속 검증이며, 일반 setup 전체 기한·operation 기한은 계속 미완이다.

## Host 등록 전체 응답 예산

Initialize 이후 session.open·operations/list·events.subscribe를 하나의
기본 10초 예산으로 제한했다. Python `setup_timeout`(초), Node
`setupTimeout`(ms)으로 전달한다. 실패 시 기존 close 회수 경로를 사용하고
수신 pump는 구독까지 성공한 뒤 시작한다. 무응답인 세 단계를 각각
subprocess로 실행하고 회수를 확인했다. 단계별 지연은 짧지만 합이 예산을
넘는 fixture도 검사한다. 초기 Python red는 setup 옵션 부재로 3개 분기에서
실패했다(`host-setup-timeout-red.log`). 일반 operation·사람 질문의 기한이나
호스트 연결 종료와 다른 개별 native cancellation 계약은 이 변경으로
완료됐다고 주장하지 않는다. 전체 계획은 미완이다.

`python3 -B scripts/check-protocol.py`는 403개(핵심 238/Python 48/Node 117)를
69.910초에 통과했다(`host-setup-timeout-gate.log`, macOS arm64/Python
3.14.6). 각 RPC마다 예산을 새로 주는 임시 Python·Node 변이는 누적 지연
분기에서 예상한 TransportError가 없어 실패했다
(`host-setup-reset-budget-mutant.log`, `host-setup-node-reset-budget-mutant.log`).
이 등록 예산 변경의 Linux 검증은 아직 미실행이다.

후속 Linux arm64/Python 3.11.2 gate도 변경 없는 `245734c`에서 403개가
75.700초에 통과했다(`linux-host-setup-timeout-core/result.json`). 위 등록
예산 변경의 Linux 미실행 기록을 보완한다. 첫 상태표도 이미 확인한
Pi/OpenCode 자동 재접속과 Linux OpenClaw native fixture를 반영했다.
실제 모델·사용자 UI·worker·원격·메신저와 나머지 요구는 그대로 미완이다.

## OpenClaw 다음 도구 진입의 transport 복구

종료된 host를 다음 native 도구 진입에서 닫고 재등록한다. 동시 호출의
복구는 하나로 합치며 epoch/dispose 검사를 새 host 생성 전후에 유지한다.
실패한 operation을 재전송하지 않는다. 실제 backend 종료 후 회귀는
변경 전 EOF TransportError로 실패했다(`openclaw-boundary-recovery-red.log`).
수정 후 single recovery·dispose 중 재등록 차단·실패 호출 미재실행을
포함한 연결 7개가 통과했다(`openclaw-boundary-recovery-verified.log`).
추가 검사 초회에는 존재하지 않는 xsm_status 도구명을 사용해 1개가
실패했다. 유효한 inbox 도구로 바로잡았으며 실패 로그도 남겼다
(`openclaw-boundary-recovery-final.log`). 자동 idle·agent_end 복구, 종료 전
claim과 기존 queue token 회수·Linux native 검증은 아직 미완이다.

고정 native OpenClaw 2026.10.9/macOS arm64/Node 24.22.2에서도 backend를
종료하고 다음 inbox 도구로 같은 ref·새 PID·새 세대에 재등록한 뒤 큰
원문 100/100 수락·prompt 소비·명시적 ACK가 통과했다
(`openclaw-boundary-recovery-native-100.json`). 복구 뒤 전송 표본의 p95 상한은
504.905ms다. 모델·사람·실제 agent turn은 0회다. 예상한 종료 EOF 한 건이
진단에 남았다. 이 표본은 outage 전체 시간이나 종료 전 claim 회수의
증거가 아니다. 공통 gate 406개(핵심 238/Python 48/Node 120)는 68.904초에
통과했다(`openclaw-boundary-recovery-gate.log`).

## OpenClaw 등록 세션의 자동 transport 복구

Transport 종료 후 native 재진입 없이 250ms부터 재접속하고 일시적 실패 시
두 배씩 최대 5초까지 backoff한다. 같은 대화/ref와 busy/idle을 유지하고
새 generation을 사용한다. Session end/dispose는 예약과 진행 중 재등록을
막는다. 실패 작업은 재전송하지 않는다. 등록에 쓰는 native context에는
이전 도구 호출의 assertInvocationCurrent callback을 보관하지 않는다.

자동 재접속 검사는 변경 전 3초 안에 새 host가 생기지 않아 실패했다
(`openclaw-auto-reconnect-red.log`). 자동 복구·session end 취소·연결 실패
두 번 뒤 backoff와 활동 복원을 포함한 10개가 통과했다
(`openclaw-auto-reconnect-verified.log`). 최초 등록 전 실패·종료 전 claim/
기존 queue token 회수·agent_end 자체 복구·Linux와 전체 계획은 미완이다.

고정 OpenClaw 2026.10.9/macOS arm64/Node 24.22.2에서는 새 native 호출
없이 같은 ref·새 PID·generation을 관측한 뒤 큰 원문 100/100 수락·prompt
소비·ACK가 통과했다(`openclaw-auto-reconnect-native-100.json`). 복구 후
전송 p95 상한 511.044ms이며, 예상한 backend EOF 진단 1건을 보존했다.
모델·실제 agent turn·사람은 0회다. 자동 재접속을 없앤 변이와 backoff를
없앤 변이는 각각 실패했다(`openclaw-reconnect-no-auto-mutant.log`,
`openclaw-reconnect-no-backoff-mutant.log`). 공통 409개(핵심 238/Python
48/Node 123)는 67.654초에 통과했다(`openclaw-auto-reconnect-gate.log`).
최종 연결 검사에는 종료된 이전 도구의 invocation guard를 무효화한 뒤에도
대화 scope의 자동 복구가 되는 검사를 포함했다. Linux·기존 claim/token
회수·agent_end 별도 복구·나머지 전체 계획은 여전히 미완이다.

최종 연결 검사 초회(`openclaw-auto-reconnect-final.log`)에서는 backoff
검사 1개가 새 host 반환 직후 아직 idle인 행을 읽어 실패했다. Mock의
connect 반환과 native 활동 복원 완료를 같은 시점으로 취급한 검사 경쟁이다.
상태 행의 busy 복원까지 기다리도록 바로잡았으며 실패 표본을 보존했다.

관측 경쟁을 바로잡은 최종 연결 10개가 통과했다
(`openclaw-auto-reconnect-final-verified.log`). 최종 공통 gate도 409개가
70.157초에 통과했다(`openclaw-auto-reconnect-gate-final.log`). 이 두 결과는
앞선 최종 초회 실패 뒤의 표본이며 섞어 집계하지 않는다.

Linux 후속 표본도 변경 없는 `87a52d0`으로 통과했다. 고정 native SDK의
새 도구 호출 없는 같은 ref·새 PID/generation 복구 뒤 큰 원문 100/100
수락·소비·ACK, 복구 후 전송 p95 상한 409.313ms를 확인했다
(`linux-openclaw-auto-reconnect-native-100/output/native-queue-100.json`).
공통 gate 409개는 Linux arm64/Python 3.11.2에서 79.712초에 통과했다
(`linux-openclaw-auto-reconnect-core/result.json`). 앞선 Linux 미실행
기록의 후속 검증이며, 실제 모델·사람 UI·기존 claim/token 회수·간헐적
burst ACK 실패 해결과 전체 계획의 완료를 뜻하지 않는다.

## 이미 소유한 원문의 ACK token 재조회

기존 안내는 만료 token을 inbox에서 다시 읽으라고 했지만 일반 inbox는
소유 중인 claim을 건너뛰어 자동 재등록 뒤 현재 token을 얻을 공개 경로가
없었다. `xsm_inbox(message_ids=[...])`를 기존 내부 targeted reader에
연결했다. 같은 대화/owner/generation의 current token을 lease 연장 없이
반환하고 ACK는 별도다. 다른 대화나 선택하지 않은 원문은 읽거나
회수하지 않는다. Byte budget·실패 cleanup에서도 이전부터 소유한 claim을
반환하지 않게 했다. SDK의 ACK 안내에는 message_ids도 넣었다.

기존 API에서 targeted 조회 검사는 거부돼 실패했다
(`inbox-owned-token-red.log`). 첫 구현의 invalid ID 3건은 protocol
validator에 pattern/maxItems 처리가 없어 ToolError가 그대로 올라왔다
(`inbox-owned-token-green.log`). 두 제약을 validator에 연결하고 경계·외부
JSON Schema 사례도 검사했다. 최종 protocol/catalog 35개가 통과했다
(`inbox-owned-token-final-verified.log`). Filter를 무시한 변이는 실패했다
(`inbox-owned-token-ignored-filter-mutant-verified.log`). 변이 초회는 fixture
setup이 module을 다시 로드해 주입이 사라졌으므로 유효한 검증이 아니며
해당 로그도 보존했다(`inbox-owned-token-ignored-filter-mutant.log`).

고정 native SDK의 종료 전 원문 복구도 통과했다
(`openclaw-owned-claim-recovery.json`). 기존 큐와 본문 보존·이전 token
거부·일반 inbox의 소유 claim 제외·targeted current token 조회·명시적
ACK·중복 prompt 소비 없음이 포함된다. 모델/실제 agent turn/사람은
0회다. 공통 gate 413개(핵심 242/Python 48/Node 123)는 73.220초에
통과했다(`inbox-owned-token-core.log`). 외부 jsonschema 검사는 입력
11개/거부 41개, 출력 14개/거부 9개, operation 기본 21개와 targeted
정상 1개/거부 81개가 통과했다(`inbox-owned-token-schema-final.json`).
Linux의 이 변경 검증·간헐적 burst ACK 실패와 전체 계획은 계속 미완이다.

Byte budget 초과 시 기존 소유 claim까지 release하도록 바꾼 변이도
관련 검사가 실패했다(`inbox-owned-token-budget-mutant.log`). 이전 claim의
유지를 실제 정본 token과 비교한 결과다.

## Owned token 재조회의 Linux·외부 적합성 검증

변경 없는 `896e4ef`로 Linux native에서도 종료 전 큐 수락·backend 종료·
자동 재등록·기존 큐 보존·이전 token 거부·현재 owned token 조회·명시적
ACK·중복 prompt 소비 없음이 통과했다
(`linux-openclaw-owned-claim-recovery/output/claimed-recovery.json`).
같은 커밋의 Linux 공통 gate 413개는 81.337초에 통과했다
(`linux-inbox-owned-token-core/result.json`). 모델·사람·agent turn은 0회다.
테스트 VM은 중지했다.

외부 stdio 적합성 검사기에 일반 inbox의 소유 claim 제외, targeted token
조회, 대화 격리, ACK 후 targeted 부재를 추가했다. Messaging은 33개,
events는 36개가 통과했다(`inbox-owned-token-external-{messaging,events}.json`).
서버 구현을 import하거나 저장소를 읽지 않는 경계 검사다. Wire proxy가
message_ids를 제거하면 targeted owned token 검사에서 실패하는 회귀도
통과했다. Checker 회귀 13개가 통과했다
(`inbox-owned-token-external-checker.log`). 실제 wire frame 79개(성공
method 9종/notification 1개)의 공개 출력 구조도 검증했다
(`inbox-owned-token-external-wire-schema.json`). Lease 보존의 증거는
별도 정본 검사이며, 이 구조 검증으로 domain 결과 전체를 인증하지 않는다.

외부 검사기 확장을 포함한 Mac 최종 공통 gate 414개(핵심 243/Python
48/Node 123)가 74.814초에 통과했다
(`inbox-owned-token-external-core.log`). 앞선 Linux 413개와 다른 표본이다.
외부 검사기 확장의 Linux gate, 간헐적 burst ACK 실패와 나머지 전체
계획은 계속 미완이다.

## OpenClaw agent_end의 transport 복구

Agent 종료 hook이 죽은 host를 그대로 사용하던 경로를 공통 복구에
연결했다. 다른 route·종료된 참여는 건너뛰고, 복구 중 dispose는 새 host와
후속 idle 갱신을 막는다. Hook 자체가 수신 경계를 처리하고 idle을 기록한다.
실제 backend 종료 직후 검사에서 변경 전 EOF TransportError로 실패했다
(`openclaw-agent-end-recovery-red.log`). Route 격리·이미 종료된 참여 유지·
dispose 경합을 포함한 최종 연결 12개가 통과했다
(`openclaw-agent-end-recovery-final.log`).

Native 프로브 초회는 getGlobalHookRunner를 잘못된 내부 export에서 찾아
전달 표본 이전에 실패했다(`openclaw-agent-end-native-100.json`). 기존
capacity probe와 같은 공개 `dist/plugin-sdk/plugin-runtime.js` import로
바로잡고 재실행했다. 실패 로그를 보존하며 이 오류를 제품 transport
복구 실패로 분류하지 않는다. Linux·실제 모델 turn·사용자 UI·간헐적
burst ACK 실패와 전체 계획은 계속 미완이다.

수정한 고정 native 프로브에서는 실제 hook runner를 통해 같은 ref·
새 generation 재등록과 idle 복원을 확인한 뒤 큰 원문 100/100 수락·
prompt 소비·명시적 ACK가 통과했다
(`openclaw-agent-end-native-100-verified.json`). 복구 후 전송 p95 상한
514.525ms이며 모델·실제 agent turn·사람은 0회다. 공통 gate 416개
(핵심 243/Python 48/Node 125)는 74.598초에 통과했다
(`openclaw-agent-end-core.log`). 앞선 프로브 실패와 이 성공 표본은
구분한다. Linux와 전체 계획의 나머지는 계속 미완이다.

Linux 후속 검증도 변경 없는 `2f7ac31`에서 통과했다. 고정 native
OpenClaw의 agent_end hook으로 같은 ref·새 generation 재등록과 idle
복원을 확인한 뒤 큰 원문 100/100 수락·소비·ACK, 복구 후 전송 p95 상한
412.499ms를 확인했다
(`linux-openclaw-agent-end-native-100/output/boundary-recovery.json`).
공통 gate 416개도 Linux arm64/Python 3.11.2에서 82.241초에 통과했다
(`linux-openclaw-agent-end-core/result.json`). 외부 token 재조회 검사기의
앞선 Linux 미실행 기록까지 보완한다. 실제 모델·사람 UI·메신저·간헐적
burst ACK 실패와 나머지 P0–P5는 계속 미완이다.

## Hermes native API의 Linux 검증

변경 없는 `3b47940`의 Hermes v0.22.5 고정 plugin source를 Linux
arm64/Python 3.14.10에서 실행했다. 설치·lease·도구 dispatch·자동 복구·
세션/workspace·turn/finalize를 포함한 13개와 주입 API 관측 9개가
통과했다(`linux-hermes-native/output/{tools,injection}/result.json`).
공식 Python image는 조회 후 digest로 고정했고 기존 검증 환경의 exact
dependency 67개와 git source/tag/index를 기록했다. Credentials/사용자
프로필은 넘기지 않았고 검사는 network none이었다.

같은 Python 환경과 Node 24.22.2의 공통 gate 416개는 100.502초에
통과했다(`linux-python-314-hermes-core/result.json`). 제품 변경 없이
새 플랫폼 증거를 확보한 작업이다. TUI 세션 행과 namespace는 fixture,
모델·사람 UI·agent turn·메신저는 0회다. 제품은 계속 pull-only이며 이
결과를 native queue p95·idle wake·worker·전체 방향/원격의 인증으로
확대하지 않는다. 전체 계획은 미완이다.

추가 `--slow-registration`의 native 8개도 통과했다
(`linux-hermes-slow-registration/output/result/result.json`). 다른 대화의
등록을 막은 동안 정상 대화의 도구 dispatch가 진행되는 경로를 검증했다.
앞선 native 13개와 중복되는 검사를 고유 개수로 합산하지 않는다.
테스트 VM은 작업 후 Stopped로 확인했다.

## OpenClaw 소유권 기반 두 파일 설치

기존 native global 발견 규칙의 state/extensions 아래에 index.mjs와
openclaw.plugin.json을 설치한다. Immutable snapshot·Python 고정, private
journal·파일별 digest·anchored no-follow/CAS, 중단 복구와 사용자 파일
보존을 구현했다. Config·allowlist·native trust record는 바꾸지 않는다.
Native discovery가 경고하는 record-missing은 위조 provenance로 숨기지
않고, 로컬 plugin의 활성화는 운영자 선택으로 둔다.

OpenClaw component lease와 relocation에도 불변 root를 지정하는 경로를
연결했다. Backend가 없는 상태에서 snapshot 보존을 확인하고 plugin
unload 뒤 회수를 확인했다(`openclaw-owned-install-lifecycle-final.json`).
Session end에서 lease를 조기 해제한 변이는 prune 보존 검사에서
실패했다(`openclaw-owned-install-early-release-mutant.json`).

설치 전 red는 unsupported binding으로 실패했다(`openclaw-install-red.log`).
편집 manifest 거부·부분 설치 복구·plugin/parent symlink 보존·dry-run·
준비 upgrade의 두 root 보존을 포함한 설치/lease 48개가 통과했다
(`openclaw-install-ownership-tests.log`). 공개 CLI도 격리 환경 6회가
통과했다(`openclaw-install-cli/result.json`). 고정 native 프로브 초회는
출처 미확인 경고를 오류로 취급해 로딩 뒤 assertion에서 실패했다
(`openclaw-owned-install-native-first.log`). 이후 lease root의 macOS
경로 별칭 비교도 실패했으며(`openclaw-owned-install-native-local.json`),
기대 경고와 canonical path를 정확히 검사하도록 바로잡았다.

공통 gate 424개(핵심 251/Python 48/Node 125)는 75.383초에
통과했다(`openclaw-owned-install-core.log`). Native 표본은 모델·물리적 UI·
실제 agent turn·메신저를 호출하지 않았다. Linux 설치·owned queue/UI와
전체 계획은 계속 미완이다.

OpenClaw 설치의 Linux 후속 검증은 변경 없는 `f5aaee3`으로 통과했다.
고정 SDK의 global 자동 발견·native 도구·DM pull/ACK·설치 업데이트/
제거 후 기존 plugin 재개·backend 없는 prune 보존·unload 후 lease와
old root 회수를 확인했다
(`linux-openclaw-owned-install/output/installed-lifecycle.json`). Native
record-missing 경고는 그대로 보존했으며 신뢰 기록을 위조하지 않았다.
공통 gate 424개도 Linux arm64/Python 3.11.2에서 82.964초에 통과했다
(`linux-openclaw-owned-install-core/result.json`). 테스트 VM은 중지했다.
모델·실제 turn·사람 UI·메신저는 0회이며 owned queue/UI와 간헐적
burst ACK 실패·나머지 P0–P5는 계속 미완이다.

## 계측 wrapper 없는 OpenClaw owned queue 검증

설치한 index.mjs/manifest를 그대로 native global discovery에 맡기는
`--installed-queue` 프로브를 추가했다. 고정 SDK의 별도 runtime은 fixture
세션 upsert·queue 관측에만 사용하고 생산 binding의 API·명령·guard를
교체하지 않는다. Snapshot 업데이트·설치 파일 제거 뒤 old loaded
plugin으로 원문을 전달하고, backend 없는 prune 보존·unload 회수도
함께 검사한다.

macOS arm64/Node 24.22.2/OpenClaw 2026.10.9에서 큰 원문 100/100
수락·소비·ACK, p95 상한 513.012ms가 통과했다
(`openclaw-owned-queue-native-100.json`). Native 전달을 끈 복사본은
정상 fixture 준비 뒤 actual queue 수락 검사에서 실패했다
(`openclaw-owned-queue-no-delivery-mutant.json`). 즉 별도 observer가
주입을 대신한 결과가 아니다. 모델·실제 agent turn·사람 UI·메신저는
0회이며 native record-missing 경고는 유지한다. 제품 코드는 바꾸지
않은 프로브 변경이므로 기존 공통 gate를 재실행 결과로 보고하지 않는다.
Linux의 이 경로·owned UI·간헐적 burst ACK 실패와 전체 계획은 미완이다.

Linux owned queue 후속 표본도 변경 없는 `8bfc698`으로 통과했다. 고정
SDK의 원본 설치 loader·manifest를 유지한 global 발견으로 큰 원문
100/100 수락·소비·ACK, p95 상한 403.083ms를 확인했다
(`linux-openclaw-owned-queue-native-100/output/owned-queue-100.json`).
설치 업데이트/제거 후 전달, backend 없는 snapshot 보존, unload 뒤
회수도 함께 통과했다. VM은 중지했다. 모델·실제 agent turn·사람 UI·
메신저는 0회다. 제품 코드 변경이 없으므로 공통 gate는 재실행하지
않았다. Owned queue 오류/정책 전체·UI·간헐적 burst ACK 실패와
나머지 P0–P5는 계속 미완이다.

## OpenClaw owned 경로의 정책·backpressure 회귀

프로브의 설치 모드에 injection 거부·capacity retry·FYI 경계·32건
burst를 연결했다. 생산 loader·manifest·binding API는 교체하지 않는다.
별도 SDK runtime은 fixture 세션/용량 예약 행 준비와 큐 관측을 맡고
원문 주입은 설치된 binding이 수행한다.

고정 macOS SDK에서 네 실행이 통과했다
(`openclaw-owned-policy-regressions/{deny,capacity,fyi,burst}.json`).
Deny는 큐 비어 있음과 pull/ACK, capacity/FYI는 claim 반환과 새 메시지
없는 재수락/ACK, burst는 32/32 소비·ACK(16묶음/96조각)다. Native
RetryAdmission 재시도를 중지한 변이는 claim 반환 뒤 actual queue
수락 검사에서 실패했다(`openclaw-owned-capacity-no-retry-mutant.json`).
Burst는 소비 지연을 의도한 회복 표본이며 정상 p95 인증이 아니다.
모델·실제 agent turn·사람 UI·메신저는 0회다. 앞선 간헐적 ACK 실패가
이번에는 재현되지 않았으며 해결됐다고 판정하지 않는다. 제품 코드
변경이 없으므로 공통 gate는 재실행하지 않았다. Linux의 이 네 경로와
오류/정책 전체·UI·나머지 계획은 미완이다.

Owned 정책 회귀 네 실행의 Linux 후속 검증도 변경 없는 `ce9b250`으로
통과했다(`linux-openclaw-owned-policy-regressions/`). Injection 거부의
pull/ACK·큐 비어 있음, capacity/FYI의 claim 반환 뒤 새 메시지 없는
재수락/ACK, burst 32/32 소비·ACK(16묶음/96조각)를 확인했다. 네
archive hash가 같고 tracked dirty false이며 모델·실제 turn·사람 UI·
메신저는 0회다. 테스트 VM은 중지했다. 공통 gate를 재실행한 결과로
보고하지 않으며, 간헐적 ACK 실패 해결·정책/오류 전체·UI·나머지
계획은 계속 미완이다.

## 요청별 내부 오류 응답과 효과 보존

예상하지 못한 RuntimeError/OSError가 응답 없이 연결을 끝내고 KeyError는
잘못된 인자로 분류되던 경로를 수정했다. 원 request ID의 -32603/
internal server error를 반환하고 다음 요청을 처리한다. 비직렬화 내부
결과도 -32602로 잘못 분류하지 않는다. 내부 상세·traceback은 노출하지
않고 stderr에는 exception class만 기록하며, diagnostic 쓰기 실패도
원 응답을 바꾸지 않는다. 이미 발생한 효과를 rollback했다고 주장하지
않고 자동 retry/ACK를 하지 않는다. Broken transport는 기존처럼 닫는다.

변경 전 세 exception 분기와 claim 후 실패 검사는 실패했다
(`protocol-internal-error-red.log`). 내부 NaN 결과의 오류 분류도 별도
red에서 실패했다(`protocol-result-serialization-red.log`). 실제 정본
claim을 만든 뒤 오류를 주고 같은 연결의 targeted token 조회에서
복구되는 경로와 원문 보존·ACK 분리를 검사했다. 실제 Python/Node SDK와
서버 subprocess도 post-claim fault fixture로 원문 회수·명시적 ACK·
같은 session handle 유지·내부 상세 비노출을 통과했다
(`protocol-internal-error-{python,node}-sdk.log`). 이 fixture는 별도 테스트
프로세스에서만 오류를 주입한다.

SDK 회귀 추가 전 공통 427개는 76.534초에 통과했다
(`protocol-internal-error-core.log`). 이후 추가한 SDK 2개를 이 개수에
섞지 않는다. Domain-specific 오류·notification loop 전체·Linux 및
나머지 P0–P5는 미완이다.

SDK 2개를 포함한 최종 공통 gate 429개(핵심 254/Python 49/Node
126)는 76.330초에 통과했다
(`protocol-internal-error-core-final.log`). 앞선 427개 표본과 구분한다.
Linux의 이 변경 검증과 전체 오류 계약·나머지 계획은 계속 미완이다.

## CLI·MCP·host protocol의 팀 공통 서비스

팀의 list/create/show/mute/unmute/leave/add/remove/lead orchestration을
`xsm.team_service.execute`에 모았다. CLI와 OperationService는 실제 caller,
사용자 질문 callback과 기존 출력 형식을 제공하고, target 해석·정책 판단·
변경·동기화는 같은 서비스를 사용한다. 모델 인자로 승인 source를 받을
수 없고 callback이 없거나 거부하면 변경하지 않는다.

두 frontend의 실제 공통 서비스 경로, 거부 후 무변경/무발행, CLI/MCP
leave의 같은 publish를 검사했다. CLI leave가 publish하지 않던 기존
차이도 바로잡았다. 기존 leave 경로를 되살린 변이는 실패했다
(`shared-team-service-legacy-leave-mutant.log`). 새 검사 초회 red와
기존 팀 회귀를 포함한 20개 green을 보존했다
(`shared-team-service-{red,green}.log`). 공통 gate 449개(핵심 274/
Python 49/Node 126)는 79.966초에 통과했다
(`shared-team-service-core.log`). 다른 CLI 가족의 추출과 Linux 후속
검증은 계속 남아 있다. 중간 커밋은 전체 완료 지점이 아니다.

직전 내부 오류 변경의 Linux 검증도 완료했다. 변경 없는 `b08463e`의
429개가 Python 3.11.2에서 85.369초, Python 3.14.10에서 102.503초에
통과했다(`linux-protocol-internal-error-core/result.json`,
`linux-python-314-internal-error-core/result.json`). 이 결과는 팀 서비스
변경 전 표본이며 현재 449개와 섞지 않는다. 테스트 VM은 중지했다.

## CLI·model host의 보드 공통화와 미관측 버전 보존

Show/set/log/decisions/mute/unmute/sync를 board_service에 모았다. CLI와
OperationService가 이를 공유하고, 모델용 xsm_board에 기존 CLI의
decisions/sync를 연결했다. 실제 사용자 decide는 모델 인자에 열지
않고 기존 질문 결속 경로로 유지했다. 공개 입력 schema·native catalog와
외부 schema 검사도 갱신했다.

기존 CLI decisions는 membership 확인에 board.show를 호출해 출력하지
않은 보드 버전까지 읽음 처리했다. 그 뒤 set이 미관측 v2를 덮는 red를
재현했다(`shared-board-service-red.log`). 새 경로는 authorization만
확인하고 cursor를 바꾸지 않아 v2/v3가 함께 남는다. 같은 잘못된 read를
되살린 변이는 CLI/model 두 검사에서 실패했다
(`shared-board-unshown-read-mutant.log`).

기존 보드/팀 회귀와 새 서비스 48개는 green이었다
(`shared-board-service-green.log`). 이후 비회원의 새 action 거부와
public protocol의 decisions/sync 경로를 추가한 최종 공통 gate 479개
(핵심 304/Python 49/Node 126)는 82.461초에 통과했다
(`shared-board-service-core.log`). 외부 schema 검사는 board 정상 2개와
모델 decide 거부를 포함해 통과했다(`shared-board-service-schema.json`).
다른 CLI 가족의 추출·Linux 후속과 전체 계획은 계속 진행한다.

## Operation 결과 인코딩과 passive FYI의 구조 보존

Team list/show와 board log/decisions가 passive FYI를 붙이면서 JSON 뒤에
문장을 이어 전체 결과가 text로 바뀌던 경로를 재현했다
(`structured-team-board-red.log`, 네 분기 실패). 공통 인코딩 선언을
사용해 pending/incoming을 JSON 필드로 유지하고 읽은 claim은 별도
ACK하도록 했다. 새 pending metadata를 반영하기 전 두 exact-object
검사 실패도 보존했다(`structured-team-board-green.log`).

Host protocol은 같은 선언에 따라 text를 그대로 text envelope에 넣고,
JSON처럼 보인다고 임의 해석하지 않는다. 선언된 JSON 작업의 비객체/
깨진 JSON은 -32603이다. 두 동작의 변경 전 red도 보존했다
(`operation-result-envelope-red.log`). Public 출력 schema는 이제
operation result 객체를 요구한다. 전체 operation-specific 필드 schema는
여전히 남아 있다.

Protocol·공통 서비스·기존 team/board 회귀 90개가 통과했다
(`operation-result-envelope-green.log`). 외부 출력 검증은 정상 14개/
거부 14개와 기존 wire 79개를 통과했다
(`operation-result-envelope-wire-schema.json`). 앞선 FYI 구조 보존
단계의 공통 480개는 82.952초에 통과했으며
(`structured-team-board-core.log`), 이후 두 encoding 검사를 이 표본에
섞지 않는다.

인코딩 선언까지 포함한 최종 공통 gate 482개(핵심 307/Python 49/
Node 126)는 83.930초에 통과했다(`operation-result-envelope-core.log`).
앞선 480개와 구분한다. 보드 미관측 버전 문제는 불변 노드 자체의
삭제가 아니라 후속 render의 활성 버전에서 가려지는 문제였다. 실제
사용자 데이터의 과거 cursor 영향은 이 fixture로 확정하지 않으며
소급 수정을 하지 않는다.

## 단일/다중 송신의 공통 서비스

CLI와 모델 host의 single/multi send를 send_service.execute로 모았다.
호출자 증거·원문 파일 입력·출력은 frontend에 남기고 요청 ID 선택,
attachment 준비, 송신과 group 복구를 같은 orchestration으로 연결했다.
CLI path 읽기 권한은 adapter 인자로만 고르며 모델 data의 source 값이
이를 고를 수 없다. 같은 요청 ID의 바뀐 attachment는 실제 송신 전에
충돌로 거부한다.

초회 추출에서 질문 송신이 쓰는 helper의 남은 호출자 한 곳을 확인했다.
실제 질문 회귀가 AttributeError로 실패한 것을 보존했고
(`shared-send-question-helper-red.log`), 공통 prepare 함수에 다시 연결한
뒤 질문/질문그룹/첨부/다중 송신 57개가 35.652초에 통과했다
(`shared-send-question-materials-green.log`). 그 전 송신 중심 99개
통과만으로 질문 경로까지 확인했다고 계산하지 않는다.

Frontend 공통 경로·질문 helper·frozen bytes·source 권한의 새 5개가
통과했다(`shared-send-service-final.log`). CLI를 옛 직접 송신 경로로
되돌린 변이, 모델 data에서 CLI 파일 권한을 고르게 한 변이는 각각
실패했다(`shared-send-{legacy-cli-route,source-authority}-mutant.log`).
변경된 핵심과 기존 material/multisend/question-group 회귀를 포함한
공통 gate 511개(핵심 336/Python 49/Node 126)는 90.232초에 통과했다
(`shared-send-service-core.log`). 오래 대기하는 기존 question interface
회귀는 별도 57개 실행 결과이며 120초 gate에 억지로 합치지 않는다.
다른 CLI 가족과 독립 참여자·전체 계획은 이어서 구현한다.

## 독립 구현 피드백에 따른 파일·wake·결정 계약 보완

명세만 제공한 별도 구현이 첨부 식별자/내용 재조회·fallback 조건·wake
타입·오류 순서·decline/cancel/만료 의미를 완결할 수 없다고 보고했다.
공통 receive 검증에서 얻은 수신자 소유 files metadata를 inbox items에
제공하고, input의 xsm_files(storage_id/entry_id/outgoing/encoding)와
직접 연결했다. Sender에도 request-local producer metadata(send/grouped/
materials), preparation 실패에는 error.data.attachment_error를 제공한다.
표시 문자열을 파싱해 id나 의미를 추측하지 않는다. CLI/MCP의 기존
표시 문자열은 유지하며 metadata는 전역/호스트 공유 변수에 두지 않는다.

Wake는 true/false/unknown(null) 정책 값이며 수락/소비 증거가 아니다.
알 수 없는 저장 값은 unsolicited event를 만들지 않고, 누락된 legacy
값의 auto 의미는 유지한다. 만료 전에 받은 답의 exact replay가 만료 뒤
answered를 돌려주던 경로도 visible expired를 반환하도록 바로잡았다.
신규 callback의 만료 거부와 실제 적용 전 검증은 기존처럼 유지한다.

변경 전 missing files·unknown wake·expired replay의 실패를 보존했다
(`public-inbox-contract-red.log`). 처음 file 검증에서 없는 action/incoming
인자를 쓴 두 실행 실패도 보존했고, 공개 input에 맞춰 수정했다
(`public-inbox-contract-{green,verified}.log`). Sender metadata/error.data의
red도 남겼다(`public-send-metadata-red.log`). Sender outgoing read·recipient
copy read·변경 요청 복구·metadata의 request-local 유지·명시적 ACK·
원문 보존과 기존 회귀를 포함한 최종 공통 519개(핵심 344/Python 49/
Node 126)는 82.042초에 통과했다(`public-file-contract-core-final.log`).
추가 공개 경로/결정/검사기 77개가 통과했다
(`public-file-contract-verification.log`). TypeScript 선언도 tsc strict
검사를 통과했다(`public-inbox-contract-types.log`).

격리된 실제 stdio 15개 frame과 inbox 3개는 새 schema를 통과했다
(`public-file-contract-isolated-wire.json`, `public-file-contract-schema-final.json`).
Schema의 정상 inbox 2개/거부 7개와 input/output/operation 기존 검증을
함께 실행했다. 초기 standalone wire probe는 격리 누락으로 실제 상태를
썼으므로 유효 증거에서 제외했고 사건 기록과 승인된 36개 quarantine
절차를 보존했다([사건 기록](incidents/2026-11-02-probe-isolation.md)).

파일 입력 frame보다 큰 engine-limit bundle의 streaming upload API, 다른
operation-specific 결과 schema와 native UI/worker/행렬은 이어서 구현한다.

## 질문·연결·상태 조회 공통화와 독립 구현 오류 재현

CLI와 MCP의 ask/connect/question-status를 question_service로 모았다.
질문 그룹 확장, 자료 준비, 기존 요청 복구와 네트워크 상태 합성은
공통 함수가 처리한다. 호출자 증명·대기 상한·입력 pump·표시·claim은
각 frontend가 맡는다. 대기 취소가 상대 질문 취소나 ACK가 되지 않는
경로도 확인했다. 기존 회귀와 신규 검사는 122개가 40.725초에 통과했다
(`shared-question-service-current.log`). CLI가 공통 ask 경로를 우회하는
변이는 호출 횟수 검사에서 실패했다
(`shared-question-route-mutant-fixed.log`). 첫 변이 실행은 TempState의
모듈 재로딩 전에 패치해 변이가 적용되지 않았다. 그 실행은 탐지
증거로 쓰지 않고 실패 로그를 보존했다.

독립 참여자의 v3 검증은 공개 suite 120회(중복 lifecycle 포함)와 추가
checkpoint 88개를 통과했지만 음수 wait 오류 불일치 2개로 종료 코드
1이었다. 실제 UI·만료나 전체 기능 인증으로 계산하지 않는다.
부모 작업자가 send/inbox의 음수 wait가 -32004를 반환하는 경로를
새 검사로 재현했다(`negative-wait-red.log`, 실패 2개). 해당 입력
schema에 minimum=0을 추가해 먼저 -32602를 반환하도록 수정했다.
유효한 양수 wait는 기존 -32004를 유지한다. 생성된 공개 schema와
OpenClaw 도구 목록도 맞췄다. 새 경로 3개와 native catalog 검사가
통과했다(`question-wait-green.log`, `question-catalog-green.log`).
독립 동결 서버 재실행은 이 수정 뒤 별도로 수행해야 한다.

공통 gate는 522개(핵심 347/Python 49/Node 126)가 78.834초에 통과했다
(`shared-question-service-core.log`). 전체 승인 계획은 계속 미완이다.

## 일반 런타임의 불투명 로컬 주소

일반 참여자의 질문 송신과 팀 구성원 확장이 runtime:session_id를 만들지만,
해석기는 claude/codex 접두사만 받으므로 정본에 도착하지 않는 경로가 있었다.
로컬 runtime·canonical profile home·conversation을 모호한 구분자 없이
JSON으로 인코딩해 hash한 peer:<64 hex>를 추가했다. 팀은 이름으로 현재
구성원을 선택한 뒤 완전한 대화 주소를 쓴다. 질문도 같은 주소를 사용하고,
connect는 선택 뒤 원래 이름을 다시 해석하지 않는다. 기존 ref/claude/codex는
유지하며, 프로필이 다른 같은 세션 ID와 짧은 ref 충돌을 구분한다. 주소는
권한이나 실행 세대의 증거가 아니다. session.open의 추가 address는 옛 서버
호환을 위해 schema/SDK에서 optional로 두었다.

새 실제 경로 검사는 직전 질문 서비스 추출이 BoundHost에 없는 pump를
즉시 참조하는 회귀도 잡았다. 비차단 프로토콜 호스트의 pump를 명시해
수정했다. 첫 generic question red는 이 AttributeError이므로 주소 결함의
red와 혼동하지 않는다. 질문의 runtime-only 주소와 connect의 이름 재해석을
다시 넣은 변이는 각각 새 검사에서 실패했다(`selected-peer-mutants.log`).
프로필 분리·불완전 pointer·팀 재시작·기존 질문 회귀를 포함한 133개는
40.233초에 통과했다(`generic-peer-regression.log`). 공통 gate 526개
(핵심 351/Python 49/Node 126)는 79.443초에 통과했다
(`generic-peer-core.log`). 공개 schema 검사도 통과했다
(`generic-peer-schema.json`). 원격 신원과 native UI 전체 검증은 미완이다.

## 독립 참조 참여자 통합과 기능 전수표

명세·checker만 제공한 별도 구현을 examples/independent-participant/에
추가했다. 부모 작업자는 a1e4804의 새 git archive 서버에서 독립 v3 검증기를
그대로 재실행해 공개 suite 120회(중복 포함), 후속 시나리오 8개와 checkpoint
90개 통과·종료 코드 0을 확인했다. 이전 음수 wait 불일치 2개는 이 동결본에서
-32602로 통과했다. 이전 실패 증거는 보존했다. 자체 transport mock 검사
16개와 결함 변이 4개 탐지도 별도로 재실행했다. 세부 경계와 미완은
[독립 참여자 기록](independent-participant.md)에 적었다.

자체 mock 검사를 120초 공통 명령에 통합했다. 기존 526개(351/49/126)와
독립 mock 16개·변이 4개가 77.268초에 통과했다
(`independent-integrated-core.log`). 이것은 실제 네이티브 UI·사람 승인·
만료·메신저나 독립 구현의 전체 기능 인증이 아니다.

새 inventory 명령이 HOME/XSM_HOME을 격리해 CLI 말단 명령 73개·공개 작업
21개·host method 11개를 재현했다. [전수표](feature-inventory.md)는 각
CLI의 positional 선택값과 공개 작업 대응·미확정을 기록한다. doc의 노드
작업과 기존 endorsement가 동등하지 않다는 차이, Claude/Codex 한정 worker
parser도 포함했다. 미확정 항목을 범위 제외나 통과로 바꾸지 않았다.

## 문서 노드 작업의 공통 서비스와 공개 경로

CLI doc의 add/render/log/next/leaves/show를 doc_service로 모으고 공개
xsm_doc 작업으로 연결했다. 공개 작업 수는 21개에서 22개가 됐다.
생성 schema·예제·OpenClaw 정적 catalog와 Hermes manifest도 갱신했다.
모델 상대 경로는 인증된 대화 cwd를 쓰고 CLI는 기존 셸 cwd를 유지한다.
next의 표시와 JSON은 같은 노드 표본에서 만들고, CLI 기존 JSON에는
추가 text를 넣지 않는다. 기존 파일/노드 포맷은 바꾸지 않았다.

모델 author는 반드시 세션에서 만든 agent이며 호스트의 터미널 감지나
모델 데이터로 human을 만들지 않는다. endorsed는 기존 사용자 결정
경로에 남겼다. 사람 터미널 감지를 강제로 켠 변이가 endorsement를
만들면 새 검사가 실패했다(`doc-human-author-mutant-final.log`). 첫 변이는
비 tty 표본에서 위험 분기를 실행하지 못해 탐지하지 못했으므로 성공
근거로 쓰지 않는다. 추정 caller의 파일 접근 6개 동작도 red를 기록한 뒤
FILE_READING guard에 포함해 막았다(`doc-caller-{red,green}.log`).

초기 구현 전 3개 실패는 doc_service가 없는 상태였다
(`doc-service-red.log`). 실제 protocol add→parent revision→show/log/
leaves/next→render와 없는 parent 무기여, CLI/MCP 공통 경로 및 위의
작성자/호출자 검사를 실행했다. 기존 문서·프로토콜·네이티브 catalog 회귀
75개, identity 회귀 포함 52개, 설치 회귀 38개가 각각 통과했다.

첫 공통 실행은 Node 두 검사의 옛 21개 기대값 때문에 실패했다
(`doc-service-core.log`). 22개로 갱신한 최종 공통 실행은 기존 핵심
541개(366/Python 49/Node 126)와 독립 mock 16개·변이 4개가 79.577초에
통과했다(`doc-service-core-final.log`). 그 뒤 CLI 읽기에서 registry.me를
불필요하게 호출하지 않도록 기존 동작을 보존한 변경은 문서/CLI 15개로
별도 확인했다(`doc-service-cli-final.log`). 공개 schema 검사도 통과했다
(`doc-service-schema-final.json`). 실제 전체 native 행렬과 문서 결과의
완전한 operation-specific JSON Schema는 미완이다.

## 첨부 사본 조회의 공통 경로

CLI files와 xsm_files의 manifest/entry 선택·owner 검사·text/base64 응답을
files.read_result로 모았다. frontend의 인증된 caller와 기존 표시·오류
처리는 유지한다. 파일 경로나 이름이 조회 주소가 되지 않는다.

같은 binary outgoing copy를 실제 CLI와 MCP로 조회해 bytes와 결과 필드를
대조하고, 다른 owner의 조회를 거부하는 검사를 추가했다. 초기 missing
read_result 실패와 MCP의 passive inbox_pending 추가를 놓친 fixture 실패는
각각 보존했다(`file-read-service-{red,green}.log`). 해당 필드를 명시적으로
0으로 대조한 뒤 나머지 결과·실제 bytes를 비교했다. 기존 files/material/
protocol 회귀 123개가 9.582초에 통과했다
(`file-read-service-regression.log`). 공통 542개(핵심 367/Python 49/Node
126)와 독립 mock 16개·변이 4개는 79.239초에 통과했다
(`file-read-service-core.log`). 큰 첨부의 프레임 분할 문제는 이 조회
공통화로 해결됐다고 계산하지 않는다.

## 프레임보다 큰 첨부 묶음 준비와 UTF-8 경계

files.upload.open/write/commit/status/abort를 추가했다. 192KiB decoded chunk,
1MiB/file·4MiB/bundle·연결 전체 4MiB raw buffer 예약·16개 handle을 제한한다.
파일 경로는 받지 않는다. 각 entry의 크기/hash와 exact replay를 검사한 뒤
기존 materials.prepare에 넘기며, frozen manifest·request/body binding·quota·
capability·fallback은 기존 엔진을 쓴다. 준비는 body 송신이나 ACK가 아니다.
세션 종료/abort는 volatile buffer만 해제하며 영속 사본과 상대 업무는 남긴다.
프로세스 PID가 같아도 protocol_generation이 달라지면 옛 handle을 쓸 수 없다.

영속 준비는 기존 material-intents index로 request ID에 따라 회수한다.
index 부재는 unknown이며 모든 storage 단계의 rollback 증거가 아니다.
완료 전 buffer는 연결 종료 뒤 재개하지 못한다. 완료 뒤에는 frozen manifest를
일반 xsm_send/xsm_ask로 전달한다. SDK 두 종에 caller-read bytes 준비 helper를
추가했다. Python은 실제 stdio에서 1MiB 파일 4개, 총 4MiB를 준비→명시 송신→
수신 bytes/SHA 대조→ACK했다. TypeScript는 1MiB binary의 부분 chunk 재개와
같은 frozen manifest 재조회·송수신을 확인했다. 준비 직후 수신 inbox가 비어
있음도 두 경로에서 확인했다. 큰 본문 자체의 streaming을 검증한 것은 아니다.

초기 6개 missing-module red와 SDK missing-helper red를 보존했다
(`file-upload-red-six.log`, `file-upload-python-wire-red.log`). 추가 한계/세대/
abort/준비 실패 복구까지 현재 unit은 12개다. 동일 PID·다른 protocol generation
결속 검사는 실제 red 뒤 수정했다(`file-upload-generation-red.log`). digest와
연결 공통 예약 한도를 무시한 두 변이도 실패했다(`file-upload-mutations.log`).
각각 16 active slot과 4MiB aggregate 한도를 실제 채운 뒤 다음 요청 거부와
abort 후 회수를 검사했다. capability 거부 뒤 buffer 해제·frozen ID 보존과
동일 commit 복구도 확인했다.

공개 검사기에 uploads suite를 추가했다. 기존 lifecycle 16개가 포함된 39개
검사가 실제 stdio에서 통과했다(`file-upload-compatible-wire.json`). 관찰한
응답 72개와 공개 input/output/operation schema 검사가 통과했다
(`file-upload-compatible-schema.json`). 초회 36개 통과 뒤 hash 거부 검사를
넣으면서 active buffer의 상태를 unknown으로 가정해 한 번 실패했다
(`file-upload-public-wire-final.json`). uploading과 영속 index를 구분하고
abort 뒤 index 부재를 확인하도록 fixture를 수정했다. 실패는 보존했다.

UTF-8 경계를 조사한 대상은 서버 입력 reader와 공개 checker reader 두 곳이다.
서버는 잘못된 UTF-8 byte가 surrogateescape를 통해 JSON 문자열로 들어오던
경로를 엄격히 거부한다. checker도 UTF-16BE/UTF-32BE 자동 판별, 중복 JSON key,
NaN 수락을 거부한다. 초기 byte-limit 검사에서 기존 명세의 문자 수 계약을
놓쳤다. 그 초회 multibyte 초과 기대값 실패를 제품 결함으로 세지 않는다.
1MiB 문자 수 제한을 유지하고 raw UTF-8 read만 그 네 배 이내로 제한했다.
한글 400000자 입력은 frame 오류가 아닌 원래의 version 오류를 유지하며,
실제 문자 수 초과와 malformed UTF-8은 거부한다
(`utf8-character-{contract-green,regression}.log`).

최종 공통 gate 558개(핵심 381/Python 50/Node 127)와 독립 mock 16개·변이
4개가 83.67초에 통과했다(`file-upload-compatible-core.log`). tsc strict와
schema 생성기의 재실행 동일성도 확인했다. method는 11개에서 16개, 모델
작업은 22개를 유지한다. nested manifest/reference와 모든 operation-specific
결과 schema, 전체 native 행렬·실제 UI/worker/remote/messenger는 미완이다.

실제 서버 시계의 30분 만료 검사를 별도로 시작했다. 서버 동결본은 a1e4804,
사용자 답은 합성 host callback이며 실제 사람/UI로 계산하지 않는다. 첫 실행은
일반 SDK의 decision.response 차단으로 실패했고, 지원되는 trusted host helper로
수정한 두 번째 실행은 대기 중이다(`real-decision-expiry-run2/progress.json`).
만료 뒤 replay·늦은 답·기존 invocation 적용 거부를 확인하기 전 완료로 세지 않는다.

## Manifest 해시 입력 바이트와 파일 결과 구조

xsm_files의 manifest_bytes=true와 CLI --manifest-bytes를 추가했다. 기존 v1
compact UTF-8 serialization을 바꾸지 않고 그 해시 입력 bytes를 base64로 돌려준다.
caller는 bytes의 SHA-256과 bound digest를 대조하고, UTF-8 JSON을 파싱해 sha256만
뺀 원래 manifest 전체와 비교한다. 다른 언어의 float formatter로 재직렬화하지
않아도 검증할 수 있다. entry_id와는 함께 쓰지 않고 같은 copy owner 검사를 거친다.
서버 원본 경로나 새 권한을 노출하지 않는다.

초회 flag 부재 실패 3개를 보존했다(file-manifest-bytes-red.log). 기존 파일/
material과 새 query 회귀 75개가 통과했다. 고정된 Unicode·지수 표기 직렬화
vector를 추가해 v1 바이트를 보존하며, 공백을 추가하는 변이가 실패하는 것도
확인했다(file-manifest-format-mutant.log). 실제 Python/TypeScript stdio 사본
검사도 반환 preimage의 SHA를 bound metadata와 대조한다.

file-result.schema.json은 manifest/entry/preimage의 세 형태, v1 manifest와
reference 전체 필드, passive claim metadata를 기술한다. upload 결과의 nested
객체도 같은 정의를 쓴다. 공개 checksum/byte 동작 42개(기존 lifecycle 포함)와
관찰 응답 74개가 schema를 통과했다(file-canonical-public-{wire,schema}.json).
구조 검사 정상 3개·거부 8개와 실제 bytes/hash 검증을 구분한다. newline이 붙은
해시/ID를 JSON Schema의 $ anchor가 받던 red도 보존한 뒤 엄격한 끝 조건으로
고쳤다(file-result-schema-{red,green}.log). 다른 domain의 전체 결과 계약이
완료됐다는 뜻은 아니다.

같은 작업에서 Linux 3.14의 120초 실패를 보존하고 검사 그룹의 격리를 유지한
병렬 구성으로 바꿨다. 최종 macOS 공통 565개(핵심 388/Python 50/Node 127),
독립 mock 25개·변이 8개가 63.192초에 통과했다(file-contract-verified-core.log).
Linux의 새 구성은 다시 확인해야 한다. 상세는 linux-validation.md에 구분했다.

## 일반 참여자의 발견·원격 신원·lease 복구

일반 참여자의 DM 주소는 동작해도 directory와 remote identity는 Claude/Codex
목록에 묶여 있어 새 런타임이 제외되는 경로를 확인했다. runtime slug를 공통화하고,
등록된 protocol 참여자는 가상 profile namespace·현재 pointer·PID/start·실행
generation·실제로 유지 중인 lease로 검증한다. native 두 하네스의 기존 configured
home/owner 검사는 유지한다. 새 참여자 때문에 homes.json을 추가·수정하지 않는다.
등록은 publication이나 통신 권한이 아니다. 현행 deny/exclusion과 최종 선택 검사를
적용하며, 동명 새 대화나 같은 PID의 다른 실행으로 대체하지 않는다.

P2P 공개 execution generation에 protocol nonce를 포함하되, 기존 native record의
hash 입력 bytes는 그대로 유지했다. accepted 원문은 같은 대화의 재시작 뒤 회수할
수 있다. broker는 protocol 수신자를 낯선 runtime이라는 이유로 Codex adapter에
넘기지 않고 정본 event/inbox를 맡긴다. native 입력 큐 인계·소비는 해당 호스트가
보고한다. name/activity는 protocol 관측 출처로 표시하고 save 때 갱신 시각을 기록한다.

초기 local discovery/remote endpoint 실패를 보존했다(generic-directory-red.log).
현재 9개 fixture는 실제 등록 peer 선택, homes 무변경, 미보유 lock 위조 거부,
publication과 permission 분리, deny 재검사, 같은 PID 재개와 old handle 거부,
legacy adapter 미호출 및 기존 native hash 호환을 확인한다. registration proof,
legacy wake, protocol generation을 각각 제거한 3개 변이는 실패했다
(generic-directory-mutations.log). Native directory/network identity 기존 83개가
6.249초에 통과했다. fixture 초회에는 없는 config.save를 호출한 오류 1개가 있어
기존 private JSON fixture 방식으로 고친 뒤 통과했다.

두 실제 private QUIC service에 protocol actor를 등록한 2개 추가 검사는 요청/
회신·claim/ACK, 같은 대화 새 실행 뒤 accepted 원문 회수를 확인했다. 해당 local
9개와 합쳐 11개가 7.445초에 통과했다(generic-directory-network-first.log).
네트워크 기존 suite는 237개 중 236개 실행 통과·1개 skip으로 148.964초에 끝났다
(generic-network-full-regression.log). skip은 official relay binary를 명시하지 않은
기존 self-host fixture 조건이다. 이 작업자가 이번 실행에서 기록했으며 scope
제외 승인은 없다. private relay executable과 Mac UDP profile 조건을 갖춘 뒤
재실행해야 하므로 전체 suite 완료로 세지 않는다.

session.close의 종료 표식 쓰기가 실패해도 lease는 해제되는데, 살아 있는 공유
PID를 옛 소유자로 읽어 재접속을 막던 경로도 실제 OSError로 재현했다. protocol
소유권은 보유 lease로 판단해 복구하고, non-protocol 기존 pointer의 보수적 검사는
유지한다(protocol-close-marker-{red,green}.log). lock symlink 수락도 red 뒤
O_NOFOLLOW/regular-file/UID 검사로 거부했다(protocol-owner-lock-red.log).
후속 protocol/local 63개가 7.776초에 통과했다. 일반 runtime 경로가 열린 것이지
실제 native UI/모델/물리 원격/외부 메신저 전체 인증이 완료된 것은 아니다.

같은 PID에서 선택 도중 대화가 재등록되는 local race도 추가했다. 최종 local
10개가 1.292초에 통과했고, 해당 generation 비교를 제거한 네 번째 변이가
실패했다(generic-directory-race-mutant.log). 최종 공통 577개(핵심 400/Python
50/Node 127)와 독립 mock 25개·변이 8개는 64.628초에 통과했다
(generic-participant-final-core.log). 두 private-service 검사는 이 공통 수에
합치지 않았다. 이번 변경의 Linux 재검증과 물리 머신·실제 native model/UI
검증은 별도 미완이며, 이전 4ccc745 Linux 통과를 가져다 쓰지 않는다.

## 없는 사본 조회의 도메인 오류

독립 v6가 유효한 모양의 없는 storage ID 조회에서 FileNotFoundError가 -32603으로
돌아오는 것을 관찰했다. 파일 load 경계의 ENOENT를 copy-not-found FileError로
바꾸고, xsm_files는 알려진 file error를 ToolError.data.file_error.code로 보낸다.
오류 시 사본 경로나 원문을 반환하지 않는다. 예상 밖 IO 오류의 내부 오류 경로는
유지하며, 조회 거부가 rollback/자동 재전송의 근거가 되지는 않는다.

라이브러리와 실제 wire의 red를 보존했다(file-missing-copy-{red,wire-red}.log).
새 wire 검사는 -32602와 machine code를 확인한 뒤 같은 연결에서 원래 claim을
ACK해 조회 실패가 소비나 연결 종료가 되지 않음을 확인한다. 파일/material 계약
회귀 77개와 실제 stdio 3개가 통과했다(file-missing-copy-{green,wire-green}.log).
초회 공통 검사는 owner-mismatch의 옛 raw FileError 기대값 1개로 실패했다
(file-domain-error-final-core.log). 이를 실제 frontend ToolError와 구조화된 기존
owner-mismatch code로 대조하도록 바꿨으며, 새 최종 공통 결과는 별도 기록한다.

최종 공통 578개(핵심 401/Python 50/Node 127), 독립 mock 39개·변이 14개가
63.035초에 통과했다(file-domain-error-verified-core.log). 독립 v6의 새 decoder와
현재 서버의 domain 오류 수정은 버전별로 분리해 보존했다.

앞서 skip했던 self-host relay 표본은 Cargo.lock의 official iroh-relay 1.4.1을
private HOME/CARGO_HOME/target에서 준비한 뒤 실제 1개가 15.847초에 통과했다.
그 후 동결 3a1cdf5의 전체 network suite 237개를 relay 활성 조건으로 다시 실행해
skip 없이 257.036초에 통과했다(generic-network-with-relay-v2.log/json). 릴리즈용
git archive가 tests를 제외해 처음 재실행 입력이 import 실패한 것도 보존했고,
테스트 파일은 같은 commit의 git show에서 복원해 동결했다. 이 표본은 model 0,
로컬 private 실제 relay/QUIC이며 최신 missing-copy 수정이나 실제 native/물리
머신/외부 messenger 검증으로 확대하지 않는다.

## Handover 공통 서비스

CLI와 MCP의 show/선택/검증/이동 orchestration을 handover_service로 모았다.
실제 사용자 verdict 수집과 표시 방식은 frontend에 남겼고, 승인 출처가 없거나
비어 있거나 문자열이 아니면 이동하지 않는다. 승인 뒤에는 원래 이름 대신
선택한 불투명 주소로 같은 대화를 다시 검증한다. 후임이 종료되었으면 이동 전에
거부한다. 기존 unread 원문·질문·팀·보드 소유권 이동 엔진은 그대로 사용한다.

초기 missing-service 실패 4개를 보존했다(shared-handover-red.log). 신규 4개와
기존 handover/decision 회귀를 포함한 38개가 3.356초에 통과했다. 이름 재지정과
stale 후임 snapshot을 다시 넣은 두 변이가 각각 실패했다
(shared-handover-mutations.log). 최종 공통 600개(423/Python 50/Node 127),
독립 mock 39개·변이 14개는 65.793초에 통과했다(shared-handover-core.log).
실제 native UI나 원격 handover의 검증으로 확대하지 않는다.

## Owned worker 공통 dispatch

create/status/retry/reconcile과 run의 request ID 선택을 owned_service로 모았다.
CLI의 동기 실행과 MCP의 비동기 대기·취소 pump는 frontend에 유지했다. 같은
request ID를 CLI→MCP로 재호출해 실행 횟수 1과 동일 reply_id를 확인했다. CLI가
공통 dispatch를 우회하는 변이도 실패했다(shared-owned-route-mutant.log).

초기 공통 경로 검사 실패를 보존했고(shared-owned-service-red.log), 초회 회귀는
non-run의 WorkerError를 ToolError로 일괄 포장해 기존 예외 계약 1개가 실패했다.
공통 입력 ActionError만 frontend에서 변환하고 기존 worker 예외는 유지해 기존
회귀 33개가 3.636초에 통과했다. 실제 fake CLI process/강제 종료 경계의 추가
13개도 2.383초에 통과했다. 모델을 호출한 검사는 아니다.

최종 공통 633개(핵심 456/Python 50/Node 127), 독립 mock 39개·변이 14개가
70.744초에 통과했다(shared-owned-core.log). 신규 native worker provider 4종을
구현·검증했다는 뜻은 아니다. 그 목표는 여전히 남아 있다.

## 프로젝트 참여 변경 공통 서비스 (2026-11-02)

CLI join/leave와 모델 도구 xsm_join의 변경 적용을 scope_service로 통합했다.
사용자 답 수집과 typed consent 처리는 각 frontend에 유지하고, 승인 전의
프로젝트 루트를 고정해 승인 후 달라졌으면 정책을 쓰기 전에 거부한다.
이 단계는 join/leave에 한정된 구현 기록이며 reach/link 등 전체 CLI 추출은
아직 완료하지 않았다.

`python3 -B -m unittest tests.test_scope_service tests.test_link tests.test_mcp_forms`
69개가8.572초에 통과했다. 첫 실행에서는 /var와 /private/var 경로 별칭을
비교하던 새 검사1개가 실패했고, 시험 폴더를 realpath로 정규화했다.
임시 소스 복사본에서 루트 재검증을 제거하자 join/leave/승인 경로 검사3개가
모두 실패했다. 원본 코드는 변이하지 않았다. 로그와 변이 결과는
deliverables/protocol-foundation/scope-service-{regression,root-guard-mutation}.log와
scope-service-root-guard-mutation.json에 있다.

공통 핵심 gate(`python3 -B scripts/check-protocol.py`)도77.072초에 통과했다.
120초 기한을 유지했고 새 서비스 검사5개를 포함했다. 원시 출력은
scope-service-core.log에 있다. 이 결과는 macOS 핵심 회귀이며 Linux 또는
실제 native queue·UI·worker 검증을 뜻하지 않는다.

## 프로젝트 link/reach 변경 공통 서비스 (2026-11-02)

CLI link/unlink/reach와 모델 xsm_link/xsm_reach도 scope_service의 준비·적용·제거
경로를 호출한다. 권한을 넓히는 답 수집과 typed consent는 기존 frontend에
남긴다. 승인 전후 루트가 다르면 적용을 거부하고, reach의 소유 대화 필드는
준비 시 복사해 frontend가 이후 전달한 dict 변경을 따르지 않는다.

관련 회귀는74개가9.560초에 통과했다. 임시 복사본에서 link/reach 루트 재검증을
제거하면 관련 검사2개가 모두 실패했다. 핵심 gate는 Python466+SDK50+Node127,
총643개와 독립 mock39개/변이14개를77.709초에 통과했다. 명령은 앞 절과 같고
로그 접두어는 deliverables/protocol-foundation/scope-links-reach-다.
이 결과로 전체 CLI 추출이나 native 런타임 지원을 완료 처리하지 않는다.

## ACK 결과 계약 보강 (2026-11-02)

공개 ack-result.schema.json과 ack-contract.md를 추가하고 protocol describe의
필수 산출물 및 schema checker의 실제 ACK 응답 검증에 연결했다. ACK 결과의
canonical ID 배열·순서·중복 token idempotence와 pending count의 unknown을
문서화했다. 다른 결과 family 전체 스키마는 아직 미완이다.

검사 명령 scripts/check-protocol-schema.py는 정상 예제3개와 거부 예제7개를
확인했다. 임시 스키마에서 acked 필수 조건 제거·ID 타입 제거·임의 효과 필드
허용의 변이3개를 모두 검출했다(ack-schema-mutants.json).

현재 서버의 새 stdio events 표본과 별도 batch 표본에서52개 wire 관측을
검증했다(ack-result-schema-final.json). Batch의 실제 검사4개는 정상 원문2개
claim, 두 번째 잘못된 token 뒤에도 첫 ACK 영속, 중복 valid token 순서 보존,
남은 원문 최종 ACK다. 배치 오류가 앞선 ACK를 rollback하지 않는 기존 의미를
그대로 기록했다. 로그와 wire는 ack-current-wire, ack-batch-current-wire로
분리돼 있다. public export·격리 snapshot 설치 관련41개 검사도9.715초에
통과했다(ack-contract-export-install.log). 실제 사용자 승인/UI 증거는 아니다.

## 미지원 owned runtime의 Codex fallback 거부 (2026-11-02)

신규 owned 서비스 생성은 Claude/Codex로 제한돼 있으나, 저장된 worker의 runtime이
다를 때 명령 생성과 결과 파서 두 곳이 Codex로 fall through했다. 같은 레코드로
새 요청을 제출하는 경로도 별도 native 지원 검사가 없었다. 신규 provider 연결이나
이전 버전의 retained record를 다룰 때 다른 하네스를 대신 실행하면 안 되므로,
명령 생성·결과 해석·새 실행 제출의 세 경계에서 미지원 runtime을 명시적으로
거부한다. 기존 history/status 읽기와 저장된 reply 재전송 경로는 변경하지 않았다.

새 검사2개에서 Pi/OpenCode/Hermes/OpenClaw의 argv/결과 해석8건과 미지원
저장 레코드의 제출1건, 총9개 assertion이 수정 전 실패했다
(owned-runtime-fallback-before.log). 실제 모델/네이티브 실행은 없었다.
수정 후 관련34개 중33개가 통과하고1개는 과거 private Claude 원시 로그가
없어 기존 skip 조건으로 미실행이었다(owned-runtime-fallback-after.log).
이 미실행 검사는 사용자에게 그 fixture가 제공되는 경우 구현 담당자가 재확인할
항목이며, skip 자체를 승인이나 전체 회귀 완료로 해석하지 않는다.

핵심 gate는 Python468+SDK50+Node127=645개, 독립 mock39/변이14개를
82.716초에 통과했다(owned-runtime-fallback-core.log). 새 runtime provider를
구현한 것은 아니며, 네 신규 runtime의 worker/start/stop/resume는 계속 미완이다.

## Hermes native worker 실행 경계 (2026-11-02)

실제 native 부모 모델이 plugin 도구에서 public subagent_lifecycle을 호출해
자식 실행/결과·중복 거부·동일 process reconnect를 확인했다. 별도 cancellation도
실제 RUNNING→CANCELLED로 확인했다. 통합된 개발용 시험기는 complete9개,
cancel10개를 각각15.432/19.272초에 통과했다. 자식의 공급자 호출 중단이나
프로세스 재시작 후 재개, XSM owned provider 연결 완료는 아니다.
[Native worker 연결 경계](native-worker-boundary.md)에 미지원 native 옵션과
실패했던 시험기 실행, 범위 및 원시 결과 경로를 함께 기록했다.

모델 없는 callback preflight2개를 핵심 gate에 추가했다. 최신 macOS gate는
Python470+SDK50+Node127=647개와 독립 mock39/변이14개가83.232초에 통과했다
(hermes-worker-harness-core.log). Linux의 앞선 전체643/관련70개 표본과 구분한다.
전체 목표는 계속 active이며 native provider/UI·전체 matrix 등의 미완을 유지한다.

## Owned reply와 일반 프로토콜 부모 (2026-11-02)

일반 참여자를 부모로 한 실제 fake CLI process·정본 저장 검사에서 owned reply가
부모를 찾지 못했다. _native가 canonical home을 반환하는데 registry의 raw home과
필드별로 비교했기 때문이다. 이를 고친 뒤에는 fixture:<sid>를 세션 이름으로
해석해 다시 거부하는 별도 실패가 드러났다. 두 실패는 owned-generic-reply-before.log와
owned-generic-reply-canonical-only.log로 보존했다.

변경은 _reply_owned의 수신자 선택 한 곳과 주소 생성 한 곳이다. 양쪽 native
identity를 같은 규칙으로 정규화해 비교하고, 선택한 정확한 부모의 opaque address로
회신한다. 잘못된 registry 행은 건너뛰며 현재 scope/blocked 검사와 journal 예약
검증은 유지한다. 이 검사에서 CLI는 fake이고 모델 호출0이므로 실제 native
모델 지원 증거로 쓰지 않는다.

관련32개는5.270초에 통과했고, generic 부모 inbox의 원문 수신과 명시적 ACK도
실제 저장 경로로 확인했다(owned-generic-reply-after.log). 기존 native fake CLI
검사9개를 핵심 gate에 넣은 뒤 총656개(Python479+SDK50+Node127), 독립 mock39 /
변이14개가85.046초에 통과했다(owned-generic-reply-core.log).

## Hermes native CLI framing 연결 (2026-11-02)

Native CLI의 workspace/재개8개 실제 검사에 이어, 명령 생성·결과 해석 모듈을
구현하고 그 모듈이 만든 실제 CLI 명령으로 gateway 재시작 뒤 같은 대화의
문맥을 복구했다. 후속4개 검사와 read-only DB audit에서 같은 native SID와
cwd 보존을 확인했다. 자세한 경계·실패 기록은 native-worker-boundary.md에 있다.

모듈은 아직 owned runtime catalog나 실행에 연결하지 않았다. CLI의70자 native
ID를 UUID로 취급하지 않으며, 빈 resume/실패 result/본문의 metadata 위조를
명시적으로 거부한다. Framing7개와 의도적 변이3개가 검증됐고, 전체 핵심663개가
84.859초에 통과했다. Provider/profile admission과 owned journal·회신 연결은
계속 구현할 조건이다.

## 고정 provider와 pre-turn native identity (2026-11-02)

신규 native 실행은 설치본의 고정 catalog로 dispatch하며 공통 엔진에 새로운
runtime 이름 분기를 추가하지 않았다. Hermes 0.22.5를 owned 경로에 연결해
관리된 profile·operator native binary/interpreter·frontend hash를 검증한다.
Native provider metadata도 frozen 요청 plan에 포함하며 legacy plan bytes는
그대로 둔다. Root snapshot 보존과 알려진 admission 거부의 typed ToolError도
연결했다. Profile별 native backend secret scope를 사용하고 공유 gateway의
ambient worker/control hint를 제거했다.

모델 전에 native ID를 private descriptor로 journal에 고정하고 실제 native
actor의 raw/protocol-projected full identity를 worker budget에 연결한다.
기존 ordinary conversation은 모델 전에 거부한다. Metadata 정의만 검사하지
않고 실제 frontend/process/socket 경로와 일반 actor의 budget 분리를 검사했다.

같은 native 결과의 전송을 재실행 없이 복구하고, 실제 native 문맥 재사용과
회신3건의 명시적 ACK, idempotent request, 실제 max_depth 거부까지19개가
39.280초에 통과했다. DB는 첫 작업/recall2 calls, depth 도구 검사 포함 누적
5 calls/tool2였다. Source native gateway는 소유권을 확인한 PID만 종료했다.
원시 결과는 hermes-owned-native-recovered/result.json이며 실패/후속 회수는
[native worker 연결 기록](native-worker-boundary.md)에 구분했다.

최신 macOS model-free core는693개와 독립 mock39/변이14개가96.319초에
통과했다. 새 부정 경로 변이4개도 실제 assertion 실패를 확인했다. 이전 Linux
gate를 이693개 검증으로 소급하지 않는다. Linux 신규 회귀·다른 provider·native
UI/전체 lifecycle·30방향/remote/messenger 및 나머지 계획 조건은 미완이다.

## Node control client와 OpenCode awaited hook (2026-11-02)

공통 Node private-control client와 엄격한 JSON member decoder를 추가했다.
Native descriptor에서 Python controller와 실제 통신해 동일 SID/idempotent bind,
다른 SID 거부와 boolean ID·integer confirmation·duplicate member 거부를
확인했다. OpenCode input hook은 control을 await한다. 이것만으로 OpenCode
runtime을 owned catalog에 등록하거나 전체 worker 지원을 완료 처리하지 않았다.

Node SDK가 중복 protocolVersion 필드를 받아들이던 문제도 실제 peer 응답으로
수정 전 실패를 확인하고 공통 decoder에 연결했다. 첫 임시 peer는 문법 오류로
닫혀 검사가 잘못 통과했으므로 성공 근거에서 제외했다. Peer를 올바른 JSON
응답으로 고치고 정확한 duplicate 진단을 요구하자 수정 전 'Missing expected
rejection'으로 실패했다. 로그는 node-json-duplicate-before[-fixed-peer].log와
after.log에 구분돼 있다.

실제 OpenCode1.19.5/native Bun에서 초기 Socket fd 쓰기가 ERR_SOCKET_CLOSED로
실패했고, native 소스의 awaited hook이 provider를 부르기 전에500을 반환했다.
Bun의 connect fd 경로를 사용한 v5에서는6개 검사가 통과했다. 수락은 native
session callback1회+fixture provider1회였고, 거부는 callback1회+provider0회였다.
모델은 scripted fixture/model0이며 실제 LLM/owned journal/lineage 증거가 아니다.
과거 native 실패4개 실행과 최종 결과를 보존하고 각 native process를 종료했다.

SDK duplicate 허용·private integer confirmation 허용·native gate 생략의 임시
source 변이3개를 모두 assertion 실패로 검출했다(node-control-mutants.json).
704개(Python490+SDK50+provider26+Node138), 독립 mock39/변이14개를
100.825초에 통과했다(opencode-worker-control-core.log). 이 수치의 Linux 전체
실행은 아직 미실행이며, 앞선693개 Linux 결과와 구분한다.

## 개별 worker 승인 결과 계약 — 2026-11-03

[승인 결과 계약](approval-contract.md)에 `xsm_approve`의 snapshot·pending·legacy
구조를 정의했다. 실제 격리 stdio26개 검사와 frame28개, 예제4개·거부12개,
ID 제약 제거 변이1개와 wire 결함2종을 검증했다. Mac core908개는76.030초에
통과했다. 합성 worker 상태를 사용하는 검사이며 실제 사람/native UI 검증은 미완이다.
Domain schema가 없는 operation은7개이며 team/board의 일부 action도 남아 있다.

## 사용자 답·팀 결정 receipt — 2026-11-03

[결정 결과 계약](decision-contract.md)에 팀에 기록한 답과 팀 없이 받은 답의
structured receipt를 추가했다. 격리 stdio77개 검사와 frame95개, 예제4개·거부9개,
ID 변이1개와 wire 결함2종을 검증했다. Mac core909개는77.157초에 통과했다.
실제 사람/native UI 인증이 아니며 미정의 operation6개와 전체 계획이 남아 있다.

위 결정 receipt의 고정4747823도 Linux3.11에서88.957초,3.14에서113.547초로
core909개를 통과했다. 두 환경에서 새 wire77개/frame95개를 검증하고 VM 종료를
확인했다. 승인 계약37d7f3f의 Linux core908개는88.629초/116.479초이며 각
source의 수치를 구분한다. 원래 전체 계획은 미완이다.

## 범위 변경 결과 계약 — 2026-11-03

[범위 계약](scope-contract.md)에 link/join/reach snapshot과 실제 송신 정책 검사를
추가했다. Stdio41개/frame58개, 예제11개·거부12개, schema 변이1개·wire 결함3종을
검증했다. Mac core911개는78.509초에 통과했다. 결과 계약 미정의 operation은
3개이며 team/board의 남은 action과 전체 계획은 계속 미완이다.

## 문서 endorsement receipt — 2026-11-03

[문서 승인 결과 계약](endorsement-contract.md)에 생성 node와 원본 parent, 답 출처를
추가했다. Stdio25개/frame35개, 예제3개·거부7개, schema 변이1개·wire 결함2종을
검증했다. Mac core913개는77.295초에 통과했다. 미정의 operation2개와
team/board의 남은 action, 원래 전체 계획은 계속 미완이다.

## 승계 결과 계약 — 2026-11-03

[승계 결과 계약](handover-contract.md)에 내부 identity/home을 제외한 transfer와
수신 letter projection을 추가했다. Stdio28개/frame39개, 예제5개·거부9개와
wire 결함2종을 검증했다. 팀 lead·미독 편지·옛 주소로 보낸 새 DM의 claim/ACK를
실행했고 Mac core915개는77.509초에 통과했다. 마지막 owned 결과 계약과
team/board의 남은 action, 원래 전체 계획은 미완이다.

## Owned 공개 projection과 내부 기록 노출 복구 — 2026-11-03

[Owned 결과 계약](owned-contract.md)에 create/run/status의 내부 home/owner/lease
노출 재현과 공통 projection을 기록했다. 수정 전 재현2개 실패, 수정 후 관련12개
통과와 합성 runtime의 실제 stdio30개/frame31개, 예제8개·거부15개를 확인했다.
Mac core920개는78.582초에 통과했다. 22개 operation 이름 모두 domain schema가
생겼지만 team/board의 남은 action, 전체 오류·native/독립 구현 행렬은 미완이다.

## Team/board 전체 action과 owned process generation — 2026-11-03

[전체 action 계약](team-board-actions.md)에 catalog의 team9개+board7개 action을
연결했다. Stdio37개/frame42개, action 집합 일치, schema 변이2개·wire 결함4종을
검증했다. [Owned process generation](owned-process-generation.md)은 Linux 초기
3.11 실패를 보존하고 새 owned controller/child를 boot ID+start ticks로 결속했다.
Legacy 기록과 registry/classic 형식은 유지한다. 새6개를 포함한 Mac core928개는
84.435초에 통과했다. 초기 source489e7ac의 Linux는3.11 실패·3.14 통과이며,
최종 고정 source Linux 재실행 전까지 이 실패의 복구를 완료 판정하지 않는다.
성공 결과 구조가 추가된 것이며 전체 오류·native/독립 구현/원래 행렬은 미완이다.

고정20b7012의 Linux928개도3.11에서92.007초,3.14에서119.422초로 통과했다.
새 process generation6개와 실제 OpenClaw 복구를 포함했고 team/board 전체
action·owned projection의 새 stdio/schema와 VM 종료를 확인했다. 초기489e7ac의
3.11 실패는 보존했다. 표본별 성공/실패와 전체 계획 미완을 구분한다.

## 표준 오류와 unknown method 분류 — 2026-11-03

[오류 계약](error-contract.md)에9개 code와 효과/재시도/취소 경계를 정리했다.
Unknown method가 unknown session으로 분류되던 결함을 수정 전 실패로 재현하고
method allowlist를 bound lookup 전에 연결했다. Stdio27개/frame29개, 예제9개·
거부6개와 schema 변이1개를 확인했다. 실제 write 뒤 internal error에서도 정본
node1개가 남는 것을 확인했다. Mac core930개는86.030초, 별도 focused2개는
0.440초에 통과했다. 최신 전체931개와 Linux 고정 source 재실행은 구분한다.
전체 domain error payload/native/독립 구현/원래 행렬은 미완이다.

## Core serial critical path 분할 — 2026-11-03

[Core 분할](core-partition.md)은 Linux3.14의120초 초과를 보존하고 가장 큰
Python 목록을 두 격리 프로세스로 분할했다. 전체 module/test와120초 deadline을
유지한다. Exact inventory·비중첩·격리/reaping4개와 serial mutant 실패를 확인했다.
Mac931개 전체는50.353초에 통과했다. Linux는 고정 source 후속 실행 전까지
초기cf01df5의3.14 실패가 해결됐다고 판정하지 않는다. 전체 계획은 미완이다.
