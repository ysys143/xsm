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
