# 120초 핵심 검사: 큰 Python 그룹 분할

상태: P2/P5의 부분 진척이다. 전체 계획은 미완이다.

고정cf01df5의 Linux3.11은 core931개를94.911초에 통과했으나3.14는120초 예산을
초과했다. SDK56개44.320초, native133개36.381초, 외부 적합성54개74.731초는
끝났지만 가장 큰 Python core 그룹은 제한 시각까지 완료되지 않았다. Gate는
진행 중 프로세스 그룹을 종료했고 이3.14의 wire/schema는 전제 미충족으로
미실행이다. Source·실패 로그·VM 종료는 error-contract-linux/에 보존했다.

가장 큰 core module 목록을 순서를 유지한 짝수/홀수 인덱스 두 목록으로 분할해
각기 별도 Python 프로세스에서 실행한다. 모든 module과 test는 유지하며
총 deadline은120초 그대로다. 각 그룹은 서로 다른 HOME/XSM_HOME/CODEX_HOME/
CLAUDE_CONFIG_DIR를 받는다. Native/SDK/Node/외부 적합성과 독립 mock도 유지한다.

Gate 검사는 전체 module의 중복 없는 정확한 합집합, core의2개 이상 비중첩
그룹, 전체 독립 mock와 Node/SDK 명령 유지, 공통 deadline, 프로세스 격리와
실패/timeout 뒤 reaping을 검사한다.4개가0.638초에 통과했다(focused.log).
분할을 제거한 임시 source 변이는 의도한 그룹 검사에서 실패했다(mutant.log).

Mac/Python3.14.6 core931개가50.353초에 통과했다(core.log, exit0). 앞선
serial core930개/86.030초와 별도focused2개 표본을 덮어쓰지 않았다. 신규931개
전체 실행과 실패/미실행 수치를 구분한다. 독립 mock39/변이14는 별도 수치다.
원시는 `deliverables/protocol-foundation/core-partition/`다. Linux는 후속 고정
source에서 같은 전체 gate를 다시 실행해야 한다. 범위를 줄이거나 예산을 늘린
변경이 아니며, native/실제 UI/원격 전체 행렬 완료는 아니다.

## 후속 고정 source Linux 검증

249c755e45f003a65c6b4e3bf0a770fd34d9193d의 archive SHA256은
3a067434bf6daa55d28fc0e3a3fd892e8d230d700dd0c7fe7fe7b74cdf5c009d다.
Python3.11.2에서78.737초, Python3.14.10에서102.866초로 core931개를 각각
통과했다. 두 환경에서 새 errors-fixture27개/frame29개와 offline jsonschema4.26.0
검증도 통과했다. Model0/network none/cpu2/memory3g, 미실행 case0,
미실행 wire/schema0, VM stopExit0이다. 원시는 `core-partition-linux/result.json`과
환경별 output이다. 이전cf01df5의3.14 timeout은 실패 증거로 보존한다.
전체 native/UI/원격·메신저·설치 행렬과 전체 계획은 미완이다.


## 2026-11-04 Node 파일 실행 수 명시 측정

Linux3.14의979개 전체 재실행은120초 예산을 초과했다. 완료된 Node166개는
119.424초, 외부 적합성56개는118.160초였고 다른 그룹/phase2가 중단됐다.
원시는 `participant-clock-continuity-linux/core314/output/core.log`다.

Node 검사 명령에 --test-concurrency=2를 명시했다. MODULES·NATIVE_MODULES와
Node 파일 목록 및 전체120초 deadline은 유지한다. Mac979개/schema/v7은
111.212초로 통과했고 기존 gate5개도 통과했다. 통계적 속도 개선을 주장하지
않으며 고정5fec4f0의 Linux 두 Python 환경을 같은 자원에서 측정 중이다.
원시는 participant-clock-continuity/mac-core-node2.log 및 gate-node2.log다.


Node2만 명시한 고정5fec4f0의 Linux 두 환경도120초를 초과했다.3.11에서
Python303개116.770초, Node166개88.075초, 외부 적합성56개105.213초였고
phase2를 다 끝내지 못했다.3.14는 진행 중인 묶음도 제한 시각에 중단됐다.
둘 다 실패로 보존했다(`core-node2-linux/`, VM stopExit0).

가장 오래 걸린 Python core module 목록을 같은 순서의3개 비중첩 묶음으로
나눴다. 전체 목록/Node·SDK·native·적합성/독립 participant와 공통120초
deadline은 그대로다. 기존 실행 계획/격리/종료 검사5개가0.638초에 통과했고,
Mac979개(Python계열813+Node166)/schema/v7도98.801초에 통과했다.
고정d655c59 Linux 두 환경 측정은 진행 중이다. 아직 Linux 시간 조건의
해결로 표시하지 않는다. 원시는 mac-core-three-groups.log와 core-three-groups-linux다.

고정d655c59 Linux의3.11/3.14는 각각979개/schema/v7을84.985초/107.743초에
통과했다. Python core3개 묶음과 SDK/native/적합성·Node166개를 출력에서
직접 세어979개를 대조했다. Network none/cpu2/memory3g, 미실행 case0,
VM stopExit0이다. 각 검사의 정본 목록과120초 한도는 줄이거나 늘리지 않았다.
원시는 `core-three-groups-linux/result.json`, case별 core.log와
inventory-audit.json이다. 과거 시간 초과와 팀 추가 단계의 간헐 실패를
이 성공으로 지우지 않는다. 전체 계획의 나머지 조건은 미완이다.
