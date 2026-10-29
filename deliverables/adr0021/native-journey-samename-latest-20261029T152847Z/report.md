최신 최종 동결본의 실제 두 Mac handshake는 완료됐습니다. 새 모델은 Claude와 Codex 각 1개만 실행했고, 동명 self/remote a1 발견과 원격 선택 후 원 요청 `79db1ad77556442d`, 직접 회신 `25fb2f0e30aa4709`, 실제 MCP ACK 2건과 양쪽 canonical acknowledged를 확인했습니다.

추가 요청된 A21-03 공통 수학 과제는 2건 중 0건 실행으로 미완입니다. 추가 지시를 처음 확인한 시각은 2026-10-29 15:33:57 UTC이며, 두 actor와 최초 서비스 정리는 2026-10-29T15:31:42.418705+00:00에 이미 끝났습니다. Claude는 no-session-persistence로 종료돼 같은 실제 CID의 대화를 이어 갈 수 없습니다. 새 모델쌍 생성, old CID 재지정, 원문 중계, 기존 질문 복제는 하지 않았습니다. 이 보고서는 수학 검토 성공이나 A21-03 전체 완료를 주장하지 않습니다. [완료 범위](completion.json)를 별도로 기록했습니다.

| 항목 | 결과 | 근거 |
|---|---|---|
| 최종 동결 입력 결속 | Python 53개와 hooks/bin/skills 13개 일치 | source-binding.json, 입력 경로별 SHA |
| 동명 발견·정확한 원격 선택 | self a1과 remote a1 실제 2개 | 실제 MCP discover/connect |
| 원 요청·직접 회신 | 1건씩 성공 | 양쪽 network packet 및 canonical 본문 일치 |
| 실제 MCP ACK | 2건 성공 | 양쪽 native 도구 결과와 canonical acknowledged |
| 수학 최초안·수정안 | 0/2, 미완 | 추가 지시 전 두 actor 종료 |
| 서비스 재시작 전후 동일 ID 보존 답 | 로컬 보존 조회 성공 | service-recovery.json, 원본 SHA 동일 |
| 재시작 후 새 원격 status 증거 | unknown | 종료된 caller로 network.reconcile 관측 |
| 추가 사용자 승인 응답 개입 | 최초 handshake 범위 0회 | 초기 Goal 각 1개, verbatim 동의 경로, 계속 Goal 0개 |

실행 입력은 `/private/var/folders/hw/9m3g7fvn4_l3rp2y473km9sm0000gn/T/adr21-final-20261030-fx0yt4x3`입니다. [입력 전체 manifest](input-manifest.json)의 SHA256은 `5e203237d953a8b656ff4083503fd8b9b5c02c744a3f4939b1ce3236bda461ec`이고, [실행 payload manifest](source-manifest.json)의 SHA256은 `5af07457bec29f64c6ba7acf4604d1e926d18eaf47f12fe2945844ea66310d55`입니다. [입력 경로별 SHA](input-path-sha-verification.json)와 양쪽 payload 실측에서 최종 동결 입력과의 차이는 0개였습니다. 양쪽 실제 release binary SHA256은 `f17f03fafcdf3a31e374d6cbc0ccbbbd8000ba6a7eba5d9b44605e742c409aed`입니다. 원격 payload도 같은 binary를 사용했습니다. P2P 이벤트에서 양방향 payload hash와 authenticated origin이 일치하고 direct 경로 및 relay off를 확인했습니다.

이전 성공 표본과 다른 입력은 기존 6개 경로와 새 xsm/network_recovery.py입니다. [경로별 비교](source-binding.json)에 양쪽 SHA를 남겼습니다. 이전 성공 표본의 보고서·결과·source manifest·artifact manifest SHA가 그대로임을 재확인했고, 이전 pending도 원래 CID에 유지됐습니다.

| 구분 | MacBook 검토자 | jaesol-macmini 요청자 |
|---|---|---|
| runtime | Claude CLI 2.1.312, 동일 binary | Codex CLI 0.164.0 |
| 실제 init/model 관측명 | claude-sonnet-5-5 | gpt-6.1-sol |
| 최초 표시 이름 | a1 | a1 |
| 실제 CID | `446ab95c-ae71-4dd4-b0b7-5c22ac3e3cd7` | `01a18848-4c9b-7703-a707-85d4f1a9ea02` |
| 실제 native PID | 70396 | 34072 |
| 실제 MCP PID | 70492 | 34215 |
| 실제 home | `/Users/jaesolshin/.claude-3` | `/private/tmp/native-journey-samename-latest-mini-fd75g9f5/codex-home` |
| generation | `9cc7137032f1c4743cc0d34c052f115a10797591ea2e07e8639571b6a09b9212` | `854f769ea9874d90c57c36eeb0d65545744a0fb89edf0c6ff8aa4f9486965cbf` |

machine, home_id, 전체 target과 실제 등록 근거는 [results.json](results.json)과 [Claude 초기 등록](streaming-claude-registration.json)에 기록했습니다. Claude FIFO helper는 root 경로 치환을 정규화하면 이전 성공본과 byte가 동일합니다. libproc shim, 실제 provider CID·PID·MCP ancestor·native socket 초기 등록 조건도 그대로입니다. Book actor 전체와 mini MCP·자기 hook의 기존 guard를 유지했습니다. native argv와 실제 Codex provider에서 workspace-write, approval_policy=never를 확인했으며 code_mode_host disable, 새 allowedTools, 전역 hook trust 또는 권한 변경은 없었습니다.

