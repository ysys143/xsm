A21-03 공통 수학 업무를 완료했습니다. 실제 두 Mac의 같은 대화 쌍에서 수학 질문 3건·JSON 회신 3건과 준비 확인을 포함한 canonical ACK 8건을 확인했습니다. 최종 코드의 보존 답 조회와 소유 PID 정리도 완료됐습니다. 새 실험이나 모델 없이 기존 원자료로 작성한 최종 보고입니다.

원소스와 최초 조건

원래 동결 입력은 /private/var/folders/hw/9m3g7fvn4_l3rp2y473km9sm0000gn/T/adr21-final-20261030-fx0yt4x3입니다. Python 53개와 hooks/bin/skills 13개, 총 66개를 양쪽 실행 payload에 결속했습니다. Rust release SHA256은 f17f03fafcdf3a31e374d6cbc0ccbbbd8000ba6a7eba5d9b44605e742c409aed입니다. 원래 동결 입력은 변경하지 않았습니다.

앞선 별도 준비 표본은 UNIX socket 경로 106바이트로 서비스 기동이 실패했고, root를 줄인 뒤 정책 snapshot의 이력 검증이 거절됐습니다. 그 표본은 Claude 준비 모델 1개·공개 거절 1건·업무 0건이며 requester는 시작하지 않았습니다. 정상 snapshot 원본이 없어 정책 초기화·삭제·보정으로 우회하지 않았습니다. 명시적으로 배정된 새 재시도는 새 짧은 root·기기키·팀·CID로 시작했습니다. 기존 실패 표본과 원문/state/key는 [실패 보고서](../native-journey-common-math-latest-20261029T154407Z/report.md)에 보존됐으며 기존 통과 표본에도 영향이 없습니다.

정상 재시도 root는 Book /private/tmp/mq-b-hd9g8g9k와 mini /private/tmp/mq-m-tn48g8wb입니다. 모델 시작 전에 양쪽 policy health=healthy, source=defaults, history_verified=true와 snapshot.source_path==실제 XSM_HOME/config.json을 확인했습니다. 이후 root 경로와 inode는 바뀌지 않았습니다. 기존 guard·구독 profile·libproc 관측 조건을 유지했고 초기 등록에는 실제 provider CID·live PID·MCP ancestor·native 소켓만 사용했습니다. 이는 허용된 setup을 갖춘 controlled native 평가입니다.

| 구분 | Book reviewer | mini requester |
|---|---|---|
| 실제 대화 CID | d6ad76ce-8cd2-4f66-adcd-66d6c3805cc7 | 01a18861-947a-7b41-9b53-406af0d83a46 |
| runtime | 실제 Claude CLI 2.1.312 | 실제 Codex CLI 0.164.0 |
| 실제 관측 model | claude-sonnet-5-5 | gpt-6.1-sol |
| 대화 수명 | 같은 live SDK 유지 | provider가 같은 CID를 실제 resume |
| native PID | 33226 유지 | 67758 → 57613 → 73985 → 43005 → 76740 |
| 최종 MCP PID | 47061 | 76895 |

[정책 preflight Book](book-policy-preflight.json), [mini](mini-policy-preflight.json), [실행 원본](closure-runtime-execution.json)에 근거가 있습니다. CID·PID·세션 메타데이터를 위장하거나 원래 질문을 다른 CID로 재지정하지 않았습니다.

수신 버그 발견과 같은 CID의 원문 회수

준비 확인은 완료됐지만 최초 수학 질문 9f11884127764cad는 admission=true와 canonical pending 상태인데도 MCP inbox가 messages=[], claims=[], inbox_pending=0을 반환했습니다. reason과 claim_diagnostics는 제공되지 않았습니다. 별도 native wake 사본이 남긴 구형 held receipt가 정상 canonical 회수까지 막는 경계였습니다. [수정 전 실제 반환](blocked-exact-evidence.json)과 [수신 경계](held-receipt-boundary.json)를 보존했습니다.

