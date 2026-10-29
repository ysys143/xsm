# P11 C 새 조건: bootstrap 후 SSH 차단 data-plane

**이 단일 셀은 통과했다.** private 두 node가 join·등록·양쪽 who=2 준비를 마친 뒤 bootstrap SSH를 종료했다. 이후 controller/helper/engine/native가 기존과 같은 TCP 목적지 22 차단 profile 아래에서 engine 요청 → peer 자동 pull → 실제 구독 Codex 1회 → engine 회신을 완료했다. 측정 window는 **6.984564초**, 양쪽 SSH spawn은 **0회**, 자동 모델 재시도는 **0회**다.

이는 bootstrap 이후 소유 프로세스가 SSH를 쓰지 못하는 조건의 data-plane 표본이다. SSH 없는 신규 설치·전역 네트워크 차단·모든 backend 성공·실제 사용자 팀·P12/D12 선택 완료로 확대하지 않는다. 원 실패는 별도 미검증 표본으로 그대로 유지했다.

## 새 조건에서 바꾼 것과 유지한 것

- `/bin/ps` setuid 실행 대신 SDK 구조를 검증한 비승격 `libproc.proc_pidinfo(PROC_PIDTBSDINFO)` reader로 own/등록한 owned-child PID만 읽었다. PID/UID/real UID를 검사하며 임의 peer PID 탐색은 없다.
- 실제 SDK `sys/proc_info.h`, `libproc.h`와 C 컴파일 결과: flavor 3, 구조 136 bytes, PID offset 12, UID 20, start seconds 120/useconds 128. ctypes 결과와 일치했다.
- 양쪽 helper/controller의 비제한 baseline은 **자기 PID만** `/bin/ps lstart`로 읽어 실제 libproc 시작시각과 초 단위까지 일치했다. 제한 적용 뒤에도 같은 kernel generation을 확인했다. 제한 안에서 ps를 재시도하거나 setuid를 허용하지 않았다.
- profile은 원 실패와 byte-for-byte 같은 `(version 1) (allow default) (deny network-outbound (remote tcp "*:22"))`다. network/OS/파일/IPC 권한을 추가 allow하지 않았다. 전체 호스트가 아닌 소유 프로세스와 자식에만 적용했다.
- C 0.12.10 바이너리 SHA는 `6ac4bb4837469867edc2dba3cbbd6e4dd9fb18ad0389db69ff6ef21683317a44`. 기존 private two-node/team/marker/산술 native 틀을 재사용했다. 기존 C 원본 파일과 원 실패 파일은 수정하지 않았다.
- native는 기존 C의 text-only/read-only/ephemeral Codex fixture이며 모델·allowedTools·인증 권한을 추가 보정하지 않았다. 실제 CLI는 0.163.0, 정상 구독 경로를 재사용했고 API credential 조회·복사는 없다. 기존 C의 도구 비활성화 조건도 유지했으므로 일반 TUI usability 표본이 아니다.

## 준비·차단 증거·측정·회수 구분

| 단계 (KST) | 실제 수행 |
|---|---|
| bootstrap, 08:27:47.315 이전 | 양쪽 private engine, create/join, 동일 capability/team SHA, 양쪽 who=2. cap은 메모리→SSH stdin→detached helper stdin→private engine IPC로 전달. 원문 argv/별도 파일/log 기록 없음 |
| 08:27:47.315 | bootstrap SSH exit 0 및 control 종료. 기존 사용자 SSH master/연결은 유지 |
| 차단 preflight, 측정 전 | 양쪽 실제 상대 IP의 TCP:22 connect가 **EPERM(errno 1)**. 실제 ssh는 `-S none`, `ControlMaster=no`, `ControlPath=none`으로 각각 **exit 255/권한 거부**. 이 두 의도된 SSH probe는 window 호출 수와 분리 |
| **08:28:07.245765** | 양쪽 차단 proof와 who/team readback을 engine 제어 메시지로 확인한 뒤 측정 시작 |
| 08:28:07.370055 | peer helper가 **engine inbox**에서 원 산술 요청을 발견. SSH에서 body/trigger를 받지 않음 |
| 08:28:14.160466 | peer native 종료·답의 engine 발행 완료 |
| **08:28:14.230329** | NodeA engine이 원 요청에 결속된 실제 회신 및 peer 증거를 회수, 측정 종료 |
| **08:29:07.552742 이후** | 새 사후 SSH로 own private raw와 종료 metadata만 회수. task/native trigger/응답 주입 없음 |

측정 전 local SSH spawn은 bootstrap 1회+deny probe 1회, peer는 deny probe 1회다. 측정 중 양쪽 기록된 SSH spawn **0회**이며 TCP:22 정책도 계속 유지됐다. libproc reader의 Popen 계수는 fixture의 실제 child launch 시점이며 시스템 전체 SSH 감시라고 확대하지 않는다. engine 자체도 처음부터 같은 sandbox-exec profile 아래 시작했고 native는 제한된 helper의 자식이다. 측정 후 전송 증거·peer who/team metadata도 engine으로 전달됐으며 raw만 별도 SSH로 회수했다.

