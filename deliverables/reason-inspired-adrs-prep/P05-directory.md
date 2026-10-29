# P05 준비 — 업무 디렉터리와 대화 수명의 경계 명세 초안

- 상태: 읽기 전용 준비. 제품 코드·테스트·git 상태를 바꾸지 않았다.
- 기준: xsm 커밋 `4fd7c9f`, 작업 디렉터리 `cross-session-messaging`.
- 범위: ADR-0017, 계획 P05(`docs/plan/reason-inspired-adrs/plan.json`의 `status: planned-not-started`). G01·G02 진입 게이트는 아직 열리지 않았고 이 문서는 그 통과나 P05 완료로 세지 않는다.
- 이 문서의 모든 좌표는 이번 세션에서 실제로 읽은 코드 줄이다. 확인하지 못한 것은 마지막 절에 모아 두었다.

## 1. 레코드 스키마 — 이름에서 핸들로 가는 경로에서 기록·노출되는 필드

포인터 파일은 `paths.SESSIONS/<runtime>-<session_id>.json` 하나뿐이다(`xsm/registry.py:23-25`). 키가 `runtime`+`session_id` 뿐이므로, 한 대화는 한 파일이다.

### 1a. 훅이 쓰는 색인 필드 (`registry.upsert`, `xsm/registry.py:28-90`)

| 키 | 의미 | 근거 |
|---|---|---|
| `runtime` | `claude` \| `codex` | registry.py:36 |
| `home` | realpath로 정규화한 런타임 홈 | registry.py:32,36 |
| `alias` | 홈 경로 basename에서 점을 뗀 이름(`~/.codex`→`codex`) | registry.py:38, config.py:131-133 |
| `session_id` | 런타임 네이티브 대화 ID(Claude session id / Codex thread id) | registry.py:39 |
| `pid` | 대화를 실행하는 프로세스. Codex 데몬 호스팅 스레드면 데몬의 pid | registry.py:40 |
| `lstart` | `ps -o lstart=` 프로세스 시작 시각 문자열. pid 재사용 판정용 | registry.py:41, identity.py:19-23 |
| `cwd` | 세션 폴더(realpath). 실패 시 이전 레코드 값 유지 | registry.py:42 |
| `ref` | `sha256(runtime:realpath(home):session_id)[:6]` — 24비트 핸들 | registry.py:43, identity.py:83-88 |
| `updated` | 마지막 등록 시각(`time.time()`). 활동 시각이 아니다 | registry.py:44 |
| `permission_mode` | 선택. 훅 입력의 모드 | registry.py:52-53 |
| `name` | 선택. 훅 입력 `session_title`. 조회 시 덮어써질 수 있음 | registry.py:54-55, receive.py:127 |
| `socket` | Claude 전용. 훅 env의 inbox 소켓. pid와 파일명이 일치할 때만 | registry.py:56-64 |
| `mcp_pid`, `mcp_lstart` | Codex 전용. 이 스레드를 서빙하는 xsm MCP 서버 pid와 시작 시각 | registry.py:65-73 |
| `app_server` | Codex 전용 bool. pid가 홈 공용 데몬인지 | registry.py:78 |
| `inside` | 선택. 다른 런타임의 ID(중첩 실행) | registry.py:79-86 |

### 1b. 수명 주기가 덧붙이는 키

| 키 | 의미 | 근거 |
|---|---|---|
| `ended_at`, `end_reason` | SessionEnd·worker 중지가 기록. 크래시는 기록하지 않음 | registry.py:794-797 |
| `adopted`, `unprompted` | 훅 없이 xsm이 등록한 경우(동의 기반 편입) | registry.py:429,488-489 |
| `ended_at`/`end_reason`/`adopted`/`unprompted` 삭제 | 재등록(resume) 시 되살림 | registry.py:48-51 |

### 1c. 조회 시 계산되는 파생 필드 (`registry._enrich`, `xsm/registry.py:191-227`)

| 키 | 의미 | 근거 |
|---|---|---|
| `name` | Claude는 네이티브 이름, Codex는 state DB 이름. 실패 시 `codex-<tail>` 등 | registry.py:198-211, 93-97 |
| `socket` | 레코드 값 또는 Claude 네이티브 값 | registry.py:201 |
| `name_source` | `user` \| `derived` \| `auto`. `user`만 사람이 고른 이름 | registry.py:202, 100-112 |
| `native_session_id` | Claude 네이티브 세션 ID(`/clear`·resume 판정) | registry.py:203 |
| `state` | `live` \| `ended` \| `stale` \| `unknown` | registry.py:212, identity.py:96-190 |
| `end_reason` | `thread_replaced` \| `thread_unloaded` \| `superseded` 등 파생 | registry.py:213-225 |
| `registered` | 이 레코드가 있으면 `True` | registry.py:226 |

