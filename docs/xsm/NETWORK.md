# 선택적 P2P 네트워크

로컬 메시징과 기존 SSH 연결은 그대로 사용할 수 있다. P2P를 켠 기기끼리는 xsm 계정이나 양방향 SSH 설정 없이 기기키와 초대로 연결한다. Tailscale은 선택 가능한 접속 경로다. 네트워크 가입은 세션 공개나 작업 권한을 부여하지 않는다.

## 시작과 가입

현재 배포에는 Rust 엔진의 고정 소스와 Cargo.lock이 포함된다. Rust toolchain이 있는 기기에서 다음 명령으로 자기 xsm 상태 폴더에 엔진을 빌드한다. 이 명령은 전역 Rust를 설치하지 않는다. 빌드한 파일의 SHA-256은 로컬 빌드 출처 확인이며 공급자 서명 검증을 뜻하지 않는다.

```sh
xsm network build
xsm network init my-network --machine-name macbook
xsm network invite
```

`invite`는 비밀이 든 0600 파일을 만들고 파일 위치만 반환한다. 사용자가 선택한 신뢰할 수 있는 수단으로 상대 기기에 전달한다. 초대 내용은 대화·로그·명령 인자로 붙이지 않는다. 상대에서는 전달된 파일을 지정하거나 stdin으로 제공한다.

```sh
xsm network join --ticket-file /path/to/private-ticket.json --machine-name macmini
xsm network members
xsm network status
```

활성 멤버라면 누구나 초대·추가·제명을 할 수 있다. 최초 기기는 신뢰의 출발점이며 관리자 권한을 독점하지 않는다. `invite --once --expires 3600`은 한 시간짜리 일회용 초대다. `invite --expires 3600`은 한 시간 동안 재사용할 수 있는 초대다. 일회용 가입은 발급 기기가 온라인일 때 직렬화하며 응답 유실 뒤 같은 기기는 결과를 회수한다. 재사용 초대와 일회용 초대는 다른 의미다. `revoke-invite HASH`는 해당 초대를 회수한다. 제명 때 기존 재사용 초대도 함께 회수하므로 제명 기기가 옛 링크로 즉시 재가입하지 못한다. 다시 초대하려면 새 초대를 발급한다.

## 세션 발견과 협업

사용자가 미리 공개한 세션과 같은 실제 저장소로 확인된 세션을 발견한다. 원격의 같은 폴더명이나 같은 Git remote URL만으로 같은 저장소라고 판단하지 않는다. 두 기기의 저장소 대응을 사용자가 확인한 경우에만 같은 `repository-id`와 상대의 공개 기기키를 각각 기록한다.

```sh
xsm network map-repository /local/repository --repository-id agreed-repository --peer PEER_PUBLIC_KEY
xsm discover --machine macmini
```

대응을 기록하지 않은 다른 저장소의 세션도 사용자가 공개했다면 후보로 보인다. 사용자가 후보의 작업 내용을 확인하고 상대를 선택하면 기존 `connect`, `ask`, `send`를 쓴다. 반환된 주소를 그대로 사용하며 표시명으로 주소를 만들지 않는다. 공개만으로 협업 권한이 생기지는 않는다. 선택은 정확한 세션 쌍에 결속되며, 실제 상대의 상관된 성공 회신이 와야 핸드셰이크가 완료된다.

기기 간 선택 증거는 선택한 사용자의 결정을 가진 기기가 서명해 전달한다. 수신 기기는 이를 멤버의 선택 증언으로 보관하며, 자기 사용자가 별도로 승인했다는 기록으로 바꾸지 않는다. 원문 승인 답변과 로컬 홈 경로는 전달하지 않는다. 현재 멤버십·차단·폴더 제외·선택 철회를 수신 때 다시 확인한다. 이는 상호 신뢰하는 멤버 모델이며 악의적인 기존 멤버를 강하게 격리하는 관리 모델이 아니다.

