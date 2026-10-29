# 질문 응답 claims 후속 자연사용 1조건

2026-10-29 실행. **이 current 표본에서 수학 검토 3회와 handshake 1회가 완료됐고, initiator는 네 실제 답을 읽은 뒤 추가 inbox 없이 `xsm_ack`로 확인했다.** 전체 J03/J04 통과나 old 제품 대비 속도 우위의 근거로 확대하지 않는다.

## 실행 조건과 보존

- 고정본: `/private/tmp/xsm-p13-postqa-frozen-bukwksw6`. [manifest](post-qa-source-manifest.json)의 313개 파일과 실행 전후 readback이 일치했다. primary 경로는 133개다.
- 기존 [runner](natural-collaboration.py)를 [새 script](post-claims-collaboration.py)로 복사해 manifest·조건명·출력 경로만 분리했다. Actor의 launch/registration 코드는 AST가 동일하다. current 조건만 `--no-baseline --timeout 240`으로 **한 번** 실행했다.
- reviewer `.codex`, initiator `.codex-3`의 일반 native Codex 세션 두 개를 사용했다. 원래 factory MCP 이름/설정과 workspace-write·approval_policy=never·ignore-user-config 호출 조건을 그대로 유지했다. 새로운 모델/allowedTools/권한 보정은 추가하지 않았다.
- goal은 기존과 동일하다. reviewer: “이 저장소 검토 담당 a1입니다. 동료 질문을 받아 3차례 검토가 끝날 때까지 세션을 유지하세요.” initiator: “xsm으로 동료 a1을 찾아 2+2=5 제안을 검토받고 반례를 고쳐 재검토받으세요. 0+0=0 경계도 독립 검토받아 결과를 보고하세요.”
- goal에 ref·명령 순서·ACK 지시를 추가하지 않았다. MCP description의 제품 guide는 고정본에서 제공됐으며 workspace의 공통 guide도 실행 전 고정본 hash와 일치했다. 프로필·설치 지침·전역 권한 설정을 교체하지 않았다.
- controller 제품 조작은 실제 thread/PID/home 확인 후 최초 registry 등록 **2회**, reviewer의 a1 역할 이름뿐이다. 메시지 중계·ACK·index 수정은 각각 **0회**다. 등록은 agent 도구 호출 수와 따로 센다.
- MCP initialize/tools-list 등 bootstrap protocol 호출은 native event stream에 노출되지 않아 횟수가 미측정이다. 이를 agent MCP 호출 22회나 등록 2회에 합산하지 않았다.
- 기존 원본 두 조건 JSON·감사 JSON·runner는 hash가 불변이다. [새 원본 결과](post-claims-collaboration.json)도 오프라인 감사 전후 불변이다. private raw root: `/private/tmp/p13-post-claims-uwu7xsx2/post-claims-current`.

실행 명령:

```sh
PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 deliverables/p13-live/post-claims-collaboration.py --no-baseline --timeout 240
PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 deliverables/p13-live/post-claims-collaboration.audit.py
```

두 번째 명령은 기록을 읽는 오프라인 감사이며 모델/product API를 실행하지 않는다. 모델 자동 재실행은 0회다.

## 실제 업무와 ACK 대조

[감사 JSON](post-claims-collaboration.audit.json)은 정본 request/reply의 native endpoint 쌍, 원 `reply_to`, 본문/digest, 실제 MCP 반환 body와 ACK 결과를 대조한다. token 원문은 공개 요약에 싣지 않고 SHA만 남겼다. 각 회신의 정본은 최종 `acknowledged`다.

| 실제 단계 | 원문 회신의 핵심 | 답을 읽은 표면 | 후속 확인 |
|---|---|---|---|
| 준비 handshake | a1 준비 완료, 실질 검토 3회 대기 | `xsm_connect` | 반환된 claim으로 `xsm_ack`, 중간 inbox 0 |
| 제안 `2+2=5` | “4≠5…거짓”, 제안 기각 | `xsm_ask` | 반환된 claim으로 `xsm_ack`, 중간 inbox 0 |
| 수정 `2+2=4` | 같은 정의로 다시 계산, 수정안 채택 | `xsm_ask` | 반환된 claim으로 `xsm_ack`, 중간 inbox 0 |
| 독립 경계 `0+0=0` | `a+0=a`에 `a=0` 대입, 앞선 결과에 의존하지 않음 | `xsm_ask` | 반환된 claim으로 `xsm_ack`, 중간 inbox 0 |

