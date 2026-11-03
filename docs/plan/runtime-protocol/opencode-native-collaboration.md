# OpenCode 설치 경로의 보드·문서·첨부 native 검증

상태: Mac 최종21개 검사가 통과했다. Linux·실제 모델·사용자 UI와 전체 기능
행렬은 미완이다. 이번 시험은 사용자 판단이 필요한 결정·endorsement를
실행하지 않았으며 해당 native UI 검증을 대체하지 않는다.

`probe-opencode-collaboration.py`는 새 git 저장소와 HOME/XSM_HOME/OpenCode
프로필에 실제 설치 loader를 만들고 고정 OpenCode1.19.5 server를 실행한다.
모델 대신 loopback scripted SSE provider가 도구 호출을 요청하며, 실제 native
도구 커널이 plugin·공통 protocol host를 호출한다. 각 호출의 native callID·tool·
sessionID와 완료/오류 상태를 원시 transcript에서 확인한다. 일반 모드 loader는
수정하지 않는다. 변이 loader는 임시 프로필에서만 따로 쓴다.

## 확인한 경로

- 실제 도구22개 등록과 team create/list/show, 실행 중 멤버.
- Board set/log/filter와 원문·root·관측한 이전 버전의 parent 연결.
- 문서6개 action, 실제 native 세션 작성자, frontier, wip 비할당·후보 보존,
  limit 뒤 total 유지와 render 원문.
- 없는 parent·node의 실제 native 오류 원인과 거부 뒤 노드 수 보존.
- 실제 reference 송신자가 보낸 바이너리를 native inbox/files로 읽고 ACK.
  NUL/0xff 포함 bytes와 크기·SHA256을 대조한다.
- Native send/files의 outgoing 원본과 실제 reference 수신자의 copy를 대조하고
  수신자가 명시적으로 ACK한다. 다른 대화의 storage는 owner-mismatch로 거부된다.

최종 Mac은21개 검사/29개 도구 호출/7개 operation, scripted HTTP58개다.
예상된 오류는 없는 parent·node와 타 대화 storage3개다. 첫 정상 실행과 오류
원인 대조를 보강한 최종 실행은 따로 보존했다. ModelCalls=0이고 native server의
정상 종료를 확인했다. 합성 context capacity262144와 요청200개 상한, 요청 크기
8MiB 상한을 명시했다. 실제 모델 규격이나 fallback으로 사용하지 않는다.

## 검사 자체의 결함 검출

실제 설치 plugin의 execute 결과만 감싼 임시 loader가 parent 연결·문서 후보·
binary bytes를 각각 변이했다. 실제 원본 노드나 제품 소스를 고치지 않았다.
다음3개는 모두 exit1과 nativeStopped=true로 끝났다.

| 변이 | 실패한 검사 |
|---|---|
| board-parent | native board links observed predecessor |
| doc-candidate | native wip does not allocate or hide hypothesis |
| file-content | native binary attachment preserves bytes |

원시는 `deliverables/protocol-foundation/opencode-native-collaboration/`의
first/final 및 각 변이 폴더다. Native 도구 packet과 gzip HTTP 요청, source4개
snapshot/SHA manifest를 보존했다. 테스트 전용 추가라 구문 검사와 실제 native
정상/변이를 실행했으며 전체 core가 다시 통과했다고 표시하지 않는다.
다른 operation·action·UI·실제 모델과 전체 행렬은 별도 증거가 필요하다.
