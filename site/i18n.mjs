import * as en from './content.mjs';
import * as ko from './content.ko.mjs';

export const localePreferenceKey = 'xsm.locale';
export const languageNames = { en: 'English', ko: '한국어' };

function supported(value) {
  if (typeof value !== 'string') return null;
  const primary = value.trim().toLowerCase().replaceAll('_', '-').split(/[;-]/)[0];
  return ['en', 'ko'].includes(primary) ? primary : null;
}

export function resolveLocale({ requested, saved, languages = [] } = {}) {
  return supported(requested) ?? supported(saved) ?? languages.map(supported).find(Boolean) ?? 'en';
}

export function readLocalePreference(storage) {
  try { return (storage ?? globalThis.localStorage)?.getItem(localePreferenceKey) ?? null; }
  catch { return null; }
}

export function saveLocalePreference(storage, locale) {
  try {
    const target = storage ?? globalThis.localStorage;
    if (!target) return false;
    target.setItem(localePreferenceKey, locale);
    return true;
  }
  catch { return false; }
}

export function getContent(locale) { return supported(locale) === 'ko' ? ko : en; }

const korean = {
  'Skip to content': '본문으로 건너뛰기',
  'xsm home': 'xsm 홈',
  'Main navigation': '주 메뉴',
  'How it works': '작동 방식',
  'How xsm works': 'xsm 작동 방식',
  'Docs': '사용 문서',
  'Get started': '시작하기',
  'Language': '언어',
  'Open menu': '메뉴 열기',
  'Close menu': '메뉴 닫기',
  'Menu': '메뉴',
  'Mobile navigation': '모바일 메뉴',
  'Supported runtimes and setup': '지원 런타임과 연결 안내',
  'All you need is': '필요한 것은',
  'a message channel.': '메시지 채널 하나뿐입니다.',
  'The rest is done by agents.': '나머지는 에이전트가 합니다.',
  'Agent collaboration replay': '에이전트 협업 시연',
  'Scripted replay · abbreviated output': '협업 과정을 재현한 시연 · 출력 발췌',
  'Session to display': '시연에서 볼 대상',
  'Lead': '팀장',
  'Workers': '워커',
  'Board': '보드',
  'Coordinator terminal': '팀장 터미널',
  'Worker terminals': '워커 터미널',
  'API worker terminal': 'API 담당 터미널',
  'UI worker terminal': 'UI 담당 터미널',
  'Shared team board': '공유 팀 보드',
  '1 coordinator · 3 peer workers · native sessions': '팀장 1 · 수평적인 워커 3 · 각자의 네이티브 세션',
  'API team · UI team · overlapping coordination team': 'API 팀 · UI 팀 · 팀장들이 함께 속한 조율 팀',
  'Pause': '일시정지',
  'Play': '재생',
  'Play replay': '시연 재생',
  'Pause replay': '시연 일시정지',
  'Replay': '다시 보기',
  'Replay this scene': '현재 장면 처음부터 다시 보기',
  'Replay chapters': '시연 장면',
  'Reduced motion is on. Choose a chapter to read the complete session output.': '동작 줄이기 설정에 따라 정지 화면을 표시합니다. 장면을 선택해 전체 출력을 읽을 수 있습니다.',
  'READ THE GUIDE': '이 장면의 사용법',
  'Read the guide ↗': '이 장면의 사용법 ↗',
  'Using the team board ↗': '팀 보드에 상태 남기기 ↗',
  'GET STARTED': '시작하기',
  'Install and start collaborating': '설치와 첫 협업',
  'Ask the agent you already use to set up the connection.': '사용 중인 에이전트에게 연결을 맡기세요.',
  'Copy installation request': '설치 요청 문장 복사',
  'Read the setup guide ↗': '단계별 안내 읽기 ↗',
  'Documentation topics': '문서 주제',
  'Reference': '상세 안내',
  'Supported runtimes': '런타임별 지원',
  'Full reference ↗': '전체 레퍼런스 ↗',
  'Replay for this guide': '문서와 연결된 시연',
  'THIS GUIDE IN ACTION': '이 설명의 장면',
  'Expand replay ↗': '크게 보기 ↗',
  'The replay follows the guide you are reading. Pause it to read at your own pace.': '설명의 주제를 따라 시연도 함께 바뀝니다. 재생을 멈춰두고 문서를 읽어도 괜찮습니다.',
  'On this page': '이 페이지에서',
  'Messaging and shared state for agent sessions': '에이전트 세션의 메시지 전달과 공동 상태를 위한 도구',
  'Source ↗': '소스 코드 ↗',
  'Copy this request': '이 문장을 복사하세요',
  'Close copy dialog': '복사 창 닫기',
  'Your browser did not allow automatic copying. Copy the selected request below.': '브라우저가 자동 복사를 허용하지 않았습니다. 아래 선택된 문장을 직접 복사할 수 있습니다.',
  'Request to copy': '복사할 요청 문장',
  'Close': '닫기',
  'SEND TO YOUR AGENT': '내 에이전트에게 보내기',
  'Previous and next guide': '이전·다음 문서',
  'Back to the replay': '시연으로 돌아가기',
  'Request copied. Paste it into your agent.': '문장을 복사했습니다. 에이전트에게 붙여넣으세요.',
  'Replay paused.': '시연을 일시정지했습니다.',
  'Playing the replay.': '시연을 재생합니다.',
  'Read the full transcript': '장면 전체 대화 읽기',
  'Scene {number}. {title}': '장면 {number}. {title}',
  'See how xsm connects agent sessions for long-running collaborative work. Interactive replay and documentation.': 'xsm으로 에이전트 세션을 연결하고 장기 작업을 함께 운영하는 모습을 살펴보세요. 인터랙티브 시연과 사용 문서입니다.',
};

export function translate(locale, key, values = {}) {
  const text = supported(locale) === 'ko' ? (korean[key] ?? key) : key;
  return text.replace(/\{(\w+)\}/g, (match, name) => values[name] ?? match);
}

// Capture only the static shell, before scene and document output is inserted.
// Restoring English uses the original strings, not a reverse translation.
export function createStaticTranslator(document) {
  const texts = [];
  const walker = document.createTreeWalker(document.body, 4);
  while (walker.nextNode()) {
    const node = walker.currentNode;
    const original = node.nodeValue;
    const key = original.trim();
    if (Object.hasOwn(korean, key)) texts.push({ node, original, key });
  }
  const attributes = [];
  document.querySelectorAll('[aria-label], [title], [placeholder], meta[name="description"]').forEach(node => {
    for (const name of ['aria-label', 'title', 'placeholder', 'content']) {
      const original = node.getAttribute(name);
      if (original && Object.hasOwn(korean, original)) attributes.push({ node, name, original });
    }
  });
  return locale => {
    for (const { node, original, key } of texts) node.nodeValue = original.replace(key, translate(locale, key));
    for (const { node, name, original } of attributes) node.setAttribute(name, translate(locale, original));
  };
}
