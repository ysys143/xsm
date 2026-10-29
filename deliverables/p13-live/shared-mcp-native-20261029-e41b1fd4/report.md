# A23-03 실제 native subagent / MCP process 관측

**이 factory 하네스에서는 두 native 하위 thread가 같은 xsm MCP process를 공유하지 않았다.** 같은 native Codex PID 아래에서 실행됐지만 xsm MCP 서버는 thread별로 분리됐다. 따라서 실제 shared-MCP A/B/A/B 수용 증거는 **미확보**이며 합성 `_meta` 검사나 fan-in으로 성공 처리하지 않았다. 제품 결함으로 판정한 것도 아니다.

## 현재 CLI와 실행 조건

현재 PATH의 `codex-cli 0.164.0`을 사용했다. 로컬 `--help`, `features list`, `app-server generate-json-schema`를 확인했다. 기능 목록의 `multi_agent`는 stable/true였고 실제 native DB에도 부모가 같은 두 `thread_spawn` 자식이 생겼다. schema 320개와 원 출력은 private tmp에 보존했다.

source는 `/private/tmp/xsm-p13-postqa-frozen-bukwksw6`이다. 정상 `post-claims-collaboration.py` Actor.start의 factory argv/env를 사용하고 private 작업 폴더에 제품 skill만 설치했다. 기본 지침 교체, feature 비활성화/활성화, allowedTools 추가, 다른 profile 대체는 없다. 부모 native ID와 명시 식별자/API 키 이름만 제거하고 나머지 정상 런타임 환경을 유지했다. 키 값은 조회·출력하지 않았다.

모델에는 두 native 검토자가 `2+2=5`와 `0+0=0`을 독립 검토하고 xsm으로 직접 질문·후속·메모 사본을 교환하라는 자연 목표만 줬다. ref나 도구 호출 순서는 평가자가 지정하지 않았다. 개발용 Orca/별도 CLI worker를 띄운 시험이 아니며, 평가 native CLI는 1회다.

## 실제 process와 metadata

| native 역할 | xsm MCP PID | 실제 tools/call | 실제 metadata의 native CID 종류 |
|---|---:|---:|---:|
| 부모 | 42449 | 0 | 없음 |
| 하위 A: review_five | 44002 | 14 | A 1종 |
| 하위 B: review_zero | 44222 | 15 | B 1종 |

세 서버의 native Codex ancestor는 같은 PID **42107**이었다. proxy/server는 각각 독립된 실제 프로세스다. 두 child의 실제 `params._meta.threadId`는 서로 달랐고 각 서버에는 한 child CID만 나타났다. 실제 provider DB의 native CID/source/부모 관계, 확실한 Codex ancestor PID/lstart/home을 맞춘 최초 등록 setup은 3회다.

전체 시간순 호출에서 A/B 교대 부분열을 뽑을 수 있어도 **서로 다른 MCP PID를 지난 순서**다. 이를 한 공유 서버의 A/B/A/B로 세지 않는다. proxy는 각 runtime이 실제로 생성한 서버 하나의 stdio bytes를 그대로 기록·전달했으며 서버 둘을 합치거나 metadata/identity/result/body/ACK를 변경하지 않았다.

## 같은-home 범위에서 관측한 귀속

- 실제 xsm 호출은 29회다. 질문 결과와 원 저장 레코드를 대조한 sender/target 검사 4건, 실제 `xsm_files` 읽기의 caller/owner 검사 4건, outgoing/incoming 사본 owner·요청 endpoint·home hash·body SHA 검사 6건은 일치했다. 반복 조회는 별도 새 메시지 성공으로 세지 않는다.
- 최초 등록보다 먼저 들어온 호출 2건은 별도 표시했다. 이 초기 호출의 확정 caller 귀속까지 검증했다고 확대하지 않는다. 저장된 질문/사본 대조의 정확한 근거는 [summary](summary.json)에 있다.
- home은 실행한 runtime profile와 해당 native state DB의 정확한 CID 근거를 함께 사용했다. 프로세스/global HOME 문자열만으로 서명 근거를 만들지 않았다.
- 부모의 최종 보고는 xsm 상호 질문·실제 답·메모 교차 확인이 미완이라고 명시했다. 요청/사본 저장이나 일부 note 수신을 전체 업무 성공으로 바꾸지 않았다.

이 일치 표본은 **분리된 서버·같은 home** 조건이다. 공유 process의 context 교차 오염 방지나 다른-home 동일 ID의 안전성까지 증명하지 않는다. 실제 shared 표본이 없어 그 뒤의 다른-home 동일-ID/상속 타하네스 env 별도 조건은 실행하지 않았다. fake identity나 복제 native ID로 대체하지 않았다.

## 계수·한계·정리

factory native CLI 1회, 실제 대화 3개(부모 1·native subagent 2), copied native 기록의 task_started 5회·task_complete 3회를 관측했다. 나머지 시작 turn은 보존 범위에 완료 event가 없으므로 완료를 추정하지 않는다. root의 native wait 호출 15회도 원 출력에 남아 있다. backend 내부 모델 요청 횟수는 이 계수로 확정할 수 없다. 평가 전체의 자동 native 재시도와 provider/tool-host 준비 실패는 0이다.

frozen source hash는 전후 일치했다. profile `config.toml` hash drift는 관측됐고 변경 주체는 미확정이다. 평가자의 profile/권한 편집 명령은 없으며 이를 profile 불변이나 완전한 환경 통제로 과장하지 않는다. 기존 handoff/UDP 결과는 수정하지 않았다.

raw native 출력·실제 metadata/claim wire·native rollout 사본·private XSM state는 `/private/tmp/shared-mcp-native-yjfl3mjl`에 보존했다. 공개 deliverables에는 요약·코드·hash/경로만 둔다. 소유 native wrapper/실제 Codex/proxy/MCP PID와 시작 시각을 대조해 종료를 확인했고 잔여 known process는 0이다. 기존 사용자 서비스나 다른 세션은 종료하지 않았다.

[요약/실제 호출·귀속 대조](summary.json) · [실행 조건](plan.json) · [hash/경로 manifest](manifest.json) · [controller](run.py) · [기록 전용 proxy](proxy.py) · [읽기 전용 audit](audit.py)
