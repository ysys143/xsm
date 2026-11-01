# Pi 1.4.0 실험 연결

상태: 개발 중. 전체 Pi 지원·릴리즈 완료를 뜻하지 않는다.

[`integrations/pi/xsm.mjs`](../../integrations/pi/xsm.mjs)는 공통 호스트 API를
사용한다. Node 22.19.0 이상이 필요한 Pi 1.4.0을 기준으로 한다.

개발 시험은 격리된 HOME, PI_CODING_AGENT_DIR, XSM_HOME에서 다음처럼 실행한다.
이는 일반 사용자 프로필을 수정하는 설치 명령이 아니다.

```sh
pi --mode rpc --no-session -e /absolute/xsm/integrations/pi/xsm.mjs
```

Pi의 기존 세션 ID와 실제 프로필 경로로 참여한다. 세션 종료·교체는 호스트
연결을 닫고, 렌더된 peer 본문이 native message_start에 들어오거나 현재 native
branch에 같은 delivery ID와 본문으로 들어온 것을 확인한 뒤 문맥 인계를 보고한다.
Idle/non-waking append는 app event만 발생시키므로 branch 관찰도 필요하다.
ACK는 모델/사용자가 실제로 읽은 뒤 xsm_ack로 보낸다.

자동 수신의 구현 기본값은 배치당 16개/512 KiB UTF-8이다. 제한된 native 경계의
나머지는 공통 SDK가 cursor를 따라 이어 읽으며 FYI의 wake=False를 유지한다.
첫 원문 자체가 예산보다 크면 자르지 않고 단독으로 받는다.

실제 SDK의 `--batch` fixture는 30만 자 원문 3개를 wake=never로 먼저 보냈다.
Native branch의 서로 다른 입력 3개를 확인하고 native 도구로 ACK 3개를 보냈다
(`pi-default-budget-batch.json`). 기본 예산을 제거하면 하나로 합쳐져 검사가
실패했다(`native-default-budget-mutants.json`). 모델 호출은 0회다.
새 owned profile의 자동 발견/snapshot 실행에서 native 수락 100/100도 통과했고
macOS p95 상한은 431.056ms였다(`pi-batch-defaults-native-100/result.json`).
이 수락 검사를 모델 작업 성공이나 실제 사용자 응답으로 해석하지 않는다.

도구 스키마는 공통 서버에서 가져온다. `/xsm status`는 공개 ref와 도구
이름을 보여주며 `/xsm <operation> <JSON>`은 같은 API의 개발용 진입점이다.
JSON 문자열 안의 공백·개행·Unicode는 바꾸지 않는다.

질문 UI는 native select/input을 사용한다. 응답은 해당 callback에서만
호스트 질문에 돌려보내고, 원 작업 재호출에서 적용 여부를 다시 검증한다.
일반 도구나 peer 본문으로 승인 답을 만들어 넣지 않는다.

## 검증 범위

- 실제 Pi 1.4.0 RPC: 도구 21개 등록, native 선택 질문과 답, 본문 진입, ACK.
- 실제 SDK 실행 커널: 도구 argument validation과 성공/오류, 질문 경로.
  issuing assistant와 UI 응답은 명시적 fixture이며 모델 실행은 0회이다.
- native 본문 진입 지연: macOS의 격리 RPC에서 100회. 결과와 코드 해시는
  `deliverables/protocol-foundation/pi-native-*/result.json`에 남긴다.

이는 21개 기능 전부의 실사용 인증이 아니다. 물리적 TUI, 실제 모델 협업,
Linux, 기존 세션 설치·reload, 갱신·제거, worker, 원격 및 다른 런타임과의
왕복은 수용 조건이 남아 있다. 자동 연결 복구도 아직 지원 완료로 쓰지 않는다.

## 개발 검증 명령

```sh
python3 scripts/check-protocol.py
python3 scripts/probe-pi-protocol.py --pi-cli /isolated/pi/dist/bundle/cli.js --output deliverables/pi-probe --samples 100
node scripts/probe-pi-sdk.mjs /isolated/pi/package-root deliverables/pi-sdk.json
node scripts/probe-pi-sdk.mjs /isolated/pi/package-root deliverables/pi-batch.json --batch
```

