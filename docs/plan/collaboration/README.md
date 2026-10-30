# 협업·원격 구현 계획

xsm 0.5.0의 업무 검색, 선택한 상대와의 핸드셰이크, 상관된 질문과 답, 자료 사본, 사람의 판단 기록, 소유 워커, 선택적 P2P 네트워크를 만든 계획과 그 검증 기록이다. 설계 결정은 [ADR-0015 ~ ADR-0024](../../adr/README.md)에 있고, 출발점이 된 비교 조사는 [Reason 비교 노트](../../references/reason.md)에 있다.

## 상태

- ADR-0021(원격 네트워크와 멤버십)과 ADR-0024(발견·선택·핸드셰이크)는 Accepted다. 나머지 0015–0020, 0022, 0023은 Proposed이며 미결 매개변수는 사용자 결정 전이다.
- ADR-0021의 수용 조건 7개는 [종료 기록](adr-0021-closure.md)에 적힌 환경과 한계 안에서 종결했다.
- 전체 수용 조건 70개는 아직 완료가 아니다. 조건별 현재 판정은 [완료 색인](completion-ledger.md)에 있고, 실제 사람 UI와 원격 전체 여정의 검증이 남아 있다.

## 읽는 순서

| 문서 | 내용 |
|---|---|
| [spec.md](spec.md) | 실행 단위 P00–P13의 상세 작업 |
| [acceptance.md](acceptance.md) | ADR에서 추출한 수용 조건 70개와 필요한 증거 |
| [execution.md](execution.md) | 병렬 실행 순서와 게이트 G00–G13 |
| [collaboration-contract.md](collaboration-contract.md) | 발견·선택·핸드셰이크의 확정 설계 |
| [remote-decision.md](remote-decision.md) | 원격 backend 비교와 실측 |
| [adr-0021-progress.md](adr-0021-progress.md), [adr-0021-closure.md](adr-0021-closure.md) | ADR-0021 실행 현황과 종료 기록 |
| [completion-ledger.md](completion-ledger.md) | 조건별 증거 색인. `completion-ledger.json`과 함께 감사 스크립트가 생성한다 |
| [plan.json](plan.json) | 위 관계의 기계 판독용 원본 |

계획 문서의 `R01`–`R43`은 비교 조사에서 나온 발견 ID다. 발견별 세부 추적표는 저장소 밖에 보관하며, 각 발견이 어떤 수용 조건으로 이어지는지는 [acceptance.md](acceptance.md)와 [plan.json](plan.json)에 남아 있다.

## 작업 기록

[records/](records/)는 구현 중 에이전트 세션들이 남긴 운영 기록이다. 세션 간 인계, 개발 방침, 게이트별 통과 기록, 로컬 릴리스 검토 메모, ADR-0021 작업 계약, 계획 검증 결과가 있다. 판정의 근거로 인용되므로 그대로 보존하지만, 계획을 이해하는 데는 위 문서로 충분하다. 실행 원시 기록은 [deliverables/](../../../deliverables/)에 있으며, 그 안의 문서 경로는 기록 당시의 것(`docs/plan/reason-inspired-adrs/`)이다.

## 색인 감사

```bash
python3 scripts/audit-collaboration-plan.py --structure-only   # 색인 무결성. 제품 완료를 뜻하지 않는다
python3 scripts/audit-collaboration-plan.py                    # 미완 조건이 남아 있으면 exit 1이 정상이다
python3 scripts/audit-collaboration-plan.py --self-test        # 색인 변조 검출
python3 scripts/audit-collaboration-plan.py --refresh --structure-only   # 색인 재생성
```
