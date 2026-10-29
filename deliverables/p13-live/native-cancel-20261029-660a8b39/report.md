# A16-07 / A18-02 native MCP 취소셀 준비 중단

**이번 한 조건에서는 native MCP 취소를 관측하지 못했다.** 소유 TUI가 새 private Git 작업폴더의 `Trust this folder?` 화면에서 멈췄다. 화면에 신뢰 결정이 저장된다고 명시됐으므로 권한·프로필 변경 금지 조건에 따라 선택하지 않고 정리했다. native CID·모델 turn·MCP 호출·표준 pending-call Esc·notifications/cancelled는 모두 0이다. 제품 취소 실패나 런타임 미지원으로 단정하지 않는다.

[조건](plan.json) · [실제 계수/검사 결과](summary.json) · [SHA/경로 manifest](manifest.json) · [PTY controller](run.py) · [기록 proxy](proxy.py) · [offline 검사기](offlinecheck.py) · [재사용 증거 SHA](reused-evidence.json)

## 실제 경로와 중단 지점

기존 [TUI/PTY harness](../codex-state-native-eval.py)의 PTY 생성·화면 기록·terminal capability 응답·표준 입력 경로를 재사용했다. MCP에는 final315 고정본 `/private/tmp/xsm-final-receipt-frozen-i3u9pms3`과 기존 투명 wire proxy를 지정했다. 현재 CLI와 실제 화면 버전은 `0.164.0`이다. 기존 `.codex-3` 구독 프로필을 그대로 사용했고 auth 값 조회/복사·새 로그인·allowedTools/권한/프로필 편집은 없다.

기존 TUI 표본의 cwd는 이미 신뢰된 제품 저장소였고, 이번 cwd는 `/private/tmp/native-cancel-yk9ht9a9/work`라는 새 private Git 폴더다. **이 평가 준비 조건의 차이로 folder trust 전제가 생겼다.** 이전 성공 조건과 같았다고 주장하거나 외부 tool-host 장애로 고정하지 않는다. 다른 cwd로 다시 실행하는 조건은 추가하지 않았다.

실제 화면은 `Trust this folder?`와 `Your trust decision will be saved.`를 표시했다. 신뢰 선택은 보내지 않았다. native provider DB의 이 고유 cwd에 대화가 생성되지 않았고 xsm proxy/MCP server도 시작하지 않았다. 초기 자연 목표는 TUI 입력으로 1회 제공됐지만 모델에 수락된 turn은 0이다.

| 관측 항목 | 결과 | 해석 |
|---|---|---|
| 소유 TUI 실행 | 1회 | 준비 화면까지 실제 실행 |
| 실제 native CID / 모델 turn / 후속 turn | 0 / 0 / 0 | 모델 재시도 0 |
| tools/call / pending wait | 0 / 0 | 취소할 실제 RPC가 아직 없음 |
| pending-call Esc / notifications/cancelled | 0 / 0 | client가 pending 취소 시 notification을 보내지 않는다는 반례가 아님 |
| MCP EOF / 원 RPC correlation | 미관측 | MCP stream 자체가 열리지 않음 |
| canonical 원문 / claim / ACK | 0 / 0 / 0 | 원문 보존·후속 회수도 미관측; 값 주입 없음 |

## 정리와 실패 계수

소유 controller에 SIGINT를 보내 준비 중단의 finally 정리를 실행했다. 이는 MCP cancellation이나 모델 취소가 아니다. trust 화면의 Ctrl-D는 소유 TUI 종료용 cleanup 입력이며 pending 도구 취소로 세지 않는다. TUI는 exit 0으로 종료됐고 MCP 취소 notification으로 간주한 kill은 0이다. 초기 controller 검색의 실행 파일명 일치가 실패해 신호를 보내지 않았으며, 실제 소유 wrapper의 PPID/명령을 검증한 뒤 정리했다. 이 평가기 정리 검색 오류도 private blocker 기록에 남겼다.

소유 wrapper PID/lstart가 종료됐고 이 고유 root를 인자로 가진 native/node 프로세스도 없다. 기존 daemon이나 사용자/제3자 세션은 종료하지 않았다. source 315파일 SHA와 config.toml/hooks.json/settings.json hash는 전후 일치한다. product/ledger/원 plan은 수정하지 않았다.

raw PTY·실행 argv/목표·실제 blocker·process 감사는 `/private/tmp/native-cancel-yk9ht9a9`에 보존했다. 공개물에는 raw 인증값·claim/ACK·가짜 wire를 만들지 않았다. 실제 wire가 없으므로 없는 correlation을 합성하지 않는다.

`offlinecheck.py`는 이 준비 중단과 SHA/잔여 검사를 검증한다. `--require-native`는 실제 native 취소 근거가 없으므로 **exit 1**이다. A16-07/A18-02의 기존 fixture·kill/resume 근거는 그대로이며 이번 표본으로 승격하지 않는다. owner는 코디네이터이고, 이 셀의 신뢰 전제가 충족된 별도 평가가 없으면 미관측이다. 이번 작업에서는 신뢰 저장·추가 조건·추가 모델 실행 없이 종결했다.