### 1d. 목록에만 붙는 표시 필드 (`xsm/cli.py:215-234`)

`inbound`(Claude 수신 예측), `native`(예측 등급), `scope`, `scope_reason`, `addressable`, `interrupted`(Codex Esc 중단). 모두 조회 시 계산이며 포인터에 저장되지 않는다.

미등록 세션 행(`registry.unregistered`, `xsm/registry.py:713-769`)은 `registered: False`, `state: "unknown"`, `why`, `native_start`(Claude `procStart`), `fresh`를 붙인다.

## 2. 동명 동료 구분에 지금 쓸 수 있는 정보

### 이미 있다

| 정보 | 있는 곳 | 근거 |
|---|---|---|
| 홈 구분 | `name@alias`, `alias` 필터 | resolve.py:126-132 |
| 안정 핸들 | `ref`(6 hex), `runtime:<session_id>` 주소 | resolve.py:58-70, identity.py:83-88 |
| 실행 세대 힌트 | `pid` + `lstart`(및 Codex `mcp_pid`+`mcp_lstart`) | identity.py:154-182, config.py:281-289 |
| 대화 상태 | `state`(live/ended/stale/unknown) | registry.py:212 |
| 대화 경계 | `session_id`; resume해도 불변 | identity.py:83-88, registry.py:46-49 |
| 폴더 | `cwd`, 그리고 그로부터 계산되는 repo 스코프 | registry.py:42, config.py:142-163,355-359 |
| 마지막 등록 시각 | `updated` | registry.py:44 |
| Esc 중단 표시 | `interrupted` (Codex 한정, rollout tail) | cli.py:230-234, registry.py:155-188 |

### 없다

| 정보 | 사실 | 근거 |
|---|---|---|
| 업무/doing | 레코드·resolve 어디에도 필드 없음. worker의 `pending_task`/`task_id`는 xsm이 띄운 worker 파일에만 있다 | workers.py:575-580 |
| repo 이름 | 저장하지 않음. 조회할 때마다 `git rev-parse`로 계산 | config.py:142-163 |
| branch | `xsm/*.py` 전체에서 branch를 읽는 코드 없음(주석/docstring의 단어뿐). `rev-parse HEAD`는 설치기 repo 자기 검사에만 | install.py:429 |
| busy/idle | 디렉터리 필드 없음. `busy`는 데몬이 `thread/queue/start`에 답할 때의 outcome일 뿐 | codex_daemon.py:34,54 |
| 활동 시각 | `updated`는 마지막 훅 등록 시각. 마지막 대화 활동이 아니다 | registry.py:44 |
| 머신 | 원격은 `peer` 라벨·`origin`으로 다루며 세션 레코드에 machine 필드가 없다 | remote.py:144-149, 417-418 |

## 3. 업무·branch 추출을 넣는다면 읽을 수 있는 실제 경로

1. **repo/branch (git)** — `probe.git(cwd, "rev-parse", ...)`가 이미 스코프 계산에 쓰인다(`config.py:151-153`). branch는 지금 아무도 읽지 않으므로 `rev-parse --abbrev-ref HEAD` 같은 호출을 새로 넣어야 한다(제안이며 미구현). git 호출은 `probe.quick` 예산 안에서 폴더당 한 번 기억된다(`probe.py:74-80`, `config.py:161-162`).
2. **Codex 업무 텍스트** — rollout JSONL. `registry.codex_rollout(home, thread_id)`가 `state_5.sqlite`의 `rollout_path`로 경로를 얻고, 없으면 `sessions/**/rollout-*-<id>.jsonl` glob으로 찾는다(`registry.py:132-149`). **bounded tail 선례가 이미 있다**: `codex_interrupted`가 `ROLLOUT_TAIL = 256*1024`만 seek해서 읽는다(`registry.py:152,167-188`). 업무 추출도 이 tail 읽기를 재사용할 수 있다.
3. **xsm worker task** — `<XSM_HOME>/workers/<name>.json`의 `pending_task`/`task_id`(`workers.py:575-580`)와 `<XSM_HOME>/attempts/<key>.json`의 task 텍스트(200자로 절단, `attempts.py:85`). xsm 소유이고 작은 JSON이라 LLM 없이 읽힌다. 단 xsm이 띄운 worker에만 해당한다.
4. **Claude 업무 텍스트 (미확인)** — Claude 네이티브 레코드 `_claude_native`는 `name`·`socket`·`nameSource`·`sessionId`만 읽는다(`registry.py:100-112`). 훅 입력의 `transcript_path`는 `<home>/projects/…` 위치 판정에만 쓰이고(`receive.py:49-51,65-66,81-82`) **레코드에 저장되지 않는다**. 따라서 이름→핸들 해석 시점에는 transcript 경로가 없고, Claude transcript tail을 읽는 코드도 현재 없다. 추출기 도입 시 이 경로를 어디서 복원할지가 미결이다.

