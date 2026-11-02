# Hermes 0.22.5 사용자 질문 연결 경계

상태: 일반 모델 도구의 native UI 연결은 미완이다. 아래 시험은 실제 SDK
함수와 명시적 caller/UI fixture를 사용하며 실제 agent·사람 응답·메신저 시험이 아니다.

## 고정 source와 실행

Hermes v0.22.5의 bf0203a794a07aac3ff764972ab9087baa4e4f4e를 확인하고
tracked source가 tag와 같은 상태에서 실행했다. 새 HOME/HERMES_HOME/XSM_HOME을
사용했고 모델 호출과 외부 전송은0회다. 도구 등록은 실제 PluginContext,
호출은 model_tools.handle_function_call과 registry.dispatch를 각각 사용했다.
시험에서 만든 registration은 dispose했다.

초회는7개 확인 뒤 선택적 MCP SDK가 없어 ElicitResult 조회에서 실패했다
(hermes-ui-dispatch-boundary/result.json과 같은 이름의 log). 전체 성공으로
계산하지 않는다. 준비 명령의 기본 Python에는 packaging도 없어 lock marker
처리를 시작하지 못했으며 native env의 기존 packaging으로 준비를 다시 했다.

Native uv.lock의 MCP extra 전이 의존성을 고정해 wheel28개를 별도 임시 target에
설치했다. --no-deps/--no-build/--require-hashes로 lock의 wheel hash를 검증했고
기존 Hermes env·source·사용자 profile은 변경하지 않았다. 준비 목록과 설치 결과는
hermes-ui-sdk-preparation.json과 hermes-ui-sdk-install.log에 있다.

새 프로세스의 재시험은8개 확인을 통과했다
(hermes-ui-dispatch-boundary-with-mcp/result.json과 같은 이름의 log).
Native source 파일별 hash도 결과에 보존했다. 모든 원시는
deliverables/protocol-foundation/ 아래에 있다.

## 확인한 구분

- 일반 모델 dispatcher는 실제 session_id를 handler에 전달했지만 parent_agent는
  전달하지 않았다. 직접 registry.dispatch에 parent_agent를 명시적으로 넣으면
  handler가 받았다. 후자를 일반 agent 경로의 증거로 사용하지 않는다.
- 일반 도구의 PluginContext.ask_choice는 asker가 없어 None이었다. 실제
  invoke_plugin_command와 bind_asker 문맥에서는 exact 질문/선택지를 fixture
  asker에 전달하고 선택값을 받았다. 문맥을 벗어난 뒤 다시 None이었다.
- 실제 ElicitationHandler에 fixture consent accept를 반환하면 action=accept,
  content={}였다. 필수 answer enum이 있는 form을 보내도 선택값은 반환하지
  않았다. 이 결과에서 임의 answer를 만들어 XSM의 사용자 답으로 승격하지 않는다.

## 구현에 대한 의미

Plugin 문서의 optional parent_agent kwargs는 모든 모델 도구 호출이 native
clarify_callback을 받는다는 계약이 아니다. 현재 일반 도구에서 이 객체를 받을
것으로 가정하거나, 내부 active-parent getter를 plugin UI API로 대신 쓰지 않는다.
Slash-command의 공개 UI는 별도 연결 후보지만 모델 도구의 질문 전달·busy 동시성·
정확한 대화 결속·취소를 아직 구현/검증하지 않았다. MCP accept={}도 현재 XSM이
요구하는 실제 answer 필드를 만족하지 않는다.

2026-11-03 구현 담당 세션이 기록했다. 같은 담당자가 공개 native UI 경로 또는
사용자가 승인한 generic upstream API 변경으로 세션·질문·실제 답 결속을
실행한 뒤 재판정한다. 버전 변경이나 범위 제외에 대한 사용자 승인은 없으며
P4/P5와 전체 목표의 미완 조건으로 유지한다.
