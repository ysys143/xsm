# CLI/MCP parity 보정 v2 — partial 종결

**고정본 CLI의 실행 source/flags 선결 확인은 통과했으나 실제 CLI 자료 전송은 capability 협상에서 거절됐다.** `files-unsupported-or-unknown`, 실제 CLI exit2, `body_sent=false`다. MCP ask를 이어 실행하거나 inline fallback·capability/identity 보정·재시도를 하지 않았다. A16-01/A19-01의 쌍대 실제 답/digest 셀은 여전히 미완이다. 추가 조건은 시작하지 않는다.

## 원 평가자 오류와 보정 조건

[원 표본](interface-parity-native-20261029-a16.md)은 비한정 전역 `xsm`을 실행해 `invalid choice: 'ask'`로 실패했다. **모델 시작 전 CLI 실행파일의 고정본 결속을 확인하지 않은 평가자 준비 오류**였다. 그 원 script/결과/자동 판정/manifest는 hash가 그대로다.

사용자가 별도로 허용한 보정 v2에서만 새 private root와 절대경로 wrapper를 만들었다. 원 실패의 모델 재시도를 숨기지 않는다. 이번 v2도 조건1회·native2개·자동 재시도0이다. source/ledger/plan 및 전역 PATH/profile/install은 수정하지 않았다.

## 모델 시작 전 선결 검증

wrapper: `/private/tmp/p13-interface-parity-v2-ynmlmyr1/repository/frozen-xsm`

- `/usr/bin/python3`와 `/private/tmp/xsm-final-receipt-frozen-i3u9pms3`의 module prefix를 절대경로로 고정했다. `XSM_HOME`이 이 private 조건과 다르면 wrapper가 중단하도록 했으며, 환경을 임의의 다른 identity로 바꾸지 않았다.
- 실제 actor process와 같은 cwd/env 구성에서 wrapper `--help`, `ask --help`는 모두 exit0이었다. `--attachment`, `--wake`, `--wait`, `--priority`, `--text` 지원을 확인했다.
- module probe의 실제 경로는 `/private/tmp/xsm-final-receipt-frozen-i3u9pms3/xsm/cli.py`였다. CLI source 및 wrapper SHA와 help 원문은 [감사 JSON](interface-parity-native-v2-20261029-a16.audit.json)의 `CLI_preflight`에 있다.
- 이 사전 검사는 parser/source 확인이다. 모델 시작 전의 help 실행을 SDK sandbox 내 실제 쓰기·전송 권한 성공으로 주장하지 않는다. 실제 ask는 기존 factory SDK workspace-write/approval_policy=never 조건 안에서 수행했다. 새로운 sandbox/permission/allowedTools 보정은 없다.
- 평가 goal에는 사용자 허용대로 절대경로 CLI를 명시했다. 따라서 이 실험은 표면·실행 경로·priority/wake·답 형식을 지정한 parity 평가이며 natural 무지침 실험이 아니다.

## 실제 native caller 결과

sender는 native shell 안에서 wrapper를 통해 다음 의도의 호출을 실제 한 번 실행했다. body는 `parity-body.txt`의 원문을 읽어 넣었고 파일 경로는 sender의 private workspace 안이었다.

```text
ABSOLUTE_WRAPPER ask a1 --priority next --wake never
  --text EXACT_BODY --attachment PRIVATE_MATERIAL_PATH --wait 60
```

반환된 실제 결과:

```json
{
  "status": "attachment-error",
  "code": "files-unsupported-or-unknown",
  "request_id": "6cfb6983246644bf",
  "manifest_id": "e8496eed646e44cda918cd35bc6babaf",
  "body_sent": false
}
```

`CLI_EXIT_CODE=2`를 감싼 Python command 자체는 exit0이었다. 이를 CLI 성공으로 오인하지 않았고 controller가 원 오류를 확인해 조건을 종료했다. 거절은 file capability 경계다. 실제 오류에 OS 권한/sandbox 거절이나 caller identity 오류가 있었다고 단정하지 않는다. `unsupported-or-unknown`의 구체 원인을 reader 준비 경합 등으로 추측하지 않는다.

| 실제 관측 | 값 |
|---|---|
| CLI가 만든 caller-owned snapshot | `cli-os-read`, 129 bytes |
| content SHA | `3cad50466049851d62a25839a4789b5d707510690a35a9460b446c2f778b7f61` |
| manifest digest | `25c011920de727402e6ee68d8ae03ce5bf58014d802d4412bb077908b66c9a3d` |
| snapshot owner | 실제 sender native CID `01a1850f-4335-7260-adfa-467a245c9305`와 runtime/home SHA 일치 |
| sender 실제 PID/lstart | 19435 / Thu Oct 29 09:28:52 2026 |
| reviewer 실제 PID/lstart/CID | 19093 / Thu Oct 29 09:28:51 2026 / `01a1850f-40ac-7792-a2c6-1aac3e1cba5a` |
| Home | 양쪽 기존 `/Users/jaesolshin/.codex-3` |
| 실제 dispatch된 question/handoff | 0 / 0 |
| MCP sender ask / reviewer incoming file read / reply / ACK | 모두0 |

