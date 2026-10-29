# 미완 52조건 실행 가능성 frontier

**전체가 blocked라는 근거는 없다.** D12와 독립적인 local 검증 후보10개와 읽기 전용 재결속 후보8개가 남는다. 이 문서는 실행 허가/동결 해제가 아니다. 조사10분 제한은 초과했으며, 추가 조사를 중단하고 확인한 근거만 정리했다.

## 현재 기준과 계수

원70조건은 proven18/partial49/missing3이며 미완52다. ledger 전체18/78/3은 residual20·journey9를 포함한99행이다. 두Python1700/OK 원로그SHA와 current primary135/frozen 일치를 확인했다. G10은 localpassed다. 옛 closure-map의1697/14proven을 현재 수치로 잘못 쓰지 않았다.

| 분류 | 수 | IDs |
|---|---:|---|
| 1. D12/P12 의존 | 16 | A17-01, A17-03, A21-02, A21-04, A21-05, A21-06, A21-07, A23-04, A24-01, A24-02, A24-03, A24-04, A24-05, A24-06, A24-07, A24-08 |
| 2. 실제 사람 UI·새 인증/신뢰 필요 | 13 | A15-02, A15-04, A15-06, A17-06, A19-05, A20-01, A20-02, A20-03, A20-04, A20-05, A20-06, A20-07, A23-01 |
| 3. 현재 runtime 미제공 기능·미확보 물리 환경 | 5 | A17-02, A19-02, A21-01, A21-03, A23-03 |
| 4. 사용자 입력 없이 가능한 구체 local 구현/검증 | 10 | A17-05, A15-03, A16-01, A16-03, A18-04, A19-01, A19-03, A22-01, A22-05, A23-06 |
| 5. 기존 근거 재결속 가능 후보 | 8 | A16-07, A18-01, A18-02, A19-04, A22-02, A22-04, A23-05, A23-08 |

중복 없는 primary52개다. formal G07/G12 의존은 secondary로 별도 보존했다. 5번은 기존 근거 감사 후보이며 전부 자동승격한다는 판정이 아니다.

## 4번: 핵심 사용자 흐름 순, 다음 한 실행

현재 제품결함을 단정한 목록이 아니라 구체적인 미관측 local 검증 목록이다. 필요한 부분만 보완하며 모든 native/하네스 재실행을 추가하지 않는다.

### 1. A17-05 — 발견→제외 자료

- 다음 한 실행: 선택한 실제 local caller의 disposable excluded/symlink 경로 한 개를 registry.upsert→directory.discover→CLI files.prepare_cli까지 한 trace로 검증한다.
- 완료 기준: 동일 realpath에서 등록/목록 제외와 CLI 반출 거절, copy/원본변경0. MCP inline에 없는 원경로 검증을 가정하지 않는다.
- 실제 현재 막는 이유: 기존 fixture 정책은 성공. native CLI 원경로 시도0이며 shared server는 이 criterion의 전제가 아니다.

### 2. A15-03 — 연결→수집 단절

- 다음 한 실행: own pending 한 요청의 collector 수집을 끊는 경계를 consent.take_or_request의 기존 unknown/회수 경로로 캡처한다. 허용은 만들지 않는다.
- 완료 기준: unknown·원문/복구 위치 보존·같은 요청 회수. 수집 부재를 허용으로 승격하지 않는다.
- 실제 현재 막는 이유: native 단절→unknown→같은 요청 회수 trace가 없음. 실제 새 affirmative 응답이 필요한 A15-02 성공 경로와 구분한다.

### 3. A16-01 — 질문→답 회수

- 다음 한 실행: 한 실제 local 질문 Q의 같은 owner에서 CLI question-status와 MCP xsm_question_status readback을 비교한다.
- 완료 기준: 원 ID/reply_to/본문 SHA/outcome 일치, 기존 receipt-only 음성 결속, 추가송신0.
- 실제 현재 막는 이유: 각 CLI/MCP 실제 답은 있지만 같은 입력/원요청의 비교가 미결속. D12/새 계정 선택은 필요 없다.

### 4. A16-03 — 옵션→동일 의미

- 다음 한 실행: priority/wake/attachments/reply_to/outcome 5축 공통표를 실제 CLI parser/MCP schema→service→adapter 효과 capture로 완성한다.
- 완료 기준: 5축의 지원/명시미지원/실제 효과와 selector가 모두 대응. 기존 native 효과 재사용, owned 등 원문 밖 필수 축 추가 금지.
- 실제 현재 막는 이유: 부분 fixture/native는 존재. 같은 기능표의 양 인터페이스 대조가 미완이며 모든 하네스 재실행은 요구하지 않는다.

