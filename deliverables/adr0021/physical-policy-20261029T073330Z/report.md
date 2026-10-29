# ADR-0021 두 Mac의 멤버십 반례와 공개 경계

요청한 최소 반례를 실제 두 Mac의 private 제품 서비스로 실행했다. founder A의 서비스를 중지한 뒤 활성 멤버 B가 C를 초대·추가·제명했고, 제명된 C의 재접속과 옛 초대 재사용도 거절됐다. 잘못된 네트워크·만료·회수 초대로 실패한 가입은 C의 기존 현재 소속을 보존했다. 가입 뒤 공개 세션만 발견됐고 공개 자체로 업무 전송은 허용되지 않았다.

## 기준과 표본 구분

[A21-02와 A21-06](../../../docs/plan/reason-inspired-adrs/acceptance.md)은 열거한 모든 반례를 매번 두 물리 기기에서 재현하라고 명시하지 않는다. [spec P12](../../../docs/plan/reason-inspired-adrs/spec.md)는 실제 두 머신 통합 근거를 요구한다. 이전 잔여표의 표현은 이 두 축을 일괄 조건으로 읽을 수 있었으므로 이 문서에서 교정한다. 새 수용 조건을 추가하거나 원문 범위를 줄이지 않았다.

| 노드 | 물리 호스트 | 역할 |
|---|---|---|
| A | MacBook Pro | 최초 생성 노드. 공개 경계 확인 뒤 제품 서비스를 중지 |
| B | Mac mini | 기존 활성 멤버. A 서비스 중단 뒤 초대·가입 수락·제명 수행 |
| C | A와 같은 MacBook Pro | 별도 private 상태와 기기 신원의 세 번째 노드. 별도 기존 네트워크를 보유한 상태에서 실패한 가입을 먼저 검사 |

A의 서비스 중지는 MacBook 전원 중단이 아니다. 세 번째 물리 기기는 없으며 폰을 사용하지 않았다. B↔A 및 B↔C가 실제 물리 Mac 경계다.

실제 모델 호출은 0회다. 세션 후보는 별도 시험용 SQLite·rollout·registry를 생성한 **FILE actor**이며 PID는 각 제품 서비스의 live PID다. 실제 모델 세션이나 provider가 생성한 대화로 부르지 않는다. SSH는 기존 인증으로 파일 준비·제품 CLI/Unix RPC 실행·관측에만 사용했다. P2P 요청은 실제 Rust QUIC/TLS가 전달했다.

## 동결본과 실행 방법

- 현재 Python 파일 52개를 동결했다. R1 수정본 `network.py` SHA는 `f52485d50b5008a92860d8409df0b722fef0c26034c87938a1967af59d653265`, `probe.py` SHA는 `452835fb1ca280eb95094d89cc5775f8d510d4e3941c4469740f071ce27b676d`다.
- release 엔진 SHA는 `f17f03fafcdf3a31e374d6cbc0ccbbbd8000ba6a7eba5d9b44605e742c409aed`다. 소스·엔진·관측 helper 55개의 SHA가 양쪽에서 일치했다. Python은 Book 3.14.6, mini 3.9.6이었다.
- 제품 소스 파일은 변경하지 않았다. 별도 `observe.py`의 operator용 private 제어 facade가 FILE 준비·상태 조회와 직접 RPC 반례를 제공했다. 정상 CLI 작업은 원래 제품 경로로 전달했고 `Daemon.incoming`의 정책 결과·멤버십·서명 검증은 대체하지 않았다.
- stranger와 위조 sender는 송신 측 정상 업무 guard를 통과한 사용자 흐름으로 설명하지 않는다. operator가 실제 `Sidecar.request`로 입력을 보내 수신 제품의 경계를 검사한 직접 RPC 반례다.
- `init`, `invite`, `join`, `remove`, `status`, `stop`은 실제 제품 CLI를 사용했다. 초대는 private 파일과 SSH stdin 파이프로만 전달했고 값은 argv·출력·보고서에 넣지 않았다. 잘못된 network ID 변형도 private helper 내부 파일에서만 만들었다. 개인키 파일은 열지 않았다.

[manifest](manifest.json), [파일별 SHA](file-manifest.json), [실행 코드](run-policy.py), [제어 helper](node.py), [관측 코드](observe.py).

## 조건별 첫 결과

