# A23-07 doctor native 후속 검증

결과: **누락 native 셀을 현재 사용자 shared Codex runtime의 한정 표본으로 채웠다.** 새 모델 없이 최종 source의 실제 `doctor --json`을 실행하고, 실행 전후 PID/lstart와 같은 thread의 후속 실제 도구 실행을 결속했다. 기존 감사는 이전 미확보 기록으로 보존했고 product/plan/ledger 판정은 변경하지 않았다.

## 실행과 생존 근거

최종 source는 `/private/tmp/xsm-final-receipt-frozen-i3u9pms3`이며 primary **135개 hash 일치·실행 후 불변**이다. 이 실제 도구 실행의 직접 부모는 Codex runtime **PID 9102**, lstart **Wed Oct 28 05:55:24 2026**이다. 현재 thread ID는 native DB의 해당 행을 `mode=ro`, `query_only`로 확인했고 작업 cwd 일치·archived=0이었다. XSM registry나 추정 caller identity는 사용하지 않았다.

이 PID는 **공유 runtime**이며 세션 전용 PID가 아니다. doctor 직전·직후 동일 PID/lstart를 확인했고, 뒤의 별도 실제 도구 실행에서도 같은 부모 runtime과 같은 thread 문맥/DB 행을 확인했다. `ps`의 동일 세대는 runtime process 생존의 직접 증거이며, 후속 실제 도구 실행은 이 사용자 작업의 도구 처리가 계속됐다는 증거다. env/DB 행 존재만을 생존 증거로 쓰지 않았고, 모든 thread 건강이나 다음 독립 모델 turn 완료로 확대하지 않았다.

실제 실행 명령:

```text
/usr/bin/sandbox-exec -f /private/tmp/doctor-native-0lxmhs_8/doctor-v2.sb /usr/bin/python3 -B -m xsm doctor --json
```

cwd/PYTHONPATH는 최종 source이고 XSM_HOME은 own private state다. HOME/CODEX_HOME은 재지정하지 않았다. 제품 서비스·registry 교체나 monkeypatch 없이 실제 module CLI를 실행했다.

## 공개 출력 검사

| 항목 | 결과 |
|---|---|
| doctor exit | 0 |
| stdout | JSON object, 38개 최상위 필드, 3212 bytes |
| stdout SHA-256 | `d59f4a06628ea9c3b217e3ecd50c2a52cc2c9e76bb7d969f77b827c79a22ffd8` |
| stderr | 0 bytes |
| stderr SHA-256 | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |
| setup homes / registered sessions | 0 / 0 |
| active_probe | not-run |
| 일반 credential/email/invite 패턴·금지 필드 탐지 | 각각 0 |
| 실제 credential 조회·비교 | 없음 |

stdout/stderr 원문은 mode 0700인 `/private/tmp/doctor-native-0lxmhs_8` 아래 mode 0600 파일로만 보존했다. 공개 [JSON](doctor-native-result.json)에는 SHA·구조·검사·실행/생존 metadata만 있으며 원문은 복사하지 않았다.

## 격리 state와 실제 process

private state에는 home/session record를 등록하지 않았다. doctor가 실제 runtime을 발견했다고 주장하지 않는다. 사용자 runtime 생존은 doctor 출력과 별개로 OS에서 관측했다.

실제 home 읽기, own tmp 밖 쓰기, 네트워크·신호를 sandbox로 막았다. 별도 guard 검사는 실제 home의 native metadata read와 private root 밖 파일 생성이 거절됨을 확인했고 파일은 생성되지 않았다. 신호·네트워크 시험 호출은 하지 않았다. 실제 home의 설치 상태나 sandbox 제한 없는 실행을 검증한 표본이 아니다.

## 기존 근거 결속과 한계

기존 `test_setup_flow.py:159,168`의 합성 token/invite/body 거절·redaction fixture, 현재 `cmd_doctor -> install.doctor + setup_flow.doctor_report` source 검토, 최종1697 회귀에 이번 실제 CLI 출력/사용자 runtime 생존을 추가했다. 역할을 구별해 결속하면 이전 감사의 누락 native 셀은 이 조건에서 충족된다. plan/ledger 상태는 수정하지 않았다.

일반 패턴 검사는 미지의 모든 실제 credential과 대조한 검사가 아니다. 실제 credential 원문을 열거나 비교하지 않았다. setup 필드 선별/hashed home 보장을 전역 home 전체 익명화로 확대하지 않았고, 모든 실제 프로필/동료 세션을 검사하지 않았다.

첫 실행은 sandbox 정책의 지원되지 않는 `process-signal` 항목 때문에 **doctor 시작 전 exit 65**였다. `signal`로 정정한 실제 doctor 실행은 exit 0이었다. 실패 raw도 분리 보존했다. 첫 guard는 JSON을 만들지 못했고 원 stderr는 보존되지 않았다. read-deny 아래 cwd의 영향으로 추정하며, private cwd에서 재실행한 거절 검사 2개는 통과했다. 두 실패는 실제 doctor 성공 표본과 분리했다.

이전 감사 이후 workspace의 current-handoff·completion-ledger JSON/Markdown hash가 바뀌었으므로 73개 전체 불변은 주장하지 않는다. 이번 도구는 해당 파일을 쓰지 않았고 변경 주체는 조사하지 않았다. 최종 frozen primary135와 workspace 제품 xsm source는 불변이다.

새 모델·로그인·사용자/동료 세션 신호·기상·권한 변경은 0이다. 이번 공개 산출물은 doctor-native-result JSON/Markdown 두 파일이다.
