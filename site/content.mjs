export const repository = 'https://github.com/ysys143/xsm';
export const installPrompt = `${repository} 의 xsm을 이 머신의 Claude Code와 Codex에 설치해줘.
설치 상태를 검증하고 내가 직접 해야 하는 단계가 남으면 알려줘.`;
export const teamPrompt = `알림 기능을 완성하는 팀을 꾸려줘.
너는 팀장으로 목표·완료 기준·계획과 진척을 관리해.
API는 Opus, UI는 Sol, 검증은 Luna에게 맡겨.
워커들은 같은 깊이에서 서로 직접 협업하고,
현행 결정과 담당·진행은 팀 보드에 남겨줘.`;

const message = (at, from, text, kind = 'reply') => ({ at, from, text, kind });
const item = (state, text) => ({ state, text });
const waiting = { at: 0, title: '팀장의 계획을 기다리는 중', items: [item('waiting', '목표·담당·완료 기준을 정리합니다.')] };

export const scenes = [
  {
    id: 'team', number: '01', short: '팀 구성', title: '자연어로 정하는 역할과 협업 관계',
    day: 'DAY 01', duration: 18000, topic: 'team', status: '목표와 완료 기준 정리',
    caption: '팀과 역할 구성',
    description: '목표와 역할을 알려주세요. 팀장은 완료 기준과 담당을 정리하고, 워커들은 각자의 세션에서 일을 시작합니다.',
    actors: { lead: ['Claude Code', 'Fable', '팀장'], api: ['Claude Code', 'Opus', 'API'], ui: ['Codex', 'Sol', 'UI'], qa: ['Codex', 'Luna', '검증'] },
    messages: {
      lead: [message(0, 'USER → TEAM', '알림 기능을 끝까지 맡아줘.\n너는 팀장으로 계획과 진행을 관리해.\nAPI·UI·검증은 워커들과 나눠서 해.', 'user'), message(3500, 'FABLE', '먼저 목표와 완료 기준을 정리하겠습니다.\nAPI는 Opus, UI는 Sol, 검증은 Luna.\n공동 계획과 담당은 팀 보드에 남길게요.')],
      api: [message(6500, 'OPUS / API', '알림 스키마와 API 계약을 정리하고\nUI 담당과 맞출게요.')],
      ui: [message(9000, 'SOL / UI', 'API 계약을 확인해서\n알림 목록과 읽음 상태 UI를 맡을게요.')],
      qa: [message(11500, 'LUNA / 검증', '완료 기준을 확인했습니다.\n회귀 검사 항목을 준비할게요.')],
    },
    boards: [waiting, { at: 5500, title: '목표 · 담당 · 완료 기준', items: [item('done', '목표: 알림 생성부터 읽음 처리까지'), item('active', '담당: Opus API / Sol UI / Luna 검증'), item('waiting', '완료: 합의한 동작과 회귀 검사 확인')] }],
    flows: [{ at: 6500, text: 'Fable → 워커들 · 역할과 완료 기준 전달' }, { at: 11500, text: 'Luna → Fable · 담당 확인' }],
  },
  {
    id: 'direct', number: '02', short: '직접 협업', title: '워커 간 직접 요청과 회신',
    day: 'DAY 02', duration: 16000, topic: 'messages', status: 'API·UI 병렬 구현',
    caption: '워커 간 직접 요청과 회신',
    description: '워커는 필요한 상대에게 직접 묻고 답합니다. 팀 전체에 영향을 주는 결정은 보드에 남기고, 팀장은 그 기록으로 계획을 관리합니다.',
    actors: { lead: ['Claude Code', 'Fable', '팀장'], api: ['Claude Code', 'Opus', 'API'], ui: ['Codex', 'Sol', 'UI'], qa: ['Codex', 'Luna', '검증'] },
    messages: {
      lead: [message(0, 'FABLE / 현재 계획', 'API·UI는 병렬 진행합니다.\n구현 세부 사항은 담당 워커끼리 협의하고,\n공통 계약이 바뀌면 보드에 남겨주세요.')],
      api: [message(2300, 'OPUS → SOL', '알림 이벤트에 read_at을 추가했어.\nUI에서 처리 가능해?', 'dm'), message(8500, 'OPUS / 계약 기록', '좋아. 합의한 필드를 보드에 남길게.')],
      ui: [message(5200, 'SOL → OPUS', '가능해. 읽음 상태를 먼저 반영하고\n목록 갱신을 붙일게.', 'dm')],
      qa: [message(10500, 'LUNA → SOL', '읽음 상태 변경도 회귀 검사에 넣을게.', 'dm')],
    },
    boards: [{ at: 0, title: '알림 기능 / 진행 중', items: [item('done', '스키마와 API 계약 합의'), item('active', 'API·UI 병렬 구현'), item('waiting', 'Luna: 통합 검증과 사용자 확인')] }, { at: 9000, title: '공통 계약 갱신', items: [item('done', '결정: 읽음 상태는 read_at으로 전달'), item('active', 'Sol: UI 반영 / Opus: API 반영'), item('waiting', 'Luna: 읽음 상태 회귀 검사')] }],
    flows: [{ at: 2300, text: 'Opus → Sol · DM 요청 전달' }, { at: 5200, text: 'Sol → Opus · 답변 수신' }, { at: 9000, text: 'Opus → 팀 보드 · 공통 결정 기록' }],
  },
  {
    id: 'progress', number: '03', short: '계획·진척 관리', title: 'Fable의 장기 계획·진척 관리',
    day: 'DAY 03', duration: 18000, topic: 'progress', status: '8 / 12 완료 · 2 진행 · 2 대기',
    caption: '계획·결정·담당·진행 기록',
    description: '팀장은 워커의 보고를 완료 기준과 대조해 진척을 판단합니다. 완료·진행·막힘과 다음 작업 순서를 보드에 남겨 장기 계획을 유지합니다.',
    actors: { lead: ['Claude Code', 'Fable', '팀장'], api: ['Claude Code', 'Opus', 'API'], ui: ['Codex', 'Sol', 'UI'], qa: ['Codex', 'Luna', '검증'] },
    messages: {
      lead: [message(0, 'USER → FABLE', '현재 계획에서 어디까지 끝났어?\n막힌 일과 다음 할 일을 정리하고 계속 진행해.', 'user'), message(10500, 'FABLE / 진척 보고', '12개 항목 중 8개를 검증했습니다.\n재연결 중복 알림이 남아 UI와 검증의\n다음 작업 순서를 조정해 보드에 반영합니다.')],
      api: [message(2200, 'OPUS → FABLE', '스키마와 API를 검증했습니다.\n결과와 변경 계약을 보드에 남깁니다.')],
      qa: [message(4800, 'LUNA → SOL', '재연결 시 중복 알림을 재현했어.\n재현 조건을 보낼게.', 'dm')],
      ui: [message(7300, 'SOL → LUNA', '원인을 수정한 뒤 다시 검증을 요청할게.', 'dm')],
    },
    boards: [{ at: 0, title: '다음 날 / 이전 계획에서 계속', items: [item('done', 'API·스키마 검증 결과 확인'), item('active', 'UI와 통합 검증 진행'), item('waiting', '완료 기준별 결과 취합')] }, { at: 11500, title: '8 / 12 완료 · 근거와 다음 순서', progress: 8 / 12, items: [item('done', '완료: 스키마·API 통합 검증'), item('active', '진행: 재연결 중복 알림 수정'), item('blocked', '대기: 수정 뒤 회귀 검사와 사용자 확인')] }],
    flows: [{ at: 4800, text: 'Luna → Sol · 재현 조건 공유' }, { at: 10500, text: 'Fable · 완료 기준과 결과 대조' }, { at: 11500, text: 'Fable → 팀 보드 · 계획 갱신' }],
  },
  {
    id: 'teams', number: '04', short: '복수 팀 조율', title: '복수 팀의 협업과 조율',
    day: 'TEAM API × TEAM UI', duration: 16000, topic: 'teams', status: '독립 실행 · 필요한 정보만 공유',
    caption: '팀 간 합의와 보드 반영',
    description: '각 팀은 자기 계획과 보드로 진행합니다. 팀장들이 함께 참여하는 조율 팀에서 공통 계약과 통합 시점을 합의하고 각 팀의 계획에 반영합니다.',
    actors: { lead: ['Claude Code', 'Fable', 'API 팀장'], api: ['Claude Code', 'Fable', 'UI 팀장'], ui: ['Codex', 'Sol', 'UI 워커'], qa: ['조율 팀', '팀장들', '공동 결정'] },
    messages: {
      lead: [message(0, 'USER → TEAM LEADS', 'API 팀과 UI 팀은 독립적으로 진행해.\n팀장들은 공통 계약과 통합 시점을 맞추고\n각자의 팀 계획에 반영해.', 'user'), message(8500, 'API 팀장 → UI 팀장', 'v2 계약과 금요일 통합에 합의합니다.\nAPI 팀 보드와 작업 순서에 반영하겠습니다.', 'dm')],
      api: [message(3000, 'UI 팀장 → API 팀장', 'read_at 계약은 v2로 맞출게요.\n금요일에 통합 검증을 진행하죠.', 'dm')],
      ui: [message(11000, 'SOL / UI 팀', '우리 팀 보드에서 v2 계약 확인했어.\nUI에 반영할게.')],
      qa: [message(12500, '조율 팀 보드', '각 팀이 합의한 계약과 통합 시점을 공유합니다.')],
    },
    boards: [{ at: 0, title: '조율 팀 / 합의할 항목', items: [item('active', '알림 이벤트 공통 계약'), item('waiting', '각 팀 계획과 담당 반영'), item('waiting', '통합 검증 시점 합의')] }, { at: 9500, title: '팀 사이의 공통 결정', items: [item('done', '결정: 알림 이벤트 v2 계약'), item('active', '담당: 각 팀장이 자기 팀 계획에 반영'), item('waiting', '합의: 금요일 통합 검증')] }],
    flows: [{ at: 3000, text: 'UI 팀장 ↔ API 팀장 · 조율 팀에서 협의' }, { at: 9500, text: '팀장들 → 조율 보드 · 합의 기록' }, { at: 11000, text: '각 팀 · 자기 계획에 반영하고 실행' }],
  },
];

