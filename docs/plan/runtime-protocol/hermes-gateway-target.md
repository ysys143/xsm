# Hermes idle wake의 세션 지정과 실제 FIFO 경계

상태: 연결 지점의 실제 실행 조사다. XSM idle wake 구현이나 P4 완료 증거는 아니다.

`scripts/probe-hermes-gateway-target.py`는 Hermes v0.22.5 exact tag의 tracked
clean source를 새 격리 HOME/HERMES_HOME/XSM_HOME에서 실행한다. 모델·외부
플랫폼·API 키를 쓰지 않는다. 첫 부분의 저장소와 authority는 제어 가능한 대역이며,
두 번째 부분은 실제 GatewayRunner/SessionAuthority/SessionDB/local adapter와
SQLite admission을 사용한다. 모델 실행을 막으려고 drain scheduling만 비활성화한다.

## 확인한 동작

일반 `inject_message` 경로의 실제 scheduler는 authority admission 전 True를
반환한다. 예약 직후 저장소의 대화를 바꾸면 실제 dispatch는 교체된 SID로 주입한다.
이는 runtime API가 route를 대상으로 삼는 동작이며, XSM의 기존 대화·실행 세대에
결속된 수락 증거로 그대로 사용할 수 없다. 이 표본은 해당 경쟁을 결정적으로
주입한 것이며 실제 사용자 대화에 오배송됐다는 관측은 아니다.

Native `_owner`는 지정한 SID가 현재 대화와 다르면 admission_conflict를 반환한다.
단, native compression successor는 허용하므로 XSM의 대화 신원과 physical
transcript를 구별해야 한다. 명칭이나 route만 같다는 이유로 새 대화로 옮기면 안 된다.

실제 native local FIFO에서는 정확한 SID로 원문 1건이 queued 상태로 영속화됐고,
오래된 SID로 시도한 원문은 추가 기록 없이 거부됐다. `_admit_plugin_injection`은
이 경계를 통과하지만 반환값이 bool이고 local row에 명시적 bot author를 넣지 않는다.
XSM은 큐 수락과 소비 ACK를 분리하고 peer text를 사용자 승인으로 승격하지 않아야
하므로 이 helper의 성공값만을 전달 증거로 삼지 않는다.

`authority.admit_automation`을 직접 호출하면 실제 admission ID·대상 profile/session·
authority epoch를 가진 receipt를 받는다. 명시한 bot author와 원문도 local descriptor에
보존된다. 같은 producer identity와 같은 본문을 재시도하면 동일 admission으로
수렴하고, 같은 identity의 다른 본문은 admission_conflict로 거부된다.
실제 DB의 runtime epoch를 교체하자 기존 authority의 새 admission은 stale_epoch로
거부됐고 기록 수가 늘지 않았다. 이 표본은 실제 프로세스 재시작 대신 동일 DB의
native epoch 교체를 실행한 것으로, 프로세스 재시작 행렬과 구별한다.

최종 정상 실행은20개 checkpoint를 통과했다. 같은 probe에 `--mutant
ignore-stale-sid`를 주면 메모리에 적재한 native `_owner`의 SID guard만 제거한다.
그 실행은 `FIFO owner guard accepted unrelated replacement`로 exit1이 됐다.
Native 원본 파일은 수정하지 않았고 실패 원시도 별도 경로에 보존했다.

## 연결부에 남은 일

실제 native hook에서 관측한 runner/profile/route/SID/authority epoch를 호스트
수명에 결속하고 native loop에서 admission을 실행해야 한다. durable receipt와
원문·대상·producer identity를 검증한 뒤에만 SDK delivery.report를 보내야 한다.
등록 시 캡처한 authority가 교체되거나 프로필이 다르면 새 authority를 임의로
채택하지 않는다. FYI는 기존 자연 turn 경로를 유지하고 자동 ACK하지 않는다.

Local FIFO 검증을 messaging FIFO의 증거로 쓰지 않는다. Messaging automation은
기존 connector provenance를 복원하므로 실제 gateway 표본에서 별도로 확인해야 한다.
Busy/now, 실제 drain·model/UI·Telegram·Discord와 p95 행렬도 남아 있다.

원시는 `deliverables/protocol-foundation/hermes-gateway-target/`이며 첫 경로 조사와
durable-first/second/third, mutant-ignore-stale, final의 실행 결과를 덮어쓰지 않는다.