실제 모델의 초기 held deliver 시도는 사용자 yes 없이 거절됐습니다. 그 경로를 승인하지 않았고 이후 재시도하지 않았습니다. 원문·claim·ACK·동의·정책 상태를 controller가 보정하지 않았습니다. 기존 구형 held 사본은 삭제하거나 변경하지 않았습니다.

최초 승인 receive.py 패치와 표준 MCP 재접속 뒤, 같은 Claude PID 33226·CID의 새 MCP PID 78517이 원래 ID의 실제 본문과 claim 1개를 반환했습니다. 이전 claims=0 결과를 성공으로 바꾸어 해석한 것이 아니라, 변경된 MCP의 실제 반환으로 회수를 확인했습니다. [실제 패치 실행](patched-MCP-execution.redacted.json)에 source SHA·PID·도구 결과가 있습니다. claim 토큰만 비공개 처리했으며 원본은 로컬에 보존하고 원본 SHA를 기록했습니다.

소스 overlay·표준 재접속·실제 resume

| 단계 | receive.py SHA256 | handoff.py SHA256 |
|---|---|---|
| 원래 실행 입력 | e3cbe2ece4d70bafbb8d8d4ae3be05a7aeaf64035f564cdc93832fbe78512dcb | e73aec7afa15bf507465ec293061c5ff3b288a33ecf339c9dc3009f1f69e6ee7 |
| 최초 승인 패치 | e2c3fa86a3fecd35d735965c458ff833dcc562aa6b2a4d52b5a34fe33360320e | e73aec7afa15bf507465ec293061c5ff3b288a33ecf339c9dc3009f1f69e6ee7 |
| 최종 두 파일 | edc2b652dfd334bff67d56557ba512069697bd647e9551e8f642793a25fa54b6 | 12564c8c370e4cf6bfe51af249ba382539759b3168a8aa99eb9a0f7a5055691c |

표준 control_request의 subtype=mcp_reconnect, serverName=xsm으로 재접속했습니다. Claude native PID·CID는 유지됐고 MCP 자식은 33396 → 78517 → 47061로 바뀌었습니다. 두 요청 모두 실제 control_response=success가 기록됐습니다. 새 권한이나 허용 도구는 추가하지 않았습니다.

requester는 대기 뒤 자연 종료된 경우가 있어 같은 0.164 runtime이 실제 같은 CID를 resume했습니다. 실제 provider thread.started·DB·새 PID·MCP ancestry로 등록했으며, 종료된 PID를 살아 있다고 처리하지 않았습니다. 일반 계속 Goal에는 동료의 원문·답·실제 요청 ID를 중계하지 않았습니다.

[최초 patch 전후](receive-patch-application.json), [최종 patch 전후와 적용 시각](closure-patch-application.json), [재접속 요청·응답](closure-mcp-reconnect-response.json)에 원본이 있습니다.

세 질문의 실제 JSON과 ACK 8건

공통 본문 marker는 P11-QA-40c1afc34bbd43c4입니다. requester가 실제 입력 파일을 읽어 MCP로 보냈고 reviewer가 실제 inbox에서 읽고 직접 판단했습니다. CLI output schema로 정답을 고정하지 않았습니다.

| 실제 입력식 | 원 요청 ID | 실제 회신 ID | 실제 JSON |
|---|---|---|---|
| 2+2=5 검토 | 9f11884127764cad | e51fbbb4ce884a99 | {"claim_valid":false,"corrected_sum":4,"request_id":"9f11884127764cad"} |
| 2+2=4 수정 검토 | 958971a5c24e4fe4 | 18ea96f2ea894fa5 | {"claim_valid":true,"corrected_sum":4,"request_id":"958971a5c24e4fe4"} |
| 1+1=2 새 짧은 검토 | e1ce6790c1734665 | ac9c995fc5a842df | {"claim_valid":true,"corrected_sum":2,"request_id":"e1ce6790c1734665"} |

