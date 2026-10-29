# A22-03 마지막 동일 strict 조건의 통합 trace

**하나의 새 trace에서 A22-03의 업무 요구를 충족했다.** 잘못된 안→실제 반례를 반영한 수정안→독립 경계 검토의 3라운드가 모두 실제 final 회신·ACK로 완료됐다. 그 뒤 세 번째 원문과 바이트까지 같은 네 번째 질문이 strict 정책에 held됐고, 원 ID 조회·실제 대기·단 한 번의 같은 ID 재전송·실제 final 회수·ACK까지 이어졌다. 기존 성공 round/CID를 소급 합치지 않았다.

단, 검토자는 모든 검토를 마친 뒤 별도 대화식 읽음 확인 메시지를 더 기다려 자발 종료하지 않았다. 하네스가 송신자 종료 20초 뒤 소유 프로세스를 정리했다. 이는 실제 요청 결과와 구분하며 reviewer exit 0으로 바꾸지 않는다. profile config hash drift도 보존했다. 이 묶음 후 추가 실험은 하지 않았다.

## 조건과 초기 목표

- 새 private Git/XSM root: `/private/tmp/p13-strict-review-91nhwo1c`. 이전 strict/FYI 두 pair와 별개다.
- 제품: `/private/tmp/xsm-final-receipt-frozen-i3u9pms3`, 제공 final-source-manifest의 **315개 파일**을 시작·종료에 대조해 불변을 확인했다. source1697·ledger·plan 수정은 없다.
- 초기 private policy는 한 번만 설정했다: `strict`, `window_seconds=60`, `max_same_body=1`. 네 요청·재송신 동안 config.json SHA는 동일했다: `6849b49ed2bf580cbe375a0e9009681864fabb634942d2f7e18244387eaa00b8`.
- 기존 정상 factory Codex 두 세션, `.codex-3`, workspace-write/approval never, 제품 skill과 xsm MCP를 사용했다. role a1 이름과 실제 endpoint 등록만 setup했다. 새 allowedTools·권한·프로필 편집·credential 복사·API 키 경로는 없다.
- 초기 목표에 정상 3라운드 후 종료하지 말 것, 네 번째 고유 요청의 보류/원 ID 회복까지 실제 검토 4건을 마칠 것, 전체 고유 질문 4개·재전송 포함 최대 5회라는 종결 범위를 양쪽에 줬다. 원 goal 전체는 [원 결과](strict-review-native-results.json)에 보존했다. 내부 CID/ref는 goal에 주지 않았다.

실제 sender CID는 `01a1851a-d467-7d62-92cb-4243ffd6a0bb`, actual native PID 38943이다. reviewer CID는 `01a1851a-ce01-75e3-852e-d4c604ab3818`, actual native PID 38230이다. wrapper PID는 각각 38941/38228이고 MCP는 39055/38549다. 실제 CID/PID/lstart/home/cwd를 사용했으며 fake 등록·fan-in은 없다.

## 한 trace의 실제 결과

| 단계 | 원 질문 ID | 실제 회신 ID | 판정·확인 |
|---|---|---|---|
| 1. 잘못된 안 `2+2=5` | `7ecc3dd773674795` | `e31abcbf96d246bf` | 분리된 두 2원소 집합의 합집합은 4개, 제시안 거짓. final/succeeded, 양쪽 ACK |
| 2. 실제 반례를 반영한 수정 `2+2=4` | `87ad7c93ada64348` | `63bd25063f3e4d87` | 후속값 3→4로 독립 재검산, 수정안 정확. final/succeeded, 양쪽 ACK |
| 3. 경계 `0+0=0` | `666d5eedda1d4683` | `66a8b2a81add407f` | 항등원·빈 집합 근거로 독립 검산. final/succeeded, 양쪽 ACK |
| 4. 세 번째 본문 그대로의 반복 | `41f347fd38e64239` | 보류 중 없음 | 원 ID status=held, final=false, final_outcome=null. 실제 held receipt와 canonical snapshot 보존 |
| 5. 네 번째 원 ID의 회복 | **`41f347fd38e64239` 유지** | `6d45a56dd5d44be1` | 실제 대기 뒤 같은 원문·같은 ID 재전송 1회. 원 reply_to 유지한 실제 final/succeeded 회신 및 양쪽 ACK |

`outcome=succeeded`는 검토 업무 완료이며, 첫 잘못된 안을 참이라고 승인했다는 의미가 아니다. 처음 세 질문의 본문은 서로 다르며, 후속 질문은 실제 이전 reply를 받은 뒤에 생성됐다. 정상 검토가 반복 제한으로 막힌 상태를 성공으로 메우지 않았다.

