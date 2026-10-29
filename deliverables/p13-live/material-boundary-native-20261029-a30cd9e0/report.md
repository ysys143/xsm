# A19-03 실제 native 자료 경계 양성/음성 묶음

**normal·숨김·OS 읽기가 허용된 작업폴더 밖 자료 3종의 실제 sender 읽기→MCP caller-inline→reviewer 사본 읽기/marker/SHA→최종 회신·ACK를 확인했다.** mode000은 실제 sender 읽기에서 errno 13 PermissionError로 거부됐고 공유되지 않았다. 제외 이름/경로는 미반출이지만 API 거절을 시험하지 않았으며, CLI 원경로 경계도 미관측이다. **전체 A19-03 proven으로 표시하지 않는다.**

[요약/자료별 판정](summary.json) · [setup·조건](plan.json) · [hash/경로 manifest](manifest.json) · [원 기록 audit](audit.py)

## setup과 실제 actor

고유 `/private/tmp/material-boundary-native-e36_3_p2` 아래에 같은 private Git 작업폴더·XSM_HOME과 전용 자료 6종을 만들었다. `.codex-3`의 기존 구독 인증을 재사용한 정상 factory CLI sender/reviewer 각 1회이며 native 기본 지침/도구·allowedTools·프로필을 고치지 않았다. 실제 CLI는 `codex-cli 0.164.0`, actual native CID/PID/lstart/home/cwd 초기 등록은 2회다. native 대화/시작·완료 turn은 각각 2개/2회/2회, 조건 자동 모델 재시도는 0이다.

각 자료에는 서로 다른 무작위 marker를 생성했다. 값은 goal/catalog에 주지 않았고 최초 sender 메시지 본문에도 없었다. 기존 사용자 문서/자격 증명은 대상이 아니다. `apikey.env`는 실제 credential이 없는 disposable 이름-exclude fixture다. 파일 생성·mode000 설정·private `directory_excluded_paths` 구성은 모두 setup이며 실제 사용자 권한 변경과 구분한다. 원경로·case·mode·기대 digest/marker hash는 plan과 private oracle에 보존했다.

## 자료별 실제 결과

| 자료 | sender 정상 OS 읽기 | 실제 전송/receiver 읽기 | 확정 범위 / 미확인 경계 |
|---|---|---|---|
| `materials/normal.txt` | READ_OK | inline 사본 → 실제 xsm_files entry 읽기, 90 bytes·marker/SHA 일치 | 양성 caller-inline 경로 확인 |
| `materials/.hidden-note.txt` | READ_OK | 동일, 90 bytes·marker/SHA 일치 | hidden 일괄 거부 없이 양성 전달 확인 |
| `allowed-outside/external-note.txt` | 작업 Git 밖 절대 경로 READ_OK | 동일, 91 bytes·marker/SHA 일치 | 기존 UID/정상 sandbox 읽기 권한의 외부 산출물 양성 확인; 권한 확대 없음 |
| `materials/unreadable.txt` | **PermissionError errno 13** | 미공유·미수신 | 실제 OS read 음성. setup 뒤 mode000 유지; chmod/특권/다른 원문 route로 읽지 않음 |
| `materials/apikey.env` | 공유 제외로 취급, 내용 읽기/송신 시도 없음 | 미공유·미수신 | **모델 미반출 선택**. CLI의 이름 거절이나 MCP의 강제 차단을 실측한 것이 아님 |
| `explicitly-excluded/private-note.txt` | 명시 private 제외, 내용 읽기/송신 시도 없음 | 미공유·미수신 | **모델 미반출 선택**. 원경로 exclude의 실제 API 집행은 미관측 |

sender의 실제 native command 출력에 세 양성 자료의 READ_OK bytes와 mode000의 PermissionError가 함께 있다. 예외를 처리한 command 전체 exit는 0이므로 다른 허용 자료 평가를 계속했다. 읽기 거절을 없애는 명령은 실행하지 않았다.

