# ADR-0021 실행 현황

2026-10-30 기준 ADR-0021의 A21-01부터 A21-07까지 7조건을 실제 기록의 전제·환경·제약 안에서 종결했다. 현재 goal은 `adr-0021 완주`이며 이전 전체 구현 goal과 과거 snapshot은 별도 이력이다. 최종 ccc3의 두 Python 전체 1936개 OK·skip 0, 마지막 delta Opus approved·findings 0, Newton 공통 math 17항목 통과·업무 3질문/3회신·준비 포함 총 8ACK·최종 코드 원답 조회·양쪽 cleanup 0을 확인했다. 실행 판정은 부모 코디네이터와 각 실험 담당자의 도구/원자료 확인에 따른다. 실제 사용자의 D12 제품 방향 결정과 구별한다. 전역 G11/G12/G13·다른 63조건은 승격하지 않는다.

## 최종 동결본·회귀·검토

- root: `/private/var/folders/hw/9m3g7fvn4_l3rp2y473km9sm0000gn/T/adr21-closure-final-1cnnq81i`.
- manifest SHA-256: `ccc3f22a1d65a33ddc76b0ad1abc4966a65664a6e41777d52b70230cd4fd4011`. 입력 178개·제품 Python 53개, 최종 검증 기록에서 작업 트리와 일치했다.
- `/usr/bin/python3 -B -m unittest discover -s tests -q`: 1936개 OK·skip 0·exit 0, 831.018초.
- `/opt/homebrew/bin/python3.14 -B -m unittest discover -s tests -q`: 1936개 OK·skip 0·exit 0, 534.329초.
- [최종 회귀 보고](../../../deliverables/adr0021/legacy-native-recovery-20261030/final-validation/report.md), [요약](../../../deliverables/adr0021/legacy-native-recovery-20261030/final-validation/summary.json), [입력 manifest](../../../deliverables/adr0021/legacy-native-recovery-20261030/final-validation/manifest.json), [3.9 원 로그](../../../deliverables/adr0021/legacy-native-recovery-20261030/final-validation/py39.stderr), [3.14 원 로그](../../../deliverables/adr0021/legacy-native-recovery-20261030/final-validation/py314.stderr)에 결속한다. 의도된 음성 출력과 기존 ResourceWarning은 보존했다.
- [최종 delta Opus](../../../deliverables/adr0021/legacy-native-recovery-20261030/final-surface-review/review-parsed.json) approved·findings 0, [실행](../../../deliverables/adr0021/legacy-native-recovery-20261030/final-surface-review/execution.json)의 ccc3 결속을 확인했다. `handoff.old_p2p_copy_receipt` 공유 분류·pending_ids read-only notice·take_inbox_claims/poll_replies의 현재 권한 check 유지에 대한 지정 정적 범위 승인이다. 실제 업무·전체 회귀·ADR 전체 승인을 대신한 것은 아니다.

## 7조건의 기록 범위 판정

| 조건 | 종결 근거 | 유지하는 범위 |
|---|---|---|
| A21-01 | 두 Mac LAN/direct·Tailnet 주소, 공개 relay·UDP 차단/CONNECT proxy·자체 relay·Mac/Android 다른 NAT 왕복, 제한된 SSH 서버 ping | proxy/자체 relay의 같은 호스트 조건, loopback HTTP relay, 기존 관리자 SSH 서버 프로토콜과 전용 forced-command 경로 차이 |
| A21-02 | 두 Mac 정책 반례·founder 없이 초대/추가/제명, 키 교체, 실제 3서비스의 응답 유실·join-status·연속 전환/복귀·복귀 실패 후 현재 팀 보존 | 정책 FILE actor와 실제 모델 구별, 같은 호스트 3서비스 및 상호 신뢰 멤버십의 한계 |
| A21-03 | 과거 native15/cached5와 B-spike/B-product 분리, 실제 시작/가입/개입·운영/제거 비교, A/D 최초 SSH 음성, 최신 math/check17·최종 회수·복구 집계 | 처음 math 주제만 동일. 하네스·과제·cached/시간 경계 차이와 미지원·미실행·미계측 유지. 전역 G11 판정 불변 |
| A21-04 | 실제 두 Mac 동일 CID·다른 런타임 자료 여정, 동명 self/remote 선택·ACK·오배송0, 최신 math의 원 ID·3답 readback·8ACK | 초기 등록 setup·source 변화·과거 profile 관측 한계. 자동 wake·무보정 onboarding 성공으로 확대하지 않음 |
| A21-05 | 실제 로컬 질문/직접 회신의 원격 중지·엔진 링크 차단 독립성, 실제 private 설치→공유 서비스 보존→명시적 stop→uninstall·PID/socket0·UDP 재bind | 공개 relay 자체 중단과 소유 링크 차단 구별. key/runtime/원문/audit의 의도된 보존 |
| A21-06 | 가입 전후 published/unpublished/excluded·숨김 probe0·private 경로 비공개·공개만으로 task 거절·제명/협업 철회/매핑 변경 소비 거절 | 가입·공개·협업·파일/실행 권한 구별. 비공개 CLI 내부·hosted MCP 서버 미검증 |
| A21-07 | 실제 엔진 AF_INET6 실패 주입·IPv4 bind/init/join/ping·고정 포트 fallback·주소 변경과 실제 IPC 주소 갱신 | 실제 호스트 전체 IPv6 부재와 제어된 프로세스 고장 주입을 구별. 원 실패 보존 |

