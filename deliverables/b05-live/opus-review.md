# P06·P08·P09·P10 통합 검토 (읽기 전용, 동결 snapshot)

High는 찾지 못했습니다. 실제로 재현 가능한 Medium은 3건입니다(P08 2건, P06 1건). P09 traffic 연결부와 P10 setup fence에서는 Medium 이상을 찾지 못했습니다.

검토 범위와 한계:
- 이번 검토는 코드 읽기와 `review-evidence/` 문서 대조만 했습니다. 테스트를 실행하지 않았고, SHA나 실행 로그를 독립적으로 검증하지도 않았습니다.
- `gates/`에는 G00–G05 문서만 있습니다. 그래서 G06·G08·G09·G10은 spec.md와 acceptance.md를 기준으로 판정했습니다.

## 1) 실제 결함

### M1 [P08] MCP `xsm_owned run`이 같은 request_id에 이전 결과를 계속 돌려줘서, overloaded된 요청이 다시 실행되지 않음
- 위치: `xsm/mcp.py:1053-1078`
- 원인 1: `owned_jobs`는 키가 `(runtime, home, session_id, name, request_id)`이고 비워지는 곳이 없습니다(`mcp.py:397`, `:1056`, `:1068` 세 곳만 사용).
- 원인 2: 같은 키를 다시 호출하면 `job["result"]`나 `job["error"]`를 그대로 반환합니다. 저널을 다시 보거나 `reserve`를 다시 시도하지 않습니다.
- 재현 조건:
  1. 용량이 찬 상태에서 run을 호출합니다. `run_owned`가 `status=queued, admission=overloaded` 뷰를 반환하고(`workers.py:1655-1656`), 이 뷰가 job 결과로 고정됩니다.
  2. 용량이 비워진 뒤 같은 MCP 서버 프로세스에서 같은 id로 run을 다시 호출해도 같은 overloaded 뷰만 돌아옵니다.
  3. `retry`는 `result-ready`만(`workers.py:1766`), `reconcile`은 `unknown`만(`workers.py:1725`) 처리하므로, queued 요청을 MCP에서 다시 진행시킬 방법이 없습니다.
- 영향:
  - "busy+1은 진짜 queued" 계약이 MCP 경로에서 깨집니다. 응답은 "새 ID를 쓰지 말라"고 안내하는데(`mcp.py:1088`), 같은 ID로는 진행할 수 없습니다.
  - fingerprint에 worker id(세대)가 없습니다(`mcp.py:1053-1054`). 같은 이름으로 다시 만든 worker를 호출해도 이전 worker의 결과 캐시가 반환됩니다. 이는 "source/owner/generation이 다른 결과의 캐시 재사용 금지"에 어긋납니다.
- 증거 범위: live capacity 증거는 `workers.create_owned/run_owned`를 직접 호출했습니다(`p08-live-native-memory.json:3`). `tests/test_owned_interfaces.py`에도 overload 뒤 같은 id로 다시 run하는 경우가 없어서, MCP 경로는 검증되지 않았습니다.

### M2 [P08] 이미 종료된 native 실패가 용량을 영구히 차지해서 overloaded가 실제 상태가 아니게 됨
- 진행 경로:
  1. 종료 코드가 0이 아니면 `WorkerError`가 발생합니다(`workers.py:1552-1553`).
  2. 이 오류는 `mark_unknown`으로 처리됩니다(`workers.py:1680`).
  3. `ACTIVE`에 `unknown`이 포함되어 있어서(`owned_requests.py:22`) `_busy`가 이 요청을 계속 셉니다(`owned_requests.py:196-197`).
- 해제할 경로가 없습니다:
  - `reconcile_owned`는 종료 코드가 0이 아니면 즉시 반환합니다(`workers.py:1727-1728`).
  - `retire_context`는 unknown 상태를 거부합니다(`owned_requests.py:438-440`).
  - 그 밖에 `unknown`에서 다른 상태로 넘어가는 전이는 `save_result`뿐입니다.