코드·버전이 다른 표본은 같은 결과로 합치지 않는다. 모델 미구성의 큐 관측을
실제 모델의 작업 성공이나 사람이 직접 답한 사실로 해석하지 않는다.

`probe-pi-sdk.mjs ... --notice`는 receive revalidation 실패를 격리 서버에서
주입해 claim-free notice를 만든다. 실제 native branch의 본문에 빈 ACK 안내가
없는지 확인하고, 뒤이어 정상 원문을 읽어 native 도구로 ACK한다. 최초 실행은
idle branch에 저장된 입력을 수락으로 관찰하지 못해 실패했다. 현재 branch의
delivery ID·custom type·전체 본문 확인을 추가한 뒤 통과했다.
`pi-native-notice-{first,final}.json`에 실패와 성공을 구분한다. Native SDK 실행이며
issuing assistant와 UI 답은 fixture다. 모델 호출은 0회다.

## 명시적 프로필 설치·검사·제거

```sh
xsm protocol install pi --home /explicit/pi-profile --dry-run
xsm protocol install pi --home /explicit/pi-profile
xsm protocol inspect pi --home /explicit/pi-profile
xsm protocol uninstall pi --home /explicit/pi-profile
```

설치기는 실제 프로필의 `extensions/xsm.js`만 관리한다. Pi 1.4.0의 자동
발견은 `.js`/`.ts`에 한정되므로 개발용 본체 `.mjs`를 그대로 복사하지 않는다.
로더는 완성된 xsm runtime snapshot의 본체와 공유 클라이언트를 참조한다.
Python도 설치기의 기존 pin/현재 실행 파일로 고정하며 `PYTHONPATH`나
체크아웃 CWD에 기대지 않는다. 명시적 `XSM_PYTHON` 오버라이드는 유지한다.

기존 settings·auth·다른 확장은 수정하지 않는다. 소유 기록과 정확한 내용이
맞는 로더만 갱신·제거하고, 사용자 편집·symlink·손상된 소유 기록·경로 교체는
거부한다. 사용자 파일을 이전 backup으로 되돌려 덮지 않는다.

이미 실행 중인 Pi에는 설치만으로 반영됐다고 하지 않는다. native reload나
같은 대화의 재시작/재개가 필요하다. 실행 중인 old snapshot은 남겨두고,
새 프로세스는 새 로더를 읽는다. 제거도 사용자의 실행 중인 Pi를 종료하지 않는다.

개발 검사에는 `probe-pi-protocol.py --installed`가 있다. 이 모드는 `-e`,
`PYTHONPATH`, interpreter env 오버라이드 없이 실제 자동 발견·스냅샷 실행과
설치 당시 Python 버전을 확인한다. `probe-pi-install-lifecycle.py`는 명시적인
대화 fixture로 기존 대화·문맥 보존과 갱신/재개/제거를 검사한다.

## 등록된 세션의 backend 복구

다음 도구·명령·chat 경계·상태 갱신에서 실패하거나 닫힌 host를 감지하면
기존 참여를 정리하고 같은 native 대화의 새 세대를 연다. 복구 Promise를
공유하므로 동시 진입이 중복 backend를 만들지 않는다. 실패한 작업 자체를
이 경로가 자동 재실행하지 않는다. Native 대화/workspace를 확인한 뒤에만
host를 사용하며 명령도 확인된 host를 붙잡는다.

세션 시작/종료의 epoch로 아직 끝나지 않은 복구를 무효화한다. Backend open
직후와 초기 상태 갱신 뒤에도 검사해, 그 사이 shutdown이 발생하면 새 host를
닫는다. 제어된 API/backend fixture는 동시 복구·open 중 종료·상태 갱신 중
종료·다른 native 대화 거부의 4개를 통과했다
(`pi-recovery-lifecycle-verified.log`). Epoch/등록 수명 검사를 제거한 변이는
종료 검사에 실패했다(`pi-recovery-epoch-mutant-verified.log`). 이는 제어된
fixture이며 실제 Pi queue 시험과는 구분한다.

