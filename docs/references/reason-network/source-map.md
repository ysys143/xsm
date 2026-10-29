# 공개 엔진 모듈 지도

기준: v0.12.11 `b3557ff454cd26a04c2a18804ba83ae5db8b119d`. 36개 Rust 모듈과 2개 TypeScript 어댑터를 대상으로 책임·주요 진입점·연결부를 정적으로 대조했다. 같은 파일의 모든 분기를 실환경에서 실행했다는 뜻은 아니다. 전체 upstream 검사와 별도 관찰 결과는 [검사 기록](test-results.json)에 있다.

| 모듈 | 책임·대조한 경계 | 코드 줄 | 테스트 선언 수 |
|---|---|---:|---:|
| [agent.rs](https://github.com/reason-machines/reason-network/blob/b3557ff454cd26a04c2a18804ba83ae5db8b119d/src/agent.rs) | 하네스 탐지·호출 meta·프로세스와 대화 식별·소켓 게시 | 481 | 7 |
| [claude.rs](https://github.com/reason-machines/reason-network/blob/b3557ff454cd26a04c2a18804ba83ae5db8b119d/src/claude.rs) | Claude 네이티브 레지스트리·소켓과 프로세스 대조 | 168 | 2 |
| [client.rs](https://github.com/reason-machines/reason-network/blob/b3557ff454cd26a04c2a18804ba83ae5db8b119d/src/client.rs) | JSON 요청 상관관계·호출 기한·데몬 시작·재접속·재등록 | 387 | 3 |
| [codex.rs](https://github.com/reason-machines/reason-network/blob/b3557ff454cd26a04c2a18804ba83ae5db8b119d/src/codex.rs) | rollout 턴 시작·종료·부분 줄·증분 읽기 | 188 | 1 |
| [config.rs](https://github.com/reason-machines/reason-network/blob/b3557ff454cd26a04c2a18804ba83ae5db8b119d/src/config.rs) | 기본 공유·수신 정책·폴더 제외·심볼릭 링크·포트 | 434 | 9 |
| [daemon/ask.rs](https://github.com/reason-machines/reason-network/blob/b3557ff454cd26a04c2a18804ba83ae5db8b119d/src/daemon/ask.rs) | 질문 원문·중복 합류·취소·늦은 답·서명·OS 패널 | 621 | 5 |
| [daemon/directory.rs](https://github.com/reason-machines/reason-network/blob/b3557ff454cd26a04c2a18804ba83ae5db8b119d/src/daemon/directory.rs) | 로컬/원격 디렉터리·업무·presence·주소 해석 | 694 | 5 |
| [daemon/mail.rs](https://github.com/reason-machines/reason-network/blob/b3557ff454cd26a04c2a18804ba83ae5db8b119d/src/daemon/mail.rs) | 저장·전달 경로·확인·outbox·재시도·루프·첨부 협상 | 1211 | 10 |
| [daemon/mod.rs](https://github.com/reason-machines/reason-network/blob/b3557ff454cd26a04c2a18804ba83ae5db8b119d/src/daemon/mod.rs) | 데몬 생명주기·동시 IPC dispatch·상태와 락 | 429 | 1 |
| [daemon/notify.rs](https://github.com/reason-machines/reason-network/blob/b3557ff454cd26a04c2a18804ba83ae5db8b119d/src/daemon/notify.rs) | 데스크톱 알림·빈도·유효 시간·OS 차이 | 228 | 2 |
| [daemon/reason.rs](https://github.com/reason-machines/reason-network/blob/b3557ff454cd26a04c2a18804ba83ae5db8b119d/src/daemon/reason.rs) | Reason 클라우드 세션 열거·전달·비공개 relay 프로세스 경계 | 269 | 2 |
| [daemon/sessions.rs](https://github.com/reason-machines/reason-network/blob/b3557ff454cd26a04c2a18804ba83ae5db8b119d/src/daemon/sessions.rs) | 등록·이름 소유·대화 전환·hook·재개·보존·제외 폴더 | 1480 | 29 |
| [daemon/teamops.rs](https://github.com/reason-machines/reason-network/blob/b3557ff454cd26a04c2a18804ba83ae5db8b119d/src/daemon/teamops.rs) | 팀 생성·가입·초대·제명·릴레이·서명 상태 반영 | 704 | 1 |
| [daemon/update.rs](https://github.com/reason-machines/reason-network/blob/b3557ff454cd26a04c2a18804ba83ae5db8b119d/src/daemon/update.rs) | standalone 업데이트·소유자·체크섬 설치·재시작 | 125 | 1 |
| [doing.rs](https://github.com/reason-machines/reason-network/blob/b3557ff454cd26a04c2a18804ba83ae5db8b119d/src/doing.rs) | 제목과 현재 할 일 추출·캐시·부분 줄·파일 재작성 | 266 | 2 |
| [files.rs](https://github.com/reason-machines/reason-network/blob/b3557ff454cd26a04c2a18804ba83ae5db8b119d/src/files.rs) | 파일 범위·이름·크기·할당량·저장·보존·본문 대체 | 816 | 12 |
| [git.rs](https://github.com/reason-machines/reason-network/blob/b3557ff454cd26a04c2a18804ba83ae5db8b119d/src/git.rs) | 저장소·브랜치·remote slug 추출 | 58 | 1 |
| [hook.rs](https://github.com/reason-machines/reason-network/blob/b3557ff454cd26a04c2a18804ba83ae5db8b119d/src/hook.rs) | 하네스 이벤트 정규화·메일 주입·출력 뒤 확인·기한 | 202 | 2 |
| [invite.rs](https://github.com/reason-machines/reason-network/blob/b3557ff454cd26a04c2a18804ba83ae5db8b119d/src/invite.rs) | 단어 코드 생성·정규화·코드 기반 임시 키 | 71 | 1 |
| [ipc.rs](https://github.com/reason-machines/reason-network/blob/b3557ff454cd26a04c2a18804ba83ae5db8b119d/src/ipc.rs) | Unix socket/Windows named pipe·경로·접속 소유 | 93 | 0 |
| [main.rs](https://github.com/reason-machines/reason-network/blob/b3557ff454cd26a04c2a18804ba83ae5db8b119d/src/main.rs) | 공개 CLI parsing·상태·발신자 구분·등록·명령 dispatch | 937 | 5 |
| [mcp.rs](https://github.com/reason-machines/reason-network/blob/b3557ff454cd26a04c2a18804ba83ae5db8b119d/src/mcp.rs) | 스키마·초기 지침·매 호출 식별·도구 숨김·수신·파일 루트 | 447 | 2 |
| [migrate.rs](https://github.com/reason-machines/reason-network/blob/b3557ff454cd26a04c2a18804ba83ae5db8b119d/src/migrate.rs) | tincan에서의 설치 소유·서비스·실행 중 세션 호환 이동 | 100 | 0 |
| [net.rs](https://github.com/reason-machines/reason-network/blob/b3557ff454cd26a04c2a18804ba83ae5db8b119d/src/net.rs) | QUIC·멤버 gate·가입·릴레이·프록시·포트·presence·ack·재시도 | 1523 | 13 |
| [opencode-plugin.ts](https://github.com/reason-machines/reason-network/blob/b3557ff454cd26a04c2a18804ba83ae5db8b119d/src/opencode-plugin.ts) | 1.x/2.x 상태·할 일·prompt API·플러그인 종료 | 147 | 0 |
| [paths.rs](https://github.com/reason-machines/reason-network/blob/b3557ff454cd26a04c2a18804ba83ae5db8b119d/src/paths.rs) | 상태·프로필 경로·짧은 소켓·기존 경로 호환·권한 | 268 | 1 |
| [pi-extension.ts](https://github.com/reason-machines/reason-network/blob/b3557ff454cd26a04c2a18804ba83ae5db8b119d/src/pi-extension.ts) | 세션별 지연 MCP 노출·상태·steer/idle 주입·종료 | 75 | 0 |
| [proof.rs](https://github.com/reason-machines/reason-network/blob/b3557ff454cd26a04c2a18804ba83ae5db8b119d/src/proof.rs) | JWS·키 pin·issuer/audience·만료와 이름 소유 구분 | 440 | 10 |
| [proto.rs](https://github.com/reason-machines/reason-network/blob/b3557ff454cd26a04c2a18804ba83ae5db8b119d/src/proto.rs) | 로컬 요청·응답·이벤트·메시지·공개 상태 자료형 | 557 | 2 |
| [relays.rs](https://github.com/reason-machines/reason-network/blob/b3557ff454cd26a04c2a18804ba83ae5db8b119d/src/relays.rs) | 서명된 릴레이 목록·유효성·캐시·업데이트·실패 대체 | 442 | 8 |
| [render.rs](https://github.com/reason-machines/reason-network/blob/b3557ff454cd26a04c2a18804ba83ae5db8b119d/src/render.rs) | 출처 프레임·표시·제어 문자·가짜 승인·자료 경로 분리 | 670 | 7 |
| [setup/zcode.rs](https://github.com/reason-machines/reason-network/blob/b3557ff454cd26a04c2a18804ba83ae5db8b119d/src/setup/zcode.rs) | 사용자/공용 MCP 설정의 실제 우선순위·제거 | 206 | 6 |
| [setup.rs](https://github.com/reason-machines/reason-network/blob/b3557ff454cd26a04c2a18804ba83ae5db8b119d/src/setup.rs) | 설정 탐지·백업·병합·훅·MCP·서비스·제거·doctor | 1654 | 11 |
| [store.rs](https://github.com/reason-machines/reason-network/blob/b3557ff454cd26a04c2a18804ba83ae5db8b119d/src/store.rs) | SQLite 우편함·outbox·세션·첨부·중복·마이그레이션·정리 | 1124 | 13 |
| [team.rs](https://github.com/reason-machines/reason-network/blob/b3557ff454cd26a04c2a18804ba83ae5db8b119d/src/team.rs) | 서명 멤버십·admission·초대·이름 소유·상태 병합·ticket | 1254 | 25 |
| [tray.rs](https://github.com/reason-machines/reason-network/blob/b3557ff454cd26a04c2a18804ba83ae5db8b119d/src/tray.rs) | 메뉴바 상태·누가 온라인인지·미독 표시·데몬 수명 | 270 | 0 |
| [util.rs](https://github.com/reason-machines/reason-network/blob/b3557ff454cd26a04c2a18804ba83ae5db8b119d/src/util.rs) | 이름·표시·프로세스·락·권한·원자적 유틸리티 | 372 | 6 |
| [wizard.rs](https://github.com/reason-machines/reason-network/blob/b3557ff454cd26a04c2a18804ba83ae5db8b119d/src/wizard.rs) | 사람의 대화형 가입과 에이전트 비대화형 기본값·설정 선택 | 321 | 0 |

테스트 선언 수는 파일 내 표기 개수다. 플랫폼 조건과 실행기의 펼침 결과가 있으므로 실제 통과 수는 검사 로그를 기준으로 한다. Rust 모듈 외에 install.sh/install.ps1, Cargo.toml/lock, LICENSE·NOTICE, upstream tests/e2e 8개와 tests/install_script.rs의 실행 조건을 검토했다. E2E 8개는 이번에 실행하지 않았다.

## 배포 CLI 경계

비공개 CLI에서는 [여섯 JS 모듈](cli-analysis.md)을 정적으로 분석했다. 이는 공개 엔진 코드와 다른 출처다. 서버 구현이나 전체 앱 내부를 분석했다는 뜻은 아니다.

추가 [Ghidra 분석](ghidra-native.md)은 CLI 메모리 영역·native 진입점·엔진 문자열 참조와 linker 함수 경계를 대조한다. source 지도와 native 도구의 부분 자동 분석을 구별한다.
