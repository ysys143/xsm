# 승계 결과 계약

상태: P0/P2의 부분 진척이다. 전체 계획은 미완이다.

`xsm_handover`는 text를 보존하면서 action별 receipt를 추가한다. hand_over는
시각/from_ref/to_ref/teams/items/questions/groups/messages와 notes를 제공한다.
show는 같은 transfer projection에 letter를 더한다. 내부 native identity/home과
approval record는 노출하지 않는다. 구형 보존 기록의 없는 ref는 null을 허용한다.
승계는 successor의 읽기·업무 완료나 원격 동기화 성공 증거가 아니다.

공개 schema/예제를 필수 bundle과 누락 거부 검사에 연결했다. 예제5개·잘못된
결과9개를 검사했다. Stdio handovers28개/frame39개에서 팀과 lead를 실제로
만들고 미독 DM을 저장한 뒤 host 답→원 작업 retry→승계를 확인했다. 답 저장만으로는
승계하지 않으며 같은 요청은 같은 receipt를 보존한다. 수신 편지는 원본 ID와
미독 본문을 보존한다. 옛 주소로 보낸 새 DM은 successor inbox에서 claim/ACK했다.

미독 원본은 기존 동작대로 편지에 포함되고 원본 저장소에는 moved 표식과 함께
남는다. 새 inbox 복사본을 생성하는 것으로 계약을 바꾸지 않았다. Receipt의
messages는 편지에 옮긴 원본 ID 목록이지 읽기/업무 ACK가 아니다.

Mac/Python3.14.6 core915개(Python527+외부 적합성47+SDK56+native133+Node152)는
77.509초에 통과했다(core.log, exit0). Metadata 누락·다른 successor의 wire 결함
2종이 의도한 검사에서 실패했다. 독립 mock39/변이14는 별도 수치다.
원시는 `deliverables/protocol-foundation/handover-contract/`다. 초기 실패3회는
팀 생성만으로 lead라고 가정한 것, 미독 inbox 복사본을 가정한 것, 공개 lead label에
ref가 있다고 가정한 것이며 보존했다. 최종 wire-final/schema-final을 사용한다.
모델/실제 사람/native UI/원격을 실행하지 않았다. 마지막 owned 결과 계약과
team/board의 남은 action, 전체 행렬은 계속 미완이다.
