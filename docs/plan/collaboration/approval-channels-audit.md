# xsm 승인 채널 감사

대상: `feat/team-communication`, HEAD 509133d (0.5.1). 읽기 전용 분석이다. 저장소 파일, `~/.xsm`, Codex·Claude 설정은 건드리지 않았고 전체 회귀도 돌리지 않았다.

## 결론

- 가장 큰 결함은 승인 강도 문제다. 답 하나가 그 세션의 열린 요청 전부에 붙어서, p1을 물은 AskUserQuestion의 "Yes" 하나로 p1·p2·p3가 모두 통과한다. 2026-10-31 관찰은 현재 코드에서 재현된다.
- Codex 쪽은 반대로 답이 사라진다. 요청 파일이 둘 이상이면(만료된 파일 포함) 답이 아무 데도 붙지 않고, 다시 물어야 한다.
- `consent.how()`가 Codex에 "말로만 물어라"라고 하는 것은 틀렸다. `request_user_input_async`는 `approval_policy=never`에서도 돌아간다. 다만 동기 `request_user_input`은 답이 기록되지 않는 통로이므로 도구 이름을 정확히 적어야 한다.
- Codex가 답 태그에 `UserPromptSubmit`을 실제로 발화하는지는 아직 확인되지 않았다. 로그에 남은 태그 기반 판정은 모두 훅이 아니라 대화 기록 재판독(`native-question-id`) 경로다. 0.5.2 문구는 이 확인을 먼저 해야 정해진다.
- 제안된 판별표는 네 군데가 틀렸다. "이미 정했는가" 단계가 없고, 권한과 결정 기록을 한 칸에 묶었고, "권한이면 폼"은 Codex never와 폼 없는 결정에서 막히고, "알기만 하면 질문 도구"는 열린 요청이 있으면 위험하다.

## 1. 심각도순 발견

표기: [검증]은 코드 읽기와 격리 실행 또는 로그로 확인했다는 뜻이고, [추정]은 코드에서 추론했을 뿐 실행하지 않았다는 뜻이다.

### 치명

**F1. 답 하나가 열린 요청 전부를 승인한다 [검증]**

- 위치: `xsm/consent.py:453-455`, `xsm/consent.py:516-551`, `xsm/consent.py:73-77`, `xsm/consent.py:96-102`, `docs/xsm/PROTOCOL.md:382`, `skills/xsm/references/permissions.md:92-93`
- 잘못 분류한 상황: 특정 요청에 대한 답을 "세션의 모든 요청에 대한 답"으로 다룬다.
- 지금 동작: `PostToolUse`는 `note_verdict(me, text)`를 요청 id 없이 부르므로 열린 파일마다 판정을 쓴다. 격리 시뮬레이션에서 질문이 `Join p1?`인 답 하나가 p1·p2·p3 모두에 `shown` 뒤 `go=True`를 냈다. 평문 "응"도 요청 둘을 모두 통과시켰다.
- `_spend`는 `recent.json`의 프롬프트만 소모한다. 다른 요청 파일에 이미 쓰인 판정은 그대로라서, 모듈 설명의 "Words approve once"가 이 경로에서는 지켜지지 않는다. AskUserQuestion 답은 프롬프트가 아니므로 `_spend`가 표시할 것도 없다.
- 유일한 가드는 에이전트가 원문을 읽고 판단하는 단계이고, 2026-10-31 관찰은 그 가드에 기대는 설계의 결과다.
- 해야 할 것: 답은 자기 질문의 요청에만 붙는다. 답이 어느 요청의 것인지 확정되지 않으면 어느 요청도 진행시키지 않고 에이전트에게 알린다. 코드 제안은 4절 C1.

**F2. Codex 답이 조용히 사라진다 [검증]**

- 위치: `xsm/consent.py:529-532`, `xsm/consent.py:469-477`
- 잘못 분류한 상황: "요청 id를 모르는 답"을 "어디에도 붙이면 안 되는 답"으로 처리하는데, `bind_question`을 부르는 것은 `--answer-request` 경로뿐이라 일반 경로에서 `question_request`는 항상 비어 있다.
- 지금 동작(시뮬레이션): 요청이 둘이면 태그 답이 어느 쪽에도 붙지 않는다. `len(pending)`은 `_fresh_pending` 전에 세므로 만료된 파일 하나만 있어도 살아 있는 요청의 답이 사라진다. 답은 `recent.json`에도 남지 않아(`record`가 `remember` 전에 반환) 사람이 다시 답해야 한다. 에이전트는 "needs your user's yes"만 다시 본다.
- 실제 표본: 10-23 11:19 답 뒤 11:20에 두 번, 10-28 08:14 답 뒤 08:15에 "needs your user's yes"가 다시 나왔다. 그 표본에서는 수정 전후 코드가 섞여 있고 그 시점의 열린 요청 수를 보지 못했으므로 원인 판정의 근거로 쓰지 않는다.
- 해야 할 것: 만료 파일을 세지 않고, 답이 붙지 못했으면 다음 실행에서 "답은 왔지만 어느 요청인지 정해지지 않았다"고 말하며, F1과 같은 결속 규칙을 쓴다. 승인을 추정해서 붙이지 않는다.

### 높음

**F3. Codex 훅 발화가 미확인인 채로 채널을 설명한다 [로그 확인, 결론은 미확인]**

