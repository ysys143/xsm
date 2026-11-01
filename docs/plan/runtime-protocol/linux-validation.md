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
