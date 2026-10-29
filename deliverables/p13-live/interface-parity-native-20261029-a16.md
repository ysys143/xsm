# CLI/MCP parity 원 조건의 선결 실패

원 조건은 paired 검토에 도달하지 못했다. sender가 native sandbox에서 호출한 비한정 `xsm ask`는 실제 내부 종료 코드2와 `invalid choice: 'ask'`를 반환했다. 이를 감싼 Python command의 종료 코드0을 CLI 성공으로 세지 않았다. MCP ask·질문 record·자료 사본·실제 reply/ACK는 모두0이다.

**평가자가 모델 시작 전에 실제 CLI 실행파일의 고정본 source 결속을 확인하지 않은 준비 오류가 있었다.** 고정본은 ask를 지원하지만 원 실행은 전역 옛 parser를 선택했다. 원 결과·명령·출력은 보존하고 제품1697의 ask 결함이나 sandbox 권한 거절로 판정하지 않는다. 이 조건에서 재시도·경로교정·MCP 대체 전송은 없었다.

- native2, 원 실행41.907초, controller 수동send/ACK/index보정0.
- reviewer는 요청 없이 대기했고 sender는 오류 후 중단했다. 원 즉시 cleanup의 reviewer MCP alive=true는 보존했으며 사후 kernel readback에서는 native/MCP 모두 없다.
- 프로필 guard 불일치는 원인·작성자 미확정이다. profile/credential을 조사하거나 원인을 추측하지 않았다.
- 원 manifest 뒤 cleanup으로 사라지거나 바뀐 파일은 audit에 기록하고 별도 post-cleanup manifest를 만들었다. 원 manifest는 고치지 않았다.
- priority/wake/files/reply/outcome 효과·digest parity는 이 조건에서 모두 미관측이다. 본문/자료 bytes 준비를 전달 성공으로 세지 않는다.

[원 실행](interface-parity-native-20261029-a16.py) · [원 결과](interface-parity-native-20261029-a16.json) · [원 manifest](interface-parity-native-20261029-a16.manifest.json) · [offline checker](interface-parity-native-20261029-a16.audit.py) · [감사](interface-parity-native-20261029-a16.audit.json) · [post-cleanup manifest](interface-parity-native-20261029-a16.audit-manifest.json)

사용자가 별도 보정 조건 v2를 허용했다. 이는 이 실패의 모델 재시도를 숨긴 것이 아니라, CLI 실행 source 선결조건을 수정한 새 평가다. 원 표본은 계속 실패로 남는다. 제품/source/ledger/plan과 전역 PATH/profile/install은 수정하지 않았다.
