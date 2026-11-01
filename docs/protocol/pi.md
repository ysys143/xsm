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

공통 359개는 57.057초에 통과했다(`pi-backend-recovery-gate-final.log`). 이번
복구는 정상 등록된 세션의 backend 종료를 대상으로 한다. 최초 등록 자체의
실패 재시도·유휴 중 선제 재접속·실제 모델/사람 UI·worker·Linux와 전체
P3/P5는 미완이다.
