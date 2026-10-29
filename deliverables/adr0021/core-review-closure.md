# ADR-0021 기초 P2P 검토 결함 수정 증거

기존 Opus Medium F1·F2의 수정 경로를 새 회귀 7개와 source guard 제거 변이 5종으로 확인했다. 이 문서는 해당 두 경로의 제한된 수정 증거이며 전체 ADR-0021 완료 판정이나 새 Opus 승인이 아니다. coordinator의 제품 소스는 편집하지 않고 `tests/test_network_recovery.py`만 추가했다.

## F1: 네트워크 전환 뒤 이전 피어로 새 멤버십 전송

`_install` 뒤 `_load_peers`가 이전 목록을 비우고 목적 네트워크의 저장 주소만 다시 읽는 경로를 실행했다. 목적 네트워크 cache에 이전 그룹 주소를 의도적으로 섞어도 그 주소가 남지 않았다. sync는 현재 그룹 상대에게만 새 state를 전달했다. 이전 주소를 메모리에 다시 삽입한 경우에도 `rpc(sync)`가 전송 전에 거절했고 이전 피어에게 전달된 요청은 0개였다.

이 검사는 **서버 단위 RPC fixture와 실제 Rust Ed25519 sign/verify의 조합**이다. 멤버십·admission·파일 저장은 실제 구현이며 RPC 응답 전달은 제어된 fixture다. 실제 QUIC 전환이나 물리 머신 검사를 뜻하지 않는다.

## F2: sidecar 종료 뒤 daemon·lock 잔류

private CLI 서비스가 보고한 engine PID를 live Popen 부모·실행 파일명·UID와 대조한 뒤 그 engine만 SIGKILL했다. 실제 EOF를 감지한 daemon의 종료, Unix listener 해제, service lock 재획득, UDP port 재바인딩을 확인했다. 이후 공개 `xsm network start`로 service를 다시 띄워 endpoint ID·network ID·멤버십과 기존 초대 파일 bytes가 유지됨을 확인했다. init/invite의 추가 실행은 0회이고 초대 파일 수는 전후 1개였다. 개인키 파일은 읽지 않았다.

종료 코드 0으로 끝난 경쟁 starter가 기존 listener 정리 뒤 service만 다시 spawn하는 경합은 별도 fixture로 검사했다. spawn 명령은 `serve`뿐이고 RPC는 `status`뿐이었다. 종료 코드가 0이 아닌 실패는 재시도하지 않았다. 기존 fake JSONL engine을 재사용해 `running`·`process_id`의 시작 전, 실행 중, EOF, close 및 watcher 통지 전 process-poll 구간도 확인했다.

## 실행 결과

| 실행 범위 | Python 3.9.6 | Python 3.14.6 |
|---|---:|---:|
| 고정한 수정 소스 복사본의 새 회귀 | 7 통과 / 스킵 0 | 7 통과 / 스킵 0 |
| 병렬 앱 코드 추가 후 현재 원본의 실제 CLI 복구 사례 | 1 통과 / 스킵 0 | 1 통과 / 스킵 0 |

기본 명령은 `python -B -m unittest tests.test_network_recovery -v`다. 실제 interpreter 경로·cwd·출력 SHA·PID·source SHA는 [closure JSON](core-review-closure.json)에 기록했다. 두 현재 원본 재확인 실행 중 추적한 소스/테스트 6개는 변경되지 않았다. 전체 suite와 서비스8 전체를 다시 실행하지 않았다.

| 제거한 source guard | 선택 회귀 결과 |
|---|---|
| `_install`의 peer 재로딩 | assertion 실패 |
| sync의 현재 멤버 검사 | assertion 실패 |
| 실제 engine EOF 감시 조건 | assertion 실패 |
| 종료 코드 0 뒤 service 재시작 | assertion 실패 |
| `running`의 process poll | assertion 실패 |

변이는 private 소스 복사본에만 적용했으며 5/5가 exit 1의 assertion 실패로 검출됐다. coordinator의 원본 source guard를 제거하지 않았다.

## 원 검토 보존과 한계

[기존 Opus 보고서](core-opus-review.md)와 [원 판정 JSON](core-opus-review.json)은 SHA가 그대로이며 `changes_required` 판정도 변경하지 않았다. 이후 모델 호출은 0회다. 테스트 뒤 원본 `network.py`에 앱 gateway helper와 startup `identity.json` 쓰기가 추가돼 전체 파일 SHA는 고정 복사본과 다르다. `start`, `_install`, `_load_peers`, `rpc`, `watch_engine` 본문이 동일함을 대조했고 변경된 현재 `serve`는 실제 CLI 복구 사례로 양 Python에서 재확인했다. 그 밖의 앱 통합은 이번 검사의 판정 대상이 아니다.

실제 CLI 종료는 init/invite가 완료된 뒤 idle engine에서 수행했다. 임의 business operation의 실행 중 crash 복구, Byzantine/offline-fork 보장, 관리자·새 로그인, 물리 머신·NAT·relay·proxy 검증으로 확대하지 않았다. 테스트가 만든 서비스와 자식 engine만 다뤘으며 기록된 테스트 PID는 정리 뒤 모두 사라졌다.

private source 복사본·실행 로그·변이 로그는 `/private/tmp/adr0021-core-closure-5xtl1vz8`에 보존했다. 디렉터리 0700·파일 0600이며 원문에 초대나 키 값을 기록하지 않았다.
