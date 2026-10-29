# parity runtime 구성 대조 — A18-02 표본 한계

MCP와 native hook을 같은 고정본으로 볼 수 없다. child MCP argv/cwd/PYTHONPATH는 평가 고정본이고 XSM_HOME는 private state다. native hook은 고정본으로 교체하지 않은 기존 profile/plugin 구성이다.

## 관측한 경로와 hash

| 파일 | 설치본 SHA | 고정본 SHA | 동일 |
|---|---|---|---|
| hooks/codex-hooks.json | b972a24035252a9a56c1bc315549dd37b3b066c4865335625e4246cbf90a550b | b972a24035252a9a56c1bc315549dd37b3b066c4865335625e4246cbf90a550b | True |
| hooks/xsm-hook | b5d01706b7b2d0b0dc1ad0094c8a7211c730b4c5d34fb8dd1be6beea571f547c | b5d01706b7b2d0b0dc1ad0094c8a7211c730b4c5d34fb8dd1be6beea571f547c | True |
| hooks/xsm-hook.py | c94bf31c8e282e8745c3666e6de6186098bd5737bc4ad87676837c8f7328df92 | c94bf31c8e282e8745c3666e6de6186098bd5737bc4ad87676837c8f7328df92 | True |
| xsm/receive.py | e9f1989bdec12fb46ff4c40fbd15aabc11b12027dc4a8d0239deeeb6af9e4e63 | f0844cf0dde52979fb2361a7501fa9be8dd554b8052cac2acd56e3347a7add94 | False |
| xsm/registry.py | 4e6bc101aad4c2728d23f31165d7da17551281aff8983c693b60564c87adafd4 | edce2c6e75ec4d1803f402db565900080be337b2727a40ff663376c355890360 | False |
| xsm/inbox.py | 6830e2ac637a594e61a39e9fdf92a6bd74e1f2a0f85955d0a8b522839d963f67 | 299b972ff4fadd91148e495357be10a97ac2640d23d79c317e0b675699541695 | False |
| xsm/paths.py | 242b8e64b5d564e503d5e0bbef1d7e8d160690e8bd5199bc160523969835bb39 | 242b8e64b5d564e503d5e0bbef1d7e8d160690e8bd5199bc160523969835bb39 | True |

설치 plugin root는 `/Users/jaesolshin/.codex-3/plugins/cache/xsm/xsm/0.4.20`, 고정본은 `/private/tmp/xsm-doctor-privacy-frozen-47o6orah`다. hook launcher는 자체 root를 계산하며 xsm-hook.py가 그 plugin root를 sys.path 첫 자리에 넣는다. 따라서 MCP의 frozen PYTHONPATH가 native hook 구현까지 동일하게 만들지는 않는다. profile hooks.json에는 별도 `~/.reason/bin/reason-network hook codex ...` 명령도 있다. 실제 명령·config/hash는 JSON에 수록했다. 실행 당시 profile config/hooks guard hash와 현재 hash는 같지만 설치 내부 모듈의 당시 hash를 전부 캡처한 것은 아니므로 현재 경로 해석과 실행시 import provenance를 구분한다.

## namespace와 hook 실행 증거

host CLI는 `/private/tmp/persistent-parity-v3-host-9xxw5alo/state`를 명시했다. 기존 host exec에는 XSM_HOME가 없고 hook/paths의 기본은 `~/.xsm`이므로 두 namespace는 다르다. daemon의 실제 hook 환경을 직접 캡처하지는 않았다. host의 늦은 native reply developer context에는 sender/발송기록을 찾지 못한 unchecked 경고와 기존 plugin 명령이 있고 private override가 없다. 이는 namespace 차이와 부합하지만 daemon 환경의 직접 증명은 아니다.

수신 TUI의 기존 네 queued request에는 private XSM_HOME 및 plugin 경로를 포함한 xsm developer context가 보존돼 있어 hook 산출물 근거가 있다. 반면 child의 늦은 reply 직후 보존 구간에는 queued role-user 입력, harness 중단 알림과 19ms 뒤 turn_aborted만 있다. hook 실행 기록/xsm 추가문맥은 미관측이다. 이를 hook이 실행되지 않았다는 증명으로 바꾸지 않는다. host late reply의 xsm unchecked 경고는 별도 관측이다.

## 한계

같은 답의 native 재등장은 확인됐지만 업무 재실행·추가 모델 추론·중단 주체는 unknown이다. collector post-exit PID assertion은 분리한다. 이 표본은 frozen MCP와 기존 native hook이 혼재하므로 A18-02의 모든 경로가 동일 frozen 구현이었다는 보증으로 사용할 수 없다. 제품 전체 결함·해결 정책은 판정하지 않았다.

원 native JSONL/canonical/보고서/private raw는 기존 manifest SHA와 대조했으며 변경하지 않았다. credential 파일 읽기0, hook/제품 실행0, 모델0, 전역설정 변경0. 새 JSON/MD 두 파일만 작성했다. 원 증거 SHA는 JSON에 있다.
