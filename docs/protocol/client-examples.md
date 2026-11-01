# stdio 프로토콜 클라이언트

Python 표준 라이브러리 구현은 [`clients/python/xsm_client.py`](../../clients/python/xsm_client.py), Node 내장 모듈 구현은 [`clients/typescript/xsm-client.mjs`](../../clients/typescript/xsm-client.mjs)에 있다. TypeScript는 인접한 [`xsm-client.d.mts`](../../clients/typescript/xsm-client.d.mts)를 사용한다. `.mjs`를 직접 실행하므로 TypeScript 컴파일러나 npm 패키지 설치가 필요하지 않다. Python 3.9 이상과 Node 18 이상을 대상으로 한다. Python 타입 주석은 `from __future__ import annotations`로 평가를 미룬다.

두 클라이언트는 기본적으로 다음 프로세스를 셸 없이 시작하고, 연결이 반환되기 전에 `initialize` 요청을 완료한다.

```text
python3 -m xsm protocol serve --stdio
```

전송은 UTF-8 JSONL의 JSON-RPC 2.0이다. 초기 요청은 다음과 같으며, 응답 ID의 타입과 값을 그대로 대응시킨다. 줄바꿈은 각 JSON 객체 끝에 하나씩 붙는다.

```json
{"jsonrpc":"2.0","id":"1","method":"initialize","params":{"protocolVersion":"1"}}
```

이 문서는 실험적 v1 계약을 구현한 클라이언트 예제다. 소형 피어를 사용하는 전송 검사와 실제 `python -m xsm protocol serve --stdio` subprocess를 사용하는 상호 운용 검사를 구분한다. 실제 서버 검사도 자식 프로세스의 첫 import 전에 HOME과 XSM_HOME을 임시 디렉터리로 격리한다. 원격 연결이나 네이티브 런타임 인증을 검증한 것은 아니다.

## Python

저장소 루트에서 `PYTHONPATH=clients/python`으로 실행하거나 `xsm_client.py`를 애플리케이션의 모듈 경로에 둔다. 아래 함수의 `operation`과 `arguments`에는 서버가 지원하는 작업 이름과 인자를 넘긴다. 프로필·대화 식별자도 호출 환경에 맞게 제공한다.

```python
import asyncio
import os
from xsm_client import XsmClient


async def run(profile, conversation, operation, arguments):
    async with await XsmClient.connect() as client:
        opened = await client.session_open(
            runtime="python", profile=profile, conversation=conversation,
            cwd=os.getcwd(), capabilities=[],
        )
        session = opened["session"]
        try:
            await client.session_update(session, {"state": "busy"})
            # 동시 요청도 ID별로 연결되며 응답 도착 순서에 의존하지 않는다.
            results = await asyncio.gather(
                client.operation_call(session, operation, arguments),
                client.operation_call(session, operation, arguments),
            )
            return results
        finally:
            await client.session_close(session)
```

`asyncio.wait_for(client.request(...), timeout)`으로 호출 대기 시간을 제한할 수 있다. 취소한 요청의 늦은 응답은 무시한다. 연결 초기화 시간은 `asyncio.wait_for(XsmClient.connect(), timeout)`으로 제한한다.

## JavaScript와 TypeScript

아래 코드는 저장소 루트의 `.mjs` 또는 `.mts` 파일에서 사용할 수 있다. TypeScript의 `module`과 `moduleResolution`을 `NodeNext`로 설정하면 `.mjs` import에 대응하는 `.d.mts` 선언을 읽는다.

```javascript
import { XsmClient } from './clients/typescript/xsm-client.mjs';

async function run(profile, conversation, operation, args) {
  const client = await XsmClient.connect();
  try {
    const opened = await client.sessionOpen({
      runtime: 'node', profile, conversation,
      cwd: process.cwd(), capabilities: [],
    });
    const session = opened.session;
    try {
      await client.sessionUpdate(session, { state: 'busy' });
      return await Promise.all([
        client.operationCall(session, operation, args),
        client.operationCall(session, operation, args),
      ]);
    } finally {
      await client.sessionClose(session);
    }
  } finally {
    await client.close();
  }
}
```

TypeScript 호출 예제와 잘못된 인자에 대한 컴파일 검사는 [`clients/tests/types.mts`](../../clients/tests/types.mts)에 있다. Node 요청에는 개별 취소 API가 없다. `Promise.race`로 대기만 중단해도 전송된 요청은 유지된다. 연결을 종료하려면 반드시 `await client.close()`를 호출한다.

