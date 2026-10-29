# Reason에서 배운 설계의 구현 진행

## 2026-10-30 ADR21 종결

별도 `adr-0021 완주` 목표에서 A21-01–07의 7조건을 기록된 전제·환경·제약 안에서 종결했다. [조건별 종료 기록](adr-0021-closure.md)과 [진행 현황](adr-0021-progress.md)이 현재 기준이다. 아래 전체 계획 체크포인트는 ADR21 착수 전 이력이며, 그 안의 P12 미착수·다른 NAT 미관측을 현재 상태로 쓰지 않는다. 다른 63조건·전역G11/G12/G13·운영 배포의 판정은 바꾸지 않는다.

최종 manifest는 `ccc3f22a1d65a33ddc76b0ad1abc4966a65664a6e41777d52b70230cd4fd4011`이다. 제품53개 모듈을 포함한178개 입력이 검사 뒤 작업 트리와 일치했다. [최종 회귀](../../../deliverables/adr0021/legacy-native-recovery-20261030/final-validation/report.md)는 Python3.9/3.14 각각1936개 OK/skip0이며, [마지막 delta Opus5.5 검토](../../../deliverables/adr0021/legacy-native-recovery-20261030/final-surface-review/review-parsed.json)는 approved·findings0이다. 이전1933/1935개·최초 실패·이전 검토는 각 소스 이력으로 보존한다.

두 물리 Mac의 실제 발견·선택·동명 핸드셰이크·자료 검토·질문/직접 회신, 같은 CID 재개, 실제 휴대폰의 다른 NAT 왕복, IPv6 고장/포트 대체, 원격 장애 중 로컬 협업을 확인했다. [기존 소속의 가입 응답 유실·전환/복귀](../../../deliverables/adr0021/team-switch-20261030/report.md), [실제 설치·중지·제거](../../../deliverables/adr0021/uninstall-20261030/report.md)도 수행했다.

마지막 실측에서 구형 native 사본의 영수증이 현재의 정상 정본을 숨기는 결함을 고쳤다. MCP 수신·미독 표시·답 조회가 같은 엄격한 분류를 사용하고 현재 인증/권한 검증을 다시 거친다. 실제 held·현재 권한 거절·원문·기존 보류 사본을 보존했다. [최종 공통 업무](../../../deliverables/adr0021/native-journey-common-math-latest-retry1-20261029T155548Z/report.md)는 같은 두 대화의 질문3건/직접회신3건·준비 포함8ACK·원답 회수·최종 코드 readback·정리를 완료했다. 수신 실패·소스 수정·재접속·재개·주소 힌트 교환이 포함된 경과이므로 성능 순위를 만들지 않았다.

전체 계획의 과거 완료 색인은 현재 소스에 재결속되지 않아 구조 감사 exit1이며 전역G13은 미완이다. 이번 작업은 전역 설치·배포·commit/push를 수행하지 않았다.

## 전체 계획의 이전 체크포인트

2026-10-29 현재 전체 계획은 미완이며 구현 goal은 사용자 요청으로 일시정지 상태다. 08:00까지 완수하지 못했다. 진단 원문 노출을 수정하고 새 source의 전체 회귀·실제 CLI·Opus 검증을 마쳤다. D12의 제품 요구사항은 [ADR-0021](../../adr/0021-cross-machine-network-and-membership.md)로 확정했으며 P12 제품 통합은 미착수다.

전체 단계와 기준은 [실행 계획](execution.md), [plan.json](plan.json), [수용 조건](acceptance.md)에 있다. 70개 수용 조건·잔여 20개·여정 9개의 범위는 유지한다. [완료 색인](completion-ledger.md)은 본 요구사항 결정 전 검증 스냅샷에 proven25·partial71·missing3으로 결속돼 있다. 이 25개는 수용 조건이며 잔여20개·여정9개는 전체 종결되지 않았다.

## 현재 검증

- 진단 함수 `install.stuck`이 queued/unknown 원장 행 전체와 원시 오류 prefix를 반환하던 결함을 수정했다. 필요한 상태·ID·표시 metadata와 고정된 오류 분류만 반환한다. 원장 정본은 바꾸지 않는다.
- 실제 CLI 반례에서 JSON·일반 텍스트 누출을 재현했다. 수정 뒤 두 Python의 영향 검사 24개씩과 변이 3종을 확인했다. 새 CLI 검사 3개를 추가했다. [수정 보고서](../../../deliverables/p13-live/doctor-privacy-fix.md).
- 구독 Opus 5.5 단일 검토에서 actual model을 확인했고 이 제품 delta의 Medium 이상 잔여 결함은 없었다. 모델이 전체 회귀를 재실행한 것은 아니다. [독립 검토](../../../deliverables/p13-live/g10-doctor-privacy-opus-review.md).
- 수정 후 실제 CLI는 표식 7종 누출 0건, queued/unknown/error 집계, 원장 5파일 바이트 불변과 현재 사용자 runtime의 생존을 확인했다. [실제 진단](../../../deliverables/p13-live/doctor-privacy-native-20261029-828fa71c/report.md).
- 첫 1700개 전체 회귀는 두 Python 모두 같은 테스트 오류 1개로 실패했다. 부모 종료 테스트가 상속된 Claude 홈과 다른 포인터를 등록한 것이 원인이다. 제품의 홈 가드는 올바르게 거절했다. [첫 실패 보존](../../../deliverables/p13-live/doctor-privacy-v1-failure-preservation.json).
- 해당 테스트 한 메서드가 자기 홈을 명시하도록 정정했다. 두 Python에서 원 테스트 실패, 수정 통과, 결속 제거 변이 실패를 확인했다. [테스트 격리 수정](../../../deliverables/p13-live/doctor-privacy-test-isolation-fix.md).
- 두 번째 고정본은 `/private/tmp/xsm-doctor-privacy-v2-frozen-i7xbamec`다. 파일 315개·primary 135개이며 이전 1697 source 대비 제품 함수 변경은 `stuck` 하나다. 테스트 파일 두 곳이 바뀌었다. 두 Python의 전체 1700개가 모두 통과했다. Python3.9.6은435.648초, Python3.14.6은319.740초이며 skip0이다. [최종 결과](../../../deliverables/p13-live/doctor-privacy-v2-regression.json).

