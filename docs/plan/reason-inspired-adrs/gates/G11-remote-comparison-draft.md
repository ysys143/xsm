# G11 — 원격 비교 판정 초안

판정 제안은 **partial**이다. 같은 두 물리 머신에서 A/B/D native 9회와 C native 6회, 별도 cached 회수 5회가 확보됐다. 양방향 SSH 불가를 포함한 나머지 물리 환경과 신규 설치·운영 비교의 미확인 항목은 남아 있다. 이 초안은 G11 passed나 A21-03 종결을 확정하지 않는다. plan.json·catalog·실행 계획의 gate 상태는 수정하지 않았다.

기준은 [execution.md의 G11](../execution.md), [spec.md P11](../spec.md), [A21-03](../acceptance.md)이다. G11은 설치·사용자 개입·첫 왕복·경로·운영/제거의 공통 비교와 물리 조건별 지원 불가/실패/미실행 구분을 요구한다. **D12 선택 자체는 G11 통과 근거에 포함하지 않는다.** D12 미응답과 별개로 아래 증거 부족 때문에 전체 판정은 미완이다.

## 확보된 증거

| 기준 | 실제 관측과 근거 | 적용 한계 |
|---|---|---|
| 같은 두 머신·같은 실제 과제 | `Jaesolui-MacBookPro.local` ↔ `Jaesolui-Macmini.local`, marker `P11-QA-40c1afc34bbd43c4`, `2+2=5` 검토. [A/B/D 보고서](../../../../deliverables/p11-live/native-carrier-roundtrip-20261029.md)·[JSON](../../../../deliverables/p11-live/native-carrier-roundtrip-20261029.json), [C 보고서](../../../../deliverables/p11-live/C-native-roundtrip-20261029.md)·[JSON](../../../../deliverables/p11-live/C-native-roundtrip-20261029.json) | carrier fixture의 native QA. 제품 xsm 발견·권한·첨부·사용자 UI 성공으로 확대하지 않음 |
| 첫 왕복·후속·재연결 뒤 새 답 | A/B/D 각 3회, C 두 실행 각 3회: 실제 native 합계 15회. C는 본문을 engine으로 전달하고 native 실행 trigger(phase·예상 본문 SHA)는 SSH로 보냈다. C의 재시작은 local daemon만이며 peer daemon·SSH control은 유지했다. 모두 동일 marker와 `false/4`, 짧은 반례. peer 실제 CLI `/opt/homebrew/bin/codex`, `codex-cli 0.163.0` | 기존 ChatGPT 구독 인증, 매번 새 ephemeral conversation. native resume 시험 아님. 단일 표본의 시간으로 후보 성능 순위를 정하지 않음 |
| cached 회수 | A/B/D 각 1회와 C 2회, 합계 5회. 원 답을 모델 재호출 없이 회수 | native 15회와 별도 집계. C는 local private daemon 재시작/등록 뒤 offline 상태의 local inbox 회수. A/B/D는 carrier를 다시 연결해 peer 답 회수; 시간·네트워크 경계가 다름 |
| 실제 경로 | A LAN SSH, B 설계상 private LAN TCP, D tailnet SSH와 LAN direct underlay. B의 bootstrap/제어도 tailnet SSH였고 phase별 실제 socket endpoint trace는 없음. C는 매 native 뒤 양쪽 `link=direct` | C wire IP/port·선택 relay URL unknown. `relay_connected=true`를 본문 relay 경유로 해석하지 않음. 다른 NAT·강제 relay 성공 아님 |
| 개입·인증·권한 구분 | 실행 중 사용자 개입 0, 기존 SSH/hostkey/Tailscale/구독 인증 재사용. C는 전체 비교 요청에 대한 코디네이터 판단으로 두 controlled node의 일시 private fixture membership만 사용 | 별도 C 팀 명시 승인 응답 없음. 신규 onboarding의 인증/가입/동의 조작 수 미측정. 제품 origin·업무 승인·실제 사용자 identity 수용은 별개 |
| 시작 확인·정리 | A/B/D peer driver 6개·native 9개 종료, B 49909/49941 연결 거절. C daemon handle 10개·native 6개·SSH control 2개 종료, own IPC 연결 거절·private state/HOME/키/binary 사본 제거 | 기존 SSH/VPN/Reason 서비스는 중지·제거하지 않음. 운영 제거·키 회수·원격 중단 중 제품 로컬 유지 전체 시험은 미실행 |

최신 공통 비교표·정확한 단계별 시간·원시 증거 경로는 [remote-decision.md](../remote-decision.md)에 있다. 과거 합성 RPC, C 초기 로컬 IPC 14개와 peer staging은 역사로 보존하며 native 15회에 합산하지 않았다. A/B/D의 이전 보고서가 남긴 C 미실행 문구는 그 시점의 범위이고, 후속 C 보고서가 이를 보완한다.

## C 시험 범위에 대한 코디네이터 판단

