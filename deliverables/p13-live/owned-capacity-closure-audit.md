# A16-08 capacity·문맥 종결 감사

판정은 부분 충족이다. 기존 실제 4+1 admission·출력 readback·5개 crash 회복·8개 기억 turn의 성공을 인정한다. 다만 이들을 합쳐 두 발신자가 같은 협력자에 동시 요청하고 각각 후속 질문한 실행이나 퇴출 뒤 실제 기억 소실을 관측했다고 말할 수는 없다.

## 원문 기준

> 두 발신자가 같은 협력자에게 동시에 요청하고 각자 후속 질문을 보낸다. 문맥 공유 단위·직렬화·퇴출 후 기억 소실·독립 검토 격리를 각각 확인한다. 설정한 용량만큼 모두 작업 중일 때 새 발신자를 추가해 요청 유실·새 워커 즉시 회수·미실행 성공 답변이 없는지 검사한다.

출처: `docs/adr/0016-agent-messaging-interface.md:73`, `acceptance.md` A16-08. 필요한 증거는 격리 fixture·별도 프로세스/장애 주입·실제 하네스다. 모든 하네스/모든 API 전수 행렬이나 자동 idle eviction을 추가 요구하지 않는다.

## 원문별 매핑

| 원문 | 판정 | 기존 증거 | 실제 미실행/구분 |
|---|---|---|---|
| 두 발신자가 같은 협력자에게 동시에 요청하고 각자 후속 질문을 보낸다. | partial | fixture test_same_context_serial_other_context_parallel_capacity_plus_one_queued는 두 sender의 동시 요청, test_same_sender_work_resumes_two_senders_jobs_and_review_stay_isolated는 sender/work 분리·한 sender 후속을 검사한다. 실제 4+1은 한 sender/여러 work, 8턴은 독립 trial의 후속이다. | 같은 협력자에 두 sender가 동시 요청하고 양쪽이 각각 후속 질문하는 원문 조합은 이 실제 raw에 없다. 서로 다른 trial의 sender 수를 합쳐 충족으로 바꾸지 않는다. |
| 문맥 공유 단위 | satisfied-implementation-and-observed-work-identity | source context key는 worker ID + native sender(runtime/home/SID) + work (+ independent request ID). fixture는 두 sender/다른 work를 분리한다. 실제 capacity는 동일 worker·sender에서 서로 다른 work 5개에 context/native ID 5개, memory 표본은 동일 단위 후속 ID 재사용을 확인한다. | 실제 두 sender 간 기억값 교차 비노출까지의 관측은 S1 조합과 함께 미입증이다. 문맥 키/fixture 검사는 이미 있다. |
| 직렬화 | satisfied-fixture-with-real-cross-work-parallelism | fixture가 같은 문맥 진행 중 후속을 context-busy로 대기시키고 다른 sender 실행을 병렬 허용한다. reserve는 context-busy/context-order를 검사한다. 실제 capacity는 다른 work의 4개 프로세스 중첩, memory는 같은 문맥의 순차 resume를 증명한다. | native 두 요청을 같은 문맥에 겹쳐 보내 대기→후속 완료한 표본은 없지만 결정적 fixture 경로는 존재한다. 이를 모든 API native 재시험 요구로 확대하지 않는다. |
| 퇴출 후 기억 소실 | satisfied-fixture-not-observed-native-retirement | test_idle_context_retirement_fresh_session_and_worker_removal_keeps_journal는 remember→명시 retirement→새 문맥에서 이전 기억 부재 및 과거 정본 보존을 assert한다. journal fixture도 새 context/native 미결속을 검사한다. 제품은 idle-only 명시 retirement이며 자동 idle eviction이 아니다. | 실제 raw의 context는 모두 retired=false다. 모델에게 값을 기억시킨 뒤 명시 retirement하고 값 재제시 없이 후속 질문해 기억 소실을 관측한 native 표본은 없다. crash/프로세스 종료/슬롯 해제는 context 퇴출이 아니다. |
| 독립 검토 격리를 각각 확인한다. | satisfied-fixture-native-independent-not-observed | fixture는 independent=True로 다른 context ID를 만들고 unknown 문맥에서도 독립 문맥을 분리한다. source가 independent request ID를 context key에 포함한다. | 검토한 실제 journal은 independent=false다. fresh review의 실제 기억 오염 유무는 이 raw에 없지만 결정적 격리 fixture를 없는 것으로 처리하지 않는다. |
| 설정한 용량만큼 모두 작업 중일 때 새 발신자를 추가해 | partial-literal-new-sender-not-exercised | 기본 용량4에서 실제 PID 4개 동시 생존 summary와 journal running 중첩, 다섯 요청 queued/overloaded→같은 ID 실행 확인. capacity 설정을 바꾸지 않았다. | 다섯 번째는 새 work의 같은 sender다. 새 sender 추가라는 원문 변수는 fixture의 두 sender 병렬 검사와 달리 이 capacity native trial에는 없다. |
| 요청 유실·새 워커 즉시 회수·미실행 성공 답변이 없는지 검사한다. | satisfied-observed-capacity-and-recovery | capacity 5개 모두 실제 turn.completed 1회·run_attempts=1·최종 reply-stored. 초기 parser unknown 3개는 저장 stdout SHA 불변 readback으로 회수됐다. 다섯 요청이 즉시 퇴출되거나 미실행 성공으로 끝나지 않았다. crash 5경계도 실제 수행 전/후 회복을 구분하고 각 native 실행1회, after-execution unknown fencing을 확인했다. | 이들 수치는 충족한 관측이다. 새 sender 조건의 미실행은 S6에만 남긴다. 일반 side effect exactly-once 보장으로 확대하지 않는다. |

