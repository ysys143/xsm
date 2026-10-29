# Reason 역공학과 xsm 반영 추적

> 시간 제한 없는 native 자동 분석과 원본 CLI 모듈 격리 실행·E2E 7종의 후속 근거를 반영했다. [후속 실행](followup-findings.md), [전체 자동 분석](full-native-analysis.json), [미완 실환경 경로](residual-unknowns.json).

- 조사일: 2026-10-24
- 상태: Proposed ADR 9개와 R01–R43의 근거·현재 코드·수용 검사 연결. 채택·제품 구현은 미결정.
- 질문: Reason의 전체 공개 엔진과 설치 CLI에서 배운 동작을 xsm의 기존 의도·기능과 어떻게 연결할 것인가?

[조사 보고서](../reason-network.md), [소스 지도](source-map.md), [배포 CLI 분석](cli-analysis.md), [기계 판독 추적](coverage.json), [검사 결과](test-results.json).

후속 사용자 지시로 [Ghidra 네이티브 분석](ghidra-native.md)을 추가했다. [설치·복구](ghidra-install.json), [native 근거](ghidra-native-evidence.json), [수집 검증](ghidra-validation.json)을 따로 보존한다. 초기 시간 초과·선택 함수 추출과 후속 두 대상의 전체 자동 분석 완료를 구분한다.

## ADR 묶음

| ADR | 제안 계약 | 요구 수 |
|---|---|---:|
| [0015](../../adr/0015-connection-intent-and-participation.md) | 연결 의도와 참여 범위를 실행 가능한 계약으로 잇는다 | 7 |
| [0016](../../adr/0016-agent-messaging-interface.md) | 에이전트의 요청과 응답을 일관된 도구 계약으로 제공한다 | 10 |
| [0017](../../adr/0017-directory-and-session-lifecycle.md) | 업무로 세션을 찾고 대화 신원을 유지한다 | 8 |
| [0018](../../adr/0018-delivery-evidence-and-recovery.md) | 전달 증거와 메시지 복구를 같은 수명 계약으로 관리한다 | 10 |
| [0019](../../adr/0019-message-context-attachments.md) | 메시지에 필요한 자료 사본을 명시적으로 전달한다 | 5 |
| [0020](../../adr/0020-human-decisions-and-attention.md) | 사람의 판단 원문을 보존하고 중복 질문과 알림을 조절한다 | 6 |
| [0021](../../adr/0021-cross-machine-network-and-membership.md) | 원격 연결의 편의와 머신 인증을 분리된 전송 계약으로 제공한다 | 7 |
| [0022](../../adr/0022-peer-authority-and-abuse-controls.md) | 동료 입력의 권위와 통신 오용을 분리해 제어한다 | 6 |
| [0023](../../adr/0023-runtime-adapters-and-operability.md) | 설치와 하네스 어댑터의 생명주기를 검증 가능하게 만든다 | 13 |

## 전체 발견과 대응

초기에 관찰한 협업 흐름, 추가 10개와 5개, 코드·배포물 분석에서 새로 확인한 점을 포함한다. 항목마다 사실·추론·미실행 범위를 명시했다. 기존 기능의 존재와 실제 경로의 성공은 별도 판단이다.

