# A15-01 private linked-worktree 실제 native 왕복

**A15-01의 같은 저장소·다른 linked worktree 간 추가 질문 없는 실제 왕복은 이 기능 표본에서 확인됐다.** 서로 다른 cwd의 두 일반 Codex 세션이 산술 질문/수정/독립 경계 검토 3건을 직접 왕복했고, 실제 body 수신과 canonical ACK가 모두 확인됐다. 추가 link/join/publish/grant나 사람 입력은 없었다.

원 실행 JSON의 `not-completed-original-sample`은 보존했다. 단순 문자 분류기가 1차의 복합 질문과 2차의 다음 경계 예고를 모두 boundary로 분류한 수집기 문제다. 재실행 없이 원 질문/답을 대조한 [오프라인 감사](worktree-native-20261029-a15.audit.json)는 A15-01 기능 표본을 passed로 기록한다. **formal handshake는 0회이며 A24/전체 J09 성공으로 확대하지 않는다.**

## 조건과 실제 신원/cwd 근거

- source/MCP: `/private/tmp/xsm-p13-postqa-frozen-bukwksw6`. [post-QA manifest](post-qa-source-manifest.json)의 313개 파일은 실행 전후 일치했다.
- private root: `/private/tmp/p13-worktree-native-isksjjba`. 새 fixture Git 저장소와 그 linked worktree만 사용했다. 사용자 저장소의 Git/worktree/staging은 사용하지 않았다.
- private Git seed는 `mktree`/`commit-tree`/`update-ref`로 만들었다. 기존 author 설정을 사용했고 user.email을 덮어쓰지 않았다. 사용자 저장소의 commit/index 변경은 없다. private Git 명령·cwd·exit·출력은 원 JSON에 보존했다.
- 양쪽 제품 skill/guide를 동일 고정본에서 `.agents/skills/xsm`으로 복사했다. model goal에는 내부 project/ref/명령 순서/ACK 절차를 넣지 않았다.
- 기존 성공 factory의 MCP 설정/기존 `.codex`·`.codex-3` 프로필을 사용했다. 원래 factory workspace-write/approval_policy=never/ignore-user-config 호출 조건을 유지했고, 새로운 permission/allowedTools/model override·auth 복사·로그인은 하지 않았다.

| 역할 | 실제 native CID | 실제 PID/lstart | kernel·session_meta·등록 cwd |
|---|---|---|---|
| reviewer a1 / `.codex` | `01a1844f-3bc1-7743-b51a-af2e8ebc7e16` | 62728 / Thu Oct 29 05:59:07 2026 | `/private/tmp/p13-worktree-native-isksjjba/review-worktree` |
| initiator / `.codex-3` | `01a1844f-4019-7cd1-a82e-fba08b022d3d` | 63191 / Thu Oct 29 05:59:08 2026 | `/private/tmp/p13-worktree-native-isksjjba/repository` |

두 kernel cwd와 각자의 bounded native `session_meta.cwd`가 등록 cwd와 일치했다. native 메타데이터의 CLI 버전은 양쪽 모두 **0.164.0**, source는 `exec`였다. MCP source cwd는 양쪽 모두 위 고정본이다.

두 디렉터리의 실제 Git common directory는 `/private/tmp/p13-worktree-native-isksjjba/repository/.git`으로 같았다. branch는 main/reviewer로 달랐다. 생성한 다른 저장소를 URL/폴더명만으로 편입한 것이 아니라 실제 linked worktree 관계다.

## 원문 대조와 수집기 정정

| 실제 요청/회신 | 원문에 따른 판정 | 정본 결과 |
|---|---|---|
| 1차 제안 `2+2=5` + 조기 `0+0=0` 질문 | reviewer가 제안을 기각하고 `2+2=4`, `4≠5`를 계산했다. 함께 물은 경계도 분리 판정했다. | 실제 body 수신, 원 reply_to 일치, outcome=succeeded, acknowledged |
| 2차 수정 `2+2=4` + 다음 3차 경계 예고 | reviewer가 같은 정수 덧셈 정의로 재계산해 수정안을 수용했다. “다음 3차”의 `0+0=0`은 이번 요청의 주제가 아닌 예고다. | 실제 body 수신, 원 reply_to 일치, outcome=succeeded, acknowledged |
| 3차 독립 경계 `0+0=0` | reviewer가 항등원 법칙에 a=0을 대입해 직접 유도했다. 앞선 수정안 결과에 의존하지 않았다. | 실제 body 수신, 원 reply_to 일치, outcome=succeeded, acknowledged |

