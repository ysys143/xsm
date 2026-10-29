# G11 비교 자료 독립 검토

## 결론

G11을 **partial**로 둔 판단은 원 자료와 맞습니다. 숫자·횟수·버전에서 원 JSON과 어긋나는 곳은 찾지 못했습니다. 다만 선택용 자료로 내기 전에 고쳐야 할 서술 결함이 4건 있습니다. C의 SSH 실행 trigger가 결정 문서에 빠져 있고, 승인 표현이 과장돼 있고, D 추천의 근거가 이번 측정 범위를 넘고, B의 제어 경로가 기록되지 않았습니다.

## 검증 한계

- 이번 검토는 Read/Glob/Grep만 사용했습니다. SHA-256 재계산, 실행 재현, `/tmp` 원시 증거 열람은 하지 못했습니다. 아래의 hash 일치는 문서에 적힌 값끼리 비교한 결과이고, 실제 파일을 다시 계산해 확인한 것은 아닙니다.
- 링크된 파일 중 이 폴더에 없는 것이 있습니다.
  - `C-*.py`, `C-control-guard-test.json`
  - 두 C 계획서
  - `execution.md`, `spec.md`, `acceptance.md`
  - `installed-engine-release-check.json`
- 그래서 다음 항목은 코드나 원문으로 확인하지 못했습니다.
  - SSH trigger가 본문을 싣지 않는다는 주장
  - C 최초 실행(run1)의 코드
  - G11 기준의 원문

## 원 자료와 일치하는 항목

| 항목 | 대조 결과 |
|---|---|
| native 15회 / cached 5회 | A/B/D JSON: `actual_native_calls: 9`, 각 후보 `replayed_without_model_rerun: true` 1회씩. C JSON: `native_successes: 6`, `cached_readbacks: 2`, `cached_model_reruns: 0`. 합계가 맞음 |
| 단계별 시간 15칸 | `remote-decision.md:75-79`의 값이 두 JSON의 `roundtrip_ms`와 소수점까지 같음 |
| CLI 버전 | 15회 호출 모두 `codex-cli 0.163.0`, `.codex-3` |
| engine 버전 | staging과 C의 daemon handle 10개 모두 0.12.10, `6ac4bb48…`. 실행본 0.12.10과 0.12.11 분석본을 구분해 적음(`remote-decision.md:109`) |
| native resume | 모든 phase가 `fresh ephemeral exec … not native resume`. conversation ID는 A/B/D 9개, C hash 6개가 모두 다름 |
| 정리 수치 | A/B/D: driver 6개 + native 9개 = cleanup 15항목, peer 파일 80개. C: daemon 10개(실행당 local 3 + peer 2), SSH control 2개, manifest 111항목 |
| 과거 표본 분리 | 10-28 합성 RPC, IPC 14개, staging을 native 횟수에 합산하지 않음 |

## 수정이 필요한 항목

**1. [중] 결정 문서와 G11 초안에 C의 SSH 실행 trigger가 빠져 있음**
- 위치: `remote-decision.md:15,64,81`, `G11-remote-comparison-draft.md:12,14`
- C 원 자료에는 분리가 적혀 있습니다.
  - C JSON `ssh_control_path.post_join_native_trigger`: "phase and expected request-body SHA only"
  - C 보고서 `C-native-roundtrip-20261029.md:13`
- 결정 문서와 G11 초안에서는 "trigger"를 검색해도 0건입니다.
- 원 자료를 정리하면 다음과 같습니다. 본문(request/reply)은 engine을 지난 것으로 기록돼 있습니다(`received_body_sha256`가 request hash와 일치하고 reply engine ID가 있음). 반면 peer Codex를 매 턴 깨운 것은 SSH였습니다.
- 반례: 결정 문서 15행은 "peer 실행 경로 부재 … 현재 blocker가 아니다"라고 씁니다. 하지만 C가 엔진만으로 상대 에이전트를 깨운다는 것은 이번 표본에서 입증되지 않았습니다. 이는 문서가 반대 증거로 유지하는 J22(일반 Codex 유휴 수신 실패, 129행)와 바로 맞닿는 부분입니다.
- 위 두 위치에 "본문은 engine으로, 실행 trigger는 SSH로"를 명시해야 합니다. trigger가 본문을 싣지 않는다는 점도 코드로 확인하지 못했습니다(peer agent 소스가 폴더에 없음).

**2. [중] 승인을 과장하는 표현**
- `remote-decision.md:51`의 "**승인된** private adapter"는 C adapter까지 포함하는 문장입니다. 그런데 7·118행에서는 별도 명시 승인이 없었다고 씁니다. 같은 문서 안에서 서로 어긋납니다.
- `remote-decision.md:162`의 "private C 시험 **허용**을 이 응답으로 해석하지 않음"은 허용 이벤트가 있었던 것처럼 읽힙니다. "코디네이터의 범위 판단"으로 바꿔야 합니다.
- 정도는 낮지만 같은 성격의 표현이 더 있습니다.
  - `remote-decision.md:120` "승인된 기존 Codex 구독 인증"
  - `C-native-roundtrip-20261029.md:47` "승인된 기존 구독 CODEX_HOME"
  - `C-native-roundtrip-20261029.md:55` "허용된 engine 원본 binary"
  - C JSON `home_scope` "approved subscription runtime"
