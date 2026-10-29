# 두 물리 Mac Codex 여정과 동일 CID 재개 완료

fresh164-v2에서 만든 두 실제 대화를 같은 0.164 CLI로 재개해 저장된 협업 준비·최초안·수정안과 실제 회신을 회복했다. 검토자는 남아 있던 원요청 3건을 실제 MCP에서 읽고 ACK했다. 요청 3건과 회신 3건 모두 canonical acknowledged 상태다. 재개 이후 새 메시지 ID와 중복 회신은 0건이다.

## 실행 대상과 동결본

| 항목 | Book | mini |
|---|---|---|
| 물리 호스트 | Jaesolui-MacBookPro.local | Jaesolui-Macmini.local |
| 같은 실제 CID | `01a18648-551e-7ac2-8f4c-5925689f63c7` | `01a18648-4f65-7512-a426-f2966dedea84` |
| 최초 생성과 재개 CLI | `codex-cli 0.164.0` | `codex-cli 0.164.0` |
| 실제 관측 모델 | `gpt-6.1-sol` | `gpt-6.1-sol` |

모델명은 실제 provider rollout의 turn_context에서 관측했고 임의로 지정하지 않았다. 각 최초 session_meta도 CLI 0.164.0이며, 모든 재개 thread.started가 원래 CID와 일치했다. 각 단계의 CLI 인자와 실제 MCP 원문은 호스트별 resume-evidence 아래 보존했다.

실행 manifest SHA-256은 `5ac5d6338be88f4cc85754c3daa539b52b7778c48062712aa0031be549d7fe68`이다. Python 52개와 hooks/bin/skills 13개, 총 65개를 동결했다. 양쪽 private payload와 보존된 동결본의 SHA가 일치한다. 저장소 전체를 같은 상태로 고정한 결과는 아니다.

Rust는 사용자가 지정한 `/private/tmp/adr21-install-0q83fzpr/state/network/bin/xsm-net` release를 사용했다. 현재 Rust 소스의 relay loopback 정책 수정 전 바이너리다. 이번 실제 경로는 LAN direct이며 원본 바이너리 SHA와 당시 Rust 소스 SHA는 source-manifest.json에 별도로 기록했다.

## 중단 후 preflight

2026-10-29 07:02:54 UTC부터 재개 작업을 시작했다. 소유 PID와 private socket을 확인했을 때 양쪽 actor/MCP/service는 종료 상태였다. mini에는 연결되지 않는 socket 파일만 남아 있었다. 원본 CID가 provider DB에 존재하고 최초 CLI가 모두 0.164임을 확인했으며, 같은 auth 참조와 같은 실제 CLI 실행 파일을 유지했다.

같은 XSM_HOME과 원래 state/key로 동결본 serve만 다시 시작했다. init/join/map-repository를 다시 하지 않았고 state를 수동 편집하지 않았다. operator의 peer health ping에는 공개 endpoint 주소만 사용했으며 업무 본문을 중계하지 않았다. 기존 전역 profile 설정 파일의 SHA와 auth 파일 metadata는 재개 전후 두 호스트 모두 동일했다. auth 값은 controller가 읽거나 복사하지 않았다.

## 중단 전 표본과 재개 후 표본

중단 전 두 모델은 이미 실제 준비 회신·최초안 검토·수정안 재검토를 마쳤다. Book은 세 회신을 실제 소비 확인했고, mini의 세 원요청은 handoff-recorded 상태였다. 이 차이를 중단 전 snapshot으로 보존했다.

| 원질문 ID | 실제 회신 ID | mini 중단 전 | mini 재개 후 | 본문 회복 |
|---|---|---|---|---|
| `f411925587a64d35` | `911130c4ce094276` | `handoff-recorded` | `acknowledged` | 양쪽 실제 MCP 본문 확인 |
| `85f7b01d4e4c4eed` | `6c9d07e8a3af4339` | `handoff-recorded` | `acknowledged` | 양쪽 실제 MCP 본문 확인 |
| `9e17a98be37c40bc` | `e9c85c64a49d4ae8` | `handoff-recorded` | `acknowledged` | 양쪽 실제 MCP 본문 확인 |

Book의 세 회신은 중단 전후 모두 acknowledged다. mini의 상태 전이는 실제 모델의 xsm_inbox와 xsm_ack 호출로 일어났다. controller는 ACK·질문 index·본문·권한·CID를 보정하지 않았다. 원래 질문 본문, 회신 배열, 원래 네트워크 packet은 전후 동일했다.

| 호스트 | 중단 전 실제 MCP 호출 수 | 회복 단계 실제 MCP 호출 수 |
|---|---|---|
| book | `{"xsm_discover": 1, "xsm_connect": 1, "xsm_inbox": 3, "xsm_ack": 3, "xsm_ask": 2}` | `{"xsm_question_status": 3, "xsm_inbox": 1}` |
| mini | `{"xsm_inbox": 3, "xsm_send": 3}` | `{"xsm_inbox": 1, "xsm_ack": 1}` |

