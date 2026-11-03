# Pi SDK의 보드·문서·첨부 native 경로

상태: Mac에서25개 검사가 통과했다. Linux는 미실행이며 실제 모델·사람 UI·
설치된 CLI·전체 기능 행렬은 미완이다.

`probe-pi-sdk.mjs <Pi package root> <새 result.json> --collaboration`은
고정 Pi1.4.0의 실제 SDK/extension/도구 등록·검증·실행 커널을 사용한다.
임시 git 저장소와 HOME/XSM_HOME/Pi 홈을 만들고 기존 공통 서비스를 호출한다.
실제 모델은 호출하지 않으며 issuing assistant와 UI 답은 명시적인 fixture다.
시험상 host-user/human 기록은 synthetic UI 경로의 결과이며 실제 사용자 승인이 아니다.

## 검증한 경로

- 팀 생성/list/show와 실제 실행 중 멤버.
- 보드 set/log/filter, 한국어 원문과 처음 root, 읽은 이전 버전의 parent 연결.
- Native 질문 UI callback을 통한 보드 결정과 human node의 결정 참조.
- 문서6개 action(add/show/log/leaves/next/render), 실제 Pi 세션 ref의 작성자,
  parent/frontier, wip의 비할당·후보 보존, limit 뒤 total 유지.
- 없는 parent·node의 실제 도구 오류와 거부 뒤 노드 수 보존.
- Synthetic native endorsement의 원문/parent/human node와 같은 요청 재사용 시
  receipt·노드 수 보존.
- 실제 reference stdio 송신자가 보낸 바이너리를 Pi native inbox/files/ACK로
  읽기. NUL/0xff 포함4바이트, 파일 이름·크기·SHA256을 대조했다.
- Pi native send/files의 outgoing 원본과 별도 실제 reference 수신자의 copy를
  대조했다. 다른 대화의 수신 저장소를 Pi가 읽으려 하면 거부됐다.

최종 Mac은25개 검사/36개 native 도구 호출/9개 operation이었고 modelCalls=0이다.
원시는 `pi-native-collaboration-final.json`이며 최초21개 표본은 별도로 보존했다.
기존 기본 SDK probe도 통과했다(`pi-sdk-default-20261104.json`). 실행 source3개
snapshot/SHA manifest는 `pi-native-collaboration-source/`에 있다. 모든 경로가
통과했다는 의미가 아니며 나머지 공개 operation·action은 별도 증거가 필요하다.

## 검사 자체의 결함 검출

실제 binding 등록을 감싼 임시 wrapper가 도구 결과만 변이했다. 실제 제품 소스나
원본 노드를 바꾸지 않았다. 다음3개는 모두 exit1로 의도한 검사에서 실패했다.

| 변이 | 실패 검사 |
|---|---|
| 보드 revision의 parent 제거 | native board links observed predecessor |
| 문서 후보/total 숨김 | native wip does not allocate or hide hypothesis |
| 수신 binary의 base64를 다른 bytes로 변경 | native binary attachment preserves bytes |

Wrapper·실패 result는 `pi-native-collaboration-mutants/`에 보존했다. 제품 engine은
변경하지 않았다. 구문 검사와 실제 native 정상/기본/변이를 실행했고 이번 test-only
추가 때문에 전체 core가 다시 통과했다고 표시하지 않는다.
