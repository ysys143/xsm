# ADR21 최종 변경 집중 검토

실제 구독 `claude-opus-5-5`의 한 번 호출이 지정 변경 범위에서 Medium 이상 지적 없음으로 판정했다. 실제 init의 API key source는 `none`이며 도구는 Read/Glob/Grep뿐이다. 원문과 실행 metadata를 보존했다.

범위는 probe admission R1/R2 수정, 오프라인 원문 소유자 결속·내보내기·보관, 첨부 TTL/quota와 metadata-only 저장, 만료된 파일 회신의 원질문 ACK 유지 및 직접 소비 경로다. 검토 모델은 검사를 실행하지 않았으며 두 물리 머신·다른 NAT 또는 ADR 전체 완료를 승인한 것이 아니다.

최종 동결 소스 manifest SHA-256: `5e203237d953a8b656ff4083503fd8b9b5c02c744a3f4939b1ce3236bda461ec`. 이전 changes_required 판정은 수정하지 않았다. 이번 별도 판정과 세부 읽기 범위는 [검토 결과](review-parsed.json), 실제 호출은 [실행](execution.json), 원 응답은 [원문](review-raw.json)에 있다.

## 남은 한계

- Read/Glob/Grep만 써서 정적으로 검토했습니다. 테스트, 셸, 네트워크를 실행하지 않았고 다른 에이전트도 부르지 않았습니다. 별도로 진행 중인 두 Python 전체 회귀는 성공했다고 보지 않았습니다.
- 실제 모델로 하는 두 Mac 협업과 phone NAT 실측은 이 코드 리뷰가 승인하는 범위가 아닙니다. ADR21 전체가 완료됐다는 판정도 아닙니다.
- context/의 이전 changes_required 원판정(application-opus-review, application-opus-rereview R1, r1-opus-review R2)은 그대로 두었습니다. 이번 판정은 지정 변경 범위에 대한 별도 판정입니다.
- Medium 미만 관찰 1: deliver가 gateway.receive 커밋 뒤에 ingress-policy 파일을 씁니다(network.py:904-910). 그 사이에 서비스가 죽으면 policy 파일이 없는 채로 남습니다. 그러면 admission의 _read_private가 FileNotFoundError를 내고, Handler가 operation-failed를 돌려주고, inbound_record가 AdmissionUnavailable로 올려 메시지가 pending에 머뭅니다. fail-safe 방향이고, 송신 측이 같은 ID로 재전송하면 커밋된 중복 경로로 policy가 다시 기록되므로 Medium으로 보지 않았습니다. 이를 직접 검증하는 테스트는 번들에 없습니다.
- Medium 미만 관찰 2: admission은 호출자 검증 뒤에 관측을 한 번만 초기화합니다. 그래서 같은 요청 안에서 repository 경로의 실제 시간 초과와 grant 경로의 확정 철회가 겹치면, 그 회차는 held가 아니라 admission-unavailable(pending)이 됩니다. 일시적인 결과이고, 다음 평가에서 확정 거부로 수렴합니다.
- probe.quick의 전역 예산, _memo, _stalled를 서비스의 동시 요청들이 공유하는 것은 기존 동작입니다. 이번 변경 범위가 아니어서 다시 감사하지 않았습니다.
- export가 쓰는 도중 실패하면 O_EXCL로 만든 부분 파일이 남을 수 있습니다. 원본은 바뀌지 않으므로 결함으로 보지 않았습니다.
- 증명이 불완전한 부분: 네트워크를 전환한 뒤 archive와 늦은 회신이 함께 일어나는 조합, 그리고 실제 디스크 오류(EIO)가 admission-unavailable로 바뀌는 경로는 소스상 맞습니다. 다만 실제 서비스로 확인하는 테스트는 없습니다(단위 수준의 IsADirectoryError 관측 테스트만 있음).
