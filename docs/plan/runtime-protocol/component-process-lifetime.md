# Linux 시각 보정 중 실행 중인 component 코드 보존

상태: 제품 보존 판정을 수정했다. Mac focused15개·core979개·native8단계는
통과했고 고정 source의 Linux native3개와 Python3.11 core는 통과했다. Python3.14 core의
별도 선행조건 실패는 미해결이다. 전체 계획은 미완이다.

## 실제 기능 실패와 원인

OpenCode 설치/갱신 수명 검사에서 Linux 기본 조건이 backend 교체 뒤 구 UI
snapshot을 정리해 실패했다. 사용자 편집 조건과 같은 기본 조건의 후속 반복은
8단계를 통과했지만 원래 실패를 해결로 계산하지 않았다. 원시는
`opencode-lifecycle-current-linux/`와 `opencode-lifecycle-observed-linux/`다.

관측을 추가한 고정09dc923의 첫 Linux 실행에서도 같은 실패를 재현했다.
등록된 UI PID94의 kernel start ticks는3038로 같고 pidAlive=true였으며, lease
파일은 전후 동일했다. 하지만 ps 표시 시작 시각은02:08:58에서02:09:00으로,
/proc/stat의 btime은1793758108에서1793758110으로 바뀌었다.
`default-first/output/artifacts/prune-1.json`과 prune-2.json에 두 관측이 있다.

기존 active_records는 ps 표시가 달라지면 다른 프로세스로 처리했다. 시각
기준만 변한 동일 프로세스가 active component에서 빠졌고, 실제 prune이
그 UI의 구 코드를 제거했다. 이는 설치 수명/자원 정리의 기능 문제다.
기존 Linux 승인·cold receiver 실패와의 관련성은 이 증거만으로 판정하지 않는다.

## 수정

새 Linux component lease는 기존 owned 실행에서 쓰는 identity.process_start를
공유해 kernel boot ID와 start ticks를 process_start에 추가한다. 기존 lstart와
clock, 형식 버전1은 유지한다. 등록 시 관측한 표식과 현재 표식이 같으면
실행 중인 코드를 보존하고, 실제 프로세스가 교체되면 정리할 수 있다.
현재 kernel 관측이 불가능하면 사용 중인 코드일 수 있으므로 보존한다.

구 Linux 기록은 표식이 없으므로 살아 있는 PID의 표시 시각 차이만으로 코드를
지우지 않는다. 프로세스가 끝나면 기존처럼 정리된다. 구 기록의 PID가 재사용된
경우 코드가 더 오래 남을 수 있다. 새 기록은 kernel 표식으로 구별한다.
Mac의 기존 UTC 표시 비교와 등록/정리 잠금, 실행 중 component의 참조 방식은
유지한다. 기존 기록에 관측하지 않은 시작 표식을 소급 생성하지 않는다.

## 검증

회귀5개는 동일 kernel 표식/변한 표시 시각의 실제 prune 보존, 교체된 표식의
정리, kernel 관측 미제공, 구 Linux 기록, 새 등록을 다룬다. 최초 setup의
sys import 오류5개는 재현 성공으로 세지 않았다. 이후 유효한 수정 전5개는
모두 assertion 실패였고, 수정 뒤 관련15개가 통과했다.

Mac core979개(Python계열813+Node166)와 schema/v7 검사는102.521초/exit0으로
통과했다. 실제 OpenCode 설치 수명8단계도 통과했고 최종 UI exit0이었다.
원시는 `opencode-lifecycle-current/kernel-regression-*.log`, kernel-core-mac.log,
`kernel-mac-final/result.json`이다. 모델·사용자 profile/시스템 시각은 바꾸지 않았다.

고정5617701 Linux는 기본/사용자 편집/수정 전 UI 코드에서의 갱신과 두 Python
core를 실행 중이다. 이전09dc923 source는 실제 격리 구 UI를 띄우는 기준이며
기존 stable 배포로의 전체 rollback 완료를 뜻하지 않는다. 나머지 OS·기능·
모델/메신저·왕복 행렬은 상위 계획의 별도 필수 조건으로 남는다.

## Linux 실제 수명 결과와 남은 core 실패

고정5617701의 native 기본/사용자 편집/수정 전09dc923 UI에서의 갱신은
각각8단계/finalUiExit0으로 통과했다. 기본 조건에서는 실제로 ps 시작 시각이
02:22:59→02:23:01, btime1793758955→1793758957로 변했지만 kernel ticks2489는
같았고 이번에는 구 UI root가 active 목록에 남아 prune되지 않았다.
수정 전 UI의 기록에는 process_start가 없고 새 backend 기록에는 있으며,
이 조합도 구 UI 종료 전 보존/종료 뒤 정리를 통과했다.

같은 source의 Python3.11 core는979개/schema/v7을88.124초에 통과했다.
Python3.14 core는 board-wrong-body 결과 검사의 선행 team add 대기 상태에서
실패했다. 해당 결과 검사의 의도한 실패로 계산하지 않는다. 실행 중인 다른
검사 묶음이 중단돼3.14 전체를979개 완주로 표시할 수 없다. VM stopExit0이다.
원시는 `opencode-lifecycle-kernel-linux/`의 native3개/core311/core314다.

이 실패를 component 수정으로 해결했다고 쓰지 않는다. 실제 반환 진단을
unittest 실패에 포함하도록 보완했고, 다른 native component 사용 경로와
Python3.14 전체 검사를 별도로 다시 실행 중이다. 이전 실패도 보존한다.