## 세션과 알림

`session.open`의 인자는 `{runtime, profile, conversation, cwd, capabilities: []}`이며 응답 전체를 반환한다. 응답의 `session`은 비어 있지 않은 불투명 문자열이고 `generation`과 추가 필드는 그대로 보존한다. 문자열을 해석하거나 대화 ID로 대체하지 않는다. 모든 세션 메서드에 이 핸들을 명시적으로 전달한다. 여러 세션도 같은 연결에서 사용할 수 있다.

| RPC 메서드 | Python | JavaScript / TypeScript | 전송 params |
| --- | --- | --- | --- |
| `session.update` | `session_update(session, updates)` | `sessionUpdate(session, updates)` | `{...updates, session}` |
| `session.close` | `session_close(session)` | `sessionClose(session)` | `{session}` |
| `operation.call` | `operation_call(session, operation, arguments)` | `operationCall(session, operation, args)` | `{session, operation, arguments}` |
| `events.subscribe` | `events_subscribe(session)` | `eventsSubscribe(session)` | `{session}` |
| `delivery.report` | `delivery_report(session, id, state)` | `deliveryReport(session, id, state)` | `{session, id, state}` |

`updates` 안의 `session`은 클라이언트가 거부한다. 현재 서버는 `state` (`idle`/`busy`)와 `name`만 수정하며 `cwd` 등 세션 정체성을 바꾸는 필드는 `-32602`로 거부한다. `request(method, params)`는 서버 확장 메서드에도 사용할 수 있지만, 위의 세션 메서드와 `session.*`에는 `params.session`이 필요하다. `decision.response`는 신뢰된 호스트 전용이다. 두 클라이언트는 호스트 신뢰를 설정하지 않으며 범용 `request()`에서도 해당 메서드를 거부한다. 서버의 권한 검사도 별도로 필요하다.

`events/available` 알림은 다음 형태로 도착한다. 구독 응답보다 먼저 도착해도 큐에 보존된다.

```json
{"jsonrpc":"2.0","method":"events/available","params":{"session":"opaque-handle","ids":["delivery-id"]}}
```

Python에서는 다음과 같이 읽는다. 세션을 이미 연 `client`와 `session`을 사용한다.

```python
await client.events_subscribe(session)
event = await client.next_notification()
if event["method"] == "events/available":
    event_session = event["params"]["session"]
    ids = event["params"]["ids"]
```

JavaScript에서도 같은 알림 객체를 반환한다.

```javascript
await client.eventsSubscribe(session);
const event = await client.nextNotification();
if (event.method === 'events/available') {
  const { session: eventSession, ids } = event.params;
}
```

알림 수신 자체는 배달 처리 완료를 뜻하지 않는다. `delivery.report.state`는 `queued`, `refused`, `unknown`만 허용하며 `received`는 서버에서 거부한다. 보고 결과의 `acknowledged`는 `false`이고 소비 ACK를 대체하지 않는다. `xsm_inbox`가 반환한 실제 메시지를 읽은 뒤 claim의 `token`을 `operation.call`의 `xsm_ack`, `{tokens: [token]}`으로 전달한다. 클라이언트는 자동으로 배달 상태를 보고하거나 ACK하지 않는다. 알림 큐는 제한이 없으므로 구독 후 지속적으로 소비한다. 여러 소비자가 있으면 알림 하나는 소비자 하나에게 전달된다.

## 오류와 프로세스 수명

- `RpcError`는 서버가 반환한 `code`, 메시지, `data`를 보존한다. 해당 요청만 실패하며 다른 요청은 계속할 수 있다.
- EOF, 손상된 JSON/UTF-8, 잘못된 RPC 응답, 프로세스/파이프 오류는 `TransportError`로 미완료 요청과 대기 중인 알림 소비자를 모두 실패시킨다. 이미 큐에 들어온 알림은 종료 후에도 먼저 읽을 수 있다. 초기 Python 프로세스 생성 실패는 표준 `OSError` 계열이다.
- stderr는 RPC로 해석하지 않고 계속 배출한다. 기본 출력은 호출자의 stderr다. Python `on_stderr=callback`, Node `onStderr: callback`으로 동기 문자열 소비자를 지정할 수 있다. UTF-8 문자가 청크 경계에서 나뉘어도 보존한다.
- `session.close`는 RPC 요청이며 프로세스를 끝내지 않는다. `close()`는 미완료 요청을 실패시키고 stdin을 닫는다. 프로세스가 종료하지 않으면 유예 시간 후 종료 신호, 다시 유예 시간 후 강제 종료를 보내고 회수한다. Python `close_timeout`은 초 단위, Node `closeTimeout`은 밀리초 단위이며 기본값은 각각 1초와 1000ms다. 반복 호출도 가능하다.
- transport 오류도 프로세스 정리를 시작한다. 최종 회수를 기다리려면 `close()`를 호출한다. 재연결·재시도는 자동 실행하지 않는다. 동일 작업을 중복 실행할지는 호출자가 결정한다.

