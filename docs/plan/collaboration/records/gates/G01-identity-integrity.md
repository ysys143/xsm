# G01 신원·무결성 — 실행 기록

- 상태: **passed**. 1차 `failed` → 수정 라운드 → 2차 검토가 회귀 R2-1 → R2-1 수정 + P2 테스트 보강 → 3차 검토 두 축 통과. 전체 회귀 두 인터프리터 `Ran 1112 / OK`.
- revision: 수정본 = 작업 트리(커밋 `4fd7c9f` 위 미커밋 변경). 제품 버전 0.4.20.
- 실행자: 단일 구현 세션(코디네이터 겸 구현자) + 수정 라운드(서브에이전트) + R2-1·P2 보강(코디네이터 직접). 검토: Opus 5.5 3회 + reviewer 세션 3회.
- 진입 게이트 G00 `passed`. **B02(P02)의 진입을 연다.**

## 0. 최종 판정 (독립 검토 2축)

| 검토 축 | 판정 | 근거 |
|---|---|---|
| Opus 5.5 2차 | 1차 결함 전부 수정 확인 + R2-1·P2 공백 지적 | 변이 6종 검출, 조건 1 실패(당시 R2-1), 조건 2·3·4 통과 |
| reviewer 3차 | **"R2-1은 고쳐졌습니다. G01 통과에 이견이 없습니다"** | 코드 대조, 탐침 `probe_unmatched.py`(거절), 변이(조건 제거 시 FAIL), 최종 회귀 1112/OK |

**미결로 남기는 것:** F2b/IC03 경계(8절). one-yes 가드는 P01 범위로 넣었으나, 연결 적용의 승인 출처·대상 핸들·적용 결과 계약(IC03)은 P02에서 확정한다. 이 경계 확정은 사용자 결정 항목이다.

**격리 fixture로만 검증한 것:** 종료 조건 4개는 격리 fixture 통과다. 실제 하네스 셀(A17-02 공유 MCP A/B 실제 교대, A23-03 실제 비기본 홈·상속 env, A18-01 별도 프로세스·장애 주입)은 미실행이며 수용 조건 4개는 `partial`이다. 실제 세션 검증은 P13에서 한다.

## 1차 판정과 수정 라운드 (이력)

1차 구현은 독립 검토 2축에서 `failed`였다(Opus 5.5 `/tmp/xsm-g01-review-AS9zRm/review.md`, reviewer 세션 `e9708bdbc93f4cc4`). 아래가 그 결함과 수정 라운드의 처리다.

