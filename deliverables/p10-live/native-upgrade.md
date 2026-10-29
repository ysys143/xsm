# P10 실제 old-MCP/live-snapshot upgrade QA

결과: **검증됨 — 아래 로컬 범위**. 제품 소스 변경 없이 실제 구독 Codex와 실제 snapshot MCP로 실행했다.

| 확인 항목 | 관측 결과 | 판정 |
|---|---|---|
| 실제 old runtime 복사 | `~/.xsm/runtime/2389da782089`를 현재 `install.make_snapshot()`으로 고유 `/tmp`에 복사. private id `2389da782089` | verified |
| 첫 task와 실제 회신 | `015e48d807f64a15` → `6f4cd3ded0814bbb`, 본문 `P10-QA-023db9d76f-R1: 4`, 실제 old MCP 도구 호출 완료 | verified |
| 살아 있는 상태에서 upgrade | native PID `18456`, MCP PID `18595`가 살아 있을 때 CURRENT를 `c54adca61daf`로 교체 | verified |
| live snapshot prune | 실제 `prune_snapshots()` 결과 `[]`. old 경로 존재, process-table 참조 관측, 동일 MCP PID·lstart·beacon cwd 유지 | verified |
| 같은 native 대화의 두 번째 실제 회신 | `5137642a9a114c78` → `3b0b2802f0f44791`, 본문 `P10-QA-023db9d76f-R2: 42`. native CID 동일, 두 번째 본문 관측 시 old MCP PID·세대 생존 | verified |
| old 송신 조건 | 실제 `xsm_send` 2회, wake 인자 모두 없음. unsupported `never` 보정 없음 | verified |
| 추가 new-prefix 조건 | private `c54adca61daf` MCP + 기존 `.codex` home hooks. 실제 inbox → ack → correlated succeeded 회신 1회, 이 조건만 명시 quiet | verified |
| 허용 도구·권한 보정 | model/allowedTools/bypass/hook-trust 추가 없음. P06와 같은 workspace-write/never 평가 인자. 실제 사용 MCP server는 두 조건 모두 `xsm_eval`, shell 실행 0회 | verified |
| 전역 보존 | 두 home 설정 hash, global CURRENT/link, original old runtime 내용·mode 동일. credential 내용은 열지 않았으며 metadata 동일 | verified |
| 종료 후 경계 | 두 평가 CLI exit 0, 평가 native/MCP의 동일 PID·세대 생존 없음. 실제 main controller는 같은 세대로 live | verified |
| optional new CLI의 최종 turn event | quiet MCP 회신은 완료됐지만 `turn.completed`는 관측하지 못함. 해당 CLI 전체 모델 turn 완료로 확대하지 않음 | unsupported |
| 추가 kernel cwd 독립 표본 | 외부 lsof 시도는 종료 이후라 미관측. runtime readback은 평가 중 beacon cwd와 kernel PID/lstart 확인에 근거 | unsupported — 별도 강화 관측 |

## 실행과 증거

- 실행: `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. /usr/bin/python3 -u deliverables/p10-live/eval_upgrade.py`
- evaluator: [eval_upgrade.py](eval_upgrade.py)
- 원 실행 결과: [native-upgrade.json](native-upgrade.json)
- 종료 후 readback·native event 요약·로그 SHA: [runtime-readback.json](runtime-readback.json)
- private fixture: `/private/tmp/p10-upgrade-uj5wwj7e`. raw native stdout/stderr는 이 경로에만 보존했다.

첫 두 회신은 사용자가 허용한 현재 main controller의 실제 native 세션으로 기본 wake 송신했다. 추가 new-prefix 회신은 quiet storage라 별도 조건이다. task/답은 P10-QA 표식과 산술만 사용했고 relay·권한 변경은 수행하지 않았다.

첫 답은 평가 종료 뒤 실제 main controller의 후속 turn 입력에도 도착했다. [도착 대조 기록](controller-native-arrival.json)의 message ID·reply-to·native conversation·본문이 원 평가 archive와 일치한다. 이 입력의 전역 수신 판정은 `unchecked`였으므로 도착 관측만 추가하고, 검증된 발신자나 통신 권한으로 승격하지 않았다. 사용자가 추가 prompt를 넣은 표본은 아니지만 goal의 자동 계속이 있었으므로, 이를 일반 idle 세션이 스스로 깨어난 증거로 확대하지 않는다.

old MCP/native를 종료한 뒤 prune해서 성공으로 만들지 않았다. upgrade/prune와 두 번째 회신의 생존 관측을 먼저 기록했다. 이후 자신이 생성한 평가 프로세스만 finalizer 대상으로 삼았으며, 종료 후 실제 main controller의 생존·동일 세대를 별도로 확인했다. 실제 사용자·peer session 삭제나 설정 복구 작업은 하지 않았다.

이 결과는 live old snapshot 보존과 동일 old native/MCP의 upgrade 전후 왕복, 추가 new-prefix Codex 왕복에 한정한다. inactive snapshot 삭제·Claude new-prefix 실행·원격 upgrade·서명 인증을 새로 통과시킨 증거는 아니다. 기존 P06 교차 버전 증거는 이 실행과 분리해 재사용한다.