## 4. resume / rename / pid 재사용 / ref 충돌 — 현재 코드의 구분

| 사건 | 현재 구분 방식 | 못 하는 경우 |
|---|---|---|
| resume | `session_id`·`ref` 불변, 재등록 시 `ended_at`/`end_reason` 제거(`registry.py:46-51`). reach는 `pid`+`lstart`까지 같아야 유지되어 resume이면 끊긴다(`config.py:281-289`) | 같은 `session_id`가 두 홈에 있으면 포인터 파일 하나로 합쳐진다(키가 runtime+session_id 뿐, `registry.py:23-25`). `mark_ended` docstring이 이 문제를 명시(`registry.py:777-788`) |
| 같은 pid의 새 대화 | Claude `/clear`·`--resume`: `native_session_id != session_id`면 `state=ended`, `end_reason=superseded`(`registry.py:220-225`) | Codex에서 같은 데몬 pid 아래 `/new`로 스레드가 바뀌면, 레코드의 `mcp_pid` 생존으로 `thread_replaced`를 판정(`identity.py:169-182`)하되 beacon이 없으면 pid 판정으로 떨어진다 |
| rename | 이름은 정체성이 아니다. Claude는 조회 시 네이티브 이름을 다시 읽는다(`registry.py:198-202`). `name_source != user`면 바뀔 수 있다고 표시(`cli.py:305-310`) | 업무 필드가 없어 "같은 대화, 다른 업무"는 구분 대상 자체가 아니다 |
| pid 재사용 | `ps`의 `lstart`를 비교해 다르면 `stale`/`ended`(`identity.py:154-159`). beacon은 `mcp_lstart`로 따로 본다(`identity.py:178-182`) | `ps`가 거부되는 샌드박스(Codex)에서는 비교 불가 → `live_unverified`. 판정 불가는 죽음으로 읽지 않는다(`identity.py:146-148,160-162`) |
| ref 충돌 | `resolve`가 같은 `ref` 레코드가 2개 이상이면 `ambiguous`로 거부하고 session id로 지정하게 한다(`resolve.py:71-83`). `add_reach`도 실행 중 2개면 거부(`config.py:576-583`) | 쓰기 시점(`upsert`)에는 검사가 없다. 충돌 감지는 전체 레코드 스캔이 필요한 조회 시점에만 일어난다(주석: 약 1.1만 회 합성 시도에서 충돌, `resolve.py:70-71`) |

동명 동료가 **같은 홈 안에 둘**이고 둘 다 live면 `resolve`는 `ambiguous`로 실패하고 후보를 돌려준다(`resolve.py:135-137`). 즉 지금은 "업무로 골라내기"가 아니라 "고르지 않고 실패하기"다. ADR-0017의 `A17-01`(업무·branch로 후보를 찾고 실제 핸들과 일치)은 이 지점을 바꾸는 작업이다.

## 5. 미확인

- branch 추출을 넣는다면 정확한 git 명령·호출 위치·캐시 키는 정하지 않았다(위 3절의 `--abbrev-ref`는 제안일 뿐 코드에 없다).
- Claude transcript tail을 이름→핸들 시점에 읽을 수 있는지 확인하지 못했다(경로가 레코드에 없음). 실제 `~/.claude/projects/**` 레이아웃도 이번에 열어 보지 않았다.
- 각 하네스 샌드박스에서 `ps`가 실제로 거부되는지는 코드 주석의 측정 기록에 근거할 뿐, 이번 세션에서 재측정하지 않았다.
- `alias`가 서로 다른 두 홈 경로에서 충돌하는(둘 다 basename이 같음) 실제 사례가 있는지 확인하지 않았다.
- Reason의 "상태 지속 시간"·doing과 xsm `updated`/`interrupted`의 대응 관계는 이번에는 코드 근거로만 봤고 실측 대조는 하지 않았다.
- 이 문서는 읽기 전용 조사라 테스트를 실행하지 않았다. G05가 요구하는 추출 실패 시 기본 통신 유지, 제외 경로 일관성은 검증하지 않았다.

## 근거 코드

`xsm/registry.py`, `xsm/identity.py`, `xsm/resolve.py`, `xsm/probe.py`를 읽었다. 보조로 `xsm/cli.py`, `xsm/mcp.py`, `xsm/config.py`, `xsm/workers.py`, `xsm/attempts.py`, `xsm/adapters.py`, `xsm/codex_daemon.py`, `xsm/receive.py`, `xsm/remote.py`, `xsm/ledger.py`, `hooks/hooks.json`, `hooks/codex-hooks.json`, `docs/adr/0017-directory-and-session-lifecycle.md`, `docs/plan/reason-inspired-adrs/{plan.json,spec.md,acceptance.md,execution.md}`를 확인했다.