### 5. A18-04 — 단절→동일 ID readback

- 다음 한 실행: own local service 변경 요청 하나의 응답 직전/직후 client 연결 단절을 한 쌍으로 검증한다. 조회만 자동 retry한다.
- 완료 기준: 원 ID/대화 유지, mutation 추가실행0, 실제 상태 readback. local 완료와 공식 G12 종결은 분리한다.
- 실제 현재 막는 이유: local kill/복구 근거는 있음. 직전/직후와 조회 retry/readback 짝이 미결속. 원격 통합 G12는 D12/P12 대기지만 local 셀 전체가 막힌 것은 아니다.

### 6. A19-01 — 자료→사본

- 다음 한 실행: 같은 synthetic 본문/파일 bytes의 실제 CLI 원경로 송신과 caller-inline MCP 송신을 한 쌍으로 결속한다.
- 완료 기준: 본문·원문/수신 copy SHA와 receiver readback 일치. 기존 MCP 양성은 재사용하고 필요한 CLI 짝만 보완한다.
- 실제 현재 막는 이유: material 표본 CLI_attempts=0. CLI 불가/거부가 실측된 것은 아니고 MCP 실제 읽기는 성공했다.

### 7. A19-03 — 자료 권한→양성/음성

- 다음 한 실행: 기존 MCP hidden/outside 양성과 OS mode000 음성을 재사용하고 disposable 명시제외/민감이름 원경로 두 건을 실제 CLI API에 제출하는 음성 묶음을 보완한다.
- 완료 기준: 실제 거절·copy/body 반출0·원본보존. symlink/Unicode는 기존 fixture 결속, inline 서버의 원경로 권한 보장 발명 금지.
- 실제 현재 막는 이유: 기존 제외 음성은 모델 미반출 선택으로 API 집행이 아니다. 실제 CLI 시도0이며 MCP에 provenance path가 없다.

### 8. A22-01 — 수신→출처 표시

- 다음 한 실행: own native 수신 한 표본에 body/name/repo·branch/error의 합성 승인·프레임종료·ANSI·bidi·유사문자 corpus를 넣어 표시와 원문 digest를 대조한다.
- 완료 기준: 출처 프레임 불변·가짜승인 무효·digest 보존. 사람 창 적절성/G07은 별도로 유지한다.
- 실제 현재 막는 이유: renderer/codec fixture는 성공. 실제 수신 경계의 표면 대조가 미결속이며 새 권한 정책 결정은 아니다.

### 9. A22-05 — 정책→수신 호환

- 다음 한 실행: 같은 disposable local receiver에서 native 메시지와 xsm 봉투의 명시 deny/주석 한 묶음만 비교한다. 기존 허용 trace는 재사용한다.
- 완료 기준: 기존 허용/차단/주석 의미와 원문 보존. 모든 하네스 재실행을 추가하지 않는다.
- 실제 현재 막는 이유: 정상 native/봉투와 통합 fixture는 있음. 실제 음성 두 경로 비교만 미결속이다.

### 10. A23-06 — 위임→기본 owned 후속

- 다음 한 실행: 이미 인증·설치된 local 기본 설정의 공개 CLI cmd_owned create/run 후속 한 표본에서 실제 wiring/reply/native ID/기억·권한을 캡처한다. eval MCP/quiet callback 주입은 하지 않는다.
- 완료 기준: 기본 경로의 실제 reply·후속 기억·추가 권한0 확인. 기존 공개 MCP/executor 성공을 보존하고 serve 철자 부재를 결함이라 하지 않는다.
- 실제 현재 막는 이유: 공개 MCP 기본 child executor/reply/기억은 있음. 설치 default wiring와 shell 표본만 부족하며 clean 인증을 새로 요구할 이유는 없다.

## 5번: 기존 근거로 독립 재결속 가능한 후보