네 번째 initial ask는 pending으로 반환됐고, **같은 ID의 실제 조회가 held**를 확인했다. 이 pending/held를 final로 바꾸지 않았다. 정상 3라운드에 적용된 것과 같은 정책이 반복을 중단했다. 보류 snapshot의 message/digest는 회복 후 canonical과 일치하고, 실제 네 번째 reply의 reply_to는 원 ID다. clock mock·body 재작성·controller relay/ACK/index 보정은 없다.

원 질문 4개·실제 회신 4개가 모두 canonical acknowledged다. receiver가 실제 원 요청을 ACK했고 sender가 실제 답을 ACK했다. 요청 원문/reply 본문 SHA와 native event 순서·관측시각은 [audit JSON](strict-review-native-audit.json)의 rounds에 결속했다.

## 실행·수집·cleanup 구분

- 새 native pair **1개**, actor invocation **2회**, 조건 자동 재실행·새 모델 재시도 **0회**다. source/goal을 중간에 바꾸지 않았다.
- 실제 endpoint 초기 등록 setup **2회**는 모델 도구 호출과 별도다. controller 본문 relay·ACK·index 수정·추가 사용자 prompt는 모두 **0회**다.
- private policy는 전체 trace에서 동일했다. 초기화 외 정책 변경·전역 권한 변경은 하지 않았다. 각 라운드의 same sender/receiver native pair도 동일하다.
- sender는 자기 최종 보고 후 exit 0이었다. reviewer는 네 번째 실제 reply까지 보낸 후 별도 읽음 확인 note를 기다리는 inbox wait에 남았다. sender의 제품 ACK와 대화식 확인 note를 혼동하지 않고 reviewer가 스스로 종료했다고 주장하지 않는다.
- 하네스의 원 cleanup 기록에는 reviewer group/MCP에 TERM을 보낸 사실과 직후 MCP 생존 snapshot이 남아 있다. 뒤의 읽기 전용 exact PID 조회에서 wrapper 2개·실제 native 2개·MCP 2개 모두 부재를 확인했다. 새 signal이나 native 실행으로 보완하지 않았다. 사용자/peer의 다른 세션은 종료하지 않았다.

## audit 보정과 drift를 보존한 판정

최초 오프라인 audit에는 요청 기능 검증 외에 “두 actor 자연 exit 0”과 “TERM 직후 즉시 부재”를 추가해 22/24였던 결과가 있다. 이를 [initial audit](strict-review-native-audit-initial.json)로 보존했다. raw 결과·body·ACK는 변경하지 않았다.

최종 audit는 원 수용 조건의 실제 요청/회신/보류/회복을 검사하고, process 정리는 **실제 사후 PID 조회**로 확인했다. 자발 종료 여부는 별도 lifecycle 필드에 남겼다. 23개 기능·소유 종료 검사를 통과했지만 reviewer exit 0을 만들어 넣지 않았다. 소스 테스트 실패를 수정했다고 주장하는 것이 아니라 수집기 요구와 관측 표면을 바로잡은 것이다.

이번에는 profile guard의 경로별 before/after를 저장했다. 차이는 **`.codex-3/config.toml` 한 경로**이며 hash는 `1f94ac2b02b6f8a13f8246586ecf9ed27df850cb28f07a3bbd8138400134ea12` → `5f93490622e2247c60c88679faf6ede9dd98cfce9f634ea39b2548ef73639adf`다. 변경 주체/내용은 이 관측으로 확정하지 않고 보호 파일 불변이라고 쓰지 않는다. evaluator/actor의 프로필 편집 명령이나 권한 보정은 없다. private strict policy SHA와 제품 source SHA의 불변은 이 drift와 별도로 검증됐다.

따라서 **원 A22-03 동일 정책의 업무 positive/negative/recovery trace는 확보**했으며, 환경 drift와 reviewer 자연 종료 한계는 별도 보존한다. 최종 plan/ledger 승격은 coordinator가 이 원 근거로 판정하며 이 문서가 덮어쓰지 않는다.

## 보존

[원 실행 script](strict-review-native-run.py) · [원 결과/초기 goal](strict-review-native-results.json) · [offline audit](strict-review-native-audit.py) · [23개 검사/실제 ID·SHA](strict-review-native-audit.json) · [manifest](strict-review-native-manifest.json)

raw/state·중간 held snapshot·native JSONL/stderr·controller 관측시각·사후 process readback은 `/private/tmp/p13-strict-review-91nhwo1c`에 보존했다. 공개 artifact에는 claim token 원문을 싣지 않았다. 이전 두 pair 이력은 그대로 유지했고 추가 실험 없이 이 마지막 묶음을 종결했다.