- 위치: `xsm/consent.py:306-312`, `xsm/consent.py:466-475`, `docs/plan/collaboration/records/gates/G00-baseline.md:92`, `:168`
- G00이 "G02/P02가 실제 하네스에서 재현할 대상"으로 남겼고, 10월 로그 스캔에서 `question-id`나 `single-open-unbound` 표시가 붙은 실제 출력은 0건이다. 태그 답이 판정으로 보인 출력 2건은 모두 `native-question-id`다. 10-28 09:15의 G02 확인도 `user_answers.read_answer`로 대화 기록을 읽은 것이다.
- rollout에 훅 이벤트 행이 남지 않아 로그로는 가를 수 없다. `~/.xsm`은 읽지 않았다.
- 해야 할 것: 0.5.2 전에 실제 Codex에서 ask 하나를 열고 async 질문에 답한 뒤 `pending.json`에 판정이 생기는지 본다. 생기지 않으면 Codex의 정상 경로는 훅이 아니라 재판독이 되어야 하고, 지침도 그에 맞춰야 한다.

**F4. Codex에 말로만 묻게 한다 [검증]**

- 위치: `xsm/consent.py:1175-1179`, 호출처 `xsm/consent.py:1186`, `:1252`, `:1256`, `xsm/connect.py:191`
- 지금 동작: Claude 외 런타임에는 "in plain words"만 준다. 설명문의 "no other runtime's is"는 G02 수정 이후 틀린 문장이다.
- 근거: 10월 로그 305개 파일에서 `request_user_input_async` 호출 97건 전부가 `approval_policy=never`였다. 파싱 오류 12건을 뺀 85건이 `{"accepted": true}`를 받았고, 태그 답 43건이 전부 `ANSWER_RE`와 일치했다. 같은 조건에서 폼은 보이지 않고 거절된다.
- 해야 할 것: `how("codex")`가 async 도구를 안내한다. 단, F3 확인 뒤에 문구를 정한다.

**F5. 같은 이름의 두 도구가 답을 다르게 돌려준다 [검증]**

- 위치: `xsm/install.py:55-56`, `hooks/codex-hooks.json`, `skills/xsm/references/workers.md:55`, 지침 전체
- 동기 `request_user_input`은 답이 `function_call_output`의 `{"answers": {...}}`로 온다. 태그가 없고 xsm은 Codex `PostToolUse`를 설치하지 않으므로 기록되지 않는다. 호출 45건 중 44건이 Plan 모드였고 Default 모드 1건은 `request_user_input is unavailable in Default mode`로 실패했다.
- 인자 형식도 다르다. async는 `questions[].title`·`options`(문자열 배열)이고 동기는 `question`·`header`·`id`·`options`다. async 호출 97건 중 12건이 `unknown field question`으로 실패했다.
- 충돌: Codex의 Default 모드 지시문에 "Never use the `request_user_input` tool for permission requests or permission-related escalations."가 있다(개발자 메시지 표본에 288회). 반면 async 도구 설명은 "clarification, or approval"을 허용한다. 지시문이 async에도 적용되는지는 Codex 쪽 문서로 확인하지 못했다.
- 해야 할 것: 지침은 `request_user_input_async`만 이름으로 적고, 인자 형식을 적고, Plan 모드에서는 말로 묻게 한다. "질문 도구"라는 일반어를 Codex에 쓰지 않는다.

**F6. 사람이 없는 워커에게 "사용자에게 물어라"라고 한다 [코드 검증, 멈춤은 추정]**

- 위치: `xsm/consent.py:1261-1271`, `xsm/consent.py:1053`, `xsm/mcp.py:1391-1411`, `xsm/mcp.py:574`, `xsm/workers.py:97`
- CLI: 워커는 판정을 보관하지 않으므로 `cannot_keep`이 "MCP 도구가 있으면 쓰라: 양식으로 묻는다"고 안내한다. 양식은 아무도 보지 않는 tmux 창에 뜬다.
- 백그라운드 Claude 워커: `CLAUDE_WORKER_MCP`는 `xsm_send`·`xsm_inbox`뿐이라 다른 도구는 먼저 PermissionRequest로 부모에게 간다. 부모가 허용하면 양식이 숨은 창에 뜨고, `ask_client`의 대기 루프에는 시간 제한이 없다 [추정].
- 백그라운드 Codex 워커: `-a never`라 폼이 거절되고 `in_words`가 "Ask your user now"를 돌려준다. MCP 서버 환경에 `XSM_WORKER`가 없으면 `consent.ask`도 통과해 사람 없는 요청이 생긴다 [추정].
- 해야 할 것: 워커에는 "부모(팀이면 lead)에게 DM으로 올려라"를 돌려주고 폼을 보내지 않는다. 판별은 MCP 쪽에서도 되어야 한다(워커 기록 조회). 승인을 대신할 경로를 여는 것이 아니라 사람에게 가는 길을 고치는 것이다.

**F7. `xsm_decide`는 Codex never에서 막다른 길이고 안내가 서로 어긋난다 [코드 검증]**

