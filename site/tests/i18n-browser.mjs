import assert from 'node:assert/strict';
import { writeFile } from 'node:fs/promises';

export async function run({ spaceId, baseURL, outputDirectory }) {
  const task = await taskSpace(spaceId), page = task.page('p1');
  const checks = [];
  const check = (name, value) => { assert.ok(value, name); checks.push(name); };
  const language = locale => page.waitForFunction(value => document.documentElement.lang === value, locale);
  const userAgent = await page.evaluate(() => navigator.userAgent);
  await page.goto(`${baseURL}?lang=en`);
  await page.waitForSelector('#demo[data-scene="team"]');
  const previous = await page.evaluate(() => localStorage.getItem('xsm.locale'));
  // Only this app's preference on the verifier's temporary localhost origin.
  await page.evaluate(() => localStorage.removeItem('xsm.locale'));
  try {
    await page.cdp('Emulation.setUserAgentOverride', { userAgent, acceptLanguage: 'ko-KR,ko,en-US,en' });
    await page.cdp('Emulation.setEmulatedMedia', { features: [{ name: 'prefers-reduced-motion', value: 'reduce' }] });
    await page.goto(baseURL);
    await language('ko');
    check('Korean browser selects Korean automatically on first visit', await page.evaluate(() => navigator.languages[0].startsWith('ko') && document.querySelector('#language-select').value === 'ko' && document.querySelector('.main-nav').textContent.includes('사용 문서')));
    check('Korean headline uses the original message-channel meaning', await page.evaluate(() => document.querySelector('.hero h1').textContent.includes('메시지 채널')));
    await page.goto(`${baseURL}#guide/progress`);
    await page.waitForSelector('#guide-article h1');
    const before = await page.evaluate(() => ({ scene: document.querySelector('#demo').dataset.scene, elapsed: document.querySelector('#demo').dataset.elapsed, playing: document.querySelector('#demo').dataset.playing, hash: location.hash }));
    await page.snapshot();
    await page.selectOption('#language-select', 'en');
    await language('en');
    const after = await page.evaluate(() => ({ scene: document.querySelector('#demo').dataset.scene, elapsed: document.querySelector('#demo').dataset.elapsed, playing: document.querySelector('#demo').dataset.playing, hash: location.hash }));
    assert.deepEqual(after, before);
    check('switching language preserves the document, chapter, time and pause', true);
    check('English can be selected and saved on a Korean browser', await page.evaluate(() => localStorage.getItem('xsm.locale') === 'en' && location.search.includes('lang=en') && document.querySelector('#guide-article h1').textContent === 'Fable maintains the long-term plan'));
    await page.goto(`${baseURL}#guide/start`);
    await language('en');
    check('the saved language wins on the next visit without a URL override', await page.evaluate(() => document.querySelector('#guide-article h1').textContent.includes('Install')));
    await page.goto(`${baseURL}?lang=ko#guide/progress`);
    await language('ko');
    check('an explicit Korean URL wins over a saved English choice', await page.evaluate(() => localStorage.getItem('xsm.locale') === 'en' && document.querySelector('#guide-article h1').textContent.includes('진척')));

    for (const [topic, scene] of [['start', 'team'], ['team', 'team'], ['messages', 'direct'], ['board', 'direct'], ['progress', 'progress'], ['teams', 'teams'], ['handover', 'progress'], ['runtimes', 'team']]) {
      await page.click(`#guide-navigation a[data-topic="${topic}"]`, { label: 'read Korean documentation' });
      await page.waitForFunction(value => location.hash === `#guide/${value}`, topic);
      check(`Korean guide ${topic} and its replay are localized`, await page.evaluate(value => document.querySelector('#demo').dataset.scene === value && /\p{Script=Hangul}/u.test(document.querySelector('#guide-article h1').textContent) && document.querySelector('#language-select').value === 'ko', scene));
    }
    await page.click('#guide-navigation a[data-topic="start"]', { label: 'open translated setup guide' });
    await page.waitForFunction(() => location.hash === '#guide/start');
    await page.evaluate(() => { window.originalI18nClipboard = navigator.clipboard.writeText; navigator.clipboard.writeText = async text => { window.i18nCopied = text; }; });
    await page.click('[data-copy="start-0"]', { label: 'copy Korean setup request' });
    await page.waitForFunction(() => Boolean(window.i18nCopied));
    check('Korean copy requests and feedback use the current locale', await page.evaluate(() => window.i18nCopied.includes('설치') && document.querySelector('#toast').textContent.includes('복사')));
    await page.selectOption('#language-select', 'en'); await language('en');
    await page.click('[data-copy="start-0"]', { label: 'copy English setup request' });
    await page.waitForFunction(() => window.i18nCopied.startsWith('Install'));
    check('switching back replaces cached copy requests with English', await page.evaluate(() => !/\p{Script=Hangul}/u.test(window.i18nCopied)));
    await page.evaluate(() => { navigator.clipboard.writeText = window.originalI18nClipboard; delete window.originalI18nClipboard; delete window.i18nCopied; });

    for (const width of [320, 390, 1440]) for (const locale of ['ko', 'en']) {
      await page.goto(`${baseURL}__viewport?width=${width}`);
      await page.waitForFunction(() => Boolean(document.querySelector('#responsive-frame')?.contentDocument?.querySelector('#demo')?.dataset.scene));
      await page.evaluate(async value => {
        const frame = document.querySelector('#responsive-frame');
        await new Promise(resolve => { frame.addEventListener('load', resolve, { once: true }); frame.src = `/index.html?lang=${value}#guide/start`; });
      }, locale);
      await page.waitForFunction(value => document.querySelector('#responsive-frame').contentDocument.documentElement.lang === value, locale);
      check(`${locale} guide and language control fit ${width}px`, await page.evaluate(({ width, locale }) => {
        const scope = document.querySelector('#responsive-frame').contentWindow, doc = scope.document;
        return scope.innerWidth === width && doc.documentElement.scrollWidth <= width + 1 && doc.querySelector('#language-select').getBoundingClientRect().right <= width && doc.documentElement.lang === locale;
      }, { width, locale }));
      check(`${locale} page boxes have more vertical padding at ${width}px`, await page.evaluate(() => {
        const doc = document.querySelector('#responsive-frame').contentDocument;
        return Number.parseFloat(getComputedStyle(doc.querySelector('.documentation-bridge')).paddingTop) >= 36 && Number.parseFloat(getComputedStyle(doc.querySelector('.start-strip')).paddingBottom) >= 40;
      }));
      if (width === 1440) check(`${locale} documentation has a wider horizontal gap`, await page.evaluate(() => Number.parseFloat(getComputedStyle(document.querySelector('#responsive-frame').contentDocument.querySelector('.guide-view')).columnGap) >= 56));
    }
    await page.goto(`${baseURL}?lang=ko#guide/start`); await language('ko');
    const result = { passed: checks.length, checks, browserPreference: 'Emulated native Chrome Accept-Language/navigator.languages; no location or IP lookup.', clipboard: 'API boundary checked without changing the OS clipboard.' };
    await writeFile(`${outputDirectory}/i18n-browser.json`, JSON.stringify(result, null, 2) + '\n');
    console.log(JSON.stringify(result));
    return result;
  } catch (error) {
    await writeFile(`${outputDirectory}/i18n-browser-failure.json`, JSON.stringify({ checks, error: String(error) }, null, 2) + '\n');
    throw error;
  } finally {
    await page.goto(`${baseURL}?lang=en`);
    await page.waitForSelector('#demo[data-scene="team"]');
    await page.evaluate(value => { if (value === null) localStorage.removeItem('xsm.locale'); else localStorage.setItem('xsm.locale', value); }, previous);
    await page.cdp('Emulation.setUserAgentOverride', { userAgent });
  }
}
