# B05 — 자료·소유 실행·설치와 출처 제어의 로컬 통합

- 판정: G06·G08·G09·G10의 **로컬 기술 계약 통과**. 전체 70개 조건과 원격/UI 여정 완료 판정은 아니다.
- 고정본: `deliverables/b05-live/final-source-manifest.json`의 파일별 SHA-256 및 snapshot.
- 전체 회귀: Python 3.14 1648개 / 309.054초 / OK (`/tmp/b05-r3-314.log`), Python 3.9 1648개 / 424.796초 / OK (`/tmp/b05-r3-39.log`). 두 버전 모두 skip 없이 실행했다.
- 실제 사용자 환경의 전역 설치·설정·권한을 바꾸지 않은 평가다. 실제 native 프로필 인증을 재사용했고 별도 API 키 과금 경로는 쓰지 않았다.

## G06 — 자료 사본

CLI 입력은 CLI 자신의 OS 읽기 권한을 사용한다. MCP 입력은 이미 읽은 inline 내용 또는 같은 native 대화가 이미 읽어 만든 private 사본이다. 명시한 manifest 재사용은 같은 버전의 사본만 내보내며 원 경로를 다시 읽지 않는다. 새 CLI 경로 입력은 승인 대기 중 원본이 바뀌면 거절한다. raw path를 MCP에 전달해 서버의 읽기 권한을 얻는 경로는 없다.

- `test_files`, `test_materials`, `test_file_interfaces`에서 body/request/manifest/owner 결속, symlink 교체·Unicode 이름 충돌·한도·disk full·재시작·명시 fallback·만료 정리와 원본 보존을 실행했다.
- 실제 Codex 기본·비기본 홈과 Claude에서 사본 안에만 둔 무작위 token을 `xsm_files`로 읽고, ACK 후 원 요청에 회신했다. `deliverables/p06-live/native-files.json`, `native-claude-files.json`에 실제 native ID·tool call·원문 결과를 보존했다. Claude의 permission_denials는 0개다.
- 사용자 승인 기본값은 1MiB/file, 4MiB/request, 16개, 256MiB 저장, 사본 7일이다. housekeeping은 이 모듈의 만료 사본만 정리하며 원 경로·메시지 정본은 정리하지 않는다.
- 원격 자료 운반은 G12에서 검증할 부분이다. 미지원 peer에는 자동으로 내용을 바꾸어 보내지 않는다.

## G08 — 소유 실행

`owned`/`xsm_owned`의 create/run/status/retry/reconcile은 실제 journal 경로에 연결했다. 요청 확인·실행·답 저장·회신을 분리하며, sender/work 단위의 문맥과 동일 단위 직렬화를 적용한다. 일반 세션을 소유 서비스로 전환하지 않는다. 기존 scope·framework·dangerous grant 규칙을 유지했다.

- 실제 Claude·Codex에서 2턴 같은 native ID와 무작위 token 기억을 확인했다. 두 런타임 모두 기본 MCP inbox를 호출했다(`deliverables/p08-live/native-memory.json`).
- 실제 Codex 부모가 MCP `xsm_owned`로 자식을 만들고 2회 호출했다. 별도 일반 부모 대화도 resume 후 자기 값을 기억했다(`native-owned-mcp.json`). 자식의 두 번째 JSON에는 outcome이 없어 과제 finality는 unknown으로 남겼다. 기억값 확인과 과제 성공 판단을 합치지 않았다.
- 실제 native 자식 4개 동시 존재, 다섯 번째 queued/overloaded·미실행, 같은 ID의 재개를 확인했다(`native-capacity.json`). 429 재연결 진단 뒤 완료된 3건을 old parser가 unknown으로 남기는 반례를 고쳤고, 기존 stdout에서 모델 재실행 없이 회수했다(`native-capacity-readback.json`). native 실행 수는 5회로 유지했다.
- 실제 SIGKILL 5경계·별도 controller 경쟁·문맥 격리·저장 답 재사용·회신 ID 보존·scope 철회를 검사했다. 부작용 exactly-once는 보장하지 않는다.
- MCP overload 뒤 같은 ID 재입장과 이름이 같은 새 worker의 cache 혼동을 별도 공개 인터페이스 반례로 실행했다. worker 메타데이터 제거 뒤에도 자기 요청의 답을 status로 읽고 다른 홈은 읽지 못한다.

일반/소유·각 프로필의 실제 실행 조건은 JSON별로 구분했다. 표본의 성공을 모든 native TUI 상태·모든 조합의 성공으로 확대하지 않는다.

## G09 — 출처와 반복 제어

P01/P02의 caller certainty·원 요청·사용자 판단 결속을 유지하며, body와 표시 metadata를 분리했다. 원문·canonical digest는 보존하고, 이름·reply-to·branch·오류·첨부 이름의 제어 문자와 프레임을 표시 데이터로 다룬다. 보충면 Cf codec roundtrip도 검사했다.

- 공개된 실제 일반 native 두 프로필이 부모 중계 없이 반례→수정→재검토 3라운드의 ask/reply·ACK를 완료했다(`deliverables/p09-live/results.json`, `results.md`). 실제 tool 오류·권한 거절은 0개다.
- 기본은 observe다. 새로운 반복 차단 기본값이나 전역 strict 설정을 켜지 않았다. 명시 config의 strict만 한도를 적용하며, unknown 상태는 observe 진단과 strict 보류를 구분한다.
- 실제 receive 경로의 한도·재개 검사는 `test_traffic_interfaces`에 있다. 같은 ID의 읽기 전용 조회는 새 메시지로 세지 않는다. 보류 원문은 보존하고 시간이 지난 명시 재전송은 같은 ID로 처리한다. 이 사유를 새로운 통신 허용 요청으로 바꾸지 않는다.
- 설정 오류는 마지막 유효 정책의 기존 통신을 유지하고 새 grant를 중지한다. snapshot·CAS·저장 장애·시간 역행 반례를 실행했다.
- journal 전체 스캔과 무기한 진단 이력 성장은 검토의 Low로 남는다. 새 보존 정책을 임의로 정하지 않았다.