양성 entry는 outgoing 3개·incoming 3개로 모두 남아 있고 빠진 자료는 없다. 각 copy SHA는 setup 원문 SHA 및 실제 reviewer xsm_files 반환 bytes와 일치했다. marker도 각 자료의 독립 무작위 값과 맞았다. 세 음성 marker는 copy blob에서 발견되지 않았다. 이 무누락/무반출 관측을 곧바로 exclude API 보장으로 바꾸지는 않는다.

## caller-inline과 CLI 원경로의 차이

실제 MCP attachments는 **name+text뿐**이며 server path 필드를 보내지 않았다. outgoing 기록은 `input_source=caller-inline`, `sources={}`이다. incoming 사본 owner는 실제 reviewer CID, outgoing owner는 실제 sender CID이며 home hash도 해당 native runtime과 맞았다. server가 claimed 원경로를 열거나 source 권한을 대신 확보한 증거는 없다.

MCP는 전달된 inline bytes의 원경로를 검증할 수 없다. 따라서 “제외 자료를 native 모델이 보내지 않았다”와 “서버가 그 원경로의 제외를 강제했다”는 다른 사실이다. MCP의 이름/원경로 exclude 집행 보장은 이 표본에서 **unknown/미관측**이며 허구의 거절을 만들지 않았다.

실제 CLI send/ask 원경로 시도는 **0회**다. 모델은 정상 factory MCP 공유를 완료했고 CLI의 신원·저장·전송 권한 전제를 확인하지 않았다. 이를 CLI permission denial·미지원·성공 중 어느 것으로도 단정하지 않는다. 원경로 민감 이름/제외 경로의 CLI 차단과 CLI/MCP 쌍대 digest는 여전히 native 빈 셀이다. 기존 symlink/Unicode 충돌 fixture는 재실행하지 않았다.

## 실제 수신·최종 회신

MCP tools/call은 12회이며 `xsm_files` 4회 중 1회는 manifest, 3회는 실제 incoming entry content 읽기다. reviewer는 source 원경로를 열지 않고 catalog·제품 skill과 받은 사본만 읽었다. 실제 사본 문자열에서 독립 SHA 계산 결과도 MATCH였다.

원 질문에 `kind=reply`, 원 reply_to, `outcome=succeeded`인 실제 회신 1건이 질문 인덱스에 있다. 요청/회신 canonical 2건 모두 실제 actor의 ACK와 token/receiver를 대조했다. evaluator의 수동 ACK·본문 중계·index 보정은 0이다. 공유/같은 서버 thread 격리 성공은 주장하지 않는다.

## 실패·한계·보존

- 준비 script 생성 중 UTF-8 stdin SyntaxError가 1회 있었으며 모델 시작 이전이다. 원 note를 보존하고 UTF-8 data/ASCII escape로 준비를 완료했다. provider/tool-host 재실행으로 숨기지 않았다.
- sender의 policy/config 탐색 `rg` 한 command가 `.codex` 디렉터리 부재로 exit 2였다. 실제 attachment read 거부와 구분한다. RPC isError는 0이다.
- profile `config.toml` hash drift가 관측됐고 변경 주체는 미확정이다. profile 불변으로 과장하지 않는다. 실제 evaluator/model command에 profile/권한 수정 명령은 없다. frozen source는 전후 일치했다.
- mode000 원문은 setup 뒤 audit/manifest 작성에서도 다시 열지 않았다. 해당 최종 bytes hash는 재읽기 증거가 아니라 setup 때 알고 있던 기대 hash로 표시한다. mode는 0으로 보존했다.

raw native stdout/stderr·wire·state·marker oracle·source metadata는 `/private/tmp/material-boundary-native-e36_3_p2`에 보존했다. 공개물에는 marker 원값·claim token·ACK payload를 복사하지 않는다. 소유 CLI/실제 Codex/proxy/MCP PID와 시작 시각으로 종료를 확인했고 잔여 known process는 0이다. 자료 원본/미확인 기록을 삭제해 성공시킨 것이 아니며 source/기존 사용자 파일/전역 정책은 수정하지 않았다.

이 한 조건으로 실행 가능한 MCP 양성과 OS read 음성을 완료했으며, 제외 API/CLI 빈 셀은 미완으로 남긴다. 추가 native 조건·권한 우회·source 수정 없이 종결했다.