## 실제 capacity 4+1

기본 용량은 4다. 최초 네 요청의 journal running 중첩 구간은 epoch `1793201639.39588`–`1793201670.46963`이며 다섯 번째 queued 시각은 `1793201639.443648`, reserved 시각은 `1793201925.744423`다. producer는 네 PID 생존을 확인한 뒤 다섯 번째를 보냈다. 초회 overloaded 응답은 summary에 남고, 별도 응답 raw 사본은 확인하지 못했다. journal 시각과 native raw가 대기 후 실행을 보강한다.

이 다섯 요청은 모두 같은 worker·같은 native sender다. work/context/native ID는 각각 5개다. 즉 실제 업무별 문맥 분리·병렬화는 있으나 두 sender 격리 실측이나 원문의 새 sender 추가와는 다르다. 다섯 요청 모두 최종 reply-stored·run_attempts=1·실제 turn.started/completed 각1회다. 초기에 unknown이던 세 요청은 아래 원본 stdout hash가 readback 기록과 그대로 일치한다. 오류 뒤 새 모델 재시도로 성공한 표본이 아니다.

| request | native ID | retired / independent |
|---|---|---|
| capacity-3879b3ac-0 | 01a18325-90a2-7700-8bf2-3ec8b8e55efc | false / false |
| capacity-3879b3ac-1 | 01a18325-90a2-7043-a98f-931518158f12 | false / false |
| capacity-3879b3ac-2 | 01a18325-90a3-7b51-b415-f26424b537ac | false / false |
| capacity-3879b3ac-3 | 01a18325-90a3-7831-a3af-ee6fc07b542a | false / false |
| capacity-3879b3ac-4 | 01a18329-ef3b-7052-813b-22aca9b73e4e | false / false |

## 5개 crash와 기존 8턴의 의미

crash 5개는 같은 worker·한 sender·서로 다른 work로 각1 native turn이다. 전후 ID/body digest/sender/work/context는 같다. 세 후반 경계는 이미 실행한 child/stdout으로 답을 회수했고, 앞 두 경계는 최초 모델 실행이었다. 모든 context가 retired=false·independent=false다. 따라서 crash 종료나 슬롯 해제를 기억 퇴출로 해석하지 않는다.

기존 8턴은 owned Claude2 + owned Codex2 + 일반 Codex 부모2 + 공개 MCP owned Codex2다. 같은 문맥 재개·기억을 보여 주지만 두 발신자가 같은 협력자에게 각 후속을 보내거나 retired/independent 문맥을 읽는 시나리오는 아니다. capacity5 + crash5 + memory8은 서로 다른 stdout 18개로 셌고 회복/readback을 새 모델 turn으로 중복 계산하지 않았다.

