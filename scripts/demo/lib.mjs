import { spawn, execFileSync } from 'node:child_process';
import { createHash } from 'node:crypto';
import { mkdirSync, readFileSync, rmSync, writeFileSync, existsSync, realpathSync } from 'node:fs';
import { homedir } from 'node:os';
import { basename, dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { chromium } from 'playwright';

export const DEMO_DIR = dirname(fileURLToPath(import.meta.url));
export const BACKEND_DIR = join(DEMO_DIR, '..', '..', 'backend');
export const PORT = 8765;
export const VIEWPORT = { width: 1440, height: 820 };

/**
 * The demo's config and the folder its takes go to. `--config <file>` records a separate demo
 * from another config, with its takes in out/<config name>.
 */
export function loadDemo() {
  const flag = process.argv.indexOf('--config');
  if (flag === -1) {
    return { config: readConfig('demo.config.json'), OUT: join(DEMO_DIR, 'out') };
  }
  const file = process.argv[flag + 1];
  const name = basename(file).replace(/(\.config)?\.json$/, '');
  return { config: readConfig(file), OUT: join(DEMO_DIR, 'out', name) };
}

function readConfig(file) {
  return JSON.parse(readFileSync(resolve(DEMO_DIR, file), 'utf8'));
}

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
export { sleep };

/** The Session store framewise keeps for a folder, as `session_database_path` names it. */
export function sessionStorePath(folder) {
  const root = realpathSync(folder);
  const digest = createHash('sha256').update(root).digest('hex').slice(0, 16);
  const dataDir =
    process.env.FRAMEWISE_DATA_DIR ??
    join(homedir(), 'Library', 'Application Support', 'framewise');
  return join(dataDir, `${root.split('/').pop()}-${digest}.sqlite`);
}

export function sqlite(database, sql) {
  return execFileSync('sqlite3', [database, sql], { encoding: 'utf8' }).trim();
}

/**
 * Starts `framewise review` without opening a browser of its own. With `folder`, the Session
 * opens straight away; with `pickedFolder`, the Review UI starts on the folder picker and
 * bin/osascript answers its folder dialog with that folder.
 */
export function startReview({ folder, pickedFolder } = {}) {
  const args = ['run', 'framewise', 'review', '--port', String(PORT)];
  if (folder) {
    args.push(folder);
  }
  const env = { ...process.env, BROWSER: 'true', PYTHONUNBUFFERED: '1' };
  if (pickedFolder) {
    env.PATH = `${join(DEMO_DIR, 'bin')}:${env.PATH}`;
    env.FRAMEWISE_DEMO_FOLDER = pickedFolder;
  }
  const child = spawn('uv', args, {
    cwd: BACKEND_DIR,
    env,
    stdio: ['ignore', 'pipe', 'pipe'],
  });
  const ready = new Promise((resolve, reject) => {
    const onData = (chunk) => {
      process.stdout.write(`[framewise] ${chunk}`);
      if (String(chunk).includes('Review UI at')) {
        resolve();
      }
    };
    child.stdout.on('data', onData);
    child.stderr.on('data', (chunk) => process.stderr.write(`[framewise] ${chunk}`));
    child.on('exit', (code) => reject(new Error(`framewise review exited with ${code}`)));
  });
  return {
    url: `http://127.0.0.1:${PORT}/`,
    ready,
    async stop() {
      if (child.exitCode !== null) {
        return;
      }
      const exited = new Promise((resolve) => child.once('exit', resolve));
      child.kill('SIGINT');
      const fallback = setTimeout(() => child.kill('SIGTERM'), 5000);
      await exited;
      clearTimeout(fallback);
    },
  };
}

export async function launchPage() {
  const browser = await chromium.launch();
  const context = await browser.newContext({ viewport: VIEWPORT, deviceScaleFactor: 2 });
  await context.addInitScript({ path: join(DEMO_DIR, 'overlay.js') });
  const page = await context.newPage();
  return { browser, page };
}

/**
 * Captures the page with the DevTools screencast, which keeps full quality, and notes which
 * stretches of time the final video plays: normally, squeezed to a target length, or not at all.
 */
export class Recorder {
  constructor(page, outDir) {
    this.page = page;
    this.outDir = outDir;
    this.framesDir = join(outDir, 'frames');
    this.frames = [];
    this.segments = [];
    this.open = null;
  }

  async start() {
    rmSync(this.outDir, { recursive: true, force: true });
    mkdirSync(this.framesDir, { recursive: true });
    this.cdp = await this.page.context().newCDPSession(this.page);
    this.cdp.on('Page.screencastFrame', async ({ data, metadata, sessionId }) => {
      const file = `${String(this.frames.length).padStart(6, '0')}.jpg`;
      writeFileSync(join(this.framesDir, file), Buffer.from(data, 'base64'));
      this.frames.push({ file, t: metadata.timestamp });
      await this.cdp.send('Page.screencastFrameAck', { sessionId }).catch(() => {});
    });
    await this.cdp.send('Page.startScreencast', { format: 'jpeg', quality: 92 });
  }

  /** Plays what follows at normal speed. */
  play() {
    this.#close();
    this.open = { start: Date.now() / 1000 };
  }

  /** Squeezes what follows, however long it takes, into `seconds` of video. */
  squeeze(seconds) {
    this.#close();
    this.open = { start: Date.now() / 1000, target: seconds };
  }

  /** Leaves what follows out of the video. */
  cut() {
    this.#close();
  }

  async stop() {
    this.#close();
    await sleep(300);
    await this.cdp.send('Page.stopScreencast');
    writeFileSync(
      join(this.outDir, 'timeline.json'),
      JSON.stringify({ frames: this.frames, segments: this.segments }, null, 2),
    );
  }

  #close() {
    if (this.open) {
      this.segments.push({ ...this.open, end: Date.now() / 1000 });
      this.open = null;
    }
  }
}

/** Moves a visible cursor like a person would and acts with real input events. */
export class Director {
  constructor(page) {
    this.page = page;
    this.x = VIEWPORT.width / 2;
    this.y = VIEWPORT.height / 2;
  }

  async caption(text, via) {
    await this.page.evaluate(([t, v]) => window.__demo.caption(t, v), [text ?? '', via ?? '']);
  }

  async moveTo(locator) {
    await locator.scrollIntoViewIfNeeded();
    const box = await locator.boundingBox();
    if (!box) {
      throw new Error(`not visible: ${locator}`);
    }
    const x = box.x + box.width / 2;
    const y = box.y + box.height / 2;
    const distance = Math.hypot(x - this.x, y - this.y);
    await this.page.mouse.move(x, y, { steps: Math.max(12, Math.round(distance / 18)) });
    this.x = x;
    this.y = y;
  }

  async click(locator) {
    await this.moveTo(locator);
    await sleep(250);
    await this.page.mouse.down();
    await sleep(60);
    await this.page.mouse.up();
  }

  async press(key, pauseMs = 700) {
    await this.page.keyboard.press(key);
    await sleep(pauseMs);
  }

  async hold(ms) {
    await sleep(ms);
  }
}

export function requireFile(path, hint) {
  if (!existsSync(path)) {
    throw new Error(`${path} is missing. ${hint}`);
  }
}
