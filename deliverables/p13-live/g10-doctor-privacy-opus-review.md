# G10 doctor privacy delta 독립 검토

**이 delta 범위에서 구체적인 Medium 이상 잔여 결함을 찾지 못했다.** 이는 `install.stuck()`의 진단 projection과 CLI privacy 테스트3개, 제공된 실제 CLI/검사 기록에 대한 한정 판정이다. 전체 제품/G10/계획 완료 승인이 아니다.

## 실행 증명

- 구독 Claude 프로필 `.claude-3`, 실행 전 auth metadata는 claude.ai/Max/firstParty였다.
- CLI pinned binary: `/Users/jaesolshin/.local/share/claude/versions/2.1.312`.
- 기존 PID **72627**의 단일 실행을 이어 확인했다. 사용자 재시작 요청 때 중복 모델을 실행하지 않았다.
- 요청 model과 실제 init/modelUsage가 모두 **`claude-opus-5-5`**다. exit0, is_error=false, review duration77.183초다.
- 실제 도구는 Read/Glob/Grep뿐, MCP0·permission denial0이었다. 프로세스에서 ANTHROPIC_API_KEY를 제거했고 값은 조회하지 않았다. raw init의 apiKeySource는 none이다.
- product/plan/ledger/config/권한을 수정하지 않았다. 글로벌 권한 규칙 변경 없이 읽기 전용 도구를 session 인자로 제한했다.

## 검토 범위와 판단

원315/final1697 snapshot과 동결 후 두 파일(`xsm/install.py`, `tests/test_install_cli_flow.py`)의 delta만 검토했다. 전체 dirtydiff·전면 재설계·이미 미검증인 UI/원격 공백을 새 코드 결함으로 가산하지 않았다.

1. **원문·raw 오류 출력:** queued/unknown 전체 원장 행 대신 scalar 진단 metadata만 새 dict로 만들고, endpoint 안의 nested 값도 제외하는 경로를 확인했다. raw 오류 prefix/detail이 실패 label로 나가던 경로는 고정된 category 또는 other로 바뀌었다. 모델은 실제 before/after JSON/text 캡처를 직접 대조했다.
2. **원정본 보존:** projection에 원 row/endpoint 쓰기가 없음을 source로 확인했다. 기존 ledger bytes의 전후 동일성은 제공된 실제 CLI 테스트/green 기록이며, 검토 모델이 재실행한 결과는 아니다.
3. **운영 유용성과 text/table:** text가 쓰는 이름·ID·상태·실패 분류/개수는 유지된다. table은 원래 stuck을 렌더하지 않았으며 baseline non-leak control과 수정 후 구조가 일치했다. 불필요하게 table을 새 결함/새 수정 성공으로 만들지 않았다.

### 비차단 참고

JSON projection에서 delivery.steps/runtime_reached 등 원문이 아닌 운영 필드도 줄었다. 모델은 의도된 작은 진단 계약, bundle 내부의 소비 의존성 부재, ID별 status 조회 안내를 근거로 Medium으로 올리지 않았다. 외부 JSON 소비자 의존성이나 실제 status 명령 출력은 이 bundle에서 검증하지 않았다. 유용한 metadata가 모두 보존됐다는 보편 주장도 하지 않는다.

## 근거와 한계

- [수정 근거](doctor-privacy-fix.json), [정확한 delta](doctor-privacy-fix.patch), [로컬 수정 보고](doctor-privacy-fix.md)의 실제 CLI before/after12 stdout, targeted24개 양 Python green, red2 failure, 변이3종을 읽었다.
- evaluator는 실행 전 source 두 파일·patch·제공 log/capture39개 hash를 확인했다. private review bundle의 검증 파일은46개다. 검토 후에도 두 source hash가 일치했다.
- 모델은 읽기 전용으로 source와 캡처를 검토했으며 테스트 재실행·변이 재현·SHA 재계산은 하지 않았다. evaluator의 hash 검증과 독립 runtime 재현을 구분한다.
- scalar name/alias/ref/runtime은 의도적으로 남긴 운영 metadata다. universal anonymization을 새 요구로 추가하지 않았다.
- approvals/threads_replaced는 delta 밖이다. 비숫자 t 처리와 같은 baseline 동작도 이번 수정의 새 결함으로 산입하지 않았다.
- 기존1697은 이전 source의 history다. **병렬 진행 중인 new1700 full 결과는 이 판정에 포함하지 않았다.** 실제 UI·원격·전체 계획 완료와도 별개다.

## 보존

raw JSON·stderr·prompt·before/after source·실제 캡처/log bundle은 `/private/tmp/g10-doctor-opus-delta-0us8i83t`에 private 권한으로 보존했다. 상태 파일 `/tmp/g10-doctor-opus-active.json`에는 completed·PID·actual model 증명이 남아 있다. raw 본문은 공개 산출물로 복사하지 않았다.

[공개 요약/actual ID/source hash/한계](g10-doctor-privacy-opus-review.json)
