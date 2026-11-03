# Hermes native messaging FIFO 연결

상태: 실제 gateway/DiscordAdapter와 로컬 플랫폼 전송 경계 검증이다. 외부 Discord
서비스·사용자 계정·메시지 발송은 실행하지 않았으며 전체 메신저 지원은 미완이다.

NativeGateway는 local뿐 아니라 기존 messaging route의 현재 프로필 소유와
플랫폼 권한을 확인한다. Native authority는 이전에 실제 ingress가 저장한
connector envelope를 복원해 automation을 영속화한다. Bridge는 receipt의
profile/logical owner/epoch/producer identity/원문과 복원된 route/provenance,
internal automation 여부를 대조한 뒤 SDK에 admission을 보고한다. 연결되지 않은
adapter, 다른 대화·권한·connector에는 저장 수락을 만들지 않는다.

Local bot-author descriptor와 messaging authorization source는 다른 것이다.
Native messaging snapshot은 기존 connector의 source를 빌리고 turn_author를
별도로 보존하지 않는다. Bridge는 이를 peer의 bot authorship 보존이라고 보고하지
않는다. Native automation envelope와 internal 표식, is_viewer_input=False를
확인해 사용자 제출·승인 권한으로 승격하지 않는다. 원문은 canonical peer envelope에
발신자를 포함하고 소비 ACK는 명시적 native tool 호출로만 처리한다.

## 실제 경로

`scripts/probe-hermes-messaging.py`는 새 격리 홈에서 실제 설치 plugin,
PluginContext/DiscordAdapter/GatewayRunner/SessionAuthority/native FIFO drain/
AIAgent/native hooks/Tool Hub를 실행한다. Discord transport의 send만 로컬
기록기로 바꾸고 localhost scripted provider를 사용한다. 계정·토큰은 합성 fixture이며
외부 Discord에 connect하지 않는다. 모델 과금 호출은0이다.

Native ingress warmup이 실제 connector provenance를 저장한 것을 확인한 뒤,
XSM awake 원문→native messaging turn→정확한 native tool ACK→미재전달과
로컬 플랫폼 전송기의 최종 회신을 확인했다. Strict FYI는300ms 관측 동안
새 FIFO/provider 요청이 없었고 다음 실제 native ingress turn의 context에서 ACK됐다.
그 뒤 현재 플랫폼 allowlist 철회와 connector home 교체를 주입했다. 두 경우
전달이 거부됐고 connector mismatch는 native queue row를 추가하지 않았다.

최종 정상 실행은27개 checkpoint/11개 scripted HTTP request를 통과했다.
Streaming/nonstreaming 응답을 구분해 auxiliary title 요청도 유효한 JSON을 받는다.
Native 플랫폼 권한 guard를 적재된 메모리에서 제거하면
`revoked platform authorization accepted`로 exit1이 됐다. Native 파일이나
production source를 변이 때문에 수정하지 않았다. 같은 변경의 실제 local
drain21개도 다시 통과했고 Mac core960개+schema/v7은59.136초였다.

## 실패 기록과 경계

처음 두 표본은 adapter.handle_message가 백그라운드 처리를 예약한 직후 세션을
조회해 fixture가 실패했다. 세 번째 red는 warmup을 마친 뒤 기존 미지원 messaging
분기의 native hook 오류와 host 미등록으로 실패했다. Green-first는 handler를
authority 초기화 전에 연결해 connector provenance가 없는 ingress envelope를 만들었다.
Native authority가 not_found로 거부했고 타임아웃으로 끝났다. Native startup과
같은 순서로 authority를 만든 뒤 실제 callback factory를 연결해 해결했으며
provenance를 직접 조작해 성공시키지 않았다.

첫 변이 실행은 loader의 dynamic module이 sys.modules에 없어 fixture가 실패했다.
이 실행을 guard 검출로 세지 않는다. 실제 method globals를 사용한 두 번째 변이가
위 assertion으로 실패했다. 모든 red/green/변이와 native logs는
`deliverables/protocol-foundation/hermes-messaging/`에 분리해 보존한다.

Linux 고정 source, Telegram 경로와 실제 외부 Telegram/Discord, busy/now·혼합·
재시작·다중 프로필과 p95 100표본 및 원래 전체 행렬은 미완이다.
