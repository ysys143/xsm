# 팀 소통 구현 진행 기록

[구현 계획](team-implementation-plan.md)의 단계별 결과. 결정에서 따라오지 않는 세부를 구현 중에 정한 것은 "구현 시 택한 기본값"으로 적는다. 이 값들은 사용자 확인 전이며 0.5.1 릴리스 전에 확인받는다.

| 단계 | 상태 | 커밋 |
|---|---|---|
| T0 결함 수정 | 구현·단위 검증 완료, 원인 일부 미확정 | (이 커밋) |
| T1 다중 수신 send | 대기 | |
| T2 다중 수신 ask | 대기 | |
| T3 팀 | 대기 | |
| T4 connect 통합 | 대기 | |
| T5 doc 보드 | 대기 | |
| T6 결재 기록 | 대기 | |
| T7 보드 알림 | 대기 | |
| T8 인수인계 | 대기 | |
| T9 S12 재실험 | 대기 | |
| T10 스킬·문서 | 대기 | |
| T11 channel 제거 | 대기 | |

## T0

**ack 토큰 형식.** 수신 안내는 claim 객체를 보여 주며 "이 토큰으로 xsm_ack"라고 했지만, CLI와 MCP는 32자리 토큰 값만 받았다. `receive.claim_token`이 토큰 값, claim 객체, 그 JSON 문자열을 모두 받아 토큰을 꺼낸다(`ack_inbox`, `release_inbox`). 안내 문구는 `xsm_ack(tokens=[...])`와 `xsm ack <token>`의 정확한 형태를 보여 준다. MCP `xsm_ack`도 객체를 받는다. 검증: `tests/test_handoff_consumer.py::AckTokenFormTest` 4건, 수정 전 코드에서 실패 1·오류 2.

**MCP "hook record 없음".** 재현 조사로 확인한 것:
- 실패한 세션(`codex-worker-2`)과 같은 데몬의 다른 세션(`성과 요약하기`) 모두 등록 기록에 권한 모드가 없다(`mode: None`). 훅이 아닌 경로(CLI 자기 등록 또는 MCP 넘겨받기)로 등록됐다.
- 데몬과 MCP 서버의 `CODEX_HOME`은 `.codex-3`로 맞다. "서버가 자기 홈을 잘못 안다"는 가설은 틀렸다.
- 그 스레드는 지금 `.codex-3` 상태 DB에 있고 넘겨받기 조건도 충족한다. 실패 당시에는 스레드가 막 생겨 상태 DB에 행이 없었거나, 같은 데몬의 다른 기록이 끝난 상태였을 가능성이 있으나 재현하지 못했다.

원인을 확정하지 못했으므로 이번에는 진단을 고쳤다. MCP 거부 문구가 호출이 지명한 Codex 스레드와 호출자 조회가 끝난 근거를 싣는다(이전에는 서버 환경에 스레드 ID가 없어 Claude용 일반 문구 "no hook record for it"가 나왔다). 검증: `tests/test_mcp_identity.py::UnresolvedCodexCallTest`, 수정 전 실패. 다음에 같은 거부가 나오면 그 문구의 "caller lookup" 근거로 원인을 확정한다. 이 항목은 원인 미확정으로 남긴다.