- **A16-07**: stdio timeout/cancel/부분·final 경쟁 fixture/process와 실제 late reply를 원 수준대로 결속. native 모든 조합/UI취소 notification을 새 필수로 추가하지 않는다. G07 공식 gate는 유지.
- **A18-01**: 기존 queue/socket 실패 fixture/process와 실제 typed native fallback·수신 evidence를 현재 SHA로 재대조. 전체 하네스 실패 행렬은 새 요구가 아니다.
- **A18-02**: 이미 proven인 fixture/process 취소와 factory native client종료/동일CID 회수/ACK후빈inbox를 결속. native cancel=0 한계는 남기되 세부 전부를 native로 반복해야 한다는 가산은 하지 않는다.
- **A19-04**: legacy/기능미광고/본문한도 거절 fixture와 old-MCP·첨부 native의 역할을 대조. 원격 구버전 협상 전수를 원문 밖 필수로 만들지 않으며 공식G12는 별도.
- **A22-02**: 원 evidence는 fixture+review. 승인 원천/타요청 재사용 거절·실제 채널 replay_blocked·same-uid 비보장 문구를 독립 검토로 결속. native 전수는 필수 아님. G07 gate 별도.
- **A22-04**: 일반 N:N·실제 형제 subagent direct calls/사본 owner·다른 부모/연결repo trace를 기존 raw로 토폴로지별 대조. 특정 쌍이 없으면 그 쌍만 남기고 기존 성공은 유지.
- **A23-05**: checksum/team mismatch·copy/CAS 실패·old reader/설정 보존 fixture/process를 review로 결속. 실제 xsm 서명/모든 공급물 검증을 새 요구로 만들지 않음. P12 공급/G12는 별도.
- **A23-08**: 실제 old native/MCP 동일세대 upgrade·두 reply와 local update-failure/old-reader 보존을 수준별 결속. 전체 구native/socket 마이그레이션 행렬은 원문 요구가 아니다.

원문 clause/level과 raw/현재dependency hash를 대조하는 감사다. 실제 특정 쌍/음성이 없으면 그 셀만 남기고 기존 성공 전체를 취소하지 않는다. G07/G12 공식 gate는 이 감사만으로 면제하지 않는다.

## 1·2·3번: 실제 외부 경계

### 1. D12/P12 의존

- **A17-01**: 로컬 multi-home/native 후보 성공 유지. required physical과 원격 후보는 P12 discovery 미구현.
- **A17-03**: local 수명 fixture/native 성공 유지. 다른 머신 동명은 P12 원격식별 필요.
- **A21-02**: 선택 backend의 계정/팀·제명·초대·가입 전환 의미는 D12 미정.
- **A21-04**: 두 머신 carrier native 답은 있음. 제품 peer 발견/승인/후속은 P12 미구현.
- **A21-05**: local 질문/carrier 정리 성공 유지. 선택 remote/relay 중단·제품 소유 제거는 P12 후.
- **A21-06**: local 공개/제외 성공 유지. network 가입 전후 실제 공개집합/비공개 서비스는 P12 필요.
- **A21-07**: 실제 UDP bind/fallback·IPv6/주소변화는 선택 engine 계약과 환경 필요. TCP 표본 대체 금지.
- **A23-04**: local CAS/flow/finisher/old API 성공 유지. 선택 backend 로그인/가입 경쟁은 D12/P12와 실제 UI 필요.
- **A24-01**: 원격 discovery→선택→handshake/후속·수명의 해당 제품 P12 consumer 미착수. 기존 local/fixture/carrier 성공은 보존하며 원격 전체로 승격하지 않음.
- **A24-02**: 원격 discovery→선택→handshake/후속·수명의 해당 제품 P12 consumer 미착수. 기존 local/fixture/carrier 성공은 보존하며 원격 전체로 승격하지 않음.
- **A24-03**: 원격 discovery→선택→handshake/후속·수명의 해당 제품 P12 consumer 미착수. 기존 local/fixture/carrier 성공은 보존하며 원격 전체로 승격하지 않음.
- **A24-04**: 원격 discovery→선택→handshake/후속·수명의 해당 제품 P12 consumer 미착수. 기존 local/fixture/carrier 성공은 보존하며 원격 전체로 승격하지 않음.
- **A24-05**: 원격 discovery→선택→handshake/후속·수명의 해당 제품 P12 consumer 미착수. 기존 local/fixture/carrier 성공은 보존하며 원격 전체로 승격하지 않음.
- **A24-06**: 원격 discovery→선택→handshake/후속·수명의 해당 제품 P12 consumer 미착수. 기존 local/fixture/carrier 성공은 보존하며 원격 전체로 승격하지 않음.
- **A24-07**: 원격 discovery→선택→handshake/후속·수명의 해당 제품 P12 consumer 미착수. 기존 local/fixture/carrier 성공은 보존하며 원격 전체로 승격하지 않음.
- **A24-08**: 원격 discovery→선택→handshake/후속·수명의 해당 제품 P12 consumer 미착수. 기존 local/fixture/carrier 성공은 보존하며 원격 전체로 승격하지 않음.

### 2. 실제 사람 UI·새 인증/신뢰 필요

