# xsm (Cross-Session Messaging)

[English](README.md) | 한국어

> **All you need is a message channel. The rest is done by agents.**
> 필요한 것은 메시지 채널 하나뿐입니다. 나머지는 에이전트가 합니다.

xsm은 이미 쓰고 있는 Claude Code와 Codex 세션이 서로를 찾아 함께 일하게 합니다. 한 머신 안에서, 설정 홈과
런타임이 달라도, 그리고 사용자의 다른 머신 사이에서도 그렇습니다. 에이전트는 하는 일로 상대를 찾고, 사용자가
고른 상대와 연결하고, 질문을 보내 실제 답을 돌려받습니다. 단계마다 무엇이 일어났고 무엇이 아직인지도 알려 줍니다.

![XSM이 런타임의 네이티브 전달 경로와 명시적 통신 범위로 에이전트 세션을 연결하는 구조](docs/assets/xsm-overview.svg)

> **릴리스 상태.** 업무 검색, `connect`와 `ask`, 첨부, 소유 워커, 선택적 P2P 네트워크는 0.5.0에
> 들어갔습니다. [변경 기록](CHANGELOG.md)을 보세요. 부분별로 어떤
> 환경에서 검증했는지는 [ADR-0021 종료 기록](docs/plan/collaboration/adr-0021-closure.md)과
> [완료 색인](docs/plan/collaboration/completion-ledger.md)에 있으며, 계획 전체는 아직 완료되지 않았습니다.

## 철학

Orca, herdr, OpenRig 같은 멀티 에이전트 도구는 조율 자체를 제품으로 만듭니다. 디스패처, 작업 그래프, YAML로
정의한 팀, 도구가 소유한 터미널이 그것입니다. xsm은 그중 어느 것도 만들지 않습니다. 이미 쓰고 있는 세션들이
서로에게 닿을 길만 주고, 나머지는 세션들에게 맡깁니다. 에이전트는 평범한 말을 읽고 씁니다. 채널이 있으면 사람이
채팅 채널에서 하듯 일을 나누고, 넘기고, 서로 검토하고, 결과를 보고합니다. 모델이 좋아질수록 고정된 구조는 덜
도움이 되고 더 방해가 됩니다.

xsm에 없는 것:

- 오케스트레이터, 팀 정의, 작업 그래프가 없습니다. 누가 무엇을 할지는 대화에서 정해집니다
- 자체 런타임도, `claude`·`codex`를 감싸는 래퍼도 없습니다. 세션은 늘 하던 대로 띄웁니다
- 한 머신 안의 세션 사이에 서버가 없습니다. 로컬 메시징은 훅·파일·일회성 명령입니다. 계속 떠 있는 프로세스는
  선택적 P2P 네트워크 서비스 하나뿐이며, 네트워크를 만들거나 가입한 뒤에만 돌고 `xsm network stop`으로 멈춥니다

나머지를 에이전트에게 맡기는 만큼, 채널만큼은 믿을 수 있어야 합니다. xsm은 노력을 여기에 씁니다.

- **메시지가 세션을 깨웁니다.** 메시지는 보내는 쪽이 지정한 세션 앞으로 가는 DM입니다. 터미널에 타이핑해
  넣지 않고 각 런타임의 고유 경로(Claude inbox 소켓, `codex queue`)로 넣습니다. 그래서 쉬고 있는 세션도
  메시지를 받고, 메시지는 사용자가 친 입력처럼 보이지 않고 발신자 표시를 달고 도착합니다. 끼어들 필요가 없는
  메시지는 상대의 다음 자연스러운 턴까지 기다리게 할 수도 있습니다(`--wake never`).
- **보낸 쪽이 결과를 압니다.** 저장, 런타임 전달, 읽은 뒤의 수신 확인, 실제 답변은 서로 다른 네 가지 사실이며,
  결과마다 어느 것이 성립했는지 알려 줍니다. 응답을 잃어도 같은 요청 ID로 회수하고 새 ID로 다시 보내지 않으며,
  과제 완료는 상대가 명시한 결과로만 판단합니다.
- **찾았다고 권한이 생기지 않습니다.** 사용자가 공개했거나 같은 저장소에 있는 세션만 후보가 됩니다. 하나를
  고르면 그 대화와만 연결되고, 그 폴더나 다른 후보는 연결되지 않습니다.
- **경계는 사람이 정합니다.** 어떤 세션끼리 말할 수 있는지는 사용자가 정하는 범위입니다. 범위를 넓히거나
  세션을 공개하거나 네트워크에 가입하려면 사용자의 말이 필요하고, 다른 에이전트의 메시지는 사용자의 승인으로
  치지 않습니다.

## TL;DR

코딩 에이전트(Claude Code나 Codex)에게 아래 프롬프트를 주면, 에이전트가 두 런타임 모두에 xsm을 설치하고
결과를 검증합니다.

```
https://github.com/ysys143/xsm 의 xsm을 이 머신의 Claude Code와 Codex 양쪽에 설치해줘.
그다음 `xsm doctor`와 `xsm selftest`로 검증하고, Codex에서 훅 신뢰하기나 새 세션 시작하기처럼
내가 직접 해야 할 일이 남았으면 알려줘.
```

에이전트는 이 README를 따라 두 런타임에 설치하고, 무엇을 검증했는지 보고합니다. 코딩 에이전트는 `/plugin`
같은 슬래시 명령을 직접 입력하지 못하는 경우가 많습니다. 그때는 빠른 시작의 직접 설치(`xsm install`)를 씁니다.

설치가 끝나면 어느 쪽이든 새 세션을 열어 이렇게 말해 보세요.

```
이거 어떻게 쓰는 거야? 실제 데모로 보여줘.
이 세션을 xsm에서 찾을 수 있게 공개해줘.
설정 변경 작업을 하고 있는 세션들 찾아서 후보를 보여줘.
a1이랑 붙어서 일하자. 내 diff 검토 좀 부탁해 봐.
```

에이전트가 스킬의 참고 문서를 읽고 직접 `xsm`을 실행하므로, 명령을 미리 익힐 필요가 없습니다.
직접 설치하려면 아래를 이어서 읽으세요.

## 빠른 시작

### 1. 직접 설치

