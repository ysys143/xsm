# A17-05 / A19-03 현재 native caller의 local CLI/API 음성 셀

**같은 실제 repo의 symlink 표현은 registry/discovery/CLI capture API에서 일관되게 제외됐고, 두 negative 원경로는 실제 CLI parser에서도 거절됐다.** 원본 content open·post-read/hash·원장·canonical·사본·body 전송은 모두 0이다. 새 모델/native TUI는 실행하지 않았다. 이 local 셀의 근거이며 전체 A17-05/A19-03 종결을 선언하지 않는다.

[구조/판정](summary.json) · [실행 코드·원 argv](run.py) · [offline 검사기](offlinecheck.py) · [manifest](manifest.json) · [재사용 근거 SHA](reused-evidence.json) · [조건](plan.json)

## 실제 caller와 공개 계약

현재 실제 CODEX_THREAD_ID/home을 native DB의 정확한 행·자기 rollout session_meta와 비교했다. exec의 cwd와 native DB cwd는 실제 사용자 repo의 같은 realpath이며, 실제 OS ancestor Codex PID/lstart를 확인했다. raw 근거는 private root에 있다. CODEX_SANDBOX/XSM_SANDBOXED는 시작부터 없었고 지우거나 추가하지 않았다. 두 fresh private state 각각에 이 사실만으로 실제 caller record 1건을 등록했다. 실제 native DB의 이름 null도 유지했으며 basis/sure/certainty 필드를 설정하지 않았다.

실행 source는 `/private/tmp/xsm-doctor-privacy-frozen-47o6orah`이다. 공개 `files.prepare_cli(caller, request_id, body, sources, *, limits, ...)`는 CLI OS 권한으로 읽는 capture API이며 MCP 원경로 API가 아니다. 알려진 민감 이름과 공통 directory exclusion은 stat/open 전에 검사한다. CLI는 실제 `cli.main(argv)` parser→cmd_send→materials.prepare(source="cli")→files.prepare_cli 경로를 사용했다. API 서명과 원 호출/응답은 private trace에 보존했다.

## A17-05: 같은 realpath의 다른 표현

private `repo-alias` symlink만 실제 사용자 repo로 연결했다. native cwd를 새 폴더로 꾸미지 않았다. 먼저 등록한 자기 record를 보존하고 own policy에서 이 alias가 가리키는 repo만 제외했다.

| 직접 호출 API | 실제 결과 |
|---|---|
| registry.upsert, canonical/alias cwd 각각 | 두 번 모두 registered=false, excluded=true. 같은 canonical cwd로 판정 |
| directory.exclusion_status, canonical/alias | 둘 다 excluded |
| directory.discover, 실제 caller·자기 record만 입력 | candidates 빈 배열, **unknown / caller_or_policy_unverified**. 정상 공개 성공으로 세지 않음 |
| files.prepare_cli, canonical/alias의 공개 LICENSE | 둘 다 **excluded-or-unknown**, stored=false, 사본 0 |

이미 있던 자기 raw pointer는 byte 불변으로 남았다. 제외 정책이 기존 pointer를 물리 삭제했다거나 registry가 처음부터 0건이었다고 주장하지 않는다. 기존 pointer 유지와 새 upsert/공개/capture 거절을 구분한다. 이 셀은 직접 API trace이며 CLI parser 호출은 아니다.

## A19-03: 별도 제외 경로와 민감 이름

별도 private state에서는 native repo를 제외하지 않고, 직접 만든 private 폴더만 제외했다. 그 안의 합성 문서 1개와 별도 materials 폴더의 `apikey.env` 1개를 사용했다. 후자의 내용도 무작위 합성 표식이며 credential이 아니다. 생성 시 bytes에서 digest를 계산하고 파일을 닫은 뒤 exclusion을 적용했다.

| 원경로 | 직접 files.prepare_cli | 실제 cli.main parser/handler |
|---|---|---|
| own excluded/private-note | excluded-or-unknown, stored=false | exit **2**, attachment-error / excluded-or-unknown, body_sent=false, manifest_id=null |
| own materials/apikey.env | credential-path, stored=false | exit **2**, attachment-error / credential-path, body_sent=false, manifest_id=null |

실제 parser argv는 `send codex:<현재 실제 self CID> --text attachment-negative-evaluation --attachment <원경로> --request-id <고유ID> --json`이다. 실제 값은 private trace에 있다. target은 자기 실제 CID뿐이며 capture 거절이 target 처리/송신 전에 발생했다. 다른 동료에게 보내거나 깨우지 않았다.

이는 **실제 cli.main을 현재 Python worker에서 호출한 parser 경로**다. 별도 `python -m xsm` OS subprocess라고 표현하지 않는다. CLI가 자연스럽게 계산한 context는 basis=`thread_id`, sure=true였으며 값을 강제로 올리지 않았다. 직접 API에는 factual native record를 넘겼고, 그것만으로 MCP caller certainty가 검증됐다는 주장은 하지 않는다.

## 원문 미열기·무반출과 보존

준비 뒤 passive `sys.addaudithook`가 protected source의 Python/os.open을 메모리에 기록했다. event를 막거나 결과/identity/권한을 바꾸는 observer는 아니다. 두 worker의 실제 보호 원본 open event는 모두 **0건**이다. 정책 적용 뒤 원본은 stat만 했고, inode/size/mtime/mode가 생성/초기 stat과 같았다. digest는 생성 시 값이며 post-run hash가 아니다. manifest/offline 검사도 negative 원본을 열거나 hash하지 않는다.

두 state 모두 ledger/canonical/copy record/blob은 **0**이다. 실제 CLI 응답의 body_sent=false를 확인했다. 직접 capture API는 전송 API가 아니며 stored=false와 부작용 0을 확인한 것으로 구분한다. material-intent lock 등 private 준비 metadata의 존재를 사본 저장으로 세지 않는다.

기존 [hidden/outside/mode000 native 묶음](../material-boundary-native-20261029-a30cd9e0/report.md)과 변경 없는 tests/test_files.py의 symlink/Unicode collision fixture·기존 전체 회귀를 SHA로 재사용했다. 해당 fixture를 재실행하지 않았다. 이번 cwd alias는 요청받은 새 A17-05 표현 비교이며, 기존 파일 symlink-swap/Unicode fixture의 재실행이 아니다.

frozen 315파일은 불변이다. 실행 전부터 current tree의 `tests/test_workers.py`가 해당 freeze와 달랐고, 이 차이를 보존했다. 이를 수정하거나 current 135개가 freeze와 모두 같다고 보고하지 않는다. 제품·기존 script/plan/ledger/artifact·전역 설정·권한·사용자 repo 파일은 수정하지 않았다.

raw 신원·원 argv/거절·audit·원본은 `/private/tmp/exclusion-cli-native-jhehrztq`에 보존했다. 공개 manifest에는 원본에 대해 생성 digest/stat과 **미재읽기**를 명시했다. 음성 원본을 다시 열어 성공시킨 것이 아니며 추가 모델/동료 통신/권한 확대 없이 이 local 셀로 종결했다.