## fixture에 이미 있는 검증

- `test_owned_workers.py`는 같은 sender/work 재사용, 다른 sender/work와 independent context 분리, 같은 문맥 context-busy와 다른 문맥 병렬화, overload, 명시 retirement 뒤 예전 기억 부재·과거 정본 유지까지 검사한다. 모델·reply 경계는 fake다.
- `test_owned_requests.py`는 atomic reservation, queue order, retirement 뒤 새 context/native 미결속, unknown 문맥 퇴출 금지 등을 검사한다.
- 기존 final-regression의 Python 3.9.6/3.14.6 각1697개 OK 로그 hash를 확인했고 관련 네 fixture 파일을 당시 frozen source와 비교했다. 이는 기존 aggregate 실행 증거이며 이름별 개별 출력이나 실제 모델 기억 검사가 아니다. 이번에 재실행하지 않았다.

이 fixture들은 유효한 구현 증거다. 모든 축의 모델 재시험을 새 조건으로 만들지 않는다. 다만 실제 raw에서 없었던 두 sender/각 후속 조합이나 native retirement를 실행했다고 기록할 수도 없다.

## 실제 남은 공백

- M1: 실제 4+1은 한 sender, 기존 8턴도 이 두 sender/각 후속 조합이 아니다.
- M2: 명시 retirement+기억 부재 fixture는 있으나 보존된 실제 native context는 모두 retired=false. crash 회복은 대체 근거가 아니다.
- M3: 다섯 번째 요청은 새 work이나 sender는 기존 sender와 같다. native overload·readback 성공 자체는 인정한다.

독립 검토와 같은 문맥 직렬화는 결정적 fixture에 이미 있으므로 이를 구현 미검증으로 남기지 않는다. 다만 실제 independent=True raw/동일 문맥 native 경합 관측은 없다고 구분했다. A16-08 전체를 현재 실제 증거만으로 닫는 판정은 하지 않았다.

## 정확한 raw와 SHA256

전체 criterion·producer·fixture·journal·회귀 로그의 경로와 hash는 JSON의 evidence_files에 있다. 아래는 실제 native stdout과 원본 journal이다. private tmp를 이번에 복제하지 않았고 토큰/원문은 보고서에 넣지 않았다.

