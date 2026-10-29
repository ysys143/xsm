# A23-07 doctor 증거 종결 감사

판정: **partial — 기존 증거만으로 전체 종결 불가**. 남은 것은 실제 활성 사용자 세션에서 doctor 실행과 같은 PID/lstart 생존·공개 진단 출력을 결속한 native 셀 하나다. 새 모델이나 실제 사용자 대상 진단은 시작하지 않았다.

## 원 기준과 source

원 ADR-0023:71과 acceptance.md:706의 요구는 “진단을 실행해도 자격 증명·초대·원문 개인정보가 공개 로그에 남지 않고 실제 사용자 세션이 종료되지 않는다”이다. acceptance는 fixture·실제 하네스·사람/독립 검토를 요구한다. 모든 프로필 전수, 새 clean 로그인/첫 모델 왕복, 모든 파일 쓰기 금지는 이 조건에 추가하지 않았다. 기능 진단은 승인된 상대/격리 fixture에서 하며 실제 동료 임의 기상도 실패 반례다.

기준은 `/private/tmp/xsm-final-receipt-frozen-i3u9pms3`이다. final-source-manifest의 **135 primary 전부 SHA-256 일치**, 누락·불일치 0이다. workspace plan과 frozen plan은 전체 hash가 다르지만 A23-07 criterion은 같다. ADR·acceptance 원문은 frozen과 동일하다. manifest·파일 hash·함수 위치는 [JSON](doctor-closure-audit.json)에 수록했다. plan/ledger 상태는 수정하지 않았다.

## 기존 근거가 증명하는 범위

| 근거 | 실제 확인된 것 | 증명하지 않는 것 |
|---|---|---|
| `tests/test_setup_flow.py:168` | 합성 token/invite/body·home이 setup report에 없고, write/active subprocess가 금지된 조건에서 관측형 출력. :159는 비허용 evidence key 거절 | 전체 doctor CLI 출력, 실제 native 사용자 생존 |
| `tests/test_install_cli_flow.py:300`, P10 matrix | 실제 CLI parser→doctor/install 서비스. 발견은 격리 fixture. owned Python reader가 doctor 후 파일 재독출·exit 0. 두 Python upgrade/live-owned-reader passed | 실제 사용자 모델 session. matrix의 doctor 저장값은 전체 stdout이 아니라 `report.setup` |
| `clean-install.diagnostic-post.json`, `clean-install.final.json` | 실제 native CLI의 MCP 등록/조회 6셀·combined 설치/제거, 91개씩 로컬 검사 | 파일명의 diagnostic은 doctor 실행을 뜻하지 않음. native 모델 0, 활성 사용자 진단 셀이 아님 |
| `p10-live/native-upgrade.json`, `runtime-readback.json` | 실제 old Codex PID 18456·MCP 18595의 동일 세대, upgrade/prune 전후 같은 대화의 reply 2건. main controller도 종료 후 같은 세대로 생존 | evaluator에 doctor 호출 없음. 이 생존을 doctor의 영향 관측으로 합칠 수 없음 |
| B05 `opus-review.md` | P10 setup fence에 Medium 이상 없음, 코드·문서 읽기 검토 및 unavailable 하향 확인 | 검토자가 실행/SHA 독립 검증은 안 했다고 명시. 실제 doctor native 셀의 검토 결과가 아님 |
| final-regression·원 로그 | 최종 고정본 Python 3.9.6 / 3.14.6 각 1697개, skip 0, OK. 두 원 로그 hash 재확인 | 비상세 로그에 개별 시험 이름 없음. 전체 회귀가 native 셀을 대신하지 않음 |