- 위치: `xsm/mcp.py:1273-1279`, `xsm/mcp.py:1325-1327`, `xsm/mcp.py:547-552`, `skills/xsm/references/troubleshooting.md:51`, `skills/xsm/SKILL.md:87`, `skills/xsm/references/permissions.md:67`, `skills/xsm/references/teams.md:81-89`
- 팀 승인은 lead의 `xsm_decide`로 간다. lead가 Codex never면 폼이 보이지 않고 기록이 남지 않는다.
- 결과 문구는 "call xsm_decide again"이고 스킬은 "do not call it again"이다. 같은 인자로 다시 부르면 `decisions.begin`이 같은 키를 찾아 저장된 거절·닫힘을 그대로 돌려주므로 폼이 다시 뜨지 않는다. `decision_key`를 바꾸라는 말은 결과 문구에 없다.
- 실제로는 `answer_request`와 `original_question`을 주면 async 답으로 기록할 수 있다(`xsm/mcp.py:529-546`). 그러나 이 인자는 스키마 설명이 없고 어떤 지침에도 없으며, 기록의 `via`는 `mcp-elicitation`으로 남는다(`xsm/mcp.py:1337`). 출처는 `native-user`인데 기록이 다르게 말한다.
- ADR-0005 결정 4-4는 "에이전트가 기록하는 결정은 MCP로 통일, AskUserQuestion 인용 방식은 쓰지 않는다"이다. 이 재판독 경로를 정식화할지는 사용자 결정이다. 정식화하지 않으면 경로를 막아야 한다.

**F8. 샌드박스 Codex는 link·join·reach·grant·approve·team·handover를 끝내지 못한다 [코드 검증, 실행 안 함]**

- 위치: `xsm/mcp.py:1391-1411`, `xsm/consent.py:1042-1043`, `xsm/consent.py:651`
- never에서 폼이 거절되면 안내는 셸 명령이다. 샌드박스 셸은 `~/.xsm`에 쓰지 못해 `_take`의 쓰기가 `OSError`가 되고 `cannot_keep`으로 떨어지며, 그 문구는 다시 MCP 도구를 쓰라고 한다. 순환이다.
- `xsm_connect`·`xsm_publish`는 서버 안에서 `take_or_request`를 부르므로 이 문제가 없다. 폼 도구만 판정을 서버에서 읽지 않는다.
- 사용자의 Codex 홈은 `danger-full-access`라 실제로 겪지 않았을 수 있다(G00 기록).
- 해야 할 것: 폼이 답을 못 받았을 때 MCP 도구가 같은 키로 판정을 읽는다. 두 단계(보여 주고 다음 호출에서 진행)는 그대로 둔다.

### 중간

**F9. Claude 백그라운드 작업은 잘못된 해결책을 안내받는다 [코드 검증]**

- 위치: `CHANGELOG.md:57`, `docs/xsm/TESTPLAN.md:734`, `xsm/consent.py:1261-1271`, `xsm/registry.py:1128`
- 등록이 없으면 CLI는 "MCP 도구를 쓰라"고 하고 MCP는 `Server.call`에서 거부하며 "send any message in the session first"라고 한다. 메시지를 보내도 풀리지 않는다. `Server.call` 입구에서 막히므로 변경 기록의 "사람 답이 필요한 도구"보다 범위가 넓다.
- Claude Code 문서는 백그라운드 세션이 질문을 peek 패널에서, 권한과 MCP 입력은 attach해서 받는다고 적는다. 막히는 원인은 런타임이 아니라 xsm 등록이다 [문서 확인, 실제 실행 안 함].

**F10. 요청보다 먼저 쓴 질문 도구는 버려진다 [검증]**

- 위치: `xsm/consent.py:450-456`, `xsm/consent.py:716-746`, `docs/xsm/PROTOCOL.md:376`, `:383`
- 평문으로 먼저 받은 답은 `recent.json`에 남아 `--reply`로 쓸 수 있는데, 질문 도구의 답은 남지 않는다. 시뮬레이션에서 답 뒤 첫 실행은 답을 보지 못하고 `--reply`는 무시됐다. 두 런타임이 같다.
- 사람이 같은 것을 두 번 답하게 된다. 지침에 순서 경고가 없다.
- 해야 할 것: 답을 `recent.json`에 "질문과 함께" 남기되 소비 규칙은 같게 하거나, 최소한 "먼저 명령을 실행해 요청을 만들고 그다음 질문 도구로 물어라"를 적는다.

**F11. 비동기 답과 시간 창이 맞지 않는다 [검증]**

- 위치: `xsm/consent.py:118-122`, `xsm/consent.py:912-914`
- 호출과 답을 짝지을 수 있는 41건 중 지연 중앙값은 194초, 600초 초과 10건, `ASK_MAX`(1800초) 초과 1건(2039초)이다. 그 1건 같은 경우 요청이 이미 사라져 답이 붙을 곳이 없고 알림도 없다.
- `ASK_MAX` 자체를 늘리자는 뜻은 아니다. 묵은 답을 막는 근거가 있다. 답이 늦어 만료됐다는 사실을 에이전트에게 알려야 한다.
- `SHOW_DELAY`는 영향이 없다. 답이 1초 안에 온 경우는 0건이고, 이 값은 표시와 다음 실행 사이의 간격이다.

**F12. 다른 길로 끝난 요청이 열린 채 남는다 [코드 검증]**

- 위치: `xsm/consent.py:1274-1302`, `xsm/mcp.py:1391-1411`
- CLI 거부로 요청이 생긴 뒤 폼이나 입력 동의로 끝나면 요청 파일을 지우지 않는다. 남은 요청은 최대 30분 동안 이후의 말을 판정으로 받고 F1의 대상을 늘린다. 에이전트가 열린 요청을 볼 방법도 없다(`xsm_decision_status`는 폼 기록만 다룬다).

**F13. 여러 질문의 처리가 런타임마다 다르고 지침이 없다 [검증, 한 부분 미확인]**

