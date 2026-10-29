# A19-06 실제 두 버전 자료 검토 표본

**이 두 버전 native 표본은 통과했다.** sender가 직접 읽은 자료를 MCP caller-inline 사본으로 전달했고, reviewer는 실제 incoming `xsm_files`로 v1→v2→동일 v1 사본을 읽었다. v1 오류의 독립 지적, v2 수정 검토, 옛 사본의 bytes/digest/표식 불변을 원문과 대조했다. 전체 A19/P06 완료 판정이나 기존 ledger 변경은 하지 않았다.

## 조건·실행 범위

- 고정본 `/private/tmp/xsm-final-receipt-frozen-i3u9pms3`, [final manifest](final-source-manifest.json)의 315 files는 실행 전후 불변이다. 제품·guide·1697 결과 및 다른 QA/audit artifact를 수정하지 않았다.
- 조건 1회, 일반 factory Codex CLI 2개, 실제 관측 CLI `0.164.0`. 양쪽 기존 `.codex-3` 프로필을 사용했다. 새 model/allowedTools/trust/권한 보정이나 credential 복사·API 키 경로를 추가하지 않았다. 원래 factory의 workspace-write/approval_policy=never/ignore-user-config 조건을 유지했다.
- 실제 초기 등록 setup은 SID/PID/lstart/home/cwd 근거로 2회다. a1 역할 이름 외에 ref나 protocol 순서를 목표에 제공하지 않았다. 목표는 자료 수정 전후의 독립 검토·이전 판 연결·옛 사본 불변 확인과 표식 원문을 사본 안에만 유지하는 공유 요구였다.
- controller의 send/ACK/index·응답·metadata 보정은 0회, 추가 사람 입력/승인/클릭은 0회다. v2 수정과 새 표식 생성은 sender 모델이 수행했다. evaluator가 v2 내용이나 검토 답을 주입하지 않았다.
- 실행 100.970초, native 평가 재실행 0회다. 20분 상한 안이며 backend 내부 모델 요청 수를 CLI 실행 수로 추정하지 않는다.

| 역할 | 실제 native SID | PID / lstart | Home·MCP source |
|---|---|---|---|
| reviewer a1 | `01a184fa-1f69-7562-a5aa-1713cc800fab` | 69176 / Thu Oct 29 09:05:46 2026 | `/Users/jaesolshin/.codex-3`, 고정본 MCP PID69299 |
| sender | `01a184fa-21c2-7bd3-b7ed-28493eff68cb` | 69451 / Thu Oct 29 09:05:47 2026 | `/Users/jaesolshin/.codex-3`, 고정본 MCP PID69667 |

kernel cwd와 등록 cwd는 각각 private `review-worktree`/`repository`로 일치했다. 구체 경로·native generation·소스는 [감사 JSON](version-review-native-20261029-a19.audit.json)의 actors에 있다. 실제 single-process shared MCP 표본은 아니다.

## 버전·요청·사본 결속

| 항목 | v1 | v2 |
|---|---|---|
| 실제 request ID | `174240915e5f40cb` | `76ac365acc184574` |
| outgoing manifest ID | `a98b3e4fcab64d9b95c98f3dc256036d` | `04346cf6e1c14e8ab5765ae767a6a9d8` |
| version / previous | 1 / null | 2 / v1 manifest ID |
| manifest digest | `9505e898db637cea6a54b254a384c5ffb18e0af02768b264e3702b3e52e27dcf` | `26a25915c166d746dcd5ab6c6b2ee649b6c0b3cf02215b497e3532600c611dc4` |
| 실제 사본 bytes | 136 | 346 |
| content SHA-256 | `b7487d51474966007839be93d0f83c4411c82252fac070a906cf835ac12ff1a6` | `ecbb8a9a001f28e6a567027026493afc969e5e539836c81ea16fb3dfe7fb8d46` |
| 무작위 표식 값의 SHA-256 | `0321ef4f44de8de423df47bef73c9001df4fa151c5a64491cd43796b62430cbd` | `0e544ddd367afccad170f828727e4ecf3b7e5e0a73e08ef65efc9895a4406c82` |
| receiver storage ID | `fa3071ca01894f499b6b6bb897599c45` | `733e1e6843b14ee2bc1be385f368de31` |
| receiver entry ID | `74adf656eecb4605a6efd9db53cdf4b1` | `236693f48f1a404ea2e55ec1e7145ef9` |

두 outgoing record의 owner는 실제 sender SID이며 incoming record의 owner는 실제 reviewer SID다. Home SHA와 runtime도 실제 caller와 일치한다. 각 요청 body SHA는 해당 manifest binding과 일치하고, 두 manifest의 `input_source=caller-inline`, `sources={}`다. 실제 MCP 입력은 actor가 읽은 자료의 base64 내용이며 서버에 원 경로를 읽으라고 전달한 입력은 없다. syscall 전수 추적이 아니라 실제 API 입력·저장 record·고정 source 계약에 따른 판독이다.

