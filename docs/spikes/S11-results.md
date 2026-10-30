# S11 결과: 여러 에이전트가 함께 고치는 마크다운 보드

- 실행일: 2026-10-30
- 계획: [S11-markdown-board-plan.md](S11-markdown-board-plan.md)
- 실행 범위: 시나리오 4개 × 5회 = **20/20회**, 매회 Claude 하네스 2개와 Codex 하네스 1개, 본 실행 **60회**. 계획서는 변경하지 않았다.
- 측정 결과: 최종 lost update **0건**, 편집 실패 **7건** 모두 재읽기 후 재편집. 별도 워크트리의 B 반영 **0/5**, 공통 절대 경로의 B 반영 **5/5**.
- 이상치: Codex 1회가 올바르게 제공된 경로를 잘못 재구성해 게시하지 못했다. 최종 담당 표식은 **59/60개** 남았으며, 이 미작성 1건을 lost update로 세지 않았다.
- 구조 손상 보완: S11-4-r4의 Codex가 `## 담당: C` 제목을 자기 표식이 들어간 제목으로 바꿨다. 기존 표식의 유실과는 다른 **구조 손상 1건**이다. Claude/Codex를 분리하면 셸 쓰기는 각각 **0/50**, **4/19(약 21.05%)**다.
- 모델: 본 실행 60회 모두 OCX에서 `provider=openai`, `servedModel=gpt-6-luna`를 확인했다. 요청·시도에 다른 모델로의 대체는 관측되지 않았다.
- 제약 판정: **설정·권한을 실행 중 바꾸지 않는 조건은 충족하지 못했다.** Codex가 임시 프로젝트 trust 항목 20개를 실제 프로필에 자동 기록했다. 해당 블록만 제거해 실행 전 바이트와 같은 해시로 원복했다. 측정 20회는 끝났으나, 위임의 경계를 완전히 준수한 성공으로 보고하지 않는다.

## 1. 하네스·모델·실행 경로

실행 도구와 조건은 [설정 기록](../../deliverables/s11-markdown-board/preflight/setup.json), 각 셀의 `A/B/C-command.json`에 있다. A·B는 실제 Claude CLI, C는 실제 Codex CLI이며 도구나 파일 편집 결과를 스크립트로 대신 만들지 않았다.

| 항목 | 사용한 조건 |
|---|---|
| Claude 요청 모델 | `ocx-claude-native--gpt-6-luna` — OCX의 native Luna route alias |
| Codex 요청 모델 | `openai/gpt-6-luna` |
| 실제 응답 근거 | native session에 결속한 OCX conversation hash의 `servedModel`, provider와 시도별 model |
| 인증·전송 | 기존 Claude/Codex 구독 인증 → 이미 실행 중인 loopback OCX → OpenAI ChatGPT subscription backend. 자격 증명 복사·API 키 주입 없음 |
| 모델 선택 확인 | live 목록의 `gpt-6-luna [native, enabled]`, messages→responses 및 responses→responses 경로 확인 후 실제 사전 호출 |
| 추론 effort | 양쪽 하네스에 low를 요청. 설정 파일 대신 실행 인자로 지정 |
| 파일 작업 권한 | Claude `acceptEdits`, Codex `workspace-write`. 공통 보드에는 시험용 shared 경로만 추가 |
| 사용자 커스터마이징 | Claude safe-mode·빈 setting sources·빈 strict MCP, Codex ignore-user-config. 파일 편집 도구 종류는 지정하지 않음 |
| 세션·입력 | 새 native session, Claude no-session-persistence와 Codex ephemeral. stdin은 DEVNULL, 프롬프트 앞에 명시적 `--` 경계 |

