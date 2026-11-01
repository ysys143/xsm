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
- 기존 MCP 처리부가 공통 operation 경계를 통과한다. CLI 전체 서비스 추출은 아직 미완이다.
- 일반 참여자 DM은 기존 정책과 정본 handoff 저장소를 사용한다.
  알려지지 않은 런타임을 Codex 전송으로 보내지 않는다.
- 수신 알림·네이티브 큐 보고·최종 소비 ACK 분리. FYI는 알림을 발생시키지 않는다.
- 사용자 답 결속/UI는 미구현이며 `-32004`로 거부한다. 임의 답을 승인으로 기록하지 않는다.
- Python 3.9+ 클라이언트, 실행 가능한 Node 모듈과 TypeScript 타입,
  전송 fixture 및 실제 서버 subprocess 검사.
- 실험 명세·요청 스키마·README 연결. 안정된 호환성 보장은 아직 아니다.

## 단계별 판정

| 단계 | 상태 | 남은 조건 |
|---|---|---|
| P0 계약·현황 | 부분 구현 | 전체 기능별 normative 스키마, 독립 구현 적합성, 안정판 API 감사 |
| P1 공통 서비스 | 부분 구현 | CLI 추출, 일반 원격 신원, 사용자 판단, 비동기 작업 수명 |
| P2 SDK·검사기 | 부분 구현 | Python↔Node 교차 참여자 시험, 독립 구현, 전체 오류/취소 계약 |
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