| 원문 관련 조건 | 실제 경계와 입력 | 관측 결과 |
|---|---|---|
| 가입 전 공개 경계 | 미가입 B mini→A Book directory 요청 | `not-an-active-member`, 후보 0 |
| 정상 가입 | A의 초대 파일을 B가 제품 join으로 소비 | 같은 network ID, B active |
| stranger | 별도 네트워크의 C Book→B mini ping | `not-an-active-member` |
| 위조 sender | TLS origin은 B인데 directory caller의 machine을 C로 주장, B mini→A Book | `origin-mismatch` |
| 가입 뒤 공개 경계 | B mini가 A Book의 published/unpublished/excluded FILE 후보 조회 | published 1개만 반환. private 경로 없음. 발견 직후 `directory._native` 호출은 published 1, unpublished 0, excluded 0 |
| 공개와 업무 권한 분리 | 저장소 매핑·선택 협업이 없는 B가 공개 A 세션으로 task 전송 | `selection-required`, 수신 canonical은 `not-found` |
| founder 오프라인 | A 제품 서비스를 중지 | 소유 PID·control socket 잔여 0, B는 active 유지 |
| 잘못된 네트워크 | B의 초대에서 network ID만 C의 기존 네트워크로 변형, B mini→C Book | join exit 4, `join-refused-or-state-mismatch`, 기존 current network·signed state·active pointer 동일 |
| 만료 초대 | B의 1초짜리 일회용 초대, 2초 대기 뒤 C join | 같은 거절 코드, 기존 현재 소속과 상태 동일 |
| 회수 초대 | B가 새 초대를 회수한 뒤 C join | 같은 거절 코드, 기존 현재 소속과 상태 동일 |
| 다른 활성 멤버의 초대·추가 | A 서비스 중단 상태에서 B mini가 새 초대를 발급하고 C Book이 join | C active, A의 network ID로 가입. 서명된 C admission의 issuer가 B |
| founder 없이 실제 통신 | B mini↔C Book ping | 양방향 성공. 양쪽 요청/응답 digest와 TLS origin 일치 |
| 다른 활성 멤버의 제명 | C를 먼저 중지한 뒤 B mini가 C를 remove | C removed. 서명된 remove의 issuer가 B |
| 제명 뒤 재접속 정책 | C를 같은 private 상태로 재시작 | 같은 기기 신원. 현재 네트워크는 보존되며 C active=false, self status=removed. 정상 ping과 직접 wire ping 모두 거절 |
| 옛 초대로 제명 취소 금지 | 성공했던 B의 옛 재사용 초대로 C가 다시 join | 거절. 제명 상태와 현재 소속 보존 |

반례별 에러가 모두 세부 사유를 노출하는 것은 아니다. 초대 실패의 공통 코드와 함께 실제 입력 조건·회수 동작·기존 상태 전후를 기록했다. 공개된 후보라는 사실을 업무 승인으로 사용하지 않았다.

## 물리 통신·서명·정리 근거

founder 서비스가 없는 동안 B↔C의 실제 선택 경로는 모두 `direct`였다. B→C의 상대 주소는 `192.168.0.11:55185`, C→B는 `100.77.24.16:52048`이었다. 각 native response 이벤트의 TLS origin이 상대 endpoint와 같았고 발신·수신 요청 SHA 및 회신 SHA도 각각 일치했다. 다른 NAT나 지속적인 Tailnet 전용 경유의 결과로 확대하지 않는다.

종료 뒤 읽은 B의 서명 멤버십 기록에서 C admission과 C removal의 issuer가 모두 B임을 확인했다. 서명 연산·검증은 실제 Rust 기기키와 제품 membership 경로를 사용했으며 fixture 서명은 없다. 이는 악의적인 기존 멤버의 모든 오프라인 fork를 막는 강한 암호학적 제명을 입증하는 결과는 아니다.

실제 제품 실행 구간은 27.099초이며 준비·복사 시간은 별도다. 서비스 시작은 4회(A/B/C 최초와 C 재접속)였다. 모든 소유 서비스·엔진·control socket을 종료했고 실제 UDP 바인딩 8개를 다시 bind할 수 있었다. 키·상태·증거는 각 private 폴더에 보존했다. 기존 SSH 키·authorized_keys·사용자 프로필·방화벽·폰·다른 프로세스를 변경하는 명령은 실행하지 않았다.

- [전체 조건 결과와 native 관측](results.json)
- [간단 요약과 양방향 digest 대조](summary.json)
- [서명 연산의 issuer·대상 메타데이터](signed-operation-metadata.json)

키 교체·가입 응답 유실·전환 실패 후 복귀 전체와 실제 모델 여정은 이 표본의 결과에 포함되지 않는다. 원문 반례와 P12의 두 머신 통합 근거를 보강한 제한된 표본이며 ADR 전체 완료 판정이나 새 정책 결정을 만들지 않았다.
