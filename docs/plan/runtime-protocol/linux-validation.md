# Linux 공통 프로토콜 검증

상태: Linux arm64의 모델·외부 메신저 없는 공통 gate 통과. 전체 Linux native
runtime 지원이나 P5 통합 완료는 아니다.

## 실제 표본

| 항목 | 값 |
|---|---|
| 제품 소스 commit | c460a6937730ea489aa32e2863cf0506934bdae6 |
| 소스 상태 | 추적 파일 변경 없음 |
| 플랫폼 | Linux 6.8.0-64-generic, aarch64, glibc 2.36 |
| Python | 3.11.2 |
| Node | 24.22.2 |
| 검사 | 핵심 236 + Python SDK 44 + Node 110 = 390 |
| 시간 | 70.270초, 120초 기준 통과 |
| 실행 자원 | VM 2 CPU/4 GiB, container 2 CPU/3 GiB, PID 512 |
| 네트워크 | 검사 container는 none; loopback만 사용 |

원시 결과는 `deliverables/protocol-foundation/linux-tracked-core-fixed/`의
result.json, environment.json, protocol.log에 있다. Source archive SHA-256,
Docker image ID/architecture와 검사 요약을 함께 기록했다. Native 에이전트
4종의 실제 Linux 설치·모델·UI·큐 지연은 이 표본에 포함하지 않는다.

## 재사용 경로

`scripts/containers/protocol.Dockerfile`은 Node 24.22.2 bookworm-slim의 Linux
arm64 platform manifest digest를 고정한다. Python·Git·procps는 image build에서
설치하며 실제 Python/Node 버전과 완성된 image ID를 실행 결과에 기록한다.
APT 패키지 전체가 영구 고정됐다고 주장하지 않는다.

```sh
docker build --platform=linux/arm64 -t xsm-protocol-linux:node-24.22.2 \
  -f scripts/containers/protocol.Dockerfile scripts/containers
python3 scripts/check-protocol-linux.py \
  --docker-host unix:///path/to/test/docker.sock \
  --docker-config /path/to/test/docker-config \
  --shared-dir /path/visible/to/the/daemon \
  --output deliverables/linux-new-run
```

Docker endpoint와 설정 경로를 명시하며 runner는 VM을 시작하거나 전역 context를
선택하지 않는다. Shared dir는 daemon에도 같은 표기로 보이는 경로여야 한다.
Colima mount의 /var 경로를 호스트 realpath인 /private/var로 바꾸면 guest에는
없을 수 있으므로 runner는 지정 표기를 유지한다.

입력은 Git 추적 working 파일이다. 변경 여부·commit·archive hash를 기록해
미커밋 소스와 commit만 검사한 결과를 구분한다. Untracked 파일과 사용자 홈은
container에 전달하지 않는다. Credential-like 추적 파일 이름은 거부하며, 이
이름 검사가 소스의 모든 비밀을 탐지한다는 보장은 아니다. Docker client의
인증 설정은 container에 마운트하지 않는다.

검사 container는 source tar만 읽기 전용으로 받고 출력 폴더만 쓸 수 있다.
자체 이름으로 생성한 container만 제거하며 deadline은 180초다. 공통 gate의
120초 제한은 그 안에서 별도로 적용한다. 기존 출력이 있으면 거부하고 이전
result가 바뀌지 않음을 확인했다(`linux-output-preservation.json`).

## 준비 실패와 격리 확인

- 최초 Colima 생성은 긴 socket 경로로 실패했다(`linux-vm-start.log`). 별도
  Colima home을 짧은 /tmp 경로로 바꿔 시작했다(`linux-vm-start-short.log`).
- Git release archive는 .gitattributes에 따라 tests를 제외했다. 첫 실행의
  import 오류 18개는 실제 테스트 18개 실패로 세지 않는다. 후행 SDK 검사는
  전제 미충족이었다(`linux-core-run.json`, VM 공유 출력의 protocol.log).
- 추적 파일 묶음의 첫 시도는 host canonical 경로와 guest mount 표기 차이로
  container 생성이 실패했다. 테스트는 실행되지 않았다
  (`linux-tracked-core/result.json`). 수정 후 전체 390개가 통과했다.