현재 source의 `cmd_doctor:1592`는 `install.doctor:2283`와 `setup_flow.doctor_report:312`에 실제 연결된다. setup report는 PID/lstart·socket stat을 수동 관측하고 `active_probe=not-run`을 반환한다. 이 섹션의 hashed-home/필드 whitelist를 전체 JSON 익명화로 확대하지 않았다. 전체 doctor는 home/path/생성 hook command 등의 운영 metadata도 출력한다. `cli.main:2924`에는 ensure_home·주기 정리·telemetry·미독 안내가 있어 setup report의 read-only 검사를 CLI 전체 무쓰기 보장으로 읽지 않았다. 이는 원 A23-07에 새 무쓰기 요구를 더하는 판단이 아니다.

P10 matrix 당시 install/setup_flow는 최종 파일 hash와 다르다. 역사상 fixture 결과를 최종 native 성공으로 승격하지 않았고, 현재 source 연결과 최종1697 회귀를 별도로 결속했다.

## 명령·raw 결속

기록된 P10 실행 명령(이번 감사에서 재실행하지 않음):

```text
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. /usr/bin/python3 -u deliverables/p10-live/eval_upgrade.py
```

결과는 `status=passed`. old request/reply는 `015e48d807f64a15 → 6f4cd3ded0814bbb`, `5137642a9a114c78 → 3b0b2802f0f44791`이고 동일 native CID의 회신이다. raw native 이벤트를 재파싱하면 old는 완료된 inbox 2/send 2, new는 inbox/ack/send 각1이며 **shell command 이벤트 0, doctor 관측 0**이다. 시작/완료 중복 이벤트를 도구 호출 두 번으로 세지 않았다. 외부 evaluator source에도 doctor 호출이 없다.

| 원 파일 | 재확인한 SHA-256 |
|---|---|
| `/private/tmp/p10-upgrade-uj5wwj7e/old.jsonl` | `aff4228b80711fc587693d3980598996bd0531b15cf073d6493fafb7a02a0952` |
| `/private/tmp/p10-upgrade-uj5wwj7e/new.jsonl` | `3e87eb7a00aa3384ef9e30a9c008fab6fe55586db3b21e515d6fb0bcdfcdc29e` |
| `/tmp/p13-receipt-final39.log` | `1f25d348f3366b7432c3773e5456b87e9fbbe7b94b135ed1bf7ff71e237608aa` |
| `/tmp/p13-receipt-final314.log` | `547316d9748a8eb0aa43a87e51f7a9defdd1f47f7338adeeb051beb3d5d60bf7` |

fixture doctor의 argv는 source상 `<sys.executable> <tests/test_install_cli_flow.py> --fixture-cli doctor --json`이다. 임시 root/env 및 doctor 전체 stdout/stderr는 matrix에 보존되지 않아 “원 실제 명령·전체 출력 확보”로 표시하지 않았다. 최종1697의 정확한 runner argv도 해당 artifact에 없어 재구성한 명령을 원 실행 명령으로 쓰지 않았다. 감사에서 실행한 hash/json/ast 확인의 실제 출력은 JSON의 `audit_verification`에 기록했다.

## 남은 native 셀의 이유

실제 활성 사용자 세션의 doctor 실행 전후 동일 PID/lstart 생존과 공개 진단 stdout/stderr를 함께 확인한 기록이 없다. **격리 reader에서 doctor를 실행한 기록**과 **실제 old-MCP가 upgrade 중 생존한 기록**은 서로 다른 관측이다. credential metadata 불변도 공개 doctor 로그의 비출력을 직접 증명하지 않는다. 따라서 기존 증거의 합성만으로 종결하지 않았다. 이는 새 모델 실행을 요구하는 결론이 아니며, 해당 실행은 하지 않았다.

이번 감사는 기존 파일·native 이벤트의 읽기 전용 분석이다. credential 원문/파일 조회, 모델/doctor/시험 신규 실행, 프로세스 신호, 계정·권한 변경은 모두 0이다. 제품·plan·ledger·기존 preparation 파일은 변경하지 않았고 감사 JSON/Markdown 두 파일만 작성했다.