기존 사용자의 전체 P11 비교·격리 비교 실행 요청을 근거로 코디네이터가 두 controlled node만의 자기완결 일시 fixture라고 판단해 C 팀 생성·가입·client 등록을 실행했다. 별도의 C 팀 생성/가입 명시 승인 응답은 없었다. 이 요청 범위 판단과 실제 사용자 팀·전역 권한 및 D12 제품 선택을 구분한다. 실제 Jaesol’s network·현재 `.reason` 상태·실제 Reason CLI/계정·전역 membership·프로필/MCP·기존 업무 session은 사용·변경하지 않았다. engine은 고정 0.12.10 SHA `6ac4bb4837469867edc2dba3cbbd6e4dd9fb18ad0389db69ff6ef21683317a44`의 private 사본이다.

fixture roster는 두 endpoint로 제한했고 `verified=false`, `has_proof=false`였다. capability는 메모리·기존 SSH stdin·private IPC로 전달하고 공개 결과는 hash/상태로 제한했다. 자체 state/키는 종료 뒤 제거했다. 코디네이터의 시험 범위 판단이나 엔진 membership은 제품 backend·새 종속성·relay 운영·사용자 팀 편입·업무 권한 확대·배포의 승인이 아니다.

## 남은 판정 자료와 owner

| 미완 항목 | 현재 판정 / 재검토 조건 | owner |
|---|---|---|
| 양방향 SSH 불가 | A21-03이 명시한 환경 미실행. 현재 모든 비교의 제어/bootstrap은 기존 SSH를 전제. sshd 없는 승인된 상대/격리 환경 확보 시 재검토 | 실환경 담당·코디네이터 |
| 다른 NAT·다른 후보 UDP 차단·HTTPS proxy | C own engine UDP 제약/relay 추가 표본 외에는 미실행. LAN/direct 결과로 대체하지 않음 | 실환경 담당·사용자 |
| 자체 relay | C의 기존 서비스 relay 경유는 추가 확인. 자체 relay는 미실행. 기존 서비스 연결 상태만으로 성공 처리하지 않음. 승인된 서버·강제 경로 조건 확보 시 재검토 | 실환경 담당·코디네이터 |
| 신규 설치·사람/도구 개입 비교 | 기존 설치·인증 재사용과 fixture 도구 절차는 기록했으나 clean onboarding의 조작 수·전체 도구 호출 수를 동일 형식으로 확정하지 못함 | P11 비교 담당 |
| 운영·업데이트·키 회수·라이선스/공급 비용 | fixture 재연결·정리는 확보. 전체 운영·회수·제품 제거 비용의 실측 비교는 미완. 고정 source 및 기존 라이선스 자료를 제품 공급 수용으로 승격하지 않음 | P11/P12 담당·공급 검증 담당 |
| 독립 검토·G11 확정 | 위 부족 셀과 반대 증거를 같은 기준으로 대조한 독립 판정 필요. 이 초안으로 passed를 만들지 않음 | 코디네이터·독립 검증 담당 |

지원 불가, 시험체 미구현, 환경 미확보/미실행을 구분한다. B의 NAT/relay 미구현은 최소 Python spike의 한계이고 C의 현재 peer 부재를 뜻하지 않는다. 미완 셀의 생략 승인이나 새 완료 판정 권한은 만들지 않았다.

## D12와 P12 전달

D12는 사용자 미응답·미선택이다. P12는 [execution.md](../execution.md)의 G04/G05/G06/G07/G09/G10/G11 및 D12 선택을 모두 충족해야 한다. 이번 자료는 로컬 gate 상태를 바꾸지 않으며 G11 미완과 D12 미선택이 남아 있어 **P12 전제 미충족**이다. backend/default/catalog/plan.json을 변경하지 않았다.

## 문서 대조 기록

문서 통합 시 두 결과 JSON의 native/cached 개수, 각 5개 실행 행의 시간, `codex-cli 0.163.0`, engine SHA, 보고서의 tmp 경로와 상대 링크를 읽기 전용으로 대조했다. 검사 명령은 `python3 -`의 표준 라이브러리 JSON/Markdown 대조이며 새 engine/model/물리 환경 실행은 0회다. Python 3.9.6/3.14.6·111개 파일 hash·변이 거절 3개씩은 [기존 C 기록 검사](../../../../deliverables/p11-live/C-evidence-check-20261029.json)의 결과로만 인용한다.

## 독립 검토와 후속 수정

Opus 5.5의 1차 읽기 전용 검토는 partial 유지와 문서 수정 필요였다([원문](../../../../deliverables/p11-live/opus-review.md)). 코디네이터가 C의 SSH trigger/local-only cached 회수, B의 tailnet 제어와 phase별 경로 증거 부재, D 추천의 운영 가설과 unstable/dev 전제, 별도 승인 이벤트 부재를 문서에 반영했다. 이 수정은 물리 환경의 새 실행이나 G11 passed 판정이 아니다. 기록 검사에는 새 실행 시각과 실제 검사한 manifest/result/checker hash를 결속한다.

## 검토 뒤 추가한 C 제한 셀

[UDP 차단/relay 보고서](../../../../deliverables/p11-live/udp-blocked-report-20261029.md)의 실제 native1회와 양쪽 link=relay를 기본 비교15회와 분리해 추가했다. 기존 cached5회는 변함없다. 제한은 own daemon의 커널 UDP outbound deny이며 네트워크 전체 firewall이나 다른 후보의 같은 조건을 검증한 것은 아니다. 이 추가 표본은 코디네이터의 오프라인 기록 대조 범위이고 앞선 Opus1회 검토 범위에 소급 포함하지 않는다. G11은 partial이다.
