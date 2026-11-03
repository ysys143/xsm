# OpenCode TUI의 보드 결정·문서 endorsement

상태: Mac·Linux의 native TUI에서 각각6개 정상 모드와 출처 변이2개를 검증했다.
실제 사용자·모델·메신저와 전체 계획은 미완이다. 입력은 자동화한 PTY 키 입력
fixture이며 실제 사용자가 답한 표본으로 부르지 않는다.

`probe-opencode-question-ui.py --native-bridge --installed --workflow board|endorsement`는
고정 OpenCode1.19.5의 실제 server·설치 loader/TUI companion·DialogSelect를
실행한다. Provider는 scripted fixture다. 보드는 native team create→decide→
board log/decisions, 문서는 native doc add→doc_endorse→doc log/render를 거친다.
Setup·효과 readback도 같은 실제 native 도구 커널이 수행한다.

실제 terminal 화면에서 질문과 해당 session ID가 보이고 native displayed
관측이 있을 때만 Enter 또는 Escape를 쓴다. 기존 UI instance/nonce claim·
표시·답 전송·공통 승인 저장 경로를 바꾸지 않았다. 모델이 답을 넣거나
호스트 승인 API를 직접 호출하지 않는다.

## Mac 검사 결과

| 흐름 | 선택 | 취소 |
|---|---|---|
| 보드 결정 | human node1개·결정1개, API receipt와 persisted host-user record 일치 | 노드0개·결정0개 |
| 문서 endorsement | 원문/parent 일치 human endorsed child1개, host-user receipt·render | 원래 agent node1개만 남음 |
| 기존 색상 질문 | applied | dismissed |

각 정상 모드는 실제 표시·세션 문맥·component lease의 TUI PID/UTC 수명·설치
snapshot backend를 확인했다. Native control frame은 빈 ignored/synthetic part
4개 이상이었으며 model request에 xsmUi와 그 nonce가 없음을 대조했다.
선택은 applied, 취소는 dismissed였고 source는 host-user다. 이는 synthetic
keypress가 통과한 native 경로의 기록이며 실제 사람 승인 인증이 아니다.

`--workflow-mutant receipt-via`는 실제 native UI 작업 뒤 execute 결과의 출처만
model로 바꾼다. 보드는 `native board receipt matches persisted user decision`,
문서는 `native endorsement receipt is host-user`에서 각각 exit1이었다. 실제
원본 노드나 제품 source는 변이하지 않았다. 정상 loader는 그대로이고 변이
loader는 임시 프로필에만 둔다.

새 선택 경로의 첫 표본과 강화한 receipt 대조의 최종 표본은 별도로 보존했다.
네 workflow와 두 기본 모드를6개로 세며, 같은 선택 흐름을 반복한 표본은
중복 집계하지 않는다. 원시는 `deliverables/protocol-foundation/opencode-native-ui-workflows/`의
*-choose-final, *-cancel, default-* 및 *-via-mutant다. Terminal raw·UI event·
provider request·native transcript와 source7개 snapshot/SHA manifest를 보존했다.

## 시험 도구 보완

준비한 package/lock을 새 profile로 복사해 native dependency 대기가 외부 설치를
다시 하지 않게 했다. 플랫폼 binary는 기존 pinned helper로 골라 Linux arm64를
잘못 linux-x64로 고르던 하네스 분기를 바로잡았다. 새 출력 폴더만 허용해 이전
실패를 덮지 않는다. 이 플랫폼 보완도 실제 Linux arm64 TUI 실행에서 확인했다.
제품 engine·UI protocol은 바꾸지 않았다. 실제 native 정상/변이 경로와 구문을
실행했으며 test-only 변경으로 전체 core 재통과를 주장하지 않는다.

## Linux 고정 source 검증

고정b7d34e5/Linux arm64에서 새 workflow4개와 기본 질문2개가 모두 통과했다.
출처 변이2개도 각각 의도한 assertion/exit1이었다. Native terminal/도구/승인
저장 경로를 모두 실행했으며 Mac과 같은 applied/dismissed·human 노드 유무를
확인했다. 6개 정상 모드의 실제 control frame 각4개 이상이 ignored/synthetic
빈 part였고, nonce와 xsmUi가 전체 provider request에 없음을 별도 대조했다.
Network none/model0/read-only 준비 패키지, 미실행0, VM stopExit0이다.
원시는 `opencode-native-ui-workflows-linux/`의 case별 output/artifacts와
result.json/audit.json이다. 이는 자동 키 입력 fixture이며 실제 사용자의
판단·모델 협력·메신저나 전체 기능 행렬의 인증은 아니다.
