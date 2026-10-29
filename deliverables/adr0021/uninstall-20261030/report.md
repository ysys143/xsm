# A21-05 실제 설치·중지·제거 관측

최종 frozen source로 인증 없는 private HOME·XSM_HOME·Codex profile을 구성하고 실제 공개 CLI 설치·가입·중지·제거를 실행했다. 한 홈 제거는 공유 서비스를 죽이지 않았고, 명시적 network stop 뒤 마지막 홈 제거에서 소유 PID·control socket 잔여 0과 UDP 포트 재바인딩을 확인했다. 새 모델 호출은 0회다. 전체 ADR 또는 G13 완료 판정은 아니다.

## 소스와 실행 조건

- 동결본: `/private/var/folders/hw/9m3g7fvn4_l3rp2y473km9sm0000gn/T/adr21-final-20261030-fx0yt4x3`. manifest에 있는 파일 178개의 SHA를 실행 후 확인했다. 제품·테스트 파일은 수정하지 않았다.
- Python: `/usr/bin/python3` 3.9.6. 실제 Codex CLI: `codex-cli 0.165.0`. `codex mcp add/get/remove`는 구독 인증 없는 새 private profile에서 설정 작업으로만 실행됐다.
- 네트워크 엔진은 동결본의 사전 빌드 release를 `XSM_NET_BINARY`로 지정했다. 새 build나 전역 설치는 하지 않았다. 서비스는 같은 호스트의 두 private XSM_HOME으로 연결했다.
- privateRoot: `/private/tmp/adr21-uninstall-2fafuj8s`. 기존 사용자 profile·SSH·Tailscale·권한·키는 읽어 바꾸거나 연결하지 않았다. CLI의 HOME·CODEX_HOME·XSM_HOME과 temp 경로는 이 root 안에 한정했다. API 키·기존 런타임 식별 환경은 자식 환경에서 제외했다.

## 실제 명령별 기록

각 시각은 명령 완료 UTC이고 초 값은 해당 subprocess 실행 시간이다. 첫 설치는 frozen `bin/xsm`, 설치 후에는 private `HOME/.local/bin/xsm`을 사용했다. 마지막 link 제거 후 peer 정리는 frozen 공개 CLI로 실행했다. 초대는 private ticket 파일로만 전달했고 값은 출력하지 않았다.

| 단계 | 실제 인자 | 완료 시각 UTC | 소요 초 | 종료 코드 |
|---|---|---|---:|---:|
| install-a | `install --codex-home $PRIVATE_ROOT/codex-a --python /usr/bin/python3` | 2026-10-29T15:38:29.382701+00:00 | 0.737 | 0 |
| install-b | `install --codex-home $PRIVATE_ROOT/codex-b --python /usr/bin/python3` | 2026-10-29T15:38:29.802635+00:00 | 0.419 | 0 |
| configure-shared | `network configure --relay off --port 0` | 2026-10-29T15:38:30.579885+00:00 | 0.777 | 0 |
| init-shared | `network init private-uninstall-evaluation` | 2026-10-29T15:38:30.966221+00:00 | 0.386 | 0 |
| configure-peer | `network configure --relay off --port 0` | 2026-10-29T15:38:31.246045+00:00 | 0.279 | 0 |
| invite-private | `network invite` | 2026-10-29T15:38:31.462481+00:00 | 0.216 | 0 |
| join-peer | `network join --ticket-file $PRIVATE_ROOT/state/network/invites/afc681186c8f62915267ed377372a54f.json` | 2026-10-29T15:38:31.861174+00:00 | 0.398 | 0 |
| shared-before-uninstall | `network status` | 2026-10-29T15:38:32.081982+00:00 | 0.220 | 0 |
| uninstall-a-shared-service-live | `uninstall --codex-home $PRIVATE_ROOT/codex-a` | 2026-10-29T15:38:32.395113+00:00 | 0.306 | 0 |
| shared-after-a-removal | `network status` | 2026-10-29T15:38:32.611648+00:00 | 0.216 | 0 |
| explicit-network-stop | `network stop` | 2026-10-29T15:38:32.826983+00:00 | 0.214 | 0 |
| uninstall-b-after-explicit-stop | `uninstall --codex-home $PRIVATE_ROOT/codex-b` | 2026-10-29T15:38:33.391095+00:00 | 0.310 | 0 |
| cleanup-status-peer | `network status` | 2026-10-29T15:38:33.609563+00:00 | 0.214 | 0 |
| cleanup-stop-peer | `network stop` | 2026-10-29T15:38:33.835723+00:00 | 0.226 | 0 |
| install-c-canonical-preservation | `install --codex-home $PRIVATE_ROOT/codex-c --python /usr/bin/python3` | 2026-10-29T15:40:51.426914+00:00 | 0.427 | 0 |
| uninstall-c-canonical-preservation | `uninstall --codex-home $PRIVATE_ROOT/codex-c` | 2026-10-29T15:40:51.740595+00:00 | 0.302 | 0 |

