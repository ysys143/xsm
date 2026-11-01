# OpenCode UI 설치의 남은 구현

상태: 미구현. native 서버–TUI 제어 경로는 구현했지만 기본 설치는 아직
`nativeUi`를 켜거나 TUI 플러그인을 등록하지 않는다. 전체 계획의 다음 설치
수용 조건이며 제외하지 않는다.

## 소유할 변경

- 기존 `plugins/xsm.js` 로더에서 native UI 연결을 활성화한다.
- 별도 TUI 로더 대신 immutable snapshot의 `integrations/opencode/tui.mjs` URI를
  native `tui.json`/`tui.jsonc`의 plugin 목록에 등록할 수 있다. 이 모듈은 기본
  TUI entry와 id를 이미 제공한다. 서버 plugin 디렉터리에 넣으면 안 된다.
- 기존 사용자 설정·댓글·다른 plugin과 auth/권한 설정을 보존한다. JSONC를
  정규화해 다시 쓰기보다 원문 위치를 찾아 소유 URI만 삽입·갱신·제거한다.
- 최초 생성 파일은 소유 기록이 있고 내용이 그대로인 경우에만 제거한다.
  사용자가 다른 설정을 더했으면 자기 URI만 제거하고 파일을 유지한다.
- 설치/제거 전 두 대상 모두 검사한다. 기존 소유권/CAS/no-follow 경계를
  유지하고, 준비/완료 journal로 중단 후 복구한다. 사용자 수정 위에 과거
  backup을 덮어 복구하지 않는다.

## snapshot 참조

- 서버 로더와 UI URI가 서로 다른 버전을 가리키는 준비 중 상태에서도 둘 다
  정리 대상에서 제외해야 한다. 소유 기록의 UI 참조를 로더 갱신에서 잃지 않는다.
- TUI 프로세스는 별도 xsm 대화 참여자가 아니다. 따라서 대화 registry만으로
  실행 중인 old TUI snapshot 사용을 알 수 없다. native TUI 수명에 결속한
  내부 component lease 또는 동등한 증거로 실제 PID/시작 세대/소스 root를
  확인하고, 활성 old snapshot을 보존해야 한다. profile 간 임의 PID/argv를
  수집하지 않는다.

## 확인할 경로

깨끗한 설치·갱신·같은 대화 재개·실행 중 old UI 보존·제거·소유 파일 수정·
다른 plugin 추가·JSONC 댓글/후행 쉼표·설치 중 중단·symlink/경로 교체를
격리 프로필에서 실행한다. 실제 사용자 프로필을 시험 대상으로 삼지 않는다.

완료 증거에는 기본 설치 경로에서 native 도구→TUI→호스트 적용/취소,
모델 입력에서 제어 프레임 제외, 설치/제거 뒤 사용자 설정 보존을 포함한다.
현재 개발용 로더로 통과한 시험을 기본 설치 완료 증거로 대체하지 않는다.