| ID | 발견·검토 대상 | 현재 근거 수준 | xsm 현황과 개선 쟁점 | ADR | 수용 검사 |
|---|---|---|---|---|---|
| R01 | 에이전트가 수행하는 설치·가입·초기 연결 | 기존 설치에 로그인·가입·훅 신뢰 사용자 개입이 있었다. 추가 인증 구현 12개 격리 관측으로 잠금·재개·거부·만료·요청 교체 경계를 확인. 실제 가입 재시험과 구분. | 설치·doctor가 이미 있다. clean 설치와 기존/새 세션의 첫 왕복을 분리해 개선한다. | [0023](../../adr/0023-runtime-adapters-and-operability.md) | A23-01, A23-02 |
| R02 | 연결 의도·사용자 출처·승인 수집과 복구 | xsm 실제 비동기 승인 수집 실패를 보존. 원본 인증 모듈 12개 격리 관측에서 잠금·재개·거부·만료를 구분했고, pending flow 교체 뒤 이전 결과 저장의 조건부 틈을 확인. | 승인 후 연결·재전송 경로가 이미 있으나 기존 표본의 승인 응답은 반영되지 않았다. | [0015](../../adr/0015-connection-intent-and-participation.md), [0020](../../adr/0020-human-decisions-and-attention.md) | A15-02, A15-03, A20-07 |
| R03 | 신원·자격·팀 가입·업무 권한의 구분 | 서명·계정 증명·멤버십 소스와 upstream 검사. 업무 권한과 별개. Ghidra에서 팀 밖 거부 문자열·403 전달의 native 후보 경로를 확인. | 로컬 uid와 원격 SSH 키·범위가 이미 구분된다. 네트워크 신원을 업무 승인으로 승격하지 않는다. | [0015](../../adr/0015-connection-intent-and-participation.md), [0021](../../adr/0021-cross-machine-network-and-membership.md) | A15-04, A21-02 |
| R04 | 새 저장소의 자연스러운 참여와 공유 범위 | 이전 S5에서 Reason 새 저장소 왕복 성공. 공개 E2E에서 합성 팀 가입·여러 폴더 참여를 확인. xsm 연결 후 구간은 여전히 미검증이며 새 시험으로 덮지 않음. | 기존 프로젝트/연결을 자동 제안한다. 기본 참여 단위와 신규 공유 범위를 논의한다. | [0015](../../adr/0015-connection-intent-and-participation.md) | A15-01, A15-02, A15-06 |
| R05 | 부모·자식 관계와 독립적인 동료 N:N 협업 | 양쪽 모두 동료 직접 검토·회신 성공. | N:N은 원래 의도이며 실제 작동한다. 부모·워커 예외를 전체 토폴로지로 정당화하지 않는다. | [0015](../../adr/0015-connection-intent-and-participation.md), [0022](../../adr/0022-peer-authority-and-abuse-controls.md) | A15-05, A22-04 |
| R06 | 업무·저장소·브랜치·사람·머신으로 상대 발견 | 기존 실제 목록과 소스에서 업무·branch·상태·수신 능력 표시 확인. | 이름·폴더·홈·ref로 발견한다. 업무 선택 정보의 차이를 보완한다. | [0017](../../adr/0017-directory-and-session-lifecycle.md) | A17-01 |
| R07 | 제목·계획·할 일에서 작업 상태 자동 추출 | 제목·계획·할 일 추출 소스·upstream 검사와 합성 훅 E2E를 대조. 의미 요약의 정확도·공개 범위 적절성 전수는 미검증. | 구조화된 doing 추출의 동등 경로는 미확인. 강제 수동 보고를 새로 요구하지 않는다. | [0017](../../adr/0017-directory-and-session-lifecycle.md) | A17-04 |
| R08 | 대화에 결속된 이름·충돌·재개·만료 | 격리 IPC의 이름 충돌·재시작 보존과 upstream 수명 검사. | 기존 ref는 resume에도 유지된다. 오프라인 이름 소유·대화/실행 세대 정책은 명시적 비교 대상. | [0017](../../adr/0017-directory-and-session-lifecycle.md) | A17-03, A17-06 |
| R09 | 홈·스레드·프로세스·공유 MCP의 호출자 결속 | 같은 Codex의 실제 실패/성공과 합성 공유 MCP의 호출자 식별을 대조. hooks 63·codex_busy 35 검사 추가. CODEX_HOME native 참조는 대상 홈 전달이나 단일 원인 입증이 아님. | 홈·스레드·프로세스를 이미 사용한다. 최신 이웃 대체 정책과 위험한 작업의 결속을 별도 검토한다. | [0017](../../adr/0017-directory-and-session-lifecycle.md), [0023](../../adr/0023-runtime-adapters-and-operability.md) | A17-02, A23-03 |
| R10 | 여러 머신의 사람·터미널·세션 주소 구분 | names의 의도한 0.12.6 시험체에서 36/36 통과. two_machines에서 사람·머신·터미널 주소를 대조. 한 물리 호스트의 논리 머신이며 물리 원격 실측과 구분. | 원격 이름@홈@호스트가 있다. 사람·머신·대화 정보를 표시와 인증에 어떻게 연결할지 제안한다. | [0017](../../adr/0017-directory-and-session-lifecycle.md), [0021](../../adr/0021-cross-machine-network-and-membership.md) | A17-01, A21-04 |
| R11 | 질문 한 호출로 실제 답을 회수하는 계약 | CLI 배포물 jr과 기존 실제 동기 질문 성공. 주소 대체 매칭의 한계도 기록. | wait는 영수증 대기다. 기존 의미를 보존하고 실제 답 회수 계층을 추가한다. | [0016](../../adr/0016-agent-messaging-interface.md) | A16-01, A16-07 |
| R12 | 비동기 작업·수신 안내·작업 중 개입 | 기존 실제 병렬 작업·수신 안내 및 훅 소스. | 비동기 송신·수신 안내가 이미 있다. Codex 작업 중 수신 경로의 일관성을 개선한다. | [0016](../../adr/0016-agent-messaging-interface.md), [0018](../../adr/0018-delivery-evidence-and-recovery.md) | A16-02, A16-05 |
| R13 | 깨우기와 FYI·우선순위 및 채널 게시의 구분 | 기존 FYI 무기상·후속 미독, 격리 wake=false 저장, MCP wake 인자 부재. | priority=later·채널 게시가 이미 있다. MCP priority 및 실제 소비·하네스별 보장을 대조한다. | [0016](../../adr/0016-agent-messaging-interface.md), [0018](../../adr/0018-delivery-evidence-and-recovery.md) | A16-03, A18-06 |
| R14 | 환경에 따라 필요 없는 도구를 감추기 | 실제 inbox가 있는 Claude에서만 check_inbox를 숨기는 소스. 합성 codex에는 4개 노출. | 전체 도구 목록을 제공한다. 환경별 최소 노출과 하향 시 복구를 함께 제안한다. | [0016](../../adr/0016-agent-messaging-interface.md) | A16-05 |
| R15 | 도구에 내장된 최소 지침과 단일 원문 | skill 원문을 MCP 초기 지침으로 읽는 소스·instructions 단위 검사. | 기존 스킬·설명·도구 지침을 단일 계약으로 맞출 대상. | [0016](../../adr/0016-agent-messaging-interface.md) | A16-03 |
| R16 | CLI/MCP 기능 일치와 전달 경로 자동 선택 | 같은 일반 Codex의 CLI 실패 뒤 MCP 복구와 양쪽 FYI/priority 스키마 차이를 보존. 합성 훅·작업 중 Codex E2E 성공이 실제 모든 프로필의 성공은 아님. | 가능한 경로 선택과 기능 차이를 에이전트가 기억하지 않게 한다. | [0016](../../adr/0016-agent-messaging-interface.md), [0023](../../adr/0023-runtime-adapters-and-operability.md) | A16-03, A16-04 |
| R17 | 저장·전달 중·수신·읽음·과제 결과의 증거 강도 | 실제 낙관적 Codex 문구와 실패를 보존. 공식 0.12.10·debug 0.12.11의 알림 장벽 관측 각 4개에서 OS 명령 완료 전 popped up 응답과 후속 실패를 확인. | 전달 영수증과 typed outcome이 이미 분리돼 있다. 모델 이해·독립 검증과 혼동하지 않는다. | [0018](../../adr/0018-delivery-evidence-and-recovery.md) | A18-01, A18-05, A18-07 |
| R18 | 대기 취소와 메시지 소비의 분리 | StopWaiting 합성 IPC·peek/Delivered와 대기 취소 소스를 대조. late-answer upstream 검사 통과. 실제 OS UI와 하네스 전체 취소 경쟁은 미검증. | 기존 수신·소비 경로를 대조해 대기 취소와 미독 보존 계약을 명시한다. | [0016](../../adr/0016-agent-messaging-interface.md), [0018](../../adr/0018-delivery-evidence-and-recovery.md) | A18-02, A16-07 |
| R19 | 재전송·중복 방지·재시작·확인 불명의 복구 | 격리 재시작 보존과 upstream ID 중복·재시도 검사. CLI SDK의 조회 재시도와 변경 요청 readback 분리도 정적 확인. | 동일 ID 재전송·본문 대조·unknown 조정이 이미 있다. 전체 본문 결속과 경로 일관성을 검증한다. | [0018](../../adr/0018-delivery-evidence-and-recovery.md) | A18-03, A18-04 |
| R20 | 오프라인 우편함·대상 수명·보존·만료 안내 | 오프라인 만료 안내 소스·단위 검사와 격리 미독 재시작. | 승인 전 outbox·보류·수신 저장이 있다. Reason 원격 outbox와 같은 이름의 다른 의미를 구별한다. | [0018](../../adr/0018-delivery-evidence-and-recovery.md), [0017](../../adr/0017-directory-and-session-lifecycle.md) | A18-04, A18-07, A17-06 |
| R21 | 메시지와 첨부 사본·맥락 묶음·공동 문서의 구분 | 기존 실제 첨부 검토와 합성 MCP의 A 파일 수신. | text-file은 본문 입력이다. 공동 문서 규약을 유지하며 첨부 사본 계약을 추가한다. | [0019](../../adr/0019-message-context-attachments.md) | A19-01, A19-06 |
| R22 | 상대 기능 협상과 구버전 첨부 대체 전달 | features 협상·본문 대체·미지원 명시 소스와 upstream 검사. | 원격 호환 경로가 있다. 첨부 지원 여부를 버전 추측 대신 능력으로 협상한다. | [0019](../../adr/0019-message-context-attachments.md) | A19-04 |
| R23 | 호출자별 첨부 루트·파일명·용량·보존 제한 | 합성 공유 MCP에서 B 호출자가 A 프로세스 자료 루트로 검사되어 거절됨을 재현. 실제 하네스의 MCP 공유 단위는 미검증. | 새 첨부를 도입할 때 호출자 식별과 자료 루트를 함께 결속해야 한다. | [0019](../../adr/0019-message-context-attachments.md) | A19-02, A19-03, A19-05 |
| R24 | 사용자가 본 원문·요청 ID·승인 증거의 결속 | 서명된 Approval 모든 필드·팀 결속 단위 검사와 표시 내용 소스. | 사용자 결정에 질문·답과 출처를 이미 기록한다. 여러 경로의 실제 표시·원 요청 결속을 통일한다. | [0020](../../adr/0020-human-decisions-and-attention.md), [0022](../../adr/0022-peer-authority-and-abuse-controls.md) | A20-01, A20-05, A22-02 |
| R25 | 늦은 답·미응답·거부·취소의 구분과 후속 전달 | upstream late-answer 검사가 통과했고 인증 구현 격리 실행에서 거부·만료·중단·다른 clientId를 구분. pending 교체 조건의 이전 결과 저장을 관측. 실제 OS UI 경쟁·다중 CLI 도달성은 미검증. | MCP 자동 거절·사용자 거절 차이를 이미 다룬다. 비동기 응답 채널 누락을 함께 복구한다. | [0020](../../adr/0020-human-decisions-and-attention.md) | A20-03, A20-04 |
| R26 | 중복 질문 합치기와 진행 중 질문 재대기 | 같은 popup 내용의 waiting 합류 호출 경로를 검토. 공개 검사에서 late answer·표시 실패·표시 범위를 대조했으나 실제 GUI 중복 호출·포커스 경쟁은 미검증. | 보관 요청 중복 제거가 있다. 승인창·결정의 중복 합치기는 별도 계약으로 대조한다. | [0020](../../adr/0020-human-decisions-and-attention.md) | A20-02 |
| R27 | 사람 알림·에이전트 깨우기·포커스·빈도 조절 | 알림 장벽·실패 관측 각 4개를 두 엔진에서 확인. E2E 알림 로그 검사 1건은 두 번 실패했고 나중에 기대 내용이 기록됨. 실제 사용자 알림은 실행하지 않음. | 사용자 질문/워커 알림이 있다. 메시지 수신과 사람의 주의 요청을 분리해 대조한다. | [0020](../../adr/0020-human-decisions-and-attention.md) | A20-06 |
| R28 | 동료 입력·사용자 권위·예약 표시 위조의 분리 | 격리 가짜 승인 프레임과 upstream 렌더링 변형 검사. | 봉투·중첩·출처 문맥이 이미 있다. 본문·목록·오류의 동일한 권위 경계를 검증한다. | [0022](../../adr/0022-peer-authority-and-abuse-controls.md) | A22-01, A22-02 |
| R29 | 루프·속도·그룹 제어와 일반 직접 협업의 분리 | 격리 agent 그룹 거절과 쌍별 12건 후 거절을 확인. 별도 워커 풀에서 6명 busy 뒤 새 발신자의 즉시 회수 결함을 원본 모듈로 관측. 정상 N:N 협업의 한도 적절성은 미검증. | 직접 통신·일부 반복 제어가 있다. 부모 관계 제한과 오용 탐지를 구별하고 정상 왕복을 보존한다. | [0022](../../adr/0022-peer-authority-and-abuse-controls.md) | A22-03, A22-04 |
| R30 | VPN 없는 P2P·NAT·릴레이와 선택적 원격 연결 | 공개 E2E 7종에서 논리 머신의 실제 iroh 연결·릴레이 목록·오프라인·재접속을 대조. 한 호스트의 합성 하네스이며 서로 다른 NAT·물리 원격 실측은 미검증. | 양방향 SSH가 기존 계약이다. 선택적 백엔드와 로컬 비의존 유지의 비용을 제안한다. | [0021](../../adr/0021-cross-machine-network-and-membership.md) | A21-01, A21-03, A21-05 |
| R31 | 초대·키·가입·제명·계정 증명·이름 소유 | 가입·제명·초대·증명·이름 소유 소스와 서명/병합 단위 검사. CLI 가입 결과·기존 소속·팀 전환 복귀 경계를 정적 확인. linker 경계 복구로 팀 밖 거부 메시지·코드·길이를 전달하는 native 호출 확인. | 키·호스트 인증과 명시적 pairing이 있다. 계정·팀·업무 권한을 별도로 비교한다. | [0021](../../adr/0021-cross-machine-network-and-membership.md) | A21-02 |
| R32 | 메타데이터 노출·수신 정책·호스팅 MCP 신뢰 경계 | 공개 presence 필드·공유 기본값·cloud relay 경계. 원격 MCP 서버 내부 미확보. 설치 CLI의 hosted relay가 서버 작업을 로컬 세션으로 전달하는 경계를 정적 확인. | 로컬 scopes와 원격 pairing이 있다. 공유 대상과 hosted 경로의 신뢰를 명시한다. | [0015](../../adr/0015-connection-intent-and-participation.md), [0021](../../adr/0021-cross-machine-network-and-membership.md) | A21-06, A15-06 |
| R33 | 하네스 어댑터·설정 백업·제거·훅 신뢰·서명 유지 | 설정 병합·백업·권한·소유 경로와 macOS 서명 stand-in 검사. CLI의 엔진 pin·설치 영수증·더 최신 standalone 유지 경로도 정적 확인. PostToolUse를 참조하는 native 함수 두 곳을 linker 경계로 복구. | 설치 소유 항목과 프로필 지원이 이미 있다. 실제 행렬과 rollback을 검증한다. | [0023](../../adr/0023-runtime-adapters-and-operability.md) | A23-01, A23-02, A23-05 |
| R34 | 자동 등록·헬스체크·데몬 재접속·옵션 경계 | Link 재접속·등록 복원과 MCP 등록 지연 소스. 격리 데몬 재시작. CLI의 비동기 가입 완료·재연결·변경 상태 readback을 추가 대조. | 필수 데몬 없는 로컬 경로를 유지하며 장기 MCP 수명과 실제 능력 하향을 다룬다. | [0018](../../adr/0018-delivery-evidence-and-recovery.md), [0023](../../adr/0023-runtime-adapters-and-operability.md) | A23-04, A18-04 |
| R35 | doctor·상태 하향·관측·실제 도달 검증 | 실제 상태·낙관적 문구·알림 후속 실패와 Ghidra 설치/실제 기능의 차이를 대조. 시간 제한 없는 두 native 분석·전체 목록·저장 완료. 성공 단계별 근거를 분리. | doctor·원장·OTLP가 있다. 설정 존재와 실제 도달을 구분하고 본문 비저장 결정을 존중한다. | [0023](../../adr/0023-runtime-adapters-and-operability.md), [0018](../../adr/0018-delivery-evidence-and-recovery.md) | A23-04, A23-07, A18-01 |
| R36 | 비공개 CLI serve의 수명·문맥·워커 소유 경계 | CLI 배포물의 Claude strict MCP·Codex 새 exec와 이전 serve 실제 transcript. | 소유 워커의 app-server·승인 전달이 있다. 일반 세션과 serve를 같은 수명으로 취급하지 않는다. | [0016](../../adr/0016-agent-messaging-interface.md), [0023](../../adr/0023-runtime-adapters-and-operability.md) | A16-06, A23-06 |
| R37 | 공개 범위·라이선스·출처·업데이트 공급 경로 | 공개 라이선스·바이너리 SHA·CLI 추출 구간·업데이트 소유자를 고정. Ghidra에서 CLI 여섯 JS 영역의 메모리 SHA와 바이너리 SHA를 대조. | 출처와 배포 소유를 남긴다. 공개 엔진 라이선스를 비공개 CLI에 자동 적용하지 않는다. | [0023](../../adr/0023-runtime-adapters-and-operability.md) | A23-05 |
| R38 | 실패·반대 증거·기존 사용자 결정·비교 한계 유지 | 양쪽 성공·실패·기존 결정·버전 차이를 유지. 초기 600초 시간 초과와 후속 무제한 분석 완료를 구분. E2E 최초 306/4와 시험체 정정 후 309/1도 보존. | 부모 전용 철학·Reason 전반 우월·xsm 기능 부재로 일반화하지 않는다. | [0015](../../adr/0015-connection-intent-and-participation.md), [0016](../../adr/0016-agent-messaging-interface.md), [0017](../../adr/0017-directory-and-session-lifecycle.md), [0018](../../adr/0018-delivery-evidence-and-recovery.md), [0019](../../adr/0019-message-context-attachments.md), [0020](../../adr/0020-human-decisions-and-attention.md), [0021](../../adr/0021-cross-machine-network-and-membership.md), [0022](../../adr/0022-peer-authority-and-abuse-controls.md), [0023](../../adr/0023-runtime-adapters-and-operability.md) | A15-02, A18-05, A21-04, A22-05 |
| R39 | 발신자별 warm 문맥 재사용·직렬화·병렬화·유휴 회수 | 원본 ask-worker의 격리 실행 15개 관측: 발신자별 재사용·직렬/병렬·임시 주소 정규화와 Codex 요청별 새 exec 확인. 6명 busy 때 일곱 번째 새 워커 즉시 회수 조건도 재현. | 세션/워커 재사용이 이미 있다. 발신자별 문맥 공유와 독립 검토 격리의 차이를 명시한다. | [0016](../../adr/0016-agent-messaging-interface.md), [0023](../../adr/0023-runtime-adapters-and-operability.md) | A16-08, A23-06 |
| R40 | 업무 수신 저널·답 보관·회신 실패와 과제 재실행 분리 | 원본 모듈과 실제 파일·별도 프로세스 종료/재시작으로 요청 선보관·답 재사용·회신 실패 후 재송신을 확인. 부작용 후 답 저장 전 중단에서는 재실행에 따른 부작용 중복을 관측. | 보관 요청·원장·워커 pump가 있다. 업무 수신 ack와 결과 복구의 전체 장애 경로는 별도 검증 대상. | [0018](../../adr/0018-delivery-evidence-and-recovery.md), [0023](../../adr/0023-runtime-adapters-and-operability.md) | A18-08 |
| R41 | 기존 실행 세션을 유지하는 설정·상태 마이그레이션 | mixed_versions는 0.10.8과 23/23, names는 의도한 0.12.6과 36/36. 이전 경로·소켓 이동 소스와 CLI 설치 소유자를 대조. 전체 이전 버전·실제 사용자 프로필 롤백 행렬은 미검증. | 런타임 설치·호환 기능이 있다. 기존 세션 유지와 실제 롤백 경로를 전수 검사한다. | [0023](../../adr/0023-runtime-adapters-and-operability.md) | A23-08 |
| R42 | 고정 UDP 포트·대체 포트·실제 네트워크 경로 진단 | 0.12.11 upstream에서 실제 UDP bind·점유 포트 fallback·IPv6 조건의 검사도 통과. 설정 파싱만의 검사는 아님. 물리 NAT·라우터/방화벽 포트 운용은 미검증. | SSH 원격 경로에는 다른 진단이 필요하다. 선택한 백엔드의 실제 경로를 보여 준다. | [0021](../../adr/0021-cross-machine-network-and-membership.md), [0023](../../adr/0023-runtime-adapters-and-operability.md) | A21-07, A23-04 |
| R43 | 심볼릭 링크·다중 작업 폴더·정책 손상의 일관된 경계 | 0.12.11의 링크/미생성 경로 제외 검사와 설정 오류 시 기본값 대체 소스. | realpath·폴더 범위·설정 로더가 있다. 경계 일관성과 손상 때 조용한 권한 확대를 검사한다. | [0015](../../adr/0015-connection-intent-and-participation.md), [0017](../../adr/0017-directory-and-session-lifecycle.md), [0019](../../adr/0019-message-context-attachments.md), [0022](../../adr/0022-peer-authority-and-abuse-controls.md) | A17-05, A19-03, A22-06 |

