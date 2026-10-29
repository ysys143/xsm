# P09 실제 일반 native 세션 N:N 표본

- 상태: passed-this-native-sample
- 표본: 같은 호스트·같은 repo, 기존 .codex/.codex-3 구독 CLI 일반 exec 대화 2개.
- 모델/sandbox/approval/allowedTools 보정 없음. 제품 소스·전역 설정·권한·계정 변경 없음.
- coordinator는 초기 역할/ref만 전달. 검토 본문 relay, inbox 답 우회, controller ACK/index 보정 없음.
- transport readiness fixture는 실제 모델 성공으로 세지 않음.
- 전체 P09·모든 하네스·실제 UI·원격 수용의 통과 선언이 아님.

| 라운드 | 요청 ID | 원 reply_to / 회신 ID | 실제 판정 | 결과 |
|---|---|---|---|---|
| 1 | 40cf3c0e071d4a44 | 40cf3c0e071d4a44 / 4825007b53764d3b | 1라운드 독립 검토 결과: ‘2+2=5’는 거짓입니다. 구체 반례로 사과 2개에 사과 2개를 더하면 사과는 4개입니다. 계산식: 2+2=(1+1)+(1+1)=4, 4≠5. 올바른 등식은 2+2=4입니다. 검토 작업을 완료했습니다. | 성공 |
| 2 | ff8e67fb8b5842a5 | ff8e67fb8b5842a5 / 1daa87614d0341e5 | 2라운드 독립 재검토 결과: 수정 주장 ‘2+2=4’는 참입니다. 계산식: 2+2=2+1+1=3+1=4. 따라서 수정안의 등식이 성립하며, 검토 작업을 완료했습니다. | 성공 |
| 3 | 556fb60bc27f49ac | 556fb60bc27f49ac / a536eba8a60542a2 | 3라운드 독립 검토 결과: ‘0+0=0’은 참입니다. 독립 계산식: \|∅\|+\|∅\|=\|∅∪∅\|=\|∅\|=0. 원소가 없는 두 집합을 합쳐도 원소 수는 0이므로 0+0=0입니다. 상대가 제시한 항등원 계산식 a+0=a에 a=0을 대입한 판정과도 일치합니다. 경계조건 검토를 완료했습니다. | 성공 |

## 근거

- 상세 JSON: results.json 및 실행별 results-<run>.json.
- source 파일/sha, factory import readback, native profile/thread/model metadata, 실제 MCP 호출과 응답을 JSON에 보존.
- 원본 native stdout/stderr와 임시 공유 상태: /private/tmp/p09-nn-native-m2bavr8b
- 공개 보존 claim token은 hash로 치환. 실제 ACK에는 런타임이 반환한 원 token을 모델이 사용.
- paid-model 평문 flood는 수행하지 않음. 엄격 반복 fixture는 coordinator 별도 검증.

## 소스·실행 범위 추가 확인

- 2라운드 요청은 실제 1라운드 회신 index 뒤에 생성됨: True.
- 실행 중 source SHA 변경: xsm/cli.py, xsm/mcp.py. 동일 동결 revision 성공으로 주장하지 않는다.
- Native file-change event: 0. shell commands는 두 프로필 모두 0개.
- 실제 관측 기본값: 두 프로필 모델 gpt-6.1-sol, approval never, sandbox danger-full-access. runner는 이를 설정/보정하지 않았다.
- 최초 runner 준비 오류는 실행별 JSON에 보존했고, 성공한 두 native 세션은 이후 재시작하지 않았다.