Colima 0.9.1의 별도 HOME/COLIMA_HOME/DOCKER_CONFIG, --activate=false,
--ssh-config=false, --template=false를 사용했다. Mount는 전용 share 하나로
확인했다. 기존 기본 VM은 전후 모두 Stopped, 전역 Docker context는 colima이며
새 private context가 실제 사용자 context 목록에 추가되지 않았다. 종료 시
테스트 VM p도 Stopped로 확인했고 image/증거/cache만 보존했다
(`linux-vm-stopped.json`, `linux-vm-stop.log`).

Linux x86_64와 다른 Python 버전, native Pi/OpenCode/Hermes/OpenClaw의 전체 경로,
30개 방향·동종·원격·메신저·native worker 및 최종 native p95 행렬은 미완이다.

## OpenCode 1.19.5 native Linux arm64

실제 Linux arm64 binary·SDK·plugin 모두 1.19.5로 설치했다. Source image는 위와
같은 Node 24.22.2/ Python 3.11.2 환경이며 dependency 설치 container와 검사
container를 분리했다. 설치는 npm --ignore-scripts로 수행하고 package-lock을
기록했다. 검사 container는 network none이다.

기존 프로브는 모든 Linux를 x64로 골랐다. OS/machine별 고정 package 경로로
선택하고 모르는 플랫폼은 거부한다. 실제 npm optionalDependencies 목록과
Mac 설치본의 package 버전을 대조했다. Mapping 검사 2개와 x64 fallback 변이
검출은 native-platform-x64-fallback-mutant.json에 남겼다.

