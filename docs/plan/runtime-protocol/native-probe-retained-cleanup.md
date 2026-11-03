# Native probe의 service 제거 뒤 정리

상태: P4/P5의 부분 진척이다. 전체 계획은 미완이다.

고정e1f58f7의 실제 Linux OpenClaw19개 mode를 모두 실행했다. 성공한 checkpoint는
632개였고16개 mode는 통과했지만 cold-error/cold-silent/native-error3개는
기능 검사38개를 마친 뒤 teardown에서 실패했다. 각 시나리오가 service metadata를
제거해 retained journal 조회를 검증한 뒤 observer가 현재 worker file을 다시
요구했기 때문이다. Gateway는 모두 종료됐고 batch 전체는 failed다. 원시는
native-probe-observer-linux/에 보존했다. 같은 source의943개 core는 Linux3.11에서
80.933초,3.14에서106.431초에 통과했다. 미실행 mode0/VM stopExit0이며 core의
통과를 세 native mode의 성공으로 대체하지 않는다.

Observer는 생성 시 정확한 격리 root/parent/owned flag/worker id를 검증하고 private
원본 snapshot을 보관한다. 그 뒤 request/cleanup은 원본 owner identity와 worker id로
journal을 조회한다. 지워지거나 재사용된 이름의 현재 service를 채택하지 않는다.
Narrow cancellation도 이름이 아니라 exact worker/request에 적용한다. 현재 provider
metadata 조회는 계속 엄격히 검사하며 state root 확인도 모든 경로에서 유지한다.

실제 workers.stop으로 metadata를 지운 뒤 retained request를 읽는 새 검사가 수정 전
RuntimeError로 실패했다(removed-before.log). 수정 후 observer/PID15개가0.284초에
통과했다(retained-focused-final.log). 신호의 process-group 경로가 실패한 뒤 PID
fallback에서도 generation을 다시 확인한다. 이 추가 검사는 수정 전 다른 세대 PID에
fallback signal이1회 호출돼 실패했다(fallback-before.log); 실제 신호는 mock이다.

Mac core945개(Python550+외부 적합성54+SDK56+native133+Node152)와 canonical schema,
기존 mock39/변이14 및 v7 local 예제132·mutant188·양성17/음성23·annotation42·
감지2개가56.249초에 통과했다(retained-core-final.log). 앞선944개/54.765초도
별도로 보존했다. 실제 native19개 mode는 다음 고정 source에서 다시 실행해야 한다.
원시는 `deliverables/protocol-foundation/native-probe-observer/`다.

이전 receiver stale 사건은 이번 batch에서 재현되지 않았으며 원인은 미확정이다.
그 상태를 이 cleanup 복구와 합쳐 해결됐다고 하지 않는다. 실제 모델/UI·원격·
메신저·설치와 원래 전체 계획도 미완이다.

## 고정 source 전체 native 재검증

85718b2a74ce3ee2fe3ddcdf0bd70a2e88cf8d07의 archive SHA256은
d110ba5b76b026f6eedc29fd8c51c03915e1aeecf351dc03066369e78b65dcd5다.
동일한 고정 OpenClaw2026.10.9/Node24.22.2에서19/19개 native mode와632개
checkpoint가 통과했다. 정상/분리 context/101개 session 뒤 cold lookup,
frontend 종료·gateway 재시작 뒤 정상/오류/무응답 복구, 실행 전/queue/실행 중 취소와
확인 유실, direct·public 경로를 모두 재실행했다. 모든 mode에서 gatewayStopped와
ownedChildrenExited가 true였으며 미실행 mode0이다. 이전 cleanup 실패3개도
이 source에서 통과했고 최초 실패 batch는 보존했다.

같은 source의945개 core+schema/v7 local은 Python3.11.2에서80.356초,
Python3.14.10에서104.900초로 각각 통과했다. Model0/network none/cpu2/memory3g,
VM stopExit0이다. Prepared native volume은 읽기 전용으로 검증하고 사용했다.
원시는 `native-probe-retained-cleanup-linux/result.json`과 mode별 output이다.
이것은 OpenClaw owned 경계의 실제 native SDK/gateway 증거이며 실제 모델·사용자
UI·일반 interactive 모든 모드·다른 runtime/원격/메신저 전체 인증은 아니다.
최초 receiver stale의 미확정 상태도 별도로 유지한다.
