# 영속 TUI parity 별도 조건: 준비 미충족

151.325초 후 중단했다. 실제 수신 TUI 한 개만 실행했고 sender는 시작하지 않았다. plain/파일 CLI·MCP 비교, 업무질문, correlated reply, ACK는 모두 0이며 A16-01/A19-01/A16-03의 새 성공 근거는 없다. 자동 재시도·추가 조건은 없다.

## 실행과 관측

- 실제 Codex CLI 0.164.0, 이미 trusted인 현재 repository cwd. 새 trust 선택·Esc·취소·전역설정/권한 변경 없음.
- privacy 고정본 `/private/tmp/xsm-doctor-privacy-frozen-47o6orah` 315개 파일을 전후 검증했다. CLI 절대경로 wrapper의 `--help`, `ask --help`는 exit0이고 attachment/wake/priority/wait 지원을 확인했다.
- 실제 CID `01a1854a-0f56-7071-91bc-026423b57ad4`, native PID 87240. private hook record와 native SQLite의 CID/cwd를 대조했다. hook 등록 자체를 MCP 준비나 files capability 증거로 세지 않았다.
- TUI는 제품 skill/guide를 읽은 뒤 “현재 도구 목록에 xsm MCP 수신함 도구가 없어 wait=0 조회는 실행하지 못했습니다”라고 답했다. 준비 성공이라는 말로 대체하지 않았다. 실제 xsm MCP call/wire/capability 광고를 확보하지 못해 sender 시작 선결조건이 불충족이다.
- 재사용 proxy의 `folder.mkdir(mode=0o700)`은 `tui/proxies` 부모를 요구하지만 이 러너는 `tui`까지만 생성했다. 평가자 준비 결함이다. proxy wire/handles가 전혀 없고 실제 시작 오류 stderr는 확보하지 못했으므로 직접 원인까지 확정하지 않는다. 두 TUI warning을 추가 입력으로 열거나 설정을 보정하지 않았다.
- 종료는 소유 프로세스 정리이며 Esc/tool cancel을 사용하지 않았다. wrapper와 native PID의 기록된 generation이 남아 있지 않음을 확인했다. 원문·ACK·ID·인덱스·결과 보정 0.

## 보존 및 한계

이 조건은 앞선 headless 3조건/6 launch와 분리했다. parity 평가 누계는 4조건/7 native launch이며 이번 수신자 1개가 추가됐다. 별도 A19-06 등 다른 평가의 launch를 이 누계에 합치지 않았다. 원래 실패 산출물은 수정하지 않았다.

현재 repo 제품 경로의 전후 hash와 frozen 315 hash가 동일하다. profile config/hooks/settings의 저장된 전후 guard도 동일하다. 이 guard는 모든 사용자 파일이나 모든 프로필 상태의 불변을 뜻하지 않는다. hook의 permission_mode 표시는 권한 증거로 승격하지 않았다. 실제 invocation은 read-only/approval never다.

raw/state는 `/private/tmp/persistent-parity-native-tryj59qc`에 보존했다. 원 실행 JSON/manifest와 별도 offline audit JSON/manifest를 함께 보존했다. offline checker는 모델·제품 명령을 실행하지 않고 기존 raw SHA, 실제 native CID/cwd, 종료 generation과 준비 실패를 대조한다. 제품/plan/ledger 변경 및 새 전체검사는 하지 않았다. 제품 결함이라는 판정이나 parity 성공 판정은 내리지 않는다.

산출물: 같은 prefix의 `.py`, `.json`, `.manifest.json`, `.audit.py`, `.audit.json`, `.audit-manifest.json`. native rollout 사본과 PTY raw의 SHA는 audit manifest에 있다.

## 시간 상한 뒤 최종 종결

동일 raw 기준 native CID 1개, 모델 turn 시작/완료 각 1, 실제 native 도구 호출 4개(exec), xsm MCP 호출 0이다. sender/업무질문/reply/ACK는 0이다. 이전 3조건/6 launch를 보존해 실패 또는 준비 미충족 누계는 4조건/7 launch다. 전체 사용자 repo의 모든 파일 불변은 검증하지 않았으며 기록한 제품 경로 hash 불변만 확인했다. wrapper PID 87238/native PID 87240 및 해당 평가 runner/proxy가 남지 않아 추가 신호 없이 정리를 확인했다. 기존 전역 세션은 조작하지 않았다. 추가 조건·모델·재시도는 없다. 세부 수치와 실제 model은 `.closure.json`에 기록했다.
