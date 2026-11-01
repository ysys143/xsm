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
