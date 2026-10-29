# ADR-0021 기초 P2P batch 독립 Opus 검토

고정한 소스에서 구체적인 Medium 결함 2건을 보고해 **수정 필요**로 판정했다. 이 결과는 기초 P2P 가입·멤버십 batch에 한정하며, 전체 ADR-0021 완료 판정이 아니다.

## 구체적인 Medium 이상 결함

### F1 · Medium · 네트워크 전환 후 이전 네트워크 피어 목록(_peers)이 남아, 새 네트워크의 서명 멤버십 스냅샷이 비멤버에게 계속 전송됨

- 소스: `xsm/network.py:216-254, 308-311, 313-323, 382-388` (아래 고정 복사본 기준).
- 조건: 기기가 네트워크 A의 활성 멤버로 동작하며 Daemon._peers에 A의 피어 P_A가 있다. 이 상태에서 사용자가 `xsm network join --ticket-file <B 티켓>`을 실행해 네트워크 B로 전환하고 성공한다. ADR-0021 58/79행은 팀 전환을 요구사항으로 명시한다.
- 재현 경로: local('join')은 store가 있어도 거부하지 않고 _join을 호출한다. _install이 active.json을 B로 바꾸지만 self._peers는 초기화하지 않고 B 피어만 추가한다(251행). 이어 _save_peers가 P_A까지 peers-<B 해시>.json에 기록한다(311행). synchronize(384-386행)는 2초마다 self._peers 전체에 rpc(peer, {'op':'sync'})를 보낸다. rpc의 317행 활성 검사는 op=='sync'이면 건너뛰고, store는 이제 B이므로 322행에서 packet['state']=B.snapshot()이 붙는다. 323행 transport.request가 이 패킷을 P_A로 전송한다. P_A의 incoming은 network_id 불일치로 'network-unavailable'을 반환하지만, 본문은 이미 P_A의 프로세스/핸들러에 도착한 뒤다. 재시작 전까지 반복되며, serve() 418행의 is_active 필터는 재시작할 때만 적용된다. 정적 추론이며 실행하지 않았다.
- 영향: MembershipStore.snapshot 계약('활성 멤버에게만 전송할 내부 상태')을 위반한다. B의 네트워크 이름, 모든 멤버 endpoint ID와 machine_name, 초대 해시·만료 정보, 이 기기의 주소가 B 비멤버인 A 피어들에게 주기적으로 공개된다. 비밀값·개인키는 아니지만 다른 팀의 명단·기기 메타데이터 노출이다.
- 검사 근거: tests/test_network_service.py의 test_failed_wrong_network_and_verified_wrong_state_preserve_active는 전환 실패 시 active.json 보존만 검사한다. 전환 성공 뒤 _peers나 sync 대상을 검사하는 테스트는 확인된 범위에 없다. test_network_membership.py의 adopt 테스트는 store 단위에 그친다.

### F2 · Medium · sidecar가 종료되면 Python 서비스가 감독 없이 남아 lock을 계속 쥐고, `start`가 재기동하지 못한 채 실패함

- 소스: `xsm/network.py:122-147, 208-214, 391-448` (아래 고정 복사본 기준).
- 조건: 서비스 실행 중 Rust xsm-net 프로세스가 종료된다. 예: panic, 외부 kill, ipc_write_timeout 뒤 serve 종료(native/xsm-net/src/ipc.rs 54-66, 97). 이 경로는 코드에 명시적으로 처리된 상황이다.
- 재현 경로: network_transport.py 304-307행 _watch_process가 _fail('process_exited')와 _dispose만 수행하고, Daemon과 serve()에는 아무 통지가 없다. 그래서 serve_forever(445행)가 계속 돌며 service.lock을 쥔다. 활성 네트워크가 있으면 status()의 store.is_active가 _Graph 검증에서 Sidecar.verify를 호출한다. 이 호출이 SidecarError를 내면 valid=False가 되어 MembershipError('invalid_signature')로 이어지고, Handler는 'operation-failed'를 반환한다. 이때 start()의 125행 status 호출이 실패해 새 child를 spawn하지만, child는 397행 flock LOCK_NB에 실패해 즉시 0으로 종료한다. 그 결과 144-145행에서 'service-start-failed'가 난다. 네트워크가 없을 때는 status가 stale ready_info로 'running'을 보고하므로 start()가 성공처럼 반환된다. 그 뒤 init/join은 서명 또는 요청 단계에서 실패한다(_join에서는 process_exited가 'join-response-unknown'으로 분류됨, 233-244행). 정적 추론이며 실행하지 않았다.
- 영향: sidecar가 한 번 종료되면 P2P 수신·동기화·가입·초대가 영구히 불가능해진다. 자동 복구가 없고, CLI가 안내하는 recover_at(status)도 operation-failed나 오해 소지 있는 running을 돌려준다. 사용자가 `xsm network stop`을 알아야만 복구된다. 수명·crash 처리 요구(검토 범위 7)에 해당한다.
- 검사 근거: tests/test_network_transport.py의 test_process_exit_fails_all_pending_without_payload_or_stderr는 Sidecar 객체 수준의 pending 실패만 확인한다. tests/test_network_service.py는 정상 stop/restart(test_service_restart_retains_keys_membership_and_closes_listeners)만 다루고, 서비스 실행 중 sidecar 종료는 다루지 않는다.