## 대화에서 열거한 추가 15개의 대응

| 원래 항목 | 발견 | 추적 ID |
|---|---|---|
| 추가 10개·1 | 불필요한 도구 숨김 | R14 |
| 추가 10개·2 | 도구와 함께 사용하는 지침 | R15 |
| 추가 10개·3 | 작업 상태 자동 추출 | R07 |
| 추가 10개·4 | 상대 수신 능력 표시 | R06, R17 |
| 추가 10개·5 | 요청과 자료 사본 전달 | R21 |
| 추가 10개·6 | 대화에 이름 결속 | R08 |
| 추가 10개·7 | 대기 취소와 소비 분리 | R18 |
| 추가 10개·8 | 오프라인 재시도·만료 | R19, R20 |
| 추가 10개·9 | 상대 기능 협상 | R22 |
| 추가 10개·10 | 실제 반복을 근거로 제어 | R29 |
| 추가 5개·1 | 실제로 보여 준 요청과 승인 연결 | R24 |
| 추가 5개·2 | 늦은 사용자 답 회수 | R25 |
| 추가 5개·3 | 중복 질문 합치기 | R26 |
| 추가 5개·4 | 사람 알림과 에이전트 깨우기 분리 | R27 |
| 추가 5개·5 | 본문의 승인 표시 위조 방지 | R28 |

