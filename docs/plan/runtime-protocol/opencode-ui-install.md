# OpenCode UI 설치의 남은 구현

상태: macOS·OpenCode 1.19.5의 기본 설치와 native 수명 시나리오를 검증했다.
기본 조건과 사용자 편집 조건이 각각 8단계를 통과했다. 다른 플랫폼·버전과
전체 런타임 지원이 완료됐다는 뜻은 아니다.

## 구현한 소유 변경

- 기존 `plugins/xsm.js` 로더에서 native UI 연결을 활성화한다.
- 별도 TUI 로더 대신 immutable snapshot의 `integrations/opencode/tui.mjs` URI를
  native `tui.json`/`tui.jsonc`의 plugin 목록에 등록한다. 이 모듈은 기본
  TUI entry와 id를 이미 제공한다. 서버 plugin 디렉터리에 넣으면 안 된다.
- 기존 사용자 설정·댓글·다른 plugin과 auth/권한 설정을 보존한다. JSONC를
  정규화해 다시 쓰지 않고 원문 위치를 찾아 소유 URI만 삽입·갱신·제거한다.
- 최초 생성 파일은 소유 기록이 있고 내용이 그대로인 경우에만 제거한다.
  사용자가 다른 설정을 더했으면 자기 URI만 제거하고 파일을 유지한다.
- 설치/제거 전 두 대상 모두 검사한다. 기존 소유권/CAS/no-follow 경계를
  유지하고, 준비/완료 journal로 중단 후 복구한다. 사용자 수정 위에 과거
  backup을 덮어 복구하지 않는다.

## 구현한 snapshot 참조

- 서버 로더와 UI URI가 서로 다른 버전을 가리키는 준비 중 상태에서도 둘 다
  정리 대상에서 제외해야 한다. 소유 기록의 UI 참조를 로더 갱신에서 잃지 않는다.
- TUI 프로세스는 별도 xsm 대화 참여자가 아니다. 따라서 대화 registry만으로
  실행 중인 old TUI snapshot 사용을 알 수 없다. native TUI 수명에 결속한
  내부 component lease로 실제 PID/시작 세대/소스 root를 기록한다. 서버의 JS
  코드도 대화가 없는 동안 보존한다. 생성과 정리는 동일 잠금을 사용한다.
  조회는 기록된 PID에 한정하며 시작 시각은 C locale/UTC로 고정한다.
- 소유 기록과 다른 URI를 사용자가 설정했어도 그 실제 snapshot 참조를 보존한다.
  참조 보존은 변경 소유권을 주장하거나 사용자 편집을 덮는 근거가 아니다.

## 완료한 검사

`python3 scripts/check-protocol.py`의 핵심 180개 + Python 클라이언트 18개 +
Node 45개, 총 243개가 Python 3.9.6에서 43.324초, 3.14.6에서 28.600초에
통과했다. 별도 기존 설치 회귀 104개도 65.389초에 통과했다.
`py39-ui-install-release.log`, `py314-ui-install-release.log`, `ui-install-regression-release.log`가 근거다.

`probe-opencode-question-ui.py --native-bridge --installed --action choose|cancel`은
격리된 실제 OpenCode 1.19.5에서 통과했다. 개발 로더 대신 기본 설치된 서버와
UI를 사용했고 소스 root와 실제 UI PID의 UTC 수명 기록을 확인했다.
모델과 키 입력은 명시적 fixture이며 실제 사람의 응답으로 부르지 않는다.

JSONC 댓글/후행 쉼표·중단 후 반복 갱신·사용자 plugin 추가·늦은 파일 편집·
경로 교체·제거 중단 후 복구·살아 있는 수명 기록의 snapshot 보존은 격리 검사로
통과했다. CAS, 사용자 설정 보존, 활성 component 보존, 정리 잠금을 제거한
네 변이는 관련 검사를 실패시켰다(`ui-install-mutations.json`).

## 실제 native 수명 시나리오

```sh
python3 scripts/probe-opencode-install-lifecycle.py --native-root /isolated/npm-root --output deliverables/opencode-lifetime
python3 scripts/probe-opencode-install-lifecycle.py --native-root /isolated/npm-root --output deliverables/opencode-lifetime-user --user-edit
```

각 명령은 새 HOME/설정/저장소에서 실제 서버와 TUI를 열어 다음 순서를 확인한다.