계획된 material binding request ID와 만들어진 outgoing 사본을 실제 전송된 질문으로 세지 않는다. 사본1개가 있다는 사실도 상대 열람의 증거가 아니다. 본문 BODY 표식과 자료 FILE 표식은 구분했으나, 쌍대 전송이 없어 받은 표식·원 reply_to·같은 실제 답을 대조할 단계에는 도달하지 못했다.

## 기능표: 현재 계약과 이 표본의 관측

표의 source/fixture 근거는 고정본에 있던 기존 검사이며 이번에 재실행하거나 새 native 셀로 세지 않았다.

| 기능 | 기존 source/fixture 계약 | CLI v2 실제 | MCP 실제 / 기존 표본과의 구분 |
|---|---|---|---|
| priority next | Codex 지원. CLI/MCP 공유 service, `tests/test_question_interfaces.py`·`tests/test_questions.py` | parser 수용, material 협상에서 중단되어 전달 효과 미관측 | 본 조건 미실행. 이전 native default-next 성공과 별도 |
| priority now | Codex 명시 unsupported. Claude next/now UDS frame은 기존 socket fixture | 선택/반복하지 않음 | Codex/Claude 새 모델을 추가하지 않음 |
| wake never | no queue/socket/wake의 passive local 저장. `tests/test_subagent_transport.py`, `tests/test_b04_interfaces.py` | flag 수용. 거절로 body가 안 나간 것을 never 전달 성공으로 세지 않음 | 본 조건 미실행. 이전 post-claims quiet 관측은 그 표본으로 유지 |
| wake auto | 기존 transport 정책, exact unloaded-subagent unsupported만 MCP route. logical wake/ID/digest 불변 | 본 조건에서 선택하지 않음 | 이전 different-parent actual auto8/ACK8 근거만 유지. CLI auto parity 신규 credit 없음 |
| files | CLI own OS read / MCP caller-inline, exact-capability·manifest/request 결속. `tests/test_file_interfaces.py`, `tests/test_materials.py` | 실제 own snapshot 생성 후 `files-unsupported-or-unknown`·body_sent=false | 본 조건 미실행. 이전 A19-06의 incoming3회 읽기는 다른 조건의 성공 |
| reply/reply_to | 실제 원 요청·native 쌍의 checked reply, receipt와 분리 | 질문 dispatch 전이라 미관측 | 미실행, 실제 답을 만들어 넣지 않음 |
| outcome | reply의 명시 succeeded/failed만 final. nonreply outcome 거절 fixture | 미관측 | 미실행, 지원 여부를 이 표본으로 바꾸지 않음 |
| 명시 ACK | 표준 claims 읽은 뒤 caller owner/generation으로 확인, 자동ACK 없음 | 받은 답 자체가 없어 ACK0 | 수동 ACK/중계/결과 보정0 |

정상 쌍대 대조라면 request/manifest ID가 각기 달라 전체 request/manifest digest는 달라질 수 있다. 같은 입력의 body SHA·자료 content SHA를 비교하고 각 ID의 canonical digest/refs 결속을 따로 검증해야 한다. 이 표본은 그 둘째 실제 전송이 없으므로 digest parity가 같다고 주장하지 않는다.

## 종료·한계·보존

- 보정 조건은20.441초, native2개·초기 actual 등록2회·자동 재시도0이었다. 오류 확인 뒤 소유 actor를 종료했다. 원 actor 종료 전 상태와 사후 kernel readback을 구분하며 잔존 native/MCP는0이다.
- 프로필 guard는 또 불일치했다. 원인·작성자는 미확정이며 credential/profile 내용을 조사하거나 추측해 보정하지 않았다.
- frozen source와 raw는 보존됐다. 제품/source135·ledger·plan 변경, 새 full 검사, 추가 MCP 대체 전송·inline fallback·또 조건은 없다.
- global 옛 CLI 원 표본과 보정 v2를 각각 보존하며, 둘 다 A16-01/A19-01의 전체 native paired cell은 미완으로 남긴다. 정상 unknown-capability 거절을 generic error 우회로 활성화하지 않는다.

[보정 script](interface-parity-native-v2-20261029-a16.py) · [원 결과](interface-parity-native-v2-20261029-a16.json) · [원 manifest](interface-parity-native-v2-20261029-a16.manifest.json) · [offline checker](interface-parity-native-v2-20261029-a16.audit.py) · [감사 결과](interface-parity-native-v2-20261029-a16.audit.json) · [post-cleanup manifest](interface-parity-native-v2-20261029-a16.audit-manifest.json)

실행 로그: `/tmp/p13-interface-parity-v2-run.log`. raw/state/동일자료·본문/고정 CLI wrapper는 `/private/tmp/p13-interface-parity-v2-ynmlmyr1`에 그대로 남겼다.