- 재현 조건: 같은 owner에서 종료 코드가 0이 아닌 실패가 `max_workers`번 쌓이면(기본 4) 됩니다. 예: 구독 인증 만료, 재시도 초과 후 exit 1, exit 7을 쓰는 기존 테스트 `test_owned_native.py:181-208`. 출력이 불완전한 SIGKILL 자식도 같은 결과입니다.
- 영향:
  - 살아 있는 자식이 0개인데도 모든 새 run이 `overloaded`와 `busy=4`를 반환합니다.
  - `reserve_worker_slot`이 같은 `_busy`를 쓰므로(`owned_requests.py:257`) 기존 TUI spawn까지 막힙니다.
  - 저널을 손으로 고치지 않으면 pool을 복구할 수 없습니다.
- 판단 범위: unknown을 보수적으로 붙잡아 두는 것 자체는 설계 선택일 수 있습니다(`test_unknown_execution_is_not_rerun_or_idle_evicted`). 다만 종료가 확인된 자식을 busy로 보고하는 것은 "진짜 queued/overloaded"와 충돌합니다.

### M3 [P06] cleanup이 중간에 중단되면 그 uid의 모든 첨부 수신이 막힘
- 원인: `_remove`가 `listdir` 순서대로 자식 파일을 지운 뒤 `rmdir`합니다(`files.py:358-365`). 중간에 죽으면 `record.json`이 없는 `storage_id` 디렉터리가 남습니다.
- 확산 경로:
  1. `receive()`의 재생 스캔은 owner와 관계없이 모든 incoming 디렉터리를 `_id`와 `_document`로 엽니다(`files.py:659-665`).
  2. 깨진 디렉터리 하나에서 `FileNotFoundError`가 나면 `storage-unavailable`로 바뀌어(`files.py:684-686`) 모든 수신이 실패합니다.
  3. `cleanup`은 이 디렉터리를 오류로만 기록하고 지우지 않습니다(`files.py:773-781`). 그래서 상태가 영구적으로 남습니다.
- 재현 가능성이 높은 이유: cleanup은 수신 훅 안에서 `maybe_prune`을 거쳐 실행됩니다(`receive.py:359`, `housekeeping.py:121`). 훅 timeout으로 kill되는 것만으로 이 상태가 생길 수 있습니다. incoming 아래에 hex가 아닌 이름이 하나라도 있으면 같은 결과입니다.
- 영향: 그 머신(같은 uid 저장소)의 첨부 send가 모두 "file storage failed; body was not dispatched"로 끝납니다(`send.py:444-452`). 본문을 delivered로 위장하지는 않습니다. 이는 "partial copy storage" 계약의 가용성 쪽 결함입니다.

### Low (참고만, 위 3건과 별개)
- **CLI 파일 이름**: 원본 basename에 `:`나 제어 문자가 있으면, 안전한 별칭을 지정해도 거절됩니다(`files.py:239-240`).
- **미완성 runtime 복사본**: 임시 디렉터리 이름은 `sid + ".new-"` 접두어로 만들어지는데(`install.py:939`), prune은 `.new`로 끝나는 이름만 찾습니다(`install.py:1104`). 그래서 미완성 복사본이 정리되지 않고 디스크에 남습니다. live snapshot을 지우는 문제는 아닙니다.
- **doctor setup 섹션**: 포인터 파일 하나가 private이 아니거나 손상되면 setup 섹션 전체가 `unavailable`이 됩니다(`setup_flow.py:298`, `cli.py:1568-1572`). 잘못 보고하는 것은 아니고 unavailable로 구분됩니다.
- **owned 자식 기록 공백**: `Popen`과 `note_child` 사이(`workers.py:1526-1533`)에서 controller가 SIGKILL되면 child 기록 없이 unknown이 됩니다. 이 경우 readback이 불가능합니다(`workers.py:1740-1742`).

## 2) 남은 검증 조건 (구현 결함과 별개)

**P06**
- live 증거는 Codex 홈 두 곳이 MCP `xsm_files`로 사본을 읽고 원 request에 회신한 것까지입니다. 수신자가 Claude인 경우는 증거에 없습니다.
- 임시 파일, 숨김 파일, symlink 교체, disk full, 유니코드 충돌은 fixture 수준 주장(validation.md)이고, 저는 실행 결과를 확인하지 않았습니다.
- 원격 첨부는 명시적으로 거절됩니다(`send.py:264-265`). P12 범위입니다.

