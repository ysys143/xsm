# Native probe의 공개 관측과 operator 진단 분리

상태: P1/P4/P5의 부분 진척이다. 전체 계획은 미완이다.

Owned public projection과 Linux process generation 변경의 영향을 scripts 전체에서
조사했다. Public probe2개는 제거한 native_provider/child/native_binding/execution
필드에 의존했고, direct OpenClaw probe1개와 subscription probe는 raw ps lstart로
kernel key를 비교했다. Subscriber cleanup의 raw 비교는 살아 있는 새 kernel-key
child를 이미 종료된 것으로 오인할 수 있어 새 경로의 재검증 전에 수정했다.
다른 Hermes/Pi/OpenCode direct probe는 private backend view를 쓰므로 public
projection에 의한 동일 변경 대상이 아니었다.

새 OwnedProbeObserver는 state root가 실제 격리된 backend root와 같고 parent ref,
mode/owned, immutable worker id가 맞을 때만 private record를 읽는다. 다른 service의
요청을 채택하지 않는다. Teardown은 자기 queued launch를 먼저 취소한 뒤 exact
child만 종료하고 확인 불가를 성공으로 처리하지 않는다. 공개 모델 응답에는
내부 PID/lease/provider를 되넣지 않았다. Probe 결과 디렉터리는0700으로 만든다.

Native settlement의 의미 있는 요약은 public projection에서 보존한다. state/
observed_at/native_session_id/context_epoch만 반환하고 child/evidence는 제외한다.
Cancellation recovered_from은 readback 출처를 식별한다. 실제 model frontend
status 경로를 SDK fixture로 실행한 확장 검사가 수정 전 native_execution KeyError로
실패했고, 수정 후0.787초에 통과했다(settlement-before/after.log). Task unknown,
result/reply null과 내부 child/evidence 비노출을 함께 확인했다.

Workers._terminate도 kernel/legacy generation을 지원하고 각 신호와 대기 중 세대를
재확인한다. PID 재사용·조회 불가에는 신호를 보내지 않는다. 옛 ps-only guard 변이는
새 검사에서 실패했다(old-termination-mutant.log). Operator/PID 관련13개는
0.150초, 관련 SDK/owned37개는11.064초에 통과했다. 초기 focused 실행은 TempState의
module reload 뒤 stale identity module을 patch한 검사2개가 실패했다. 현재 worker가
쓰는 module을 각 test에서 다시 가져오도록 수정했고 원시 실패를 보존했다.

Mac core943개(Python548+외부 적합성54+SDK56+native133+Node152)와 canonical schema,
기존 mock39/변이14 및 v7 예제132·mutant188·action 양성17/음성23·annotation42·
감지2개가54.723초에 통과했다(core.log). 이후 exact owned=true guard 보완은
focused-final13개로 확인했다. 실제 upstream native CLI/gateway mode의 재실행은
아직 진행 전이며 위 SDK fixture를 그 증거로 부르지 않는다.

원시는 `deliverables/protocol-foundation/native-probe-observer/`다. 다음 고정 source
검증은 기존 OpenClaw19개 mode를 모두 실행해 callback/수신/취소/복구/teardown을
확인해야 한다. Source별 예전 성공/실패를 덮어쓰지 않는다. 이전 receiver stale의
원인은 아직 미확정이며 새 direct probe는 저장/현재 ps 값과 kernel generation을
함께 기록해 재발 시 진단한다. 실제 모델/UI·원격·메신저·설치와 전체 계획은 미완이다.

고정e1f58f7의 실제19개 mode 재실행에서3개는 service metadata 제거 뒤 observer
teardown에서 실패했다. 원인과 원본 신원 snapshot을 유지하는 후속 수정은
[retained cleanup](native-probe-retained-cleanup.md)에 기록했다. 이 첫 batch는
failed로 보존하며 기존38개 기능 checkpoint의 통과를 teardown 통과로 대체하지 않는다.