## 실제 실행과 보존

- pinned CLI: `/Users/jaesolshin/.local/share/claude/versions/2.1.312` · 버전 `2.1.312` · PID **44220**.
- 구독 프로필 `.claude-3`; 실제 auth metadata는 `claude.ai / max / firstParty`였다. API 키 환경을 제거했으며 값은 조회하지 않았다. 실제 init의 `apiKeySource`는 `none`이다.
- 요청 모델, 실제 init 모델, 최종 modelUsage ID가 모두 **`claude-opus-5-5`**다. 별도 CLI 모델 실행 **1회**, 재시도 **0회**, 완료 후 추가 모델 실행 **0회**다.
- 종료 코드 0, `is_error=false`, 모델 검토 276.488초. 허용 도구는 Read/Glob/Grep, 실제 사용은 Read/Grep 18회였다. MCP·bundle 밖 읽기·permission denial은 모두 0이다.
- 도구 제한은 해당 세션 인자로 적용했다. 모델 영속 등록이나 권한 규칙 변경 명령은 실행하지 않았다.
- 원 리뷰 JSON·stderr·prompt·실행 메타데이터·소스 복사본은 `/private/var/folders/hw/9m3g7fvn4_l3rp2y473km9sm0000gn/T/adr0021-core-opus-xsse80k4`에 보존했다. 디렉터리 0700·파일 0600을 확인했다.
- 실제 복사한 소스/계약 파일은 18개다. 각 source SHA와 검토 후 현재 파일 비교는 [공개 JSON](core-opus-review.json)에 기록했다. 복사본은 검토 후에도 모두 동일했다.
- 원 리뷰 JSON SHA-256: `213a3c1deb18da71403900760035603d723319ae2452b1731940eb2bbc510da8`.
- bundle manifest SHA-256: `b2ea07c03372db80ebe45b512d70e0179dc623a03292970a89d7afda57a00235`.

## 검토 범위와 한계

TLS origin·서명/admission/operation 결속·JSON 숫자 보존·가입 응답 유실과 원자적 전환·제명 후 옛 재사용 링크 회수·비밀 비노출·서비스 수명을 검토했다. 원 리뷰는 개인키를 Rust 안에 두는 경로, 동등 멤버 권한, 제명/탈퇴 batch와 수치 회귀 수정도 소스 기준으로 확인했다. 구체적인 Medium 이상으로 보고하지 않은 추측은 결함 목록에 넣지 않았다.

**리뷰어와 이번 검토 evaluator는 테스트를 실행하지 않았다.** 두 결함은 소스의 실행 경로를 대조한 정적 판정이며 실제 재현 실행은 하지 않았다. 기존 membership 11개 양 Python 통과와 두 CLI 서비스의 가입 성공은 이 독립 리뷰의 실행 결과와 구별한다. 서비스8 재검증은 요청 시 진행 중이었으므로 이번 문서는 그 통과를 주장하지 않는다.

Cargo.lock과 native sidecar 테스트 일부는 의존성·버전 맥락에서 확인했다. 전체 의존성 감사, 모든 테스트 행의 완전한 검토, 물리 머신·NAT·relay·proxy의 실측이 아니다. 친구 신뢰 모델 밖의 Byzantine 보장·관리자·새 로그인·전면 재설계를 요구하지 않았다.

검토 후 다음 원본 파일의 SHA가 복사본과 달라졌다. 후속 통합 변경을 이번 판정에 포함하지 않았다:

- `xsm/network.py`
