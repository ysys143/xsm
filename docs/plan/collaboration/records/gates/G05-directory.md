# G05 업무 디렉터리

- 상태: **passed — B03 로컬 계약**. Opus 1차 지적을 수정하고 코디네이터가 재현·영향 검사·최종 전체 회귀로 종결했다.
- 진입: G01/G02 passed. 기준은 spec P05와 Accepted ADR-0024.

## 구현

- 후보는 명시 공개 또는 동일 git common repository의 폴더/linked worktree 합집합이다. 공통 origin URL/폴더명만으로 다른 clone을 자동 편입하지 않는다.
- publish/withdraw는 runtime·정규 home·native conversation에 결속한다. 공개는 통신 허용이 아니다. CLI/MCP 공개 API는 실제 사용자 지시를 원문으로 소비하고, 선택 권한·링크를 만들지 않는다.
- raw registry에서 머신·정책·제외·후보 조건을 먼저 고르고 native title/plan/TodoWrite·branch·활동·수신 능력을 bounded head/tail로 읽는다. extra LLM/전체 transcript scan은 없다.
- 값·출처·관측 시각·freshness·unknown을 구분한다. 표시 freshness 300초는 구현용 관측 힌트이며 권한·공개·보존 만료가 아니다. native title 실패의 hook-name fallback은 record.updated와 unknown freshness를 표시한다.
- target=candidate:<full hash>는 실제 구현한 주소다. 호출자의 현 visibility/exclusion, 양끝 신원, native 교체, registry generation을 다시 대조해 원래 native 대상만 해석한다. 공개 철회 뒤 옛 후보를 조용히 다른 대상에 연결하지 않는다.
- 절대 home/path는 후보 출력에 나오지 않는다. home_id·source·native conversation·is_self를 제공한다. 같은 이름/짧은 ref 충돌도 full endpoint hash로 구분한다.
- shared excluded(path)는 realpath/symlink/없는 하위 경로에 같은 의미다. registry 신규 등록/기존 목록에 연결했고, 빈 제외 설정은 기본 발견 예산에 directory probe를 더하지 않는다. 첨부 읽기의 실제 소비는 P06 종결 셀로 유지한다.
- Claude hook의 transcript_path를 own home 안의 검증된 포인터로 저장한다. metadata 추출 실패는 기본 통신을 막지 않는다. 원격 머신 필터는 unknown/remote_discovery_unverified이며 로컬 성공을 맥미니 성공으로 바꾸지 않는다.

## 실행 증거

- 실제 CLI 및 Claude MCP discover(work=reviewer)에서 same_repo/main/reviewer 후보를 반환했다. 부분 native source가 미확정이면 전체 결과 status=unknown을 숨기지 않았다. 같은 candidate 주소로 실제 핸드셰이크·작업 회신까지 확인했다.
- Git/SQLite/native transcript 격리 fixture에서 공개 합집합/미공개 누출/동명/home/ref 충돌/별도 clone/linked worktree/rename/resume/pid 재사용/truncate·replace/unknown 스키마·예산 소진을 실행한다.
- tests/test_directory_contract.py의 기존 skip을 실제 공통 제외 검사로 전환했다. 이는 등록·목록 및 첨부용 공통 판정의 검사이며, 아직 없는 P06 첨부 송신을 실행했다고 주장하지 않는다.
- tests/test_directory_interfaces.py에서 실제 사용자 지시→CLI 공개→후보 주소 해석→철회와 같은 MCP 목록, 폴더 통신 범위 불변을 검사한다.
- 사람이 읽는 격리 표본은 a1/main “opencodex 설정 적용”, a2/main “설정 변경 리뷰”였다. 사용자가 2026-10-28 질문 call_46579cc639784216a0306d1ac3c66792에 “충분하고 공개 범위에 맞음”이라고 답했다. 실제 a1/a2 세션을 공개한 것은 아니다. 증거 `deliverables/b03-live/directory-samples.json`, `human-review.json`.

## 종결 범위

로컬 P05 게이트이며 A17/A24의 원격·첨부·전체 설치 조합은 지정된 후속 게이트에서 종결한다. 전체 70개 수용 조건 완료와 구분한다. 기술 source/권한 근거가 unknown이면 이를 표시하며, 연결 권한을 metadata 존재나 peer 계보에서 추론하지 않는다.

## Opus 검토 1차와 수정 라운드

1차 판정은 수정 필요였다(`/tmp/b03-opus-review.log`). 공개의 fail-closed 결과를 기본 등록/통신에 그대로 적용한 잘못을 고쳤다.

- `exclusion_status`는 included/excluded/unknown을 구분한다. 공개·발견의 `excluded` wrapper는 unknown에도 공개하지 않는다. registry는 확정 excluded만 필터하고 unknown은 별도 관측값으로 보존해 기본 등록/이름 해석/통신을 없애지 않는다. 유효한 확정 match는 다른 잘못된 항목 때문에 해제되지 않는다.
- 존재하지만 깨졌거나 비객체인 CONFIG는 공개 정책 unknown이다. 파일 부재의 정상 defaults와 구분한다. 기본 통신의 기존 config.load fallback은 유지한다.
- 잘못된 root/glob·예산 0 조건은 전체 포인터를 제외로 바꾸지 않는다. 빈 설정은 기존 탐색 비용을 유지한다.
- Codex/Claude adoption 전 경로에서 upsert의 제외/registered=False placeholder를 저장하거나 authoritative identity로 반환하지 않는다. 기존 잘못된 placeholder도 raw/by_session/beacon reader에서 주소로 승격하지 않는다.
- 전수 검사에서 registry 밖 `workers._register_named_thread`의 재저장 한 곳을 추가로 발견해 같은 가드를 넣었다. 실제 owned native thread ID는 보존하되 거절된 공개 포인터는 만들지 않는다. 새 worker 기능을 시작한 것이 아니라 기존 등록 consumer의 우회를 닫은 것이다.

반례와 경로 검사는 tests/test_directory.py, tests/test_directory_contract.py, tests/test_worker_directory_registration.py에 있다. source 함수 전수 확인 범위는 registry의 upsert/adopt_codex_thread/adopt_open_codex/adopt_claude 계열 및 외부 호출 receive.register/workers._register_named_thread다.

## 최종 판정

Python 3.14.6: Ran 1305 / OK (197.353s), Python 3.9.6: Ran 1305 / OK (221.689s). 로그 `/tmp/b03-close314.log`, `/tmp/b03-close39.log`. 두 실행 사이 제품·테스트 소스 hash 변경 0개를 대조했다. `deliverables/b03-live/closure.json`에 지적별 검사와 source hash를 결속했다. Opus의 첫 판정은 수정 필요였으며 이를 Opus 통과로 바꾸어 인용하지 않는다. 최종 기술 판정자는 코디네이터다. 후속 단계의 종결 셀과 전체 70개 완료는 별개다.
