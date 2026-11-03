# Hermes native queue 전달 지연

상태: Hermes0.22.5 gateway/TelegramAdapter + local platform transport의 Mac/Linux 각100표본이다.
실제 외부 Telegram·구독 모델·UI나6런타임/2OS 전체 지연 행렬의 인증은 아니다.
이전 Linux 승인 불안정성도 미해결이므로 전체 지원 완료의 전제는 충족하지 않았다.

`probe-hermes-messaging.py --platform telegram --latency-samples 100`은 실제 설치
plugin/NativeGateway/native FIFO drain/AIAgent/hooks/Tool Hub를 사용한다. 모델 대신
localhost scripted provider를 쓰고 플랫폼 send는 로컬 기록기로 바꾼다. 각 표본
전에 native idle을 확인하고, 표본 뒤에는 실제 turn 완료와 정확한 native ACK를
기다린다. 같은 표식의 FIFO admission이 정확히1개인지도 확인한다.

## 측정 경계

시작은 송신 RPC 호출이 아니다. 별도 송신 protocol 프로세스의 실제
`handoff.store`가 성공해 반환한 직후 `CLOCK_MONOTONIC` ns를 기록한다.
`tests/fixtures/protocol_timed_host.py`의 관측기는 원래 저장 결과를 바꾸지 않는다.
끝은 stdout 전송이 아니라 실제 native authority가 SQLite commit을 마친 뒤
`_admitted`를 호출한 시점이다. 두 프로세스는 같은 호스트의 동일 clock을 쓴다.
Scripted provider 처리와 외부 플랫폼 transit은 이 구간 밖이다.

원문 저장 tick은 stored.jsonl, native queue tick·admission ID·idle·ACK는 각
표본 결과에 보존한다. 결과를 매 표본마다 저장하며 attempted/completed/failed/
unexecuted를 구분한다. 실제 queue 관측만 제거한 변이는 native turn/ACK가
성공해도 timestamp 검사가 exit1로 거부했다. RPC 성공만으로 p95를 만들지 않는다.

## 관측 결과

| 표본 | OS/Python | 완료/실패/미실행 | p95 | 최댓값 |
|---|---|---|---|---|
| mac100-final | macOS26.5 arm64/Python3.14.6 |100/0/0|253.082ms|326.893ms|
| hermes-latency-linux | Linux arm64/Python3.14.10 |100/0/0|214.999167ms|221.388584ms|

Nearest-rank p95는 정렬한100개 중95번째 값이다. 저장 trace100개, 표본100개,
서로 다른 native admission ID100개와 raw ns 차이의 p95를 별도 재계산해 대조했다.
설치 engine과 보존한 source SHA256이 일치한다. Worktree probe 변경 상태에서
측정했으므로 pristine0f3e3c2 실행으로 표시하지 않고 source snapshot/manifest를
원시에 보존한다. 실제 provider 요청453개 중 native background review20개가
있었고, review 기능을 꺼서 수치를 낮추지 않았다. 실제 모델 과금 호출은0이다.

처음100개(mac100)는287.090ms였다. 이 표본에서 auxiliary API hook이 별도 review
SID에 불필요한 신원 조회를 해 경고를 냈다. 이 경고가 측정 차이의 원인이라고
판정하지 않는다. 보조 요청이 인계 문맥을 새로 만들지 않도록, pre_api 관측은 이미
열린 host의 실제 pending context가 있을 때만 신원을 검증하도록 수정했다.
기존 session/host/turn/전체 원문 검사와 native ACK는 유지한다. 해당 unit은 수정 전
실패했고 수정 후 기존 binding/context와31개/15.813초를 통과했다. 최종100개에는
그 hook 경고가 없으며 core963개/schema/v7도59.780초에 통과했다.

Raw HTTP는 요청 수를 제한하고 gzip으로 보존한다. 무제한 trace나 삭제한
실패는 없다. 최초2표본 smoke와 의도한 missing-queue 변이도 별도 경로에 남긴다.
Mac 원시는 `deliverables/protocol-foundation/hermes-latency/`에 보존한다.

Linux 후속 결과는 고정3cc635a이며 동일 native image의 Python은3.14.10이다.
Native729개 checkpoint/453 HTTP와 raw100개 ns 차이·100개 고유 admission ID를
대조했다. 설치 plugin unload와 warning 부재를 확인했고, 같은 소스의 전체963개/
schema/v7도3.11 84.026초/3.14 108.802초에 통과했다. 최종 status=passed/stopExit=0이다.
Mac 보존 source manifest의6개 측정 관련 파일 hash도3cc635a blob과 일치한다.
Linux 원시는 `deliverables/protocol-foundation/hermes-latency-linux/`에 있다.
두 OS의 이 모드는 목표를 통과했으나, 다른 runtime/mode·실제 서비스/UI와 원래
전체 행렬은 미완이며 이전 Linux 승인 실패의 원인도 미확정이다.
