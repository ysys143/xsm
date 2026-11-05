import assert from 'node:assert/strict';
import { mkdir, writeFile } from 'node:fs/promises';

// Executed by ego-browser nodejs, which supplies taskSpace and the Page API.
export async function run({ spaceId, baseURL, outputDirectory }) {
  const task = await taskSpace(spaceId);
  const page = task.page('p1');
  const checks = [];
  const check = (name, value) => { assert.ok(value, name); checks.push(name); };
  const read = () => page.evaluate(() => {
    const scope = document.querySelector('#responsive-frame')?.contentWindow ?? window;
    const doc = scope.document;
    const demo = doc.querySelector('#demo');
    return {
      ready: Boolean(demo?.dataset.scene),
      scene: demo?.dataset.scene,
      playing: demo?.dataset.playing,
      elapsed: Number(demo?.dataset.elapsed),
      focus: demo?.dataset.focus,
      hash: scope.location.hash,
      heading: doc.querySelector('#guide-article h1')?.textContent,
      overflow: doc.documentElement.scrollWidth > scope.innerWidth + 1,
      width: scope.innerWidth,
    };
  });
  const waitScene = scene => page.waitForFunction(value => {
    const doc = document.querySelector('#responsive-frame')?.contentDocument ?? document;
    return doc.querySelector('#demo')?.dataset.scene === value;
  }, scene, { timeout: 30000 });
  await mkdir(outputDirectory, { recursive: true });
  try {
    await page.cdp('Page.bringToFront');
    const userAgent = await page.evaluate(() => navigator.userAgent);
    await page.cdp('Emulation.setUserAgentOverride', { userAgent, acceptLanguage: 'en-US,en' });
    await page.cdp('Emulation.setTouchEmulationEnabled', { enabled: false });
    await page.cdp('Emulation.setEmulatedMedia', { features: [{ name: 'prefers-reduced-motion', value: 'no-preference' }] });
    await page.goto(baseURL);
    await page.cdp('Emulation.setDeviceMetricsOverride', { width: 1440, height: 1100, deviceScaleFactor: 1, mobile: false });
    await page.waitForSelector('#demo[data-scene="team"]');
    await page.snapshot();
    check('hero lists all six supported runtimes', await page.evaluate(() => ['Claude Code', 'Codex', 'Pi', 'OpenCode', 'Hermes', 'OpenClaw'].every(name => document.querySelector('.runtime-list').textContent.includes(name))));
    check('hero has no supplementary pitch or tiny link group', await page.evaluate(() => !document.querySelector('.hero-aside') && !document.querySelector('.hero-links')));
    await page.waitForFunction(() => Number(document.querySelector('#demo').dataset.elapsed) > 500, undefined, { timeout: 10000 });
    check('normal motion starts the real story clock', (await read()).playing === 'true');
    await waitScene('direct');
    check('the real clock automatically changes scene and URL', (await read()).hash === '#demo/direct');
    await page.click('#play-button', { label: 'pause the story' });
    check('pause freezes the rendered clock', await page.evaluate(async () => {
      const node = document.querySelector('#demo');
      const elapsed = node.dataset.elapsed;
      for (let i = 0; i < 8; i++) await new Promise(resolve => requestAnimationFrame(resolve));
      return node.dataset.playing === 'false' && node.dataset.elapsed === elapsed;
    }));
    await page.click('#replay-button', { label: 'restart this chapter' });
    await page.waitForFunction(() => document.querySelector('#demo').dataset.playing === 'true');
    check('replay button restarts the chosen chapter', (await read()).scene === 'direct' && (await read()).elapsed < 2000);
    await page.press('#play-button', 'Enter');
    await page.waitForFunction(() => document.querySelector('#demo').dataset.playing === 'false');
    check('keyboard Enter pauses playback', (await read()).playing === 'false');
    await page.press('#play-button', 'Enter');
    await page.waitForFunction(() => document.querySelector('#demo').dataset.playing === 'true');
    check('keyboard Enter resumes playback', (await read()).playing === 'true');
    await page.press('#play-button', 'Enter');
    await page.waitForFunction(() => document.querySelector('#demo').dataset.playing === 'false');

    for (const scene of ['team', 'direct', 'progress', 'teams']) {
      await page.click(`#chapters a[data-scene="${scene}"]`, { label: 'select story chapter' });
      await waitScene(scene);
      const state = await read();
      check(`chapter ${scene} has readable paused content`, state.playing === 'false' && (await page.evaluate(() => document.querySelector('#lead-messages').textContent.length)) > 30);
      check(`chapter ${scene} paused messages are immediately visible`, await page.evaluate(() => [...document.querySelectorAll('.message')].every(node => Number(getComputedStyle(node).opacity) === 1)));
      if (scene === 'direct') check('Claude and Codex use their respective tool-call formats', await page.evaluate(() => document.querySelector('#api-messages').textContent.includes('xsm - xsm_send (MCP)') && document.querySelector('#ui-messages').textContent.includes('Called xsm.xsm_send') && document.querySelector('#ui-messages').textContent.includes('[xsm v1')));
    }
    await page.click('#chapters a[data-scene="progress"]', { label: 'read progress management' });
    await waitScene('progress');
    check('progress scene shows verified count and blocker', await page.evaluate(() => document.querySelector('#board-summary').textContent.includes('8 / 12') && document.querySelector('#qa-report').textContent.includes('duplicate')));
    check('terminal uses monospace output and real tool-call notation', await page.evaluate(() => getComputedStyle(document.querySelector('.message-text')).fontFamily.includes('Mono') && document.querySelector('#lead-messages').textContent.includes('xsm - xsm_board (MCP)') && document.querySelector('#lead-messages .tool-result:not([hidden])') !== null));
    check('board is shown as a terminal command and Markdown output', await page.evaluate(() => document.querySelector('.board-command').textContent === '$ xsm board show notifications' && document.querySelector('#board-title').textContent === '# notifications board'));
    check('the full transcript includes tool results', await page.evaluate(() => [...document.querySelectorAll('#transcript-content .transcript-result')].some(node => node.textContent.includes('set progress: notifications (node'))));
    await page.evaluate(() => window.scrollTo({ top: 0, behavior: 'instant' }));
    await page.screenshot({ path: `${outputDirectory}/desktop.png`, fullPage: true });
    await page.click('#scene-guide-link', { label: 'open matching documentation' });
    await page.waitForSelector('#guide-view:not([hidden])');
    let state = await read();
    check('scene links to its matching document without resuming', state.hash === '#guide/progress' && state.playing === 'false' && state.heading.includes('Fable'));
    check('document owns the same player', await page.evaluate(() => document.querySelector('#guide-slot > #demo') !== null));
    await page.snapshot();
    await page.screenshot({ path: `${outputDirectory}/guide.png`, fullPage: true });
    for (const [topic, scene] of [['start', 'team'], ['team', 'team'], ['messages', 'direct'], ['board', 'direct'], ['progress', 'progress'], ['teams', 'teams'], ['handover', 'progress'], ['runtimes', 'team']]) {
      await page.click(`#guide-navigation a[data-topic="${topic}"]`, { label: 'read documentation topic' });
      await page.waitForFunction(value => location.hash === `#guide/${value}`, topic);
      state = await read();
      check(`document ${topic} has content and the correct scene`, state.scene === scene && state.playing === 'false' && !state.overflow && await page.evaluate(() => document.querySelector('#guide-article').innerText.length > 200));
      check(`document ${topic} interface is entirely English`, await page.evaluate(() => { const copy = document.body.cloneNode(true); copy.querySelector('[data-language-control]')?.remove(); return !/\p{Script=Hangul}/u.test(copy.innerText || copy.textContent) && document.documentElement.lang === 'en'; }));
    }
    check('guide paragraphs and sections have generous spacing', await page.evaluate(() => Number.parseFloat(getComputedStyle(document.querySelector('.article-section')).marginTop) >= 40 && Number.parseFloat(getComputedStyle(document.querySelector('.article-section p')).marginBottom) >= 20));
    await page.evaluate(() => history.back());
    await page.waitForFunction(() => location.hash === '#guide/handover');
    check('browser back restores the document and scene', (await read()).scene === 'progress');
    await page.click('#expand-show', { label: 'return to the story' });
    await waitScene('progress');
    check('returning to the show preserves pause', (await read()).playing === 'false');

    await page.goto(`${baseURL}#demo/teams?focus=board`);
    await waitScene('teams');
    check('deep links restore scene and focus', (await read()).focus === 'board');
    await page.cdp('Emulation.setEmulatedMedia', { features: [{ name: 'prefers-reduced-motion', value: 'reduce' }] });
    await page.reload();
    await waitScene('teams');
    check('reduced motion starts stopped with all content', (await read()).playing === 'false' && await page.evaluate(() => document.querySelector('#lead-messages').textContent.includes('Agreed')));

    for (const width of [390, 320]) {
      await page.goto(`${baseURL}__viewport?width=${width}`);
      await waitScene('progress');
      await page.snapshot();
      state = await read();
      check(`mobile ${width}px has no horizontal overflow`, state.width === width && !state.overflow);
      await page.click('#focus-lead', { label: 'focus coordinator session' });
      await page.press('#focus-lead', 'ArrowRight');
      check(`mobile ${width}px keyboard selects workers`, (await read()).focus === 'workers' && await page.evaluate(() => document.querySelector('#responsive-frame').contentDocument.activeElement.id === 'focus-workers'));
      await page.press('#focus-workers', 'ArrowRight');
      check(`mobile ${width}px keyboard selects the board`, (await read()).focus === 'board');
      await page.press('#focus-board', 'Home');
      check(`mobile ${width}px Home selects the coordinator`, (await read()).focus === 'lead');
      await page.press('#focus-lead', 'End');
      check(`mobile ${width}px End selects the board`, (await read()).focus === 'board');
      await page.press('#focus-board', 'ArrowLeft');
      check(`mobile ${width}px left arrow selects workers`, (await read()).focus === 'workers');
      await page.press('#focus-workers', 'End');
      await page.evaluate(async () => {
        const frame = document.querySelector('#responsive-frame');
        await new Promise(resolve => {
          frame.addEventListener('load', resolve, { once: true });
          frame.contentWindow.location.reload();
        });
      });
      await waitScene('progress');
      check(`mobile ${width}px reload restores selected panel`, (await read()).focus === 'board');
      if (width === 390) {
        await page.evaluate(() => { const frame = document.querySelector('#responsive-frame'); frame.style.height = `${frame.contentDocument.documentElement.scrollHeight}px`; });
        await page.screenshot({ path: `${outputDirectory}/mobile.png`, fullPage: true });
      }
      await page.click('.mobile-menu', { label: 'open mobile navigation' });
      await page.waitForFunction(() => !document.querySelector('#responsive-frame').contentDocument.querySelector('#mobile-navigation').hidden);
      check(`mobile ${width}px menu opens`, await page.evaluate(() => !document.querySelector('#responsive-frame').contentDocument.querySelector('#mobile-navigation').hidden));
      await page.press('.mobile-menu', 'Escape');
      await page.waitForFunction(() => document.querySelector('#responsive-frame').contentDocument.querySelector('#mobile-navigation').hidden);
      check(`mobile ${width}px escape closes menu`, await page.evaluate(() => document.querySelector('#responsive-frame').contentDocument.querySelector('#mobile-navigation').hidden));
      await page.click('.main-nav a[data-nav="guide"]', { label: 'read guide on mobile' });
      await page.waitForSelector('#guide-view:not([hidden])');
      check(`mobile ${width}px guide fits viewport`, !(await read()).overflow);
    }

    // Check the Clipboard API boundary without changing the user's OS clipboard.
    await page.evaluate(() => {
      const scope = document.querySelector('#responsive-frame').contentWindow;
      scope.originalWriteText = scope.navigator.clipboard.writeText;
      scope.navigator.clipboard.writeText = async text => { scope.copiedPrompt = text; };
    });
    await page.click('[data-copy="start-0"]', { label: 'copy installation request' });
    await page.waitForFunction(() => { const scope = document.querySelector('#responsive-frame').contentWindow; return Boolean(scope.copiedPrompt) && !scope.document.querySelector('#toast').hidden; });
    check('copy sends the installation prompt and reports success', await page.evaluate(() => { const scope = document.querySelector('#responsive-frame').contentWindow; return scope.copiedPrompt.includes('github.com/ysys143/xsm') && !scope.document.querySelector('#toast').hidden; }));
    await page.evaluate(() => { document.querySelector('#responsive-frame').contentWindow.navigator.clipboard.writeText = async () => { throw new Error('Clipboard unavailable'); }; });
    await page.click('[data-copy="start-0"]', { label: 'check manual copy fallback' });
    await page.waitForFunction(() => document.querySelector('#responsive-frame').contentDocument.querySelector('#copy-dialog').open);
    check('clipboard denial opens a selected readable fallback', await page.evaluate(() => { const doc = document.querySelector('#responsive-frame').contentDocument; return doc.querySelector('#copy-dialog').open && doc.querySelector('#copy-fallback').selectionEnd === doc.querySelector('#copy-fallback').value.length; }));
    await page.press('#copy-fallback', 'Escape');
    await page.evaluate(() => { const scope = document.querySelector('#responsive-frame').contentWindow; scope.navigator.clipboard.writeText = scope.originalWriteText; delete scope.originalWriteText; delete scope.copiedPrompt; });
    for (const width of [900, 1440]) {
      await page.goto(`${baseURL}__viewport?width=${width}`);
      await waitScene('progress');
      state = await read();
      check(`terminal layout ${width}px fits its viewport`, state.width === width && !state.overflow);
      check(`terminal layout ${width}px does not overlap playback controls`, await page.evaluate(() => {
        const doc = document.querySelector('#responsive-frame').contentDocument;
        const workspace = doc.querySelector('.workspace').getBoundingClientRect();
        const bottom = Math.max(...[...doc.querySelectorAll('.workspace .terminal,.workspace .board-window')].map(node => node.getBoundingClientRect().bottom));
        return bottom <= workspace.bottom + 1 && doc.querySelector('.playback').getBoundingClientRect().top >= doc.querySelector('.demo-stage').getBoundingClientRect().bottom - 1;
      }));
    }
    await page.goto(`${baseURL}#guide/progress?section=progress-1`);
    await page.waitForSelector('#progress-1');
    await page.waitForFunction(() => document.activeElement.id === 'progress-1');
    check('document section links focus the matching heading', await page.evaluate(() => document.activeElement.id === 'progress-1'));
    await page.goto(`${baseURL}#guide/not-a-topic`);
    await waitScene('team');
    check('invalid routes recover to the first scene', (await read()).hash === '#demo/team');
    const resources = await page.evaluate(() => performance.getEntriesByType('resource').filter(entry => entry.responseStatus >= 400).map(entry => ({ url: entry.name, status: entry.responseStatus })));
    check('the final page has no failed asset requests', resources.length === 0);
    const result = { passed: checks.length, checks, clipboard: 'Clipboard API boundary checked; OS clipboard was not changed.', viewport: 'Desktop plus the real site in fixed 390px/320px same-origin frames; pointer and keyboard input, not a physical phone.', screenshots: ['desktop.png', 'guide.png', 'mobile.png'] };
    await writeFile(`${outputDirectory}/browser.json`, JSON.stringify(result, null, 2) + '\n');
    console.log(JSON.stringify(result));
    return result;
  } catch (error) {
    const failure = { passed: checks.length, checks, error: String(error), state: await read() };
    await writeFile(`${outputDirectory}/browser-failure.json`, JSON.stringify(failure, null, 2) + '\n');
    console.log(JSON.stringify(failure));
    throw error;
  }
}