| ID | 결함 | 수정 |
|---|---|---|
| **F1** | `mcp.py`의 `_resolve`가 홈을 `CODEX_HOME or CLAUDE_CONFIG_DIR`로 판정했다. (P1) 기본 홈 서버가 다른 홈(`/homes/codex-a`)의 같은 thread 레코드를 채택해 `home=/homes/codex-a`가 되고 A23-03이 우회됐다. (P2) Claude 셸에서 띄운 Codex는 상속된 `CLAUDE_CONFIG_DIR` 때문에 자기 홈 레코드를 거절해 결과가 `None`이 됐다(spec P01.1의 '상속된 다른 하네스 env' 반례). | 홈은 **서버가 실제로 서는 프로세스**에서 정한다. `own_runtime`(pid 아래 live 레코드들의 runtime, 없으면 `identity.comm(pid)`)으로 런타임을 가른 뒤, 그 런타임의 env 변수만(`CLAUDE_CONFIG_DIR` 또는 `CODEX_HOME`) 또는 그 런타임의 기본 홈을 쓴다. thread 채택 후보도 이 홈 하나로 좁힌다(`adoptable_homes`). |
| **F4 / O-F2** | `remote.py`가 수신 측 소켓 write 직후 `remote_stored=True`를 쓰고 `ledger.py`가 그것을 `runtime_reached`로 접었다. hostB가 `queued / runtime_reached=True / receipt=None`으로 읽혔다. spec P01.4 위반이고 `remote.py:443-444` 주석과도 모순. | `runtime_reached`는 **이 머신의 영수증(`hook_taken`)**만으로 정한다. `remote_stored`는 '이 머신이 프레임을 채널에 넣었다'까지만 뜻하고 도달이 아니다. `ledger.step`과 `evidence_of` 양쪽에서 파생 규칙을 고쳤다. |
| **F5** | legacy 행(no digest) → `queued()` 재전송(`upgraded_from_legacy=True`) → `step('accepted')` → `evidence_of`가 `legacy=False, verified=True`를 냈다. 주석이 막겠다고 한 바로 그 상태. | `verified`는 `bool(digest) and not upgraded_from_legacy`. 업그레이드 표시를 `evidence_of`가 읽고 결과에 싣는다. |
| **F3** | `send.py`의 provisional 표시 검사가 `_send` 내부의 `call`(CLI가 `send.py:143`에서 만든다)에 닿지 않았다. CLI의 cwd 기반 송신은 `from_certainty`에만 남고 결과에는 표시되지 않았다. spec P01.2 '표시와 함께 유지' 미충족. | CLI 경로의 `call`이 `ctx["call"]`로 빠져나와 `send()`가 결과 note에 provisional을 싣는다. |
| **F2 / O-F4** | IC01이 약속한 '파일 읽기는 확실한 결함을 요구'가 코드에 없었다. `require_sure`를 부르는 곳은 MCP WIDENING 하나뿐이었고, `xsm_doc_endorse`는 추측된 neighbor의 `me.cwd`로 파일을 읽었다. CLI widening(cli.py join/reach/link)도 같은 가드가 없었다. | `mcp.py`에 `FILE_READING`(= `xsm_doc_endorse`)을 두고 같은 `require_sure`를 건다. CLI join/leave·reach·link에 `_unsure_ctx` 가드를 넣어 MCP와 같은 의미로 막는다(leave/unlink는 좁히는 일이라 예외). |
| **F2b** | `xsm_send`의 one-yes 경로(`connect.offer` → `connect.run` → `add_link`)가 `call.sure`를 확인하지 않았다. neighbor로 추측된 호출자가 다른 세션 ref에 기록된 yes로 링크를 적용할 수 있었다. | 재현했고(변이 검출), one-yes 연결 적용 앞에 `require_sure`를 건다. 사람이 터미널에서 직접 타이핑한 `xsm send`는 예외(그 사람 자신의 yes). |
| **O-F1 (회귀)** | 단독 Claude 세션에서 MCP 권한 도구 5개가 전부 거절됐다. Claude는 `_meta.threadId`를 보내지 않으므로 `_resolve`가 newest-live로 떨어져 `BASIS_NEIGHBOR`(provisional) → WIDENING 가드가 grant/approve/link/join/reach를 막았다. HEAD 4fd7c9f에서는 다섯 도구 모두 본래 로직까지 들어갔다. 기존 허용을 줄인 회귀. | thread id가 없는 호출에서 **이 서버와 같은 런타임이며 pid 아래 유일한 live 레코드**는 그 프로세스의 세션 자체다(Claude는 pid↔세션 1:1). 이를 `BASIS_ANCESTOR`(certain)로 올린다. 같은 pid에 후보가 여럿일 때만 newest-live(= `neighbor`)를 쓴다. |
| **O-F3** | 구 writer(4fd7c9f)가 새 필드를 지운다. 새 코드가 쓴 기록에 구 코드가 `--resend`로 `ledger.queued`를 다시 쓰면 `digest/evidence/req_version`이 사라지고, 새 reader가 `legacy: True, digest: None`으로 읽는다. | 교차 실행 결과를 기록하고 `OlderWriterTest`로 고정했다. 이 버전의 writer는 재전송 시 `evidence`/`upgraded_from_legacy`를 보존한다(구 writer의 소실은 막을 수 없다). D03 결정 지점으로 넘긴다. |
| **O-F5a** | `test_xsm.py:2505` 테스트 이름은 `...not_as_a_reach`인데 `:2515` 단언은 `runtime_reached`가 True였다(이름과 단언이 반대). | 이름을 `test_a_legacy_entry_reads_as_legacy_and_unverified`로 바꾸고, 도달 축과 legacy/unverified 축을 각각 단언하도록 정리했다. |
| **O-F5b** | `send.py:372`에서 기록된 attachments(정규화 리스트)를 다시 `request_identity`에 넣으면 `str(list)`로 재정규화돼 digest가 어긋난다(첨부를 붙이는 순간 재전송이 항상 거절). | `envelope.request_identity`가 이미 정규형인 4-튜플 manifest를 그대로 받는다. `AttachmentsResendTest`로 고정. |
| **F6 / O-F6** | `envelope.received_digest`는 `to`·첨부·송신 home이 빠진 다른 모양인데 '같은 계약'으로 표현됐다. | docstring을 '**같은 정규화 규칙, 다른 입력**'으로 정정. 두 digest를 비교하는 곳은 없다(버그 아님). |
| 주의(설계) | ledger 파일의 `evidence`는 step 맵(`{step: {ok,t}}`)인데 `status()`가 같은 키에 `{steps, runtime_reached, …}` 래퍼를 덮어 반환했다. 같은 이름 두 형태라 G06 소비자에게 위험. | 래퍼를 `delivery` 키로 분리. `evidence`는 파일의 step 맵 그대로, `runtime_reached`는 top-level로도 노출. |
| 주의(#17/#18) | `send.py:143-144`가 미등록 호출자이면 `me_context` 다음에 `registry.me()`가 또 돌아 quick 예산(3s)을 두 번 쓸 수 있었다. | 한 번의 `registry.me()`(내부적으로 `_me` 1패스) + `registry.last_identity()`로 합쳤다. 폴백 `registry.me()` 제거. |

## 0. 독립 검토 결과 (1차, 요약)

두 축이 독립으로 검토했고, 종료 조건 하나가 실패로 확정됐다.

| 검토 축 | 결론 | 핵심 근거 |
|---|---|---|
| Opus 5.5 (`/tmp/xsm-g01-review-AS9zRm/review.md`) | **failed** | 조건 3 실패(원격 수신측 소켓 write만으로 `runtime_reached=True`), 조건 4 근거 방향 오류, **회귀 O-F1** |
| reviewer 세션 (응답 `e9708bdbc93f4cc4`) | **통과 불가** | 실패 4건(F1·F3·F4·F5) + 미확인 2건 |

### 초안에서 정정한 것

- 종료 조건 3("queue 실패·소켓 write만으로 도달 아님")을 `통과` → **`실패`**.
- 종료 조건 4(구 reader 유지)의 근거를 바꾼다. 초안이 인용한 4개 테스트는 모두 "새 reader 가 구 기록을 읽는" 시험이었다. 독립 검토가 **구 코드(4fd7c9f)가 새 기록을 읽는 교차 실행**을 대신 했고, 구 `status()`·구 `resend_refusal` 이 정상 동작함을 확인했다. 그 과정에서 O-F3 이 드러났다.
- 검토가 지적한 mock 한계: `DeliveryEvidenceTest`·`LostAnswerTest` 는 한 프로세스 안에서 어댑터를 대체한다. 실제 소켓·수신 프로세스·장애 주입이 없다.

## 1. 종료 조건별 증거

| 종료 조건 (execution.md G01) | 1차 | 수정본 | 증거 |
|---|---|---|---|
| A/B 호출별 신원·홈과 원 ID/digest 일치 | 통과(격리 fixture) | 통과(격리 fixture) | `tests.test_mcp_identity.SharedServerInterleaveTest` 3개(A/B/A/B 교대에서 thread·cwd·basis·home이 호출마다 자기 것), `DifferentHomeSameIdTest`, `InheritedEnvTest`, 신규 `HomeIsTheServersOwnTest` 3개(기본 홈 서버가 다른 홈 레코드를 안 채택, 상속 `CLAUDE_CONFIG_DIR` 무시), 신규 `SingleSessionIsExactTest` 3개 |
| 200자 동일·다른 본문·다른 대상 재전송 거절 | 통과 | 통과 | `tests.test_xsm.ResendTest`의 `test_two_bodies_sharing_the_first_200_chars_are_not_the_same`, `test_swapping_reply_to_is_refused`, `test_swapping_outcome_is_refused`, `test_the_same_native_id_in_another_home_is_another_session` + `test_remote.LostAnswerTest`의 원격판, 신규 `AttachmentsResendTest` 2개(첨부 재전송이 스스로와 일치) |
| queue 실패·소켓 write만으로 런타임 도달 성공 아님 | **실패** | 통과 | `tests.test_xsm.DeliveryEvidenceTest`(신규 `test_a_legacy_entry_reads_as_legacy_and_unverified`, `test_an_upgraded_legacy_row_stays_unverified`, `test_status_keeps_the_step_map_and_the_wrapper_apart` 포함 7개), `tests.test_remote.LostAnswerTest`(신규 `test_the_receiving_machine_does_not_call_a_stored_frame_reached` 포함). 수신 측 `remote_stored`가 더 이상 `runtime_reached`가 아니다(F4). |
| 구 reader가 기존 송신 유지 | 통과(근거 방향 오류) | 통과 | **교차 실행**(1차 검토): 구 코드(4fd7c9f)의 `status()`·`resend_refusal`이 새 기록을 정상으로 읽음. 그 과정에서 O-F3(구 writer가 새 필드를 지움)이 드러났다. 이 버전의 writer 재전송은 `evidence`를 보존한다(신규 `OlderWriterTest` 2개). `test_a_legacy_record_without_a_digest_still_resends_on_the_preview`, `test_a_legacy_entry_reads_as_legacy_and_unverified`, `test_a_legacy_receipt_without_a_digest_is_not_treated_as_a_repeat`, 기존 `test_a_receipt_an_older_hook_wrote_has_no_fingerprint_and_is_not_a_repeat` |
| 전체 회귀 | 통과(두 인터프리터) | 통과(두 인터프리터) | 수정본(최종 revision): 3.14.6 `Ran 1109 tests in 183.635s / OK`(`/tmp/z314.log`), 3.9.6 `Ran 1109 tests in 183.185s / OK`(`/tmp/z39.log`), 둘 다 `EXIT=0`. 기준선 1040 → 1109(신규 69개). |

조건 1·2·4는 1차와 수정본 모두 격리 fixture 기준으로 통과다. 조건 3은 1차에서 **실패**였고 수정본에서 통과로 바뀌었다. 네 조건 모두 실제 하네스 증거는 아직 없으므로 수용 조건 판정은 `partial`이다(3절).

## 2. 변경 범위

공유 파일 통합 담당은 이 세션 하나다(단일 구현 세션). execution.md 3절의 공유 경계별로:

| 경계 | 파일 | 이번 변경 |
|---|---|---|
| 호출자 신원·탐색 | xsm/context.py(신규), registry.py, mcp.py, cli.py | `CallContext` 도입, `registry.me_context`·`last_identity`, MCP `_resolve`가 basis·certainty를 반환. 홈은 서버 자신의 런타임으로만 판정(`own_runtime`/`own_home`). CLI widening(join/reach/link)에 같은 `require_sure` 가드 |
| 원 ID·digest·증거 | envelope.py, ledger.py, send.py, receive.py, adapters.py(무변경) | 정규형·SHA-256, evidence 축, duplicate 계약. `runtime_reached`는 영수증만, `verified`는 업그레이드 legacy를 배제, `status()`는 step 맵(`evidence`)과 래퍼(`delivery`)를 분리 |
| 수신·전달 | receive.py, remote.py | hook 컨텍스트, 수신 digest, remote_sent/remote_stored(`remote_stored`는 도달 아님) |

`adapters.py`는 수정 후보였으나 변경하지 않았다: queue 성공·wake 결과는 이미 `Queued.wake`로 돌아오고, 그 값을 `send.py`가 evidence로 옮기면 충분했다. 새 영구 필드는 모두 additive(`req_version`, `digest`, `reply_to`, `outcome_req`, `priority`, `attachments`, `from_basis`, `from_certainty`, `evidence`, `runtime_reached`, `upgraded_from_legacy`, 영수증의 `req_digest`/`req_version`)다. 기존 `status`·`preview`는 그대로 남는다.

`status()`가 돌려주는 키가 하나 늘었다: `delivery`(=`evidence_of`의 래퍼 `{steps, runtime_reached, digest, req_version, legacy, verified, upgraded_from_legacy}`). `evidence`는 이제 파일의 step 맵 그대로다. 이는 영구 형식이 아니라 조회 결과의 키 이름이므로 소비자(P03 이후)는 `delivery`를 쓴다.

## 3. 수용 조건

| 조건 | 판정 | 실행한 검사 |
|---|---|---|
| A17-02 | partial (격리 fixture 통과, 실제 하네스 미실행) | SharedServerInterleaveTest, InheritedEnvTest, SingleSessionIsExactTest, ClaudeWideningThroughResolveTest, CliWideningNeedsSureIdentityTest, WideningNeedsSureIdentityTest |
| A18-01 | partial (격리 fixture 통과, 실제 하네스 미실행) | DeliveryEvidenceTest 7개, LostAnswerTest(신규 수신측 미도달 포함) |
| A18-03 | partial (격리 fixture 통과, 별도 프로세스/장애 주입 미실행) | ResendTest, DuplicateContractTest, LostAnswerTest, AttachmentsResendTest |
| A23-03 | partial (격리 fixture 통과, 실제 하네스 미실행) | DifferentHomeSameIdTest, InheritedEnvTest, HomeIsTheServersOwnTest, SingleSessionIsExactTest |

네 조건의 `closure_gates`는 G01과 G06(그리고 최종 G13)이다. 이 기록은 G01의 fixture 증거이며, 실제 하네스 셀과 G06은 아직 열리지 않았다. 조건 전체를 통과로 표시하지 않는다.

## 4. 반례 검출 (변이)

임시 복사본(실제 저장소 아님)에서 결함을 되돌려 새 검사가 실패하는지 확인했다. 1차 라운드 변이 6개는 모두 검출됐고, 2차 수정 라운드에서 다음 변이를 추가로 확인했다(임시 복사본 `rsync` 사본, 저장소 무변경).

| 변이 | 되돌린 곳 | 검출한 새 검사 |
|---|---|---|
| F1: 홈을 `CODEX_HOME or CLAUDE_CONFIG_DIR`로 판정 | `mcp.own_home` | `HomeIsTheServersOwnTest` 2개 FAIL(다른 홈 채택, 상속 env로 자기 홈 거절) |
| F4: `remote_stored`를 `runtime_reached`로 접음 | `ledger.step`/`evidence_of` | `test_the_receiving_machine_does_not_call_a_stored_frame_reached` FAIL |
| F5: `verified=bool(digest)` | `ledger.evidence_of` | `test_an_upgraded_legacy_row_stays_unverified` FAIL |
| F2b: one-yes `require_sure` 제거 | `send._send` | `test_a_guessed_caller_cannot_consume_a_yes_to_connect` FAIL |
| O-F5b: 정규형 manifest 재문자열화 | `envelope.request_identity` | `AttachmentsResendTest` 2개 FAIL |
| 키 충돌: `status()`가 `evidence`에 래퍼 덮어씀 | `ledger.status` | `test_status_keeps_the_step_map_and_the_wrapper_apart` FAIL + `LostAnswerTest` 5개 ERROR |

1차 라운드 변이(참고): resend가 preview만 비교 → ResendTest 4개·LostAnswerTest 2개, duplicate가 reply_to/outcome/scope 무시 → DuplicateContractTest 3개, MCP widening 가드 제거 → WideningNeedsSureIdentityTest 2개, evidence가 queue를 reached로 접음 → DeliveryEvidenceTest 3개, 다른 홈 레코드 채택 → DifferentHomeSameIdTest 1개, legacy가 verified로 읽힘 → DeliveryEvidenceTest 1개.

## 5. 정책 결정 지점 (D03)

영구 형식의 의미를 확정하는 결정은 하지 않았다. 새 필드는 additive이고 버전(`req_version`)으로 구분한다. 남은 결정 지점:

1. **원문 보존 범위** — ledger는 여전히 `preview`(200자)만 남긴다. 전체 digest는 기록하지만 원문은 아니다. 원문을 보존할지, 보존한다면 기간·암호화·cleanup은 D03 소관이다.
2. **구기록 재전송 의미** — digest 없는 구기록은 preview로만 대조한다. 그 preview 기반 대조를 계속 허용할지, 아니면 digest 없는 재전송을 거절할지가 D03의 결정이다. 현 구현은 기존 동작을 유지하는 쪽(허용)이다.
3. **evidence 형식** — `evidence` 딕셔너리의 키·버전·보존 기간을 영구 계약으로 굳히는 일은 D03에서 확정한다. 지금은 additive·관측 전용으로만 쓴다.
4. **구 writer의 필드 소실(O-F3)** — 구 버전(4fd7c9f)의 writer가 `--resend`로 `ledger.queued`를 다시 쓰면 `digest`/`evidence`/`req_version`이 사라진다. 이 버전의 writer는 재전송 시 `evidence`/`upgraded_from_legacy`를 보존하지만, 구 writer의 소실은 막을 수 없다(파일 형식 수준의 문제). 섞여 도는 두 머신(K10)에서 구 writer가 새 기록을 지우는 것을 허용할지, 파일에 별도 sidecar/버전 키를 두어 구 writer가 통째로 덮지 못하게 할지가 D03의 결정이다. 현 구현은 소실을 감수하고 새 reader가 그 기록을 `legacy/unverified`로 읽는 쪽이다. 재현: `tests.test_xsm.OlderWriterTest`.  
5. **`delivery` vs `evidence` 키** — `status()` 결과의 래퍼 키를 `delivery`로 분리했다(파일의 `evidence`는 step 맵 그대로). P03 이후 소비자가 쓸 이름을 확정하는 일도 D03 소관이다.
6. **`remote_stored`의 의미** — 수신 머신이 프레임을 자기 채널에 넣었다는 표시. 이것을 도달로 셀지, 수신 측 hook 영수증만 도달로 셀지는 IC02에서 하나로 정한다. 현 구현은 영수증만 도달로 센다(수정).

## 6. 재현 명령

```sh
# 두 인터프리터, 격리 XSM_HOME, 깨끗한 env
cd <repo>
env -i PATH=/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin HOME="$HOME" \
  XSM_HOME="$(mktemp -d)/state" PYTHONDONTWRITEBYTECODE=1 \
  /opt/homebrew/opt/python@3.14/bin/python3.14 -m unittest discover -s tests -q
env -i PATH=/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin HOME="$HOME" \
  XSM_HOME="$(mktemp -d)/state" PYTHONDONTWRITEBYTECODE=1 \
  /usr/bin/python3 -m unittest discover -s tests -q
```

## 7. 이 판정이 틀릴 수 있는 지점

- 실제 하네스(공유 MCP A/B, 비기본 홈, 상속 env)는 격리 fixture로만 검증했다. execution.md는 G01의 네 조건에 실제 하네스 증거를 요구하므로, 실제 세션 시험 전에는 `partial`이다. 특히 F1/O-F1의 수정(`own_runtime`/`own_home`, 단독 레코드=`BASIS_ANCESTOR`)은 mock 없이 **실제 Codex daemon과 실제 Claude 세션**에서 다시 확인해야 한다. 실제 Claude 세션에서 MCP 권한 도구가 여전히 동작하는지, 실제 비기본 홈 서버가 자기 홈만 쓰는지는 이 fixture가 보증하지 않는다.
- A18-03은 별도 프로세스/장애 주입 셀을 요구한다. 지금은 같은 프로세스 안에서 대조했다.
- O-F1 수정은 `_resolve`가 thread id 없는 호출에서 유일한 live 레코드를 `certain`으로 올린다. 같은 pid에 서로 다른 세션의 레코드가 하나만 남아 있는 드문 경우(예: 옛 스레드가 정리되고 새 스레드가 등록되기 전)에는 그 하나가 이 호출의 세션이 아닐 수 있다. Codex 공유 daemon에서는 live 레코드가 둘 이상일 때 `neighbor`로 남으므로 이 위험이 줄지만, 실제 daemon 표본으로 확인이 필요하다.
- F2/F2b의 가드가 IC01 범위인지: 아래 8절의 판단을 참조. 정책 결정은 사용자 몫이다.
- 이 기록은 수정본에 대한 2차 검토 입력이다. 실행 계획 7절에 따라 **독립 검토(2차)가 없으면 판정이 아니다**.

## 8. F2/F2b의 범위 판단 (정책 결정은 사용자 몫)

`spec.md` P01 항목 2는 "일반 메시징의 기존 불확실 신원 대체 정책은 표시와 함께 유지한다. **허용 확대와 파일 읽기는 확실한 호출자 결속을 요구**하며 정상 통신까지 일괄 거부하지 않는다"고 적는다. `execution.md`의 IC01은 "CallContext의 home·대화·세대·식별 근거·**파일 권한과의 관계**"를 G01에서 처음 고정하는 경계로 둔다. 이 두 문장이 F2(파일 읽기 가드)를 P01/IC01 범위로 만든다. `xsm_doc_endorse`는 지금 존재하는 경로이고 `me.cwd`로 파일을 읽으므로, P01이 '파일 읽기'라 부른 그 동작이다. 첨부 전송 자체(P06/G06)는 범위 밖이지만, 문서 읽기는 아니다.

F2b(one-yes 경로가 `call.sure`를 확인하지 않음)는 판단이 갈린다. 한쪽으로는 연결 적용이 '허용 확대'이므로 P01 항목 2의 대상이다. 다른 쪽으로는 one-yes 흐름 자체가 P02(연결 의도·사람 판단)의 산출물이고 그 계약(IC03)은 G02에서 고정되므로, 여기서의 수정은 P02의 일부로 볼 수도 있다. 다만 이번 라운드에서 (a) 결함이 실재함을 재현했고(변이 검출), (b) `connect.offer`/`connect.run`이 이미 P01의 `send.py` 안에서 호출되며, (c) 가드를 한 줄로 넣을 수 있어, **수정은 P01 범위로 넣되 P02에서 IC03 계약과 함께 재검토**하도록 남긴다. P02가 연결 적용의 승인 출처·대상 핸들·적용 결과를 다시 정의하면 이 가드의 형태도 그 계약에 맞춰 바뀔 수 있다. 어느 쪽으로 확정할지는 사용자 결정이다.

## 9. 남은 미해결 (정확히 무엇이 남았는지)

- **O-F3**: 이 버전의 writer는 재전송 시 `evidence`/`upgraded_from_legacy`를 보존하지만, 구 writer(4fd7c9f)가 새 기록을 지우는 것은 막지 못한다. D03 결정 지점 4로 넘겼다.
- **실제 하네스 셀**: G01의 네 조건은 execution.md가 실제 하네스 증거를 요구한다. A17-02(공유 MCP A/B 실제 교대), A23-03(실제 비기본 홈·상속 env), A18-01(별도 프로세스/장애 주입)은 아직 미실행이다.
- **F2/F2b 범위**: 8절의 판단대로 수정은 넣었으나, IC01/IC03 경계 확정은 사용자 결정이다.

## 10. 2차 검토 반영 (reviewer 축, 응답 `fed20c1d2ce444ce`)

2차 reviewer 검토는 1차 지적 F1·F3·F4·F5·F2와 키 충돌이 모두 고쳐졌음을 확인했고, F2b를 P01 범위로 넣은 판단도 타당하다고 봤다(IC01=호출자 확실성, IC03=yes와 원 요청의 결속으로 축이 다름). 다만 O-F1 수정이 만든 **새 회귀 R2-1**을 냈다.

### R2-1 (수정 완료)

**결함:** 호출이 `_meta.threadId`로 thread를 명시했는데 그 thread의 레코드가 없고 adopt도 실패하면, pid 아래 유일한 live 레코드(다른 세션, 예: 부모 thread)가 `BASIS_ANCESTOR`/certain으로 승격됐다. 호출이 명시한 이름과 다른 세션을 확실로 표시하는 것이라 spec P01.2·IC01의 핵심을 어긴다. 1차 구현에서는 neighbor/provisional이라 거절됐으므로 O-F1 수정이 만든 회귀다.

**수정:** `xsm/mcp.py`의 유일 레코드 승격 분기에 `not self.call_thread` 조건을 넣었다. thread를 명시하지 않은 호출만 유일 레코드를 exact로 쓴다. thread를 명시했는데 맞는 레코드가 없으면(그리고 adopt도 실패하면) neighbor/provisional로 남고, 그 근거를 evidence에 적는다. O-F1(Claude 단독 세션)은 `call_thread`가 없을 때만 승격하므로 그대로 유지된다.

**반례 테스트 2개 신설** (`tests/test_mcp_identity.py`, 실제 `serve()` 경로):
- `test_a_named_thread_with_no_record_is_not_signed_as_the_only_other` — thread 명시+레코드 없음+adopt 실패 → `neighbor`, `sure=False`, xsm_grant 거절
- `test_a_named_thread_with_its_own_record_is_still_exact` — thread 명시+레코드 있음 → `thread_id`, `sure=True`

**변이 검출:** 임시 복사본에서 `not self.call_thread` 조건을 제거(R2-1 재도입)하면 새 테스트가 실패한다(`ancestor` != `neighbor`). O-F1 유지도 확인했다(같은 클래스 5개 + `SingleSessionIsExactTest` + `McpCallerIdentityTest` + `test_discovery_latency` 64개 OK).

### 테스트 공백 보강 (Opus 2차 검토 지적)

Opus 2차 검토는 F1 수정 자체는 인정하면서, 1차의 **P2 반례를 그대로 재현하는 테스트가 없다**고 지적했다. 기존 `test_a_codex_keeps_its_own_home_record_when_it_inherits_claude_config_dir`는 `CODEX_HOME`도 함께 설정해 원래 결함(`CLAUDE_CONFIG_DIR`만 상속)을 잡지 못한다. 그래서 `test_a_default_home_codex_ignores_an_inherited_claude_config_dir`을 신설했다: 기본 홈(CODEX_HOME 없음) Codex가 `CLAUDE_CONFIG_DIR`만 상속한 경우, 서버 자신의 런타임 기본 홈(`~/.codex`)을 써서 자기 레코드를 채택하는지 검사한다.

**변이 검출:** `own_home`을 `CODEX_HOME or CLAUDE_CONFIG_DIR`(F1 원래 결함)로 되돌리면 `HomeIsTheServersOwnTest` 4개 중 3개가 실패한다.

### 최종 회귀

| 인터프리터 | 결과 |
|---|---|
| 3.14.6 | `Ran 1112 tests in 143.191s` / `OK` (`/tmp/final-314.log`) |
| 3.9.6 | `Ran 1112 tests in 185.992s` / `OK` (`/tmp/final-39.log`) |

기준선 1040 → 1112(신규 72개). 두 축(Opus 5.5·reviewer)이 R2-1을 독립으로 같은 지점에서 찾았고, 둘 다 같은 수정(thread 명시 호출로 한정)을 권고했다.
