# G04 — 회수 가능한 인계의 로컬 기술 판정

- 판정: passed, B04 고정본의 로컬 계약. 전체 70개 수용 조건의 완료 판정이 아니다.
- 선행: G03 passed. D05의 claim 120초·확인 전 원문 유지·확인 뒤에도 원문 보존을 적용했다.
- 대상 revision: `deliverables/b04-live/frozen-regression.json`의 snapshot 및 파일별 SHA-256. 이후 P06/P08/P10 준비가 진행 중인 현재 작업 트리 전체의 최종 검증으로 확대하지 않는다.

## 실행 증거

| 경로 | 명령·실제 결과 |
|---|---|
| 전체 회귀 | 고정 snapshot에서 `env -i … python3.14 -m unittest discover -s tests` → 1517개, 259.178초, OK (`/tmp/b04-frozen2-314.log`) |
| 전체 회귀 | 같은 snapshot에서 `/usr/bin/python3 -m unittest discover -s tests` → 1517개, 335.690초, OK (`/tmp/b04-frozen2-39.log`) |
| 실제 일반 Codex 두 홈 | `PYTHONPATH="$PWD" /usr/bin/python3 /tmp/b04-native-profiles.py` → `.codex`·`.codex-3` 각각 `xsm_inbox`→`xsm_ack`→`xsm_send`; 원 요청과 결속된 succeeded 회신. `deliverables/b04-live/native-profiles.json` |
| strict FYI | 위 실제 하네스는 canonical `wake=False`로 저장한 요청을 MCP 소비 시점에 읽었다. 네이티브 queue/socket/wake를 호출하지 않는 검사는 `test_handoff_consumer` 및 `test_b04_interfaces`의 실제 send 경로로 별도 확인 |
| 구 reader | 설치된 `~/.xsm/runtime/2389da782089/xsm/inbox.py`를 실제 별도 Python 프로세스로 실행, export 1개 파괴적 소비 뒤 신버전이 원문 회수→ACK→중복 억제. `deliverables/b04-live/legacy-reader.json` |
| 중단 경계 | `test_handoff_crash`: 실제 SIGKILL, store/claim/ack/pre-replace 및 별도 reader 경쟁. `test_crash_boundaries`: canonical claim commit에서 CLI SIGKILL 뒤 lease 만료를 고정 시계로 재현하고 같은 원 ID 회수·ACK |
| 공개 인터페이스 | `test_b04_interfaces`: CLI/MCP read/ack, 자연 tool 소비, stdout 실패 release, provisional 거절, native hook token, transport 오류 후 명시 retry, 같은 본문 반복의 관측 |

첫 전체 회귀는 두 버전 각각 1517개에서 5 fail·3 error였다. 로컬 승인 안내를 peer body로 감싼 출력 회귀를 되돌리고, JSON 수신함 mock을 실제 계약과 맞췄다. 옛 `.taking` 유실을 기대하던 기준선 검사는 새 canonical claim의 실제 SIGKILL·회수 경로로 교체했다. 수정 후 좁은 41개 및 위 전체 회귀가 통과했다.

## Opus 5.5 검토와 수정 종결

`deliverables/b04-live/opus-review.md`의 1차 판정은 수정 필요다. 검토자는 셸이 없어 hash/외부 로그를 직접 검증하지 못했고, 검토 중 바뀐 MCP/decision 두 파일을 명시했다. 이 한계를 통과 판정으로 인용하지 않는다. 코디네이터가 실제 도구 출력·고정 snapshot·후속 검사로 대조했다.

- F1: native hook 문맥에도 claim token을 제공했다. 읽은 runtime이 명시 ACK하면 lease 만료 뒤 재전달되지 않는다.
- F2: EOF·실제 죽은 MCP reader는 pending display 소유권을 회수한다. waiter 취소는 질문 철회와 다르다. 취소·만료·dismiss 이후 사용자의 새 요청은 모든 form 도구가 제공하는 새 `decision_key`로 질문한다. 실제 거부는 자동 재질문하지 않는다. 별도 프로세스 MCP SIGKILL 뒤 같은 의도 복구도 검사했다.
- F3: transport refused/error를 canonical delivery_state에 기록했다. 명시 재시도 전에는 inbox에서 조용히 전달하지 않는다.
- F4: `reply-to`를 표시 데이터로 escaping했다. 원 헤더·본문 바이트는 유지한다.

네 수정 각각을 무력화하는 변이는 해당 반례 검사에서 실패했다(`deliverables/b04-live/review-mutations.json`). 독립 전체 재리뷰는 반복하지 않았다.

## 남은 통합 조건

A18-04의 원격 변경·readback·재시작은 G10/G12에서 계속 검증한다. A18-05의 설치 이행 조합은 G10의 책임도 남는다. 이번 실제 두 홈 평가는 별도 MCP를 주입한 구독 Codex CLI이며, 새 전역 훅·신뢰 정책을 설치한 표본이 아니다. G07의 실제 사람 UI 관측과 G09의 첨부/다회 N:N 전체 조건은 별도 미완이다.

첫 legacy fixture 실행은 XSM_HOME을 import 뒤에 설정한 실수로 제외했다. 자체 생성한 synthetic JSON만 검증해 정리했고, 기록은 `deliverables/b04-live/invalid-fixture-cleanup.json`에 남겼다. 첫 두 native 평가의 잘못된 임시 MCP 설정과 wake 거절도 별도 실패 JSON으로 보존했다. 성공 표본으로 합치지 않는다.