첫 native 실행은 plugin bootstrap의 dependency 대기에서 timeout이 났고 수신
표본은 0개였다(`linux-opencode-native-stage.json`, 그 stage의 output/native/).
node_modules 연결만 있고 profile package manifest/lock이 없어 재설치를 시도한
경로다. 고정 버전의 [Config dependency 준비](https://github.com/anomalyco/opencode/blob/v1.19.5/packages/opencode/src/config/config.ts)와
[Npm.install의 node_modules/lock 대조](https://github.com/anomalyco/opencode/blob/v1.19.5/packages/core/src/npm.ts)를
확인하고 준비한 manifest·lock도 시험 profile에 복사했다. 설치 검사를 무력화하거나
개발 버전으로 바꾸지 않았다. 그 뒤 offline smoke 5회가 통과했다.

최종 `linux-opencode-native-100/output/native/result.json`에서는 다음을 확인했다.

- Linux/aarch64, OpenCode 1.19.5, Python 3.11.2.
- Backend 종료 후 명시적 native 진입 전 같은 주소의 새 세대로 자동 재등록.
- 실제 native transcript 수락과 native tool ACK 100/100개.
- 복구 후 store→관측 지연 p95 상한 277.750ms로 1초 기준 통과.
- Provider는 loopback scripted assistant이며 모델 추론·사람 UI는 미실행.

Package lock, source archive hash, commit 및 tracked dirty 여부도 같은 출력에
기록했다. 이번 입력은 81a844b 기반에 프로브/검사 변경이 있는 working tree다.
수락된 연결 구현 hash는 현재 파일과 일치한다. 실패 stage와 offline 5회 결과를
지우지 않았다. 해당 표본을 모델 소비 또는 메신저 전달로 확대하지 않는다.

새 mapping 검사를 포함한 공통 392개(핵심 238, Python 44, Node 110)가 Mac의
Python 3.14.6에서 64.046초, Linux arm64의 Python 3.11.2에서 70.194초에 통과했다
(`native-platform-macos-gate.log`, `linux-platform-core/result.json`). 기본 context와
기본 VM은 유지했고 테스트 VM은 다시 Stopped로 확인했다
(`linux-native-vm-stopped.json`). Pi/Hermes/OpenClaw의 Linux native 검증, x86_64,
다른 Python·원격·전체 방향·모델/메신저·worker와 전체 P0–P5는 미완이다.

## Pi 1.4.0 native Linux arm64

같은 Linux arm64 image에서 Pi 1.4.0을 고정해 실행했다. Dependency 준비는 별도
network-enabled container에서 npm --ignore-scripts로 하고, 검사 container는
network none으로 분리했다. Package lock과 archive hash를 보존했다.


실제 RPC 실행 결과(`linux-pi-native-100/output/native/result.json`):

- Linux arm64, Node 24.22.2, Python 3.11.2, Pi CLI 1.4.0.
- 설치 profile 자동 발견과 immutable runtime 실행 확인.
- Backend 종료 후 native 진입 전 같은 ref·새 PID/세대로 자동 재접속.
- Snapshot 업데이트와 binding 제거 뒤에도 로드된 old runtime 보존, quit 뒤 회수.
- 실제 native 수락 100/100개와 RPC 명령 ACK 100/100개.
- 복구 후 store→관측 p95 상한 215.806ms, 1초 기준 통과.
- Native select 프로토콜도 driver가 응답한 fixture이며 실제 사람의 승인이 아니다.

`ack-audit.json`은 native stdout의 명령 ACK 100개가 모든 수신 ID와 일치하고,
현재 Pi/shared lease 구현 hash도 일치하는 것을 확인한다. 원시 source는
68e75f6의 변경 없는 추적 파일이다. 이 숫자를 모델이 원문을 읽은 증거로 쓰지
않으며 outage 전체 구간 지연 인증으로도 쓰지 않는다.

별도 실제 SDK의 nested tool 실행 kernel에서도 원문을 claim한 backend를 종료한
뒤 회수·이전 token 거부·새 native 도구 ACK가 통과했다
(`linux-pi-sdk/sdk-recovery.json`). 이 도구 ACK 표본과 RPC 명령 ACK 100개는
구분한다. 큰 FYI 3개가 별도 native 입력으로 나뉘고 도구 ACK 3개가 완료되는
회귀도 통과했다(`linux-pi-sdk/sdk-batch.json`). 두 SDK 표본 모두 모델 호출은
0회이며 assistant 메시지·UI 답은 명시적 fixture다.

이번 검증에는 제품/프로브 수정이 필요하지 않았다. 공통 gate는 이전 392개
결과를 재실행으로 보고하지 않는다. 테스트 VM은 작업 후 Stopped, 기본 VM과
전역 context도 이전 상태로 확인했다(`linux-pi-vm-stopped.json`). Hermes/OpenClaw의
Linux native 검증·x86_64·실제 모델/사람 UI·worker·원격/메신저·전체 방향 행렬과
P0–P5의 나머지는 미완이다.

## OpenClaw 2026.10.9 native Linux arm64

Node 24.22.2/Python 3.11.2의 격리 Linux arm64 container에서 고정 native
SDK와 prompt helper를 실행했다. 설치 단계와 분리해 검사 network는 none이다.
실제 agent turn·모델·사람 UI·메신저는 실행하지 않았다.

최초 100건 실행은 67건 수락·ACK 뒤 timeout, 진단 실행은 1건 수락 뒤
ACK token 오류로 실패했다. 원시 로그를 보존했다. Native commit 직후
consumer가 큐를 비우면 producer의 재조회가 수락을 놓치고 claim을 반환하는
경로를 단위 검사에서 재현했다. Committed snapshot 검증으로 수정한 뒤:

- `node --test clients/tests/test_openclaw_context_queue.mjs`: 19/19 통과.
  즉시 소비 검사는 수정 전 실패했고, 다른 SID 반환 거부와 null fallback도 검사했다.
- `linux-openclaw-commit-native-100/output/native-queue-100.json`: 100/100
  수락·prompt 소비·명시적 ACK, p95 상한 406.116ms.
- `openclaw-commit-macos-native-100.json`: 같은 100/100, p95 상한 513.468ms.
- `linux-openclaw-regressions/output/deny.json`, `capacity-fyi.json`: 정책 거부와
  capacity claim 반환·자동 retry·FYI 자연 경계 retry 통과.
- 같은 폴더의 `burst.json`: 32건 중 10건 prompt 관측 후 ACK token 오류.
  ACK 뒤 갱신하는 consumed counter 0을 실제 관측 0으로 해석하지 않는다.
- `linux-openclaw-burst-diagnosed/output/burst.json` 및
  `linux-openclaw-burst-no-delay/output/burst.json`: 재실행 각각 32/32 수락·ACK.
  후자는 성공 경로에 진단 파일 읽기를 넣지 않았다. 앞선 간헐적 ACK 실패의
  원인은 미확정이며, 재실행 통과로 해결됐다고 판정하지 않는다.

공통 gate 395개(핵심 238/Python 44/Node 113)가 Mac 63.582초
(`openclaw-commit-macos-gate-final.log`), Linux 70.547초
(`linux-openclaw-core/result.json`)에 통과했다. 원시 자료는 모두
`deliverables/protocol-foundation/` 아래 있다. Burst 지연은 소비를 고의로
미룬 표본이므로 정상 부하 p95 인증에서 제외한다. Hermes Linux native,
x86_64, 실제 모델/사람 UI, worker, 원격·전체 방향·메신저 및 P0–P5는 미완이다.

### Burst 추가 재현과 진단 보강

`928e82c`의 제품 구현을 사용한 macOS arm64 32건 burst를 5회 반복해
160/160 원문 소비·ACK가 통과했다
(`openclaw-burst-repeat-928e82c/run-1.json`부터 `run-5.json`). 앞선 Linux
실패를 해소하는 증거는 아니다. 1–4회는 기존 프로브, 5회는 아래 진단
변경을 포함한 프로브이며 제품 구현은 같다.

프로브는 이제 native logger의 전달 오류를 `nativeDeliveryErrors`에 보존한다.
ACK 실패 뒤 정본에서 읽은 상태는 `claimAuditAfterAckFailure`로 기록한다.
다중 token ACK는 일부 token을 먼저 처리했을 수 있으므로 이 조회를
ACK 이전 상태나 원자적 실패의 증거로 해석하지 않는다. 성공 경로에는
정본 진단 읽기를 넣지 않는다.

`openclaw-error-capture-injected.json`에서는 임시 프로브에만 native commit
실패를 주입했다. 실행은 의도대로 exit 1/status failed였고
`nativeDeliveryErrors`에 `xsm: injected-native-commit-failure`가 남았다.
임시 주입 스크립트는 제거했다. 정책 거부 회귀
(`openclaw-native-error-capture.json`)와 최종 burst는 정상 통과하고
해당 오류 배열은 비어 있었다. 제품·사용자 설정은 이 주입으로 바꾸지 않았다.

Linux에서도 변경 없는 `cb403aa`로 32건 burst 5회를 추가 실행했다
(`linux-openclaw-burst-repeat-cb403aa/run-{1..5}/output/burst.json`). 모두
32/32 소비·ACK, 총 160/160이며 native 전달 오류는 없었다. 다섯 stage의
source archive SHA-256이 같고 tracked dirty는 false다. `summary.json`에
이를 대조한 집계를 남겼다. 기존 간헐적 실패는 이 표본에서 재현되지
않았으며 해결 판정은 계속 미결이다. 검사 전용 VM은 다시 Stopped로
확인했다(`vm-stopped.json`). 모델·실제 사람·메신저 호출은 0회다.

## SDK initialize 기한의 Linux 검증

변경 없는 `1c90ac7`을 대상으로 격리 Linux arm64/Python 3.11.2/
Node 24.22.2에서 공통 gate 401개(핵심 238/Python 47/Node 116)가
71.523초에 통과했다. 120초 기준을 충족했다. 결과는
`linux-initialize-timeout-core/result.json`과 `protocol.log`에 있고 source
archive SHA-256·image ID·network none·tracked dirty false도 기록했다.
무응답 initialize의 timeout·자식 회수와 native host 옵션 전달 검사까지
실행한 결과이며, 일반 작업 전체 기한이나 Hermes native 실행의 증거는
아니다. 이 변경의 Mac gate는 66.503초였다. 전체 P0–P5는 미완이다.

## Host 등록 전체 예산의 Linux 검증

변경 없는 `245734c`의 격리 Linux arm64/Python 3.11.2/Node 24.22.2에서
공통 gate 403개(핵심 238/Python 48/Node 117)가 75.700초에 통과했다.
`linux-host-setup-timeout-core/result.json`과 `protocol.log`에 결과·source
archive SHA-256·image ID·network none·tracked dirty false를 보존했다.
세 등록 RPC의 무응답·회수, 개별 응답은 빠르지만 합이 기한을 넘는 경로와
잘못된 기한의 spawn 전 거부를 포함한다. Mac은 동일한 403개가 69.910초에
통과했다. 실제 사용자 UI·모델·메신저 검증을 뜻하지 않는다. 기본 context는
colima, 기본 VM은 Stopped를 유지했다. P0–P5 전체는 미완이다.

## OpenClaw 자동 transport 복구의 Linux native 검증

변경 없는 `87a52d0`을 고정 OpenClaw 2026.10.9/Linux arm64/Node
24.22.2/Python 3.11.2에서 실행했다. Backend를 종료한 뒤 새 native 도구
호출 없이 같은 ref·새 PID·새 generation을 관측했다. 이어 큰 원문
100/100 수락·prompt helper 소비·명시적 ACK가 통과했고, 복구 후 전송
p95 상한은 409.313ms였다
(`linux-openclaw-auto-reconnect-native-100/output/native-queue-100.json`).
Stage에는 source commit·archive SHA-256·tracked dirty false를 보존했다.
예상한 종료 EOF 진단 1건도 남았다. 검사 network는 none이고, 모델·사람·
실제 agent turn·메신저 호출은 0회다. 이 표본은 outage 전체 지연이나
종료 전 claim·기존 queue token 회수, 간헐적 burst ACK 실패 해결의
증거가 아니다. 전체 계획은 미완이다.

동일한 변경 없는 `87a52d0`의 공통 gate 409개(핵심 238/Python 48/Node
123)도 79.712초에 통과했다
(`linux-openclaw-auto-reconnect-core/result.json`, `protocol.log`). 테스트
전용 VM의 종료 상태는 같은 폴더 `vm-stopped.json`에 기록했다.

## 종료 전 claim의 token 재조회

변경 없는 `896e4ef`를 고정 OpenClaw 2026.10.9/Linux arm64/Node
24.22.2/Python 3.11.2에서 실행했다. 종료 전에 큰 원문이 native 큐에
수락된 뒤 backend를 종료했다. 자동 재등록 후 기존 큐 본문·ID 보존,
이전 token 거부, 일반 inbox의 소유 claim 제외, message_ids로 현재
token 조회, 명시적 ACK 및 중복 prompt 소비 없음이 통과했다
(`linux-openclaw-owned-claim-recovery/output/claimed-recovery.json`).
모델·실제 agent turn·사람·메신저는 0회다.

같은 변경 없는 커밋의 공통 gate 413개(핵심 242/Python 48/Node 123)가
81.337초에 통과했다(`linux-inbox-owned-token-core/result.json`). 네트워크
none·source archive hash·image ID·tracked dirty false를 기록했고 VM은
다시 Stopped로 확인했다(`vm-stopped.json`). 이후 추가한 외부 검사기
확장까지 포함하는 Linux gate 표본은 아니다. 간헐적 burst ACK 실패와
전체 계획은 여전히 미완이다.

## OpenClaw agent_end hook의 Linux 복구

변경 없는 `2f7ac31`을 고정 OpenClaw 2026.10.9/Linux arm64/Node
24.22.2/Python 3.11.2에서 실행했다. Backend 종료 직후 실제 native
hook runner의 agent_end를 호출해 같은 ref·새 PID·새 generation의
재등록과 idle 복원을 확인했다. 이어 큰 원문 100/100 수락·prompt 소비·
명시적 ACK가 통과했고 복구 후 전송 p95 상한은 412.499ms였다
(`linux-openclaw-agent-end-native-100/output/boundary-recovery.json`).
Source archive hash·commit·tracked dirty false도 stage에 보존했다.
모델·실제 agent turn·사람·메신저는 0회다. 실제 모델 turn 종료와
outage 전체 지연의 인증으로 확대하지 않는다.

같은 커밋의 공통 gate 416개(핵심 243/Python 48/Node 125)는
82.241초에 통과했다(`linux-openclaw-agent-end-core/result.json`). 외부
targeted token 검사기 확장과 agent_end 회귀까지 포함한 Linux 표본이다.
Network none·image ID·source archive hash·tracked dirty false를 기록했고
테스트 VM은 다시 Stopped로 확인했다(`vm-stopped.json`). 전체 계획은
계속 미완이다.

## Hermes 0.22.5 native Linux arm64

고정 소스 v0.22.5/commit `bf0203a794a07aac3ff764972ab9087baa4e4f4e`의
PluginContext·registry·주입 함수 본문을 Linux arm64에서 실행했다. Python
3.14.10/glibc 2.41이며, 준비 단계에서 조회한 공식 Python image를 digest로
고정했다. 기존 Mac 검증 환경에서 읽은 정확한 dependency 67개를 wheel로
설치했다. Hermes 자체는 고정 source를 import하며 git tag·tracked clean을
대조했다. Git 설정·hook·자격 증명은 복사하지 않았고 tag/objects/index만
검증용으로 보존했다. Image digest·requirements·source archive hash·build
로그는 `linux-hermes-prepare/` 아래 있다. 검사는 network none이다.

`linux-hermes-native/output/tools/result.json`의 13개가 통과했다. 실제
PluginContext의 21개 도구 등록, 별도 세션/workspace, native 도구 dispatch의
DM pull·명시적 ACK, backend 종료 후 native 진입 전 자동 재등록, 같은
ref·새 세대 복구, workspace 이동, turn end와 finalize/resume 구분,
UI 없는 승인 거부, 설치 제거 후 로드된 snapshot 보존, unload 뒤 lease
회수와 운영자 설정 보존을 포함한다. 제품 코드는 변경하지 않았다.

`linux-hermes-native/output/injection/result.json`의 실제 주입 API 관측
9개도 통과했다. Policy 거부·matching TUI key의 busy queue·기존 transport
보존·unknown key 거부/별도 gateway scheduling·classic CLI queue·중복 요청의
true 반환·같은 key의 첫 TUI 선택을 확인했다. Session 행과 method namespace는
명시적 fixture다. 실제 TUI/agent/model을 실행한 검사가 아니며, gateway의
성공 반환을 TUI 큐 삽입과 동일시하지 않는다. 이 관측만으로 제품의 native
push·idle wake·profile별 안전한 routing·queue p95를 인증하지 않는다.

같은 Python image에 검증된 digest의 Node 24.22.2 실행 파일을 추가한
Linux 공통 gate 416개(핵심 243/Python 48/Node 125)가 100.502초에
통과했다(`linux-python-314-hermes-core/result.json`). 변경 없는
`3b47940`의 소스이며 120초 기준을 충족했다. Image ID·source hash·tracked
dirty false·network none도 기록했다. 모델·사람 UI·메신저 호출은 모두
0회다. 실제 native queue 100표본 p95·worker·전체 방향/원격·버전과
플랫폼 전체 및 P0–P5는 계속 미완이다.

별도 native `--slow-registration` 실행의 8개도 통과했다
(`linux-hermes-slow-registration/output/result/result.json`). 실제 registry
dispatch에서 다른 대화의 backend 등록을 막아 둬도 정상 대화의 도구
실행이 진행되는 경로를 포함한다. 앞선 13개와 중복 항목이 있어 고유
검사 30개로 합산하지 않는다. 테스트 전용 VM은 다시 Stopped로 확인했다
(`linux-python-314-hermes-core/vm-stopped.json`).

## OpenClaw owned 설치 수명의 Linux 검증

변경 없는 `f5aaee3`을 고정 OpenClaw 2026.10.9/Linux arm64/Node
24.22.2/Python 3.11.2에서 실행했다. Explicit load path 없이 state의
extensions/xsm을 자동 발견하고 실제 도구·DM pull/ACK를 실행했다.
업데이트·설치 파일 제거 뒤에도 기존 plugin을 재개했고, backend가
없는 상태에서 prune해도 로드된 snapshot이 보존됐다. Native unload 후
lease 제거와 old root 회수까지 통과했다
(`linux-openclaw-owned-install/output/installed-lifecycle.json`).

로컬 plugin의 native provenance가 없다는 record-missing 경고 1건을
그대로 보존했다. 설치기는 trust record·allowlist를 쓰지 않았으며,
검증 fixture에서만 명시적으로 로딩을 허용했다. 모델·실제 agent turn·
사람 UI·메신저는 0회다. Owned loader를 통한 native queue/UI 인증으로
확대하지 않는다.

같은 커밋의 공통 gate 424개(핵심 251/Python 48/Node 125)는
82.964초에 통과했다(`linux-openclaw-owned-install-core/result.json`).
Source archive hash·image ID·tracked dirty false·network none을 기록했다.
테스트 VM은 다시 Stopped로 확인했다(`vm-stopped.json`). Owned queue/UI·
간헐적 burst ACK 실패와 전체 계획은 계속 미완이다.

## 설치 loader를 통한 native queue

변경 없는 `8bfc698`의 `--installed-queue 100 --large-context`를 고정
OpenClaw 2026.10.9/Linux arm64/Node 24.22.2/Python 3.11.2에서 실행했다.
실제 설치 loader와 manifest는 바꾸지 않고 global discovery로 로드했다.
별도 SDK runtime은 fixture 세션 준비·queue 관측에만 사용했다.

큰 원문 100/100 수락·prompt 소비·명시적 ACK와 p95 상한 403.083ms가
통과했다(`linux-openclaw-owned-queue-native-100/output/owned-queue-100.json`).
업데이트·설치 파일 제거 후에도 로드된 plugin이 전달을 계속했고,
backend 없는 snapshot 보존과 unload 뒤 회수도 통과했다. Source hash·
commit·tracked dirty false·network none을 보존했다. 모델·실제 agent
turn·사람 UI·메신저는 0회이며 record-missing 경고는 유지한다.

테스트 VM은 다시 Stopped로 확인했다(`vm-stopped.json`). 제품 코드
변경 없는 프로브 검증이므로 기존 공통 gate를 새 결과로 재집계하지
않았다. Owned queue의 오류/정책 전체·UI·간헐적 burst ACK 실패와
전체 계획은 계속 미완이다.

## Owned OpenClaw의 정책·용량·FYI·burst

변경 없는 `ce9b250`으로 고정 Linux arm64 SDK에서 네 실행을 각각
격리했다(`linux-openclaw-owned-policy-regressions/{deny,capacity,fyi,burst}/
output/result.json`). Native 설치 loader/manifest는 그대로 두고 별도
SDK runtime으로 fixture 세션과 용량 예약 행을 준비했다. Injection
거부의 pull/ACK와 비어 있는 큐, 용량/FYI의 claim 반환 후 새 메시지
없는 재수락/ACK, 32건 burst의 32/32 소비/ACK가 모두 통과했다.
Burst는 16묶음/96조각이며 지연을 의도한 표본이므로 정상 p95 인증이
아니다. 앞선 간헐적 ACK 실패가 이번에는 재현되지 않았을 뿐, 해결
판정은 하지 않는다.

네 source archive hash가 같고 tracked dirty는 모두 false다. 검사
network는 none, 모델·실제 agent turn·사람 UI·메신저는 0회다. 각
실행의 source/image 증거와 summary.json을 보존했다. 테스트 VM은
다시 Stopped로 확인했다(`vm-stopped.json`). 제품 변경이 없는 프로브
검증이므로 공통 gate는 재실행하지 않았다. 오류/정책 전체·UI·나머지
전체 계획은 미완이다.

## 내부 요청 오류의 두 Python 검증

변경 없는 `b08463e`의 공통 gate 429개(핵심 254/Python 49/Node
126)가 Linux arm64의 Python 3.11.2에서 85.369초, Python 3.14.10에서
102.503초에 통과했다(`linux-protocol-internal-error-core/result.json`,
`linux-python-314-internal-error-core/result.json`). 두 source archive
hash가 같고 tracked dirty false이며 network none이다. 실제 SDK와
stdio 서버의 claim 후 오류·현재 token 회수·명시적 ACK·같은 연결
유지 검사도 포함했다. 뒤따른 팀 서비스 추출 전 표본으로 구분한다.
테스트 VM은 Stopped로 확인했다.
