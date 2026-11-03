# Owned Linux 프로세스 세대 식별 복구

상태: P1/P5의 부분 진척이다. 전체 계획은 미완이다.

고정489e7ac의 Linux3.11 core는 OpenClaw retained-history 복구 검사에서 실패했다.
저장된 child lstart와 같은 PID의 재조회 문자열이08:59:10/08:59:09로1초 달랐다.
원시는 `owned-contract-linux/core311/output/protocol.log`다. Native133개 중1개가
실패했고 core gate가 다른 진행 중 그룹을 종료했다. 해당3.11의 wire/schema는
전제 미충족으로 미실행이다. 같은 source의3.14는 core920개를117.256초에 통과했고
owned stdio/schema도 실행했다. 두 환경 모두 실행됐지만 전체 판정은 failed이며,
VM stopExit0이다. 이 실패를 지우거나3.14의 통과로 대체하지 않았다.

직접 영향 경로는 owned controller 세대 기록(_process), child 생성 시각 기록,
_alive의 비교다. 기존 lstart는 ps의 wall-clock 표시 문자열이다. 새 owned 기록은
Linux에서 /proc boot_id와 /proc/PID/stat의 starttime ticks를 함께 보존한다.
[Linux man-pages의 field22 정의](https://man7.org/linux/man-pages/man5/proc_pid_stat.5.html)를
조회해 필드 위치와 clock ticks 의미를 확인했다. Command 이름의 공백/괄호를
건너뛰고 파싱한다. Registry와 classic worker의 기존 lstart 형식은 바꾸지 않는다.

Process generation은 reboot/PID 재사용을 구분하고 kernel 정보가 없으면 unknown을
반환한다. 조회 실패를 ps 값이나 현재 PID만으로 일치시켜 승격하지 않는다.
이전 journal의 ps 문자열은 기존 정확 비교로 읽는다. ±1초 허용을 넣지 않았다.
기존 기록을 확정할 수 있는 추가 증거 없이 새 kernel token으로 소급 변환하지 않는다.

새 검사6개는 wall-clock 문자열 변화와 독립적인 동일 세대, PID 재사용, reboot,
조회 거부, legacy/macOS 비교, owned _alive 연결, 현재 프로세스 경로를 검사한다.
수정 전 before.log는 새 경로가 없어 실패했고 수정 후6개가0.017초에 통과했다.
초기 실제 Linux 실패가 회귀의 출발 근거이며 새 API 부재 실패만으로 원인 복구를
주장하지 않는다. 전체 Linux core·실제 OpenClaw 복구 경로를 후속 고정 source로
다시 실행해야 한다.

첫 Mac 전체 검사는 진행 중 team/board 변경의 additive sync receipt 때문에
기존 text-only 동등성 assertion1개가 실패했다(core.log). Backend/native133개는
통과했다. 기존 assertion은 text와 structured receipt를 함께 검증하도록 갱신했다.
최종 전체 검사는 `team-board-actions/core.log`에 구분해 남긴다.
원시는 `deliverables/protocol-foundation/owned-process-generation/`다.

최종 Mac core928개(Python535+외부 적합성52+SDK56+native133+Node152)는
84.435초에 통과했다(team-board-actions/core.log, exit0). 여기에는 새 process
generation6개와 실제 OpenClaw 복구·native133개가 포함된다. Linux는 후속
고정 source 실행 전까지 초기3.11 실패가 해결됐다고 판정하지 않는다.