모델 확인은 모델에게 이름을 물은 자기 보고가 아니다. Claude의 session metadata 해시와 Codex의 thread ID 해시를 OCX의 conversation ID와 결속했다. 본 실행 60개에 연결된 OCX 요청 254개의 응답·시도 메타데이터를 보존했다. 각 셀 `*-result.json`의 `model_evidence`와 [전체 결속 색인](../../deliverables/s11-markdown-board/validation.json)을 따른다. SDK가 출력한 비용 추정값을 실제 API 과금액으로 해석하지 않는다.

사전 호출은 본 실행에 포함하지 않는다. Claude 3회·Codex 1회가 있으며 로그를 모두 [preflight](../../deliverables/s11-markdown-board/preflight)에 보존했다. 첫 임시 Claude 프로필은 로그인 부재로 실패했다. 다음 호출에서는 variadic 옵션·stdin 때문에 프롬프트 전달 검사가 실패했다. 기존 구독 인증, DEVNULL, 명시적 옵션 경계로 고친 Claude 호출에서 지정 응답과 Luna route를 확인한 뒤 본 실행을 시작했다. 다른 모델·하네스로 대체하지 않았다.

## 2. 시험 배치와 측정 방법

매회 새 임시 Git 저장소와 초기 보드를 만들었다. S11-3/4에는 같은 임시 저장소에서 A·B·C 워크트리를 각각 만들었다. 임시 저장소의 초기 commit은 워크트리 배치를 위한 준비이며 xsm 저장소에는 commit·push하지 않았다. 사용자 프로젝트는 시험 대상으로 사용하지 않았다.

세 프로세스는 매회 같은 barrier에서 시작했다. 작업 지시는 항목과 넣을 표식만 지정하며 Edit·Write·apply_patch·셸 중 쓰기 방식을 지시하지 않았다. 다른 참여자가 쓴 내용의 의미 모순은 평가하지 않았다.

S11-2의 외부 삽입기는 성공한 보드 Read를 관측한 뒤 반복별 고정 seed에서 뽑은 약 30–200ms 지연 후 결정 항목에 한 줄을 삽입했다. 삽입 전후 원문·SHA·시각을 기록했고 실제 삽입은 **5/5회** 발생했다. 삽입기 자체도 read/replace 방식이며 에이전트와 파일 잠금을 공유하지 않는다.

S11-3/4에서 B는 A 실행 종료를 알리는 공통 준비 파일 뒤에 자기 보드를 읽도록 했다. 준비 파일과 B 프롬프트에는 A의 무작위 결정값을 넣지 않았다. 이는 시작 시점 차이를 이력 비공유로 오판하지 않기 위한 읽기 순서 제어이며, 보드 쓰기 방식은 지정하지 않았다. C는 자기 담당 항목을 갱신했다.

lost update는 최종 파일에서 빠진 표식 중 **중간 스냅샷이나 성공한 쓰기 결과에서 실제로 기록됐음을 확인한 것**만 센다. 쓰지 못한 표식은 별도 미작성으로 센다. 보드는 5ms 간격으로 관측했으므로 그보다 짧은 일시적 쓰기를 전부 보았다고 주장하지 않는다. [분석기](../../deliverables/s11-markdown-board/analyze_s11.py)는 기록 후 표식을 지우는 변이를 검출하고, 한 번도 쓰지 않은 표식을 lost update로 오인하지 않는 대조를 수행했다.

## 3. 시나리오별 수치

| 셀 | 완료/계획 | 모델 확인 | 최종 lost update | 미작성 | 편집 실패 | B가 자기 담당 항목에 A 결정을 반영 |
|---|---:|---:|---:|---:|---:|---:|
| S11-1 같은 체크아웃·자기 담당/진행 | 5/5 | 15/15 | 0 | 0 | 0 | 해당 없음 |
| S11-2 같은 결정 항목·외부 삽입 | 5/5 | 15/15 | 0 | 0 | 7 | 해당 없음 |
| S11-3 별도 워크트리·각자 보드 | 5/5 | 15/15 | 0 | 0 | 0 | 0/5 |
| S11-4 별도 워크트리·공통 절대 경로 | 5/5 | 15/15 | 0 | 1 | 0 | 5/5 |
| 합계 | **20/20** | **60/60** | **0** | **1** | **7** | S11-3/4 각각 위와 같음 |

