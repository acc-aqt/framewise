// Records the demo video's raw takes. Usage:
//   node record.mjs open   picker → open the Session → analysis, then snapshots the store
//   node record.mjs work   merges → compare and Make Winner → Rating write-back
// `work` starts from the snapshot each time, so it can be retaken without analysing again;
// `work --rehearse` stops before writing any ratings.
import { copyFileSync, existsSync, readFileSync, rmSync } from 'node:fs';
import { join } from 'node:path';
import {
  DEMO_DIR,
  Director,
  Recorder,
  launchPage,
  requireFile,
  sessionStorePath,
  sleep,
  sqlite,
  startReview,
} from './lib.mjs';

const config = JSON.parse(readFileSync(join(DEMO_DIR, 'demo.config.json'), 'utf8'));
const OUT = join(DEMO_DIR, 'out');
const SNAPSHOT = join(OUT, 'analysed.sqlite');
const store = () => sessionStorePath(config.folder);
const REHEARSE = process.argv.includes('--rehearse');

const takes = { open: recordOpen, work: recordWork };
const take = takes[process.argv[2]];
if (!take) {
  console.error('usage: node record.mjs open|work');
  process.exit(1);
}
await take();

async function recordOpen() {
  if (existsSync(store())) {
    throw new Error(`${config.folder} is analysed already; run \`framewise reset\` on it first.`);
  }
  const review = startReview({ pickedFolder: config.folder });
  await review.ready;
  const { browser, page } = await launchPage();
  const rec = new Recorder(page, join(OUT, 'open'));
  const act = new Director(page);
  try {
    await page.goto(review.url);
    await page.getByTestId('choose-session').waitFor();
    await rec.start();
    rec.play();
    await act.hold(800);
    await act.caption('Open a shoot', '(click)');
    await act.click(page.getByTestId('choose-session'));
    rec.cut();
    await page.locator('header .root').waitFor({ timeout: 180_000 });
    await act.caption('Analysis runs locally, Groups fill in');
    rec.squeeze(config.analysisSeconds ?? 5);
    await waitForAnalysis(page);
    rec.play();
    await act.caption('');
    await act.hold(1500);
    await rec.stop();
  } finally {
    await browser.close();
    await review.stop();
  }
  sqlite(store(), `.backup '${SNAPSHOT}'`);
  console.log(`Analysed Session snapshot saved to ${SNAPSHOT}`);
}

