# P11 두 머신 native 업무 carrier 비교

A의 LAN SSH, D의 Tailscale SSH, 기존 B private TCP에서 같은 짧은 검토 과제를 실제 peer Codex로 실행했다. 세 carrier의 첫 과제·후속·재연결 뒤 새 과제가 모두 같은 업무 ID의 JSON 답을 반환했다. 총 native 실행은 9회다.

이 결과는 P11 carrier 비교체의 native QA 증거다. 제품 xsm scope/가입 승인과 P11/G11/G12 전체 완료 판정은 남아 있다.

## 과제와 실제 환경

- 현재 머신: `Jaesolui-MacBookPro.local`; peer: `Jaesolui-Macmini.local` (`jaesol-macmini`). 양방향 기존 SSH hostname 응답을 확인했다.
- 업무 ID: `P11-QA-40c1afc34bbd43c4`. 공개 본문은 marker와 `2+2=5` 검토로 한정했다.
- peer CLI: `codex-cli 0.163.0`, `/opt/homebrew/bin/codex`, 기존 `.codex-3`의 ChatGPT 구독 인증. API 키 값은 조회하지 않았다.
- `--ignore-user-config --ignore-rules --ephemeral --sandbox read-only --json`과 hooks/plugins/apps/shell 비활성화를 invocation에만 적용했다. 실제 tool event는 0개였다.
- 새 로그인·trust·사용자 조작은 0회다. 기존 SSH/Tailscale/구독 인증은 전제이며 최초 인증 설정의 조작 수는 측정하지 않았다.

## 측정

| carrier | 첫 native 왕복 ms | 후속 native 왕복 ms | 재연결 뒤 보존 답 회수 ms | 재연결 뒤 새 native 왕복 ms |
|---|---:|---:|---:|---:|
| A-LAN-SSH | 6137.471 | 6712.996 | 10.001 | 5409.321 |
| D-Tailscale-SSH | 4971.326 | 6304.035 | 12.623 | 6277.135 |
| B-private-TCP | 5816.222 | 7377.910 | 19.796 | 5657.270 |

각 값은 단일 표본이며 CLI 기동·프로필 인증·구독 서비스 추론·carrier 왕복을 포함한다. 성능 순위나 순수 네트워크 지연으로 해석하지 않는다.

실제 답은 각 실행에서 `claim_valid=false`, `corrected_sum=4`였고, 한 문장 반례와 같은 `request_id`를 반환했다. schema는 답의 타입만 지정했으며 정답 값은 고정하지 않았다.

## 후속·재연결과 native conversation

native 호출마다 새 ephemeral conversation을 사용했다. 후속에는 같은 업무 ID와 직전의 작은 수학 답을 입력으로 전달했다. native resume나 하네스 기억 유지 시험은 수행하지 않았다.

carrier를 닫고 다시 연결한 뒤에는 저장된 직전 native JSON을 모델 재실행 없이 회수했다. 이어 같은 업무 ID의 새 native turn을 실행했다. 새 native turn 9개의 conversation ID는 모두 다르며, 회수 응답의 ID는 원래 후속 응답과 일치한다.

| carrier | first native conversation | followup native conversation | after-reconnect native conversation |
|---|---|---|---|
| A-LAN-SSH | `01a18366-2ce2-7182-ad93-735b0a10c1cb` | `01a18366-440f-71a2-9556-43bbdb714ef3` | `01a18366-5f95-7ee0-abaf-7e27aaa0d52a` |
| D-Tailscale-SSH | `01a18366-7626-7461-a309-0ebb98e6503c` | `01a18366-8952-7b33-987b-4d013244384a` | `01a18366-a3a0-78d1-b979-32eb9d167024` |
| B-private-TCP | `01a18366-be65-7783-90df-5df1e2effa96` | `01a18366-d502-7d90-833a-f48bae166167` | `01a18366-f426-70c3-a51f-90fe4b7ec7af` |

## 실제 경로와 B 범위

