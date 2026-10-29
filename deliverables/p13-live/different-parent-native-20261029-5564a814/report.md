# A15-05 실제 다른 부모의 native child 간 협업

**factory 부모 2개가 각각 native child 1개를 둔 조건에서 직접 질문·수정 검토·메모·최종 상호수신을 확인했다.** 실제 child의 parent_thread_id는 서로 다르고 각자의 실제 부모 CID와 일치한다. 같은 CODEX_HOME `.codex-3`와 같은 private Git common을 사용했다. 기존 1부모/2child 결과는 유지하며 shared-MCP 성공으로 세지 않는다.

## 실제 관계와 계수

아래 CID는 공개 요약에서 hash로 표시한다. 실제 원 ID/provider source와 대응 hash는 private raw 및 summary/manifest로 검증한다.

| child 초기 역할명 | 실제 부모 CID hash | 실제 child CID hash | provider parent_thread_id hash | 실제 native PID |
|---|---|---|---|---:|
| a1 | `0924883f570f6ecc…` | `766842235fefdf73…` | `0924883f570f6ecc…` | 57273 |
| a2 | `f23747694fb78088…` | `478350d5f3a2226b…` | `f23747694fb78088…` | 57275 |

두 parent_thread_id가 다른 것은 표시 이름 차이가 아니라 실제 provider DB의 thread_spawn 관계다. PID도 서로 다른 실제 부모 runtime에 속한다. 초기 등록 setup은 실제 CID/PID/lstart/home/cwd/부모 관계로 4회 수행했다. 동일 PID fan-in·가짜 ID·metadata 재작성은 없다. 두 부모의 xsm tools/call은 모두 0이고, 부모가 본문 전송·수동 ACK·질문 인덱스 보정에 관여하지 않았다. 부모는 자기 child 시작·대기·종결과 최종 보고만 수행했다.

평가 조건은 1회, factory 부모 CLI 2회·native child 2개다. CLI는 `codex-cli 0.164.0`이며 실제 native turn event 계수는 summary에 보존했다. backend 내부 모델 요청 수는 turn 계수로 추정하지 않는다. 조건/모델 자동 재시도와 추가 source 수정은 0이다.

## 직접 업무 왕복

- 원문 **8건이 요청 auto를 유지한 채 exact unsupported→stored/mcp-inbox로 전환됐고 실제 상대 claim/ACK까지 확인**됐다. quiet를 선택한 메시지는 0건이다. native queued/wake evidence는 모두 false이며 성공을 날조하지 않았다.
- 질문은 3건이다. 최초 `2+2=5` 제안, 반례 수용 뒤 수정안 `2+2=4` 및 메모 검토, 역방향 `0+0=0` 경계 질문이 있다. 원 질문 reply_to를 유지한 최종 outcome은 모두 succeeded다. 최초 제안에는 outcome 없는 부분 회신 1건도 있고 최종 회신과 구분했다.
- 상대 incoming 파일 entry를 실제로 읽은 **2회**에서 caller ownership과 파일 content SHA를 manifest와 대조했다. 메모 저장만으로 열람을 판정하지 않았다.
- 원 ID·message wake·원문/identity/digest를 유지했고 수신·ACK·reply는 실제 child CID 사이에서 발생했다. public 요약에는 ID/token hash와 상태만 두고 실제 claim token·ACK payload는 복사하지 않았다.

두 부모 최종 보고도 직접 반례·수정안 확인·경계 질문·상대 메모 열람과 종결 회신 수신을 완료했다고 밝혔다. 이 표본의 상호수신 판정은 그 발언만이 아니라 실제 ACK/질문 인덱스/파일 읽기 원 기록을 함께 사용했다. 전체 계획/모든 A15 조건 완료를 선언하지 않는다.

## 고정본·오류·한계

source `/private/tmp/xsm-final-receipt-frozen-i3u9pms3`와 제공 `final-source-manifest.json`의 **315 files / 135 primary**를 실행 전후 대조했다. source hash는 유지됐다. 두 factory CLI의 기존 argv/env와 native 기본 지침/도구를 유지하고 제품 skill만 private 작업 폴더에 설치했다. ref/도구 순서/wake 파라미터 힌트는 추가하지 않았다. 실제 요청은 default auto였다.

