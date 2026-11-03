# 범위 변경 결과 계약

상태: P0/P2의 부분 진척이다. 전체 계획은 미완이다.

Link/join/reach는 기존 text에 scope snapshot을 추가한다. kind와 active/changed,
연결의 두 root, 가입의 project/root/other_members, reach의 root/owner_ref와
회수 개수를 명시한다. 정본 permission record나 runtime profile home은
노출하지 않는다. Root는 기존 표시 문장이 이미 제공하던 선택된 프로젝트 경로다.
Cached replay는 당시 snapshot을 보존하며 현재 권한을 보장하지 않는다.

공개 schema는 세 snapshot과 host 대기, legacy text를 정의한다. Checker는
operation과 kind를 결속하고 removed/changed의 일치도 검사한다. Schema/예제를
필수 bundle 목록과 누락 거부 검사에 연결했다.

실제 격리 stdio scopes41개 검사와 관측 frame58개를 검증했다. 두 git root 사이에
각각 link/reach/join을 적용하고 xsm_send가 실제로 stored인지 검사한다. Host 답
저장만으로는 refused 상태를 벗어나지 않아야 한다. Unlink/reach 회수/leave 뒤에는
다시 refused여야 한다. Deny 뒤 재호출은 closed-decision 오류이며 권한이 생기지
않는다. 이 경로에는 실제 로컬 파일/stdio를 쓰고 모델·네트워크는 쓰지 않는다.

예제11개·잘못된 결과12개를 검사했다. Wire 결함은 scope metadata 누락,
다른 root, 해제 뒤 active=true의 세 가지이며 각각 snapshot 검사에서 실패해야 한다.

원시는 `deliverables/protocol-foundation/scope-contract/`다. 첫 실행은 송신
거부를 JSON-RPC 오류로 기대해 실패했고, 두 번째는 macOS /var 경로와 /private/var
정규화 차이로 실패했다. wire-complete는 denied retry의 closed-decision 오류를
text 결과로 기대해 실패했다. 세 기록은 보존했고 성공 수치에서 제외했다.
wire-final.json/schema.json이 최종 검사다. 최초 checker 실행의 scope keyword
중복 SyntaxError도 발견 즉시 수정했다. 실제 사람/native UI 인증과 전체 계획은 미완이다.

Mac/Python3.14.6 core911개(Python527+외부 적합성43+SDK56+native133+Node152)는
78.509초에 통과했다(core.log, exit0). Wire 결함3종이 모두 의도한 검사에서
실패했고 changed에 정수를 허용한 schema 변이도 검출했다(mutant.json).
독립 mock39/변이14는 별도 수치다. Linux 검증은 아래에 기록한다.

## 고정 source Linux 검증

1020dd17acf5b74560d725f64a2522b7a849ce3a의 archive SHA256은
9e781ca5b71459c70c4bbc3ea1c1a03d5b7bfbd32179f5fffb55c528e435cfc3다.
Python3.11.2에서91.827초, Python3.14.10에서116.427초로 core911개를 각각
통과했다. 두 환경에서 새 scopes41개/frame58개를 수집하고 offline
jsonschema4.26.0으로 검증했다. 예제11개·거부12개도 검사했다.
Model0/network none/cpu2/memory3g, 미실행 case0, 미실행 wire/schema0,
VM stopExit0이다. 원시는 `scope-contract-linux/result.json`과 환경별 output이다.
실제 사람/native UI 및 전체 runtime 행렬은 미완이다.