마지막 계산값 2는 입력식 1+1=2에 대한 답입니다. 세 회신 모두 outcome=succeeded입니다. 준비 확인의 요청·회신 2건과 위 세 질문·회신 6건을 합쳐, 실제 MCP ACK와 양쪽 canonical acknowledged 8건을 확인했습니다. [results.json](results.json)에 원문 hash·reply_to·실제 ACK ID와 P2P payload hash가 있습니다.

위 표는 최종 결과를 묶은 것입니다. 실제 진행은 최초 두 검토 → 서비스 재시작과 기존 답 조회 → 주소 연결 복구 → 마지막 검토의 동일 ID 재시도 순서였습니다.

재시작 뒤 cached 원답 회수

최초 두 검토와 처리 확인 뒤 같은 private state/key로 양쪽 소유 서비스를 재시작했습니다. 재시작 전후 Claude PID 33226과 당시 requester PID 73985는 그대로였습니다. 원문·질문·network packet hash도 동일했습니다.

준비 신호 뒤 requester가 실제 xsm_question_status로 9f11884127764cad와 958971a5c24e4fe4를 조회해 같은 기존 답을 받았습니다. 답을 새로 생성하거나 질문을 다시 발송한 것은 아닙니다. [재시작 원본](restart.json), [실제 재조회](results.json)의 post_restart_original_ID_MCP_reads에 근거가 있습니다.

주소 힌트 교환과 거절된 동일 ID 재시도

relay=off/port=0에서 양쪽 서비스를 함께 재시작하면서 실제 포트가 51296/57444에서 60039/51783으로 바뀌었고, peer hint에는 옛 포트가 남았습니다. 마지막 ask는 resolve 전에 service-unavailable-or-response-unknown으로 거절됐으며 e1ce6790c1734665의 질문 원본은 생성되지 않았습니다. [접속 경계](post-restart-connectivity-boundary.json)를 별도로 남겼습니다.

추가 운영 복구로 자기 private 서비스만 관측된 원래 포트에 한 차례 더 재기동했습니다. 이어 공개 status가 반환한 현재 endpoint address를 정상 control RPC ping(peer=현재 address)으로 양방향 2회 교환했습니다. peer cache나 초대 비밀을 직접 고치지 않았고, 기기키·팀·membership은 동일했습니다. 자동 재발견 성공으로 보고하지 않습니다.

원문 not-found와 resolve 전 거절을 확인한 뒤, 실제 같은 requester CID가 지원되는 request_id 필드로 e1ce6790c1734665와 동일 본문만 재시도했습니다. 신규 ID나 질문 복제는 없었습니다. 실제 MCP ask 호출은 전송 전 거절 1회를 포함해 4회이며, 논리적 업무는 3건입니다. [포트 복구](stable-port-restoration.json), [정상 주소 교환 2회와 시간](normal-address-exchange.json), [동일 ID·본문 비교](results.json)에 근거가 있습니다.

최종 코드의 실제 MCP 재조회

세 답 생성은 최초 승인 receive.py 패치 단계에서 끝났습니다. 그 뒤 지정된 최종 receive.py·handoff.py만 양쪽 자기 payload에 반영했습니다. 최종 parent root는 /private/var/folders/hw/9m3g7fvn4_l3rp2y473km9sm0000gn/T/adr21-closure-final-1cnnq81i이며 manifest SHA256은 ccc3f22a1d65a33ddc76b0ad1abc4966a65664a6e41777d52b70230cd4fd4011입니다.

같은 Claude SDK의 새 MCP 47061이 실제 inbox를 반환했습니다. 같은 Codex CID의 native PID 76740·MCP PID 76895는 기존 세 ID를 실제 xsm_question_status로 조회해 같은 보존 답을 반환했습니다. 최종 코드 적용 후 새 ask는 0건입니다. 최종 코드로 세 수학 업무를 새로 반복했다고 주장하지 않습니다.

최종 양쪽 payload 66개 파일의 승인 source 차이는 0개입니다. 원래 동결 입력은 보존됐습니다. [전체 source-binding](source-binding.json), [최종 실행 manifest](source-manifest-closure-executed.json), [실제 source·PID·도구 반환](closure-runtime-execution.json)에 기록했습니다.

