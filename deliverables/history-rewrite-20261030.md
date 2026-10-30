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