실제 Pi 1.4.0 SDK는 원문을 claim한 backend를 종료하고 다음 native 도구 호출로
같은 주소의 새 세대에서 원문 회수·이전 claim 거부·native 도구 ACK를 확인했다
(`pi-sdk-recovery-verified.json`). 이전 commit의 연결 본문은 같은 SDK 시험에서
EOF 오류로 실패했다(`pi-backend-recovery-baseline.json`). 모델 호출은 0회다.

실제 설치 snapshot의 RPC 프로브도 `--crash`를 지원한다. 자체 backend를
종료하고 /xsm status 명령으로 재등록한 뒤 native 수락 100/100개와 RPC 명령
ACK 100/100개를 확인했다. macOS/protocol Python 3.14.6 p95 상한은 421.134ms다
(`pi-backend-recovery-verified-100/result.json`). 정본 ACK 수와 실행 코드의 해시
일치는 `pi-backend-recovery-ack-audit.json`에 별도로 기록했다. RPC 명령 ACK를
모델이 원문을 읽은 증거로 부르지 않는다. SDK 도구 ACK 표본과도 구분한다.
복구 후 native select 프로토콜의 답도 fixture가 주었으며 실제 사람 응답이 아니다.

공통 359개는 57.057초에 통과했다(`pi-backend-recovery-gate-final.log`). 위
충돌 복구 표본은 정상 등록된 세션의 backend 종료를 대상으로 한다. 최초 등록
실패의 후속 처리는 아래 절과 구분한다. 유휴 중 선제 재접속·실제 모델/사람
UI·worker·Linux와 전체 P3/P5는 미완이다.


## 최초 backend 등록 실패의 재시도

Native session_start가 대화/workspace를 확인한 뒤에는 backend 생성이 실패해도
참여 의도를 유지한다. 다음 도구·명령·chat/status 진입에서 같은 native 신원으로
등록을 다시 시도하며, 최초 도구 등록까지 끝내지 못했다면 함께 수행한다.
초기 상태 갱신 실패로 이미 열었던 host는 닫는다. 등록 시도도 공유 Promise로
관리하고 shutdown은 참여 의도를 닫으므로 그 뒤 명령이 다시 등록하지 않는다.

Backend open 실패·초기 상태 갱신 실패·실패 뒤 shutdown을 포함해 제어된 수명
검사 7개가 통과했다(`pi-bootstrap-final-tests.log`). 수정 전 open/state 실패
검사는 다음 명령에서 복구하지 못했다(`pi-bootstrap-red.log`). 고정 SDK의
registerTool은 post-bind refreshTools를 호출하므로 최초 명령에서의 동적 등록을
지원한다.

실제 Pi 1.4.0 설치본 프로브의 `--bootstrap-failure`는 임시 Python wrapper로
첫 protocol serve 실행만 실패시킨다. 그 뒤 /xsm status 재등록·21개 도구·native
선택 프로토콜·수신/명령 ACK 5회가 통과했다
(`pi-bootstrap-native-verified/result.json`). 5회는 smoke이며 100개 지연 기준의
인증으로 사용하지 않는다. 모델과 사람의 응답은 실행하지 않았다.

첫 주입은 설치 명령까지 실패시켰고, 두 번째 주입은 설치 후 환경 변수 제거로
적용되지 않아 표식 검사에서 실패했다. 두 로그를 `pi-bootstrap-native.log`와
`pi-bootstrap-native-fixed.log`에 보존했다. 수정된 프로브는 native serve에만
적용되는 wrapper를 명시적으로 유지하며 사용자 프로필·설정을 바꾸지 않는다.
공통 362개는 58.794초에 통과했다(`pi-bootstrap-gate.log`). 자동 idle 재접속과
전체 P0–P5의 나머지 수용 조건은 미완이다.

## 등록된 transport의 자동 재접속

등록된 host의 transport 실패가 관측되면 native 명령을 기다리지 않고 같은
대화/workspace에 다시 참여한다. 250ms 뒤 시작하며 연결 실패가 계속되면 대기를
두 배로 늘려 최대 5초로 제한한다. 일반 native 거부는 재접속하지 않는다.
Native 작업을 재실행하지 않고 참여와 상태만 복구한다. 세션 전환/shutdown은
타이머를 취소하고 epoch가 다른 시도는 진행하지 않는다.

