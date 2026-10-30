# Parley 모듈 지도

조사 HEAD: `07f445c48723e446fa4d62ed068acfdf53c3f803`. Go 구현 57파일·검사 63파일·11패키지다. 전체 목록과 핵심 호출 경로를 정적 대조했으며 모든 분기를 실행했다는 뜻은 아니다.

| 패키지 | 구현/검사 파일 수 | 책임 |
|---|---:|---|
| `cmd/parley` | 23/30 | CLI 구성·인자 검증·설정 생성·작업 폴더/대화 준비·소유 확인·종료/rollback |
| `internal/channel` | 1/1 | Claude 수신 MCP initialize/notification과 출력·종료 경계 |
| `internal/codex` | 2/2 | Codex 큐 인계·argv 한도·primer turn 이벤트 해석 |
| `internal/doctor` | 8/6 | 버전·도구 표면·스킬·서버 검사와 선택적 live probe |
| `internal/ergoconf` | 1/1 | embedded Ergo 설정의 주소·DB 경로 치환과 소유 임시 파일 |
| `internal/opencode` | 7/8 | HTTP 서비스 발견·인증·세션/idle·queued prompt/readback·본문 한도 |
| `internal/primer` | 1/1 | 하네스/모드별 공통 초기 지침·셸 인용·UTF-16 길이 |
| `internal/state` | 4/4 | nick/ID lock·cursor·계정 비밀·thread/session ID 보관 |
| `internal/stream` | 3/5 | 공통 Stream·nick 규칙·Deliverer·출처 렌더링·gate |
| `internal/stream/file` | 1/1 | NDJSON append·offset/fingerprint cursor·회전 gap·poll |
| `internal/stream/irc` | 6/4 | loopback 검증·SASL/등록·capability·multiline·CHATHISTORY·재접속 |

## 구현 파일 전수 목록

아래 링크는 해당 HEAD의 파일에 고정했다. 모듈 지도는 커버리지 색인이며 실행 판정은 validation.json을 따른다.

### cmd/parley