## 실제 요청·모델·회신

| 축 | 값 |
|---|---|
| request engine ID | `01M62DF92GP7M1JVGZTE4MBK5F` |
| reply engine ID | `01M62DFFT3A3R88YEZRVJE6N5M` |
| reply_to | `01M62DF92GP7M1JVGZTE4MBK5F` |
| 요청 body SHA-256 | `837ccd0b9c717c72343451a35cb3aea070e1fcab5e473b4144e17e4e1656dc0e` |
| 회신 body SHA-256 | `de7656614b12b147340977a7c541a9c35bf20a0b0b76ad2b3a0f335cb5d8df92` |
| actual native PID / generation | `75449` / `unix:1793230087.392092` |
| actual native CID | `01a184d7-a6ab-7f72-a5e2-10412eff57ab` |
| native count | 1 attempt, 실제 turn.started 1 / turn.completed 1, exit 0, 모델 도구 호출 0 |
| 실제 답 | claim_valid=false, corrected_sum=4, counterexample 있음 |
| node readback | 양쪽 who=2, team=2, endpoint hash가 정확히 두 소유 node와 일치. 전후 engine link는 direct |

요청 ID SHA는 peer가 실제 받은 engine ID와, 요청 body SHA는 native에 전달한 원문과 대조했다. 회신 SHA는 실제 native JSON answer와 NodeA가 받은 engine reply body가 일치했다. 모델 응답을 주입하거나 저장 답을 만든 fixture가 아니다.

## RootMetadata의 출처와 범위

[결과 JSON](no-ssh-v2-results.json)의 `RootMetadata`는 **실제 SDK libproc 관측과 kernel connect 결과를 기록한 평가 metadata**다. Codex protocol이 반환한 `RootMetadata` 이벤트라고 표기하지 않는다.

local controller/engine, peer helper/engine의 실제 PID·UID·시작시각과 동일 profile을 묶었다. native 직전에는 작은 비승격 launcher가 자기 PID/generation·cwd와 실제 peer TCP:22 EPERM을 저장하고 **exec로 Codex에 전환**했다. exec는 PID/start를 유지한다. 이 metadata의 PID/generation은 실제 native handle과 일치하고, CID는 실제 stdout thread.started와 일치한다. launcher는 model 입력/응답을 재작성하지 않았고 새로운 권한을 주지 않았다. 상수 PID나 가짜 lstart/명령 결과를 사용하지 않았다.

## 정리

helper는 자체 deadline과 finally cleanup을 가졌으며, 이번 실행에서는 정상 종료했다. controller도 원 C cleanup을 완료했다. 사후 readback은 알려진 handle만 libproc로 조회해 동일 generation의 잔여가 없음을 확인했다.

| 역할 | PID | kernel start generation | 잔여 |
|---|---:|---|---:|
| local controller | 32952 | unix:1793230046.925707 | 0 |
| local 최초 engine | 32956 | unix:1793230047.040260 | 0 |
| local 재시작 engine | 32986 | unix:1793230048.169236 | 0 |
| peer helper | 74936 | unix:1793230063.847418 | 0 |
| peer 최초 engine | 74938 | unix:1793230063.938033 | 0 |
| peer 재시작 engine | 74993 | unix:1793230066.399695 | 0 |
| actual native | 75449 | unix:1793230087.392092 | 0 |

local IPC는 종료 직후 연결 거부(61), peer IPC는 사후 경로 없음(2)이었다. 모델 전후 기존 profile/settings/known_hosts metadata는 동일했다. 원 실패 공개 파일의 기존 manifest SHA가 모두 유지됐다. 제품 source1697·실제 권한 규칙·전역 firewall/SSH 설정·실제 Reason 팀은 수정하지 않았다.

## 산출물

- [검증 27항목·전체 결과](no-ssh-v2-results.json), [manifest](no-ssh-v2-manifest.json)
- [controller](no-ssh-v2-run.py), [자율 helper](no-ssh-v2-peer.py), [공용 fixture adapter](no-ssh-v2-lib.py)
- [SDK layout C](no-ssh-v2-proc-layout.c), [libproc reader](no-ssh-v2-proc.py)
- [native fixture 파생본](no-ssh-v2-native.py), [native pre-exec 관측](no-ssh-v2-native-launch.py)
- [사후 readback](no-ssh-v2-readback.py), [오프라인 audit](no-ssh-v2-audit.py)
- private raw local: `/private/tmp/p11-C-no-ssh-v2-local-51bqm_cj`
- private raw peer: `/private/tmp/p11-C-no-ssh-v2-peer-iorbhq2p`

전체 범위의 다른 backend/설치 조건은 이 결과에 포함하지 않는다. 원 실패와 새 조건은 합치지 않았다.