두 구현 모두 `command`, `cwd`, `env` 연결 옵션으로 실행 환경을 지정할 수 있다. `env`를 생략하면 현재 환경을 상속하고, 지정하면 전달한 환경으로 대체한다. 세션을 여는 `cwd`와 프로세스 실행 옵션의 `cwd`는 각각 명시한다.

## 검증

저장소 루트에서 다음 명령을 실행한다. `/usr/bin/python3` 3.9.6을 사용해 Python 전체 검사와 Node 테스트의 Python 자식 프로세스를 검증한다. TypeScript 검사는 별도 컴파일 검사다.

```sh
PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 -W error -m unittest discover -s clients/tests -p 'test_*.py' -v
PYTHON=/usr/bin/python3 node --test clients/tests/test_*.mjs
tsc --noEmit --strict --module NodeNext --moduleResolution NodeNext --target ES2022 clients/tests/types.mts
```

역순 동시 응답, 모든 세션 메서드의 핸들 전달, 구독 응답 전 알림, UTF-8 분할과 큰 프레임, stderr 분리, RPC 오류 후 재사용, 잘못된 프레임·EOF·호스트 요청에 대한 일괄 실패, 초기화/프로세스 생성 실패, 정상 종료와 종료 신호를 무시하는 프로세스 회수를 검사한다. Python에서는 요청 취소 후 늦은 응답도 검사한다.

`echo_peer.py`는 전송 검사만을 위한 느슨한 피어이며 실제 서버의 인자 검증을 증명하지 않는다. [`test_python_protocol.py`](../../clients/tests/test_python_protocol.py)와 [`test_node_protocol.mjs`](../../clients/tests/test_node_protocol.mjs)는 실제 서버를 실행해 같은 저장소의 서로 다른 두 세션, `xsm_send`의 `wait: 0`, `events/available`, `xsm_inbox`의 메시지/claim, `xsm_ack` 후 정본의 `acknowledged` 상태와 빈 inbox를 검사한다. 세 가지 배달 보고가 ACK하지 않는 것, `received`와 `session.update.cwd`의 거부도 확인한다. 상태 파일은 임시 XSM_HOME 아래에만 저장되며 사용자 세션·원격·네이티브 런타임을 사용하지 않는다.

응답 ID 연결을 요청 순서에 따른 연결로 바꾸는 변이를 두 구현에 각각 메모리에서 적용했고, 역순 응답 검사의 단언이 실패하는 것을 확인했다. 원본 파일은 변형하지 않았다.

## 호스트 전용 사용자 질문 연결

`XsmHostClient`는 Python과 Node 양쪽에 있다. 이 객체는 설치된 호스트 확장의
UI 코드만 소유한다. 모델 도구에는 일반 `XsmClient`의 협업 작업만 노출한다.
호스트 클라이언트도 일반 `request("decision.response", ...)`는 차단한다.

1. 세션을 열 때 `capabilities`에 `user-decisions`를 명시한다.
2. 작업이 `waiting-for-user`를 반환하면 `decision/request` 알림을 받는다.
3. 런타임의 실제 사용자 UI에서 원문·선택지를 표시하고 답을 수집한다.
4. Python은 `respond_to_decision(event, displayed=실제_표시_원문,
   source_id=실제_질문별_응답_ID, answer=실제_답)`를 호출한다. Node는
   `respondToDecision(event, { displayed, sourceId, answer })`를 사용한다.
5. `answered` 뒤 원 작업과 인자를 그대로 다시 호출한다. 새 질문이나 새
   `decision_key`를 만들어 기존 거부·미확인 결과를 우회하지 않는다.

응답 콜백 시험은 UI 대신 명시적인 시험 호스트를 사용했다. 실제 사용자
표시·답 수집과 네이티브 런타임 인증이 끝났다는 의미는 아니다.