파일 사본은 같은 메시지 인터페이스에서 수신 세션의 실제 현재 지원 여부를 확인한 뒤 보낸다. 파일 사본은 외부 데이터이며 파일 읽기·실행·권한 변경 승인이 아니다. P2P의 `--wake never`는 네이티브 입력·깨우기 없이 저장한다. 자동 깨우기는 해당 버전의 수신 훅이 실제 실행된 세션에만 시도한다. 지원 여부가 확인되지 않으면 MCP 수신을 위해 원본을 보존한다.

## 경로·복구·종료

```sh
xsm network configure --port 12345
xsm network configure --relay https://your-relay.example
xsm network configure --relay public
xsm network configure --direct-address 100.64.0.1:0
xsm network stop
xsm network start
```

설정은 다음 시작부터 적용된다. 기본 포트는 임의 포트이고 명시한 포트가 점유됐을 때만 대체 포트를 사용한다. `status`는 요청 포트·실제 바인딩·대체 여부·마지막 관측 경로를 구분한다. relay가 설정됐다는 사실은 그 메시지가 relay를 경유했다는 증거가 아니다. `--relay off`는 직접 연결만 시험할 때 사용한다. Tailscale 주소를 추가해도 기기키·멤버십·세션 권한은 그대로다.

가입 또는 발신 응답이 유실되면 성공·실패를 단정하지 않는다. 현재 네트워크 ID와 기기키를 확인하고, 메시지는 같은 ID로 `status` 또는 `question-status`를 조회한다. 새 ID로 자동 재전송하지 않는다. 저장·네이티브 전달·수신자의 명시적 ACK·실제 답변은 서로 다른 증거다.

네트워크 서비스를 껐거나 다른 팀으로 전환한 뒤에도 현재 대화가 작성한 원문을 복구할 수 있다.

```sh
xsm network requests
xsm network export REQUEST_ID --output /path/to/new-private-file.json
xsm network archive REQUEST_ID
xsm network requests --archived
```

조회·내보내기·보관은 서비스를 시작하거나 피어에 접속하지 않는다. 정확히 확인된 현재 작성자의 요청만 대상으로 하며 내보내기는 새 0600 파일을 만든다. 기존 파일은 덮어쓰지 않는다. 원문·immutable 첨부 참조를 내보내며 첨부 바이트는 기존 용량·만료 정책의 사본 저장소에 있다. 보관은 네트워크 복구 목록에서 항목을 숨기고 같은 ID의 재전송을 막는다. 원문·질문 이력·늦은 회신을 버리지 않으며 원격 작업의 취소나 중지를 뜻하지 않는다.

`stop`은 자기 xsm 네트워크 서비스와 엔진만 종료한다. 로컬 메시징은 계속 동작하며 네트워크를 다시 시작하면 같은 기기키와 가입 상태를 사용한다. `remove PUBLIC_KEY`와 `leave`는 멤버십 변경이므로 사용자 지시를 확인한 뒤 실행한다. 키 교체는 새 private 상태에서 새 기기를 초대하고 이전 키를 제명하는 절차로 다룬다. 기존 키 파일을 덮어쓰거나 상태를 자동 삭제하지 않는다.

## 프로필에서 제거

특정 Claude/Codex 홈에서만 xsm을 제거하면 다른 홈과 공유 네트워크 서비스는 유지한다. 네트워크 사용까지 끝내려면 먼저 서비스를 중지하고 해당 홈의 설치를 제거한다.

```sh
xsm network stop
xsm uninstall --codex-home /path/to/codex-home
```

Claude 홈에는 `--claude-home`을 쓴다. 제거기는 자신이 추가한 MCP·훅·스킬 항목만 제거한다. 사용자가 만든 항목, 다른 홈, 원문·기기키·runtime 사본은 보존한다. 마지막 설치 홈을 제거하면 xsm이 만든 CLI 링크도 제거한다. 한 홈의 제거를 멤버 제명이나 진행 중 작업 취소로 해석하지 않는다.

현재 구현·실측 범위와 미검증 환경은 [ADR-0021 진행 기록](https://github.com/ysys143/xsm/blob/a124b22782d68c1541f6dd5893a57bbe6797b926/docs/plan/collaboration/adr-0021-progress.md)에 있다. 같은 호스트 시험과 두 물리 머신 시험, 실제 모델 세션과 네이티브 파일 시험체를 구분한다.
