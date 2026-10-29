# A23-07 doctor native v3 — 실제 선택 home 보완

판정: **partial로 최종 종결**. 허용된 보완 doctor는 **1회만** 실행했고 exit 0이었다. 실제 CODEX_HOME 1개·실제 CID/PID/lstart 관측 등록 1개를 읽어 설치·trust를 관측했지만, `setup.process/home_match`는 `unknown`이고 관측기 초기화가 실패했다. 조건 변경·재실행·후속 실험은 하지 않았다. 기존 sandbox homes0/records0 표본과 감사 파일은 수정하지 않았다.

## 관측 사실과 권한의 구분

OS에서 현재 실제 도구의 직접 부모인 shared Codex runtime PID **9102**, lstart **Wed Oct 28 05:55:24 2026**을 확인했다. 현재 CID와 cwd·archived=0은 실제 CODEX_HOME의 native DB를 `mode=ro + query_only`로 확인했다. 그 사실 그대로 `registry.upsert`를 호출해 own private state에만 등록했다. name/socket/mcp_pid나 추정 caller certainty는 추가하지 않았다. 이 등록은 메시징·권한 승격에 사용하지 않았다.

최종 source `/private/tmp/xsm-final-receipt-frozen-i3u9pms3`의 실제 CLI를 실행했다. primary **135개 hash는 실행 전후 일치**했다.

```text
/usr/bin/sandbox-exec -f /private/tmp/doctor-native-v3-8t5nskxm/doctor-v3.sb /usr/bin/python3 -B -m xsm doctor --json
```

HOME/CODEX_HOME은 재지정하지 않았다. XSM_HOME만 own private state이고 PYTHONPATH는 최종 source와 수동 접근 관측기 경로다. registry/doctor/identity/transport 함수를 교체하지 않았다. 선택 CODEX_HOME의 필요한 metadata 읽기를 허용하면서 auth/key 파일 읽기·전역 쓰기·신호는 제한했다. 읽기 전용 daemon 상태 조회는 명시 차단하지 않았다.

## 실제 doctor 반환 구조

| 항목 | v3 결과 |
|---|---|
| exit | 0 |
| 실제 선택 home / 등록 session | 1 / 1 |
| sessions live / stopped / unregistered | 1 / 0 / 0 |
| 설치 metadata | present, error 없음 |
| trust | observed, 반환된 trust flag 2개 true |
| setup.process / home_match | **unknown / unknown** |
| setup.mcp / first_roundtrip | unknown / unknown |
| active_probe | not-run |
| own synthetic decisions / internal errors 집계 | 1 / 1 |
| synthetic invite/body의 stdout·stderr 포함 | 모두 false |
| 민감정보 일반 패턴 검출 | 0 |
| stdout / stderr | 5744 / 163 bytes |

`codex_trust`는 source에서 선택 home의 hooks.json/config.toml을 읽는다. 이번 반환값의 실제 선택 home 일치·present 설치·parsed trust flag는 homes0/records0과 다른 실제 metadata 경로의 긍정 증거다. 다만 접근 로그가 없어 파일별 성공 read trace로 주장하지 않았다. `live=1`만으로 `setup.process/home_match=unknown`을 메우거나 native loaded-list의 실제 성공을 추정하지 않았다.

## synthetic 비출력과 raw 보존

own state의 `decisions.jsonl`에 synthetic body/invite를 넣었다. 기존 doctor가 그 기록을 읽어 decisions/internal-error count를 각1로 집계했고 marker는 두 출력에 없었다. 이는 해당 오류 집계 경로의 비출력 증거이며, 모든 state의 원문 비출력이나 실제 key값 전수 비교를 뜻하지 않는다. 실제 credential 파일/값을 열거나 비교하지 않았다.

raw stdout/stderr와 전체 native/등록 metadata는 mode0700인 `/private/tmp/doctor-native-v3-8t5nskxm` 아래 mode0600으로만 보존했다. [JSON](doctor-native-v3-result.json)에 정확한 명령·원문 SHA·구조·검사 결과를 결속했다. 원문은 공개 파일에 복사하지 않았다. 실제 home 경로가 출력되는 metadata는 있어 전역 home 전체 익명화를 주장하지 않는다.

## 실패·생존·미확보를 분리

추가한 수동 관측기의 `sitecustomize` 초기화가 own audit-log open 단계에서 PermissionError로 실패했다. stderr는 이 초기화 오류 2줄이며 접근 로그는 없다. 제품 CLI는 계속 실행해 JSON/exit0을 반환했지만 clean stderr·file-open/RPC trace를 확보했다고 보지 않는다. 권한/관측 조건을 수정하거나 다시 실행하지 않았다.

외부 OS에서 doctor 전후 및 같은 thread의 후속 실제 도구 실행 모두 PID/lstart 동일 세대를 확인했다. 이는 실제 사용자 shared runtime 생존과 후속 도구 처리의 증거다. doctor 자체 `setup`의 process/home-match 관측과는 별개이며 그 `unknown`을 대신하지 않는다. 공유 PID 생존을 모든 thread 건강이나 다음 독립 모델 turn 완료로 확대하지 않았다.

원 source의 PID 확인에는 `kill(pid,0)`이 포함된다. 이는 신호를 전달하지 않는 생존 검사이며, 실제 종료·기상 신호와 구분한다. 이번 driver의 비영 신호·기상·메시지·로그인 호출 및 새 모델은 0이다. 선택 config/hooks의 stat metadata는 전후 같았고 제품·plan·ledger는 수정하지 않았다.

실제 선택 metadata와 synthetic 비출력은 보완됐지만, doctor가 선택 process/home match를 observed로 반환한 표본과 정상 관측기 증거는 얻지 못했다. **추가 조건이나 실험 없이 partial로 끝냈다.**
