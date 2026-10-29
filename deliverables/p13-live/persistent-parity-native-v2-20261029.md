# 제5조건: 준비 성공, CLI 거절 및 평가자 신원 결속 오류로 partial

실행 67.204초, TUI 1명과 sender 1명을 시작했다. 수신자의 실제 MCP wait0·files capability·live native PID/CID 확인 뒤 sender를 시작했다. 첫 plain CLI 업무질문이 sandbox guard에 거절돼 sender가 중단했다. 나머지 세 질문·재시도·MCP 대체 전송·권한 보정은 하지 않았다. 네 질문 완료와 parity/digest 쌍대 비교는 미완이며 성공 credit은 없다.

## 실제 단계

| 단계 | 실제 증거/결과 |
|---|---|
| source/CLI 준비 | privacy frozen315 전후 SHA 일치, codex-cli 0.164.0, absolute wrapper help/ask flags 확인 |
| TUI 기동 | wrapper8158/native8160, CID `01a18558-e932-70b1-92d0-743ebb5d4132`, 기존 trusted repo cwd |
| MCP 초기화 | proxy8505/server8516, initialize/tools/list 성공, 시작 stderr 빈 값 |
| 실제 준비 | native meta가 붙은 xsm_inbox(wait=0), 성공 응답 messages/claims 빈 배열, observed files v1 capability, reader8516 |
| sender 시작 | wrapper10979, 실제 thread.started CID `01a18559-5c95-73c2-8445-30d55d91ffa9`; TUI 준비 뒤 시작 |
| 첫 plain CLI | request `acc0671f703e4152`, status refused, 실제 nested CLI exit2. 외부 Python shell은 exit0이므로 성공으로 세지 않음 |
| 거절 원문 | this shell is sandboxed and cannot reach a Codex session (`codex queue` needs Codex's state DB and app server); send it with the xsm_send MCP tool: same target, kind and text |
| 통신 | runtime_reached=false, digest=null, claims/replies 빈 배열. dispatch0/reply0/ACK0/file-read0 |

## 독립적인 평가자 결함

재사용 `Actor.refresh`는 private state의 살아 있는 MCP beacon 중 사용되지 않은 단일 후보를 고른다. 이 TUI+sender 조합에서는 `used_beacons`를 빈 집합으로 시작해 기존 수신자의 MCP reader를 sender 것으로 잘못 골랐다. sender SID에 proxy PID8505/MCP8516을 결속한 원 초기등록을 그대로 보존했다. 이 등록은 올바른 sender 신원 증거가 아니며 metadata를 수정해 성공시키지 않았다. 평가자가 이 helper를 재사용하면서 수신자 beacon을 제외하지 않은 오류다.

CLI sandbox 거절은 실제 출력으로 보존하되, 잘못된 등록과 무관한 모든 제품 경로의 올바름을 입증했다고 확대하지 않는다. source/API 제품 결함 또는 정상 parity 성공이라는 판정도 내리지 않는다. 본 실행에서 source·권한·원문·ACK·결과 보정은 하지 않았다. 초기 등록의 잘못된 결속 자체는 위 평가자 오류로 명시하며 이를 '모든 metadata가 정확했다'는 주장으로 덮지 않는다.

## 수량과 보존

- native 두 actor 각각 모델 turn 시작/완료 1회. receiver actual xsm MCP call1(wait0), sender MCP call0. sender provider JSONL 완료 shell 도구4회. rollout의 custom exec 기록 각3은 서로 다른 표기 단위로 보존한다.
- 업무 시도1, dispatch0. plain MCP·파일 CLI·파일 MCP는 각0. body/file 입력 bytes와 SHA는 private raw manifest에 보존했으나 이를 canonical semantic digest 쌍대 비교로 대체하지 않았다.
- 원4조건/7 launch는 그대로 보존했다. 이번 별도 제5조건의 2 launch를 더해 누계5조건/9 native launch이며 자동 재시도0이다. 별도 version-review 등 다른 평가의 actor를 이 parity 누계에 섞지 않았다.
- TUI/proxy/server와 sender wrapper의 기록된 PID/lstart가 더 이상 살아 있지 않고 private MCP beacon도0임을 확인했다. 기존 전역 세션을 조작하지 않았다.
- 고정본315 및 기록한 현재 제품 경로 hash 불변, profile config/hooks/settings guard 동일. 사용자 repo 전체 파일 inventory는 수집하지 않았으므로 전체 파일 불변은 증명하지 않는다. 실제 actor 명령에는 read/help/ask만 있으며 사용자 repo 파일 쓰기는 관측되지 않았다.

raw: `/private/tmp/persistent-parity-v2-native-o6sv15xh`. 초기 단계 PID/status는 실행 중 result.json에 기록했다. 원 `.json/.manifest.json`의 collected 상태는 수집 상태일 뿐 성공 판정이 아니다. 최종 판정은 별도 `.audit.json`, 실제 원문/SHA는 `.audit-manifest.json`이며 모델 없는 `.audit.py`로 대조했다. 제품/plan/ledger 및 앞선 원산출물 수정 없음. 추가 모델·조건은 실행하지 않았다.