const source = path => `${repository}/blob/main/${path}`;
export const topics = [
  {
    id: 'start', label: '시작하기', scene: 0, title: '설치와 첫 협업',
    intro: 'Claude Code와 Codex에 xsm을 연결하고, 평소처럼 말로 요청하세요. 에이전트는 xsm 안내를 읽고 세션을 찾아 연락합니다.',
    sections: [
      { title: '01  에이전트에게 설치를 맡기세요', paragraphs: ['사용 중인 Claude Code나 Codex에 아래 문장을 보내세요. 에이전트가 설치와 상태 점검을 수행하고, 새 세션 시작이나 훅 신뢰처럼 사람이 해야 하는 단계가 남으면 알려줍니다.'], prompt: installPrompt, copy: '설치 요청 문장 복사' },
      { title: '02  첫 대화를 연결하세요', paragraphs: ['설치 후 새 세션에서 협업할 상대를 찾아달라고 하세요. 에이전트가 후보를 보여주면 상대를 고릅니다. 다른 폴더나 세션에 연결할 때는 필요한 범위의 사용자 확인을 거칩니다.'], prompt: '지금 UI 작업 중인 세션을 찾아서 후보를 보여줘.\n내가 고른 세션에 알림 API 계약 검토를 요청해줘.', copy: '첫 협업 요청 복사' },
      { title: '03  역할을 정하고 작업을 이어가세요', paragraphs: ['장기 병렬 개발에는 계획을 유지하는 팀장과 같은 깊이의 워커 구성을 권합니다. 팀장은 전체 목표와 완료 기준을 관리하고, 워커들은 담당 범위에서 직접 협업합니다.'], link: ['team', '팀과 역할 구성하기'] },
    ], references: [['설치·사용 안내', source('README_ko.md')], ['설치 상태 점검', source('skills/xsm/references/troubleshooting.md')]],
  },
  {
    id: 'team', label: '팀 구성하기', scene: 0, title: '역할과 협업 관계',
    intro: '역할은 자연어로 정합니다. 팀장을 누구로 둘지, 워커가 무엇을 맡을지, 누구와 직접 협업할지 알려주세요.',
    sections: [
      { title: '팀장은 목표와 계획을 유지합니다', paragraphs: ['Fable을 선택한 세션을 팀장으로 두고 목표·완료 기준·주요 제약을 전달합니다. 팀장은 과제를 나누고 결과를 대조하며 계획과 진척을 유지합니다. 모델 선택은 각 런타임의 설정에서 합니다.'] },
      { title: '워커는 같은 깊이에서 실행합니다', paragraphs: ['주력·보조는 업무 역할입니다. Opus·Sol을 구현과 검증에, Luna 같은 보조 워커를 범위가 명확한 조사·검사에 배치할 수 있습니다. 워커끼리 질문하고 도움을 요청해도 생성 깊이가 늘어나지는 않습니다.', '한 번의 요청으로 끝나는 작업은 하네스의 서브에이전트에 맡기고, 문맥을 유지하며 계속 협업할 상대는 독립 워커 세션으로 둡니다.'], prompt: teamPrompt, copy: '팀 구성 요청 복사' },
      { title: '조직은 작업에 맞춰 정합니다', paragraphs: ['이 구성은 장기 병렬 개발에 권하는 운영 방식입니다. 동등한 구성원이 토론하는 조직이나 서로 검토하는 관계도 말로 지정할 수 있습니다. xsm은 팀의 통신과 공동 상태를 제공하며, 조직의 의사결정을 자동 집행하지 않습니다.', '자연어 역할 지시와 실제 팀 등록·통신 권한은 구분됩니다. 에이전트가 필요한 절차를 수행하고, 사용자가 판단해야 하는 범위는 확인합니다.'] },
    ], references: [['조직 운영 모델', source('docs/xsm/ORGANIZATION.md')], ['팀·보드 사용법', source('skills/xsm/references/teams.md')]],
  },
  {
    id: 'messages', label: '요청하고 답받기', scene: 1, title: 'DM으로 요청하고 답받기',
    intro: 'DM은 행동이나 답을 요청하는 경로입니다. 워커는 필요한 상대에게 직접 질문하고, 요청한 세션으로 결과를 돌려줍니다.',
    sections: [
      { title: '질문은 필요한 상대에게 직접', paragraphs: ['구체적인 배경과 필요한 답을 함께 전달하세요. API 담당과 UI 담당이 세부 계약을 맞추는 일까지 팀장이 중계할 필요는 없습니다. 공통 전제나 담당이 바뀌면 팀장에게 알리고 보드에 남깁니다.'], prompt: 'UI 담당에게 read_at으로 읽음 상태를 처리할 수 있는지 물어봐.\n답을 받아 API 계약에 반영하고, 공통 결정은 팀 보드에 남겨줘.', copy: '협업 요청 복사' },
      { title: '저장·전달·수신 확인·답변은 서로 다릅니다', paragraphs: ['메시지가 저장된 것, 상대 런타임에 도착한 것, 상대가 읽고 수신 확인한 것, 실제 답변한 것은 별개의 사실입니다. 전달 확인만으로 과제가 끝났다고 판단하지 않습니다.', '답은 해당 세션으로 돌아옵니다. 기다리기 위해 긴 셸 폴링 루프를 돌리는 방식 대신, 에이전트가 다른 작업을 진행하고 요청 ID로 상태와 답변을 회수합니다. 깨우기 동작은 런타임과 연결 설정에 따라 다릅니다.'] },
      { title: '찾았다고 연결되는 것은 아닙니다', paragraphs: ['같은 저장소의 세션이나 명시적으로 공개한 세션을 찾을 수 있습니다. 발견과 연결 권한은 구분됩니다. 공개된 상대라는 이유만으로 모든 폴더나 세션이 서로 대화할 수 있는 것은 아닙니다.'] },
    ], references: [['세션 찾기와 메시징', source('skills/xsm/references/messaging.md')], ['사용자 확인과 연결 범위', source('skills/xsm/references/permissions.md')]],
  },
  {
    id: 'board', label: '팀 보드', scene: 1, title: '현행 계획과 결정을 남기는 보드',
    intro: 'DM에서 누군가에게 행동을 요청하고, 보드에는 팀 전체에 유효한 계획·결정·담당·진행을 남깁니다.',
    sections: [
      { title: '다시 읽을 수 있는 공동 상태', paragraphs: ['팀 보드는 각 항목의 현재 상태를 보여줍니다. 목표와 완료 기준, 현재 결정, 담당, 진행과 막힘을 기록해 모든 내용을 팀장 한 세션의 대화 문맥에만 두지 않습니다.'] },
      { title: '읽은 상태를 바탕으로 갱신', paragraphs: ['다른 구성원이 작성한 항목을 고치기 전에는 현재 내용을 읽습니다. 읽지 않은 변경이 있다면 한쪽을 조용히 덮어쓰는 대신 함께 남기며, 두 내용을 확인한 뒤 현행 상태를 정리합니다.'], prompt: '팀 보드의 현재 계획과 담당을 읽어줘.\n합의한 API 계약 변경을 반영하고, 영향을 받는 워커에게 알려줘.', copy: '보드 갱신 요청 복사' },
      { title: '기록과 행동 요청을 연결', paragraphs: ['결정 때문에 누군가가 일을 해야 한다면 DM에서 관련 보드 항목을 가리키며 구체적으로 요청하세요. DM과 보드에 서로 다른 계획을 중복 관리하지 않습니다.'] },
    ], references: [['팀 보드 안내', source('skills/xsm/references/teams.md')]],
  },
  {
    id: 'progress', label: '계획과 진척 관리', scene: 2, title: 'Fable의 장기 계획·진척 관리',
    intro: '팀장은 각 워커의 보고를 완료 기준과 대조합니다. 무엇을 끝냈는지, 무엇이 막혔는지, 다음에 무엇을 해야 하는지 계획에 반영합니다.',
    sections: [
      { title: '계획에는 완료 판단 방법도 포함합니다', paragraphs: ['과제마다 담당, 필요한 입력, 기대 산출물과 확인 방법을 지정합니다. 단순한 답변 수신과 검증된 과제 완료를 구분합니다.'], prompt: '현재 계획을 완료·진행·막힘으로 나눠 보고해줘.\n완료한 항목의 검증 근거와 남은 일을 정리하고,\n의존성을 확인해 다음 작업 순서를 갱신해줘.', copy: '진척 관리 요청 복사' },
      { title: '진척은 에이전트가 근거로 판단합니다', paragraphs: ['시연의 “8 / 12 완료”는 예시 계획의 완료 항목을 집계한 수치입니다. xsm이 개발 완료율을 자동 추정하는 기능은 아닙니다. 팀장이 워커의 결과와 검사 근거를 확인해 완료·진행·대기를 구분합니다.'] },
      { title: '막힘이 생기면 계획을 갱신합니다', paragraphs: ['검증 담당이 중복 알림을 발견하면 UI 담당과 직접 재현 조건을 맞춥니다. 팀장은 수정 뒤 재검증이 필요하다는 의존성을 계획에 반영하고, 사용자에게 필요한 판단을 모아 보고합니다.'] },
      { title: '다음 날에도 기록에서 이어갑니다', paragraphs: ['목표·현행 결정·담당·진행을 보드에 남겨 장기 계획을 뒷받침합니다. 세션이 바뀔 때는 기록과 작업 맥락을 정리하고 인수인계 절차로 연결합니다.'], link: ['handover', '세션과 작업 이어받기'] },
    ], references: [['팀장·워커의 운영 원칙', source('docs/xsm/ORGANIZATION.md')]],
  },
  {
    id: 'teams', label: '여러 팀 운영', scene: 3, title: '복수 팀의 협업과 조율',
    intro: '큰 작업은 목표나 책임 영역별로 팀을 나눕니다. 각 팀은 자신의 계획과 보드로 진행하고, 필요한 정보만 공유합니다.',
    sections: [
      { title: '팀장들은 조율 팀에도 참여합니다', paragraphs: ['API·UI 팀장은 자기 작업 팀과 별도의 조율 팀에 함께 속할 수 있습니다. 조율 팀에서는 공통 계약, 의존성과 통합 시점처럼 팀 사이에 필요한 내용을 협의합니다. 이 다중 소속은 생성 깊이를 늘리지 않습니다.'], prompt: 'API 팀과 UI 팀은 독립적으로 진행해.\n두 팀장은 별도 조율 팀에도 함께 참여하고,\n공통 계약과 통합 시점을 맞춰줘.\n합의한 내용은 각자 팀의 계획과 보드에 반영해.', copy: '복수 팀 운영 요청 복사' },
      { title: '합의는 각 팀의 실행 계획으로', paragraphs: ['팀장들은 동등하게 협의하고 공통 결정을 조율 보드에 남깁니다. 각 팀장은 그 합의를 가리켜 자기 팀의 담당과 계획을 갱신합니다. 모든 세부 대화를 모든 팀에 반복 전달할 필요는 없습니다.'] },
      { title: '통신 범위는 별도로 유지합니다', paragraphs: ['여러 팀이 있다는 이유만으로 모든 상태와 메시지에 접근할 권한이 생기지 않습니다. 필요한 상대와 연결하고, 사용자가 정한 범위 안에서 협업합니다.'] },
    ], references: [['복수 팀 조직 모델', source('docs/xsm/ORGANIZATION.md')], ['팀 운영', source('skills/xsm/references/teams.md')]],
  },
  {
    id: 'handover', label: '세션 이어받기', scene: 2, title: '세션과 작업 맥락 이어받기',
    intro: '작업을 다른 세션에 넘길 때는 현재 목표와 결정, 검증한 결과, 남은 일과 보드 위치를 먼저 정리합니다.',
    sections: [
      { title: '지속할 문맥을 정리합니다', paragraphs: ['어떤 완료 기준으로 어디까지 확인했는지, 누구의 답을 기다리는지, 다음 단계의 입력이 무엇인지 전달하세요. 새 담당자가 보드와 산출물을 읽고 이어갈 수 있어야 합니다.'], prompt: '지금 작업을 넘길 수 있게 인수인계 내용을 정리해줘.\n목표·현행 결정·완료 근거·남은 일·대기 중인 요청과\n관련 보드·파일 위치를 포함해줘.', copy: '인수인계 정리 요청 복사' },
      { title: '역할 인계와 프로필 승계를 구분합니다', paragraphs: ['다른 대화에 작업과 팀 내 자리를 넘기는 인수인계와, 같은 네이티브 대화를 다른 설정 홈으로 옮기는 프로필 승계는 다른 절차입니다. 실제 대상을 확인하고 해당 도구가 요구하는 사용자 선택을 따릅니다.'] },
    ], references: [['인수인계', source('skills/xsm/references/teams.md')], ['프로필 승계', source('skills/xsm/references/migration.md')]],
  },
  {
    id: 'runtimes', label: '런타임별 지원', scene: 0, title: '런타임과 연결 방식',
    intro: '주 시연은 Claude Code와 Codex를 사용합니다. xsm 0.6.0에는 Pi·OpenCode·Hermes·OpenClaw의 실험적 연결도 포함되어 있습니다.',
    sections: [
      { title: '기존 런타임에서 이어서 사용합니다', paragraphs: ['xsm의 플러그인·연결을 설치하고 해당 런타임을 다시 시작하거나 다시 불러옵니다. 자체 에이전트 런타임이나 세션 래퍼로 작업 방식을 옮기지 않습니다.'] },
      { title: '연결마다 전달 경로가 다릅니다', paragraphs: ['메시지 송신과 inbox·ACK 등 공통 동작을 사용하지만, 쉬는 세션 깨우기·질문 UI·메신저 게이트웨이는 런타임과 설정에 따라 다릅니다. 이 시연은 모든 런타임의 기능이 동일하다는 의미가 아닙니다.'] },
    ], references: [['Claude Code·Codex 설치', source('README_ko.md')], ['Pi', source('docs/protocol/pi.md')], ['OpenCode', source('docs/protocol/opencode.md')], ['Hermes', source('docs/protocol/hermes.md')], ['OpenClaw', source('docs/protocol/openclaw.md')]],
  },
];