- **A15-02**: hardening 후 같은 실제 사용자 승인 채널 원문→적용→연결→원 ID 전송. 기존 승인 성공은 보존하나 새 실제 응답이 필요한 부분을 자동 승격하지 않음.
- **A15-04**: 거부/취소/추가질문·늦은 답/철회 실제 사람 표본과 G07 미충족.
- **A15-06**: 실제 승인된 업무/세대 범위와 철회/resume 원천 필요. 임의 consent 생성 금지.
- **A17-06**: 새CID 미독 비상속/원CID resume 실제 성공은 있음. 해당 fixture에 승인 exact pair가 없어 권한 비상속에는 실제 affirmative 원천이 필요.
- **A19-05**: fixture/process는 이미 재결속됨. 원 plan closure G07 미통과가 남음. native 전수를 추가할 조건이 아님.
- **A20-01**: UI intent prepared-not-displayed. 실제 원문/잘림 표시와 사람 대조 없음.
- **A20-02**: 중복 억제 fixture 성공. 실제 승인창1/적용1 UI 관측 부족.
- **A20-03**: process 경합 fixture 성공. 실제 UI 늦은 답/취소 후 답/철회 경쟁 부족.
- **A20-04**: 실제 거부/닫힘/자동거절/desktop 부재 구분 UI 표본 없음.
- **A20-05**: 가짜태그/타요청 fixture 성공. 실제 승인 원천 재사용 음성과 G07 결속 필요.
- **A20-06**: OS exit0/장벽 fixture는 있음. human_saw/display_range=null, 표시/억제 사람 대조 없음.
- **A20-07**: 동일 실제 승인 수집 채널의 hardening 후 S5 전체 복구는 표식 응답만으로 대체 불가.
- **A23-01**: 실제 CLI등록6셀/설치제거/old·new-prefix reply 성공. 해당 clean 프로필의 정상 인증·필요 trust·첫 모델왕복 미실행. 기존 profile 성공은 유지.

### 3. 현재 runtime 미제공 기능·미확보 물리 환경

- **A17-02**: factory runtime이 thread별 다른 MCP PID를 생성. 한 server의 실제 A/B 호출을 제공하지 않음. 분리 server 귀속 성공은 유지.
- **A19-02**: 실제 분리서버 파일 owner 성공은 있음. 단일 MCP process의 두 caller 루트 격리는 제공되지 않음.
- **A21-01**: 기본 native15/cached5와 C UDP/noSSH/CONNECT 부분 성공 유지. 다른NAT/기업proxy/자가relay/신규설치무SSH 환경 미확보.
- **A21-03**: A/B/C/D 기본 비교/G11 검토 있음. SSH불가 신규설치·미확보 환경의 설치/개입비용이 부족. D12 응답이 비교 자체 선행은 아님.
- **A23-03**: 같은 native daemon 아래 MCP3개/server당 CID1종. 실제 shared 및 그 전제하 다른home 동일ID/상속env 미확보.

## 증거를 지우지 않기 위한 경계

- shared native 표본은 실제 MCP가 thread별 다른 PID였다. 분리 server 정상귀속/사본 읽기는 성공이며, 이를 한 server A/B로 바꾸거나 제품 결함이라 하지 않는다.
- material 표본은 MCP normal/hidden/outside 양성·receiver3 reads·mode000 errno13 성공이다. 제외 음성은 모델 미반출 선택이었고 CLI_attempts=0이다. CLI 불가/실패를 관측했다고 하지 않으며 inline의 원경로 검증도 발명하지 않는다.
- session-lifetime의 새CID 미독 비상속·원CID resume reply는 성공이다. 실제 승인pair가 없었던 한계를 권한 음성 성공으로 바꾸지 않는다.
- 공개 owned MCP/기본 child executor/reply/후속 기억은 성공이다. 설치 default wiring/shell 경로 공백과 serve 철자 부재는 다른 문제다.
- carrier15/cached5·C UDP/noSSH/proxy 성공은 유지하지만 선택 제품 P12 전체와 미확보 물리환경을 대체하지 않는다.
- A18-02 등은 fixture/process와 실제 native 회수/ACK를 수준별로 먼저 결속한다. 모든 세부의 native 반복이나 장시간부하는 원문 없이 더하지 않는다.

## 전체 goal blocked 판단

일괄 blocked는 지지하지 않는다. D12는 remote product 구현/종결의 실제 경계지만 독립 local검증10개와 읽기 전용 감사8개까지 막지 않는다. 특히 5번은 새 모델도 필요 없다. 전체 종결에는 D12/P12·실제 사람UI/정상clean인증·필요trust·현재미제공 shared runtime/물리환경이 필요하다. 실행은 별도 지시와 source 동결 경계를 따른다.

[JSON](remaining-execution-frontier.json)에52개 원criterion 전문·현재level별 evidence/ref·기록된gap과분류근거·formal gate·source/test경로·원자료SHA를 수록했다. source/plan/ledger/기존closure-map·doctorv3 partial/unknown은 변경하지 않았다. 새모델·실험·네트워크·시험 실행은0이다.