async function recordWork() {
  requireFile(SNAPSHOT, 'Record the `open` take first.');
  restoreSnapshot();
  const review = startReview({ folder: config.folder });
  await review.ready;
  const { browser, page } = await launchPage();
  const rec = new Recorder(page, join(OUT, 'work'));
  const act = new Director(page);
  try {
    await page.goto(review.url);
    await page.getByTestId('group-tile').first().waitFor();
    await waitForAnalysis(page);
    await rec.start();
    rec.play();
    await act.hold(600);

    for (const [index, merge] of config.merges.entries()) {
      await act.caption(
        index === 0 ? 'Merge Groups that belong together' : 'Merge again',
        '(click)',
      );
      if (!(await openGroupShows(page, merge.open))) {
        if (await page.getByTestId('group-view').isVisible()) {
          await act.click(page.getByTestId('back-to-groups'));
          await act.hold(500);
        }
        await act.click(groupTile(page, merge.open));
        await page.getByTestId('group-view').waitFor();
        await act.hold(700);
      }
      const heading = page.locator('app-group-view .heading');
      const before = await heading.textContent();
      await act.click(
        page.getByTestId(merge.direction === 'previous' ? 'merge-previous' : 'merge-next'),
      );
      await page.waitForFunction(
        (text) => document.querySelector('app-group-view .heading')?.textContent !== text,
        before,
      );
      await act.hold(1300);
    }

    const loupeKey = async (key, holdMs) => {
      await page.keyboard.press(key);
      await sleep(150);
      rec.cut();
      await page.waitForFunction(() => {
        const images = [...document.querySelectorAll('[data-testid=loupe-image]')];
        return (
          images.length > 0 && images.every((image) => image.complete && image.naturalWidth > 0)
        );
      });
      rec.play();
      await act.hold(holdMs);
    };

    await act.caption('Compare with Winner', '[C]');
    await loupeKey('c', 1200);
    await page.getByTestId('loupe-side').nth(1).waitFor();
    await act.caption('Step through the Group', '[→]');
    for (let step = 0; step < 20 && (await currentFile(page)) !== config.winner; step++) {
      await loupeKey('ArrowRight', 800);
    }
    if ((await currentFile(page)) !== config.winner) {
      throw new Error(`${config.winner} is not in the open Group`);
    }
    await act.caption('Make Winner', '[W]');
    await act.press('w', 300);
    await page.waitForFunction(
      (file) =>
        document.querySelectorAll('[data-testid=loupe-side] .file')[1]?.textContent === file,
      config.winner,
    );
    await act.hold(1200);
    await act.caption('Step through the Group', '[← →]');
    await loupeKey('ArrowLeft', 900);
    await loupeKey('ArrowLeft', 900);
    await loupeKey('ArrowRight', 900);
    await act.caption('');
    await act.press('Escape', 300);
    await act.press('Escape', 500);

    await act.caption('Rating write-back', '(click)');
    await act.click(page.getByTestId('open-write-back'));
    rec.cut();
    await page.getByTestId('write-back-apply').waitFor({ timeout: 600_000 });
    await act.caption('Dry run: every file’s rating and label before → after');
    rec.play();
    await act.hold(2600);
    if (REHEARSE) {
      await rec.stop();
      console.log('Rehearsal: stopped before writing any ratings.');
      return;
    }
    await act.caption('Write ratings into the files', '(click)');
    await act.click(page.getByTestId('write-back-apply'));
    await act.hold(500);
    await act.click(page.getByTestId('write-back-confirm'));
    rec.cut();
    await page.getByTestId('write-back-result').waitFor({ timeout: 3_600_000 });
    await act.caption('Ready for Lightroom');
    rec.play();
    await act.hold(2500);
    await rec.stop();

    console.log('Undoing the demo write-back, DNGs can take minutes…');
    const undo = await page.evaluate(() =>
      fetch('/api/write-back/undo', { method: 'POST' }).then((response) => response.json()),
    );
    console.log(`Undo: ${JSON.stringify(undo).slice(0, 300)}`);
  } finally {
    await browser.close();
    await review.stop();
  }
}

function groupTile(page, file) {
  return page
    .getByTestId('group-tile')
    .filter({ has: page.locator('.file', { hasText: file }) })
    .first();
}

async function openGroupShows(page, file) {
  if (!(await page.getByTestId('group-view').isVisible())) {
    return false;
  }
  return (await page.locator('app-group-view .file', { hasText: file }).count()) > 0;
}

async function currentFile(page) {
  return page.locator('[data-testid=loupe-side] .file').first().textContent();
}

async function waitForAnalysis(page) {
  for (;;) {
    const progress = await page.evaluate(() => fetch('/api/progress').then((r) => r.json()));
    if (progress.frames_left === 0) {
      return;
    }
    await sleep(2000);
  }
}

/** Starts each `work` take from the analysed Session. Refuses while a write-back is in
 * place, so its record of the files' original ratings is never lost. */
function restoreSnapshot() {
  const database = store();
  if (Number(sqlite(database, 'SELECT count(*) FROM write_back_originals')) > 0) {
    throw new Error('A Rating write-back is in place; undo it before retaking.');
  }
  for (const suffix of ['-wal', '-shm']) {
    rmSync(database + suffix, { force: true });
  }
  copyFileSync(SNAPSHOT, database);
}
