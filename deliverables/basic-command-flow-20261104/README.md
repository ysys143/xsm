# 기본 명령 수정과 실제 하네스 검증

승인한 구현과 여섯 하네스의 기본 모델 왕복 검증을 마쳤다.
각 하네스에서 확인한 경로는 아래와 같으며, 전부 같은 방식으로 시험한 것은 아니다.
실패·준비 단계·개입 기록도 함께 보존했다.

## 구현

- `0e2c413`: native publish/connect 명령을 정확한 대화·상대에 일회 결속하고,
  저장소 검색·표 출력을 CLI/MCP에 반영했다. 자연어 요청은 완전한 발견 결과의
  유일한 살아 있는 저장소 상대만 고른다. 대상 이름 불일치·질문·취소·부분 결과는 자동 승인하지 않는다.
- `5e31d76`: 실제 Pi 공급자가 거절한 inbox ID 스키마의 lookaround를 제거했다.
  정확한 ID 검사와 마지막 개행 거절은 서비스에 유지했다. 구조 스키마 검사와 서비스 검사를 구분했다.
- `68636fb`, `0068070`: 뒤늦은 native 질문 답변도 미소비 명령·자연어 선택보다 우선하도록 보완했다.
- README·스킬·프로토콜 안내에 발견과 권한의 구분, 자연어 대상 선택,
  장시간 대기 루프 금지, JSON 필드에 의한 상태 판정, queued의 의미를 반영했다.

전역 설치·릴리즈는 하지 않았다. Claude 시험에는 선택된 기존 대화에만 개발 플러그인과
격리 XSM_HOME을 적용했다. 기존에 설치된 0.5.2의 동작이 소스 수정만으로 바뀌었다고 주장하지 않는다.

## 실제 모델 경로

| 하네스 | 모델 | 확인한 결과 | 남은 경계 |
|---|---|---|---|
| Claude Code | 실제 응답 `claude-opus-5-5` | native `/xsm publish` 한 번으로 공개, discover 위치 인자·표 출력, idle 입력 수신→실제 MCP ACK·회신→reference 수신·ACK | 상대는 generic protocol reference. 자연어 타 저장소 선택은 서비스 통합 검사로 별도 확인 |
| Codex 0.166.0 | native turn_context `gpt-6.1-sol` | 지정 ref:8e85bd의 기존 대화 재개. 실제 CLI inbox 읽기→ACK→succeeded 회신→reference 수신·ACK | passive 요청의 명시적 수신. idle queue wake와 native 공개 동의는 미검증. raw provider 모델 표기는 별도 수집하지 않음 |
| Pi 1.4.0 | 실제 응답 `gpt-6-luna` | 전체 도구 목록, native 모델의 xsm_send, 실제 답변, reference에서 note·답변 두 건 ACK. 공급자 요청 2회 | owned native turn이며 ordinary idle wake와 native 공개 동의 UI는 별개 |
| OpenCode 1.19.5 | 실제 응답 `gpt-6-luna` | 전체 도구 목록, native 모델의 xsm_send, 실제 답변, reference에서 두 건 ACK. 공급자 요청 3회 | Pi와 같은 경계 |
| OpenClaw 2026.10.9 | 실제 응답 `gpt-6-luna` | 준비 분리 후 전체 도구 목록으로 실제 모델 송신·회신, reference ACK 2건. 공급자 요청 4회 | 최초 timeout과 준비 스크립트 오류는 별도 실패 기록. ordinary idle wake·native 공개 동의 UI는 별개 |
| Hermes 0.22.5 | 실제 응답 `gpt-6-luna` | 전체 도구 목록, native 모델의 xsm_send, 실제 답변, reference에서 두 건 ACK. 공급자 요청 5회 | 최초 preflight는 실패로 보존. 가용성 회복 뒤 최초 native 턴에서 확인. ordinary idle wake·native 공개 동의 UI는 별개 |

Pi·OpenCode·OpenClaw·Hermes는 이미 설치된 ocx의 OpenAI 구독 passthrough를 사용했다.
upstream은 chatgpt.com/backend-api/codex이며 API 키 과금 경로를 사용하지 않았다.
시험용 relay는 Chat Completions→Responses 경계에 `strict:false`를 명시했다.
스키마 필터·모델 인자 수정·응답 합성 없이 전체 XSM 도구를 전달했다.
프로필·전역 proxy 설정은 바꾸지 않았다.

## 실패와 개입

- 최초 Pi Anthropic 구독 요청은 HTTP 400 “You're out of extra usage”였다.
  같은 구독 경로로 다른 하네스의 실패를 반복하지 않았다.
- OpenAI 경로의 최초 Pi 실행은 `message_ids.items.pattern` lookaround 때문에 HTTP 400이었다.
- send-only 진단에서는 실제 모델이 note에 outcome을 붙이고 target/targets를 함께 보냈다.
  native 도구가 이를 거절했다. upstream 인자와 native 인자가 같았으며 ACK는 0건이다.
  이 진단을 통과로 세지 않았다. 이후 스키마와 strict 설정을 수정한 별도 실행에서 전체 도구로 통과했다.
- Claude 첫 셸 왕복은 환경변수 접두사가 붙은 명령을 시험 allow-list가 놓쳐
  ACK·회신 명령에 각각 일회 허용이 필요했다. 무개입 성공으로 세지 않았다.
  두 번째 실제 MCP 왕복에는 이 개입이 없었다.
