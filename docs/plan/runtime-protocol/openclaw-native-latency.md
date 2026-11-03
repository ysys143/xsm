# OpenClaw 실제 wake 경로의 저장→native queue 지연

상태: macOS·Linux에서 각각100개를 완료했다. UI·실제 모델·서비스와 전체
런타임/모드 행렬의 인증이 아니다.

실제 설치 binding/native SDK를 사용한다. 시험용 loader proxy는 원래 API를
변경 없이 호출하고 patchSessionEntry가 반환한 committed row의 message IDs,
session ID/revision/native item ID와 process.hrtime.bigint를 기록한다. 이 loader는
관측 wrapper이므로 일반 설치 ownership 검사의 결과로 대신 사용하지 않는다.
SDK 결과나 모델 답변을 native commit으로 간주하지 않는다.

송신 프로세스의 실제 handoff.store 성공 반환 뒤 tick을 기록한다. Mac은
CLOCK_MONOTONIC_RAW, Linux는 CLOCK_MONOTONIC을 명시하고, 실제 Node 값이
Python before/after 구간 안인지 먼저5회 확인한다. Default timed-host clock은
기존 Hermes와의 호환성을 위해 MONOTONIC을 유지했다. 근거와 차이는
[clock 조사](openclaw-latency-clock.md)에 있다.

각 표본 앞뒤에 실제 native idle을 확인하며, 실제 native turn과 exact tool ACK가
끝나야 다음 표본을 시작한다. Native SID/revision과 표본별 저장/commit 관측1개씩을
대조한다. 정상 연결100표본과 reset/transport 주입 모드는 별도 실행이다.

| 표본 | 완료/실패/미실행 | p95 | max |
|---|---|---|---|
| mac100-first |100/0/0|284.0855ms|385.990875ms|
| Linux latency100 (c05104d) |100/0/0|259.723542ms|308.266309ms|

고정 OpenClaw2026.10.9/Node24.22.2와 localhost scripted provider를 사용한다.
Native model의 합성 context capacity는262144로 명시해 반복 turn history를 보관한다.
이는 실제 모델 규격·추천이나 모델 교체가 아니다. 실제 모델 과금 호출은0이다.
Provider request는32+6×표본 수로 제한하고 raw HTTP는 gzip으로 보존한다.

Source/end trace100개씩과 고유 native item100개를 별도 대조하고 raw ns 차이의
정렬95번째 값으로 p95를 재계산했다. Source3163b5f의 worktree probe 변경을 사용해
pristine commit 실행으로 표시하지 않으며 코드 snapshot/hash manifest도 보존했다.
2개 smoke는100개에 포함하지 않는다. Linux는 고정c05104d로 실행했으며
별도로 source/end 각100개, 고유 native item100개와 raw ns의95번째 값을
재계산했다. Clock 정렬5회 모두 일치했고313개 checkpoint가 통과했다.
Gateway 정상 종료와 VM stopExit=0을 확인했다.

실제 native commit 관측만 제거한 변이는 native turn/ACK가 진행돼도
`latency has exact canonical store and native committed queue observations`로
exit1이 됐다. Requested1/attempted1/completed0/failed1/unexecuted0이며 gateway는
정상 종료됐다. 임의 RPC 성공만으로 지연 수치를 만들지 않는 검사다.

Mac 원시는 `deliverables/protocol-foundation/openclaw-latency/`, Linux 원시는
`deliverables/protocol-foundation/openclaw-native-latency-linux/`다. 다른 모드·실제
모델/UI/서비스·전체 행렬은 미완이다. 기존 승인 불안정성과
cold receiver stale의 원인을 이 결과로 해결했다고 표시하지 않는다.
