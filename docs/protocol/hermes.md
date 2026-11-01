# Hermes 0.22.5 실험 연결

상태: 초기 구현. 실제 PluginContext/도구 registry에 연결했으며, 실제 agent turn·
CLI/TUI 전체 수명·자동 주입·사용자 UI·설치·worker는 미완이다.

[`integrations/hermes/xsm.py`](../../integrations/hermes/xsm.py)의 `register(context)`는
공통 서버의 스키마로 native 도구 21개를 등록한다. 도구 dispatcher가 제공한
`session_id`와 native `session_cwd()`를 사용하고 기존 참여의 폴더 일치를 확인한다.
모델 인자로 발신자를 고르거나 gateway 프로세스의 cwd를 대신 쓰지 않는다.
프로필은 등록 시 실제 Hermes home으로 고정한다.

`on_session_end`는 turn 종료이므로 idle로만 갱신한다. 실제 finalize/delete에서
참여를 닫고, 같은 native ID를 다시 열면 주소를 유지하면서 세대를 바꾼다.
현재 참여 중 작업 폴더가 바뀌면 재참여를 요구하는 오류를 반환한다. 이 경로의
자동 전환은 아직 구현하지 않았다.

SDK는 immutable root마다 별도 Python package namespace로 로드한다. 같은
프로세스에서 서로 다른 snapshot의 client 클래스가 먼저 import된 버전으로
섞이지 않게 한다. 비동기 수명과 정책은 공통 `XsmHost`가 처리한다.

## 현재 동작과 증거

Directory entry `__init__.py`와 도구 21개/수명 hook을 선언한 `plugin.yaml`을
제공한다. 실제 0.22.5 manifest parser와 directory loader의 import를 통과했다.
이 검사는 활성화 정책·plugin validator·실제 agent 실행을 증명하지 않는다.
원시 결과는 `hermes-directory-entry-fixed.log`에 남겼다. 첫 호출은 parser
인자를 잘못 전달해 실패했으며 그 로그도 보존했다.

후속 실제 native validator는 15개 검사를 경고 없이 통과했다
(`hermes-validator-final.log`). 기록용 context가 핸들을 반환하지 않는 경우도
native API 계약대로 허용하며 충돌 처리는 native registry에 맡긴다. SDK 직접
실행에서는 도구 21개가 실제 등록됨을 별도로 확인했다. Private session 모듈
import는 제거했다. 초기 validator 실패도 `hermes-validator-first.log`에 남겼다.

기본 연결은 pull 방식이다. Native push callback이나 사용자 UI를 연결하지
않았으므로 events/user-decisions를 광고하지 않는다. 읽기는 `xsm_inbox`, 소비는
명시적 `xsm_ack`로 구분한다. 질문/승인이 필요한 작업은 답을 만들지 않고 거부한다.

`scripts/probe-hermes-tools.py`는 실제 고정 SDK의 PluginContext, registry.dispatch,
hook dispatcher에서 등록·세션/폴더 분리·전송/pull/ACK·caller 불일치 거부·
turn 종료와 finalize/resume 구분·미연결 UI 거부를 확인한다. 호출 세션은 명시적
fixture이며 실제 Hermes agent나 외부 메신저의 동작을 시험한 것은 아니다.

```sh
/isolated/hermes-env/bin/python scripts/probe-hermes-tools.py --native-source /isolated/hermes-source --output deliverables/hermes-tools
```

모든 HOME/HERMES_HOME/XSM_HOME은 새 임시 경로다. v0.22.5 tag와 실제 import
경로를 대조한다. SDK 의존성은 고정 lock으로 설치하며 API 키나 실제 모델을
사용하지 않는다. 최신 결과는 `hermes-public-api-final/result.json`에 있다.
최초 전송은 서로 다른 비 git 폴더라 정책이 거부했다. 같은 저장소의 두 작업
폴더를 만드는 것으로 fixture를 고쳤으며 그 거부를 우회하지 않았다.

## 안정판 API 감사와 남은 연결

PluginContext에 session_key 메서드가 없다는 이전 조사만으로 불가능하다고
판정하지 않는다. 고정 버전에는 별도
[plugin_session](https://github.com/NousResearch/hermes-agent/blob/v0.22.5/hermes_cli/plugin_session.py)의
task-local session_key와
[session_context](https://github.com/NousResearch/hermes-agent/blob/v0.22.5/gateway/session_context.py)의
async_delivery_supported가 있다.

[inject_message](https://github.com/NousResearch/hermes-agent/blob/v0.22.5/hermes_cli/plugins_injection.py)의
True는 표면별로 의미가 다르다. Local TUI는 실제 큐 수락이지만 messaging
gateway는 작업 예약 뒤 비동기 dispatch 결과가 실패할 수 있다. Classic CLI는
session_key를 검사하기 전에 현재 REPL 큐로 들어간다. 이를 동일하게 admitted로
바꾸지 않으며, 실제 세션/세대와 수락 근거가 검증되는 adapter가 추가로 필요하다.

[ask_choice](https://github.com/NousResearch/hermes-agent/blob/v0.22.5/hermes_cli/plugin_choices.py)는
동기 slash-command의 asker 문맥에 한정된다. 일반 native 도구에서 그대로
호출해 사용자 응답을 확보할 수 있다고 가정하지 않는다. Agent의 clarify는
별도 inline 실행 경로를 쓰므로 registry.dispatch만으로 UI를 대신하지 않는다.
Native UI 결속과 messaging requester 신원은 미완으로 유지한다.
