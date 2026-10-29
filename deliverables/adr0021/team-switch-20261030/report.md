# 기존 소속이 있는 가입 응답 유실과 전환·복귀

최종 동결 소스로 실제 Rust QUIC·서명 멤버십·공개 CLI의 연속 시나리오를 완료했다. 같은 호스트의 세 private 서비스이며 실제 모델은 0회다. 제품 소스·서명·원문·권한 판단은 바꾸지 않았다. issuer의 실제 콜백이 서명 admission을 저장한 뒤 첫 join 응답 한 건만 private Python/Rust IPC 출력 경계에서 억제했다. 공개 CLI 응답만 버린 시험과 구분한다.

| 단계 | 실제 결과 |
|---|---|
| 기존 팀에서 새 팀 가입 | issuer가 가입을 저장한 뒤 응답 1건 유실 |
| 응답 불명 구간 | 기존 팀 active pointer 바이트 보존, issuer에서 신규 active 확인 |
| 제품의 자동 확인 | 30초 뒤 실제 `join-status`, 요청한 새 network ID·기기키 확인 후 전환 |
| 같은 초대 재시도 | issuer의 서명 멤버십 상태 불변, 중복 admission 없음 |
| 잘못된 팀 전환 | `join-refused-or-state-mismatch`, 현재 새 팀 보존 |
| 유효한 옛 초대로 복귀 | 옛 network ID 확인, 옛 팀 ping 성공 |
| 새 팀으로 다시 이동 후 옛 팀에서 제명 | 옛 초대 복귀 거절, 현재 새 팀 pointer 보존, 새 팀 ping 성공 |

명령: `/opt/homebrew/bin/python3.14 -B deliverables/adr0021/team-switch-20261030/run.py` → exit0, completed=true. 실제 응답 유실부터 readback까지 30.121초다. 소유 서비스/엔진 PID 6개 잔여0이다. source manifest SHA-256 `5e203237d953a8b656ff4083503fd8b9b5c02c744a3f4939b1ce3236bda461ec`. 운영 네트워크·계정·사용자 프로필·전역 권한은 변경하지 않았다.

[실행 코드](run.py) · [응답 유실 주입 코드](response-loss-sitecustomize.py) · [실제 drop/join-status 이벤트](issuer-response-events.json) · [결과](results.json). 이벤트는 native TLS origin과 op/ID/시각만 남기며 초대 비밀·서명 원문·개인키를 로그에 넣지 않았다.
