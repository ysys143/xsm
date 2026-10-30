"""S12: freeze synthetic inputs and author labels before any inference."""
import datetime as dt
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent

def write(name, obj):
    (ROOT / name).write_text(json.dumps(obj, ensure_ascii=False, indent=2) + '\n')

sessions = [
    dict(id='Oriole', task='로그인 토큰 갱신의 경쟁 조건 수정', owned=['auth-refresh'], files=['src/auth/refresh.ts'], premises=['인증 세션은 공유 Redis에 저장된다.', '로그인 토큰의 session_rev 필드는 정수다.'], resources=['auth-staging']),
    dict(id='Birch', task='상품 상세 캐시의 무효화 및 만료 처리 수정', owned=['product-cache'], files=['src/cache/products.ts'], premises=['상품 캐시는 Redis에 저장된다.', '상품 갱신 이벤트는 item.updated이고 중복 전달될 수 있다.'], resources=['cache-staging']),
    dict(id='Cedar', task='매출 분석 화면의 실시간 차트와 페이지 이동 구현', owned=['sales-console'], files=['web/sales/chart.tsx'], premises=['매출 API 응답의 필드는 snake_case다.', '매출 페이지의 next_cursor는 불투명 문자열이다.'], resources=['preview-slot']),
    dict(id='Dune', task='문서 의미 검색의 벡터 색인 갱신 구현', owned=['doc-index'], files=['src/search/indexer.py'], premises=['검색 벡터는 PostgreSQL pgvector에 저장된다.', '문서 임베딩 차원은 768이다.'], resources=['gpu-embedding']),
]

