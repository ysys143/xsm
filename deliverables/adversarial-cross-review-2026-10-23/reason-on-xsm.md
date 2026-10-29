<!-- 독립 비평 원문의 주장과 판정은 유지하고 링크 목적지만 정리함. -->
xsm에 대한 가장 강한 기소는 **사용자의 의사를 에이전트가 이미 이해했는데도, 메시지 채널이 별도의 승인 기록과 재실행 절차를 충족하라고 요구한다는 것**이다. 실제 사용자가 연결을 승인했지만 xsm은 그 답을 수집하지 못했고, 안내한 복구 수단인 `--reply`까지 거절했다. “나머지는 에이전트가 한다”는 약속은 여기서 깨진다. 일을 맡기고 돌아가려던 사용자는 승인 입력 방식을 다시 맞춰야 하고, 에이전트는 대화 대신 훅·승인 기록·전송 경로의 상태를 해석해야 한다.

이 평가는 Reason을 지지하는 실무 에이전트의 관점을 가정한 독립 비평이며 공식 견해가 아니다. 이하 **E**는 [원시 실행 증거](/Users/jaesolshin/Documents/GitHub/cross-session-messaging/deliverables/xsm-reason-live-comparison-2026-10-23/evidence.json), **R**은 [캐시된 Reason 설계 문서](https://github.com/reason-machines/reason-network/blob/039b9571dab11f980813918b60a827b8bb27fbfd/DESIGN.md)다. 실험 버전은 xsm `0.4.20`, Reason CLI `0.2.557`, 엔진 `0.12.10`, Claude Code `2.1.309`, Codex `0.163.0`이다. 기존 설치가 공존한 단일 머신의 작은 표본이며, Reason 평가용 Claude 송신은 사전 승인돼 있었다.

1. **승인했는데도 승인 복구를 사용자에게 다시 요구한다.**

   **행동과 부담.** 다른 저장소의 `cmp-gamma`에 일을 맡긴다. xsm이 연결 승인을 요구해 사용자가 “비교용 연결 허용, 종료 후 해제”라고 답한다. 그런데 정상 재실행은 계속 승인을 요구하고, 답변 원문을 전달한 `--reply`도 거절한다. 사용자에게 남는 일은 업무 판단이 아니라 자신의 승인을 도구가 알아들을 입력으로 다시 만드는 것이다.

   **확인한 사실.** E의 `approval_ingestion`은 실제 답변 수신을 `true`, 승인 문구의 recent 기록 존재를 `false`, pending의 `verdict`를 `null`로 기록한다. `calls[18]`의 재실행은 거절됐고, `recorded_results["xsm-approval-explicit-reply1.json"]`도 종료 코드 2와 `--reply is ignored`를 남겼다. 현재 [consent.py:596](/Users/jaesolshin/Documents/GitHub/cross-session-messaging/xsm/consent.py:596)는 같은 세션의 recent 기록이 존재하면 그 안의 말과 일치해야 답변을 받는다. 기록이 전혀 없을 때는 같은 원문을 받는다. 메모리 fixture로 이 차이를 재현했다.

   **Reason의 배치와 xsm 반론.** Reason의 `ask_user`는 답변을 해당 호출의 결과로 돌려주도록 설계했다(R:189). 승인 수집 책임을 별도 요청에 묶는 방식이다. 이 경로의 실제 성공은 이번 표본에서 미검증이다. xsm의 합당한 반론은 에이전트가 승인 문구를 지어내는 것을 막아야 한다는 것이다. 그러나 그 목적은 정당해도, 실제 답변을 놓친 뒤 동일한 수집 기록만 요구하는 복구 경로는 해결되지 않는다.

   **판정·철회 조건.** 승인 수집과 복구 실패는 실행으로 확정된다. 정확히 어느 하네스 이벤트가 빠졌는지는 미확정이며, 설치본 `consent.py`의 체크아웃 일치 기록도 없다. 같은 비동기 답변 경로에서 추가 사용자 입력이나 상태 파일 편집 없이 승인·재전송이 끝나는 실행 증거가 나오면 이 공격을 철회한다. 연결 이후 구간은 현재 미검증이다.

2. **“저 세션에 맡겨”를 통신 관계의 범위와 수명 선택으로 확대한다.**

   **행동과 부담.** 다른 저장소의 동료에게 한 번 검토를 부탁한다. 기본 연결 계획은 두 폴더의 세션들을 양방향으로, 해제할 때까지 연결한다. 사용자는 특정 업무를 넘기는 동시에 앞으로 어떤 세션들까지 서로 통하게 할지 판단해야 한다. 더 좁은 `reach`나 여러 폴더의 `join`을 쓰려면 에이전트가 그 의미를 구분해야 한다.

   **코드 사실.** [connect.py:45](/Users/jaesolshin/Documents/GitHub/cross-session-messaging/xsm/connect.py:45)는 일반적으로 `link`, 넓은 폴더에서는 `reach`, 특정 가입 상태에서는 `join`을 선택한다. [config.py:218](/Users/jaesolshin/Documents/GitHub/cross-session-messaging/xsm/config.py:218)의 link는 폴더 양쪽 전체에 적용된다. 부모·워커 예외는 [config.py:297](/Users/jaesolshin/Documents/GitHub/cross-session-messaging/xsm/config.py:297)처럼 그 쌍만 허용한다. 서로 다른 저장소의 워커들이 같은 부모와 통한다는 사실만으로 동료끼리도 통하는 것은 아니다.

   **Reason의 배치와 xsm 반론.** Reason은 팀 가입 단계에 범위를 크게 배치하고, 그 안에서 저장소가 달라도 세션을 직접 고르게 한다(R:33–36, 207–211). E의 gamma는 그 상태에서 실제 회신했다. 이는 승인 비용이 없다는 뜻이 아니라 **앞서 더 넓게 승인한 비용**이다. xsm은 저장소 경계를 보존하고 `reach`도 제공한다고 반론할 수 있다. 맞다. 하지만 선택지가 있다는 사실은 일회성 위임 전에 관계 유형을 판단해야 하는 부담을 없애지 않는다.

   **판정·철회 조건.** 이는 보안 결함이 아닌 제품 선택의 대가다. 현재 xsm은 부모·자식 전용도 아니다. 같은 저장소의 N:N 직접 검토는 성공했고, 원래 의도 역시 다른 홈·런타임의 자연스러운 N:N 통신이다([INTENT.md:5](/Users/jaesolshin/Documents/GitHub/cross-session-messaging/INTENT.md:5), 19행). 이미 표현된 위임 의도만으로 필요한 관계가 설정되고, 추가 범위 선택·정리 없이 동료 간 조율까지 이어지는 경로가 확인되면 공격을 철회한다.

3. **주소는 정확하게 찾지만, 일을 맡길 상대를 고를 정보는 빈약하다.**

   **행동과 부담.** 사용자가 “지금 인증 쪽 보는 세션에 물어봐”라고 말한다. xsm의 기본 목록은 현재 통신 범위 안으로 제한되고, 표에는 폴더·세션 이름·홈 별칭·ref·상태 안내가 나온다. 에이전트는 범위를 넓혀 다시 찾고, 이름과 폴더에서 담당 업무를 추측하거나 사용자에게 되물어야 한다.

   **코드 사실.** 목록 필터는 [cli.py:51](/Users/jaesolshin/Documents/GitHub/cross-session-messaging/xsm/cli.py:51), 기본 표는 [cli.py:156](/Users/jaesolshin/Documents/GitHub/cross-session-messaging/xsm/cli.py:156)에 있다. 이름 충돌 시 [resolve.py:106](/Users/jaesolshin/Documents/GitHub/cross-session-messaging/xsm/resolve.py:106)는 후보를 반환하며, 주소에 홈·ref를 붙여 구분하게 한다. 이 목록에는 업무 내용·브랜치·busy/idle 지속 시간 같은 구조화된 선택 정보가 없다.

   **Reason의 배치와 xsm 반론.** Reason은 디렉터리에 저장소·브랜치·상태·`doing`·전달 등급을 제공하겠다고 명시한다(R:186–191). 실제 `codex_native_events[3]`에도 `cmp-*`의 idle 시간, 저장소·브랜치, `push`가 나왔다. `doing`의 정확성과 완전성은 미검증이다. xsm의 반론은 런타임 이름을 그대로 쓰고 모호하면 거절하는 편이 오배송보다 낫다는 것이다. 그 거절은 옳다. 공격 대상은 모호함을 거절하는 정책이 아니라 **업무 맥락을 주소 선택에 충분히 제공하지 않는 인터페이스**다.

   **판정·철회 조건.** 표시 정보의 차이는 사실이고, 그 때문에 사용자가 얼마나 자주 개입하는지는 추론이다. 이번 표본에 오배송은 없다. 임의로 이름 붙인 시연 세션이 아닌 실제 업무 세션들에서도 목적에 맞는 상대를 추가 질문 없이 고르는 정보가 제공되면 철회한다.

4. **같은 “보내기”인데 에이전트가 실행 경로와 기능 차이를 알아야 한다.**

   **행동과 부담.** 일반 Codex 세션이 답장을 보낸다. 셸 명령은 샌드박스로 거절되고, 에이전트가 MCP로 바꿔 보내야 한다. 전송 내용을 그대로 유지하는 것 외에, 어느 경로가 가능한지 기억하고 실패를 분류해야 한다.

   **실행·코드 사실.** E의 `codex_native_events[6–9]`에는 CLI 거절과 MCP 재전송이 모두 있다. 최종 회신은 `calls[12]`에서 실제 수신됐다. 따라서 “Codex에서 답장할 수 없다”는 공격은 틀리다. 다만 [send.py:199](/Users/jaesolshin/Documents/GitHub/cross-session-messaging/xsm/send.py:199)는 경로 전환을 호출자에게 지시한다. 기능도 완전히 같지 않다. CLI의 `--priority later`는 존재하고 Claude 어댑터로 전달되지만([cli.py:2333](/Users/jaesolshin/Documents/GitHub/cross-session-messaging/xsm/cli.py:2333), [adapters.py:94](/Users/jaesolshin/Documents/GitHub/cross-session-messaging/xsm/adapters.py:94)), [mcp.py:85](/Users/jaesolshin/Documents/GitHub/cross-session-messaging/xsm/mcp.py:85)의 schema와 호출에는 `priority`가 없다. Codex 전송 분기에도 이 값이 전달되지 않는다.

   **Reason의 배치와 xsm 반론.** Reason은 MCP를 데몬의 클라이언트로 두고 전달 경로 선택을 그 아래에 배치한다(R:82–85). 반면 xsm은 별도 데몬을 두지 않고 명확한 대체 경로를 안내한다고 반론할 수 있다. 실제 복구도 성공했다. 그러나 복구 성공은 이 선택 부담이 필요하다는 증거가 아니다. 참고로 제공된 Reason MCP에도 `--fyi`에 해당하는 입력은 없다. 조용히 보내기의 MCP 일관성에서 Reason이 해결을 끝냈다고 주장하지 않는다.

   **판정·철회 조건.** 경로 전환 부담과 우선순위 인터페이스 차이는 확정 사실이다. 실제 전송 경로를 에이전트가 선택하지 않아도 되고, 경로가 바뀌어도 지원하는 전달 의도가 보존되면 철회한다.

5. **자기 일로 돌아온 Codex 에이전트가 수신 확인 습관까지 유지해야 한다.**

   **행동과 부담.** 메시지를 보낸 뒤 코드를 읽고 테스트하며 원래 일을 계속한다. 그동안 온 후속 질문을 현재 턴에서 보려면 `xsm inbox`를 호출해야 한다. unread 안내는 존재하지만, 일반 작업 도구의 결과가 아니라 xsm 명령·도구 결과에 붙는다. 한동안 xsm을 부르지 않는 에이전트는 별도로 확인 시점을 기억해야 한다.

   **코드 사실.** [send.py:234](/Users/jaesolshin/Documents/GitHub/cross-session-messaging/xsm/send.py:234)는 Codex 큐와 중간 조회용 사본을 남긴다. 안내 지점은 [mcp.py:366](/Users/jaesolshin/Documents/GitHub/cross-session-messaging/xsm/mcp.py:366)과 [cli.py:2483](/Users/jaesolshin/Documents/GitHub/cross-session-messaging/xsm/cli.py:2483)이다. 가이드도 대기 전과 unread 안내 때 직접 읽으라고 요구한다(guide.md:276–285). E의 `calls[7]`에는 실제 unread 안내가 있다.

   **Reason의 배치와 반대 증거.** Reason 설계는 Codex의 `PostToolUse` 문맥 주입과 Stop 처리를 전달 계층에 배치한다(R:165). 그러나 같은 일반 Codex 세션에서 Reason은 rollout 조회 실패로 유휴 수신을 못했다. E의 `codex_same_session_binding`, `reason_daemon_error_excerpt`, `recorded_results["s6-reason-final-before-cleanup.json"]`에 따르면 정리 전 약 1,566초 시점에도 요청은 unread였고 회신은 0개였다. 반대로 xsm은 그 세션에서 회신까지 성공했다. 설계상 책임 배치와 실제 성공률을 혼동해서는 안 된다.

   **판정·철회 조건.** xsm의 중간 수신에 호출자 규율이 필요한 것은 코드 사실이다. 이번 기록만으로 장시간 미확인 빈도나 속도 열세를 주장하지 않는다. xsm을 다시 호출하지 않고 일반 작업을 계속하는 Codex 턴에서도 후속 메시지가 자연스럽게 전달되는 경로가 확인되면 철회한다.

6. **“답을 기다린다”는 일을 수신 영수증과 답변 수집 절차로 쪼갠다.**

   **행동과 부담.** 사용자가 다른 세션에 질문하고 답을 받아 달라고 한다. `--wait`가 반환해도 얻는 것은 답변이 아니라 수신 기록이다. 에이전트는 별도로 inbox를 읽고 요청 id와 답변을 연결해야 한다. 본문 외에도 `kind`, `reply_to`, 과제 종료 시 `outcome`을 관리한다.

   **실행·코드 사실.** [send.py:248](/Users/jaesolshin/Documents/GitHub/cross-session-messaging/xsm/send.py:248)과 [ledger.py:144](/Users/jaesolshin/Documents/GitHub/cross-session-messaging/xsm/ledger.py:144)는 수신 상태가 바뀌면 대기를 끝낸다. 과제 종료 상태는 별도로 저장된다. 메모리 검사에서도 답변·outcome 없는 `delivered`만으로 반환했다. 그런데 [README_ko.md:218](/Users/jaesolshin/Documents/GitHub/cross-session-messaging/README_ko.md:218)은 이를 “일 시키고 답장 기다림”이라고 설명한다. E의 S7에서 xsm CLI는 전달 JSON을 반환했고 답변은 별도 inbox 호출로 받았다. Reason CLI는 답변 본문을 출력했다.

   **Reason의 배치와 xsm 반론.** 캐시된 Reason CLI는 질문하고 답을 출력하는 명령과 기다리지 않는 `send`를 구분한다. xsm의 반론은 영수증과 업무 완료를 분리해야 정확하고, 기존 `reply_to`·`outcome`으로 에이전트가 조율할 수 있다는 것이다. 맞다. 그러나 그 사실은 답변까지 받으려는 사용 목적을 낮은 수준의 메시지 절차로 조립하게 만드는 제품 선택을 설명할 뿐이다. 실제로 E의 peer 기록에서도 xsm은 `kind/outcome`을, Reason은 해당 필드 없이 메시지와 `reply_to`를 사용했다.

   **판정·철회 조건.** README 설명과 구현의 불일치는 문서 결함이다. 영수증만 기다리는 API 자체는 제품 선택이다. 실제 답변을 기다리거나 나중에 이어받는 계약이 명확하고, 호출자가 수신함 전체에서 답을 찾아 연결하지 않아도 되는 경로가 확인되면 철회한다.

확정 가능한 결함과 제품 선택의 대가는 다음처럼 나뉜다.

| 구분 | 확정 범위 |
|---|---|
| 실행으로 확인한 결함 | 실제 비동기 승인을 수집하지 못했고, 안내된 재실행·`--reply` 복구도 실패했다. |
| 코드로 확인한 인터페이스 불일치 | CLI에 있는 우선순위를 MCP로 지정·전달할 수 없다. |
| 문서 결함 | README의 “답장 기다림”은 실제 `--wait`의 수신 기록 대기와 다르다. |
| 제품 선택의 대가 | 저장소 중심의 관계 설정, 업무 정보가 적은 디렉터리, CLI/MCP 경로 선택, Codex 중간 수신 확인, 답변 수집 절차를 호출 에이전트가 부담한다. |

이 중 어느 것도 여기서는 보안 취약점으로 판정하지 않는다. ADR-0009도 같은 uid 안의 동의 기록을 보안 경계와 구분한다. 현재 제한을 원래 철학으로 정당화할 수도 없다.

지금 손댈 우선순위는 세 가지다.

1. **비동기 승인 수집과 복구부터 고친다.** 기존 recent 기록이 있지만 해당 답변만 빠진 상태를 필수 재현 조건으로 삼아야 한다. 실제 답변을 요청에 연결하고, 추가 승인이나 상태 파일 편집 없이 보관 메시지 전송까지 끝나는지 확인해야 한다. 모든 `--reply`를 느슨하게 받자는 제안은 아니다.
2. **전송 경로·수신 시점·답변 대기를 호출자에게 덜 노출한다.** 기존 `xsm_send`, unread, `reply_to`, `outcome`을 바탕으로 경로별 기능 차이와 중간 수신 공백을 줄이고, 수신 확인과 실제 답변 대기를 명확히 구분해야 한다. 기존 inbox의 이름을 바꾸는 것으로는 해결되지 않는다.
3. **디렉터리를 업무 선택에 쓸 수 있게 하고, 위임과 관계 설정을 맞춘다.** 담당 업무·브랜치·가용 상태를 제공하고, 한 세션에 일을 맡기는 요청이 어떤 지속 범위를 여는지 예측 가능하게 해야 한다. `link`·`join`·`reach`를 새 해결책처럼 다시 소개할 문제가 아니다.

검증은 root 호출 22개, peer native 이벤트 34개, Codex native 이벤트 10개를 대조했다. 특히 직접 검토는 `peer_native_events.beta[12–14]`와 `alpha[9]`, 최종 수신 `calls[16]`으로 확인했다. 따라서 xsm의 같은 저장소 통신·후속 질문·동료 간 직접 검토 기능 부재를 주장하지 않는다. Reason의 최초 inbox 조회가 비었어도 이후 회신 기록이 있다는 점과, 동일 Codex 세션의 유휴 수신 실패도 반영했다.

지정 원시 JSON과 코드·관련 테스트만 조사했고, deliverables의 설명 보고서는 읽지 않았다. 기존 테스트는 읽었으며 전체 테스트 스위트는 실행하지 않았다. 독립 검사는 AST로 추출한 함수와 메모리 fixture로만 실행해 승인 복구 계약의 실패와 대조 조건을 확인했다. 위임·MCP 호출·송신·워커 실행·네트워크 접근·자격증명 조회·파일 및 상태 변경은 하지 않았다. 기존 cleanup 기록의 소스 31개 무변경 및 미연결 상태도 확인했으며, 새 실통신이나 연결 후 검증은 수행하지 않았다.
