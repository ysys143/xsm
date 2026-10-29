# C private fixture 전체 실행계획 (실행 전 고정)

작성 시각: 2026-10-28T17:59:58.467710+00:00. 이 계획은 isolated C 비교체에만 적용한다. D12 backend 선택·제품 채택·배포 승인이 아니다.

## 고정 입력과 격리

- engine은 0.12.10, SHA-256 `6ac4bb4837469867edc2dba3cbbd6e4dd9fb18ad0389db69ff6ef21683317a44`만 사용한다. 기존 binary는 읽고, 실행 사본은 각 tmp에 둔다.
- local `/private/tmp/p11-C-a33f52rq`, peer `/private/tmp/p11-C-q27ngmzj`. 두 root 모두 본인 UID/0700이며 state·HOME·XDG·IPC socket·코드·입출력을 이 root 아래로 한정한다. socket은 `<root>/state/network.sock`이고 macOS short-path fallback이 발생하지 않는 길이다.
- `REASON_NETWORK_HOME`과 engine HOME는 명시적으로 private 경로를 사용한다. 기존 REASON_NETWORK/TINCAN/agent 환경을 제거한다. `lan=false`, `tray=false`, `reason=false`, `auto_update=false`, `share_unmanaged=false`; NO_SERVICE/NO_TRAY/NO_MDNS를 설정한다.
- 실제 Jaesol’s network, 현재 `.reason` 상태, 실제 Reason CLI, Reason 계정/키, 전역 membership·프로필·MCP는 사용하지 않는다. native Codex는 이전 A/B/D처럼 기존 ChatGPT 인증만 참조하고 user config/rules·hooks/plugins/apps/shell을 끈 ephemeral/read-only invocation이다. auth 파일 내용을 직접 읽거나 복사하지 않는다.

## 규약과 필수 외부 endpoint

- `probe_engine.py` 및 upstream v0.12.10의 proto/paths/config/net/relays/teamops 소스를 확인했다. IPC는 명시 Unix socket의 JSONL, create_team(name,person), link(new=false), join(ticket,person), register(pull), send/inbox/delivered/team이다. 로그인 proof를 만들거나 읽지 않는다.
- transport 제어/비밀 전달: 기존 `ssh jaesol-macmini`만. `BatchMode=yes`, `StrictHostKeyChecking=yes`, `UpdateHostKeys=no`; 새로운 hostkey 수락 없음.
- engine의 기본 signed relay 목록: `https://reasonmachines.com/network/relays.json`.
- 현재 목록의 정상 relay: `https://relay-sfo1.compute.reasonmachines.com`, `https://relay-iad1.compute.reasonmachines.com`, `https://relay-fra1.compute.reasonmachines.com`, `https://relay-sin1.compute.reasonmachines.com` (HTTPS/네이티브 relay 프로토콜).
- 기본 iroh endpoint 주소 lookup/publish: `dns.iroh.link` 및 `https://dns.iroh.link/pkarr`의 native 기본 경로. direct QUIC/UDP endpoint는 엔진이 bind/관측한 실제 값만 기록한다. relay 사용 여부는 IPC team.machines.link/relay_connected readback만 인정한다.
- native Codex는 기존 ChatGPT subscription 서비스에 정상 접속한다. 새 서비스/VM/relay 배포·방화벽·TCC·계정 변경은 없다. source 조회는 고정 GitHub raw 소스의 읽기 전용 다운로드였다.

## 순서와 중단 기준

1. 양쪽 바이너리 hash/version과 private root/socket 길이·비어 있는 state 확인, process handle(PID/start/소유 경로) 기록.
2. foreground private daemon 두 개만 시작한다. raw 로그는 저장하지 않고 line hash와 안전한 상태/오류 분류만 저장한다.
3. local private 팀 생성. link capability는 Python 메모리에서 받아 기존 SSH stdin으로 peer Python에 전달하고 peer의 명시 IPC join에만 사용한다. argv/파일/원시 로그/보고/출력에 capability나 비밀값을 저장하지 않는다. 엔진 자신의 필요한 private state/key는 0700 격리 상태에만 존재하며 종료 후 정리한다.
4. membership readback에서 두 controlled endpoint만 active인지 검증하고 공개 ID는 hash로만 남긴다. local·peer fixture pull client만 등록한다. 실제 작업 session/제3자는 편입하지 않는다.
5. 같은 짧은 `2+2=5` 과제를 native Codex로 first/followup 실행한다. 진짜 모델 JSON·request ID·native conversation·PID/시간을 확인한다. echo/합성 모델은 통과가 아니다.
6. private client/peer daemon의 controlled reconnect 후 같은 요청의 보존 native 답을 회수하고, 새 native turn을 추가한다. native conversation은 이전 A/B/D와 같은 ephemeral 조건으로 새로 생기며 native resume/기억 유지로 주장하지 않는다.
7. 정확한 자기 handle의 model/daemon/client/listener만 종료한다. IPC 연결 거절과 프로세스 종료를 재조회한다. private membership/key/state와 실행 사본은 정리하며 secret 없는 코드·최소 입력/결과·hash/상태는 보존한다.

OS 권한/TCC/로그인/외부 가입 요구, fixture 밖 membership 또는 endpoint 사용이 필요하면 우회하지 않고 즉시 중단한다. capability/secret 노출 가능 raw 출력은 저장하지 않는다. 다른 NAT·UDP 차단·proxy·relay 강제 환경은 미확보로 남는다. 새 팀은 이 자가완결 fixture의 두 노드만으로 제한한다.