관측 시간과 개입 횟수

| 질문 | 같은 Mini 시계의 질문 생성부터 실제 답 수신 |
|---|---:|
| 9f11884127764cad | 1298.948초 |
| 958971a5c24e4fe4 | 110.461초 |
| e1ce6790c1734665 | 81.298초 |

이 값에는 코드 수정·대기·복구가 포함된 관측이 들어 있습니다. 마지막 값은 실제 원본 생성 뒤의 구간이며, 앞선 resolve 거절과 주소 복구 구간은 별도입니다. 순수 네트워크 지연이나 성능 비교가 아닙니다. Book/controller와 Mini의 시계 차이도 관측돼 서로 다른 호스트 시각을 빼서 네트워크 지연을 만들지 않았습니다. 정확한 native 종료 시각·provider 내부 대기 등 직접 계측하지 않은 값은 미계측입니다.

[단계별 시간표](comparison-timing.md)와 [원시 시간 기록](timing.json)에 설정·초대·가입·패치·재접속·ACK·주소 교환을 분리했습니다.

| 항목 | 실제 기록 |
|---|---:|
| 정상 재시도 표본의 새 대화 | 2개 |
| Claude CLI 기동 | 1회 |
| Codex CLI 전체 기동 | 5회 |
| 그중 실제 같은 CID resume | 4회 |
| 별도 agent 일반 계속 Goal | 6회 |
| 표준 Claude MCP 재접속 | 2회 |
| 정상 주소 힌트 교환 | 2회 |
| 최초 network 서비스 기동 | 2회 |
| 계획한 재시작의 서비스 기동 | 2회 |
| 추가 포트 복구의 서비스 기동 | 2회 |
| 초대 생성 / 가입 | 1회 / 1회 |
| native 런타임에서 추가 human yes·승인 답변 | 0회 |
| controller 본문·답 중계 | 0회 |

0 human은 추가 사용자 승인 답변이 없었다는 뜻입니다. 별도 agent cue 6회, 실제 resume 4회, reconnect 2회, address 교환 2회와 setup·패치·운영 복구까지 없었다는 뜻이 아닙니다. 관측 wrapper의 exit counter는 자신이 쓴 두 입력만 세므로 직접 FIFO로 보낸 계속 Goal 원본을 별도로 집계했습니다.

과거 A/B/C/D의 ephemeral Codex 0.163과 이번 persistent Claude SDK·Codex 0.164는 수명·도구 협상·resume·source 수정·운영 준비 조건이 다릅니다. 성능 순위를 만들지 않으며, 최종 생산 onboarding의 마찰 0이나 무개입 성공으로 과장하지 않습니다.

소유 PID 정리와 보존

양쪽 cleanup 원본의 remaining_owned는 빈 목록입니다. PID·시작 시각으로 확인한 소유 신원 22개도 모두 종료됐습니다. 원문/state/key/held와 기존 실패 표본은 삭제하지 않았습니다. 구형 held 사본은 bytes가 그대로임을 확인했습니다. [Book cleanup](book-cleanup.json), [mini cleanup](mini-cleanup.json), [소유 PID 재확인](final-owned-PID-check.json), [held bytes 보존](old-held-final-byte-check.json)에 근거가 있습니다.

현재 보존 기록 비교 17개는 passed입니다. 최신 전체 회귀·집중 검토는 coordinator의 별도 작업이며, 이 보고서 작성 중 새 코드·실험·모델·추가 검사는 수행하지 않았습니다.

metadata 대조에서는 Book의 .claude-3/settings.json, .claude-3/.claude.json, .codex/config.toml hash 차이를 관측했습니다. 변경 주체와 권한 내용 변화 여부는 미확인입니다. Mini의 기존 Codex metadata 비교는 일치했습니다. 이 작업에서 global profile 명시적 쓰기나 auth 값 조회·복사를 하지 않았고 임의 복구도 하지 않았습니다. global profile 전체 불변을 주장하지 않습니다. [metadata 범위와 한계](profile-metadata-limits.json)에 기존 기록을 남겼습니다.