G10의 로컬 기술 판정을 passed로 복구했다. 제품 전체·UI·원격 완료를 의미하지 않는다. 이전 1697개씩 OK인 `/private/tmp/xsm-final-receipt-frozen-i3u9pms3`와 첫 1700개 실패는 각 source의 이력으로 보존한다.

## 실제 사용에서 확인한 것

- 같은 repository와 linked worktree 사이에서 추가 link/join/publish/grant 없이 실제 회신 3회와 ACK를 확인했다. formal handshake 관측과는 구분한다.
- 서로 다른 실제 부모의 child 사이에서 직접 회신과 파일 읽기, claim/ACK를 확인했다. 부모의 본문 중계는 없었다. 현재 factory의 MCP는 대화마다 별도 process여서 공유 MCP 하나의 성공으로 세지 않는다.
- 발신자는 질문을 한 번 보낸 뒤 별도 CSV 작업을 마쳤고, 4.328초 늦은 실제 답을 원 ID로 회수했다. 수정본과 옛 사본도 각각 검토했으며 옛 bytes·digest·표식은 유지됐다.
- cached tools/list 상태의 수신 하향·미독 회수와, 기상 없는 FYI를 자연스러운 도구 사용 시 읽는 경로를 확인했다.
- 같은 strict 정책에서 정상 검토 3라운드 뒤 반복 보류, 원 ID 조회·재전송·최종 회신·ACK를 확인했다.
- 두 발신자의 문맥 분리·직렬화, 4개 busy 상태에서 다른 발신자의 요청 보류·회수, 퇴출 후 기억 소실과 독립 검토 격리를 확인했다. 이후 같은 private journal에 추가된 요청은 과거 request subset과 별도로 결속했다. 과거 journal 전체 SHA가 그대로라는 주장은 하지 않는다.
- claim 직후 종료한 실제 대화를 같은 CID·새 PID로 재개해 원문 회수·ACK·상관 회신을 확인했다. native MCP 취소 notification은 별도 미관측이다.
- 실제 old MCP를 유지한 업그레이드와 같은 native 대화의 회신을 확인했다. 실제 clean CLI 설치·제거와 손상 설정 보존도 검증했다. 새 clean 프로필의 로그인·첫 모델 왕복과는 별개다.

실패와 한계도 [관측한 마찰](../../../deliverables/p13-live/observed-friction-after-integration.md)에 남겼다. 앞선 headless reviewer 종료·CLI source 확인 누락을 보존했고, 후속 영속 TUI 표본에서 같은 본문/파일의 실제 CLI/MCP 네 왕복을 확인했다. 이번 문서 반영은 추가 실행이나 검증 판정 변경을 하지 않는다. 여러 기존 프로필 표본의 config hash drift는 변경 주체·의미가 미확정이다. source·원 실패·실제 호출·ACK·설정 보정의 범위를 바꾸지 않는다.

## 원격과 사람 입력의 남은 전제

D12의 제품 요구사항은 결정 완료다. 자체 P2P 기본·선택적 Tailscale 경로·공개 relay 기본/자체 설정·계정 비필수·Reason식 동등 멤버십을 채택했다. 관리자 계층과 별도 가입 승인은 두지 않는다. 라이브러리·버전·주소 등 구현 항목과 실제 운영 승인은 별개다. 기존 완료 색인은 이 요구사항 결정 전 실행 근거의 스냅샷이며, 그 안의 D12 미응답 표시는 현재 정책 상태로 사용하지 않는다. P11 carrier 비교는 native 18회·cached 5회이며, C의 소유 프로세스에 한정한 UDP 차단·CONNECT proxy·bootstrap 후 SSH 차단을 추가로 관측했다. 이를 제품 peer 발견·선택·승인·handshake의 성공으로 세지 않는다. [원격 비교와 한계](remote-decision.md).

P12는 제품 미착수다. `deliverables/p12-prep/`의 22개씩 검사와 변이 2개는 통합 계약의 준비이며 remote adapter/auth/join/directory/files/회복 구현 완료가 아니다.

실제 사람 UI의 이전 두 intent는 응답 없이 만료됐다. 표시·잘림·중복·늦은 답·철회 관측과 새 결속 답이 필요하다. 다른 NAT·기업 인증 proxy·자체 relay·신규 무SSH 설치와 실제 공유 MCP 조건도 각 근거의 공백으로 남긴다. credential을 복사하거나 만료 답을 새 승인으로 사용하지 않았다.

## 작업 경계

전역 설치·배포·commit·push·PR은 하지 않았다. 기존 staging과 사용자 작업, `.orca/`는 보존했다. raw/state/claim wire는 private tmp에 두고 공개 산출물에는 요약·코드·hash와 경로를 남겼다. 새 원격 요구사항의 확정이나 평가 fixture 성공을 실제 사용자 네트워크·서비스·권한 변경 승인으로 대신하지 않는다.