## 기존 결정과 연결

0004의 쉬운 연결·의사 표현, 0013의 비차단·사람에게 명령 입력을 요구하지 않는 결정, 0003의 로컬 핵심 경로 비의존, 0007의 SSH, 0008의 네이티브 이름, 0005·0006의 채널·공동 문서, 0010의 워커, 0011의 관측을 각 ADR에서 대조했다. 기존 Accepted 본문과 상태는 수정하지 않았다.

제안의 승인 범위·수명·보존·공유 기본값은 미결정이다. 확정되지 않은 값을 구현 기본값처럼 적지 않았다. 토론 기록의 Round 0은 이번 코디네이터 작성이며 독립 검토나 사용자 동의를 대신하지 않는다.

## 검증 범위

[validation.json](validation.json)은 문서 구조·전체 요구 연결·링크·출처·원본 불변을 확인한다. 각 A15–A23 수용 검사는 제안한 제품 변경 이후 실행할 조건이며 지금 구현됐다고 표시하지 않는다. 원격 물리 머신·실제 OS 질문 경쟁·실제 모델 포함 CLI 통합 장애 시험 등 남은 실행 조건은 보고서와 해당 ADR에 기록했다.

재검사 실행기는 [verify_research.py](verify_research.py)다. 고정 소스 두 개와 사설 native 증거 경로를 지정한다. 누락된 요구·Accepted로 잘못 바꾼 상태·깨진 링크를 변이 입력으로 넣어 실제로 거부하는지도 검사한다.

```sh
python3 docs/references/reason-network/verify_research.py --current-source /path/to/reason-v0.12.11 --baseline-source /path/to/reason-v0.12.10 --native-root /path/to/native-evidence --output docs/references/reason-network/validation.json
```