전체 명령·해시·환경·실패·제약은 [7조건 종료 기록](adr-0021-closure.md), 공통 단계·지표·비용은 [최종 비교](../../../deliverables/adr0021/comparison-20261030/report.md)와 [집계 JSON](../../../deliverables/adr0021/comparison-20261030/summary.json)에 있다. 기록 범위에서 남은 필수 대기 셀은 없다. 원문 범위를 줄이거나 미지원·미계측을 성공으로 바꾸지 않았다.

## Newton 최종 실제 math·회수와 비교 마찰

[최종 원결과](../../../deliverables/adr0021/native-journey-common-math-latest-retry1-20261029T155548Z/results.json)는 passed·17항목 모두 true다. 원래 `9f11884127764cad`를 포함한 3업무/3회신과 준비 handshake 1쌍, 실제 양쪽 MCP/canonical ACK 8건이다. 원 ID/본문·역방향 endpoint 유지, 재시작 뒤 기존 답 2개 동일 reply ID 회수, 최종 ccc3에서 보존된 3답 read-only 조회, 구 held bytes 불변·양쪽 소유 cleanup 0을 확인했다.

최초 검토 `2+2=5`만 과거 A/B/C/D와 정확히 같은 주제다. 실제 JSON은 최초 false/4·수정 true/4·마지막 true/2다. `observed_same_host_seconds` 1298.9484422206879·110.46094274520874·81.29840421676636은 Mini 시계의 생성→회신 수신 전체 경과이며 두 물리 Mac P2P 업무다. 소스 수정·수신 대기·일반 계속 Goal·resume·주소 교환을 포함하고 순수 네트워크 지연이나 성능 순위로 쓰지 않는다. cached 원답 회수의 단독 소요는 미계측이다.

성공 retry1 집계는 Claude CLI 1·Codex CLI 5(같은 CID resume4), 일반 FIFO 계속 Goal6·표준 MCP 재접속2, 서비스 최초2+계획 재시작2+stable-port 복구 시작2, 정상 주소 교환2·invite1/join1이다. 실제 MCP ask4는 전송 전 거절1·같은 ID 재시도를 포함하며 논리 업무는3이다. 추가 human yes0·본문/답변 중계0이다. 앞선 준비 정책 실패1건·실제 held 수신 차단·재시작 새 포트 hint 실패와 정상 복구를 각각 보존했다. 중간 3쌍6ACK·MCP 재접속1건·계속 Goal1회의 관측을 최종 집계에 더하지 않는다.

실행 manifest `942a5deca7ccb0ec89cfc92e71fa52495fa6ff92cdb16251125db99728bdf03f`와 최종 회수 ccc3를 구별한다. 같은 CID를 유지하며 source 수정·MCP 재접속 후 원문을 회복한 여정이며, 전 과정이 변경 없는 ccc3였던 무보정 benchmark로 쓰지 않는다. 새 승인·held 사본 delivery·수동 peer 파일 보정·기존 원문 보정은 없었다.

## 보존한 이력과 판정 경계

- 5e20 manifest `5e203237d953a8b656ff4083503fd8b9b5c02c744a3f4939b1ce3236bda461ec`의 전체1933개(3.9 562.074초·3.14 374.320초), 추가3반례/3변이·지정범위 Opus approved는 [그 당시 기록](../../../deliverables/adr0021/final-validation-20261030/report.md)으로 보존한다.
- 직전 62bb manifest `62bb612595c09a535ab0866852c25164aa55ccf9b1c7ac580b364cdb86fda32f`의 전체1935개(3.9 799.788초·3.14 522.792초)·predicate 집중검토 승인도 당시 이력이다. 이전1915개 실패·1918개 통과와 기존 changes_required를 수정하지 않았다.
- [물리 정책](../../../deliverables/adr0021/physical-policy-20261029T073330Z/report.md), [키 교체](../../../deliverables/adr0021/key-rotation-20261030/report.md), [연속 팀 전환](../../../deliverables/adr0021/team-switch-20261030/report.md), [실제 로컬 장애 여정](../../../deliverables/adr0021/physical-policy-a21-05-native-20261029T090428Z/report.md), [실제 설치·제거](../../../deliverables/adr0021/uninstall-20261030/report.md)는 각 동결본의 실제 범위를 보존한다.
- pure latency·bootstrap 세부 시작·사람 판단 대기·provider 내부 스케줄링·숫자 없는 운영/업데이트/라이선스 비용은 미계측이다. 최초 인증 전체와 후보별 업데이트 전수는 새 A21 의무로 만들지 않았고 관련 P10/A23 검증을 대신하지 않는다.
- 코디네이터가 확인한 과거 색인의 `audit --structure-only` exit1, 조건29행 stale·전역 카탈로그/결정/집계/통합5항목 한계와 과거1700 snapshot은 유지한다. 이번1936개 통과·ADR21 기록 종결을 다른63조건·전역G11/G12/G13·전체70조건의 승격으로 사용하지 않는다.

실제 사용자의 D12 선택은 자체 P2P 기본·선택적 Tailscale·공개 relay 기본/자체 설정·계정 비필수·Reason식 동등 멤버 권한의 제품 방향 결정이다. 코디네이터/실험 담당자의 조사·실행·검토 결과를 실사용자의 코드 조사나 성공 판정으로 귀속하지 않는다. 최종 문서 정리는 closure/progress만 수정했으며 제품·검사·모델·실험·전역 설정·권한·키·staging·commit/push는 변경하거나 재실행하지 않았다.