- Codex 후보를 본 대화라고 판단했던 것은 공유 데몬 PID를 대화 ID로 오인한 잘못이었다.
  실제 ID를 대조하면 본 대화는 ref:e6bd9e, 지정 시험 대화는 ref:8e85bd로 다르다.
  잘못 판단한 동안 Codex에 시험 메시지를 보내지 않았다. native thread/read의 notLoaded를
  확인한 후 지정한 기존 대화를 재개했다. 새 격리 대화 승인 질문은 필요 없어졌고 새 대화를 만들지 않았다.
  `codex/before-native-status.json`과 `codex/result.json`에 실제 ID를 기록했다.
- Codex 실행기의 첫 준비는 Python import 경로 누락으로 native 실행 전에 실패했다.
  경로 수정 후 한 번의 실제 native turn으로 원 요청을 읽고 회신했다.
- OpenClaw의 첫 timeout은 모델 요청 0회였다. 준비 단계를 분리한 후속 시험에서는
  검증기가 추가한 idempotencyKey가 native principal/device 조건을 만족하지 않아 준비 RPC가 거절됐다.
  본체 creation_params와 같은 인자를 쓰는 준비 재검사는 통과했다. 최초 timeout의 원인을
  이 시험 구성 오류와 동일하다고 단정하지 않는다. 준비가 끝난 별도 새 세션·nonce로
  실제 모델 단계 14.204초, 전체 29.179초에 왕복을 확인했다. 원 요청을 재전송하지 않았다.
- Orca discover 입력은 앞선 권한 창 때문에 제출이 막혔다. 같은 요청 ID의 receipt를
  확인하고 앞선 작업 종료 후 이미 입력된 명령만 제출했다. source transcript에서 실제 실행을 확인했다.
- mutation 첫 구성은 복사본에 provider catalog/파일이 없어 실행 자체가 실패했다.
  `*-setup-attempt.log`와 `mutation-setup-attempt.json`에 보존했다.
  완전한 fixture로 정상 검사 통과를 확인한 뒤 독립 검토에서 찾은 다섯 변이와 native 질문 답변 변이를 각각 주입했다.
- 추가 동시 검사 22건 중 통합 경로 한 건에서 CLI 출력이 비어 JSONDecodeError가 발생했다.
  ResourceWarning도 함께 남았다. 원인은 확정하지 않았다. CLI stderr를 검사 실패에 표시하도록
  보완했고, 해당 경로와 후속 동의 검사 세 건을 다시 실행해 통과했다. 원 실패는 `consent-tests.log`에 있다.

## 검사 명령과 출력

서로 겹치는 검사이므로 아래 수를 합산하지 않는다. native 모델 검증 수에도 넣지 않는다.

- `final-regressions.log`: 최종 수정 뒤 public command·native consent·network interfaces 55건 통과.
- `core-tests.log`: public command, directory, selected connection, native consent,
  OpenClaw schema, common question service, instructions, network interfaces. 124건 통과.
- `protocol-tests.log`: `python3 -m unittest tests.test_protocol tests.test_openclaw_schema
  tests.test_messaging_instructions tests.test_public_command_flow -q`. 당시 79건 통과.
- `consent-recheck.log`: 후속 사용자 취소·native 질문 답변·전체 명령 회신 경로 3건 재검사 통과.
- `native-answer-recheck.log`: native 답변이 이전 명령·자연어 연락 요청을 무효화하는 경로 및 기존 native consent 9건 통과.
  자연어 요청의 새 검사는 수정 전 실제 실패를 `native-contact-answer-red.log`에 보존했다.
- `python3 deliverables/basic-command-flow-20261104/check-mutations.py`: 정상 복사본 검사 후
  여섯 변이 모두 의도한 assertion으로 실패했다. `mutation-results.json` 참조.
- `python3 scripts/check-protocol-schema.py --output .../protocol-schema-check.json`: passed=true.
- `python3 scripts/generate-protocol-operations.py --check`: 종료 0.
- `python3 scripts/generate-messaging-guide.py --check`: source와 일치, 종료 0.
- `git diff --check`: 종료 0.

Claude의 원시 tool 호출·결과는 `claude-native-evidence.json`, 실제 reference 연산은
`claude-reference-operations.json`에 추출했다. unrelated 사용자 대화와 모델 thinking은 복사하지 않았다.
나머지 런타임 실행·실패 원문은 `native/`, 파일 크기·hash는 `native/manifest.json`에 있다.
자격 증명·사용자 프로필은 복사하지 않는다.

## 완료 범위와 한계

기본 모델 왕복은 6/6이다. Claude만 native idle 입력을 직접 확인했다. Codex는 passive
요청을 CLI에서 명시적으로 읽었고, 나머지 넷은 owned native turn을 사용했다. 상대는
모두 reference 참여자다. 모든 native 간 조합·native UI·publish 동의를 여섯 종에서
시험한 것으로 일반화하지 않는다. 사용자 설정·훅 신뢰·권한 규칙·전역 proxy는 바꾸지 않았다.

시험용 child·reference·gateway는 종료를 확인했다. 기존 Claude 대화는 공개를 철회하고
그대로 남겼다. 메신저 재검증·속도 행렬·전역 설치·릴리즈는 하지 않았다.
