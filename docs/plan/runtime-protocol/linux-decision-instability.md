# Linux 부하 중 승인 검사 불안정성

상태: 실패는 확인했고 원인은 아직 미확정이다. 승인 정책을 완화하거나 원래 실패를
후속 성공으로 대체하지 않는다.

| Source | 검사 | 관측 |
|---|---|---|
| b2086dd | Linux3.11 전체 core | scopes의 join 승인에서 caller/scope changed |
| 9d1f5bb | Linux3.11 단독 scopes20회 | 전부 통과,33.952초; 원래 실패 미재현 |
| 9d1f5bb | Linux3.11 전체 core | 첫 link의 decision.response 시간·상태 거부 |
| 455f426 | Linux3.11 전체 core |962개/schema/v7 통과; 정책 수정 없음 |

앞선 두 전체 실행의3.14는 통과했고 모든 VM은 stopExit=0이었다. 오류 문구만으로
PID 재사용·ps start 변동·wall clock rollback·만료 중 하나를 단정할 수 없다.

`tests/fixtures/protocol_observed_host.py`는 실제 stdio 서버에 실패 관측만 붙인다.
Caller 거부에는 state reason, saved/observed ps start, kernel start, generation과
cwd 일치 여부를 기록한다. Response 거부에는 pending 상태와 실제 predicate에
쓰인 time.time 값·코드 위치를 기록한다. 정상 모드에서 원래 함수 반환값과 시각을
바꾸지 않는다. 토큰·질문·경로는 출력하지 않는다. 두 명시적 시뮬레이션은 실제
발생 원인 증거가 아니라 관측기 검증이며 정상 scope와 합쳐3개/5.304초에 통과했다.

`scripts/probe-clock-stability.py`는 실제 wall clock을 monotonic read 두 개로
감싸 측정한다. 읽기 중 스케줄링 지연을 단순 clock offset으로 잘못 판정하지
않도록 두 monotonic 값의 범위를 사용한다. Wall clock 역행과1ms를 넘는 범위
이탈, 같은 PID의 ps/kernel 시작값 관측 변화를 보존한다. 프로세스 시작값의
읽기 실패를 PID 재사용으로 단정하지 않는다. 시스템 시각이나 설정은 변경하지 않는다.

Mac1초 경로 실행은243개 표본/역행0이었다. 이는 Linux나 과거 실패의 증거가
아니다. 다음 Linux 부하 실행에서 개별 승인 거부 관측과 독립 clock 관측을 함께
보존한다. 원시는 `deliverables/protocol-foundation/`의 hermes-messaging-linux,
hermes-messaging-observed-linux, scope-repeat-linux, scope-clock-full-linux 및
hermes-messaging의 로그로 구분한다.

0f3e3c2의 실제 Telegram 경로27개/11 HTTP 뒤 부하 검사도962개/schema/v7을
85.302초에 통과했고 stopExit=0이었다. 별도105초 관측은43,017표본/역행0/
start observation 변화0이었다. 그 실행에 과거의 결함이 재현되지 않았다는
증거이며, 이전 실패의 원인 또는 해결을 증명하지 않는다.