20개 셀의 하네스는 모두 정상 종료 결과를 반환했지만, 정상 종료는 실제 편집 성공과 다르다. S11-4-r1의 C는 읽기 경로 오류 뒤 작업을 포기해 자기 표식이 없다. 이를 하네스 정상 종료로 숨기지 않는다.

분석 결과는 [analysis.json](../../deliverables/s11-markdown-board/analysis.json)에 있다. B의 반영은 공유 보드 어딘가에 A 값이 있는지가 아니라 **담당 B 항목 안에 그 값을 썼는지**로 판정한다. 실행기의 임시 summary 필드 `B_reflected_A`는 파일 전체를 확인하므로 S11-4의 반영 증거로 사용하지 않는다. 분석기는 “A 값은 다른 항목에 있으나 B에는 NOT_SEEN”인 음성 대조를 거부한다. 원 summary는 보존하고 최종 판정에는 `B_reflected_in_B_section`을 썼다.

## 4. 쓰기 방식과 실패 뒤 행동

| 셀 | Claude Edit 성공 | Codex patch update 성공 | 파일 전체 Write 성공 | 셸 쓰기 성공 | Edit 실패 |
|---|---:|---:|---:|---:|---:|
| S11-1 | 20 | 5 | 0 | 0 | 0 |
| S11-2 | 10 | 3 | 0 | 2 | 7 |
| S11-3 | 10 | 4 | 0 | 1 | 0 |
| S11-4 | 10 | 3 | 0 | 1 | 0 |
| 합계 | **50** | **15** | **0** | **4** | **7** |

성공한 보드 쓰기 도구 호출은 69회다. 파일 전체 Write·셸 쓰기의 합은 4회로 **4/69 = 약 5.80%**다. 실패한 7회까지 포함한 쓰기 시도는 76회이며 같은 분자는 **4/76 = 약 5.26%**다. 핵심 동시 편집 셀 S11-1/2만 보면 성공 쓰기는 40회, 셸 쓰기는 2회로 **5.00%**다. 분모를 혼용하지 않는다.

하네스별 분리가 중요하다. 아래 수치는 기존 로그 재분석이며 모델을 다시 호출하지 않았다.

| 하네스 | 성공 쓰기 | Edit | patch update | Write | 셸 쓰기 | 성공 쓰기 중 전체·셸 비중 |
|---|---:|---:|---:|---:|---:|---:|
| Claude | 50 | 50 | 0 | 0 | 0 | 0/50 = 0% |
| Codex | 19 | 0 | 15 | 0 | 4 | 4/19 = 약 21.05% |

따라서 전체 평균 5.80%가 각 하네스에서도 10% 미만임을 뜻하지 않는다. Codex 표본은 계획서의 제안 기준을 넘는다. 제목 구조도 별도로 전수 확인해 공유 보드 1개에서 `## 담당: C`가 사라진 것을 확인했다. [하네스·구조 재분석](../../deliverables/s11-markdown-board/harness-and-structure-supplement.json)

7건의 Edit 실패는 모두 S11-2에서 `File has been modified since read … Read it again before attempting to write it.`로 거절됐고, 모두 보드를 다시 읽은 뒤 Edit로 갱신했다. 이 실패 뒤의 전체 덮어쓰기·셸 우회는 **0건**, 성공 재시도 없이 끝난 편집 실패도 **0건**이다. Codex에서 같은 편집 실패를 관측한 것은 아니므로 Codex도 같은 stale-read 검문을 한다고 결론 내리지 않는다.

