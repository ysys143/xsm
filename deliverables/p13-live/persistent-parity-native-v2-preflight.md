# 영속 TUI v2 모델 없는 준비 검사

결과: PASS. 별도 v2 준비 harness의 `prepare_proxy_root()`가 `tui/proxies`를 사전 생성한다. 이전 4조건/7 launch 산출물은 수정하지 않았다.

동일 proxy.py를 복사하고 frozen MCP의 `/usr/bin/python3 -m xsm mcp`를 실제 실행했다. proxy의 argv/cwd와 명시 환경값은 JSON에 기록했다. 별도 private XSM state로 initialize → initialized notification → tools/list만 보냈다. native metadata를 만들거나 수신 도구를 호출하지 않았다.

- proxy exit 0, MCP server exit 0.
- proxy 시작 stderr와 server stderr 모두 빈 문자열.
- 실제 tools/list에 xsm_inbox, xsm_files 포함 총 20개 도구 광고.
- 실제 codex-cli 0.164.0 및 CLI help 검증. TUI sandbox/ask-for-approval/no-alt-screen, ask attachment/wake/wait/priority flags 확인.
- frozen source 315파일 전후 SHA 검증. 현재 repo cwd의 기존 trusted 설정 확인, config SHA 불변. 제품·권한·전역설정·plan·ledger 수정 없음.
- 모델 실행 0, 수신 tool 호출 0. preflight의 PID/state는 본 평가 native readiness로 사용하지 않는다.

남은 전제는 별도 시작 지시, 실제 TUI에서의 MCP wait0 성공과 actual CID/live PID/files capability 확인이다. tools/list 성공만으로 native 준비나 통신 성공을 주장하지 않는다. 후속 모델은 시작하지 않았다.

raw: `/private/tmp/persistent-parity-v2-preflight-9brckzcg`. 동일 prefix의 `.py`는 실행 코드, `.json`은 실제 응답/검사 결과, `.manifest.json`은 raw 및 script SHA다. 원 준비 실패를 성공으로 덮어쓰지 않았다.
