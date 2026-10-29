# ADR-0021 애플리케이션 통합 검사

네트워크 가입·세션 공개·선택 협업을 구분하고 기존 인터페이스로 연결했다. 다음은 이번 소스에서 직접 수집한 실행 결과다. 서로 범위가 겹치므로 검사 수를 합산하지 않는다.

| 명령 | 결과 | 범위 |
|---|---|---|
| `python3 -B -m unittest tests.test_network_identity tests.test_network_service -q` | 12개, 35.099초, OK | 실제 Rust와 두 서비스의 코어 및 원격 신원 |
| `python3 -B -m unittest tests.test_network_recovery -q` | 7개, 3.795초, OK | 원 Opus 두 결함의 복구 경로 |
| `python3 -B -m unittest tests.test_install_runtime tests.test_network_identity -q` | 52개, 10.735초, OK | 새 packaging 검사 추가 전 설치·신원 |
| `python3 -B -m unittest tests.test_network_messages tests.test_network_interfaces -q` | 75개, 5.219초, OK | 게이트웨이·질문 intent·기존 CLI/MCP 경계 |
| `python3 -B -m unittest tests.test_network_application -q` | 8개, 27.272초, OK | 실제 QUIC 서비스 + 네이티브 파일 시험체 |
| `python3 -B -m unittest tests.test_network_application tests.test_network_recovery -q` | 16개, 28.181초, OK | 이후 추가된 private directory 검사 포함 |
| `/usr/bin/python3 -B -m unittest tests.test_network_application -q` | 8개, 50.330초, OK | Python 3.9 단독 애플리케이션 실행 |

Python 3.9에서 interfaces→application→messages→install-runtime을 묶은 실행은 132개 중 2 FAIL·2 ERROR였다. 직접 서비스의 admission은 true인데 같은 프로세스의 private canonical 조회가 맞지 않았고, claim token 소유권도 어긋났다. 선행 테스트가 xsm 모듈을 재로딩한 뒤 보관된 fixture 모듈 참조를 조사하고 있다. 이 실패를 현재 전체 회귀 성공으로 기록하지 않는다. 제품 검사는 완화하지 않았다.

고정 Rust source를 실제 release build하고 private 설치 엔진이 기본 탐색으로 선택됨을 확인했다. configure/start/stop을 실행했으며 [설치 결과](installation-check.json)에 경로·SHA·폴더 권한·중지 관측을 기록했다. 최초 build가 상위 network 폴더를 0755로 만들어 다음 configure가 거절되는 결함을 먼저 재현하고 missing 부모를 각각 0700으로 생성하도록 수정했다. 설치 snapshot에 고정 Rust source를 포함하는 검사는 실제 복사 경로로 통과했고, source 포함 규칙을 제거하면 실패했다. 첫 변이 시도는 fixture의 모듈 재로딩 전에 패치해 규칙이 적용되지 않았으며 이를 검출 성공으로 세지 않았다.

실제 LLM 세션·다른 NAT·relay 경유·proxy 전체 성공을 위 숫자로 대체하지 않는다. 현재 애플리케이션 Opus5.5는 `/private/tmp/adr21-app-opus-9il8p9yn/bundle`의 고정 67개 파일을 검토 중이다. 원 core 검토와 별개의 한 번 호출이며, 이 문서는 새 판정을 대신하지 않는다.

## 수정 후 추가 실행

- `python3 -B -m unittest tests.test_network_application -q`: 12개, 36.003초, OK. F2의 실제 inbox 소비 중 서비스 중단과 F3의 저장 뒤 같은 CID 재개 반례를 포함했다.
- `python3 -B -m unittest tests.test_network_receive tests.test_network_interfaces -q`: 34개, 13.982초, OK. 기존 ID 충돌의 온라인/오프라인 거절과 원 ledger 보존, 재사용 초대 만료·회수 CLI, founder 중단 뒤 다른 멤버의 양방향 통신을 포함했다.
- F1 원 결함은 `/private/tmp/adr21-f1-repro-xiqjfuhm`에서 고정 원본 network.py로 실제 서비스 호출을 재생했다. 새 원격 body를 보내지 않았는데 기존 local delivered 결과를 읽어 `delivered != refused` assertion이 실패했다. 수정 후 같은 경로는 `message-id-conflict`로 거절한다. 서비스 자체가 없을 때도 잘못된 이전 영수증을 읽지 않도록 frontend canonical 선검사를 추가했다.

위 숫자는 실제 LLM 여정 완료나 Opus 재승인을 의미하지 않는다. 주소 갱신을 IPC로 새로 읽는 변경은 초기 ready의 주소만 고정하던 relay 연결 결함을 고치는 후속 변경이며, 원 실패 표본과 새 carrier 조건을 구분해 수집 중이다.

## 첫 전체 회귀의 실패와 원인

동결본 `/private/tmp/adr21-regression-t48kcqw9`에서 Python3.14와3.9가 각각 1,915개를 실행했다. 두 실행 모두 `FAILED (failures=1, errors=2)`였다. 3.14는465.351초,3.9는701.274초다. 원본 로그를 보존했다.

- 실패1개는 생성 가이드만 바꾸고 원본 `xsm/instructions.py`의 `MESSAGING_GUIDE`를 갱신하지 않은 실제 일관성 결함이다. 원본을 수정하고 `scripts/generate-messaging-guide.py`로 재생성했다.
- 오류2개는 동결 복사본에서 루트 `.mcp.json`과 `.gitattributes`를 빠뜨린 준비 오류다. 원래 저장소에는 두 파일이 존재하며 기존 관련 검사8개는 현재 저장소에서 통과했다.
- 첫 동결본에는 이후 R1 내부 probe 평가 불가 수정이 없다. 이 실행을 최신 소스 전체 통과로 주장하지 않는다.

별도 실제 로컬 독립성 검사 `tests.test_network_receive.NetworkReceiveTests.test_local_question_and_reply_complete_with_all_network_services_stopped`는 두 네트워크 서비스를 모두 중지한 뒤 로컬 ask→원문 소비→직접 reply→최종 결과/ACK 경로로 통과했다(1개,2.663초). 실제 LLM 여정이라고 주장하지 않는다.