`math_kind()`가 문자열에서 `0+0=0`을 먼저 찾으므로 원 자동 판정은 세 요청을 모두 boundary로 기록했다. 원 JSON/실행 script/manifest는 고치지 않았고, 별도 audit script/JSON에만 정정을 기록했다. 모델 재실행·수동 ref 교정·본문 중계·ACK/index 보정은 0회다.

## 자동 scope·발견·handshake의 구분

- initiator의 첫 실제 `xsm_ask(target="a1")`는 자연 이름으로 상대를 해석했다. 후속은 제품이 반환한 실제 상대 ref를 모델이 사용했다. controller가 주소를 전달하거나 수정하지 않았다.
- reviewer는 실제 제품 CLI `xsm list --table`로 상대를 찾았다. 명시 `xsm_discover`/`xsm_connect` 호출은 모두 0회다. 이름 해석과 기존 CLI 목록 사용을 candidate-discover API 관측으로 바꾸지 않는다.
- 세 요청의 실제 scope는 `repo:repository`였다. private `config.json`은 존재하지 않았고, last-valid snapshot도 source_exists=false였다. 추가 links/reaches/projects/scopes 값, directory publication, selected-collaboration record는 모두 없었다.
- 실제 MCP 및 shell 명령에서 link/join/reach/publish/grant/approve/setup 호출은 0회였다. controller의 제품 작업은 실제 SID/PID/home/cwd 기반 최초 등록 **2회**, a1 역할 이름뿐이다. 추가 사람 질문·명령·승인·클릭은 0회다.
- question record 세 건의 purpose는 모두 question이다. formal handshake request/상관 reply·completed 상태는 없었다. reviewer의 초기 자기소개 FYI를 formal handshake로 세지 않았다.

A15-01은 같은 repo/worktree가 추가 질문 없이 왕복하는 기준이다. 이 표본의 formal handshake 미실행을 A15-01 제품 실패로 판정하지 않는다. 반대로 이 표본으로 A24의 선택·handshake나 전체 J09를 통과시키지도 않는다. 별도 clone 자동 편입 금지의 native 음성 표본은 실행하지 않았으며 기존 fixture 반례와 분리한다.

## 호출·오류·관측 한계

- native CLI 2회, 조건 1회, 자동 재시도 0회. 총 **90.451초**로 12분 한도 안이다. 두 actor 모두 exit0이고 MCP/수신 도구 오류는 0이었다.
- agent MCP 19회: reviewer inbox4/send4/ACK3, initiator ask3/ACK4/inbox1. shell 7회를 합친 agent 도구 호출은 26회다. setup 등록 2회는 별도다.
- initiator의 inbox1은 reviewer가 먼저 보낸 자기소개 FYI를 읽고 확인한 동작이다. 답의 token 획득을 위한 중복 inbox로 세지 않았다. formal 준비 확인과도 구분했다.
- reviewer의 파일 탐색 `rg --files …` 1회는 매칭 파일 없음으로 exit1이었다. sandbox 거절·통신 실패나 제품 오류와 구분한다.
- **프로필 guard는 불일치했다.** 설정 hash 또는 auth metadata guard의 변화이며, 이 equality guard의 per-file before 값이 별도 보존되지 않아 파일/작성자/원인을 특정하지 못한다. 평가자의 profile/권한 편집 명령은 관측되지 않았지만 프로필 불변·완전 격리 비교라고 주장하지 않는다.
- 고정 source와 private raw manifest는 불변이다. native/MCP 잔존 실행 프로세스는 기록된 handle 기준 모두 없었다. 기존 QA 및 먼저 종결한 audit/ledger/closure-map의 hash도 모두 유지했다. 새 평가를 ledger에 덮어 반영하지 않았다.

## 산출물

- [원 실행 script](worktree-native-20261029-a15.py), [원 자동 결과](worktree-native-20261029-a15.json), [원 private evidence manifest](worktree-native-20261029-a15.manifest.json)
- [읽기 전용 원문 대조 script](worktree-native-20261029-a15.audit.py), [원문 대조 결과](worktree-native-20261029-a15.audit.json)
- 실행 로그: `/tmp/p13-worktree-native-run.log`. raw/native/state/private Git fixture는 위 private root에 보존했다.

제품·프로토콜·전역 설정을 추가 수정하거나 새 full 회귀를 실행하지 않았다. 추가 native 재실행은 하지 않았다.
