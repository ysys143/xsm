# 구형 native 사본과 현재 P2P 정본의 수신 복구

실제 두 Mac의 공통 검토에서, 설치된 구버전 훅이 P2P origin을 알지 못해 별도 사본을 보류하고 digest 없는 영수증을 썼다. 현재 broker의 인증·원문·현재 권한은 정상이었지만 MCP가 그 영수증 때문에 canonical 원문을 건너뛰었다. 원문이 pending인데도 inbox와 미독 숫자가 비어 있었고, 같은 선검사가 답 조회에도 있었다.

## 수정 범위

`handoff.old_p2p_copy_receipt`가 같은 ID·같은 수신 runtime/ref·pending 원문/전달 상태·digest/body 결속 필드 부재·정확한 구형 unsupported-P2P 사유만 분류한다. 이 분류는 수신 후보를 현재 검증 경로로 돌리는 용도다. MCP 수신과 답 조회는 기존 fresh admission·현재 멤버십·업무 권한·본문/헤더·파일·traffic 검증을 통과해야 한다. 미독 숫자는 읽기 전용 후보 정보다.

구형 held 사본은 전달·삭제하지 않는다. 현재 digest-bound 거절과 정본 자체의 실제 held는 유지한다. ACK는 실제 소비자가 반환된 토큰으로 따로 수행한다. 범위는 `xsm/handoff.py`, `xsm/receive.py`, `tests/test_network_receive.py`다.

## 재현·검사·검토

- 실제 최초 질문 `9f11884127764cad`는 admission=true·body/header 일치·canonical pending인데 MCP가 claims0을 반환했다. 수정 전 격리 반례도 claims0으로 실패했다.
- 처음 수정에서 raw record의 state와 공개 status view를 혼동해 반례를 통과하지 못했다. `handoff._view` 계약을 확인해 정정했다. 첫 실패를 통과로 바꾸지 않았다.
- 한 소비자만 고친 1935개 단계는 두 Python에서 통과했다. 이후 영향을 전수 확인해 미독 후보와 답 조회의 두 선검사도 같은 함수로 연결했다. 그 두 검사는 이전 코드에서 pending empty/poll0으로 실패했다.
- 최종 관련 검사10개는 Python3.14 34.362초, Python3.9 71.973초로 통과했다. 세 새 메서드는 정상 원문 회수·미독 표시, 실제 hold와 현재 거절 보존, checked reply index의 무claim/무ACK 및 현재 제명 후 비공개를 실행한다.
- 최종 세 반례는 정상 코드에서 통과하고, 이전 두 소비자로 회귀·digest-bound 거절 무시·수신 현재 gate 생략·답 조회 현재 gate 생략의 네 변이를 모두 검출했다. [원 명령과 결과](final-red-results.json)에 결속했다.
- 실제 구독 Opus5.5의 [판별식 검토](review-parsed.json)와 [마지막 두 경로 delta 검토](final-surface-review/review-parsed.json)는 각각 approved/findings0이다. 모델은 Read/Grep 정적 검토만 했으며 검사를 실행하지 않았다. 원문·제한·입력 source hash를 보존했다.

직전1933개, 한 소비자 수정1935개, 최종 세 경로 수정은 서로 다른 소스다. 최종 입력 manifest SHA-256은 `ccc3f22a1d65a33ddc76b0ad1abc4966a65664a6e41777d52b70230cd4fd4011`이다. 최종 두 Python은 각각1936개 OK/skip0다(3.9 831.018초,3.14 534.329초). [최종 전체 회귀](final-validation/report.md)에 원 명령과 로그를 따로 보존했으며 검사 뒤178개 입력이 현재 작업 트리와 일치했다. 이전 성공을 대신 쓰지 않는다.

## 실제 대화 복구

같은 Claude CID와 실제 Codex CID 재개에서 MCP를 정상 재접속해 원문을 읽었다. 실제 요청·회신·ACK를 쓰며 기존 held 파일·원문·동의 상태를 보정하지 않았다. [공통 수학 표본](../native-journey-common-math-latest-retry1-20261029T155548Z/report.md)에 source overlay 전후·실제 MCP PID·재접속·보존 답 회수·조작 수와 실패를 기록한다. 실제 망 이동이나 무보정 신규 onboarding을 이 복구 성공으로 주장하지 않는다.

전체 G13·다른 ADR의 완료 판정은 이 수정 범위에 포함되지 않는다.
