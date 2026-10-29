# J01 clean native 설치 관측과 MCP 등록 결함 수정

로컬 설치 결함은 수정·검증됐다. clean native의 발견→첫 질문/회신은 인증 전제 미충족으로 미실행이다. 전체 J01/G10 통과로 확대하지 않는다.

## 원 clean 관측

새 Claude/Codex 설정 홈과 private XSM_HOME에서 실제 `xsm install`을 호출했다. installer HOME도 private으로 두어 실제 `~/.local/bin/xsm`을 바꾸지 않았다. native 조회에는 factory MCP, `--ignore-user-config`, 수동 설정 주입, hook-trust 우회, allowedTools 보정을 사용하지 않았다.

두 clean 홈의 정상 CLI 로그인 상태는 모두 미로그인이었다. credential 값·파일을 열거나 복사하지 않았고 로그인·승인·계정 변경도 하지 않았다. native 모델 0회, 발견→첫 질문/회신은 미관측이다. [OpenAI 인증 문서](https://developers.openai.com/codex/auth/)의 파일 cache/OS credential store 지원과 별개로, 이 실행의 clean 기본 조회는 인증을 찾지 못했다. 다른 재사용 경로가 모두 불가능하다는 뜻은 아니다.

## 실제 설치 결함과 영향 범위

원 combined CLI는 exit 4/InstallConflictError였다. auth 부재와 독립적으로 native `claude mcp get xsm`이 clean `.claude.json`을 생성하면서 firstStartTime/version, migration, 알림·로컬 식별 metadata를 기록했다. 설치기가 이를 읽기 전용 조회로 가정해 revision 충돌이 발생했다. 결과에는 metadata 값 대신 변경 key·파일 hash·trace만 남겼다.

| 실제 CLI 조건 | 수정 전 | 수정 후 native readback |
|---|---|---|
| Claude clean | 조회 중 config 생성 → conflict | added, get exit 0, 설치 prefix 일치 |
| Claude 기설치 stale | replaced | replaced, get exit 0 |
| Claude current/재설치 | initialized 설정에서는 재진행 가능 | current, get exit 0 |
| Codex clean | added | added, get exit 0 |
| Codex 기설치 stale | replaced | replaced, get exit 0 |
| Codex current | current | current, get exit 0 |
| Claude+Codex multi홈 | 첫 Claude 실패로 후속 Codex 미진행 | install exit 0, 두 get 모두 설치 prefix 일치 |

단일 clean Claude 결함이 포함된 multi홈 호출은 중단된다. 모든 기설치 홈이나 Codex 자체가 같은 결함이라고 확대하지 않았다. 원 실패와 수정 후 run은 분리·보존했다.

## 제품 변경과 보존 계약

- `install.py`: Claude user-scope MCP 등록을 JSON의 비파괴 읽기로 확인한다. 등록/교체는 계속 native add/remove를 사용한다. Codex 조회 경로는 유지했다.
- invalid JSON·비정상 구조·symlink를 고치거나 삭제하지 않는다. revision 재기준화나 metadata 변경의 blanket 허용은 없다. 실제 concurrent edit 검사를 current 조기 반환보다 먼저 수행한다.
- `remove_mcp`의 False는 absent다. native remove nonzero는 명시 예외로 남긴다.
- coordinator의 공개 uninstall 수정은 MCP를 첫 변경으로 검사·제거하며 OSError/ValueError는 단일 진단/exit 4다. 실패 home의 hooks와 runtime/CLI 정리를 보존한다. 이 담당은 cli.py를 수정하지 않았다.

## uninstall 실제 반례

| 입력 | 원 실패 | 수정 후 |
|---|---|---|
| 손상 JSON | traceback/exit 1, hooks 일부 변경 | exit 4, 진단 1줄, traceback 없음, hooks/MCP bytes·revision 불변 |
| config symlink | traceback/exit 1, hooks 일부 변경 | exit 4, 진단 1줄, hooks/link/destination 불변 |
| 정상 Claude+Codex | 별도 정상 fixture | install 0 → uninstall 0, 양쪽 xsm 등록 제거 |
| native remove exit 7 | False로 absent와 혼동 가능 | 명시 예외 → 공개 exit 4, hooks/config 보존 |

원 두 손상 fixture는 복구하거나 삭제하지 않았다. green 재실행에는 같은 입력의 새 fixture를 사용했다.

## 검사·동결

Python 3.9·3.14 각각 **91개 통과**: native MCP 회귀 11개와 install safety/runtime/Codex 영향 검사. 실제 `cli.main` 정상·invalid JSON·symlink·native 실패를 검사했다. CAS guard 제거 변이와 옛 cmd_uninstall만 복원한 메모리 변이는 모두 red였다. mutation으로 제품 파일을 바꾸지 않았다.

이 담당의 제품 변경은 `xsm/install.py`, 신규 `tests/test_install_native_mcp.py`뿐이며 동결했다. 추가 native 모델 실행, credential 값 조회/복사, 전역 profile 변경, hook trust 부여, 추가 API 과금은 없다. installer가 clean 홈에 만드는 기본 규칙 외에 권한 보정은 하지 않았다.

## 증거

- [원 clean 실패](clean-install.json)
- [수정 전 실제 CLI 6조건·trace](clean-install.diagnostic-pre.json)
- [수정 후 실제 CLI 6조건·combined](clean-install.diagnostic-post.json)
- [원 uninstall 실패](clean-install.uninstall.json)
- [수정 후 두 반례](clean-install.uninstall-fixed.json)
- [정상 multi홈 uninstall](clean-install.uninstall-normal.json)
- [CAS 변이](clean-install.mutations.json) / [옛 caller 변이](clean-install.uninstall-mutation.json)
- [묶음 결과·hash·검사 로그](clean-install.final.json)