모든 reply의 `outcome=succeeded`는 검토 수행 완료다. 최초 제안의 참/채택을 뜻하지 않는다. 요청·답 원문, 실제 ID·원 reply_to·digest 및 token SHA/event 순서는 감사 JSON에 보존했다.

## 호출 수와 마찰

| 구분 | reviewer | initiator | 합계 |
|---|---:|---:|---:|
| agent MCP 호출 | 13 | 9 | 22 |
| agent shell 도구 호출 | 3 | 3 | 6 |
| agent 도구 호출 전체 | 16 | 12 | 28 |
| inbox | 5 | 0 | 5 |
| 명시 ACK | 4 | 4 | 8 |
| 도구 오류 | 0 | 0 | 0 |

- initiator의 MCP 호출은 discover 1·connect 1·ask 3·ACK 4다. 실제 답을 읽은 뒤 ACK 사이에 inbox를 호출한 경우는 **0회**다. “불필요 inbox”는 이미 반환 body와 ACK 가능한 claim을 가진 상태에서 다시 inbox를 부르는 경우로 한정했다.
- reviewer의 inbox 5회는 검토 요청을 받는 쪽의 동작이며 initiator의 답 확인용 중복 호출과 구분한다. 이를 모두 불필요 호출로 세지 않았다.
- [이전 new 조건 감사](natural-collaboration-audit.json)의 initiator는 MCP 13회·inbox 4회였고 두 역할의 MCP 합계는 26회였다. 이번 표본은 각각 9회·0회·22회다. 같은 업무 goal의 관측 호출 수에서 답 확인용 추가 inbox 4회가 없어졌고 명시 ACK 4회는 유지됐다. 단일 후속 조건이므로 보편적 호출 수·성능 개선률을 추정하지 않는다.
- 최초 실제 반환 답 관측은 initiator 시작 뒤 **19.616초**이며 준비 handshake를 포함한다. controller polling으로 관측한 값이지 wire latency가 아니다. 수학 첫 답의 별도 정밀 시간은 기록하지 않았다.
- 조건 실행 시간은 **67.817초**로 6분 한도 안이다. 이 시간과 최초 답 시간을 old 제품 대비 속도 우위에 사용하지 않는다.

## 실패·사람 개입·종료 경계

- 두 native 프로세스는 각각 exit 0·`turn.completed`였다. tools/call 이전 native 호스트 실패는 관측되지 않았다. 자동 재실행·별도 baseline 실행은 없었다.
- 추가 사람 prompt/click/command/approval 및 OS UI 조작은 모두 0이다. 이 사실은 실제 사람 승인 UI의 성공 증거가 아니다.
- 프로필 설정 hash·인증 파일의 metadata-only guard가 불변이었다. 인증 값은 읽거나 복사하지 않았다. runtime source도 실행 전후 불변이었다.
- native 두 개와 각 MCP의 사후 `ps` readback은 모두 실행 중인 non-zombie 프로세스가 아니었다. 다른 세션이나 전역 서비스를 종료하지 않았다.
- 제품 파일·설정·권한·기존 감사기/ledger는 수정하지 않았다. 이번 후속만으로 전체 source 회귀나 전체 여정 완료를 선언하지 않는다. 새 전체 회귀의 판정은 coordinator의 같은 고정본 결과에 남는다.

감사 source는 [post-claims-collaboration.audit.py](post-claims-collaboration.audit.py), 실행 로그는 `/tmp/p13-post-claims-run.log`다. private raw event/stderr의 SHA·크기는 감사 JSON의 `private_raw_evidence`에 있다.
