# P11 C: bootstrap 이후 SSH 없는 data-plane 단일 셀

**미검증이다.** private 두 node의 engine 시작·team 생성/join·등록과 bootstrap SSH 종료까지 진행했지만, controller/helper의 in-process sandbox 적용 단계에서 예상된 SSH connect 거부와 다른 `PermissionError`가 났다. 지시된 stop 조건에 따라 중단했다. 측정 window·산술 요청·native 실행에 도달하지 않았고 모델 호출은 **0회**다. 정책을 우회하거나 새 SSH 연결로 task를 중계해 성공시키지 않았다.

## 조건과 실제 진행

기존 C 0.12.10의 동일 바이너리를 복사했다. SHA-256은 `6ac4bb4837469867edc2dba3cbbd6e4dd9fb18ad0389db69ff6ef21683317a44`다. 기존 `C-fixture-lib.py`, `C-native-base.py`는 수정 없이 재사용했으며 bootstrap copy와 해시가 같다. private person/team/node 및 marker `P11-QA-40c1afc34bbd43c4` 조건이다. 실제 Reason 팀이나 제품 xsm 소스는 변경하지 않았다.

| 단계 | 실제 증거 / 결과 |
|---|---|
| 준비 | local MacBookPro·peer Macmini. peer의 기존 `.codex-3` 공개 login status는 ChatGPT, exit 0. credential 값은 읽지 않음 |
| 정책 문법 확인 | literal IP `(remote tcp "100.77.24.16:22")`는 sandbox-exec 문법 거부(exit 65). OS가 받는 `(remote tcp "*:22")`를 사용: 소유 프로세스의 TCP 목적지 port 22 전체 차단이며 global firewall 변경 아님 |
| 독립 local kernel probe | sandbox-exec child가 실제 peer 100.77.24.16:22 connect → EPERM(errno 1), child exit 0. 이는 한쪽의 사전 probe이며 양쪽 SSH 차단 증명을 대신하지 않음 |
| bootstrap | 양쪽 engine을 owned sandbox-exec 아래 시작. private team create/join, 동일 team·capability SHA readback, pull 등록. peer team readback은 두 machine online. peer who 초기 readback은 자기 session 1개이므로 **양쪽 who 2개 준비 완료는 확인하지 못함** |
| control 종료 | bootstrap SSH exit 0, stdin/stdout 종료 후 local restriction 단계 진입. helper는 detached·deadline 보유, bootstrap 후 20초 대기 뒤 스스로 제한·probe·pull할 구조 |
| 실제 중단 | local과 peer 모두 `deny_current()` 호출에서 PermissionError. 정상 restriction 결과·SSH preflight 결과가 저장되지 않음. 측정 시작 없음 |
| data-plane | request/reply ID·본문 SHA·native PID/CID 모두 미생성. 모델 0회. SSH 측정-window 호출 0은 **window 미진입의 공허한 0**이며 성공 근거 아님 |
| 사후 회수 | controller 종료·실험 중단 후에만 SSH로 peer 자기 fixture의 증거/PID를 회수. task/native trigger를 보내지 않음. 원 상태 보존 |

capability는 local 메모리 → bootstrap SSH stdin → detached helper stdin → private engine IPC로만 전달했다. argv·별도 파일·공개 로그에는 원문을 기록하지 않았고 SHA만 남겼다. helper는 engine inbox의 실제 산술 요청을 봐야만 native를 한 번 실행하도록 구성됐으나, 그 분기에는 도달하지 않았다. 자동 모델 재시도는 없다.

## 실패 경계와 진단 한계

두 OS 오류는 type/문자열 SHA가 동일하다: `PermissionError`, SHA `42eacbf06c1e66e5a1773f5863fc6325667b177adf9a0d7b6a9a7c88cedd854f`, 분류 `operation not permitted`.

`deny_current()`는 `sandbox_init()` 성공 후 결과 dict를 구성하면서 `process_start()`의 `ps` subprocess를 호출한다. nonzero sandbox_init은 RuntimeError로 처리하게 작성돼 있으므로, 포착 PermissionError는 적용 후 ps/spawn bookkeeping 실패와 부합한다. 내부 cleanup도 같은 process_start를 사용하며 같은 오류를 냈다. **raw traceback/실패 syscall을 포착하지 않아 이 해석을 확정 원인으로 단정하지 않는다.** 정상 SSH connect의 expected-deny로 분류해서 계속하지 않았다.

이 실패는 현재 평가 하네스의 준비 경계다. native 모델·engine data-plane 요청을 실행하지 않았으므로 제품 통신 결함이나 C backend 불가로 확대하지 않는다. 다른 backend·네트워크 단절·SSH 없는 신규 설치에 대한 결과도 아니다. D12 제품 선택 응답을 대체하지 않는다.

## 정리와 잔여

내부 cleanup 실패 뒤 허용된 사후 회수 과정에서 PID/lstart가 일치하는 소유 engine만 종료했다. 현재 사용자 SSH 연결·authorized_keys·sshd·전역 firewall·프로필은 변경하거나 종료하지 않았다.

| 호스트 / 소유 프로세스 | PID | lstart (KST) | 사후 확인 |
|---|---:|---|---|
| local 최초 engine | 20871 | Oct 29 08:14:48 2026 | team 생성 재시작 때 이미 종료 |
| local 재시작 engine | 20990 | Oct 29 08:14:49 2026 | 생존 확인·generation 일치 후 종료, 잔여 없음 |
| peer 최초 engine | 59831 | Oct 29 08:14:56 2026 | join 재시작 때 이미 종료 |
| peer 재시작 engine | 59880 | Oct 29 08:14:58 2026 | 생존 확인·generation 일치 후 종료, 잔여 없음 |
| peer helper | 59829 | Oct 29 08:14:56 2026 | 스스로 finally/종료, 사후 잔여 없음 |

양쪽 private IPC는 종료 후 connect_ex=61로 연결되지 않았다. 위 관측 handle의 잔여는 0이다. local controller는 도구 프로세스 종료/exit 0을 확인했으나 controller PID/lstart를 시작 시 별도 저장하지 못했다. 따라서 전체 프로세스의 완전한 generation 계보를 확보했다고 주장하지 않는다. 양쪽 private state는 재현 증거로 남겼으며 실제 team/key state를 공개 artifact로 복사하지 않았다.

## 인계·재개 조건

이 단일 셀의 원 실패를 유지한다. 후속 소유자는 coordinator이며, 새 모델 없이 process sandbox 적용·bookkeeping 실패를 먼저 진단할 별도 지시가 재개 전제다. 새로운 data-plane 셀은 양쪽 실제 kernel/비multiplex SSH 거부와 who 준비를 충족하고, bootstrap/control 종료·측정 시작·사후 회수를 분리해야 한다. 이번 미검증 범위를 다른 성공 표본으로 채우지 않는다.

- [결과 JSON](no-ssh-native-results.json), [manifest](no-ssh-native-manifest.json)
- [controller](no-ssh-native-run.py), [helper](no-ssh-native-peer.py), [제한 라이브러리](no-ssh-native-lib.py), [사후 회수](no-ssh-native-recover.py)
- raw local: `/private/tmp/p11-C-no-ssh-local-hd13c8g2`
- raw peer: `/private/tmp/p11-C-no-ssh-peer-w3yq1ccr`
