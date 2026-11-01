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