parent-a1 stderr에 `failed to load models cache: EOF while parsing a value at line 1 column 0` 경고 1건이 있었으나 실제 실행은 계속돼 두 부모 wrapper가 exit 0으로 끝났다. 모델 cache를 수정·삭제하거나 재시도하지 않았다. RPC isError 응답은 0건이다. exact unsupported는 위 허용된 대체 전달의 원 오류로 별도 보존했다. profile config hash drift는 관측됐고 변경 주체는 미확정이다. 평가자의 전역 설정/권한/profile 편집 명령이나 auth 값 조회·유료 API 경로는 없다.

실제 MCP 서버는 parent/child별로 분리됐다. shared-MCP 증거 미확보는 그대로이며 이번 다른 부모 간 positive 교차 메시징과 별개다. 다른 home이나 새 daemon 버전 조건을 도입하지 않았다.

## 보존과 종료

raw/state·실제 provider 부모 관계·native rollout 사본·원 JSONL은 `/private/tmp/different-parent-native-3jr1o8uv`에 보존한다. 공개 deliverables는 요약·script·hash/경로만 포함한다. 소유 wrapper/native Codex/proxy/MCP PID와 시작 시각으로 종료를 확인했고 잔여 known process는 0이다. 기존 사용자 세션/서비스를 중지하지 않았다. 기존 실패·1부모2child·handoff/UDP 원본을 덮지 않았다.

이 조건을 마지막 실험으로 종결했다. 추가 source 수정·모델 실행·재시도는 하지 않았다.

[요약·실제 계수/원 관계 hash](summary.json) · [조건](plan.json) · [hash/경로 manifest](manifest.json) · [controller](run.py) · [기록 전용 proxy](proxy.py) · [읽기 전용 audit](audit.py)

## 캐시 경고 1건의 읽기 전용 대조

22:26:40.163358 UTC의 `codex_models_manager::manager` 로그는 **models-cache 로드 중 JSON EOF 파싱 실패**이며 로그 등급은 ERROR다. parent-a1 stderr에서 관측됐다(wrapper PID 57266, 확인된 native PID 57273, 부모 CID hash `0924883f570f6ecc…`). 오류 줄에는 요청/대화 ID나 cache 파일 경로가 없으므로 특정 메시지의 오류로 결속할 수 없다. 최초 질문 생성은 그 뒤인 22:27:02.469 UTC다. cache 내용·변경 주체·왜 EOF였는지는 이 raw로 확인되지 않아 원인을 추측하지 않는다. **이 runtime 경고 1건과 MCP RPC isError 0건은 별도 계수다.**

기존 manifest hash와 다시 대조한 canonical **8건**은 ACK 상태와 원문/digest가 보존돼 있고 질문 인덱스 **3건**도 바뀌지 않았다. `11f8150b86184fc2`에는 부분 회신 1건과 최종 succeeded 회신, `7bbf155fed2340ad`·`8ebd81df269d48cb`에는 최종 succeeded 회신이 각각 있다. 회신 총 4건의 body·원 reply_to가 해당 canonical과 일치했다. 두 부모 CLI는 exit 0이었다. 따라서 **이 완료 표본에서 원문·질문 인덱스·최종 reply의 손상/유실 영향은 관측되지 않았다.**

이는 cache 자체의 재로드/복구 성공을 증명하지 않는다. 경고 뒤 새 실행·동일 CID resume·오프라인 재시작으로 회수를 검증하지 않았고, cache 상태가 향후 native 기동에 영향을 주지 않는다고 보장할 수 없다. 보존된 원문/회신은 현재 읽기 전용 대조가 가능하다는 범위다. [final-regression.json](../final-regression.json)의 두 Python 전체 1697개 OK·제품 135 hash 불변은 별도 회귀 근거이며 cache 수리/재기동 성공 근거로 사용하지 않는다. 새 실험·source/상태 수정 없이 이 대조로 종결했다.