총 공개 CLI 명령은 16개이며, 원문의 canonical 보존을 위한 추가 install/uninstall 2개와 상태 확인·독립 peer 정리도 포함했다. 명령 실행 시간의 합은 5.647초다. 준비·소스 검토·보고서 작성 시간은 이 합에 포함하지 않았다. 추가 사용자 prompt·로그인·권한 조작은 0회다. 다만 설치기는 각 홈의 다음 native 세션에서 hook trust와 새 세션/MCP 재연결이 필요하다고 안내했다. 이 후속 승인은 실행하지 않았고 설치 setup의 first-roundtrip은 unknown이었다. 따라서 실제 native 초기 사용까지 사용자 개입이 0회라고 확대하지 않는다.

## 제거 계약과 결과

문서 README_ko 158줄은 uninstall이 설치가 더한 훅·MCP·skill·설정 항목과 마지막 CLI link를 제거하되 runtime 사본은 남긴다고 설명한다. 네트워크 서비스는 별도 중지 대상이다. `cmd_uninstall`에는 network stop 호출이 없으며 이를 자동 중지로 가정하지 않았다.

1. A·B Codex 홈을 하나의 XSM_HOME에 실제 설치했다. init/invite/join으로 독립 peer XSM_HOME까지 실제 membership 연결을 만들었고 두 멤버 활성 상태를 확인했다.
2. 서비스가 살아 있는 상태에서 A만 uninstall했다. 공유 service/engine PID가 동일하고 서비스가 계속 active였으며, B 홈 전체의 파일/링크가 byte 단위로 같았다. B를 위한 CLI link도 남았다.
3. B를 통해 명시적으로 `network stop`했다. service/engine PID와 private control socket이 사라졌고 원래의 IPv4·IPv6 UDP 바인딩 2개를 모두 다시 bind했다.
4. 이후 B를 실제 uninstall했다. xsm MCP entry·hook group·skill link와 마지막 CLI link는 없어졌다. 사용자 custom MCP/hook/skill/설정 값은 유지됐다.
5. main 공유 state와 별개인 peer 서비스는 그동안 active였다. 마지막에 peer도 공개 `network stop`으로 정리해 PID·socket 잔여 0, UDP 바인딩 2개 재사용을 확인했다.
6. canonical 원문 보존은 별도 C profile을 실제 설치한 뒤, 실제 `handoff.store` API로 새 보존 fixture를 만들고 C를 uninstall해 확인했다. canonical 기록 bytes와 본문 digest가 동일하고 상태는 pending 그대로였다. 실제 모델 세션 원문이나 native 소비 성공으로 부르지 않는다.

## 보존 및 남은 파일

network의 자체 device key는 내용을 열지 않고 inode/size/mtime/mode가 같은지 대조했다. membership·key·원문·custom XSM config와 runtime copies는 남았다. 이는 복구와 다른 사용 홈을 위한 의도된 보존이며 제거 성공을 데이터 삭제로 만들지 않았다. private Codex 홈의 auth.json은 모두 없었다. 사용자 custom 설정 값과 custom hook 원문·skill·marker도 보존됐다.

남은 경로에는 runtime copies/current, network state/key, homes registry, interpreter pin, install audit/lock, policy cache, 원문·ledger와 telemetry가 있다. xsm의 활성 등록·owned component와 단순 보존/audit 잔여를 구분했다. 실제 사용 중인 다른 사용자 서비스나 profile을 종료·수정하지 않았다.

무효 업데이트·기존 runtime 보존은 최종 frozen suite의 기존 interrupted-copy/publish-failure/corrupt-snapshot 검사 근거를 연결했다. 양 Python 1933개 통과 기록은 frozen의 이전 결과이며 이번 제거 실측이나 새 전체 실행으로 합산하지 않았다. 이번에는 suite를 다시 실행하지 않았다.

평가 helper의 최초 문법 오류는 어떤 제품 명령도 실행하기 전에 발생했고 helper만 바로잡았다. 이후 공개 CLI 명령의 실패는 없었고 제품 결함은 이 범위에서 관측하지 않았다.

[명령·검사·소스 증거 JSON](summary.json) · [실행 결과](results.json) · [실행 helper](run.py)