# Each list contains twenty authored changes, two per batch. Labels concern
# the primary session; the author separately annotates shared prerequisites.
changes = [
 [('R1','Oriole가 auth-refresh의 갱신 요청 중복 처리를 맡는다.'),('R2','팀 Echo가 로그인 토큰의 동시 갱신 잠금 구현에 착수했다.'),
  ('R3','인증 세션 저장소를 Redis에서 로컬 메모리로 바꾸기로 결정했다.'),('R4','Echo가 auth-staging을 오늘 18시까지 독점 사용한다.'),
  ('R2','다른 작업자가 만료 직전 토큰의 재발급 경쟁 상태를 수정 중이다.'),('R3','로그인 토큰 session_rev를 정수에서 UUID 문자열로 변경한다.'),
  ('R4','auth-staging 예약이 Foxtrot의 부하 시험과 겹쳐 내일로 밀렸다.'),('R1','src/auth/refresh.ts 리뷰 담당에 Echo를 추가한다.'),
  ('R1','auth-refresh 완료 기준에 재시도 시 중복 갱신 방지를 추가한다.'),('R3','인증과 상품을 포함한 공유 Redis 서비스는 이번 배포에서 완전히 폐기한다.'),
  ('R2','Echo가 로그인 토큰 재발급의 다중 탭 충돌 방지 패치를 작성한다.'),('R4','인증 검증용 auth-staging을 Echo가 전체 작업 시간 동안 점유한다.'),
  ('R3','로그인 토큰 버전 값은 더 이상 정수가 아니며 이제 십진 문자열이다.'),('R1','Oriole의 갱신 오류 수정은 보안 리뷰가 끝날 때까지 보류한다.'),
  ('R4','Foxtrot이 auth-staging을 오늘 종료 시각까지 예약했다.'),('R2','다른 팀이 재발급 요청 두 개가 동시에 올 때의 잠금 로직을 구현한다.'),
  ('R1','src/auth/refresh.ts에 대한 리뷰 요청이 새로 등록됐다.'),('R3','인증 세션은 이제 공유 저장소 없이 각 프로세스 안에만 보관한다.'),
  ('R2','Echo가 갱신 토큰의 동시 사용 시 중복 발급 방지 작업을 시작했다.'),('R4','auth-staging 단독 슬롯을 다른 팀에 배정하여 오늘은 사용할 수 없다.')],
 [('R3','상품 상세 캐시의 저장소를 Redis에서 프로세스 메모리로 바꾼다.'),('R4','Echo가 cache-staging을 오늘 18시까지 독점 사용한다.'),
  ('R1','Birch가 product-cache 만료 처리의 회귀 점검을 맡는다.'),('R2','팀 Foxtrot이 상품 상세 캐시 무효화 로직을 다시 구현하기 시작했다.'),
  ('R4','cache-staging 예약을 다른 작업의 장시간 부하 시험에 배정했다.'),('R1','src/cache/products.ts의 수정 사항에 리뷰가 필요하다.'),
  ('R2','Echo가 상품 갱신 이벤트의 중복 수신에 대한 캐시 제거 패치를 작성한다.'),('R3','상품 갱신 이벤트 명칭을 item.updated에서 catalog.changed로 바꾼다.'),
  ('R3','상품 캐시를 포함한 공유 Redis 클러스터의 사용을 종료한다.'),('R2','Foxtrot이 상품 상세 데이터의 만료와 재조회 처리를 구현 중이다.'),
  ('R1','product-cache의 완료 조건에 중복 이벤트 처리를 추가한다.'),('R4','다른 팀이 cache-staging의 전용 슬롯을 오늘 종일 점유한다.'),
  ('R2','팀 Echo가 상품 수정 알림을 받으면 캐시를 비우는 기능에 착수했다.'),('R3','상품 변경 알림은 item.updated 대신 product.revised로만 발행한다.'),
  ('R1','Birch의 상품 캐시 패치에 대한 리뷰어를 Foxtrot으로 바꾼다.'),('R4','cache-staging의 남은 사용 시간을 다른 팀이 전부 예약했다.'),
  ('R4','cache-staging을 저녁까지 Echo의 재현 시험에 배정했다.'),('R1','src/cache/products.ts의 변경 범위에 만료 경계 조건을 포함한다.'),
  ('R3','상품 상세 데이터는 이제 Redis에 캐시하지 않고 프로세스별로 보관한다.'),('R2','다른 팀이 상품 상세 캐시의 만료 시점 경합을 고치는 중이다.')],
 [('R2','팀 Echo가 매출 차트의 실시간 데이터 갱신 UI 구현을 시작했다.'),('R1','Cedar가 sales-console 페이지 이동 부분의 검수를 맡는다.'),
  ('R4','Foxtrot이 preview-slot을 오늘 18시까지 독점 사용한다.'),('R3','매출 API의 필드를 snake_case에서 camelCase로 변경한다.'),
  ('R1','web/sales/chart.tsx에 대한 디자인 검토가 필요하다.'),('R4','preview-slot을 다른 팀 데모에 배정하여 오늘은 비어 있지 않다.'),
  ('R3','매출 페이지 next_cursor를 불투명 문자열 대신 정수 오프셋으로 바꾼다.'),('R2','다른 작업자가 매출 분석 화면의 다음 페이지 버튼을 구현 중이다.'),
  ('R4','웹 검증 환경 preview-slot은 Echo가 업무 종료까지 점유한다.'),('R2','Foxtrot이 매출 통계의 실시간 그래프를 만드는 작업에 착수했다.'),
  ('R3','매출 응답의 gross_sales 필드는 grossSales로만 반환한다.'),('R1','sales-console의 완료 기준에 페이지 이동 중 실시간 갱신을 추가한다.'),
  ('R1','Cedar의 매출 차트 구현에 Foxtrot을 리뷰어로 지정한다.'),('R2','Echo가 매출 화면의 실시간 차트와 페이지 전환 UI를 다시 작성한다.'),
  ('R3','매출 API는 다음 페이지 위치를 문자열 토큰 대신 숫자로 반환한다.'),('R4','preview-slot 사용 예약이 다른 팀의 발표와 겹쳐 승인되지 않았다.'),
  ('R2','다른 팀이 매출 대시보드의 실시간 시각화 구현을 시작했다.'),('R1','web/sales/chart.tsx의 페이지 전환 변경에 리뷰를 요청한다.'),
  ('R4','preview-slot은 다른 팀이 오늘 하루 단독으로 사용한다.'),('R3','매출 API에서 snake_case 필드 제공을 중단하고 모두 camelCase로 제공한다.')],
 [('R4','Echo가 gpu-embedding을 오늘 18시까지 독점 사용한다.'),('R3','문서 임베딩 차원을 768에서 1024로 변경하기로 결정했다.'),
  ('R2','Foxtrot이 문서 의미 검색의 벡터 색인 갱신 작업을 시작했다.'),('R1','Dune가 doc-index의 증분 갱신 검수를 맡는다.'),
  ('R3','문서 검색 벡터 저장소를 pgvector에서 별도 벡터 서비스로 옮긴다.'),('R2','다른 작업자가 문서 변경 시 검색용 벡터를 다시 기록하는 코드를 작성한다.'),
  ('R1','src/search/indexer.py 변경 사항을 Echo가 리뷰한다.'),('R4','gpu-embedding 예약을 Foxtrot의 학습 작업에 오늘 종일 배정했다.'),
  ('R2','Echo가 문서 의미 색인의 오래된 벡터를 갱신하는 처리를 구현 중이다.'),('R1','doc-index 완료 조건에 문서 삭제 시 벡터 정리를 추가한다.'),
  ('R4','다른 팀이 gpu-embedding을 종료 시각까지 점유한다.'),('R3','새 문서 임베딩 모델은 768차원이 아닌 1536차원 벡터를 반환한다.'),
  ('R4','gpu-embedding의 남은 전용 시간을 다른 팀이 모두 예약했다.'),('R1','Dune의 문서 색인 갱신 패치 리뷰 담당은 Echo다.'),
  ('R2','Foxtrot이 문서 검색 벡터의 증분 재색인 로직 구현을 시작했다.'),('R3','문서 벡터를 PostgreSQL 밖으로 옮기고 pgvector 확장을 제거한다.'),
  ('R3','임베딩 서비스가 이제 문서당 512개 성분의 벡터만 반환한다.'),('R4','gpu-embedding을 다른 팀의 야간 작업까지 계속 사용한다.'),
  ('R1','src/search/indexer.py의 증분 처리 변경에 리뷰를 요청한다.'),('R2','다른 작업자가 문서 임베딩 갱신과 벡터 색인 교체를 구현한다.')],
]