4건의 셸 쓰기는 Python의 `read_text`/`write_text`로 내용을 바꾸는 방식이었다. 모두 Codex 실행이며, 실패한 Edit 뒤의 우회가 아니라 처음 택한 쓰기 방식이다. 결과에는 보존됐지만 읽기와 전체 파일 쓰기 사이의 경쟁 가능성은 남는다.

Codex JSONL의 `file_change`는 업데이트 대상과 성공 상태를 보여 주지만 patch hunk 전체를 노출하지 않는다. 위 15건은 도구 수준의 patch-update 분류다. 모든 patch가 항목 범위만 건드렸음을 이 로그만으로 증명하지 않는다. 같은 항목을 다루는 Edit 역시 모든 가능한 경쟁 조건에 대해 원자적인 다중 작성자 병합이라는 뜻은 아니다.

## 5. 가설별 판정

| 가설 | 판정 | 근거와 제한 |
|---|---|---|
| H1 다른 항목 동시 편집의 보존 | 이번 표본에서 지지 | S11-1 5회, 담당·진행 표식 모두 보존. 장시간·큰 보드에 대한 무손실 보장은 아님 |
| H2 충돌 실패 후 재읽기·병합 | 관측한 실패 경로에서 지지 | S11-2 stale Edit 실패 7건 모두 재읽기 후 Edit 성공. 동시 시작이 모든 편집의 실제 경합이나 Codex의 실패 경로까지 증명하지는 않음 |
| H3 항목 편집 위주 | 하네스별로 다름 | Claude 셸·Write 0/50. Codex 셸 4/19로 제안된 10% 기준 초과, 제목 구조 손상 1건. Codex hunk 범위 미노출로 의미상 항목 편집 전수 증명도 아님 |
| H4 별도 워크트리는 서로의 변경을 보지 못함 | 이번 배치에서 지지 | A 결정은 각 A 보드에 남았으나 B 반영 0/5. 보드의 원격 Git 동기화는 시험하지 않음 |
| H5 공통 절대 경로가 다음 작업의 관측을 연결 | A→B 경로에서 지지 | B 담당 항목의 실제 결정 반영 5/5. C의 경로 오독 1건은 별도 실패로 유지 |

**10%는 계획서의 제안값이며 사용자 결정이 아니다.** 전체 집계에서는 최종 lost update 0·전체/셸 비중 5.80%지만 Codex만 보면 21.05%로 제안 기준을 넘는다. 표식이 남아도 제목 구조가 손상될 수 있었으며 경로 오독 1건과 프로필 trust 변경도 있었다. 전체 평균만으로 이 방식을 쓸 만하다고 판정하지 않는다. 마크다운 보드 채택, 새 채널 기능의 불필요, 장기 협업 안정성은 확정하지 않는다.

## 6. 이상치와 설정·권한 경계 위반

### S11-4-r1 C의 경로 오독

입력에는 올바른 `…/xsm-s11-va4hq9ed/cases/S11-4-r1/shared/BOARD.md`가 있었다. Codex는 이를 `…/xsm-s11-4-r1/shared/BOARD.md`로 재구성해 `rg`를 실행했다. 두 번의 조회가 실패한 뒤 보드를 갱신하지 못했다고 보고했다. 임의의 다른 파일을 덮어쓰거나 실제로 쓴 표식을 잃은 경우는 아니다. [프롬프트](../../deliverables/s11-markdown-board/S11-4-r1/C-prompt.txt) · [실제 도구 로그](../../deliverables/s11-markdown-board/S11-4-r1/C.jsonl)

### S11-4-r4 C의 제목 구조 손상

Codex는 자기 담당 항목의 본문 대신 제목 `## 담당: C` 자체를 `## 담당: S11-4-r4-C-1dd60504afc7`로 치환했다. 표식은 남았지만 기대한 항목 제목은 없어졌고 본문은 `대기.`로 남았다. lost update 0이라는 판정과 분리해 구조 손상 1건으로 기록한다. [실제 도구 로그](../../deliverables/s11-markdown-board/S11-4-r4/C.jsonl) · [최종 보드](../../deliverables/s11-markdown-board/S11-4-r4/after-C.md)