- 이 폴더에는 이 승인들의 근거가 되는 이벤트가 없습니다. 참고로 C manifest 736행에서 보고서는 "authorization wording correction"을 거쳤는데, 위 표현들은 그 수정 뒤에도 남아 있습니다.

**3. [중] D 추천의 근거가 이번 측정 범위를 넘음**
- 위치: `remote-decision.md:11`
- 측정된 네 후보의 결과는 모두 같습니다(성공, `false/4`). 그래서 추천은 사실상 "기존 설치를 다시 쓸 수 있다"는 이유 하나에 기대고 있습니다. 그런데 이 항목은 문서 스스로 미측정이라고 적은 축입니다(58행, 156행).
- 반대 근거에서 빠진 사실이 있습니다. 양쪽 Tailscale이 `1.105.110, unstable/dev` track입니다(37행).
- "A의 진단·재시도 개선을 보존"한다는 부분은 이번 자료에 근거가 없습니다. A fixture는 개선이 들어가지 않은 일반 LAN SSH carrier였습니다.
- 추천을 "측정되지 않은 운영 전제 재사용에 기댄 가설"로 표시해야 합니다.

**4. [중하] B의 SSH 제어가 tailnet을 탔고, 본문 경로의 phase별 증거가 없음**
- 위치: `remote-decision.md:63`, A/B/D 보고서 43행
- A/B/D JSON 711·728행: B driver의 `ssh_connection`이 `100.123.30.11 … 100.77.24.16 22`입니다. 즉 B의 bootstrap과 제어는 D와 같은 경로에 의존했습니다. 문서에는 "기존 SSH"라고만 적혀 있습니다.
- B 본문이 `49909`/`49941` TCP로 오갔다는 기록이 phase 레코드에는 없습니다. 이 주장은 driver 설계에만 기대고 있습니다.

**5. [하] 같은 이름 아래 뜻이 다른 cached·재연결**
- cached 5회의 성격이 갈립니다.
  - A/B/D 3회: carrier를 다시 연결한 뒤 peer에서 회수했습니다.
  - C 2회: 회수 시점에 local이 `relay_connected=false`, peer `online=false`였습니다. 네트워크를 거치지 않은 local inbox 회수입니다(C JSON `cached_readback`).
- C의 "재연결"은 local daemon만 재시작한 것입니다. SSH control과 peer daemon은 계속 유지됐습니다(C JSON `plan_execution_note`). A/B/D는 SSH나 driver를 새로 띄웠습니다.
- 위치: `remote-decision.md:64`, `G11-remote-comparison-draft.md:12`. 같은 "재연결 뒤 새 답"이라는 칸에 들어가 있으므로 이 차이를 칸 안에 적어야 합니다.

**6. [하] 기록 검사 결과가 검사 대상과 묶여 있지 않음**
- `C-evidence-check-20261029.json`에는 실행 시각이 없고, 검사한 manifest의 hash도 적혀 있지 않습니다.
- 보고서 문구는 사후에 수정됐습니다(manifest 736행). 따라서 111개 hash 검사가 수정 뒤의 manifest를 대상으로 돌았는지 이 자료만으로는 판정할 수 없습니다.

**7. [참고] 후속 입력이 사실상 고정돼 있음**
- phase별 request hash(`837c…`, `5e53…`, `d0ec…`)가 A/B/D와 C 두 실행에서 모두 같습니다.
- C 두 번째 실행의 followup 답은 문구가 달랐는데("…4개입니다"), 다음 입력 hash는 그대로였습니다.
- 그러므로 "후속" 턴은 앞선 답의 내용이 다음 요청으로 전달됐다는 증거가 아닙니다. 기껏해야 `claim_valid`/`corrected_sum` 수준의 정보만 이어졌을 수 있습니다. 문서의 "최소 수학 결과만 전달"과 모순되지는 않지만, 입력이 이 값에서 계산됐는지 하드코딩됐는지는 코드가 없어 확인하지 못했습니다.

## Gate 범위 판정

- **G11: partial 유지가 타당하고, passed는 불가합니다.** 비교체의 native 15회와 cached 5회는 원 자료와 일치합니다. 설치·개입 비용의 동일 기준 비교와 미실행 환경은 여전히 비어 있습니다.
- **미해소 결함: 있습니다.** 증거를 조작하거나 수치가 틀린 곳은 찾지 못했습니다. 다만 1~4번 서술 결함이 고쳐지지 않았습니다(C trigger 누락, 승인 표현 과장, 추천 근거 과장, B 제어 경로 누락). 선택용 자료로서 정직성을 갖추려면 이 네 가지를 먼저 수정해야 합니다.
- 이 검토는 G12나 전체 제품 완료를 판정한 것이 아닙니다. 파일은 하나도 수정하지 않았습니다.