**P08**
- A16-06이 요구하는 "일반 세션과 owned 각각"의 후속 기억 대조에서, `review-evidence/`에는 owned headless 쪽만 있습니다.
- Codex argv의 `approval_policy="never"`와 `sandbox_mode="workspace-write"`, Claude의 `--permission-mode default`는 고정 인자입니다(`workers.py:1390`, `:1402`). ADR-0010:76과 일치하므로 결함은 아닙니다. 다만 증거의 "permission_adjustment: false"는 "고정 제품 인자 외에 추가 보정 없음"이라는 뜻으로 읽어야 합니다.
- MCP 경로의 capacity+1과 같은 id 재개는 검증되지 않았습니다(M1).

**P10**
- matrix 94셀은 모두 `first_roundtrip: unknown`인 격리 셀입니다.
- plugin 경로의 readback은 digest가 있기만 하면 runtime을 succeeded로 기록합니다(`setup_flow.py:262-264`). 즉 버전이 맞는지가 아니라 설치돼 있다는 관측입니다.
- 서명은 caller-provided일 때만 `match`가 되고, 실행 경로에서 서명을 넘기는 호출자는 없습니다. 그래서 실제로는 늘 `unknown`이고, 이는 계약대로입니다.

**P09**
- 이번에는 traffic/inbound/strict 복구 연결부만 읽었습니다. 본문, 이름, reply-to, 첨부 renderer 전체에 대한 출처 표시 감사는 다시 하지 않았고, 첨부 요약의 `display_text` 경로만 확인했습니다.
- 실제 사용자 config에서 strict를 켜고 운용한 기록은 없습니다.

**공통 미완 (통과로 확장하면 안 됨)**
- Native UI 답 대기, 서로 다른 NAT, UDP 차단, proxy, 자체 relay, C 원격, D12 백엔드 선택은 모두 미완입니다.
- P11·P12는 이번 판정 범위가 아닙니다.

## 3) 게이트 기술 판정

| 게이트 | 판정 | 근거 |
|---|---|---|
| G06 | 미통과 (M3 열림) | MCP는 inline만 받고 CLI 경로 재검증은 CLI에서만 합니다(`materials.py:78-83`, `files.py:247-248`). 그 밖에 헤더는 refs만 실음, 알 수 없는 peer는 명시 fallback 외 거절, 본문 ID·digest·owner 결속, 1MiB/4MiB/16개/256MiB/7일 한도, 원본을 따라가지 않는 cleanup이 코드로 연결되어 있습니다. live 증거는 Codex 두 홈으로 한정됩니다. |
| G08 | 미통과 (M1·M2 열림) | 저널 순서, 결과 저장 후 모델 재실행 없는 재송신, Claude final 1개·같은 session 검사, Codex 진단 error 뒤 completed 허용과 turn.failed 거절, scope 철회 후 consent를 우회하는 경로 없음(`workers.py:1600-1614`, `send.py:330`)은 확인했습니다. A16-06의 일반 세션 쪽 증거는 폴더에 없습니다. |
| G09 | 검토 범위에서 결함 없음 | 기본은 observe이고 strict는 명시된 config에서만 켜집니다. last-valid 정책을 유지하고, 메시지 id당 한 번만 계상합니다(`handoff.py:209-233`). defer된 원본은 보존되고, 같은 id 재송신은 훅 경로(`send.py:481`과 `receive.py:544-557`)와 inbox 경로(`receive.py:1111-1127`) 양쪽에 연결되어 있습니다. renderer 전수 감사가 남았으므로 최종 통과는 아닙니다. |
| G10 | 구현 경계 결함 없음, 종결 불가 | flow·target·generation fence가 `_cas_bytes`, link 교체·삭제, snapshot, MCP 쓰기와 readback에 걸려 있습니다(`install.py:189`, `:288`, `:299`, `:924`, `:991`, `:2447-2466`). 오래된 snapshot은 retire와 live start 기준으로 보존됩니다. 그러나 첫 왕복은 모든 셀에서 미관측이고, 코드가 스스로 `G04-not-passed`와 D11 미결정을 표기합니다(`setup_flow.py:8`, `:372-375`). |