원격 origin·가입/제명·remote user decision은 G12 범위로 남으며 machine 인증을 사람 승인으로 보장하지 않는다.

## G10 — 설치와 관측

- 실제 CLI plan/apply/readback에 flow ID·target·generation을 연결했다. 설정 후속 편집·부분 실패·flow 교체·mode·소유 항목 보존을 검사했다.
- named matrix는 두 Python의 40개 기본 셀＋7개 오류/업그레이드 셀로 총 94개다(`deliverables/p10-live/matrix.json`). 이 셀의 첫 LLM 왕복은 unknown이며, filesystem 셀을 native 모델 실행으로 세지 않는다.
- 실제 old snapshot MCP PID 18595와 같은 native 대화를 유지하면서 private CURRENT를 교체·prune한 뒤, 원 요청에 대한 답 2개를 받았다. old snapshot은 보존됐다. 별도 new-prefix 왕복도 확인했다(`native-upgrade.json`, `native-upgrade.md`). 추가 new-prefix 조건은 MCP 회신까지의 관측이며 native 최종 turn.completed로 확대하지 않았다.
- setup 첫 왕복은 새 유효 질문의 실제 상관 회신이 들어올 때만 기록한다. doctor는 저장된 질문/회신을 재확인하고 관측 시각을 표시한다. 이전 flow의 요청·답은 새 설치를 완료시키지 않는다. fixture 증거는 fixture로 남고, 관측 실패는 정상 회신을 숨기지 않는다.
- 제품 진단의 내부 G04/G10·계획 단계 문구를 제거했다. 공급 checksum·signature·license는 관측하지 못한 것을 unknown으로 유지한다.

기존 지원 약속·자동 교체·백업 보존 약속은 이번 구현이 임의로 확장하지 않았다. 사용자 설치 적용과 필수 native hook 신뢰 등 실제 사용자 권한 판단은 별도 경계다.

## Opus 5.5 검토와 지적 종결

1차 통합 검토(`deliverables/b05-live/opus-review.md`)는 Medium 3건으로 수정 필요였다. reviewer는 읽기 전용이며 SHA/실행 로그의 독립 검증은 하지 않았다. 이를 최종 통과 판정으로 바꾸어 인용하지 않는다.

| 지적 | 수정·반례 |
|---|---|
| M1 queued 캐시·worker 세대 | 동기 submit으로 ID/body/worker 검증 후 job을 시작한다. 완료 job을 제거해 같은 ID가 실제 journal 상태로 재입장한다. MCP overload 회복·worker 재생성 반례 red→green |
| M2 이미 종료된 unknown이 슬롯 점유 | 확인된 종료는 실행 슬롯에서 빼며, unknown side effects와 같은 문맥의 fencing은 남긴다. 확인 불가 child는 별도로 보존한다. 자동 모델 재실행·idle 퇴출은 하지 않는다 |
| M3 cleanup 중단의 전역 수신 장애 | atomic tombstone 삭제·재개, legacy 손상 폴더 진단 격리, 보수적 실제 사용량 계상. 실제 SIGKILL·다른 owner 수신·quota 회피 반례 |
| C1 공개 history 회수 | worker record가 없어도 자기 native sender의 저장 답은 조회. 다른 홈/대화 조회 거절 |
| C2 실제 관측 연결 | 검증된 새 reply→현재 setup flow→doctor readback 경로 실행. 오래된 질문·기록 장애 반례 |
| C3 만료 표시 | 답 없이 만료된 질문은 status에서 expired, 같은 오래된 의도로 새 창을 열지 않음. clock rollback은 새 적용으로 이어지지 않음 |
| C4 불필요한 원본 재읽기 | 이미 같은 대화가 읽은 frozen private bytes는 MCP에서 재사용. 새 원본 경로 읽기 권한으로 해석하지 않음 |

코디네이터의 M1/C1/C2/C3/C4 변이는 모두 검출했다(`review-mutations.json`). M2/M3 구현자의 변이·좁은 실행 결과도 대조했다. 별도 독립 전체 재리뷰는 반복하지 않았다.

첫 전체 1629개는 3 fail이었다. default send가 새 ID를 강제해 승인 후 crash 복구의 held ID를 잃던 회귀를 고쳤고, 이미 제공하는 attachments/wake capability를 미지원으로 기대하던 두 검사를 갱신했다. 다음 전체 1648개는 제품 진단에서 없앤 내부 gate 필드를 여전히 기대한 한 matrix의 40개 subcase error였다. 제품 변경 없이 그 fixture를 고친 뒤 두 버전 전체가 위 결과로 통과했다.

## 전체 목표의 남은 일

G07의 실제 UI 표본과 G11/G12의 선택된 원격 제품 경로·미확보 물리 환경·G13의 전체 여정은 미완이다. P11은 기존 두 머신 A/B/D native carrier와 C 격리 비교를 별도로 수행하며, 그 결과가 xsm의 원격 가입·선택·자료 운반 완료를 뜻하지 않는다. D12 backend 선택은 아직 미응답이다. 기존 scope·actual 팀·프로필·운영 서비스·배포를 임의로 바꾸지 않았다.
