# G10 — 로컬 기술 판정

최신 로컬 판정은 doctor privacy v2 source의 passed다. [현재 고정본](../../../../deliverables/p13-live/doctor-privacy-v2-source-manifest.json)은315파일·135 primary이며, [전체 회귀](../../../../deliverables/p13-live/doctor-privacy-v2-regression.json)는 Python3.9.6 **1700개/435.648초 OK**, Python3.14.6 **1700개/319.740초 OK**, skip0이다. 현재와 고정본 primary hash는 일치했다. 전체 계획·사람 UI·clean 인증/첫 모델 왕복의 완료는 아니다.

doctor가 queued/unknown 원장 행의 preview와 임의 error prefix를 출력하던 경로를 [수정](../../../../deliverables/p13-live/doctor-privacy-fix.md)했다. 실제CLI red2→green, 양Python24개 영향 검사, 변이3종을 확인했다. 실제 선택 home/session을 둔 [postfix 진단](../../../../deliverables/p13-live/doctor-privacy-native-20261029-828fa71c/report.md)은 표식7종누출0·원장5파일불변·사용자runtime생존을 확인했다. [구독 Opus5.5 단일 delta검토](../../../../deliverables/p13-live/g10-doctor-privacy-opus-review.md)는 실제model과Medium+0을 확인했으며, 모델의 시험 재실행이나 모든외부JSON소비자 검증으로 확대하지 않는다.

첫1700 full은 두Python모두 부모종료테스트의 상속홈 불일치로 errors1이었다. [원 실패](../../../../deliverables/p13-live/doctor-privacy-v1-failure-preservation.json)를 보존하고 해당test한메서드의홈 fixture만 [정정](../../../../deliverables/p13-live/doctor-privacy-test-isolation-fix.md)했다. 제품 홈 가드·기존 assertion·실행 의미는 유지했다. 이 테스트 환경 정정은 Opus가 검토한 제품 delta와 분리하며, v2의 제품 SHA는 검토 source와 동일하다.

아래 설치/1667 기록은 이전 source epoch의 이력이다.

현재 판정은 로컬 기술 계약 passed다. 실제 CLI에서 재현한 clean Claude MCP 등록 충돌과 손상 MCP 설정의 제거 실패를 수정했다. [종결 기록](../../../../deliverables/p13-live/clean-install.final.json), [원인·범위·같은 경로 readback](../../../../deliverables/p13-live/clean-install.md)에 근거를 모았다. Claude/Codex의 clean·stale·current 6셀, 다중 홈 실제 설치/제거, 손상 JSON·symlink·native 제거 실패의 명시 exit와 보존을 확인했다. 두 Python 각각 91개 영향 검사와 두 변이를 확인했다.

설치·제거와 질문 reply claim 수정까지 포함한 [최종 로컬 고정본](../../../../deliverables/p13-live/post-qa-regression.json)은 Python 3.9.6의 1667개/433.487초, Python 3.14.6의 1667개/322.974초가 모두 OK다. skip은 없고 실행 뒤 관련 파일 133개의 hash가 일치했다. 이전 1648개·1649개 결과는 각 고정본의 역사로 유지한다.

원 실패는 [clean 결과](../../../../deliverables/p13-live/clean-install.json)에 그대로 남겼다. 기존 named matrix가 `--no-mcp`였던 한계를 실제 CLI 등록 검사로 보완했으며, source 정의나 파일 존재로 대신하지 않았다. 새 clean 프로필의 인증과 첫 모델 왕복은 전제 미충족으로 미실행이다. 로컬 기술 판정을 전체 J01·지원 행렬·원격·UI·70개 수용 조건 완료로 확대하지 않는다. 기존 Opus 검토와 지적 종결 범위는 [B05 기록](B05-local-integration.md)에 보존하며 전체 모델 검토를 반복하지 않았다.