macOS와 Linux에서 동작합니다. Unix 소켓, `ps`, `/dev/tty`, tmux가 필요하므로 네이티브 Windows는 지원하지
않습니다. 로컬 메시징은 Python 표준 라이브러리만 씁니다. 선택적 P2P 네트워크는 엔진을 한 번 빌드할 Rust
toolchain이 더 필요합니다([다른 머신과 일하기](#5-다른-머신과-일하기) 참고). 설치란 각 세션이 xsm의 훅을
실행하게 만드는 일입니다.

**Claude Code 플러그인** (권장). 저장소 자체가 마켓플레이스입니다.

```
/plugin marketplace add ysys143/xsm
/plugin install xsm@xsm
```

플러그인에는 훅, 스킬, MCP 서버, `bin/`이 함께 들어 있습니다. `plugin.json`의 `version`이 오르면 갱신되고,
플러그인을 끄면 훅도 함께 꺼집니다.

**Codex 플러그인** (권장). 같은 저장소가 Codex 마켓플레이스이기도 합니다.

```bash
codex plugin marketplace add ysys143/xsm
codex plugin add xsm@xsm
```

플러그인에는 훅 두 개, 스킬, MCP 서버가 들어 있습니다. Codex는 플러그인의 훅을 신뢰한 뒤에만 실행하므로,
첫 세션에서 `/hooks`의 "Trust all and continue"를 고르세요.

<details>
<summary>Codex 플러그인 더 보기: PATH, 갱신, 이전 설치의 잔여물</summary>

- Codex는 플러그인의 `bin/`을 PATH에 넣지 않으므로, 세션이 시작될 때마다 `~/.local/bin/xsm`을 플러그인에
  링크합니다. 그 자리에 xsm 플러그인 폴더를 가리키지 않는 링크나 파일이 있으면 건드리지 않습니다.
- 갱신하려면 `codex plugin marketplace upgrade xsm`을 실행한 뒤 `codex plugin add xsm@xsm`을 다시 실행합니다.
- 이 홈에 예전에 `xsm install --codex-home`으로 설치한 적이 있다면, 플러그인을 추가한 뒤 `xsm install --refresh`를
  한 번 실행하세요. 그 설치가 남긴 훅 그룹, MCP 항목, 스킬 링크를 지웁니다. 남아 있으면 플러그인의 것과
  나란히 실행됩니다.

</details>

<details>
<summary>플러그인 없이: <code>xsm install</code></summary>

```bash
bin/xsm install --claude-home <my-claude-config-dir>          # 플러그인 대신 직접 설치할 때
bin/xsm install --claude-home <dir-A> --claude-home <dir-B>   # 여러 홈을 한 명령으로
bin/xsm install --codex-home <my-codex-home>                  # Codex 훅, 스킬, MCP
bin/xsm install --refresh                                     # 이미 설치한 모든 홈을 최신으로
bin/xsm doctor                                                # 설치 상태, 낡은 사본, 지금 막힌 것
```

`--claude-home`에는 Claude Code의 설정 디렉터리(`CLAUDE_CONFIG_DIR`)를, `--codex-home`에는 Codex의
설정 디렉터리(`CODEX_HOME`)를 넣습니다. 바꾸지 않았다면 각각 `~/.claude`, `~/.codex`입니다. 기본 홈은 없으므로
`--refresh`를 쓰는 경우를 빼면 홈을 하나 이상 적어야 합니다. 홈이 여러 개면 `--claude-home`을 반복하세요.

직접 설치한 사본은 저장소가 바뀌어도 따라가지 않습니다. `xsm doctor`가 낡았다고 알려 주면
`xsm install --refresh`로 갱신하세요. 플러그인을 갱신한 뒤에는 새 버전의 `bin/xsm`으로 `install --refresh`를
실행합니다.

직접 설치가 실행하는 코드: `xsm install`은 이 체크아웃의 실행에 필요한 것(`xsm/`, `hooks/`, `skills/`,
`bin/`, 플러그인 매니페스트)을 `~/.xsm/runtime/<id>/`로 복사하고 모든 것을 그 사본으로 향하게 합니다. Claude
훅 명령(`hooks/xsm-hook` 런처: 쓸 수 있는 파이썬을 스스로 찾고, 열 수 없는 스크립트는 프롬프트를 막지 않는
오류로 바꿉니다), MCP 서버 등록(`hooks/xsm-mcp` 런처), `~/.local/bin/xsm`이 그렇습니다. macOS는 세션을 연 앱에
체크아웃이 있는 폴더(`~/Documents`) 접근을 막을 수 있고, 실행하지 못한 훅이 프롬프트를 막아서는 안 됩니다. 직전
사본은 그보다 먼저 시작한 살아 있는 세션이 없어질 때까지 남고, 그 뒤 다음 `xsm install`이 끝날 때
정리됩니다(그전에는 아닙니다. 정리가 프로세스 표를 읽는데 훅에는 그럴 시간이 없습니다). `xsm doctor`의
`runtime` 줄이 사본을 알려 주고 체크아웃이 앞서가면 그렇게 말하며, 그러면 에이전트가
`<체크아웃>/bin/xsm install --refresh`를 실행합니다. `--dev`(또는 `config.json`의 `"runtime": "checkout"`)는
xsm을 개발할 때 모든 것을 체크아웃에 둡니다. `--dev`는 그 줄을 스스로 저장하므로 이후의 `install --refresh`와
`doctor`도 그것을 지킵니다(사본으로 돌아가려면 그 줄을 지웁니다). Codex 직접 설치는 이미 가진 훅 명령을 그대로
둡니다. Codex의 신뢰가 그 문자열을 덮기 때문입니다. 새로 하는 설치는 갱신해도 그대로인
`~/.xsm/runtime/current`를 씁니다. 기존 Codex 설치를 체크아웃에서 옮기는 것은 `codex plugin add xsm@xsm`뿐입니다.

설치는 Claude 홈마다 `crossSessionInbound`도 `"accept"`로 둡니다(Claude Code 2.1.224 이상, 홈에 이미 값이 있으면
그대로 둡니다). 그러면 두 세션의 권한 모드가 달라도 Claude가 내 다른 세션의 메시지를 전달합니다. 메시지 명령을
이름과 런타임의 절대 경로로 `permissions.allow`에 넣습니다: `connect`, `ask`, `question-status`,
`decision-status`, `discover`, `send`, `inbox`, `ack`, `files`, `owned`, `list`, `who`, `held`, `ledger`,
`status`, `doctor`, `board`, `--version`. 짝이 되는 MCP 도구도 넣습니다: `xsm_connect`, `xsm_ask`,
`xsm_question_status`, `xsm_decision_status`, `xsm_discover`, `xsm_send`, `xsm_inbox`, `xsm_ack`, `xsm_files`,
`xsm_owned`, `xsm_board`. 그래서 auto와 default 모드가 메시지를 막지 않습니다. `publish`, `network`, `spawn`,
`doc add`는 목록에 없으며 런타임의 권한 확인을 그대로 거칩니다.

`xsm uninstall`은 설치가 더한 훅, MCP 항목, 스킬 링크, 상태줄, 설정 항목을 뺍니다. `~/.local/bin/xsm` 링크가
런타임 사본을 가리키고 다른 홈에 xsm이 남아 있지 않으면 그 링크도 뺍니다. `~/.xsm/runtime`의 사본은 남으므로,
그것을 쓰는 세션이 없을 때 그 폴더를 지우면 됩니다. 한 홈을 제거해도 다른 홈과 실행 중인 네트워크 서비스는
그대로입니다.

이 기본값은 모두 열린 쪽이고 `~/.xsm/config.json`이나 환경 변수(이쪽이 이깁니다)로 닫을 수 있습니다:
`runtime`(`snapshot` | `checkout`, `XSM_RUNTIME`), `claude_inbound`(`accept` | `leave`, `XSM_CLAUDE_INBOUND`),
`allow_messaging`(`XSM_ALLOW_MESSAGING`), `human_send_connects`(`XSM_HUMAN_SEND_CONNECTS`: 사람이 직접 친 범위 밖
`xsm send`가 필요한 폴더를 잇고 전달합니다). 기본값에서 벗어난 것은 `xsm doctor`가 `policy` 한 줄로 보여 줍니다.

</details>

<details>
<summary>주의: 훅 중복, PATH, Linux의 이름 충돌</summary>

- 한 홈(Claude든 Codex든)에 플러그인과 직접 설치가 함께 있으면 훅이 두 번 실행되어 위험합니다.
  `xsm install`은 그런 홈을 거부하며, `--force`를 주면 넘어갑니다.
- `xsm install`은 설치한 런타임의 `bin/xsm`을 `~/.local/bin/xsm`에 자동으로 링크하므로(다른 것을 가리키는
  링크는 건드리지 않습니다), `~/.local/bin`이 PATH에 있는지 확인하세요. Claude 플러그인은 세션 안에서 PATH를
  설정하고, Codex 플러그인은 위의 링크를 유지합니다.
- xsm을 설치하기 전에(또는 플러그인을 켜기 전에) 시작한 세션은 아직 훅이 돈 적이 없습니다. 그 세션은 처음 xsm
  명령이나 도구를 실행할 때 스스로 등록하고, 그 이름으로 보내는 쪽에는 열려 있지만 등록되지 않았다는 것과
  등록되는 방법이 알려집니다.
- xsm을 갱신할 때 이미 떠 있던 세션은 시작할 때의 훅과 MCP 서버를 그대로 씁니다. 새 버전을 쓰려면 새 세션을
  여세요.
- Linux에서는 X.Org의 세션 관리자도 이름이 `xsm`입니다(x11-session-utils 패키지). 설치되어 있다면
  `command -v xsm`으로 이쪽이 먼저 잡히는지 확인하세요.

</details>

### 2. 써 보기

따로 등록하지 않습니다. 훅이 설치된 세션은 시작할 때와 프롬프트를 낼 때마다 스스로 등록합니다.
등록이 곧 동의이므로, 훅을 실행한 적 없는 세션은 목록에 `unregistered`로만 보이고 주소로 쓸 수 없습니다
(ADR-0001, 세션 레지스트리).

보통은 말로 부탁합니다("설정 변경을 검토하는 세션 찾아줘", "저쪽 세션에 물어봐"). 에이전트가 스킬의 참고
문서를 읽고 명령을 골라 직접 `xsm`을 실행합니다. 명령을 스킬 `xsm`의 인자로 넘길 수도 있습니다. Claude Code는
`/xsm`, Codex는 `$xsm`입니다.

```
/xsm list                            # Claude Code: 이 프로젝트에서 말을 걸 수 있는 세션들
$xsm list                            # Codex
/xsm who                             # 이 세션이 다른 세션에 어떻게 보이는지
/xsm send ref:a1b2c3 이것 좀 봐줘      # 대상 다음은 모두 메시지
```

터미널에서는 같은 명령을 `xsm list`, `xsm who`, `xsm send ...`로 씁니다. 인자 없이 부르면 스킬이 사용법 한 줄을
출력합니다. 같은 이름의 개인 스킬이 있다면 플러그인 쪽은 `/xsm:xsm list`로 부릅니다.

자주 쓰는 명령: `discover`, `publish`, `connect`, `ask`, `question-status`, `send`, `inbox`, `ack`, `list`,
`who`, `log`, `projects`, `doctor`, `link`, `join`, `leave`, `reach`, `network`. 전체 목록은 `xsm --help`가
보여 줍니다.

## 사용 사례

### 1. 세션 이름 짓고 찾기

이름은 런타임이 가진 것이라 `xsm rename` 같은 명령은 없습니다. xsm은 조회할 때마다 런타임에서 이름을 읽으므로,
세션 자체의 이름을 바꾸면 xsm도 따라갑니다.

```bash
# Claude Code 세션에서
/rename my-reviewer                            # 세션 이름 변경

# 그 다음, 다른 세션에서
xsm list                                       # 이 프로젝트에서 말 걸 수 있는 세션들
xsm list --dir ~/src/other-repo                 # 다른 프로젝트의 세션 조회
xsm list --all                                 # 모든 프로젝트와 종료 세션 조회
xsm list clear                                 # 이 프로젝트의 종료 세션 등록 정리
xsm who                                        # 이 세션이 어떻게 보이는지
```

`list`는 등록 정보를 먼저 읽고, 요청한 프로젝트·런타임·홈에 맞는 세션만 검사합니다. 그래서 등록이 남아 있는
종료 세션(7일 동안 보관)이 많아도 느려지지 않습니다. 한 번의 조회에 쓰는 검사들은 총 3초의 시간 한도를
공유합니다. 검사 하나가 답하지 않으면 그것 없이 진행하고 stderr에 한 줄로 알립니다. 어떤 검사였는지는
`xsm doctor`가 보여 줍니다. `who`는 세션이 등록돼 있으면 자기 세션만 확인합니다. 등록된 `ref:`, `claude:`,
`codex:` 주소로 보내면 그 대상만 확인하고 열린 Codex 창을 찾지 않습니다.

### 2. 하는 일로 협업 상대 찾기

세션의 이름이나 주소를 몰라도 됩니다. 무엇을 하고 있는 세션을 찾아 달라고 에이전트에게 부탁하고, 각 후보가
하는 일을 본 뒤 함께 일할 상대를 말하면 됩니다.

```
macmini에서 설정 변경 작업 하고 있는 세션 찾아와 봐.
a1이랑 붙어서 일하자.
```

후보는 사용자가 공개한 세션과 같은 Git 저장소에 있는 세션입니다. 같은 저장소의 다른 폴더와 linked worktree도
따로 공개하지 않아도 들어갑니다. 후보마다 머신, 런타임, 이름, 저장소, branch, 작업 요약, 상태와 각 값의 최신성이
나옵니다. xsm이 읽지 못한 값은 짐작하지 않고 unknown으로 표시합니다. 그 아래에서 에이전트는 이렇게 실행합니다.

```bash
xsm publish                                    # 이 대화를 찾을 수 있게 공개. 사용자가 말했을 때만
xsm publish --off                              # 공개 철회
xsm discover --machine macmini --work config   # 후보(에이전트용 JSON), 각 후보에 target이 붙음
xsm connect candidate:<id> --wait 30           # 사용자가 고른 상대와 핸드셰이크
```

공개는 세션을 보이게 할 뿐, 누구에게도 메시지를 보낼 권리를 주지 않습니다. 사용자의 선택은 두 대화만
연결하고 그 폴더는 연결하지 않으며, 다른 후보도 그대로입니다. 핸드셰이크는 고른 상대가 직접
`outcome=succeeded`로 답했을 때만 완료됩니다. 실패 결과는 거절이고, 답이 없으면 준비 여부는 미확인으로 남습니다
(시간이 지난 뒤에는 `--request-id`로 같은 핸드셰이크를 잇습니다). 재개한 대화는 다시 확인하고, 이름만 같은 새
대화는 아무것도 물려받지 않습니다.

### 3. 묻고 실제 답 받기

`ask`는 질문 하나를 지정한 세션에 DM으로 보내고 그 질문에 대한 답을 모읍니다. 기본으로는 요청 ID를 바로
돌려주고 에이전트는 하던 일을 계속합니다. 시간이 지나거나, 도구 호출이 취소되거나, 재시작한 뒤에도 답을
나중에 회수할 수 있습니다.

```bash
xsm ask a1 --text "이 마이그레이션이 기존 행을 남겨?"          # 요청 id를 바로 반환
xsm ask a1 --text "..." --wait 60                              # 또는 답을 기다림
xsm question-status <id> --wait 60                             # 답. 늦은 답과 부분 답도
xsm question-status                                            # 응답을 잃었을 때 내 요청 id 목록
xsm ack <token>...                                             # 답을 실제로 읽은 뒤
```

전달 영수증은 답이 아니고, 답을 출력했다고 읽은 것도 아닙니다. 에이전트는 읽은 뒤 `ack`(MCP `xsm_ack`)로
수신을 확인하며, 그 전까지 원문은 회수할 수 있습니다. 과제 완료는 상대가 명시한 `outcome`으로만 판단합니다.

답을 모을 필요가 없는 알림이나 일 넘기기는 전처럼 `send`를 씁니다.

```bash
xsm send my-reviewer --text "이것 좀 봐줘"                        # 알림
xsm send my-reviewer --text "이 테스트 고쳐줘" --kind task --wait 15  # 일 넘기기. 전달을 기다림
xsm send my-reviewer --text "참고만" --wake never                # 저장만. 상대는 다음 턴에 읽음
xsm send reviewer tester docs --text "18시까지 main 동결"         # 각자에게 DM 하나씩, 누가 함께 받았는지 알려 줌
xsm ledger                                                       # 전달 상태
```

`send --wait`은 답이 아니라 수신 기록을 기다리는 시간입니다. 그 안에 수신 기록이 없으면
`sent-unconfirmed`(종료 코드 3), 전달이 실패하면 `error`(종료 코드 4)이고 원장에 남습니다. 결과 줄 끝에는
메시지 ID가 붙습니다. `xsm status <id>`와 `--resend <id>`에 그 ID를 씁니다. `--priority now`는 Claude에 다음
턴 대신 즉시 전달로 넘어갑니다. Codex는 턴 사이에만 메시지를 받으므로 `now`를 명시적으로 거부합니다.

### 4. 메시지에 파일 붙이기

```bash
xsm ask a1 --text "이 설정 검토해 줘" --attachment ./config.yaml
xsm files <storage_id>                         # 받는 쪽: 메시지와 함께 온 것
xsm files <storage_id> --entry <entry_id>      # 파일 하나를 텍스트로 (바이너리는 --encoding base64)
```

`--attachment`는 보내는 CLI 자신의 읽기 권한으로 파일을 스냅숏합니다. MCP는 에이전트가 실제로 읽은 내용만 받고,
열어 볼 경로는 받지 않습니다. 받는 쪽은 저장소 ID가 붙은 별도 사본을 받습니다. 원본 파일은 건드리지 않으며,
사본은 상대가 보낸 데이터일 뿐 읽기·실행·변경 권한이 아닙니다. 승인이나 중단 뒤에 다시 보낼 때는 같은 요청
ID와 그 manifest를 다시 씁니다. 파일이 바뀌었으면 새 요청입니다. 파일을 받지 못하는 상대에게는 거부되며,
`--attachment-fallback inline`을 고르면 UTF-8 텍스트를 본문에 넣어 보냅니다(자동으로 낮추지 않습니다).
기본값은 파일당 1 MiB, 메시지당 4 MiB·16개, 사본 저장 256 MiB, 보관 7일입니다.

### 5. 다른 머신과 일하기

**선택적 P2P 네트워크.** 기기끼리 기기키와 초대로 가입하며, xsm 계정도 SSH 설정도 필요 없습니다. 기본은 공개
relay이고, 자체 relay를 설정할 수 있으며, Tailscale 주소를 같은 프로토콜의 경로로 더할 수도 있습니다.

```bash
xsm network build                                    # 한 번: xsm 상태 폴더에 엔진 빌드 (Rust 필요)
xsm network init my-network --machine-name macbook
xsm network invite                                   # 비공개(0600) 초대 파일을 만들고 경로만 출력
# 그 파일을 믿을 수 있는 수단으로 다른 머신에 옮긴 뒤, 그 머신에서:
xsm network join --ticket-file /path/to/ticket.json --machine-name macmini
xsm network members
xsm network status                                   # 요청 포트와 실제 포트, relay, 마지막 관측 경로
```

그 뒤에는 `discover --machine macmini`가 그 머신의 공개 세션과 같은 저장소 세션을 보여 주고, `connect`, `ask`,
`send`가 로컬과 똑같이 동작합니다. 두 머신의 저장소는 양쪽에 대응을 기록한 뒤에만 같은 저장소로
봅니다(`xsm network map-repository`). 폴더 이름이나 remote URL이 같다는 것만으로는 부족합니다.

활성 멤버라면 누구나 초대·추가·제명할 수 있고, 처음 만든 기기도 다른 기기에 대한 관리자 권한이 없습니다.
네트워크에 가입해도 세션이 공개되지 않고, 어느 멤버에게도 그 세션과 일할 권한이 생기지 않습니다. 서로 믿는
기기들을 위한 모델이며, 악의적인 멤버를 막아 주지는 않습니다.

`xsm network stop`은 네트워크 서비스만 멈추고 로컬 메시징은 계속 동작합니다. `start`는 같은 키와 가입 상태로
다시 시작합니다. 서비스를 멈추거나 다른 네트워크로 바꾼 뒤에도 내가 보낸 원문은 회수할 수
있습니다(`xsm network requests`, `export`, `archive`). 만료되거나 한 번만 쓰는 초대, 멤버 제명, 키 교체, relay,
포트, 복구는 [네트워크 안내](docs/xsm/NETWORK.md)에 있습니다.

**양방향 SSH.** SSH로 짝지은 머신도 그대로 동작합니다.

```bash
xsm remote add <host>                          # 짝짓기는 사용자가 결정
xsm remote sessions <host>                     # 그 머신의 살아 있는 세션
xsm send <이름>@<홈>@<host> --text "..."       # 답도 같은 길로 돌아옴
```

### 6. 다른 저장소 전체와 연결

보통은 위처럼 고른 세션 하나와 연결하면 충분합니다. 두 폴더의 모든 세션이 서로 말하게 하려면 연결합니다.

```bash
/xsm link ~/src/other-repo                     # 어느 한쪽 세션에서 직접 입력 (Codex: $xsm link ...)하거나 에이전트에게 연결을 부탁
xsm projects                                   # 어떤 폴더들이 연결·참여되어 있는지
```

`link`, `join`, `reach`는 [통신 범위](#통신-범위)를 보세요.

### 7. 워커에게 일 시키기

```bash
xsm spawn codex --task "이 테스트 고쳐줘"      # tmux에 워커를 띄우고, 지시하고, 답장으로 결과를 받음
xsm workers                                    # 워커 상태
```

반복되는 headless 작업에는 소유 워커를 만들고 요청을 보냅니다. 요청은 워커가 시작하기 전에 기록되고, 문맥은
보낸 쪽과 작업 단위별로 나뉘며, 저장된 답은 모델을 다시 돌리지 않고 회수하거나 다시 게시할 수 있습니다.

```bash
xsm owned create reviewer --runtime codex                       # --dir를 주지 않으면 이 세션의 폴더
xsm owned run reviewer --work pr-42 --text "diff 검토해 줘"      # 독립 문맥은 --fresh
xsm owned status reviewer                                        # 내 요청과 그 답
```

이미 떠 있는 일반 세션을 소유 워커로 가져오지는 않습니다. Orca나 herdr 터미널 안에서는 사용자가 따로 정하지
않는 한 워커 띄우기를 그 도구에 맡깁니다(`xsm frameworks`).

### 8. 설치가 안 된 홈 진단

```bash
xsm doctor                                     # 어느 홈에 훅이 없는지, 낡은 사본, 지금 막힌 것
xsm selftest                                   # 훅이 실제로 도는지
```

### 9. 팀으로 일하기

여러 세션이 한 가지 일을 함께 하면 팀으로 묶습니다. 팀은 구성원 목록과 (있으면) 팀장입니다. 구성원끼리는 프로젝트와
머신이 달라도 DM을 주고받을 수 있고, `team:<이름>`으로 보낸 DM은 실행 중인 모든 구성원에게 가며 각자에게 누가 함께
받았는지 알려 줍니다. 범위 밖 세션을 넣는 것과 팀장을 정하는 것은 사용자의 승인을 받습니다. `xsm connect`는 구성원
둘인 팀을 만듭니다.

```bash
xsm team create core                                   # 이 세션이 첫 구성원
xsm team lead core planner                             # 사용자의 결정
xsm team add core api-worker                           # 팀장이 같은 프로젝트 세션을 넣으면 묻지 않음, 아니면 사용자 승인
xsm send team:core --text "18시까지 main 동결"           # 모든 구성원에게 DM 하나씩
```

팀마다 보드가 있습니다. 지금 팀에 유효한 것(현행 결정, 누가 무엇을 맡았는지, 진행)을 항목 하나에 하나씩 둡니다.
구성원은 항목을 xsm doc의 불변 노드로 쓰고, 쓰기는 쓴 세션이 읽은 버전만 이어받습니다. 그래서 아무도 읽지 않은 버전이
가려지지 않고, 둘을 읽은 세션이 정리할 때까지 둘 다 보입니다. 에이전트가 따르는 규칙은 짧습니다. 누군가를 움직이려면 DM, 팀 전체가 알아야 할 사실이면 보드, 둘 다에
쓰지 않는다. 보드가 바뀌면 각 구성원의 다음 프롬프트에 바뀐 항목 이름을 담은 한 줄이 한 번 붙습니다(본문은 싣지
않습니다).

```bash
xsm board set core "decision: cache" --text "redis, 세션 저장소용"
xsm board show core                                    # ~/.xsm/teams/core/BOARD.md, 모든 워크트리에서 같음
```

결재는 사용자와 대면하는 팀장을 거칩니다. 비용, 밖으로 나가는 일(push, PR, 릴리스, 게시), 범위 변경은 보통 결재
대상입니다. 팀장이 양식으로 묻고(팀을 지정한 `xsm_decide`) 사용자의 답은 보드 옆에 고유 ID로 기록되며, 보드 항목에
누가 결정했는지 나옵니다. 결정이라고 주장만 하는 노드는 "not confirmed"로 보입니다.

한 세션의 자리를 다른 세션에 넘기려면, 떠나는 세션에서 "night-shift한테 인수인계해"라고 말하면 됩니다. 에이전트가
작업 맥락 요약을 쓰고 `xsm handover`를 실행하며, 사용자가 확인합니다. 팀 자리와 팀장 자리, 자기 보드 항목, 안 읽은
DM, 답을 기다리는 질문이 후임에게 옮겨 가고, 후임은 다음 프롬프트에서 이 모두를 받습니다. 이후 옛 세션 앞으로 오는
DM은 후임에게 갑니다.

## 참고

### 통신 범위

같은 Git 저장소 안의 세션끼리는 하위 폴더가 달라도 통신할 수 있습니다. Git 저장소 밖에서는 같은 폴더의
세션끼리 통신합니다. 그 밖으로 넓히는 길은 둘입니다.

- **고른 세션 하나**([사용 사례 2](#2-하는-일로-협업-상대-찾기)): 사용자의 선택은 정확히 두 대화만 연결하고
  다른 것은 열지 않습니다.
- **폴더 전체**: 어느 한쪽 세션의 에이전트에게 연결해 달라고 부탁하세요. 에이전트가 사용자에게 말로 묻고
  `xsm link <폴더>`를 직접 실행하며, 사용자의 답이 동의입니다. `/xsm link <폴더>`를 직접 입력해도 됩니다.
  한쪽에서만 하면 되고, 연결은 양방향이며 직접 풀 때까지 유지됩니다.

```bash
xsm link ~/src/other-repo            # 사용자가 허락한 뒤 에이전트가 실행하는 명령
/xsm link ~/src/other-repo           # 또는 세션에서 직접 입력 (Codex: $xsm link ...). 직접 입력했으므로 따로 묻지 않습니다
xsm unlink ~/src/other-repo          # 연결은 누구나 풀 수 있습니다
```

- `join`: 여러 폴더를 한 묶음으로 두려면 각 폴더의 세션에서 에이전트에게 `<이름>` 프로젝트에 가입해 달라고
  부탁합니다(`/xsm join <이름>`을 직접 입력해도 됩니다).
- `reach`: 세션 하나만 그 세션이 끝날 때까지 연결하려면 그 세션의 에이전트에게 그 폴더와 연결해 달라고
  부탁합니다(`/xsm reach <폴더>`를 직접 입력해도 됩니다).

### 메시지 송신

`send`와 `ask`는 DM을 보냅니다. 지정한 대상이 곧 받는 세션입니다.

```bash
xsm send agent-name --text "이것 좀 봐줘"
xsm send agent-name --text "이 테스트 고쳐줘" --kind task --wait 15
xsm send ref:a1b2c3 --text "..."             # 이름이 겹칠 때는 ref로
xsm send candidate:<id> --text "..."         # discover가 돌려준 대상, connect 뒤 (로컬이든 다른 머신이든)
xsm send agent@home@hostB --text "..."       # SSH로 짝지은 머신
xsm ask agent-name --text "..."              # 답을 돌려받을 질문
```

에이전트는 명령이 돌려준 대상을 그대로 쓰고, 표시 이름으로 주소를 지어내지 않습니다. 샌드박스 안의 Codex는
셸이 Codex의 상태에 닿지 못하므로, 서버가 샌드박스 밖에서 도는 MCP 도구(`xsm_send`, `xsm_ask` 등)를 씁니다.

### 메시지 수신

DM을 받는 쪽은 아무것도 실행하지 않습니다. 훅이 게이트 역할을 해서 범위와 발신자를 확인한 뒤 메시지를
세션의 프롬프트로 직접 넣습니다. 거절된 메시지는 버려지지 않고 보관됩니다. Claude 자체의 세션 간 메시지
(`SendMessage`, xsm 헤더 없음)는 이 기계의 세션이 보냈다면 범위와 상관없이 그대로 들어갑니다. Claude 자체 게이트가
이미 판정했고, 보낸 쪽도 같은 기계의 사용자 자신이기 때문입니다. 이 기계 밖(Remote Control, 클라우드)에서 온 것은
어디서 왔는지 적은 쪽지와 함께 들어갑니다(`"remote_native": "hold"`면 예전처럼 보관합니다). 범위는 xsm 자체
메시지에 적용되고, `xsm send`는 범위 밖 대상을 보내기 전에 거부합니다. linked worktree(Orca,
`claude --worktree`)와 메인 체크아웃은 같은 저장소로 봅니다. xsm 헤더가 없는 메시지를 모두 보관하려면
`~/.xsm/config.json`에 `"strict_peers": true`를 넣습니다(ADR-0013). Claude 자체 게이트가 먼저 판정하므로, 권한
모드가 달라 Claude가 보류한 메시지는 xsm까지 오지 않습니다.

수신함(`xsm inbox`, MCP `xsm_inbox`, Codex의 일반 경로)으로 읽은 메시지에는 claim 토큰이 붙습니다. 에이전트는
읽은 뒤 그 토큰으로 `ack`를 부릅니다. 그 전까지 원문은 회수할 수 있고, 그 뒤에는 원문을 보관하되 다시 전달하지
않습니다. 답을 기다리는 동안 다른 메시지를 소비하지 않으며, 결과마다 이 대화에 아직 남은 메시지 수를 알려 줍니다.

사용자가 원한 세션 간 대화는 보이지 않는 보류에 막히지 않습니다. 게이트가 고장 나거나 메시지를 확인하지 못하면(보낸
세션이 이미 끝났거나 이 기계 밖에서 왔을 때) 보관하지 않고 `[xsm] could not check this message` 쪽지와 함께 넣습니다.
그래도 보관되는 것(사용자가 막은 세션, 범위 밖)은 양쪽에 알리고, 사용자의 예에 에이전트가 `xsm held deliver <id>`로
풉니다. 연 보류는 `~/.xsm/config.json`의 `fail_open`, `remote_native`, `stale_sender`, `reply_from_request`,
`reply_flag`(또는 환경변수 `XSM_<키>`)로 다시 닫을 수 있고, `xsm doctor`의 `policy` 줄이 지금 값을 보여 줍니다.

```bash
xsm ledger                           # 최근 메시지와 전달 상태
xsm status <message-id>              # 한 건의 상태
xsm held                             # 이 머신이 거절하고 보관한 것
```

### 사용자의 결정

xsm이 사용자의 허락을 받아야 할 때(폴더 연결, 넓은 권한으로 워커 띄우기, 공동 문서 승인)는 에이전트가 묻고,
xsm이 질문과 답을 원문 그대로 남깁니다. 같은 결정을 다시 시도하면 새 질문을 열지 않고 같은 기록을 잇습니다.
범위나 질문이 바뀌면 새 결정입니다. 대기 중인 질문은 회수하거나 철회할 수 있습니다(`xsm decision-status`,
`--cancel`). 질문을 철회해도 이미 적용된 권한은 되돌아가지 않으니, 그 권한 자체의 해제를 쓰세요. 다른
에이전트의 메시지는 결코 사용자의 승인이 아닙니다.

### 트래픽 제어

xsm은 보낸 쪽과 받는 쪽 짝별로 메시지 트래픽을 기록합니다. 기본은 관찰만 합니다. 제한하려면
`~/.xsm/config.json`에 한도를 명시합니다. 내장된 차단 수치는 없으며, 아래 값은 예시일 뿐입니다(`strict`에는
window와 한도 하나 이상이 필요합니다).

```json
{"traffic_control": {"mode": "strict", "window_seconds": 60, "max_messages": 30, "max_same_body": 3}}
```

제한된 메시지도 요청 ID를 유지하고 회수할 수 있습니다. 트래픽 제어는 부하만 다루며 통신 범위를 넓히거나 좁히지
않습니다.

### 관측 (텔레메트리)

xsm은 자신의 송수신을 스팬과 메트릭으로 기록합니다. OpenTelemetry SDK를 설치하지 않고 OTLP 형식을 직접
만들기 때문에, 의존성은 여전히 표준 라이브러리뿐이면서 표준 백엔드와 연동됩니다(ADR-0011, 텔레메트리).

```bash
xsm metrics                 # 이 머신에 쌓인 호출 수, 에러, p95
xsm metrics --json
```

메시지 본문은 스팬에 넣지 않습니다. 끄려면 `XSM_NO_TELEMETRY=1`을 설정하세요.

<details>
<summary>보관 기간, collector로 내보내기, 계측 비용</summary>

스팬과 메트릭은 기본 7일간 보관합니다(`telemetry_retention_days`). 정리는 이미 내보낸 줄만, 파일 머리에서만
지우므로 아직 전송하지 않은 기록은 남습니다.

기록은 `$XSM_HOME/otel-spans.jsonl`과 `otel-metrics.jsonl`에 append됩니다. 전송은 별도 명령을 실행할 때만
일어나므로, 송수신 경로에서 네트워크를 쓰는 일은 없습니다.

```bash
# OTEL_EXPORTER_OTLP_ENDPOINT가 없으면 http://localhost:4318
xsm otlp-export --once
xsm otlp-export --follow --interval 5
```

실제 OpenTelemetry Collector(v0.161.0)로 검증했습니다.

```bash
docker run --rm -p 4318:4318 otel/opentelemetry-collector:latest
xsm otlp-export --once
```

한 메시지의 전 구간(발신, SSH, 수신 머신, 대상 세션의 훅)이 하나의 trace로 이어지므로, Jaeger나
Grafana Tempo에서 메시지가 어디서 멈췄는지 바로 볼 수 있습니다.

계측 비용은 send 1회당 약 0.175ms입니다
([telemetry-overhead.md](docs/references/telemetry-overhead.md)).

</details>

## 동작 방식

xsm은 메시지를 한 세션의 입력으로, 그 런타임이 이미 가진 경로를 통해 직접 넣습니다. 이 메시지는
DM(direct message, 직접 메시지)입니다. 보내는 쪽이 받는 세션을 지정하고, 메시지가 그 세션의 입력으로 들어가므로
세션을 깨울 수 있고, 전달이 기록되고 받는 쪽이 수신을 확인할 수 있으며, 답을 받을 수 있습니다. 직접이라는 말은 받는 쪽을
지정한다는 뜻이지 일대일이라는 뜻이 아닙니다. Slack의 그룹 DM도 DM인 것과 같습니다. 팀 전체가 알아야 할 사실은
DM 대신 팀 보드에 둡니다([사용 사례 9](#9-팀으로-일하기)). 보드는 누구도 깨우지 않고, 구성원이 찾아와 읽습니다
([ADR-0025](docs/adr/0025-team-and-multi-recipient-dm.md), [ADR-0026](docs/adr/0026-team-board-on-xsm-doc.md)).

```
Claude Code Session A -> xsm -> Claude Code Session B     같은 머신
Claude Code <-> Codex                                     서로 다른 CONFIG_HOME 사이에서도
Machine A -> P2P (직접 또는 relay) -> Machine B           선택적 네트워크: 기기키와 초대
Machine A -> SSH -> Machine B                             양쪽 다 xsm 설치 + `xsm remote add`
```

각 세션의 훅이 시작할 때와 프롬프트를 낼 때마다 자신을 등록합니다(등록이 곧 동의). 발신은 각 런타임이
이미 가진 수단, 곧 Claude 인박스 소켓과 `codex queue`로만 합니다. 수신 측 훅이 게이트가 되어 범위와 발신자를
확인한 뒤 세션의 프롬프트로 넣고, 거절한 메시지는 보관합니다. 모든 메시지는 원문과 요청 ID를 지니므로, 답을
질문과 짝지을 수 있고 응답을 잃은 뒤에도 회수할 수 있습니다. 머신 사이에서는 P2P 서비스가 같은 메시지를
나르며, 받는 머신이 전달하기 전에 멤버십, 자기 쪽 차단과 제외, 선택을 다시 확인합니다.

원칙:

- **No wrapper runtime**: 별도 런타임 없이 기존 Claude Code와 Codex 세션 안에서 동작합니다. 계속 떠 있는 우리
  쪽 프로세스는 선택적 네트워크 서비스뿐입니다.
- **Project-scoped trust**: 누가 누구와 통신할 수 있는지를 프로젝트별로 정의하며, 선택은 정확히 한 쌍만 더합니다.
- **Session-independent**: 각 세션의 `CONFIG_HOME`(`~/.claude`, `~/.codex` 등)과 무관하게 동작합니다.
- **Async-first**: 메시지는 비동기이고 답은 나중에 회수할 수 있어서, 협업이 서로를 막지 않습니다.
- **Separate evidence**: 저장, 전달, 수신 확인, 실제 답을 따로 보고합니다.
- **Observable**: 스팬과 메트릭을 OTLP 형식으로 기록하며, SDK 의존성은 없습니다.

<details>
<summary>저장소 구조</summary>

```
├── .claude-plugin/                     # 플러그인·마켓플레이스 매니페스트
├── .codex-plugin/, .agents/plugins/    # Codex용 같은 매니페스트
├── bin/xsm                             # 런처 (현재 디렉터리와 상관없이 자기 폴더의 xsm.cli를 실행)
├── hooks/                              # 훅 진입점, 플러그인의 훅과 MCP 서버 정의
├── xsm/                                # 메시징·정책·CLI (Python, stdlib만)
│   ├── cli.py                         # 서브커맨드 전부
│   ├── registry.py                    # 세션 레지스트리 (훅이 기록, 조회 시 런타임에서 보강)
│   ├── send.py / receive.py           # 송신, 그리고 훅이 부르는 수신 게이트
│   ├── envelope.py                    # 메시지 봉투와 헤더
│   ├── adapters.py                    # 두 가지 네이티브 전달 경로 (UDS 소켓, codex queue)
│   ├── directory.py                   # 공개와 발견 (ADR-0017, 0024)
│   ├── collaboration.py / connect.py  # 선택한 짝과 그 핸드셰이크
│   ├── handoff.py / inbox.py          # 상관된 답, claim과 수신 확인 (ADR-0016, 0018)
│   ├── files.py / materials.py        # 첨부 스냅숏과 사본 (ADR-0019)
│   ├── decisions.py / attention.py    # 기록된 사용자 결정, 우선순위와 깨우기 (ADR-0020)
│   ├── abuse.py                       # 트래픽 관찰과 명시적 한도 (ADR-0022)
│   ├── owned_requests.py              # 소유 headless 워커의 요청 기록
│   ├── network*.py                    # P2P 멤버십, 디렉터리, 메시지, 복구 (ADR-0021)
│   ├── remote.py                      # 다른 머신 (양방향 SSH, ADR-0007)
│   ├── workers.py                     # 워커 생성·승인·종료 (ADR-0010)
│   ├── doc.py / board.py              # 공동 문서 (0006), 팀 보드 (0026)
│   ├── telemetry.py / otlp_export.py  # 스팬·메트릭 기록, OTLP/HTTP+JSON 전송 (ADR-0011)
│   ├── install.py                     # 훅 설치·진단
│   └── mcp.py                         # MCP 서버
├── native/xsm-net/                     # 선택적 P2P 엔진 (Rust, iroh)
├── skills/xsm/                         # 스킬 하나: `/xsm <명령>`(Codex `$xsm <명령>`)과
│                                       #   references/ 아래 용도별 참고 문서
├── docs/
│   ├── adr/                           # 아키텍처 결정 기록 (0001-0024)
│   ├── xsm/                           # 프로토콜·테스트 계획·네트워크 안내
│   ├── plan/                          # 구현 계획과 증거 색인
│   ├── references/ · spikes/ · reviews/
│   └── list-agents-cross-session-messaging.md
├── deliverables/                       # 계획이 증거로 인용하는 실행 기록
├── evals/                              # 스킬의 `claude plugin eval` 케이스
├── tests/                              # unittest, 벡터 포함
└── tools/, scripts/                    # 스파이크·벤치마크·감사 스크립트
```

</details>

## 주요 문서

- **[CHANGELOG.md](CHANGELOG.md)**: 릴리스별 변경 기록
- **[INTENT.md](INTENT.md)**: 프로젝트 목표 및 비전
- **[ADR (Architecture Decision Records)](docs/adr/)**: 설계 결정 기록
  - [Session Registry](docs/adr/0001-session-registry.md)
  - [Communication Scope](docs/adr/0004-communication-scope.md)
  - [Remote Transport & Trust](docs/adr/0007-remote-transport-and-trust.md)
  - [Cross-machine Network & Membership](docs/adr/0021-cross-machine-network-and-membership.md)
  - [Discover, Select & Handshake](docs/adr/0024-discover-select-and-handshake.md)
- **[Protocol Spec](docs/xsm/)**: 메시지 프로토콜 명세
- **[Network Guide](docs/xsm/NETWORK.md)**: 선택적 P2P 네트워크
- **[Test Protocol](docs/xsm/TESTPLAN.md)**: 실사용 점검 절차 (개발자용 테스트는 여기)
- **[Collaboration Plan](docs/plan/collaboration/execution.md)**: ADR-0015~0024의 계획과 남은 일
- **[Agent Messaging Guide](docs/list-agents-cross-session-messaging.md)**: 에이전트 메시징 구현

## 라이선스

MIT

## 피드백

이슈, 제안, PR 모두 환영합니다.
