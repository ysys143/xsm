# UDP 차단 C fixture 실행 전 계획

작성 UTC: 2026-10-28T19:59:46.050516+00:00. 기존 전체 비교 요청 내 owned-process 제한 실험이며 D12 backend 선택·전역 권한 변경이 아니다.

양쪽 실제 kernel preflight는 `udp-blocked-preflight-results-20261029.json`에 고정했다. 정상 UDP 수신, 같은 child profile의 errno 1/무수신, 같은 profile의 TCP echo가 모두 통과했다.

- local `/private/tmp/p11-C-udp-s3mrn30l`, peer `/private/tmp/p11-C-udp-tih25w67`에 새 private HOME/state/명시 IPC/socket과 0.12.10 engine 사본을 둔다. SHA는 `6ac4bb4837469867edc2dba3cbbd6e4dd9fb18ad0389db69ff6ef21683317a44`만 허용한다.
- profile `(version 1) (allow default) (deny network-outbound (remote udp "*:*"))`은 양쪽 own engine daemon Popen에만 적용한다. SSH control·metadata CLI·native Codex는 이 profile에 넣지 않는다. deny 제거 재실행은 없다.
- 두 controlled endpoint만 private fixture create/join/register한다. 실제 Reason CLI/계정/사용자 팀·현재 .reason state·전역 membership/MCP·제품코드는 사용/변경하지 않는다. capability는 Python 메모리→기존 strict-hostkey SSH stdin→명시 private IPC만 사용하고 공개에는 hash/상태만 남긴다.
- 기존 C와 같은 공개 수학 marker/2+2=5의 first 요청 1건을 실제 구독 peer Codex 1회로 검토한다. 요청/답은 engine inbox/send/reply_to로만 전송한다. 동일 request ID·본문 SHA·reply_to·실제 native 결과와 양쪽 상대 link=relay readback이 있어야 해당 제한 조건의 relay native 성공으로 센다. relay_connected만으로는 통과하지 않는다.
- 기존 정상 서비스: native engine의 signed relay 목록/iroh discovery와 기존 구독 Codex 서비스, 기존 jaesol-macmini SSH만 사용한다. 자체 relay/다른 NAT/전역 firewall 시험으로 확대하지 않는다.
- 정확한 UDP sendmsg/quinn_udp 계열 EPERM만 의도한 제한으로 분류한다. 다른 파일/IPC/로그인/OS 실행/sandbox_apply 권한 실패는 중단한다. 로그 원문은 공개하지 않고 메모리에서 분류 후 hash/상태만 남긴다. 실제 전송 실패도 보존하고 모델 자동 반복은 없다.
- 시작 handle 확인, 자기 daemon/native/control만 종료, IPC 거절·잔여 process·private key/state/binary 정리를 확인한다. raw native 자료는 고유 /private/tmp, 공개 deliverables에는 udp-blocked-* 코드/보고/hash만 둔다. 전체 20분 상한.

## 부트스트랩 수정 후 실제 표본 경로

최초 부트스트랩은 평가 peer script의 모듈명 불일치로 peer engine/team/model 이전에 종료했다. 원 결과·코드는 별도 tmp와 bootstrap JSON에 보존했다. UDP deny를 제거하지 않았고 모델 재호출은 없었다. 실제 두 노드 표본은 local `/private/tmp/p11-C-udp2-sjkpra10`, peer `/private/tmp/p11-C-udp2-cysgvtr5`의 새 private root에서 같은 고정 profile·binary로 한 번 수행한다.

## Pull session 준비 readback 보완

앞선 실제 send는 양쪽 machine link=relay 뒤에도 peer pull session이 아직 발신 목록에 없어 거부됐으며 오류 원문은 보존 hash와 고정 소스로 대조했다. native 호출은 0이다. 이 실패를 별도 보존하고 최초 모델 과제 전 실제 who 목록이 양쪽 controlled session을 포함할 때까지 준비를 확인한다. 새 local `/private/tmp/p11-C-udp3-mnbiv37u`, peer `/private/tmp/p11-C-udp3-a6yz6nss`만 사용하며 profile은 동일하고 모델 반복 호출/UDP deny 해제는 없다.