1. 설치 전 대화와 문맥을 만들고, 설치 후에도 재로딩이 필요함을 확인한다.
2. 같은 대화를 재개해 설치된 서버·UI와 도구 21개를 로드한다.
3. 다른 내용의 snapshot으로 갱신해도 실행 중인 이전 코드는 유지한다.
4. Backend를 새 코드로 재시작한 뒤, 이전 UI만 이전 snapshot을 보존함을 확인한다.
5. 이전 UI를 정상 종료하고 실제 정리기가 이전 snapshot을 제거한다.
6. 새 UI로 같은 대화와 문맥을 다시 연다.
7. 제거해도 실행 중인 프로세스와 사용자 설정·mode는 보존한다.
8. 다시 시작하면 같은 대화는 남고 xsm 서버·UI는 로드되지 않는다.

사용자 편집 변형은 설치 후 다른 plugin을 추가하고, 실행 중 로더를 편집한
경우 설치가 거부되어 현재 파일과 대화가 유지됨도 검사한다. 제거 뒤 추가한
plugin이 실제 TUI에서 로드된다. 무변경 파일은 원래 bytes, 편집 파일은 사용자
값과 댓글을 보존하는 기준으로 각각 검사한다.

UI pin을 일부러 무시한 `--mutate-omit-ui` 실행은 4단계에서 살아 있는 UI의
snapshot을 삭제해 실패했다. 정상 실행의 같은 단계에는 다른 참조가 없었고
살아 있는 이전 component도 UI 하나였음을 기록했다. Legacy PID 시각은 초
단위이므로 새 backend는 retirement보다 확실히 늦은 초에 시작해 무관한
보수적 보존이 검사를 가리지 않게 한다.

첫 실패의 5초 초기화 관측과 native SDK 의존성 대기는 별도 실패 로그에 남겼다.
시험은 실제 고정 SDK의 package/lock 정보를 함께 준비한다. OpenCode가 xsm
설치 전에 `$schema`를 자동 추가하므로 설치 직전 bytes를 비교 기준으로 기록한다.
이 native 자체 변경을 xsm의 변경으로 세지 않는다. Python 3.9에서 지원하지
않는 하네스 write_text 인자도 수정했고 실패 실행은 보존했다.

결과는 `opencode-lifecycle-final`, `opencode-lifecycle-user-edit-fixed`,
`opencode-lifecycle-final-no-ui-pin`의 result.json과 원시 화면/서버 로그에 있다.
실제 사용자 프로필이나 모델 추론을 시험 대상으로 삼지 않는다. Linux, 실제
모델 협업, 다른 런타임 및 전체 수용 조건은 상위 계획의 미완 항목이다.

수명 검사와 잠금 보완 뒤의 빠른 묶음은 핵심 182개 + Python 클라이언트
18개 + Node 45개, 총 245개다. Python 3.9.6에서 43.295초, 3.14.6에서
27.866초에 통과했다. 설치·setup 회귀 117개는 64.868초에 통과했다.
수치는 `*-lock-lifecycle-complete.log`, `lifecycle-install-setup-regression.log`에
남겼으며 기존 기본 설치 선택·취소 표본과 별도 실행으로 구분한다.


## 2026-11-04 현재 도구 목록으로 수명 검사 재실행

기존 probe의 기대 도구 수21은 xsm_doc 추가 뒤 실제22개와 달랐다. 실제 기본
시나리오가 첫 재로딩 뒤 해당 assertion에서 실패함을 확인했다
(`opencode-lifecycle-current/before`,1단계 후 실패). 기대값 두 곳을22로 맞췄고
제품 설치기나 런타임 코드는 바꾸지 않았다.

후속 Mac의 기본 조건과 --user-edit 조건은 각각8단계를 모두 통과했다. 같은
native 대화의 설치 전/후 재개, 실행 중 구 snapshot 보존, backend 교체 뒤
구 UI만의 snapshot 보존, UI 정상 종료 뒤 실제 prune, 새 UI 재개, 제거 뒤
실행 중 프로세스/사용자 설정·mode 보존, 제거 후 재시작의 대화 보존과
xsm 미로딩을 확인했다. 최종 UI exit0이었다. 원시는
`deliverables/protocol-foundation/opencode-lifecycle-current/final`과 `user-edit`다.
이 재실행의 Linux와 기존 stable 배포로의 데이터 보존 rollback은 아직 미완이다.
보안 감사가 아닌 설치·갱신·재개·제거의 기능 호환성 검사다.
