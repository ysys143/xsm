# OpenClaw gateway·agent의 보드·문서·첨부 native 검증

상태: Mac21개 검사가 통과했다. Linux·실제 모델·사용자 UI와 전체 기능 행렬은
미완이다. 결정·endorsement의 실제 UI 검증은 이번 실행에 포함하지 않았다.

`probe-openclaw-collaboration.py`는 고정 OpenClaw2026.10.9/Node24.22.2의
실제 gateway·agent·Tool Hub와 설치 plugin을 실행한다. Operator controller는
제품 worker_rpc/native SDK로 세션을 만들고, 각 실제 agent run의 SID/revision과
idempotency key를 수락·완료 영수증에 대조한다. 모델 대신 loopback scripted
SSE provider를 사용한다. 임시 HOME/XSM_HOME/OpenClaw profile/git 저장소만
쓰고 실제 모델 호출0이다. Gateway token은 임시 private config에만 둔다.

다른 runtime과 `probe_native_collaboration_cases.py`의 같은 동작 검사를 공유한다.
실제 Tool Hub의 tool_call 결과 이름과 protocol details, 예상 native 오류를
확인하며 native 형식을 원시에 보존한다. 정상 설치 loader는 변경하지 않는다.
변이 loader는 실제 tool execute에 위임한 뒤 결과만 바꾸는 임시 proxy다.

## Native 검색의 배치 제한

최초 실행은 catalog assertion에서 실패해 기능 표본0개였다. 실제 검색 응답은
큰 input 요약의 후보를 생략하고 truncated=true로 표시했다. 고정 native source의
compactBatchCandidate는 필수 metadata가2000자를 넘으면 후보를 생략한다.
이를 도구 미등록으로 해석한 하네스가 잘못이었다. 제품 스키마·도구를 줄이지
않고 truncated 후보를 단일 검색으로 다시 확인했다. Batch13개 응답은 둘째
실행의 catalog 영수증13개(배치2개+단일11개)이며22개 native 이름을 모두 확인했다.
본문의13개는 검색 호출 수이며 batch 호출이13개였다는 뜻은 아니다.
원시 실패와 native source excerpt/hash를 보존했다.

ScriptedTools는 OpenClaw의 query/id+args와 Hermes의 queries/calls를 구분한다.
공유 변경 후 OpenCode21개/58HTTP와 Hermes21개/89HTTP의 정상 회귀도 통과했다.
Tool-call ID는 OpenClaw에서 변형되지 않는 영숫자를 사용했다.

## Mac 결과와 결함 검출

21개 검사/29 XSM 호출/7개 operation이 통과했다. 팀·보드 predecessor/filter·
문서6개 action/작성자/wip/limit/render/없는 노드, 바이너리 파일 송수신과
크기/SHA256/명시적 ACK/owner 거부를 포함한다. 예상 오류3개는 실제 Tool Hub의
status=error/tool=tool_call 및 no node/owner-mismatch 원인을 대조했다.

Catalog13개와 XSM discovery29개를 포함해 native receipt71개/HTTP113개다.
발급ID71개와 실제 native message ID71개의 고유성·일치를 독립 확인했다.
Gateway 정상 종료와 native 참여 종료를 확인했다. 합성 context262144,
HTTP200개/8MiB 요청 상한을 명시했다. 실제 모델 규격·API 과금 경로가 아니다.

| 변이 | 실패 검사 |
|---|---|
| board-parent | native board links observed predecessor |
| doc-candidate | native wip does not allocate or hide hypothesis |
| file-content | native binary attachment preserves bytes |

세 변이는 모두 exit1/gatewayStopped=true/nativeParticipationsEnded=true였다.
원시는 `deliverables/protocol-foundation/openclaw-native-collaboration/`의
first/second 및 변이 폴더다. Provider gzip·native RPC stdout/stderr·native
영수증, source7개 snapshot/SHA manifest와 audit.json을 보존했다.
제품 engine은 바꾸지 않았으며 test-only 추가로 전체 core가 다시 통과했다고
표시하지 않는다. UI·모델·다른 operation/action과 전체 행렬은 별도 증거가 필요하다.