표식 원문은 초기 goal이나 메시지 body에 제공하지 않았다. 실제 자료 파일과 inline attachment 및 수신 사본에만 있었고, 모든 canonical message body에서 v1/v2 표식 원문 포함은 **0건**이었다. 공개 요약은 표식의 SHA만 보존한다.

## 실제 receiver 읽기·독립 검토

1. reviewer가 v1 storage/entry를 실제 `xsm_files`로 읽었다. 반환 body는 incoming blob과 같았고 entry SHA·owner가 일치했다. `2+2=5`를 오류로 지적하고 표준 정수 계산 결과4를 독립 제시했다.
2. sender는 지적 뒤 원자료를 v2로 고치고 새 무작위 표식을 생성했다. 새 request/manifest를 만들었고 schema의 previous가 v1 manifest를 가리킨다. 자료 자체에도 이전 판·요청·manifest·content SHA의 연결을 남겼다.
3. reviewer가 v2 storage/entry를 실제 읽고 `2+2=4`가 정확함을 확인했다. 이어 **같은 v1 storage/entry를 다시** 읽었다. 두 v1 반환 body의 bytes·SHA·표식 SHA가 모두 같았다. 원경로 재열람이나 v1 새 사본 생성으로 대체하지 않았다.

실제 incoming entry 읽기는 총3회(v1·v2·동일v1 재읽기)다. 내용/소유자/해시와 reviewer 내 event 순서는 감사 JSON의 `actual_incoming_entry_reads`에 결속했다.

| 실제 reply ID | 원 reply_to | 관측 의미 |
|---|---|---|
| `370f715017f6407e` | `174240915e5f40cb` | v1 오류·136bytes·content/표식 SHA 보고. outcome 없음: 부분 회신으로 보존 |
| `fc3e76d4ff1b4159` | `76ac365acc184574` | v2 수정 정확성 및 v2 읽기 뒤 동일v1 재읽기 불변 보고, succeeded |
| `4e6dd8d3dc634ebf` | `174240915e5f40cb` | 원 v1 요청의 후속 검토까지 종결, succeeded |

두 요청과 세 실제 reply는 모두 canonical acknowledged다. v1 최초 부분 회신을 즉시 final로 바꾸지 않았다. v2 검토 후 도착한 v1 최종 회신도 원 요청 ID를 유지했다. ACK는 actor의 실제 명시 호출이며 evaluator가 대신하지 않았다.

## 호출·오류·한계

- reviewer MCP12회 / sender MCP6회, 합계18회다. sender ACK3회·reviewer ACK2회로 요청2건/회신3건을 확인했다. sender inbox1회는 v2 검토 뒤 도착한 v1 최종 회신을 회수한 호출이다.
- shell 도구13회를 합친 agent 도구 호출은31회다. 초기 등록2회와 bootstrap protocol은 agent tools/call 수에서 분리한다. initialize/tools-list의 전체 계수는 native event만으로 측정하지 않았다.
- 두 actor exit0, 실제 MCP 오류0. reviewer의 `rg` 탐색1회는 매칭 파일 없음으로 exit1이며 sandbox/권한/파일 사본 읽기 실패와 구분한다.
- **프로필 guard는 불일치했다.** config/auth metadata equality guard의 변화이며 before per-file 값이 별도 보존되지 않아 파일·작성자·원인을 확정하지 못한다. evaluator의 profile/권한 편집 명령은 없었으나 프로필 불변·완전 격리 비교라고 주장하지 않는다.
- source와 raw manifest는 불변이고, 기록된 두 native/MCP의 잔존 실행은 없다. 다른 세션·서비스는 종료하지 않았다.
- 이 결과는 A19-06의 실제 두 버전 검토 셀에 한정한다. 다른 홈/공유 MCP·모든 attachment 정책·권한 거절·retention 전체 행렬은 이 실험으로 채우지 않는다. 기존 audit/ledger나 전체1697 결과는 갱신하지 않았다.

## 보존 산출물

- [실행 script](version-review-native-20261029-a19.py), [원 결과](version-review-native-20261029-a19.json), [private raw/state manifest](version-review-native-20261029-a19.manifest.json)
- [오프라인 원문 대조 script](version-review-native-20261029-a19.audit.py), [감사 JSON](version-review-native-20261029-a19.audit.json)
- raw/state/source 자료: `/private/tmp/p13-version-review-native-30_zo4ej`, 로그 `/tmp/p13-version-review-run.log`.

새 제품 수정·추가 native 조건/자동 재실행·전체 제품 검사는 없었다. 준비/원 실행/오프라인 감사는 분리해 보존했다.
