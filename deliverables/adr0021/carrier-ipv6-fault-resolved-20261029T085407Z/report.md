# A21-07 프로세스별 IPv6 socket 고장 주입 결과

소유한 실제 제품 엔진 두 개에만 `socket(AF_INET6)`의 `EAFNOSUPPORT`를 적용한 상태에서 IPv4 bind, init, join, 양방향 ping, 점유 포트 대체가 통과했다. 실제 호스트는 시험 전후 모두 IPv6 socket 생성이 가능했다. 이 결과는 **제어된 고장 주입**이며 호스트 전체의 IPv6 부재 환경 성공으로 해석하지 않는다.

## 기존 실패의 원인

기존 [첫 시도](../carrier-ipv6-fault-20261029T071008Z/report.md)의 loaded 1 / socket event 0 / service exit 4만으로 원인을 판정하지 않았다. 같은 동결 binary와 같은 기존 dylib를 새 0700 root에서 직접 한 번 실행하고 stdout JSONL과 stderr를 별도 파일에 보존했다. relay off, port 0이었다.

직접 실행 PID 14435는 ready 이전에 SIGABRT로 종료했다. stderr 97바이트의 원오류는 Rust main thread의 stack overflow였다. stdout은 0바이트였고 interposer-loaded만 기록됐다. 이때 SDK가 버리던 native stderr를 처음 확보했다.

`nm -u`의 실제 native import는 `_socket`이다. `socket$NOCANCEL` 불일치가 아니었다.

NULL/ENOSYS 가설을 구분하려고 기존 C 소스에 포인터·dlerror 기록과 constructor 종료만 추가한 별도 진단을 실행했다. main이나 socket 경로는 다시 실행하지 않았다.

| 실제 포인터 확인 | 결과 |
|---|---|
| `actual_socket == NULL` | 0 |
| `actual_socket == replacement` | 1 |
| `dlerror` 있음 | 0 |

원시 주소 두 개는 `/private/tmp/c21-v6ptr-wvihocsw/raw/resolver.jsonl`에만 보존했다. 따라서 이번 실패는 NULL 반환 후 ENOSYS로 빠진 경우가 아니다. `RTLD_NEXT("socket")`가 replacement를 반환했고, 기존 전달 호출이 자기 자신으로 재진입했다. 기존 socket-passed 로그가 원함수 호출 뒤에 있어 재귀 중에는 기록이 생기지 않았다.

## 원함수 전달 대조

새 조건에서는 호출 진입을 먼저 기록하고 재진입 guard를 넣었다. IPv6만 실패시키며 IPv4는 실제 원래 socket 경로로 전달했다. 제품 소스는 바꾸지 않았다.

| 별도 진단 | ready / exit | IPv6 거절 | IPv4 성공 | 재진입 |
|---|---|---:|---:|---:|
| BSD socket syscall 전달 | true / 0 | 23 | 79 | 없음 |
| interposer 이미지 안의 직접 `socket()` 호출 | true / 0 | 23 | 79 | 0 |

최종 제품 검사는 두 번째 방식을 사용했다. dyld의 이미지 내부 참조 동작을 추정만 하지 않고 실제 IPv4 FD 생성과 재진입 0으로 대조했다. C 로그는 파일에만 쓰며 native stdout에 진단 문자열을 섞지 않았다.

## 실제 제품 결과

동결 release binary SHA는 `f17f03fafcdf3a31e374d6cbc0ccbbbd8000ba6a7eba5d9b44605e742c409aed`다. 기존 실패와 동일하다. Python 소스 52개도 기존 manifest와 복사 전후 동일했다. 기존 `run.py`, `observe-exact.py`를 변경 없이 재사용했고 새 모델이나 검증 프레임워크를 추가하지 않았다.

final dylib는 Python 시작 후 native 자식 환경에만 넣었다. socket trace의 PID는 각 엔진 PID 하나씩뿐이었다. 고정 포트 53271은 제어 프로세스가 실제 IPv4 UDP socket으로 먼저 점유했다.

| 항목 | 제품 A | 제품 B |
|---|---|---|
| Python service PID | 37765 | 37771 |
| 실제 engine PID | 37768 | 37791 |
| AF_INET6 / errno 47 거절 | 26회 | 26회 |
| 실제 IPv4 socket 성공 | 80회 | 80회 |
| 직접 전달 재진입 | 0 | 0 |
| requested port | 53271 | 53271 |
| 실제 bind | `0.0.0.0:49588` | `0.0.0.0:50760` |
| port_fallback | true | true |
| native stderr | 0바이트 | 0바이트 |

두 ready 모두 IPv6 bound address가 없었다. 실제 공개 CLI로 init, 일회용 invite, stdin join을 수행한 뒤 양쪽 active 상태를 확인했다. 양방향 제품 ping은 모두 IPv4 direct 경로였으며, 해당 native response event의 TLS origin과 상대 수신·회신 본문 digest가 일치했다. 다른 표본의 경로 snapshot이나 후보 주소로 성공을 대신하지 않았다.

검증한 경로는 A→B `192.168.0.11:50760`, B→A `127.0.0.1:49588`이다. 같은 호스트의 두 실제 제품 서비스이며 다른 NAT·relay 경유 표본으로 합치지 않는다.

## 정리·보존·범위

서비스 두 개는 정상 stop 후 exit 0이었다. 소유 엔진 잔여 0, control socket 잔여 0이며, 두 실제 포트와 점유 대조 포트 총 3개를 다시 bind할 수 있었다. native와 service stdout/stderr는 역할별 파일 또는 실제 JSONL pipe로 분리했고, 직접 진단의 원 stdout JSONL은 그대로 보존했다.

기존 실패 폴더·C source·기존 dylib·state·key는 건드리지 않았다. 새 상태와 키도 private root에 보존했고 키 값은 읽거나 복사하지 않았다. 전역 IPv6, 방화벽, 프로필, 인증·키 설정, 제품 소스, plan·ledger를 수정하지 않았다. 사용자 세션에 보낸 신호는 0이다.

- [실제 제품 결과](result.json)
- [진단·SHA·범위 대조](validation.json)
- [수정한 C interposer](noipv6-direct.c)
- [제품 실행 코드](controlled-run.py)
- 최종 제품 private raw: `/private/tmp/c21-v6sys-mv0pn9dt/`
- 같은 기존 조건의 직접 native 원오류: `/private/tmp/c21-v6diag-r1p10hzv/raw/`
- 기존 C constructor 포인터·dlerror: `/private/tmp/c21-v6ptr-wvihocsw/raw/`

실제 IPv6 없는 호스트 자체의 수용 근거는 별도로 남는다. 이번에 통과한 범위는 명시한 소유 프로세스의 AF_INET6 실패를 실제로 주입한 조건에서의 IPv4 제품 동작과 포트 대체다.