- 위치: `xsm/consent.py:333-337`, `xsm/consent.py:469-477`, `xsm/consent.py:437-442`, `xsm/user_answers.py:114-115`
- Codex는 id가 둘 이상이면 소리 없이 버린다. 에이전트는 이유를 듣지 못한다. Claude는 시뮬레이션에서 `Join v1? -> No; Run tests? -> Yes`처럼 한 판정으로 합친다.
- 질문 하나만 쓰라는 지침은 어디에도 없다. 코드가 거부하는 것을 지침이 예고하지 않는다.
- 미확인: 로그에 async 다중 질문 호출 3건이 있지만 답이 0건이다. 실제로 한 메시지에 배열로 오는지, 질문마다 따로 오는지 모른다. 따로 온다면 단일 id 답으로 통과하고 거부 규칙은 작동하지 않는다. 시험 픽스처의 배열 형식은 실측이 아니다.

**F14. 재판독 경로의 조건이 지침에 없고 일부 결정에서는 성립하지 않는다 [검증]**

- 위치: `xsm/consent.py:917-931`, `xsm/mcp.py:133`, `:140`, `:334-335`, `xsm/instructions.py:120-122`, `xsm/cli.py:3210-3218`
- 태그의 `question`은 `title`과 항상 같지 않다. 41건 중 4건이 달랐고 모두 긴 제목(233~402자)에서 228~299자로 바뀌었다. `original_question`과 폼 문구의 완전 일치는 긴 문구에서 실패한다. 변형 규칙은 확인하지 못했다.
- `_mentions`는 질문에 대상이 들어 있어야 한다. `grant`의 대상은 `runtime:path:options`, `endorse`는 digest라 사람에게 묻는 문장에 들어가지 않는다. 이 둘에서 `--answer-request`는 사실상 쓸 수 없다. `ASKING` 목록은 이들을 포함한다.
- `link`·`reach`는 질문에 절대 경로나 `~` 경로가 있어야 맞는다. 지침에 없다.

**F15. `connect`와 `publish`의 거부 문구에 묻는 법이 없다 [검증]**

- 위치: `xsm/connect.py:257-258`, `:319-320`, `:351`, `xsm/mcp.py:129-142`
- `asks()`를 거치지 않아 몇 번 실행해야 하는지, 어떤 도구로 물을지 말하지 않는다. 판별표로는 "권한이니 폼"인데 이 둘에는 폼이 아예 없다.

### 낮음

**F16. Codex에 PermissionRequest가 없다는 설명이 낡았다 [검증]**

- 위치: `xsm/install.py:52-55`, `xsm/workers.py:93-94`, `docs/xsm/PROTOCOL.md:415`, `:421`, `skills/xsm/references/workers.md:36`
- `xsm/install.py:1436`이 이미 `permission_request`를 알고, 0.165 바이너리에 `hooks/src/events/permission_request.rs`가 있다. 다만 `-a never`에서는 요청 자체가 일어나지 않는다. 백그라운드 Codex 워커를 사람에게 잇는 일은 정책 변경이므로 문구 수정과 별개로 사용자가 정한다.

**F17. 워커의 AskUserQuestion이 권한 요청으로 중계될 수 있다 [추정]**

- 위치: `xsm/workers.py:940-948`, `xsm/workers.py:1002-1005`
- `permission_request`는 도구를 가리지 않는다. 문서는 AskUserQuestion에 allow만 돌려주는 것으로는 부족하고 `answers`가 필요하다고 적는다(PreToolUse 절). 이 도구가 PermissionRequest를 일으키는지는 실행해 보지 않았다.

**F18. 플러그인 홈에서 워커 훅이 두 번 돌 수 있다 [추정]**

- 위치: `hooks/hooks.json:48-58`, `xsm/workers.py:404-406`
- 플러그인 훅과 `--settings` 훅이 합쳐지면 한 요청이 승인 파일 둘이 된다. 메시지에는 중복 제거가 있으나 `permission_request`에는 없다. 사용자 Claude 홈은 직접 설치라 겪지 않았을 수 있다.

**F19. "사람만 고를 수 있다"는 주석이 정확하지 않다 [문서 확인]**

- 위치: `xsm/consent.py:451-452`
- Claude Code 문서상 `PreToolUse` 훅이나 SDK 콜백이 AskUserQuestion에 답할 수 있다. `permissions.md`는 폼에 대해서만 같은 한계를 적는다. 신뢰 경계(uid) 안의 일이므로 문구 문제다.

## 2. 런타임 × 결정 표

칸의 순서가 실제로 시도되는 순서다. "답"은 판정 경로(질문 도구나 말 → 훅 기록 → 재실행 두 번)를 뜻한다. [막힘]은 그 칸에서 결정이 끝나지 않는다는 뜻이다.

- Claude: 대화형 Claude Code. `/xsm` 입력, 폼 표시, AskUserQuestion이 된다.
- Codex 표시: 폼이 보이는 Codex TUI(`on-request` 등). 폼 표시는 소스 주석 근거이고 사용자 홈이 전부 never라 직접 확인하지 않았다.
- Codex never: `approval_policy=never`. 폼은 보이지 않고 거절된다. 셸이 `~/.xsm`에 쓸 수 있다고 가정했다. 샌드박스면 답을 쓰는 칸은 F8로 막힌다.
- 워커 칸은 백그라운드 워커다. 패널 워커는 사람이 그 패널에서 답한다.