- A SSH 연결은 `192.168.0.11 → 192.168.0.18:22`, D는 `100.123.30.11 → 100.77.24.16:22`였다.
- D는 tailnet 주소의 기존 SSH다. 현재 underlay는 LAN direct endpoint로 관측했으며 relay 경유를 입증한 표본은 없다.
- B는 기존 spike의 private IPv4 bind·HMAC·요청 journal 구조를 재사용했다. bind는 `192.168.0.18`, 임시 포트는 `49909`와 `49941`이었다. 공개 listener·방화벽·가입 권한을 추가하지 않았다.
- B payload는 암호화하지 않은 최소 수학 과제다. ephemeral fixture 인증 재료는 기존 SSH stdin으로만 전달했고 파일/argv/공개 결과에 남기지 않았다.
- 기존 `/tmp/p11-transport-comparison-20261028.py`의 `SSH`, `PEER`, `LAN`, `start`를 AST로 읽어 재사용했다. 원 스크립트의 main을 import/실행하지 않아 기존 JSON을 덮어쓰지 않았다.

## C 고정 엔진 staging

`reason-network 0.12.10`의 15,266,656-byte 고정 binary를 peer 고유 `/tmp`에 전달했다. 양쪽 SHA-256은 `6ac4bb4837469867edc2dba3cbbd6e4dd9fb18ad0389db69ff6ef21683317a44`로 같았다. peer에서 `--version`과 `--help`가 exit 0이었다.

HOME/XDG 상태 위치를 staging 안으로 한정했고 모두 빈 상태였다. daemon·team·membership·listener는 만들지 않았다. staged 실행 파일은 확인 뒤 제거했다. 이 결과는 byte 일치와 실행 가능성까지이며 원격 C 가입/업무 왕복은 미실행이다.

## 오류 보존과 정리

첫 bootstrap은 pathlib 경로 조합 오류로 ready 이전에 종료됐다. 세 시도 모두 native 호출 0회이며 성공 표본에서 제외했다. 원 실패 결과·stderr·초기 source hash를 보존하고, 두 경로 식을 고친 뒤 실제 QA를 실행했다.

- peer driver 6개와 기록된 native CLI handle 9개가 종료됐다. 고유 `/tmp`가 argv에 남은 추가 프로세스도 0개다.
- local SSH handle은 모두 exit 0으로 회수됐다. 초기 실패 marker를 가진 남은 SSH 프로세스도 0개다.
- B 두 포트의 종료 뒤 connect 결과는 모두 `61`(refused)이었다.
- native 호출 전후의 열거된 설정파일 metadata와 local 설정 metadata가 일치했다. 전체 런타임 캐시의 동시 변경 여부는 별도 판정하지 않았다.
- 제품 소스·repo 설정·프로필 설정·전역 XSM_HOME·기존 key/hostkey·network/remote pairing/project 설정을 쓰는 명령은 실행하지 않았다. 실제 legacy xsm pairing은 사용하지 않았다.
- 양쪽 고유 `/tmp`의 코드·입력·결과는 재현 증거로 유지했다. 기존 프로세스나 서비스를 종료하지 않았다.

## 남은 환경

다른 NAT·UDP 차단·HTTPS proxy·자체 relay·SSH 불가 환경은 미확보/미실행으로 남는다. NAT 유형과 egress는 이번에 다시 측정하지 않았다. C의 원격 membership·native 업무와 D12 선택도 남아 있다. 합성 결과나 staging을 해당 환경의 실제 성공으로 승격하지 않는다.

## 증거 위치

- [실제 결과 JSON](native-carrier-roundtrip-20261029.json)
- [코드/원시 파일 SHA-256 manifest](native-carrier-manifest-20261029.json)
- local: `/tmp/p11-native-r292609m`
- peer: `/tmp/p11-native-2nemv2of`
- 코드 SHA-256: `37c7f02d2d717c91683d61de6f44afd43e80aa4eda49673567b43c0e8fe1ab6a`

이 run의 코드는 고유 경로에 결속되어 있다. 후속 실행은 새 `/tmp`와 새 run ID로 분리해야 원 기록을 유지할 수 있다.