titles = ['진행', '결정', '자원', '담당', '검토', '의존성', '일정', '운영']
board = '# 합성 협업 보드\n\n' + '\n\n'.join(f'## {s["id"]}-{i+1:02d} {title}\n상태: 아직 변경 없음.' for s in sessions for i,title in enumerate(titles)) + '\n'
(ROOT/'BOARD.md').write_text(board)
batches=[]; labels=[]
for b in range(10):
    entries=[]
    # Alternate domain order to prevent selection from being a fixed position.
    for di in [(b+j)%4 for j in range(4)]:
        for offset in range(2):
            idx=2*b+offset; label, content=changes[di][idx]
            slot=(idx%8)+1; heading=f'{sessions[di]["id"]}-{slot:02d} {titles[slot-1]}'
            # IDs in titles are board section IDs, not session mentions: avoid
            # accidental F0 matches by replacing domain prefixes with numeric IDs.
            section=f'T{di*8+slot:02d} {titles[slot-1]}'
            item=f'B{b+1:02d}-{len(entries)+1:02d}'
            entries.append(dict(id=item, title=section, before='상태: 아직 변경 없음.', after=content))
            for si,s in enumerate(sessions):
                lab=label if si==di else 'N'
                if di==0 and idx==9 and si==1: lab='R3'
                if di==1 and idx==8 and si==0: lab='R3'
                labels.append(dict(case=f'B{b+1:02d}-{s["id"]}',item=item,label=lab))
    batches.append(dict(id=f'B{b+1:02d}', entries=entries))