| 결정 | Claude | Codex 표시 | Codex never | Claude 워커 | Codex 워커 | Claude 백그라운드 작업 |
|---|---|---|---|---|---|---|
| link | 입력 → 요청문 → 폼 → 답 | 입력 → 요청문 → 폼 → 답(async) | 입력 → 요청문 → 폼 거절 → 셸로 답(async) | [막힘] F6 | [막힘] F6 | [막힘] F9 |
| join, leave | 위와 같다 | 위와 같다 | 위와 같다 | [막힘] F6 | [막힘] F6 | [막힘] F9 |
| reach | 위와 같다 | 위와 같다 | 위와 같다 | [막힘] F6 | [막힘] F6 | [막힘] F9 |
| grant | 폼 → `spawn`/`remote add` 재실행으로 답 | 같다 | 폼 거절 → 셸로 답 | [막힘] 부모가 해야 함 | [막힘] 같음 | [막힘] F9 |
| approve (워커 요청) | 폼(부모) → `xsm approve`로 답 | 같다 | 폼 거절 → 셸로 답 | 요청자: PermissionRequest가 부모로 중계 | 요청 없음: `-a never`로 거부 | 부모가 되면 [막힘] F9 |
| team add (사용자 몫) | 폼 → 답 | 같다 | 폼 거절 → 셸로 답 | lead에게 DM이어야 하나 안내 없음 F6 | 같음 | [막힘] F9 |
| team lead | 폼 → 답 | 같다 | 폼 거절 → 셸로 답 | 같음 | 같음 | [막힘] F9 |
| handover | 폼 → 답 | 같다 | 폼 거절 → 셸로 답 | [막힘] F6 | [막힘] F6 | [막힘] 0.5.1 시험 14-11 |
| decide | 폼만. 답 경로 없음 | 폼만 | [막힘] 기록 불가. 문서 없는 `answer_request`만 가능 F7 | [막힘] lead에게 DM | [막힘] 같음 | [막힘] F9 |
| doc endorse | 폼 → `doc add --tag endorsed`로 답 | 같다 | 폼 거절 → 셸로 답 | [막힘] F6 | [막힘] F6 | [막힘] F9 |
| publish | 답만. 폼 없음 F15 | 같다 | 답만. MCP 서버 안에서 읽으므로 샌드박스도 됨 | [막힘] 사람 없음 | [막힘] 같음 | [막힘] F9 |
| connect (선택) | 답만 F15 | 같다 | 답만, 샌드박스도 됨 | [막힘] 사람 없음 | [막힘] 같음 | [막힘] F9 |
| held deliver | 답만. 폼 없음 | 같다 | 셸로 답. 샌드박스면 [막힘] | 판정 보관 안 됨 [막힘] | 같음 | [막힘] F9 |
| spawn (보통) | 사람 몫 아님 | 같다 | 같다 | `max_depth` 안에서 가능 | 같음 | 등록이 없으면 부모 관계가 없음(미확인) |
| spawn (위험 옵션, 범위 밖) | grant와 같다 | 같다 | 폼 거절 → 셸로 답 | 부모가 해야 함 | 같음 | [막힘] F9 |

런타임별로 실제로 보일 수 있는 것:

| 런타임 | PermissionRequest | 질문 도구 | MCP 폼 | 비고 |
|---|---|---|---|---|
| Claude Code 대화형 | 런타임 프롬프트. xsm 훅은 워커가 아니면 침묵 | AskUserQuestion, 훅 기록 | 표시 | 입력 동의는 `UserPromptExpansion` |
| Codex TUI | xsm 훅 없음. 런타임 자체 승인 | async는 태그로 답, 동기는 Plan 모드만이고 기록 안 됨 | 정책에 따름 | 입력 동의는 `UserPromptSubmit` |
| Codex never | 요청 자체가 없음 | async 동작(97건 전부 never) | 보이지 않고 거절 | 태그 답의 훅 발화 미확인 F3 |
| Claude 백그라운드 워커 | 훅이 부모로 중계, 600초 뒤 거부 | 숨은 창, 중계 없음 | 숨은 창, 시간 제한 없음 | 판정 보관 안 함 |
| Codex 백그라운드 워커 | 없음 | 숨은 창. `accepted`만 돌아옴 [추정] | 거절 | `codex exec`가 아니라 TUI로 뜸 |
| Claude 백그라운드 작업 | 문서상 attach로 답 | 문서상 peek로 답 | 문서상 attach로 답 | xsm 등록이 없어 모두 무의미 |

## 3. 판별표 교정

제안: 런타임이 막았으면 PermissionRequest, 답이 권한이나 기록의 근거면 MCP 폼, 아니면 훅이 기록하는 질문 도구, 알기만 하면 되면 질문 도구, 아니면 말.

틀린 곳:

1. **첫 단계가 빠졌다.** 사람이 이미 정했는지부터 봐야 한다. 입력한 명령(`consent.take`), 사람의 요청(`_from_request`), 터미널의 사람(`human_terminal`)은 어떤 채널도 쓰지 않는다. 이 단계가 없으면 2026-10-01에 사용자가 거부한 핑퐁이 돌아온다. 채널은 넷이 아니라 이 셋에 `--reply`와 `xsm board decide`까지 더 있다.
2. **PermissionRequest는 에이전트가 고르는 채널이 아니다.** xsm이 답하는 경우는 백그라운드 Claude 워커뿐이다. 보통 세션에서 훅은 침묵하고, 부모 쪽의 `xsm_approve`는 폼이다. auto 모드가 `xsm_grant`를 막은 경우도 "런타임이 막은 것"이지만 올바른 길은 질문 도구로 물은 뒤 재호출이다(`workers.md:54-62`, TESTPLAN 10-13 실측). Codex에서는 xsm 경로가 없다.
3. **"권한이면 폼"은 세 곳에서 틀린다.** 코드는 판정도 폼과 같은 권한 근거로 쓴다. Codex never에서는 폼이 보이지 않으므로 폼을 고집하면 막힌다. 그리고 publish, connect, unblock, held deliver, attempts clear, frameworks ignore에는 폼이 없다.
4. **"권한"과 "기록"은 다른 칸이다.** 권한은 폼과 답 둘 다 된다. 사람 명의 문서 노드(endorse)도 답이 된다(`_decided_by_reply`). 결정 기록(`xsm_decide`)은 폼과 터미널만 된다(ADR-0005, PROTOCOL 5.14). 권한은 끝나면 사라지지만 결정 기록은 나중에 "사용자가 정했다"는 증거로 읽히기 때문이다.
5. **"훅이 기록하는 질문 도구"에는 조건이 있다.** AskUserQuestion과 `request_user_input_async`만 해당하고, 요청이 먼저 있어야 하고, 질문은 하나여야 하고, Codex 훅 발화는 확인되지 않았다. 동기 `request_user_input`은 해당하지 않는다.
6. **"알기만 하면 질문 도구"는 열린 요청이 있으면 위험하다.** 그 답도 판정이 된다(시뮬레이션 C에서 무관한 질문의 답이 열린 요청에 `single-open-unbound`로 붙었다). 평문도 판정이 되므로 "아니면 말"이 더 약한 채널인 것도 아니다.
7. **"사람이 있는가"라는 축이 없다.** 워커의 사람은 부모이고 팀 구성원의 창구는 lead다. 피어는 사람이 아니다.

교정안(순서대로 처음 맞는 것):

1. 사람이 이미 정했으면(입력, 요청, 터미널) 아무것도 묻지 않고 실행한다. 명령이 판단한다.
2. 이 세션에 사람이 없으면(워커) 부모나 lead에게 DM으로 올린다. 폼과 질문 도구를 쓰지 않는다.
3. 런타임이 내 도구 호출을 사람에게 묻고 있으면 런타임에 맡긴다. 내가 띄운 워커가 기다리면 `xsm_approve`를 부른다. 분류기가 xsm 도구를 막았으면 질문 도구로 묻고 다시 부른다.
4. 남는 것이 결정 기록이면 폼만 쓴다. 폼이 닿지 않으면 기록되지 않는다고 사람에게 말한다. Codex 재판독 경로를 인정할지는 사용자 결정이다(F7).
5. 남는 것이 권한이면 폼 도구가 있고 보이는 런타임에서 폼을 쓴다. 폼이 없거나 보이지 않으면 먼저 명령을 실행해 요청을 만든 뒤, Claude는 AskUserQuestion, Codex는 `request_user_input_async`(Plan 모드는 말)로 그 결정 하나만 묻고, 두 번 재실행한다.
6. 알기만 하면 되는 질문은 열린 요청이 없을 때 질문 도구나 말로 묻는다. 열린 요청이 있으면 그것을 먼저 끝낸다. F1이 고쳐지면 이 조건은 풀 수 있다.

## 4. 0.5.2 변경 목록

고치지 않았다. 코드와 시험이 먼저이고 문구는 F3 확인 뒤다.

### 코드

- C1. 판정 결속. `asks()`와 `in_words()`가 요청마다 짧은 표식을 주고 질문에 넣게 한다. 훅은 질문 원문(AskUserQuestion의 `answers` 키, 태그의 `question`)에서 표식이나 대상을 찾아 그 요청에만 붙인다. 찾지 못하면 어느 요청도 진행시키지 않고 "어느 요청의 답인지 정해지지 않았다"를 보여 준다. 평문은 원문에 질문이 없으므로 열린 요청이 하나일 때만 붙이는 안을 사용자 결정으로 올린다. `_take`는 같은 말이 다른 요청에서 이미 쓰였으면 진행하지 않는다.
- C2. `note_verdict`의 `len(pending)`을 유효한 요청 수로 바꾼다(`xsm/consent.py:520`, `:531`).
- C3. 태그 답이 어디에도 붙지 않았을 때 질문·답·id를 보관해 다음 실행에서 보여 준다. 승인으로 쓰지 않는다.
- C4. 다중 질문을 버릴 때 다음 실행의 거부문에 이유를 적는다(`xsm/consent.py:476-477`). Claude 다중 질문도 같은 규칙으로 맞출지 정한다.
- C5. `how()`를 런타임별로 바꾸고 설명을 고친다. 관련 시험 `tests/test_person_decisions.py:789`, `:1005`를 함께 고친다.
- C6. 폼 도구가 답 없음으로 끝날 때 MCP 안에서 판정을 읽게 한다(F8). 두 단계는 유지한다.
- C7. 폼이나 입력 동의로 끝난 결정의 열린 요청을 지운다(F12). 열린 요청을 보여 주는 읽기 전용 경로를 둔다.
- C8. 워커 판별을 MCP와 `cannot_keep`에 넣고 안내를 부모나 lead로 바꾼다(F6).
- C9. `unregistered_reason`과 `cannot_keep`이 백그라운드 작업을 구별해 "여기서는 결정할 수 없다"고 말하게 한다(F9). 등록 자체는 별도 과제다.
- C10. 요청 만료를 이유로 답이 버려지면 알린다(F11).
- C11. `connect`·`publish` 거부문을 `asks()`로 통일한다(F15).
- C12. `xsm_decide` 결과의 `call xsm_decide again`을 없애거나 `decision_key` 안내로 바꾼다. 재판독으로 기록되면 `via`를 `native-user`로 남긴다(사용자 결정 뒤).
- C13. `answer_request`·`original_question` 스키마에 설명을 넣는다. 안 쓸 도구에서는 뺀다(F14).
- C14. 필요하면 Codex `PostToolUse` 훅으로 동기 도구 답을 기록할지 조사한다. 훅 신뢰가 풀리므로 사용자 판단이 필요하다.

