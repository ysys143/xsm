# XSM 데모·문서 디자인

[pen 원본](xsm-demo.pen) · [인터뷰와 디자인 브리프](spec.md)

[웹 구현과 로컬 실행](../../../site/README.md) · [구현 검증 기록](implementation.md)

쓰던 Claude Code·Codex 세션에 역할을 주고 장기 작업을 운영하는 관람형 시연이다. Fable 팀장이 계획과 진척을 유지하고, 워커들이 직접 협업한다. 시연에서 고른 장면은 같은 주제의 문서로 이어지고, 문서에서도 해당 장면을 다시 본다.

| 화면 | 미리보기 | 내용 |
|---|---|---|
| 첫 화면 | [01-home.png](previews/01-home.png) | 큰 타이포그래피, 네이티브 세션을 재현한 시연, 재생·장면 선택, 관련 문서 |
| 문서 | [02-guide.png](previews/02-guide.png) | 설치 요청 → 팀과 역할 지정 → 계획 유지. 설명 옆에 해당 장면의 재생 창 |
| 장면 01 | [03-form-team.png](previews/03-form-team.png) | 자연어로 팀장·워커·완료 기준을 정하는 시작 |
| 장면 03 | [04-long-running.png](previews/04-long-running.png) | 다음 날의 검증 결과, 막힘 보고, Fable의 계획·진척 갱신 |
| 장면 04 | [05-multiple-teams.png](previews/05-multiple-teams.png) | API·UI 팀의 독립 실행과 팀장 간 조율 |
| 모바일 | [06-mobile.png](previews/06-mobile.png) | 읽을 수 있는 터미널 크기, 역할별 보기, 같은 장면의 사용법으로 연결 |

장면 02(워커 간 직접 협업)는 첫 화면에 들어 있다. 같은 홈페이지에서 시간에 따라 바뀌는 모습을 장면별 아트보드로 나눴다.

첫 화면은 README의 기존 문구를 그대로 쓴다. **“All you need is a message channel.”**을 제목에, **“The rest is done by agents.”**를 설명에 둔다. 각 장면 제목은 역할 구성·계획과 진척 관리·복수 팀 조율 등 실제 내용을 설명한다.

TypeSafe는 시각 디자인의 기준, 프로필은 터미널 에뮬레이션의 표현, Reason Network는 시연과 문서를 연결하는 구성을 참고했다. 인터뷰의 원문 취지와 출처는 브리프에 기록했다.

pen 원본과 정적 미리보기는 화면 설계를 보관한다. 실행되는 데모와 문서는 `site/`에 구현한다. 상단 보조 설명·작은 링크 제거와 지원 런타임 6종 표시는 웹과 pen에 함께 반영했다.
