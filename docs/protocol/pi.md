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
연결을 닫고, 렌더된 peer 본문이 native message_start에 들어온 뒤에만
문맥 인계를 보고한다. ACK는 모델/사용자가 실제로 읽은 뒤 xsm_ack로 보낸다.

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
```

코드·버전이 다른 표본은 같은 결과로 합치지 않는다. 모델 미구성의 큐 관측을
실제 모델의 작업 성공이나 사람이 직접 답한 사실로 해석하지 않는다.