### 문구

| 위치 | 지금 | 바꿀 내용 |
|---|---|---|
| `xsm/consent.py:27-53` | Claude 질문 도구만 설명 | Codex async와 태그, 결속 규칙 추가 |
| `xsm/consent.py:775-778` | "Ask them in plain words" | 런타임별 `how()` 사용 |
| `xsm/consent.py:1175-1179` | Codex는 말로만 | 위 C5 |
| `xsm/consent.py:628-631` `OLD_HOOK` | MCP 폼 도구 안내 | 폼이 안 보이는 런타임 처리 추가 |
| `xsm/mcp.py:1279`, `:1326` | 말로 묻고 다시 호출 | 기록되지 않음을 명시, 재호출 문구 정리 |
| `xsm/workers.py:1095`, `xsm/bounce.py:100`, `xsm/cli.py:411` | "in plain words" | `how()` 사용 |
| `xsm/mcp.py:129-142`, `:251-300` 설명 | "asks with a form"만 | 폼이 안 될 때의 길 한 문장, publish·connect는 답 경로 명시 |
| `xsm/instructions.py:120-122`, `skills/xsm/references/messaging.md` | 인자 이름 없음 | `--answer-request`, `--question`, `answer_request`, `original_question`과 조건 |
| `skills/xsm/SKILL.md:62` | "Claude Code only: or AskUserQuestion" | 런타임별 도구, 요청 먼저, 질문 하나 |
| `skills/xsm/SKILL.md:86-87` | "pass the result on as it is" | 결과가 지시하는 대로 하라와 일치시킴 |
| `skills/xsm/references/permissions.md:65`, `:72-76`, `:117`, `:123` | Claude 전용 문구 | async 추가. 인자는 `title`과 `options` |
| `skills/xsm/references/permissions.md:92-93` | 답이 모든 요청에 붙는다 | C1에 맞춤 |
| `skills/xsm/references/sessions.md:37`, `:176` | "in plain words" | 같은 문구 |
| `skills/xsm/references/troubleshooting.md:44`, `:48`, `:51`, `:110` | Claude 행만 있음 | Codex 행 추가: 답이 안 보일 때, 동기 도구, 다중 질문 |
| `skills/xsm/references/workers.md:36`, `:55-62` | "your question tool" | 런타임별 이름. 워커는 부모로 올린다는 절 추가 |
| `skills/xsm/references/teams.md:34`, `:81-89` | 폼 전제 | lead가 Codex never일 때의 처리 |
| `hooks/hooks.json`, `hooks/codex-hooks.json` 설명 | Codex 답 언급 없음 | 맞춤 |

### 문서

| 위치 | 문제 |
|---|---|
| `docs/xsm/PROTOCOL.md:366-387` | Codex 질문 도구, 태그, `--answer-request`, 재판독, 다중 질문 거부를 전혀 다루지 않는다 |
| `docs/xsm/PROTOCOL.md:377` | `post --tag decision`이 목록에 있으나 `ASKING`에 `post`가 없다. team, handover, publish, connect, held가 빠졌다 |
| `docs/xsm/PROTOCOL.md:378` | "밑줄이 든 태그는 하니스 텍스트"라고만 적어 답 태그 예외가 없다 |
| `docs/xsm/PROTOCOL.md:382` | "모든 요청에 쓴다"는 AskUserQuestion과 평문에만 맞고 Codex 태그에는 틀리다 |
| `docs/xsm/PROTOCOL.md:386` | `decide`가 "명령을 먼저 실행"한다고 적었으나 셸 경로가 없다 |
| `docs/xsm/PROTOCOL.md:415`, `:421` | Codex 훅 없음 설명이 낡았다(F16) |
| `docs/xsm/PROTOCOL.md:501`, `docs/xsm/README.md:337` | 기록 경로가 둘뿐이라는 설명과 재판독 경로가 어긋난다(F7) |
| `docs/xsm/README.md:422` | "`xsm approve`는 터미널에서만 동작한다"는 틀렸다. `xsm/cli.py:2667-2688`이 답 경로를 연다 |
| `docs/xsm/README.md:457` | "터미널에서 칠 명령"은 2026-10-01 결정과 맞지 않는다. 에이전트가 실행한다. async 대안이 없다 |
| `docs/xsm/README.md` 전체 | 질문 도구 언급은 420행 한 곳뿐이고 Codex 도구 이름이 없다 |

## 5. 검증한 것과 추정한 것

검증:

