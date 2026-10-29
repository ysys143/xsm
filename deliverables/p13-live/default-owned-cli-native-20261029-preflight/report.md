# 기본 공개 owned CLI wiring 실제 검증

판정: 관측한 Codex 기본 공개 CLI 셀 통과. child 실제 2턴/동일 CID, 새 native parent 0, 자동 모델 재시도 0회.

## 기본 경로와 실제 결과

현재 v2 고정본을 PYTHONPATH로 지정한 절대경로 /usr/bin/python3 -B -m xsm 공개 parser만 사용했다. create→run→run에 executor/reply/MCP callback 보정은 없었다. 기본 xsm MCP는 기존 활성 0.4.20 plugin에서 제공됐다. private XSM과 동일 git common-dir의 private worktree는 평가 조건이며 새 grant/trust/MCP 설정은 아니다.

| 턴 | 원 요청 ID | 실제 child CID | reply ID | outcome |
|---|---|---|---|
| first | default-cli-c1de9346-first | 01a1857d-99f2-7461-aeb8-f691c01bf02e | fc97ac5fbe6a4443 | succeeded |
| second | default-cli-c1de9346-second | 01a1857d-99f2-7461-aeb8-f691c01bf02e | 246fdc7b0efd4e94 | succeeded |

첫 child는 기존 기본 xsm MCP xsm_inbox를 1회 실제 호출했다. 두 번째 요청에는 표식을 다시 넣지 않았고 같은 CID/context에서 표식을 기억했다. 두 요청 모두 실제 JSON body/outcome, native stdout terminal event와 공개 status 결과를 대조했다. 기본 argv는 Codex exec/exec resume, approval_policy=never, sandbox_mode=workspace-write이며 임시 MCP 설정·권한 확대는 없다.

## 회신·수신·ACK의 구분

원 요청 상태는 sent이고 기본 reply transport는 sent-unconfirmed/runtime_reached=false다. CLI run/status exit3을 native 전달 성공으로 읽지 않았다. 별도로 공개 inbox에서 실제 reply 2개와 본문을 읽고 공개 ack가 두 reply ID를 확인했다. canonical reply_to/outcome과 acknowledged 상태를 확인했다. 이는 공개 CLI 소비/ACK 증거이며 부모 모델의 native UI 전달/자연 수신은 unknown으로 남긴다.

## 조건과 cleanup

부모 CID/PID/home는 기존 native session_meta/SQLite 및 private CLI who와 대조했다. sandbox marker를 제거하지 않았다. 이전 global identity probe에서는 parent-root adoption이 관측됐지만 private public who가 실제 inherited CID로 정상 결속했으며 수동 CID/metadata/upsert를 주입하지 않았다.

315 frozen source·135 current primary와 profile config 전후 SHA를 확인했다. 실제 사용자 세션은 같은 PID/lstart로 살아 있고 child execution 세대는 남지 않았다. 생성한 private worktree만 정리했으며 private XSM 상태/raw는 보존했다. source/plan/ledger·profile/credential/trust 수정과 추가 실험은 없다.

raw/의 native stdout/stderr와 check.json의 argv·MCP tool·원 요청·reply_to/outcome·ACK·정확한 SHA로 결속한다. 이번은 Codex 공개 기본 wiring 한 셀이며 Claude·clean 설치·모든 profile 전체 완료로 확대하지 않는다.
