# 최종 parity 보완 v3 — partial 종결

**실제 쌍대 reply/digest 비교는 미완이다. 추가 조건이나 모델을 실행하지 않는다.** reviewer가 MCP 호출 없이 초기 평가 goal에 `needs-material` JSON을 답하고 종료했다. files 광고가 없으므로 파일 전송은 제외했고, plain sender의 최초 CLI는 종료된 a1을 대상으로 `only stopped sessions match 'a1'`, 실제 exit2를 반환했다. MCP ask·업무 request record·reply·ACK는0이다.

이는 최종1697 제품의 CLI/MCP 전달 실패로 일반화할 근거가 아니다. **수신 대기를 유지시키지 못한 reviewer goal 구성과, reviewer 종료를 관측한 뒤에도 plain fallback sender를 시작한 생존 선결 가드 누락은 평가자 준비 오류다.** 등록 완료를 files 준비나 실제 수신 가능 상태로 등치하지 않았다.

## 선결조건과 실제 결과

- frozen source·기존 `.codex-3` 홈·factory MCP/SDK sandbox·절대경로 CLI preflight는 v2 조건을 유지했다. source/ledger/plan·전역 PATH/profile/install·권한·allowedTools는 수정하지 않았다.
- v2의 body/자료 bytes를 그대로 복사했다. body SHA와 material SHA는 각각 v2와 정확히 같다. 새 표식이나 추가 본문을 만들지 않았다.
- reviewer의 actual SID/PID/home/cwd 기반 등록 뒤, 실제 raw MCP 호출과 current endpoint/reader에 결속된 capability 광고를 읽기 전용으로 확인했다. capability 파일 쓰기·가짜 상태·결과 주입은0이다.
- 준비 예산15초 안의 **5.266초에 reviewer가 exit0으로 종료**했다. 실제 첫 MCP 호출은 없고 capability observation record도0이었다. 44회 관측의 마지막 상태는 `unknown / native identity/generation unverified`였다. 이는 15초 만료까지 정상 대기한 결과가 아니라 조기 종료로 준비를 못 마친 결과다.
- 파일 pair 허용을 false로 고정해 files 전송을 하지 않았다. 이후 plain CLI 1회가 stopped target으로 거절돼 sender는 지시대로 중단했다. MCP plain 1회와 파일 두 질문은 실행하지 않았다.

reviewer가 반환한 JSON은 다음과 같았다.

```json
{"verdict":"needs-material","correct_sum":null,"body_marker":null,"file_sha256":null,"file_marker_sha256":null}
```

이것은 **harness 초기 goal에 대한 최종 답**이며 실제 peer question/reply_to와 연결된 xsm 회신이 아니다. A16-01의 실제 답으로 세지 않았다. v3 goal에 plain/files 분리와 자료부재 JSON 규칙을 덧붙인 점을 보존하며, reviewer goal이 엄밀히 v2와 동일했다고 주장하지 않는다. 앞선 조건과의 차이를 숨겨 단일 변수 실험으로 만들지 않는다.

## 실제 plain CLI 거절

절대경로 wrapper의 source/`--help`/`ask --help` 및 `--attachment/--wake/--wait/--priority` preflight는 모델 시작 전 exit0이었다. 실제 sender는 같은 body를 첨부 없이 읽어 `priority=next`, `wake=never`로 CLI ask 한 번을 호출했다.

- 실제 내부 CLI exit2, 외부 Python command exit0. 내부 실패를 외부 성공으로 바꾸지 않았다.
- 결과 `status=refused`, 이유 `only stopped sessions match 'a1'`.
- 반환된 ID `93912b0bb54d47b6`는 질문 record나 실제 전송으로 이어지지 않았다. question/handoff/copy record는 모두0이다.
- SDK sandbox 우회·identity/capability 보정·inline fallback·수동 send/ACK/index 수정은 없다.

## 전체 조건·actor 계수

| 별도 허용 조건 | native CLI launch | 실제 경계 | source/관측 보존 |
|---|---:|---|---|
| 원 v1 | 2 | 실행파일 source 사전 결속 누락, 전역 옛 parser가 ask를 거절(exit2) | [원 실패](interface-parity-native-20261029-a16.md) |
| 보정 v2 | 2 | 고정본 parser 검증 성공, 실제 caller OS 사본 뒤 files-unsupported-or-unknown/body_sent=false(exit2) | [v2 partial](interface-parity-native-v2-20261029-a16.md) |
| 최종 v3 | 2 | reviewer 첫 MCP/광고 없이 종료, plain CLI가 stopped target 거절(exit2) | 본 보고·원 raw |
| 합계 | **6** | 허용된 별도 조건3개, 자동 native 재시도0 | 이전 실패·원본은 수정하지 않음 |

backend 내부 모델 요청 수를 위 launch 수로 추정하지 않는다. v3는27.312초였고 새 native2개로15분 상한 안이다. 원 native JSONL·자동 `collected-needs-parity-readback` 표시는 보존했으며, 그 자동 표시는 조건 통과가 아니다. 추가 사람 입력은0이다.

## 남은 셀과 한계

- A16-01 plain CLI/MCP의 실제 동일 reply와 원 reply_to·ACK 대조: 미완.
- A19-01 동일 bytes의 CLI/MCP 실제 receiver file read·digest pair: 미완. v2의 own OS snapshot1개는 상대 열람이나 paired 성공이 아니다.
- A16-03 신규 priority/wake/files/reply/outcome 효과의 두 표면 native 대조는 추가하지 않았다. 기존 source/fixture/다른 native 근거는 [v2 기능표](interface-parity-native-v2-20261029-a16.md)에 범위를 나눠 기록했다.
- **실제 등록 != 실제 files capability ready**이며, readiness에는 살아 있는 reviewer도 필요하다. 이번에는 그 둘째 선결이 깨졌는데 plain fallback을 시작한 점을 숨기지 않는다.
- profile guard는 불일치했고 작성자·원인은 unknown이다. credential/profile 조회로 원인을 추측하거나 보정하지 않았다.
- 기록된 native/MCP는 사후 kernel readback에서 모두 종료돼 있었다. source135 hash는 유지했고 제품·전체 회귀·기존 완료 색인을 수정/재실행하지 않았다.

[실행 code](interface-parity-native-v3-20261029-a16.py) · [원 결과](interface-parity-native-v3-20261029-a16.json) · [원 manifest](interface-parity-native-v3-20261029-a16.manifest.json) · [offline checker](interface-parity-native-v3-20261029-a16.audit.py) · [감사/전체 조건 계수](interface-parity-native-v3-20261029-a16.audit.json)

raw/state/실제 readiness 관측은 `/private/tmp/p13-interface-parity-v3-d4vpjzwz`에 보존했다. 실행 로그는 `/tmp/p13-interface-parity-v3-run.log`다. 이것을 마지막 조건으로 종결했으며 후속 조건은 시작하지 않았다.
