# A18-02/J05: workspace-write 단일 조건 추가 표본

**workspace-write에서도 native tool-host 협상 실패가 남았다.** 실제 `xsm_inbox` 호출·claim은 0회이며 same-CID resume/회수/ACK/reply·정상 ACK 뒤 중복 억제는 미실행이다. A18-02/J05 필수 native 중단 표본은 미확보로 유지한다. 첫 [read-only 실패](../native-handoff-20261029-f2193749/report.md)는 보존했고 추가 자동 native 재시도는 하지 않았다.

## 한 조건만 바꾼 근거

| 항목 | 유지 / 변경 |
|---|---|
| CLI / source / auth | `/opt/homebrew/bin/codex`, 실제 `codex-cli 0.163.0`; `/private/tmp/xsm-p13-local-frozen-dn7tom1y`; 기존 `.codex-3` ChatGPT 인증 유지 |
| proxy / 제품 skill·guide / 자연 목표 | 원 표본과 byte 또는 목표 hash 일치. 평가자가 ref·명령 순서·tools/call·identity·ACK를 주입하지 않음 |
| 변경 인자 | 경로 prefix를 `<RUN>`으로 정규화한 argv 차이는 index 6의 `read-only` → `workspace-write` 한 개(`--sandbox` 값) |
| 기존 중복 config | `-c sandbox_mode="read-only"`도 원 argv 그대로 유지. native 자체 `turn_context`에서 명시 `--sandbox workspace-write`가 적용됨을 확인 |
| 실제 실행 범위 | native cwd `/private/tmp/native-handoff-workspace-adude01_/work`에 새 private git 작업 폴더. 기존 사용자 repo를 cwd/추가 writable root로 지정하지 않음 |
| 그 밖의 제약 | approval_policy=never·기존 도구/feature 제한 유지. 허용 도구 추가·profile 대체·전역 설정/권한 조정 없음 |

native가 자신의 rollout에 기록한 `sandbox_policy.type`은 실제 `workspace-write`, `network_access=false`였고 cwd는 위 private 작업 폴더였다. 이는 CLI 인자만 보고 적용됐다고 추정한 판정이 아니다. 해당 대화의 native metadata를 SQLite read-only 조회와 rollout 읽기로 확인했으며 제품 identity/index를 만들거나 보정하지 않았다.

## 원 실행 결과

실행은 UTC `2026-10-28T20:13:45.697`부터 `20:15:25.802`까지 100초의 동일한 자연 등록 관찰 예산을 사용했다. 정확한 시작/종료 시각은 [summary.json](summary.json)에 있다. MCP initialize·notifications/initialized·tools/list까지 관측됐고 `tools/call`은 0회였다. native router는 `timed out negotiating with the code-mode host`를 2회 기록했다. native stdout은 thread.started/turn.started까지이고 완료 turn·모델 답은 없다. backend 내부 모델 요청 횟수는 이 출력으로 확정할 수 없다.

| 계수 | 결과 |
|---|---:|
| 이 조건의 native CLI 호출 / native 완료 turn | 1 / 0 |
| 원 read-only 뒤 코디네이터가 배정한 조건 추가 | 1 |
| 이 run의 coordinator same-CID resume / 자동 native 재시도 | 0 / 0 |
| 추가 사람이 입력한 prompt / sender 실행 | 0 / 0 |
| 실제 tools/call / claim / ACK / correlated reply | 모두 0 |
| proxy claim 응답 보류 fault | 미도달 |

실제 native conversation은 새 조건의 원 `thread.started` ID이며 공개 요약에는 hash만 기록했다. 원 메시지 ID·xsm native consumer generation은 실제 호출 전이라 성립하지 않았다. 이를 수동으로 만들어 다음 단계에 진입하지 않았다. workspace-write 하나로 이번 호스트 협상 실패가 해결되지 않았다는 관측이며, xsm handoff 로직의 제품 결함이나 모든 Codex 환경의 미지원 판정으로 확대하지 않는다.

## 보존과 종료

raw native stdout/stderr·MCP client/server wire·private XSM_HOME·effective policy·정확한 argv 비교는 `/private/tmp/native-handoff-workspace-adude01_`에 보존했다. 공개 deliverables는 이 요약·script·hash/경로 manifest만 포함한다. claim token·실제 ACK·auth 값은 공개 보고서에 복사하지 않았다.

소유 CLI·proxy·MCP server를 PID/시작 시각으로 대조해 종료했고 잔여 own/tmp-bound 프로세스는 0이다. frozen source hash는 전후 일치했다. 다만 기존 `.codex-3/config.toml` hash는 실행 중 바뀌었고 hooks/settings hash는 같았다. 평가 명령에는 profile 설정 편집이 없으며 MCP도 initialize/tools/list만 실행했지만, 변경 주체·원인은 확인하지 못했다. 따라서 profile 불변이나 외부 조건까지 완전히 동일하다는 주장은 하지 않는다. 양쪽 invocation의 `--ignore-user-config`는 유지됐으나 이 drift를 단일 조건 비교의 별도 제약으로 남긴다. 원 hash 차이는 summary와 private result에 보존했고 전역 파일을 복원·편집하지 않았다. 제품 소스·도구 권한·기존 사용자 repo에 대한 평가자의 수정 명령은 없었다. UDP 표본을 정리한 뒤 시작한 별도 조건이며 UDP 결과를 대체하거나 변경하지 않았다.

[조건 계획](plan.json) · [요약·계수](summary.json) · [원 파일 hash/경로](manifest.json) · [실행 controller 기록](controller.py) · [동일 proxy](proxy.py)