회복 단계에서 Book은 원래 세 ID로 xsm_question_status를 호출하고 자신의 수신함을 확인했다. mini는 실제 수신함에서 원래 세 본문을 회복해 처리 확인을 완료했다. 신규 xsm_ask/xsm_send/xsm_connect 호출은 없었다. 실제 회신 본문은 2+2=5의 원소 수 반례와 2+2=4 수정안의 최종 판정을 담고 있다. 각 본문과 원래 요청의 결속은 resume-results.json의 workflow에 보존했다.

Book의 상태 조회 시점에는 mini의 후속 ACK가 아직 끝나지 않아 별도 network_delivery의 pending 표시가 관측됐다. 해당 표시를 고치지 않았다. 최종 판단은 뒤에 실제 MCP ACK로 바뀐 canonical 상태와 원문 대조를 근거로 삼았다.

## 도구 노출과 하네스 오류

업무 회복 전에 같은 두 CID에서 도구 노출만 확인하는 턴을 분리했다. 첫 시도에서는 helper가 이전 PID의 등록 파일을 현재 PID의 등록으로 잘못 인정했다. 그 결과 startup barrier가 tools/list 전달을 풀지 못했고 모델에는 함수가 노출되지 않았다. 이번 두 실행과 이전 mini 0.164 재개, 총 3개 실행이 이 관측 오류의 영향을 받는다. 실패 원본을 보존했고 동일 조건을 반복하지 않았다.

helper의 판정을 실제 thread.started CID·provider DB·현재 live PID와 MCP ancestry가 모두 일치할 때만 참이 되도록 바로잡았다. 이 변경은 관측과 허용된 초기 등록 setup에 한정하며 동결된 제품 소스는 바꾸지 않았다. 이후 같은 CID에서 양쪽 xsm_discover 실제 1회 호출과 status=ok, 등록 완료 startup barrier를 확인한 뒤 업무 회복 턴을 시작했다. 업무 프롬프트에는 회신 본문이나 예상 답변을 주입하지 않았다.

이것은 초기 등록 setup을 갖춘 controlled native 평가다. 새 버전 native 수신 hook 실행은 관측하지 않았으며 실제 수신은 MCP pull 경로였다. 자동 wake 성공이나 무보정 onboarding 성공으로 확대하지 않는다.

## 옛 실패 표본과 소스 차이

옛 0.163 표본의 질문 `ed42ef075aff4b47`은 그대로 pending이고 관련 파일의 SHA도 재개 전후 동일하다. 해당 CID로 메시지를 보내거나 새 CID로 redirect하거나 질문을 복제하지 않았다.

여정 종료 무렵 main이 R1 timeout 구분을 위해 수정한 `xsm/network.py`와 `xsm/probe.py`는 이번 실행 복사본에 적용하지 않았다. [소스 차이](source-drift-after-resume.json)에 실제 실행 SHA와 현재 저장소 SHA를 기록했다. 실행 manifest와 payload는 유지했다. 느린 파일시스템 복구는 main의 별도 검사 대상이다. 추가 native 모델 재시작은 하지 않았다.

## 종료와 남은 자료

모든 재개 actor와 MCP가 정상 종료한 뒤 양쪽 소유 service와 engine을 공개 stop으로 종료했다. stop exit는 둘 다 0이고 강제 종료 신호는 없었다. 확인한 소유 PID 잔여는 0개다. 원본 state/key·기존 실패 자료·이번 전후 snapshot은 각 호스트 private/tmp와 이 산출물 디렉터리에 보존했다. 커밋·외부 메시지 발송·전역 profile 또는 권한 변경은 하지 않았다.

현재 복구는 07:11:41 UTC 관측에서 끝나 처음 상태 확인부터 9분 안에 실제 결과를 수집했다. 이후 원문·ACK·동일 CID·해시·PID 대조와 자료 보존을 마쳤다. 분석상 완료 기준은 [resume-results.json](resume-results.json)의 completed=true와 각 원래 요청/회신의 실제 MCP 본문 및 ACK 결속이다. 보고·상태 문구는 지정한 CJK 범위 정규식으로 검사했다. raw 모델·서버 증거는 변경하지 않았다.

증거 경로:

- [동결 manifest](source-manifest.json), [재개 결과](resume-results.json), [분석 코드](analyze-resume.py)
- [Book 재개 전](book-before-resume.json), [mini 재개 전](mini-before-resume.json)
- [Book 재개 후](book-resume-evidence/resume-evidence/after-resume.json), [mini 재개 후](mini-resume-evidence/resume-evidence/after-resume.json)
- [Book 종료](book-resume-final-cleanup.json), [mini 종료](mini-resume-final-cleanup.json)

## Claude와 Codex의 별도 최소 여정 계획

1. 실제 Claude CLI와 기존 구독 인증 home을 metadata로 확인하고, 다른 home의 Codex와 함께 별도 private 표본을 준비한다. 전역 설정과 인증 값은 바꾸거나 복사하지 않는다.
2. 모델에 업무 목표만 주고 발견·선택·실제 준비 회신·최초안 검토·수정안 최종 회신을 수행한다. 양쪽 실제 MCP/수신 본문과 소비 확인을 수집한다.
3. 각 런타임에서 처음 만든 같은 실제 대화를 재개해 미처리 업무 회복을 확인하고 PID·profile 해시를 대조한 뒤 종료한다. 이번에는 계획만 남겼으며 Claude 모델은 실행하지 않았다.