| 경로 | bytes | SHA256 |
|---|---:|---|
| `/private/tmp/p08-native-memory-cn0y8j6u/state/owned-requests/edb213838f65f5acef39cf4c8cdf2716f5dbb029aa4237cf0730f0e1950e178b.json` | 58809 | `b11678d6beaa44d13726a7252b0385d94e0b41405b79b91f14182bbf61c27ae1` |
| `/private/tmp/p08-native-memory-cn0y8j6u/state/owned-runs/d97a626982844501a7bdc8ec43befe75/capacity-3879b3ac-0.jsonl` | 21654 | `51e5a5974efbd9728737244319ab67a8fd8384f0b089f95314d7c056c35bd78c` |
| `/private/tmp/p08-native-memory-cn0y8j6u/state/owned-runs/d97a626982844501a7bdc8ec43befe75/capacity-3879b3ac-1.jsonl` | 21502 | `994a05d62b5b8eda96ce5e38012519308c28c6a9db23fd5d8816c83df73cbcdd` |
| `/private/tmp/p08-native-memory-cn0y8j6u/state/owned-runs/d97a626982844501a7bdc8ec43befe75/capacity-3879b3ac-2.jsonl` | 21821 | `7fae00629856cb53600fc6de20bdecaec7b97a298cf449c43fdbd15779aec181` |
| `/private/tmp/p08-native-memory-cn0y8j6u/state/owned-runs/d97a626982844501a7bdc8ec43befe75/capacity-3879b3ac-3.jsonl` | 21632 | `49e39d6f54df8b669e133398aee320ae3c6737ca407ca488c47c9b71f41d3516` |
| `/private/tmp/p08-native-memory-cn0y8j6u/state/owned-runs/d97a626982844501a7bdc8ec43befe75/capacity-3879b3ac-4.jsonl` | 21633 | `67316e44babda5b98201c0526b9cbea201ae2db844c5af58697ca32f4f21bb06` |
| `/private/tmp/p13-owned-crash-jly3ax9r/state/owned-runs/da60eb284e7d48398d5e893259d09f23/p13-crash-jly3ax9r-3.jsonl` | 2515 | `0f9b3457a5fdd6248eaae08f58a30dd032530313665f9512e76c9b5353063767` |
| `/private/tmp/p13-owned-crash-jly3ax9r/state/owned-runs/da60eb284e7d48398d5e893259d09f23/p13-crash-jly3ax9r-1.jsonl` | 2193 | `ad6f21c3a39a8b1327fe452dddacf7bbbe75ca2932730715fc37ef433b3a2428` |
| `/private/tmp/p13-owned-crash-jly3ax9r/state/owned-runs/da60eb284e7d48398d5e893259d09f23/p13-crash-jly3ax9r-4.jsonl` | 2337 | `a7411821089daea328a19c9a9b326a331dfa2c416f8b02d0b0326f5521a36fd8` |
| `/private/tmp/p13-owned-crash-jly3ax9r/state/owned-runs/da60eb284e7d48398d5e893259d09f23/p13-crash-jly3ax9r-0.jsonl` | 2218 | `fedd86907aa3f4b237b45f394070e8b4307b49c1b33612fcbe24becbe6084c78` |
| `/private/tmp/p13-owned-crash-jly3ax9r/state/owned-runs/da60eb284e7d48398d5e893259d09f23/p13-crash-jly3ax9r-2.jsonl` | 1641 | `d69438a38607497ddb07e662b827e6c711b836bc941cdf4a65883acce6f49fe8` |
| `/private/tmp/p08-native-memory-cn0y8j6u/state/owned-runs/a880c4aade174414a8967f37a2eab43e/memory-claude-first.jsonl` | 31346 | `6b96c107279c9748a72b8249a1f9c4276a0135bf0a9da8cbd5debca334fab563` |
| `/private/tmp/p08-native-memory-cn0y8j6u/state/owned-runs/a880c4aade174414a8967f37a2eab43e/memory-claude-second.jsonl` | 24749 | `616c987f3b0ba1944577669c475858e827448a85e01bfc2ec251eb4f6a957b3c` |
| `/private/tmp/p08-native-memory-cn0y8j6u/state/owned-runs/d97a626982844501a7bdc8ec43befe75/memory-codex-first.jsonl` | 45612 | `c0e66e0823db10bb9dff7204799e1ea39cfa993d490e607721a4ecf7611ce749` |
| `/private/tmp/p08-native-memory-cn0y8j6u/state/owned-runs/d97a626982844501a7bdc8ec43befe75/memory-codex-second.jsonl` | 428 | `e9d49b74e84b6d6a3dff0a1b853c49006cc8b4acff516c6366a13510fa761c61` |
| `/private/tmp/p08-mcp-owned-0q8nu4is/first.jsonl` | 60961 | `72e27105424e2294989a7fac7de369a78194a52c406d17c02ac90c0c75142d13` |
| `/private/tmp/p08-mcp-owned-0q8nu4is/followup.jsonl` | 413 | `79378ddc91bc683a5c9d2e0a264998db69fce06c78e41cc5a6d3cf25e65a4c9f` |
| `/private/tmp/p08-mcp-owned-0q8nu4is/state/owned-runs/fa311c9931cb417698dd21edfeb30cf0/1e5fc71fee55-first.jsonl` | 423 | `c10c3417251ebb79f0863e543693f7761973249d1f3eb7dd5b2443f78936c995` |
| `/private/tmp/p08-mcp-owned-0q8nu4is/state/owned-runs/fa311c9931cb417698dd21edfeb30cf0/1e5fc71fee55-second.jsonl` | 407 | `dd054ac60d37e046288808ae05334ef64faf1d8b3bebac9b94049650073ebe97` |

검증 결과: capacity5·crash5·기존 memory8 raw와 capacity readback3 hash, crash 보존 manifest25 항목을 대조했다. 실제 manifest 항목 수는 JSON counts를 정본으로 한다. 새 모델/테스트 실행과 제품·plan·ledger 수정은 없으며 감사 JSON/MD 두 파일만 작성했다. A23-06의 기본 설치 구성과 Claude 기본 회신 미입증 구분은 유지했다.