원 요청 SHA256은 `b268004cb9e0a4f2b2c5442a8a59992556d9feb2beba033a93c3c0caafdb865f`, 회신 SHA256은 `c0c6d0826d13de966432d98db385f39cba45d51f4d7c10c2569324d71cd7c96d`입니다. 회신은 다음 실제 본문이며, 원 요청 ID를 reply_to로 지정하고 outcome=succeeded로 보냈습니다.

> a1입니다. 역할은 검토 담당이고, 협업 준비가 됐습니다. 수신 가능한 작업 방식은 xsm 메시지로 받는 검토 요청(note, task)입니다. 코드나 문서를 읽고 의견을 회신하는 읽기 전용 검토를 하며, 권한이나 설정 변경 요청은 받지 않습니다.

connect 응답에 canonical-unavailable-or-mismatch 진단과 빈 claims가 남았습니다. 실제 요청자는 같은 회신을 MCP inbox에서 읽고 받은 토큰으로 ACK했습니다. 첫 검토자 MCP inbox 대기에서 원 요청이 회수됐으며 계속 Goal은 보내지 않았습니다. 자동 wake 성공으로 확대하지 않습니다.

서비스 보존 회수는 모델 재실행 없이 같은 private state/key로 수행했습니다. 양쪽 서비스를 시작한 상태에서 조회하고, stop 후 같은 root로 다시 시작해 같은 ID `79db1ad77556442d`의 questions.status 결과와 회신 `25fb2f0e30aa4709` 본문을 다시 읽었습니다. 원본 canonical·질문·network packet SHA가 모두 동일했습니다. 이 검사는 원래 owner record를 사용한 로컬 보존 답 조회입니다. network.reconcile은 unknown으로 돌아왔으며, 이를 새 원격 receipt나 종료 후 실제 MCP 회복으로 보고하지 않습니다. 임의 PID/CID 또는 ACK·인덱스 보정은 없었습니다.

관측 경계 시각은 아래와 같습니다. 설정·초대·가입은 CLI 출력 파일의 기록 시각, 도구 경계는 실제 MCP proxy 이벤트 시각입니다. 준비·하네스·모델 시간을 포함하므로 순수 네트워크 지연이나 성능 우위 비교에 사용하지 않습니다.

| 단계 | 완료 또는 호출 관측 UTC |
|---|---|
| book 설정 완료 | 2026-10-29T15:28:51.176129+00:00 |
| mini 설정 완료 | 2026-10-29T15:28:52.513605+00:00 |
| book 네트워크 초기화 완료 | 2026-10-29T15:28:53.786260+00:00 |
| book 초대 생성 | 2026-10-29T15:28:53.970872+00:00 |
| mini 가입 완료 | 2026-10-29T15:28:54.574937+00:00 |
| MCP initialize | 2026-10-29T15:30:03.886652+00:00 |
| MCP tools/list | 2026-10-29T15:30:03.889028+00:00 |
| MCP xsm_discover | 2026-10-29T15:30:19.626094+00:00 |
| MCP xsm_connect | 2026-10-29T15:30:23.029650+00:00 |
| MCP xsm_connect | 2026-10-29T15:30:26.990906+00:00 |
| MCP xsm_inbox | 2026-10-29T15:30:38.495313+00:00 |
| MCP xsm_ack | 2026-10-29T15:30:40.762218+00:00 |
| 직접 회신 실제 ACK | 2026-10-29T15:30:40.971555+00:00 |
| 원 요청 실제 ACK | 2026-10-29T15:30:43.792986+00:00 |
| 초기 actor 및 서비스 정리 완료 | 2026-10-29T15:31:42.418705+00:00 |

현재 표본의 Codex는 실제 0.164.0입니다. 과거 A/B/C/D의 0.163 표본은 별도 CLI·도구 협상 조건이며 여기서 재실행하지 않았습니다. 이번 수학 과제 0/2 상태이므로 과거 공통 과제와 완료율·성능을 직접 비교하지 않습니다. 초기 handshake 범위에서는 사용자에게 추가 승인 입력을 받지 않았고, 모델이 최초 사용자 Goal의 verbatim consent와 정상 도구 호출을 사용했습니다. 서비스 재시작은 명시된 operator 준비·관측 작업이며 사용자 입력 0회의 근거에 숨기지 않았습니다.

재사용한 analyze.py는 payload 수를 65에서 66으로 바꾼 뒤 같은 27개 handshake 증거 비교를 모두 통과했습니다. 이는 수학 과제를 검사한 결과가 아닙니다. 제품 xsm/tests는 수정하지 않았습니다.

최초 정리에서 native·MCP·FIFO controller·service·engine의 확인된 PID 9개가 모두 없었습니다. 보존 회수용 두 차례 서비스 기동 후에도 추가 service/engine PID 8개가 모두 없음을 확인했습니다. [최초 Book 정리](book-cleanup.json), [최초 mini 정리](mini-cleanup.json), [재시작 정리](recovery-final-pid-check.json)에 원본을 남겼습니다. state/key와 이전 pending·평가 증거는 보존했습니다.

이번 Book의 지정 3개 global 파일 hash 변화는 0개였고, Codex의 기존 관측 범위도 동일했습니다. 과거 `.claude-3/.claude.json` hash 1개 차이의 원본 before 메타데이터와 변경 주체 미입증 한계는 [기존 기록](prior-global-profile-drift-scope.json)에 그대로 보존했습니다. 임의 복구나 auth 값 조회·복사는 없었습니다.