### Codex trust 항목 20개의 자동 기록과 원복

Codex는 `--ignore-user-config`·`--ephemeral` 호출에서도 현재 프로필 config에 시험용 경로 20개를 trust 항목으로 기록했다. 실행 인자의 설정 override가 파일에 남지 않을 것으로 기대했으나, trust 기록의 별도 부수 효과를 사전에 차단하지 못했다. 따라서 실행 중 설정·권한 불변 경계를 위반했다.

영향 범위를 전수 확인했다. 해당 임시 저장소 경로의 **20개 프로젝트 블록만 제거한 후보가 실행 전 config SHA-256과 바이트 단위로 일치**했다. 그 일치를 확인하고 다른 동시 변경이 없는지를 재검사한 뒤 해당 블록만 원복했다. Claude settings와 OCX config도 실행 전후 해시가 같다. 현재 프로필 세 파일은 모두 기준 바이트로 돌아왔지만, 중간 위반 사실은 취소되지 않는다. [영향·복구 기록](../../deliverables/s11-markdown-board/codex-trust-side-effect.json) · [최종 확인](../../deliverables/s11-markdown-board/validation.json)

`ocx claude` 사용자 래퍼의 조회가 상태줄 설치기를 호출하는 점도 발견했다. 대상 프로필의 dry-run 결과는 둘 다 unchanged였고 이번 호출의 새 백업은 없었다. 이후 실제 모델 실행은 해당 래퍼를 거치지 않았다. 첫 실패 사전 호출의 OCX cache·agent 정의는 시험용 임시 Claude config 안에만 만들었다.

임시 프로필·저장소·실패 로그는 보존했고 사용자 프로젝트와 기존 xsm 코드·문서·계획서는 편집하지 않았다. 이 결과 문서와 지정된 deliverables 디렉터리만 추가했다. 중간 설정 위반 때문에 위임의 최종 회신은 `outcome=failed`로 하며, 이는 20회 측정이 미실행됐다는 뜻이 아니라 모든 경계를 준수한 성공을 주장하지 않는다는 뜻이다.

## 7. 근거와 재현 범위

- [실행기](../../deliverables/s11-markdown-board/run_s11.py): 임시 저장소·동시 시작·삽입·native JSONL·보드 스냅샷 수집.
- [분석기](../../deliverables/s11-markdown-board/analyze_s11.py): 도구 종류·실패 뒤 행동·관측된 기록의 유실·B 항목의 반영을 판정.
- [전체 분석](../../deliverables/s11-markdown-board/analysis.json): 셀별 표식·도구 호출·실패 내용·시작 시각 차이.
- [모델·파일·개수 검증](../../deliverables/s11-markdown-board/validation.json): 60개 native 실행과 OCX 응답의 결속, 최종 프로필 해시, 계획서 해시.
- 각 `S11-*-r*` 디렉터리: 시작·종료 보드, A/B/C 프롬프트·명령·stdout JSONL·stderr·결과, 외부 삽입 전후와 시각, 중간 스냅샷.

실행기는 Codex trust 부수 효과가 관측된 그대로 보존했다. **격리된 프로필·인증 경로를 별도로 검증하기 전에는 같은 실행기로 추가 모델 실행을 반복하지 않는다.** 분석기는 기존 로그만 읽으므로 다음 명령은 모델을 호출하거나 설정을 바꾸지 않는다.

```sh
python3 deliverables/s11-markdown-board/analyze_s11.py deliverables/s11-markdown-board
```

의미 모순, 사람의 동시 편집, 머신 간 Git 충돌, 장시간·큰 보드의 컨텍스트 비용, 대화형 세션, 다른 모델·하네스의 동작은 미실행이다. 이번 관측을 그 범위의 검증으로 확대하지 않는다.
