// Turns the raw takes into the final MP4: keeps the played stretches, squeezes the waits,
// frames the page in a browser window and adds the title and end cards.
import { execFileSync } from 'node:child_process';
import { mkdirSync, readFileSync, statSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import { chromium } from 'playwright';
import { DEMO_DIR, PORT, VIEWPORT, requireFile } from './lib.mjs';

const config = JSON.parse(readFileSync(join(DEMO_DIR, 'demo.config.json'), 'utf8'));
const OUT = join(DEMO_DIR, 'out');
const BUILD = join(OUT, 'render');
const WIDTH = 1440;
const HEIGHT = 900;
const CHROME_HEIGHT = HEIGHT - VIEWPORT.height;
const FPS = 30;
const TITLE_SECONDS = 2;
const END_SECONDS = 3;
/**
 * Concat-demuxer lines showing each captured frame for as long as the video plays it. In
 * squeezed stretches, a frame far smaller than the one before is the grid blanking while the
 * Groups reload; it is held over, as the speed-up would turn those blinks into a strobe.
 */
function concatLines(take) {
  const timelinePath = join(OUT, take, 'timeline.json');
  requireFile(timelinePath, `Record the \`${take}\` take first.`);
  const { frames, segments } = JSON.parse(readFileSync(timelinePath, 'utf8'));
  const shown = [];
  frames.forEach((frame, index) => {
    const path = join(OUT, take, 'frames', frame.file);
    const shownFrom = frame.t;
    const shownUntil = frames[index + 1]?.t ?? frame.t + 0.5;
    let duration = 0;
    let squeezed = false;
    for (const segment of segments) {
      const overlap = Math.min(shownUntil, segment.end) - Math.max(shownFrom, segment.start);
      if (overlap > 0) {
        const speed = segment.target ? (segment.end - segment.start) / segment.target : 1;
        duration += overlap / speed;
        squeezed ||= Boolean(segment.target);
      }
    }
    if (duration <= 0.0005) {
      return;
    }
    const size = statSync(path).size;
    const previous = shown.at(-1);
    if (squeezed && previous && size < previous.size / 2) {
      previous.duration += duration;
      return;
    }
    shown.push({ path, size, duration });
  });
  return shown.flatMap(({ path, duration }) => [
    `file '${path}'`,
    `duration ${duration.toFixed(4)}`,
  ]);
}

async function renderStills() {
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: WIDTH, height: HEIGHT } });
  const shoot = async (name, html) => {
    await page.setContent(`<style>${BASE_CSS}</style>${html}`);
    await page.screenshot({ path: join(BUILD, `${name}.png`), omitBackground: name === 'chrome' });
  };
  await shoot('chrome', CHROME_HTML);
  await shoot('title', card(config.title, config.subtitle));
  await shoot('end', card(config.endTitle, config.endSubtitle));
  await browser.close();
}

function card(title, subtitle) {
  return `<main class="card"><h1>${title}</h1>${subtitle ? `<p>${subtitle}</p>` : ''}</main>`;
}

const BASE_CSS = `
  * { box-sizing: border-box; margin: 0; }
  body { width: ${WIDTH}px; height: ${HEIGHT}px; background: transparent;
    font-family: -apple-system, BlinkMacSystemFont, "Helvetica Neue", sans-serif; }
  .card { width: 100%; height: 100%; display: flex; flex-direction: column; gap: 20px;
    align-items: center; justify-content: center; background: #111214; color: #f4f4f5;
    text-align: center; padding: 0 120px; }
  .card h1 { font-size: 64px; font-weight: 700; letter-spacing: -0.02em; }
  .card p { font-size: 30px; color: #a1a1aa; }
  .chrome { height: ${CHROME_HEIGHT}px; background: #dedfe3; border-bottom: 1px solid #c4c5ca;
    display: flex; align-items: center; gap: 28px; padding: 0 24px; }
  .lights { display: flex; gap: 9px; }
  .lights span { width: 13px; height: 13px; border-radius: 50%; }
  .url { flex: 1; max-width: 760px; margin: 0 auto; height: 38px; border-radius: 19px;
    background: #fff; display: flex; align-items: center; padding: 0 18px;
    font-size: 16px; color: #3f3f46; }
  .url b { color: #18181b; font-weight: 500; }
`;

const CHROME_HTML = `
  <div class="chrome">
    <div class="lights">
      <span style="background:#ff5f57"></span><span style="background:#febc2e"></span><span style="background:#28c840"></span>
    </div>
    <div class="url"><b>127.0.0.1</b>:${PORT}</div>
    <div style="width:63px"></div>
  </div>`;

function ffmpeg(args) {
  execFileSync('ffmpeg', ['-y', '-loglevel', 'error', ...args], { stdio: 'inherit' });
}

async function main() {
  mkdirSync(BUILD, { recursive: true });

  const lines = ['open', 'work'].flatMap((take) => concatLines(take));
  lines.push(lines.at(-2));
  writeFileSync(join(BUILD, 'body.txt'), lines.join('\n') + '\n');

  await renderStills();

  ffmpeg([
    '-f',
    'concat',
    '-safe',
    '0',
    '-i',
    join(BUILD, 'body.txt'),
    '-loop',
    '1',
    '-i',
    join(BUILD, 'chrome.png'),
    '-filter_complex',
    `[0:v]scale=${VIEWPORT.width}:${VIEWPORT.height}:flags=lanczos,fps=${FPS}[page];` +
      `[1:v][page]overlay=0:${CHROME_HEIGHT}:shortest=1,format=yuv420p[v]`,
    '-map',
    '[v]',
    '-c:v',
    'libx264',
    '-crf',
    '14',
    '-preset',
    'slow',
    join(BUILD, 'body.mp4'),
  ]);

  const output = config.output.replace(/^~/, process.env.HOME);
  ffmpeg([
    '-loop',
    '1',
    '-t',
    String(TITLE_SECONDS),
    '-i',
    join(BUILD, 'title.png'),
    '-i',
    join(BUILD, 'body.mp4'),
    '-loop',
    '1',
    '-t',
    String(END_SECONDS),
    '-i',
    join(BUILD, 'end.png'),
    '-filter_complex',
    `[0:v]fps=${FPS},format=yuv420p,setsar=1,fade=out:st=${TITLE_SECONDS - 0.3}:d=0.3[t];` +
      `[1:v]fps=${FPS},format=yuv420p,setsar=1[b];` +
      `[2:v]fps=${FPS},format=yuv420p,setsar=1,fade=in:st=0:d=0.3[e];` +
      '[t][b][e]concat=n=3:v=1:a=0[v]',
    '-map',
    '[v]',
    '-c:v',
    'libx264',
    '-crf',
    '18',
    '-preset',
    'slow',
    '-pix_fmt',
    'yuv420p',
    '-movflags',
    '+faststart',
    output,
  ]);
  const seconds = execFileSync(
    'ffprobe',
    ['-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', output],
    { encoding: 'utf8' },
  ).trim();
  console.log(`Wrote ${output} (${Number(seconds).toFixed(1)} s)`);
}

await main();
