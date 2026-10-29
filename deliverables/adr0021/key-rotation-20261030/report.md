# 새 기기키로 교체하는 실제 제품 절차

같은 호스트의 독립 private 상태 세 개에서 실제 공개 CLI·서명 멤버십·Rust QUIC으로 키 교체 절차를 실행했다. 새로운 기기키를 생성한 노드를 초대하고 이전 키를 제명한 뒤, 이전 키의 통신은 `peer-refused`, 새 키의 양방향 ping은 성공했다. 기존 키를 덮어쓰거나 키를 직접 출력하지 않았다. 실제 모델 호출은 0회이며 두 물리 머신 또는 강한 악성 멤버 제명 보장으로 확대하지 않는다.

명령: `/opt/homebrew/bin/python3.14 -B deliverables/adr0021/key-rotation-20261030/run.py`. exit 0, `completed=true`, 소유 서비스/엔진 PID 6개 잔여 0. 실행 소스 manifest SHA-256은 `5e203237d953a8b656ff4083503fd8b9b5c02c744a3f4939b1ce3236bda461ec`다. 초대 비밀은 시험 private 파일과 메모리에서만 취급했고 일반 결과에는 넣지 않았다.

[실행 코드](run.py) · [실제 결과](results.json). 네트워크 ID·기기 공개키는 공개 식별자이며 개인키가 아니다.
