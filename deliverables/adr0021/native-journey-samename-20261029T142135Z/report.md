# A21-04 self와 remote 동명 최소 표본: 선택 확인, 회신 미완

새 private 표본에서 requester와 remote reviewer를 최초 setup부터 모두 `a1`로 표시했다. 실제 MCP discover에 이름 a1 두 개가 표시됐고, 모델이 self인 로컬 Codex와 다른 머신의 Claude를 구분해 remote만 선택했다. 세 번째 후보나 제3자 다중 동명 성공으로 확대하지 않는다.

같은 후보로 실제 핸드셰이크 원문도 올바른 remote CID에 도착했다. 그러나 직접 회신과 ACK는 0건이어서 요청한 전체 표본은 미완이다. 기존 구버전 native wake hook의 별도 사본 보류 뒤 살아 있던 SDK가 수명 종료됐다. controller는 보류·본문·ACK·consent·CID를 보정하지 않았고, 종료된 CID로 위장하거나 새 모델을 추가 실행하지 않았다.

## 실제 후보와 선택

| 속성 | self | remote |
|---|---|---|
| 실제 표시 이름 | `a1` | `a1` |
| is_self | true | false |
| runtime | `codex` | `claude` |
| 실제 CID | `01a18811-2502-77c3-9a6f-f3b671cd0c51` | `b22ba192-8608-4edb-9d0d-58739e13ee7e` |
| home_id | `b8a8c431812d3580d5a8a994a3de84a0f28fc9d21d73f57c9d0b571e2ca98e5a` | `1f3efe9ffb9cf15ba352aa22f67362777ae05495d0bb84b9b5b8268090817da7` |
| machine | local projection | `c4c63394208008021443589822172e02c192ae3a400f9f1e4e98c3fe6f93fe6c` |

실제 선택 인자는 `candidate:04284306f09e84e4124c1e472649dc1c2010d63ce3cf5b476d83005eae2b6c29`였으며, 대응하는 전체 remote target은 다음과 같다.

```text
net:c4c63394208008021443589822172e02c192ae3a400f9f1e4e98c3fe6f93fe6c:claude:1f3efe9ffb9cf15ba352aa22f67362777ae05495d0bb84b9b5b8268090817da7:b22ba192-8608-4edb-9d0d-58739e13ee7e
```

세대 값은 `f3eefe3c454788661ed1ae9eb0e5c41229008a1f2fdc5a6a342d307170ca1b3f`이다. 이는 실제 discover handle과 원문 전송 packet의 receiver에서 일치했다. 원문 ID는 `b82e615ed4f74a0f`이고 수신 원본의 실제 target CID도 같은 remote CID였다. sender 질문·outbound packet·receiver handoff의 본문이 동일하며 self 또는 다른 CID로 간 원문은 0건이다.

## 모델·최초 setup·권한

실제 모델은 Claude init `claude-sonnet-5-5`와 Codex provider turn_context `gpt-6.1-sol`이었다. 모델명은 지정하지 않았다. 성공했던 persistent SDK 및 Codex 0.164 helper를 재사용했고 새 CID는 각 native runtime이 생성했다. CodeModeHost disable·위험 flags가 없음을 모델 시작 전에 정적으로 확인했다.

양쪽 `a1`은 최초 실제 CID/PID/MCP ancestry 등록 시 표시 라벨로만 설정했다. 실행 중 이름·실제 home/runtime/machine/CID를 바꾸지 않았다. 기존 표본의 actor/state/요청 ID를 복사하지 않았고 repository map도 만들지 않았다. reviewer 실제 사용자 공개 지시와 requester의 다른 머신 a1 선택은 native prompt/hook 경로를 그대로 사용했다. requester 자기 공개는 요청하지 않았다.

source manifest는 `f4172fc9f4c49433eb90fe44a54dad5631ede60249b60a5905e3524d794c62a4`이며 52개 Python과 13개 hooks/bin/skills의 실행 payload SHA가 일치했다. 제품 코드는 수정하지 않았다. 기존 성공 조건의 guard와 승인된 hook source/hash를 그대로 유지했고 새 allowedTools·trust hash·전역 rules를 추가하지 않았다.

## 미완 경계와 보존

receiver canonical은 pending이다. 별도 native wake 사본은 기존 구버전 hook에서 다음 이유로 held가 됐다.

```text
remote message from p2p origin was not received by this machine's xsm
```

실제 전체 원문 오류는 held-native-copies와 raw에 보존했다. 이 보류를 해제하거나 정상 응답으로 바꾸지 않았다. 이후 SDK native PID와 lifecycle controller의 종료가 확인됐고 native exit는 143이었다. 일반 업무 계속 지시 시도는 현재 PID 확인 단계의 assert에서 멈췄으므로 실제 socket 전송은 없었다. 종료된 no-session-persistence CID의 old pending을 새 CID로 재지정하지 않았다.

재개에 필요한 진짜 SDK stdin 다중 query 통로를 가진 FIFO helper는 [준비본](prepared-sdk-fifo-client-not-executed.py)으로만 만들고 syntax를 확인했다. 실행하지 않았다. 이 helper는 최초 Goal 및 원문/RequestId/답변이 없는 일반 계속 Goal만 같은 살아 있는 SDK stdin에 전달한다. guard·본문·MCP 결과를 바꾸지 않는다. 현재 추가 모델 제한 아래에서는 이를 새 actor로 실행하지 않았다.

## 전역 .claude.json 차이의 선행 범위 기록

모델을 시작하기 전에 [기존 차이 범위](prior-global-profile-drift-scope.json)와 [원 before 기록](original-before-hash-record.json)을 보존했다. 대상 경로는 `/Users/jaesolshin/.claude-3/.claude.json` 한 파일이다. 원 before SHA와 기록 파일 시각, 종전 after 관측 시각·SHA, 현재 inode/size/mode/mtime·SHA를 분리했다. 원래 before 시점의 전역 파일 inode/size/mtime은 기록되지 않았으므로 새로 만들어 적지 않았다.

종전 권한 설정과 auth metadata는 일치했고 변경 주체를 특정하는 증거는 없다. 임의 복구·권한 변경은 하지 않았다. 이번 짧은 표본에서도 같은 데이터 파일 hash가 fresh baseline과 달라졌으므로 전체 profile 데이터 불변성은 미확인 제한으로 유지한다.

## 종료

두 actor는 종료가 확인됐고, 소유 network service/engine도 공개 stop으로 종료했다. 소유 PID 잔여는 양쪽 0개다. 새 private state/key·원문·held·SDK·MCP 증거는 보존했다. 새 모델, 이름 상태 보정, old RequestId 재지정, controller 본문 중계 또는 ACK/consent 보정은 하지 않았다.

이 결과로 실제 self-vs-remote 동명 발견과 정확한 remote 선택·오배송 0건은 확인했다. 직접 회신/ACK까지의 완료 기준은 충족하지 못했다. [결과 JSON](results.json), [초기 argv 검사](requester-static-argv-check.json), [SDK 종료](same-sdk-terminal-state.json), [Book 종료](book-cleanup.json), [mini 종료](mini-cleanup.json)에 실제 근거를 남겼다.