- 코드 경로: `consent.py` 전체, `mcp.py`의 폼·ask_client·스키마, `decisions.py`, `cli.py`의 묻는 경로, `workers.py`의 승인과 grant, `connect.py`, `user_answers.py`, `install.py`와 훅 파일.
- 격리 시뮬레이션: 스크래치패드의 임시 `XSM_HOME`에서 `consent.record`와 `take_or_request`를 현재 코드로 직접 호출했다. 사례 A~H의 결과를 위 F1, F2, F10, F13에 적었다. 2026-10-31 관찰의 원본 파일은 읽지 않았고 같은 현상을 재현했을 뿐이다.
- 태그 형식: `~/.codex`, `-2`, `-3`의 2026년 10월 rollout 305개, Codex 0.159~0.165. 사용자 메시지 전체가 태그인 43건 모두 `ANSWER_RE`와 일치했고 항목은 1개, 키는 `answer`·`question`·`questionItemId`, id는 `["request_user_input_async","call_…",0]` 꼴의 JSON 문자열이다. `answer_reply`는 현재 형식과 맞다. 태그를 인용만 한 사용자 메시지 4건은 일치하지 않는 것이 옳다.
- 호출 수: async 97건(인자 오류 12, 수락 85, 짝지어진 답 41), 동기 45건(답 39, 취소 5, Default 모드 실패 1). 수락된 85건 중 44건은 짝지어진 태그 답이 없다. 사람이 평문으로 답했는지는 나누지 않았다.
- Codex 0.165 바이너리 문자열: async 도구 설명, `request_user_input is not supported in exec mode`, `can only be used by the root thread`, 태그 문자열, Default 모드 지시문.
- Claude Code 문서: hooks, agent view(Jina로 조회). Claude Code 2.1.314.

확인하지 못한 것:

- Codex가 태그 메시지에 `UserPromptSubmit`을 발화하는지(F3).
- async 다중 질문 답의 실제 형식(F13). 태그 `question`이 `title`과 달라지는 규칙(F14).
- Default 모드의 "Never use … for permission" 지시문이 async에도 적용되는지(F5).
- 폼이 보이는 Codex 정책에서의 동작. 사용자 홈이 전부 never다.
- 백그라운드 워커에서 양식이나 질문이 뜰 때의 실제 동작(F6, F17), 플러그인 홈의 이중 훅(F18), 샌드박스 경로의 실제 실행(F8).
- Claude 백그라운드 작업에서 xsm이 왜 찾지 못하는지. 이번 범위에서 원인을 파지 않았다. 맥미니의 로그도 보지 않았다.
- `answers_text`가 전제한 AskUserQuestion 결과 형식이 Claude Code 2.1.314에서도 같은지. PROTOCOL은 2.1.286 기준이고 Claude 대화 기록은 읽지 않았다.

작업 중 `git status`에 `docs/plan/collaboration/completion-ledger.*`, `scripts/audit-collaboration-plan.py`, `deliverables/ledger-rebind-0.5.1/` 변경이 나타났다. 이 감사가 만든 것이 아니다. 다른 에이전트의 작업으로 보이지만 확인하지는 않았다.

## 6. 처리 결과 (이슈 #25)

실측과 시험은 [TESTPLAN 15절](../../xsm/TESTPLAN.md#15-승인-결속-25)에 있다.

| 항목 | 처리 |
|---|---|
| F1 | 답은 질문이 지목한 결정에만 붙는다. `--reply`와 요청 경로도 `bound_to`, `ambiguous`로 막는다 |
| F2 | 만료 요청을 세지 않고, 붙지 못한 답은 다음 실행에 알린다 |
| F3 | 확인됨. 직접 응답한 태그에 `UserPromptSubmit`이 발화한다 |
| F4, F5 | `how()`가 `request_user_input_async`와 인자를 적고 동기 도구를 금지한다. Default 모드 지시문이 있는 세션에서도 모델이 권한 질문에 async를 썼다(표본 1건) |
| F6 | 워커 기록으로 판별해 양식 없이 부모·lead로 안내한다. 실제 Codex 워커에서 확인했다. Codex 신뢰 화면 감지 실패로 워커가 죽던 결함도 고쳤다 |
| F7 | 재판독을 인정하고 `via: native-user`로 기록한다(사용자 결정, ADR-0005 4-4 개정) |
| F8 | 같은 MCP 도구에서 답을 읽는다. 도구 주석이 없어 Codex가 호출 자체를 거부하던 첫 관문도 고쳤다 |
| F9 | 등록은 범위 밖. 새로 시작한 작업은 등록된다(실측). 대화 중 넘어간 세션은 등록을 잃을 수 있다고 안내한다. 프로세스 판별은 하지 않고 조건문으로 쓴다 |
| F10 | 질문이 대상을 지목했으면 요청 뒤에 한 번 쓴다 |
| F11 | 만료 뒤 도착한 답을 구분해 알린다. `ASK_MAX`는 그대로다 |
| F12 | 끝난 결정의 요청을 닫고 그 말을 소모한다. `--pending-consent`, `--drop-consent` |
| F13 | 질문별로 결속한다. 실제 형식은 질문마다 태그 하나다 |
| F14 | 표식이 있으면 `grant`, `endorse`도 재판독이 된다. `xsm_decide`만 원문 완전 일치 |
| F15 | `connect`, `publish` 거부문을 `asks()`로 통일했다 |
| F16 | 문구 수정. 백그라운드 Codex 워커는 `-a never` 유지(사용자 결정) |
| F17 | 백그라운드 워커의 AskUserQuestion은 즉시 거부하고 안내한다 |
| F18 | 네이티브 호출 id로 승인 요청을 합친다 |
| F19 | 주석 수정 |

C14(Codex `PostToolUse` 훅)는 사용자 결정으로 하지 않았다. 훅 해시가 바뀌면 모든 홈의 신뢰가 풀린다.
