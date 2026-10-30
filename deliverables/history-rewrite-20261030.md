# 2026-10-30 이력 재작성

`docs/references/reason-network/`와 `docs/references/reason-network.md`(비공개 CLI 분석을 포함한 Reason 상세 조사)를 공개 이력에서 지웠다. 공개된 내용은 [Reason 비교 노트](../docs/references/reason.md)다.

- 범위: 조사가 처음 들어간 PR #20의 작업부터 0.5.0 릴리스까지, `4fd7c9f` 이후의 커밋만 다시 썼다. 그 이전 커밋과 v0.4.x 태그, 다른 브랜치는 바뀌지 않았다.
- 바뀐 참조: `main`, `feat/reason-collaboration-network`, `release/0.5.0`, 태그 `v0.5.0`.
- 내용: 각 커밋의 메시지·작성자·시각과, 지운 두 경로를 뺀 파일은 그대로다. 최종 트리도 재작성 전과 같다.
- 이 저장소의 다른 기록에 적힌 아래 왼쪽 해시는 이제 공개 브랜치에 없다. 같은 커밋은 오른쪽 해시다.

| 이전 | 이후 | 커밋 |
|---|---|---|
| `b70fc67` | `0eaa0bb` | skill: split the guide by purpose, reach other machines from SKILL.md, sync the usage line |
| `092e880` | `1deecb1` | Merge pull request #20 from ysys143/feat/reason-collaboration-network |
| `4fbb225` | `2f13a04` | tests: one real shared MCP process keeps two Codex threads' inbox and attachment copies apart (A17-02, A19-02, A23-03) |
| `5773ca2` | `661ca0e` | audit: mutations for the current-HEAD rebinding; the audit is not an input of the run it audits |
| `495cc66` | `6f5f33f` | ledger: rebind to a current-HEAD full regression (1941 OK on both Pythons) |
| `3cbdd59` | `8e527bd` | tests: owned interface tests clear inherited Orca/herdr pane markers, as their siblings do |
| `a5385c0` | `921bbc4` | Merge pull request #21 from ysys143/release/0.5.0 |
| `1e85bc1` | `9d9bb86` | docs: public structure for the collaboration plan and the Reason comparison |
| `0cd2799` | `c9b80cc` | evals: another machine without SSH goes through the P2P network guide |
| `1e0159e` | `d0b0c7c` | Record collaboration and network validation |
| `12c301d` | `e507dfd` | skill: say why a sandboxed shell goes through xsm_send (the MCP server runs outside the sandbox) |
| `973c257` | `e65d7d5` | chore: release 0.5.0 |
| `b74de68` | `ee8123d` | docs: README and README_ko lead with discover, connect and ask; add CHANGELOG |
| `aef2e76` | `f1070f5` | audit: rebind fixture/process proofs to a current-HEAD full regression; register ADR21 records as bounded evidence |
| `11a2513` | `f11efdc` | Document collaboration and network decisions |

## 2026-10-30 두 번째 재작성: 계정 식별자 가리기

ADR-0021 실측 기록 두 파일에 사용자의 Claude 계정 UUID와 조직 UUID가 플러그인 경로의 일부로 들어 있었다. 파일은 지우지 않고 두 값만 `redacted-account-uuid`, `redacted-organization-uuid`로 바꿨다.

- 대상: `deliverables/adr0021/native-journey-mixed-20261029T072701Z/claude-direct-native-events.json`, `deliverables/adr0021/native-journey-samename-latest-20261029T152847Z/streaming-claude-registration.json`
- 범위: 첫 번째 재작성과 같이 `4fd7c9f` 이후의 커밋만 다시 썼다. 바뀐 참조는 `main`, `feat/reason-collaboration-network`, `release/0.5.0`, `docs/history-rewrite-map`, 태그 `v0.5.0`이다.
- 내용: 각 커밋의 메시지·작성자·시각과, 두 파일의 그 두 값 말고는 그대로다. 두 파일은 다른 곳에서 해시로 묶여 있지 않다.
- 위 표의 "이후" 열 해시도 이번에 다시 바뀌었다. 아래 표의 왼쪽이 위 표의 오른쪽이다.

| 이전 | 이후 | 커밋 |
|---|---|---|
| `0eaa0bb` | `1475744` | skill: split the guide by purpose, reach other machines from SKILL.md, sync the usage line |
| `1deecb1` | `0edc23f` | Merge pull request #20 from ysys143/feat/reason-collaboration-network |
| `2f13a04` | `f2ecc87` | tests: one real shared MCP process keeps two Codex threads' inbox and attachment copies apart (A17-02, A19-02, A23-03) |
| `4a2598f` | `d6be0df` | deliverables: map the commits rewritten to drop the detailed Reason research |
| `661ca0e` | `d4473e8` | audit: mutations for the current-HEAD rebinding; the audit is not an input of the run it audits |
| `6f5f33f` | `fa60b8a` | ledger: rebind to a current-HEAD full regression (1941 OK on both Pythons) |
| `8e527bd` | `8b2fdc3` | tests: owned interface tests clear inherited Orca/herdr pane markers, as their siblings do |
| `90a5cc9` | `278e70c` | Merge pull request #22 from ysys143/docs/history-rewrite-map |
| `921bbc4` | `ab8f173` | Merge pull request #21 from ysys143/release/0.5.0 |
| `9d9bb86` | `1844ce4` | docs: public structure for the collaboration plan and the Reason comparison |
| `c9b80cc` | `056e080` | evals: another machine without SSH goes through the P2P network guide |
| `d0b0c7c` | `7848fc4` | Record collaboration and network validation |
| `e507dfd` | `3815cd1` | skill: say why a sandboxed shell goes through xsm_send (the MCP server runs outside the sandbox) |
| `e65d7d5` | `03840b0` | chore: release 0.5.0 |
| `ee8123d` | `ccdd38b` | docs: README and README_ko lead with discover, connect and ask; add CHANGELOG |
| `f1070f5` | `1360419` | audit: rebind fixture/process proofs to a current-HEAD full regression; register ADR21 records as bounded evidence |
