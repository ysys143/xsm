# P13/J03·J04 로컬 자연 사용 — 원본 2조건 감사

## 판정과 조건

두 조건 모두 실제 a1의 **서로 다른 수학 검토 3건**이 initiator에게 돌아왔고, initiator는 결과를 보고했다. 원본 자동 판정은 수정하지 않았다. 이 표본은 전체 J01–J09 완료 증거가 아니다.

- B05 최종 고정본: `/private/tmp/xsm-b05-final-cuya9ah7`, 312개 manifest 입력 검증. factory MCP와 PATH는 이 runtime에 고정했다.
- old 조건: 실제 old 0.4.20 runtime의 MCP. **양쪽 모두 cwd=현재 REPO, 공통 새 skills/xsm 문서를 읽은 보정 비교**다. old initiator는 현재 개발트리 `bin/xsm list --table`도 선택했다. 순수한 옛 제품 usability baseline으로 해석하지 않는다.
- 두 조건의 MCP descriptions는 각 runtime의 실제 제공 내용이다. 평가자가 namespace 설명·MCP-first·ref·request ID·명령 순서·대본을 목표에 추가하지 않았다.
- `--ignore-user-config` factory-only를 명시적으로 사용했고, 기존 `.codex`/`.codex-3` HOME 인증은 유지했다. workspace-write/approval never, 모델·allowedTools 보정 없음.

목표 원문은 원 결과 JSON의 `goals`에 보존했다. controller는 실제 native SID/PID/home의 최초 등록과 a1 이름 대응만 각 조건 2회 수행했다. 메시지·relay·ACK·index 보정은 0회다.

## 실제 관측

| 항목 | B05 고정 runtime | old MCP 0.4.20 + 공통 새 문서 |
|---|---:|---:|
| 실제 수학 검토/수신 | 3/3 | 3/3 |
| 준비 확인 회신 | 1 | 0 |
| agent MCP 호출 | 26 (13+13) | 14 (8+6, 마지막 대기 포함) |
| agent shell 호출 | 7 (6+1) | 9 (4+5) |
| 실제 MCP 오류 | 0 | 0 |
| 실제 shell 비정상 종료 | 0 | 1: 없는 `.agents/.codex` 경로를 rg로 찾던 exit 2 |
| sandbox shell 송신 시도 | 0 | 0 |
| 최초 실제 peer 답 | 19.926초, 준비 확인 포함 | 원 수집기에서 정확한 값 미수집 |
| 사용자 클릭/명령/승인 | 0/0/0 | 0/0/0 |
| 설정·auth metadata/runtime source | 전후 동일 | 전후 동일 |
| 종료 후 소유 native/MCP 실행 | 모두 없음 | 모두 없음 |

setup source 검증·초기 registry 등록은 위 agent 호출수에 포함하지 않았다. native 초기 initialize/list-tools 자동 RPC 횟수는 event stream에 노출되지 않아 0이라고 추정하지 않았다.

B05의 수학 질문 순서는 proposal→수정안→경계였고, old는 proposal→독립 경계→수정안이었다. 각각 다른 원 요청 ID에 실제 reply가 결속됐으며 delivery receipt만으로 답을 계산하지 않았다.

## 수집기 오분류와 실제 마찰

1. **B05의 원 자동 not-completed는 수집기 오분류다.** 수정안은 v1의 `2+2=5`를 철회하고 `2+2=4`로 고쳤다고 명시했다. 원 규칙이 옛 식을 먼저 찾아 수정안을 proposal로 분류했다. 준비 확인 1건과 수학 검토 3건을 분리해 감사했다.
2. old ledger는 `reply_to`를 저장하지 않는다. 원 수집기는 이 필드를 요구해 실제 3회 회신을 모두 누락했다. 감사에서는 실제 완료 MCP send의 인자·발신 actor·target ref·ledger 본문 preview·initiator 수신 body를 결속했다. 제품 메시지나 index를 수정하지 않았다.
3. 문서 출력에 등장한 `sandbox` 단어를 실패로 센 오류도 있었다. 실제 shell exit를 확인하니 B05 오류 0, old는 경로 탐색 exit 2 한 건이다. sandbox 송신 반례가 이 표본에서 재현됐다고 주장하지 않는다.
4. **실제 bookkeeping 마찰:** B05 initiator는 discover 1, connect 1, ask 3 외에 inbox 4/ACK 4를 수행했다. ask의 reply-copy/index와 원 inbox의 확인 상태가 분리돼 이미 읽은 답을 다시 수신·확인하는 호출 부담이 있다. reviewer는 inbox 5/ACK 4/send 4다. 이 비용을 단순 agent 오동작이나 업무 검토 4회로 세지 않는다.
5. **task 성공과 proposal 진실은 다르다.** a1은 거짓 제안을 반박하면서 검토 업무를 완료했다는 의미로 succeeded를 보냈다. B05 답에는 제안 승인이라는 뜻이 아니라는 설명도 있었다. 수정안과 0 경계는 별도로 검산했다.
6. **사전 skill 읽기는 가능했다.** B05 reviewer는 현재 SKILL·messaging·guide를 읽고, 산술 3건은 별도 Python 계산으로 확인했다. 이 shell들은 송신 우회가 아니다. B05 initiator는 파일 탐색만 한 뒤 MCP descriptions로 discover/connect/ask를 선택했다. old 양쪽은 공통 새 문서를 읽었다. 감사 시 이 문서 SHA는 B05 고정본과 같았다.
7. old reviewer는 실제 3회 답 뒤에도 재검토 차수와 독립 경계 차수를 따로 세어 다음 요청을 기다렸다. initiator 완료 후 평가 종료에서 자신의 actor만 정리했다. 원 cleanup-not-verified는 즉시 liveness 확인의 종료 경합이었고, 사후 kernel 확인에서는 소유 native/MCP가 모두 사라졌다. user/peer 세션 정리는 하지 않았다.

## 원본과 감사 증거

- [원 실행 결과](natural-collaboration.json): 자동 판정·처음 수집값을 보존.
- [감사 결과](natural-collaboration-audit.json): 원 JSON SHA, native 로그 SHA, 실제 request/reply body SHA, 수집기 오류 설명.
- [평가 코드](natural-collaboration.py): 자연 목표는 불변. 종료 후 수정은 수집기와 `--audit-existing` 관측만이며 새 native 실행 0회.
- raw native 로그는 원 JSON의 private tmp 경로에만 보존했다. 결과에 claim token이나 원 tool 인자·출력을 복사하지 않았다.

실제 제품 source·기존 프로필/권한/계정은 바꾸지 않았다. 두 소표본으로 전반적인 성공률·속도 우위·전체 J01–J09를 결론 내리지 않는다.