- [build.go](https://github.com/colinsurprenant/parley/blob/07f445c48723e446fa4d62ed068acfdf53c3f803/cmd/parley/build.go)
- [build_end.go](https://github.com/colinsurprenant/parley/blob/07f445c48723e446fa4d62ed068acfdf53c3f803/cmd/parley/build_end.go)
- [build_new.go](https://github.com/colinsurprenant/parley/blob/07f445c48723e446fa4d62ed068acfdf53c3f803/cmd/parley/build_new.go)
- [codexroots.go](https://github.com/colinsurprenant/parley/blob/07f445c48723e446fa4d62ed068acfdf53c3f803/cmd/parley/codexroots.go)
- [doctor.go](https://github.com/colinsurprenant/parley/blob/07f445c48723e446fa4d62ed068acfdf53c3f803/cmd/parley/doctor.go)
- [flags.go](https://github.com/colinsurprenant/parley/blob/07f445c48723e446fa4d62ed068acfdf53c3f803/cmd/parley/flags.go)
- [gitwt.go](https://github.com/colinsurprenant/parley/blob/07f445c48723e446fa4d62ed068acfdf53c3f803/cmd/parley/gitwt.go)
- [line.go](https://github.com/colinsurprenant/parley/blob/07f445c48723e446fa4d62ed068acfdf53c3f803/cmd/parley/line.go)
- [line_add.go](https://github.com/colinsurprenant/parley/blob/07f445c48723e446fa4d62ed068acfdf53c3f803/cmd/parley/line_add.go)
- [line_drop.go](https://github.com/colinsurprenant/parley/blob/07f445c48723e446fa4d62ed068acfdf53c3f803/cmd/parley/line_drop.go)
- [line_exclude.go](https://github.com/colinsurprenant/parley/blob/07f445c48723e446fa4d62ed068acfdf53c3f803/cmd/parley/line_exclude.go)
- [line_new.go](https://github.com/colinsurprenant/parley/blob/07f445c48723e446fa4d62ed068acfdf53c3f803/cmd/parley/line_new.go)
- [main.go](https://github.com/colinsurprenant/parley/blob/07f445c48723e446fa4d62ed068acfdf53c3f803/cmd/parley/main.go)
- [opencode.go](https://github.com/colinsurprenant/parley/blob/07f445c48723e446fa4d62ed068acfdf53c3f803/cmd/parley/opencode.go)
- [opencode_connect.go](https://github.com/colinsurprenant/parley/blob/07f445c48723e446fa4d62ed068acfdf53c3f803/cmd/parley/opencode_connect.go)
- [opencode_session.go](https://github.com/colinsurprenant/parley/blob/07f445c48723e446fa4d62ed068acfdf53c3f803/cmd/parley/opencode_session.go)
- [server.go](https://github.com/colinsurprenant/parley/blob/07f445c48723e446fa4d62ed068acfdf53c3f803/cmd/parley/server.go)
- [setup.go](https://github.com/colinsurprenant/parley/blob/07f445c48723e446fa4d62ed068acfdf53c3f803/cmd/parley/setup.go)
- [table.go](https://github.com/colinsurprenant/parley/blob/07f445c48723e446fa4d62ed068acfdf53c3f803/cmd/parley/table.go)
- [table_end.go](https://github.com/colinsurprenant/parley/blob/07f445c48723e446fa4d62ed068acfdf53c3f803/cmd/parley/table_end.go)
- [table_new.go](https://github.com/colinsurprenant/parley/blob/07f445c48723e446fa4d62ed068acfdf53c3f803/cmd/parley/table_new.go)
- [table_own.go](https://github.com/colinsurprenant/parley/blob/07f445c48723e446fa4d62ed068acfdf53c3f803/cmd/parley/table_own.go)
- [version.go](https://github.com/colinsurprenant/parley/blob/07f445c48723e446fa4d62ed068acfdf53c3f803/cmd/parley/version.go)
### internal/channel

- [channel.go](https://github.com/colinsurprenant/parley/blob/07f445c48723e446fa4d62ed068acfdf53c3f803/internal/channel/channel.go)
### internal/codex

- [codex.go](https://github.com/colinsurprenant/parley/blob/07f445c48723e446fa4d62ed068acfdf53c3f803/internal/codex/codex.go)
- [turn.go](https://github.com/colinsurprenant/parley/blob/07f445c48723e446fa4d62ed068acfdf53c3f803/internal/codex/turn.go)
### internal/doctor

- [claude.go](https://github.com/colinsurprenant/parley/blob/07f445c48723e446fa4d62ed068acfdf53c3f803/internal/doctor/claude.go)
- [codex.go](https://github.com/colinsurprenant/parley/blob/07f445c48723e446fa4d62ed068acfdf53c3f803/internal/doctor/codex.go)
- [doctor.go](https://github.com/colinsurprenant/parley/blob/07f445c48723e446fa4d62ed068acfdf53c3f803/internal/doctor/doctor.go)
- [ergo.go](https://github.com/colinsurprenant/parley/blob/07f445c48723e446fa4d62ed068acfdf53c3f803/internal/doctor/ergo.go)
- [live_codex.go](https://github.com/colinsurprenant/parley/blob/07f445c48723e446fa4d62ed068acfdf53c3f803/internal/doctor/live_codex.go)
- [live_ergo.go](https://github.com/colinsurprenant/parley/blob/07f445c48723e446fa4d62ed068acfdf53c3f803/internal/doctor/live_ergo.go)
- [opencode.go](https://github.com/colinsurprenant/parley/blob/07f445c48723e446fa4d62ed068acfdf53c3f803/internal/doctor/opencode.go)
- [skills.go](https://github.com/colinsurprenant/parley/blob/07f445c48723e446fa4d62ed068acfdf53c3f803/internal/doctor/skills.go)
### internal/ergoconf

- [ergoconf.go](https://github.com/colinsurprenant/parley/blob/07f445c48723e446fa4d62ed068acfdf53c3f803/internal/ergoconf/ergoconf.go)
### internal/opencode

- [bound.go](https://github.com/colinsurprenant/parley/blob/07f445c48723e446fa4d62ed068acfdf53c3f803/internal/opencode/bound.go)
- [client.go](https://github.com/colinsurprenant/parley/blob/07f445c48723e446fa4d62ed068acfdf53c3f803/internal/opencode/client.go)
- [history.go](https://github.com/colinsurprenant/parley/blob/07f445c48723e446fa4d62ed068acfdf53c3f803/internal/opencode/history.go)
- [ident.go](https://github.com/colinsurprenant/parley/blob/07f445c48723e446fa4d62ed068acfdf53c3f803/internal/opencode/ident.go)
- [opencode.go](https://github.com/colinsurprenant/parley/blob/07f445c48723e446fa4d62ed068acfdf53c3f803/internal/opencode/opencode.go)
- [queue.go](https://github.com/colinsurprenant/parley/blob/07f445c48723e446fa4d62ed068acfdf53c3f803/internal/opencode/queue.go)
- [service.go](https://github.com/colinsurprenant/parley/blob/07f445c48723e446fa4d62ed068acfdf53c3f803/internal/opencode/service.go)
### internal/primer

- [primer.go](https://github.com/colinsurprenant/parley/blob/07f445c48723e446fa4d62ed068acfdf53c3f803/internal/primer/primer.go)
### internal/state

- [idlock.go](https://github.com/colinsurprenant/parley/blob/07f445c48723e446fa4d62ed068acfdf53c3f803/internal/state/idlock.go)
- [session.go](https://github.com/colinsurprenant/parley/blob/07f445c48723e446fa4d62ed068acfdf53c3f803/internal/state/session.go)
- [state.go](https://github.com/colinsurprenant/parley/blob/07f445c48723e446fa4d62ed068acfdf53c3f803/internal/state/state.go)
- [thread.go](https://github.com/colinsurprenant/parley/blob/07f445c48723e446fa4d62ed068acfdf53c3f803/internal/state/thread.go)
### internal/stream

- [deliver.go](https://github.com/colinsurprenant/parley/blob/07f445c48723e446fa4d62ed068acfdf53c3f803/internal/stream/deliver.go)
- [nick.go](https://github.com/colinsurprenant/parley/blob/07f445c48723e446fa4d62ed068acfdf53c3f803/internal/stream/nick.go)
- [stream.go](https://github.com/colinsurprenant/parley/blob/07f445c48723e446fa4d62ed068acfdf53c3f803/internal/stream/stream.go)
### internal/stream/file

- [file.go](https://github.com/colinsurprenant/parley/blob/07f445c48723e446fa4d62ed068acfdf53c3f803/internal/stream/file/file.go)
### internal/stream/irc

- [account.go](https://github.com/colinsurprenant/parley/blob/07f445c48723e446fa4d62ed068acfdf53c3f803/internal/stream/irc/account.go)
- [conn.go](https://github.com/colinsurprenant/parley/blob/07f445c48723e446fa4d62ed068acfdf53c3f803/internal/stream/irc/conn.go)
- [history.go](https://github.com/colinsurprenant/parley/blob/07f445c48723e446fa4d62ed068acfdf53c3f803/internal/stream/irc/history.go)
- [irc.go](https://github.com/colinsurprenant/parley/blob/07f445c48723e446fa4d62ed068acfdf53c3f803/internal/stream/irc/irc.go)
- [proto.go](https://github.com/colinsurprenant/parley/blob/07f445c48723e446fa4d62ed068acfdf53c3f803/internal/stream/irc/proto.go)
- [spec.go](https://github.com/colinsurprenant/parley/blob/07f445c48723e446fa4d62ed068acfdf53c3f803/internal/stream/irc/spec.go)

## 두 심화 조사 축

- 출처·사람 권한: `Delivery.Render` → body 제어문자 처리 → nick 인증 → chair 비교 → 스킬의 도구 승인 분리. 본문을 승인 메타데이터로 승격하지 않는 경계를 대조했다.
- 인계·복구: `Deliverer.collect/Commit` → front별 handoff → `SaveCursor`, held queue와 cursor의 수명 차이, IRC gap, OpenCode stable-ID/readback와 취소 경쟁. 정적 설명과 독립 API/실제 CLI 관찰을 분리했다.

그 밖의 등록·모드·설치·종료·xsm 비교는 [본문](../parley.md)에 있다.
