# 빈 owned ID가 조회/새 실행으로 바뀌는 경로 복구

상태: P1/P2의 부분 진척이다. 전체 계획은 미완이다.

Owned status에 빈 request_id를 주면 history로 바뀌고, run에서는 새 ID를 만들어
실행했다. 수정 전 MCP 경로 검사는2개 refusal 부재와 실제 새 journal 생성으로
3개 assertion이 실패했다(before.log). 실행기는 합성이고 실제 모델/과금은 없다.
ID를 잃은 재시도를 새 work로 해석하는 경로를 막는다.

공통 owned_service는 명시한 non-None ID를 handoff ID 검증기로 검사하고 잘못된
값을 ActionError로 거부한다. CLI 내부의 생략 None과 선택적 자동 ID는 유지한다.
공개 input schema에도 minLength1을 적용해 protocol 경로가 거부하도록 했다.
Owned model0 공개 suite는 빈 status/run ID를 각각 -32602로 거부하며 기존 history
검사에서 phantom request가 없는지 확인한다. Suite는30개에서32개 검사로 늘었다.

첫 전체 검사에서는 OpenClaw의 파생 tools.mjs가 옛 schema여서 sync 검사1개가
실패했다(core.log). 표준 generate-protocol-operations.py로 공개 schema/example와
native catalog를 재생성했고 examples는 내용 변화가 없었다. Refusal/동기화15개가
2.706초에 통과했다(focused-final.log). 이 실패를 지우거나 동기화 검사를 완화하지 않았다.

Mac core946개(Python551+외부 적합성54+SDK56+native133+Node152)와 canonical schema,
기존 mock39/변이14, v7 예제132·mutant188·양성17/음성23·annotation42·감지2개는
56.514초에 통과했다(core-final.log). 원시는
`deliverables/protocol-foundation/owned-empty-id/`다. Linux는 후속 고정 source
검증이며 실제 native/UI/모델·원격·메신저·설치와 전체 계획은 미완이다.

## 고정 source Linux 검증

c68259e8569ac48f125ece329b425176d8005b6c의 archive SHA256은
739c38e7798ebaff7644dc177c75d3258ffa5a0d1ecff6672d5d875247aa0393다.
Python3.11.2에서81.482초, Python3.14.10에서106.565초로946개 core와 canonical
schema/v7 local을 같은120초 내에 통과했다. 두 환경에서 새 owned-fixture32개와
wire/schema도 통과했다. Model0/network none/cpu2/memory3g,
미실행 case0/미실행 wire-schema0/VM stopExit0이다.
원시는 `owned-empty-id-linux/result.json`과 환경별 output이다.
전체 원래 행렬은 미완이다.