제어 수명 11개는 입력 없는 복구·shutdown 취소·일반 오류 제외·두 차례 실패 후
backoff를 포함해 통과했다(`pi-auto-reconnect-verified.log`). 자동 복구를 끄거나
대기를 제거한 변이는 각각 검출됐다(`pi-reconnect-{auto,backoff}-mutant-verified.log`).
처음 제어 검사 수정은 fixture 옵션 이름을 가려 기존 초기 실패 검사가 실패했으며,
수정 후 전부 다시 확인했다(`pi-auto-reconnect-first.log`).

실제 Pi 1.4.0 설치본은 `--auto-reconnect`에서 자체 backend 종료 후 다음 native
명령 전 새 PID/세대를 관측했다. 그 뒤 수신 100개와 RPC 명령 ACK 100개가
완료됐고 macOS/protocol Python 3.14.6의 p95 상한은 433.341ms다
(`pi-auto-reconnect-native-100/result.json`). 정본 ACK 수와 현재 코드 해시도
대조했다(`pi-auto-reconnect-ack-audit.json`). UI와 ACK는 fixture가 수행하며
실제 모델/사람의 소비 증거는 아니다.

공통 375개는 58.748초에 통과했다(`pi-auto-reconnect-gate.log`). 최초 backend
생성 전 실패의 자동 재시도, 다른 runtime의 자동 재접속·worker·Linux와 전체
P0–P5의 남은 조건은 미완이다. 현재 표본은 같은 runtime snapshot이 남아 있는
등록 세션의 transport 복구를 검증했다.


## 로드된 코드의 snapshot lease

설치 snapshot의 Pi 확장은 native Pi PID·시작 시각에 결속한 pi-extension
component lease를 확보한다. Backend가 종료돼 재접속을 기다리더라도 native
확장이 쓰는 코드를 prune하지 않는다. new/resume/fork에서는 lease를 유지하고
quit/reload에서 host와 진행 중 등록을 정리한 뒤 해제한다. Checkout 직접 연결은
snapshot prune 대상이 아니므로 이 lease를 만들지 않는다.

공통 Node helper는 clients/typescript/component-lease.mjs에 두고 OpenCode의
기존 경로는 compatibility export로 유지했다. 로드된 root가 lease 위치를
결정하고 설치 소유권 기록의 runtime/home과 고정 Python을 대조한다. Runtime
정리기는 pi-extension도 유효한 component로 읽는다.

제어 검사 12개는 세 전환 모드의 lease 유지와 reload 해제를 통과했다
(`pi-component-lifecycle-all-transitions.log`). Lease 확보를 생략한 변이는
실패했다(`pi-component-lease-mutant.log`). 별도 Python prune 검사는 protocol
backend 없이 Pi lease만 있을 때 old root가 남고, PID가 죽으면 회수되는 것을
대조한다. Python 3.9.6 관련 40개도 통과했다(`pi-component-python39.log`).

실제 Pi 1.4.0에서 새 snapshot을 게시·prune해도 실행 중인 old root가 남았고,
정상 quit 뒤에는 회수됐다. 이 업데이트 표본의 수신/RPC 명령 ACK 100개와
현재 구현 해시를 확인했으며 p95 상한은 432.114ms다
(`pi-component-upgrade-native-100/result.json`, `pi-component-upgrade-ack-audit.json`).
별도 업데이트 후 binding 제거 표본에서도 old root 유지·수신/ACK 5회·quit 뒤
회수가 통과했다(`pi-component-remove-native/result.json`). 이미 로드된 확장의
파일 제거는 native reload/quit까지 실행을 중지시키는 조치가 아니다.

실제 프로브의 유지 단계에는 backend도 살아 있었으며, backend 없는 경우의
독립 원인은 Python prune 검사로 구분한다. 모델 추론·사람 UI 인증은 아니다.
공통 377개는 59.067초에 통과했다(`pi-component-gate.log`). 공통 helper를 쓰는
OpenCode 1.19.5의 수락/native ACK 5회 회귀도 통과했다
(`shared-component-opencode-native/result.json`). 전체 P0–P5 나머지는 미완이다.
