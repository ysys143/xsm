# OpenClaw owned 실행의 실제 구독 모델 검증

상태: macOS의 owned 정상/재개/문맥 분리/결과 회수 표본이다. 전체 계획은 미완이다.

## 실행 경로

OpenClaw2026.10.9, Node24.22.2, protocol Python3.14.6에서 새
HOME/OPENCLAW_STATE_DIR/XSM_HOME과 임시 workspace를 사용했다. 공개
operation.call의 xsm_owned create/run/status/reconcile, inbox claim과 ACK를
실제 native gateway 및 공통 journal에 연결했다. 부모는 generic reference
참여자이며 실제 Claude/Codex 대화를 부모로 사용한 시험이 아니다.

2026-11-03 live loopback catalog에서 anthropic/claude-sonnet-5-5를 확인했다.
`ocx config get providers.anthropic.authMode`가 oauth인 기존 구독 프록시만
사용했다. OpenAI forward나 OpenRouter 경로, API key 과금 경로는 쓰지 않았다.
사용자 설정·인증·권한을 변경하거나 API key 값을 조회하지 않았다.

SubscriptionRelay는 exact direct Anthropic 모델과 기존 OAuth mode를 확인한
뒤 최대8회의 loopback 요청만 전달한다. Ambient 인증 헤더 대신 local placeholder를
쓰며 실제 upstream 응답 byte를 바꾸거나 답을 생성하지 않는다. 본문·인증 헤더·
token을 기록하지 않고 HTTP 상태, 요청 모델, 응답 model 표기와 byte 수만 기록한다.
이 모델 표기는 프록시의 reported label이며 공급자 내부 served model의 별도
attestation이 아니다.

## 결과

| 표본 | 검사 | 실제 provider 요청 | 확인 범위 |
|---|---:|---:|---|
| openclaw-owned-subscription-first | 19/19 | 3 | 정상 실행, 이전 turn에만 제공한 token 기억, 독립 context, 회신 claim/ACK, 같은 request 재조회 |
| openclaw-owned-subscription-warm | 32/32 | 4 | 위 경로와 frontend SIGKILL 뒤 원래 native run의 결과 회수 |
| openclaw-owned-subscription-cold | 36/36 | 4 | 완료된 native run 뒤 gateway 재시작, wait receipt 유실, 원래 run transcript로 결과 회수 |

각 요청은 HTTP200이며 응답 model 표기는 선택 모델과 같았다. Replay는 원래
reply ID를 유지하고 모델을 재실행하지 않았다. Warm/cold 모두 원래 child
exit=-9를 보존하고 실제 답을 읽어 명시적으로 ACK했다. Cold는 실제 assistant
message ID와 source=native-chat.history를 기록하며 terminal receipt를 만들지
않았다. 모든 gatewayStopped=true다.

첫19개는 probe source hash 필드를 추가하기 전 표본이다. 후속 warm/cold의
probeSourceSha256은61147f3의 두 probe 파일과 일치하며 native binding hash도
보존한다. 처음 relay 단위 검사에는 HTTPError 정리를 빠뜨린 ResourceWarning이
있어 test error response를 닫도록 수정했다. 실패 assertion은 없었다.

```sh
python3 -B scripts/probe-openclaw-owned-protocol.py \
  --native-cli /isolated/native/node_modules/openclaw/openclaw.mjs \
  --node /isolated/node/bin/node --output /tmp/new-owned-model-proof \
  --subscription-model anthropic/claude-sonnet-5-5 \
  --interrupt-frontend --restart-gateway
```

`--subscription-model`을 생략하면 기존 model0 fixture다. 실제 모델 취소/오류
주입은 이 옵션에 연결하지 않았다. Relay의 실제 HTTP 경로·byte 보존·기록
redaction·한도·다른 모델 거부·non-OAuth 사전 거부 검사3개를 추가했다.
한도 검사·인증 헤더 교체·exact 모델 검사를 제거한 변이3개는 각각 assertion에서 실패했다.
핵심 gate에는 모델 없는 relay 검사만 포함한다. 기존 model0 cold probe도
별도로36/36개 통과했다(openclaw-subscription-model0-regression).

최종 모델 없는 core840개(Python503+SDK52+native133+Node152)가 macOS에서
85.890초에 통과했다(subscription-probe-core-final.log). 독립 mock39/변이14는
별도 수치다. 실제 구독 모델 시험은120초 gate 밖에서 실행했다.

61147f32b4741e522023e43e0c621910f8f2b5eb를 고정한 Linux core도840개씩
Python3.11.2에서69.427초, Python3.14.10에서88.626초에 통과했다.
Archive SHA256은eeee59ac78bfeee31fbd6b7f7458508a3d7ad86966f1c1d0703cadd6c22247bd다.
Network none/model0/cpu2/memory3g, 미실행 core0, VM stopExit=0이다.
원시는 subscription-probe-linux/ 아래다. Linux 실제 모델 실행 증거가 아니다.

## 실제 모델의 native plugin 도구 송신

별도 새 profile에서 managed plugin을 gateway 시작 전에 설치하고 그 profile의
plugins.enabled/allow/entries.xsm만 명시적으로 활성화했다. 모델이 native
xsm_send를 한 번 호출해 같은 임시 workspace의 reference 참여자에게 note를
보내도록 했다. 시험기는 직접 그 note를 생성하지 않았다. 공개 inbox에서 exact
표식 원문1개를 읽고 claim token으로 ACK했으며 owned 최종 회신도 별도로 ACK했다.

초기 prototype25/25개(openclaw-subscription-native-tools)와 재현 옵션으로
정리한25/25개(openclaw-subscription-native-tools-script)가 각각 통과했다.
각 provider 요청은5회였고 gatewayStopped=true다. Prototype의 별도 source hash와
최종 script의 probeSourceSha256/nativeBindingHashes를 각 결과에 보존했다.
두 실행은 별개 표본이며 검사 수를 합쳐 유일한50개 계약으로 주장하지 않는다.

재현은 위 명령에서 --interrupt-frontend/--restart-gateway 대신 --native-tools를
사용한다. 이 도구 표본은 frontend recovery와 별도 mode다. 실제 plugin factory,
native model tool call, 공통 송신과 canonical claim/ACK의 연결을 확인했지만
나머지21개 도구·사용자 UI·수신 push·다른 runtime/OS 행렬은 미완이다.

원시는 deliverables/protocol-foundation/의 표본별 result.json, *-journal.json,
subscription-relay.jsonl과 subscription-relay-{tests,mutants}.*에 있다.
Native auth/config 파일은 추가 수집하지 않았다.

입력 큐 p95·native plugin 도구 전체·사람 UI·메신저·실제 모델 실행 중
취소·진행 중 gateway restart lineage·Linux 실제 모델·전체 런타임/방향 행렬은
이 표본의 범위가 아니며 원래 계획의 미완 조건으로 남아 있다.
