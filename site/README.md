# XSM 데모·문서 웹사이트

pen 시안: [디자인 브리프](../docs/design/xsm-demo/spec.md). 구현 기록: [요구사항과 검증](../docs/design/xsm-demo/implementation.md).

## 로컬 실행

저장소 루트에서 실행한다. 패키지 설치나 빌드는 필요하지 않다.

```sh
node site/serve.mjs
```

터미널에 출력되는 `http://127.0.0.1:<port>/`를 연다. 포트를 고정하려면 `node site/serve.mjs 4173`처럼 지정한다. 미리보기를 끝내려면 실행한 터미널에서 Ctrl+C로 종료한다. 이번 검증에는 Node.js 24.19.0을 사용했다.

## 시연과 문서

- 시연은 팀 구성, 직접 협업, Fable의 장기 계획·진척 관리, 복수 팀 조율의 네 장면이다. 한 번 재생한 뒤 끝에서 멈추며, 장면 선택·정지·다시 보기를 제공한다.
- 문서는 시작하기, 팀 구성, DM, 팀 보드, 계획·진척, 복수 팀, 인수인계, 런타임 지원의 8개 주제다. 장면에서 해당 문서를 열고, 문서에서 같은 장면을 다시 보거나 크게 볼 수 있다.
- 정지한 상태에서 장면이나 문서로 이동해도 재생을 시작하지 않는다. 동작 줄이기 설정에서는 전체 내용을 표시한 정지 화면으로 시작한다.
- 좁은 화면에서는 팀장·워커·보드로 나눠 읽는다. 탭은 방향키와 Home·End로 조작할 수 있다. 장면 전체 대화도 텍스트로 읽을 수 있다.
- 설치·협업 요청 문장을 복사할 수 있다. 자동 복사가 거부되면 선택된 문장을 직접 복사하는 창을 제공한다.

다음처럼 URL에서 장면이나 문서를 바로 열 수 있다. 하위 경로에 정적 배포해도 상대 경로로 자산을 불러온다.

```text
#demo/progress
#demo/teams?focus=board
#guide/start
#guide/progress?section=progress-1
```

상단에는 지원 런타임 6종을 표시한다. 주 시연은 Claude Code·Codex를 재현하며, Pi·OpenCode·Hermes·OpenClaw는 0.6.0의 실험적 지원 범위를 문서에서 설명한다. 대화와 진행 수치는 예시 시나리오다. 웹페이지에서 실제 모델을 호출하거나 XSM 세션을 생성하지 않는다.

## 검증

재생 상태, 문서 연결 데이터, 로컬 자산과 HTTP 제공을 Node 기본 검사기로 확인한다.

```sh
node --test site/tests/player.test.mjs site/tests/site.test.mjs
node site/tests/red-pause.mjs
```

두 번째 명령은 임시 복사본에서 정지 처리를 제거하고, 관련 검사가 실제로 실패하는지 확인한다. 원본은 바꾸지 않는다.

전체 브라우저 검사는 `ego-browser`의 소유 중인 작업 공간 ID를 지정해 실행한다. 로컬 시험 서버는 검사기가 열고 닫는다.

```sh
node site/tests/verify.mjs --space <space-id>
```

이 검사는 실제 Chromium에서 재생·문서 이동·뒤로가기·키보드를 조작하고, 실제 페이지를 폭 390px·320px의 같은 출처 프레임에 열어 반응형 동작을 확인한다. 복사 검사는 OS 클립보드를 바꾸지 않도록 Clipboard API 경계에서 전달 문장과 실패 처리를 확인한다. 결과·화면·입력 파일 해시는 `deliverables/xsm-demo-web-20261105/verified/`에 기록한다.

## 정적 배포용 파일

`index.html`, `styles.css`, `app.mjs`, `player.mjs`, `content.mjs`, `favicon.svg`, `assets/`를 같은 경로 구조로 정적 호스팅하면 된다. `.mjs`는 JavaScript MIME 타입으로 제공한다. `serve.mjs`와 `tests/`는 개발·검증용이다. 공개 배포는 이 작업에서 실행하지 않았다.

Archivo 글꼴을 로컬 자산으로 제공한다. 출처와 SHA-256은 [fonts.json](assets/fonts.json), 라이선스는 [Archivo-OFL.txt](assets/Archivo-OFL.txt)에 있다.