# Board headings must be the exact headings that occur in the deltas.
board='# 합성 협업 보드\n\n'+'\n\n'.join(f'## T{i+1:02d} {titles[i%8]}\n상태: 아직 변경 없음.' for i in range(32))+'\n'
(ROOT/'BOARD.md').write_text(board)
write('fixture.json',dict(sessions=sessions,batches=batches))
write('labels-author.json',labels)
policy=dict(
    interpretation='10 independent deltas against the same base BOARD.md; each adds 8 changed sections. Not a sequential history.',
    taxonomy=dict(R1='세션 이름, 담당 항목 또는 담당 파일을 직접 지명한다.',R2='이름 지명 없이 다른 작업자가 동일 작업에 착수한다.',R3='작업 설명의 명시된 전제를 뒤집는다.',R4='명시된 필요 자원을 다른 작업자가 점유한다.',N='관련 없음'),
    precedence=['R4','R3','R2','R1'],
    ambiguous='독립 라벨이 일치하지 않은 셀은 AMBIGUOUS로 고정하고 주요 지표에서 제외한다. 이견 원문을 보존하며 별도 집계한다.',
    repeats=[f'B{b:02d}-{sessions[(b-1)%4]["id"]}' for b in range(1,11)],
    extra_repeats=3,
    F3_batches=['B01','B05','B10'],
    f0='변경 후 본문 또는 항목 제목에 세션 이름, 담당 항목, 파일 경로가 글자 그대로 포함되면 선택. 대소문자 구분. 자원 이름 및 전제 키워드는 추가하지 않는다.',
    metrics=dict(recall='TP_label / all_gold_label',precision='TP_related / predicted_related',unrelated_pass_rate='FP_N / all_gold_N; 계획서의 정밀도 설명은 이 비율을 가리키므로 두 지표 모두 보고',quote='각 예측 항목의 quote가 해당 변경 after의 연속 부분문자열이고 공백 제외 길이가 1 이상이면 충실. 서로 다른 항목 인용은 불충실.',repeats='같은 10사례의 본 실행 및 추가 3회, 총 4회의 전체 및 라벨별 재현율 max-min 비교. 분모 0이면 NA.'),
    thresholds=dict(R2_recall=.9,R3_recall=.9,quote=.95,repeat_spread=.1,source='계획 작성자의 제안값이며 사용자가 정한 값이 아님'),
    schedule='F0 40회; F1 및 F2 각각 기본40+추가30=70회; F3 3묶음×4세션=12회. F1/F2 첫 평가 호출부터 실제 모델 검증, 불일치/검증불가면 전체 실행 중단. 각 호출은 새 프로세스.'
)
write('policy.json',policy)
prompt='''당신은 협업 보드 변경 필터다. 주어진 세션의 작업 설명과 변경 diff만을 근거로, 그 세션이 읽어야 할 관련 변경을 모두 선택하라. 직접 지명, 다른 작업자와의 업무 겹침, 작업 전제 변경, 필요한 자원의 점유를 모두 고려하라. 무관한 변경은 제외하라. 변경 전 상태만으로 관련 있다고 판단하지 말고 변경 후 내용을 판정하라. 요약하거나 바꿔 말하지 마라. 도구는 사용하지 마라. JSON만 출력하라: {"items":[{"id":"변경 ID","title":"항목 제목 그대로","quote":"변경 후 보드 본문에서 한 글자도 바꾸지 않고 인용한 원문","reason":"이유 한 줄"}]}. 관련 항목이 없으면 {"items":[]}를 출력하라. 작업을 실행하거나 파일을 수정하지 마라.\n'''
(ROOT/'filter-prompt.txt').write_text(prompt)
label_prompt='''독립 보드 라벨러 역할이다. 최초 작성자의 라벨은 제공하지 않는다. 도구와 파일 접근 없이 아래 데이터만 읽고 모든 세션×변경을 라벨링하라. 각 배치는 같은 초기 보드에서 독립적으로 발생한다. R1=세션 이름/담당 항목/담당 파일 직접 지명, R2=다른 작업자가 동일 작업 착수(지명 없음), R3=명시된 작업 전제 뒤집음, R4=명시된 필요 자원 타 작업 점유, N=무관. 복수 해당이면 R4>R3>R2>R1 우선. 문서의 주제만 같고 실제 작업 겹침이나 명시 전제 영향이 없으면 N. 생략된 셀은 N으로 처리한다. 관련 셀을 빠짐없이 JSON {"labels":[{"case":"B01-Oriole","item":"B01-01","label":"R1"}]}로 반환하라.\n'''
(ROOT/'label-prompt.txt').write_text(label_prompt+json.dumps(dict(sessions=sessions,batches=batches),ensure_ascii=False))
files=['BOARD.md','fixture.json','labels-author.json','policy.json','filter-prompt.txt','label-prompt.txt','build_fixture.py']
write('freeze-inputs.json',dict(frozen_at=dt.datetime.now(dt.timezone.utc).isoformat(),sha256={f:hashlib.sha256((ROOT/f).read_bytes()).hexdigest() for f in files},stage='pre-inference input/author-label/policy freeze; independent labels and final reconciliation follow before filter inference'))
print('fixed:',len(sessions),'sessions;',len(batches),'batches;',len(labels),'label cells;',len(board.split('## '))-1,'sections')
