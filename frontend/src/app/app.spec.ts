import { provideHttpClient, withInterceptors } from '@angular/common/http';
import {
  HttpTestingController,
  provideHttpClientTesting,
  TestRequest,
} from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { About, UpdateCheck } from './about-api';
import { App, POLL_INTERVAL_MS } from './app';
import { RECONNECT_INTERVAL_MS, watchServerConnection } from './server-connection';
import { TOOLTIP_DELAY_MS } from './tooltip';
import {
  AnalysisProgress,
  Face,
  Frame,
  Group,
  OverrideChange,
  Reason,
  SessionSummary,
} from './session-api';

const summary: SessionSummary = {
  root: '/Volumes/card/DCIM',
  total_frames: 4,
  jpg_only_count: 1,
  raw_jpg_count: 2,
  raw_only_count: 1,
  skipped: [{ path: '100LEICA/L1000009-Pano.dng', reason: 'The RAW holds no embedded preview' }],
  keeper_budget: 0.4,
  providers: {
    fingerprint: {
      active: { id: 'apple-vision-fingerprint', version: 2, source: 'automatic' },
      alternatives: [],
    },
    'face-detection': {
      active: { id: 'mediapipe-face-detection', version: 1, source: 'config' },
      alternatives: [
        { id: 'apple-vision-face-detection', version: 3, available: true },
        { id: 'cuda-face-detection', version: 1, available: false },
      ],
    },
    'eye-state': {
      active: null,
      alternatives: [{ id: 'mediapipe-eye-state', version: 1, available: false }],
    },
    'face-quality': {
      active: { id: 'apple-vision-face-quality', version: 1, source: 'automatic' },
      alternatives: [],
    },
    aesthetics: { active: null, alternatives: [] },
  },
  config_path: '/Users/me/Library/Application Support/framewise/config.toml',
};

const about: About = {
  version: '0.1.0',
  platform: 'Windows',
  changelog: [
    {
      version: null,
      date: null,
      sections: [{ heading: null, items: ['Faster grouping'] }],
    },
    {
      version: '0.1.0',
      date: '2026-11-20',
      sections: [
        { heading: null, items: ['**Rating write-back** for Lightroom Classic'] },
        { heading: 'Fixed', items: ['`framewise review` opens the browser'] },
      ],
    },
  ],
};

const noUpdate: UpdateCheck = { available: null };

const update: UpdateCheck = {
  available: {
    version: '0.3.0',
    command: 'uvx --python 3.13 --from framewise-cull[portable]@latest framewise review',
    releases: [
      {
        version: '0.3.0',
        date: '2026-12-10',
        sections: [{ heading: null, items: ['**Update notice** in the Review UI'] }],
      },
      { version: '0.2.0', date: '2026-12-01', sections: [] },
    ],
  },
};

describe('Review UI', () => {
  let fixture: ComponentFixture<App>;
  let http: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      imports: [App],
      providers: [
        provideHttpClient(withInterceptors([watchServerConnection])),
        provideHttpClientTesting(),
      ],
    });
    http = TestBed.inject(HttpTestingController);
    startApp();
  });

  function startApp(running: About = about, update: UpdateCheck = noUpdate): void {
    startAppAwaitingUpdate(running).flush(update);
  }

  /** Starts the Review UI and hands back its update check, still unanswered. */
  function startAppAwaitingUpdate(running: About = about): TestRequest {
    fixture = TestBed.createComponent(App);
    TestBed.tick();
    http.expectOne('/api/about').flush(running);
    return http.expectOne('/api/update');
  }

  afterEach(() => {
    http.verify();
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  const MAC = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 15_0) AppleWebKit/605.1.15';
  const WINDOWS = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36';

  function onPlatform(userAgent: string): void {
    vi.spyOn(navigator, 'userAgent', 'get').mockReturnValue(userAgent);
  }

  function text(selector: string, root?: HTMLElement): string {
    return (
      (root ?? (fixture.nativeElement as HTMLElement))
        .querySelector(selector)
        ?.textContent?.replace(/\s+/g, ' ')
        .trim() ?? ''
    );
  }

  function accessibleNames(selector: string): { label: string | null; title: string | null }[] {
    return all(selector).map((element) => ({
      label: element.getAttribute('aria-label'),
      title: element.getAttribute('title'),
    }));
  }

  async function hover(element: HTMLElement): Promise<void> {
    element.dispatchEvent(new MouseEvent('mouseenter'));
    await vi.advanceTimersByTimeAsync(TOOLTIP_DELAY_MS);
    await settle();
  }

  function visibleTooltip(): HTMLElement | null {
    return document.querySelector<HTMLElement>('[role="tooltip"]:not([hidden])');
  }

  function tooltipText(): string {
    return Array.from(visibleTooltip()?.children ?? [])
      .map((part) => part.textContent?.trim())
      .join(' ');
  }

  function paletteCommand(label: string): HTMLElement | undefined {
    return all('[data-testid="command"]').find(
      (row) => row.querySelector('.label')?.textContent?.trim() === label,
    );
  }

  async function runFromPalette(label: string): Promise<void> {
    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'k', metaKey: true }));
    await settle();
    paletteCommand(label)!.click();
    await settle();
  }

  function description(element: HTMLElement): string | undefined {
    return (
      document.getElementById(element.getAttribute('aria-describedby') ?? '')?.textContent ??
      undefined
    );
  }

  /** The text a sighted photographer reads, without text meant only for assistive technology. */
  function visibleText(element: HTMLElement): string {
    const copy = element.cloneNode(true) as HTMLElement;
    copy.querySelectorAll('.visually-hidden').forEach((hidden) => hidden.remove());
    return copy.textContent!.replace(/\s+/g, ' ').trim();
  }

  function all(selector: string, root?: HTMLElement): HTMLElement[] {
    return Array.from(
      (root ?? (fixture.nativeElement as HTMLElement)).querySelectorAll<HTMLElement>(selector),
    );
  }

  /** Lets the matching images finish loading, or fail to. */
  async function loadImages(selector: string, outcome: 'load' | 'error' = 'load'): Promise<void> {
    all(selector).forEach((image) => image.dispatchEvent(new Event(outcome)));
    await fixture.whenStable();
  }

  async function respond(session: SessionSummary, groups: Group[]): Promise<void> {
    http.expectOne('/api/session').flush(session);
    await respondToPoll(
      { frames_done: session.total_frames, frames_left: 0, seconds_remaining: 0 },
      groups,
    );
  }

  // Drives change detection with tick() rather than whenStable(), which never settles while
  // a request is open or under fake timers.
  async function respondToPoll(progress: AnalysisProgress, groups: Group[]): Promise<void> {
    http.expectOne('/api/progress').flush(progress);
    await settle();
    http.expectOne((request) => request.url.startsWith('/api/groups')).flush(groups);
    await settle();
  }

  async function settle(): Promise<void> {
    await Promise.resolve();
    TestBed.tick();
  }

  async function nextPoll(): Promise<void> {
    await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS);
    await settle();
  }

  function openFrameThumbnails(): (string | null | undefined)[] {
    return all('[data-testid="group-view"] [data-testid="frame-tile"]').map((tile) =>
      tile.querySelector('img')?.getAttribute('src'),
    );
  }

  function coverThumbnails(): (string | null | undefined)[] {
    return all('[data-testid="group-tile"]').map((tile) =>
      tile.querySelector('img')?.getAttribute('src'),
    );
  }

  async function choose(select: HTMLSelectElement, value: string): Promise<void> {
    select.value = value;
    select.dispatchEvent(new Event('change'));
    await fixture.whenStable();
  }

  function fileDetails(): HTMLDetailsElement {
    return all('header details[data-testid="file-details"]')[0] as HTMLDetailsElement;
  }

  async function openFileDetails(): Promise<HTMLDetailsElement> {
    const details = fileDetails();
    details.querySelector('summary')!.click();
    await settle();
    return details;
  }

  it('names the Frames disclosure File details for assistive technology', async () => {
    await respond(summary, []);

    expect(text('summary', fileDetails())).toBe('File details: 4 Frames');
  });

  it('shows the Frame count in the header, and opens it to the file kinds and Skipped files', async () => {
    await respond(summary, []);

    expect(visibleText(fileDetails().querySelector('summary')!)).toBe('4 Frames');
    expect(fileDetails().open).toBe(false);

    const details = await openFileDetails();

    expect(details.open).toBe(true);
    expect(text('[data-testid="raw-jpg-count"]', details)).toBe('2');
    expect(text('[data-testid="jpg-only-count"]', details)).toBe('1');
    expect(text('[data-testid="raw-only-count"]', details)).toBe('1');
    expect(text('[data-testid="skipped-count"]', details)).toBe('1');
    expect(text('[data-testid="skipped-files"]', details)).toBe(
      '100LEICA/L1000009-Pano.dng: The RAW holds no embedded preview',
    );
  });

  it('keeps the file kind counts out of the header row', async () => {
    await respond(summary, []);

    for (const id of ['raw-jpg-count', 'jpg-only-count', 'raw-only-count', 'skipped-count']) {
      const counts = all(`[data-testid="${id}"]`);
      expect(counts.length).toBe(1);
      expect(fileDetails().contains(counts[0])).toBe(true);
    }
  });

  it('opens the Frame count to the file kinds even when nothing was skipped', async () => {
    await respond({ ...summary, skipped: [] }, []);

    const details = await openFileDetails();

    expect(text('[data-testid="skipped-count"]', details)).toBe('0');
    expect(all('[data-testid="skipped-files"]')).toEqual([]);
  });

  it('shows the running version next to the name', async () => {
    await respond(summary, []);

    expect(text('header [data-testid="version"]')).toBe('0.1.0');
  });

  describe("What's new", () => {
    const versionButton = () => all('header [data-testid="version"]')[0];
    const panel = () => all('[data-testid="whats-new"]')[0];

    async function openWhatsNew(): Promise<void> {
      versionButton().click();
      await settle();
    }

    /** Reloads the Review UI, which must have answered its first requests already. */
    async function restartWith(running: About, available: UpdateCheck = noUpdate): Promise<void> {
      fixture.destroy();
      startApp(running, available);
      await respond(summary, []);
    }

    function shownVersions(): string[] {
      return all('[data-testid="changelog-version"]', panel()).map((entry) => text('h3', entry));
    }

    it('opens the Changelog from the version, newest first', async () => {
      await respond(summary, []);
      expect(panel()).toBeUndefined();

      await openWhatsNew();

      expect(versionButton().getAttribute('aria-expanded')).toBe('true');
      expect(shownVersions()).toEqual(['Unreleased', '0.1.0 2026-11-20']);
      const [unreleased, released] = all('[data-testid="changelog-version"]', panel());
      expect(all('li', unreleased).map((item) => item.textContent?.trim())).toEqual([
        'Faster grouping',
      ]);
      expect(all('h4', released).map((heading) => heading.textContent?.trim())).toEqual(['Fixed']);
      expect(text('li strong', released)).toBe('Rating write-back');
      expect(text('li code', released)).toBe('framewise review');
      expect(text('li', released)).toBe('Rating write-back for Lightroom Classic');
    });

    it('leaves out Unreleased when nothing is in it', async () => {
      await respond(summary, []);
      await restartWith({
        ...about,
        changelog: [{ version: null, date: null, sections: [] }, about.changelog[1]],
      });

      await openWhatsNew();

      expect(shownVersions()).toEqual(['0.1.0 2026-11-20']);
    });

    it('says so when a Release has nothing new on the platform', async () => {
      await respond(summary, []);
      await restartWith({
        ...about,
        version: '0.2.0',
        changelog: [{ version: '0.2.0', date: '2026-12-01', sections: [] }, about.changelog[1]],
      });

      await openWhatsNew();

      expect(shownVersions()).toEqual(['0.2.0 2026-12-01', '0.1.0 2026-11-20']);
      const [emptied, released] = all('[data-testid="changelog-version"]', panel());
      expect(text('[data-testid="nothing-new-on-platform"]', emptied)).toBe(
        'Nothing new on Windows in this release',
      );
      expect(all('ul', emptied)).toEqual([]);
      expect(all('[data-testid="nothing-new-on-platform"]', released)).toEqual([]);
    });

    it('says so when there are no release notes', async () => {
      await respond(summary, []);
      await restartWith({ ...about, changelog: [] });

      await openWhatsNew();

      expect(shownVersions()).toEqual([]);
      expect(text('[data-testid="no-release-notes"]', panel())).toBe('No release notes found.');
    });

    it('closes on Escape and gives focus back to the version', async () => {
      await respond(summary, []);
      await openWhatsNew();

      panel().dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
      await settle();

      expect(panel()).toBeUndefined();
      expect(document.activeElement).toBe(versionButton());
    });

    it('closes on a click outside it', async () => {
      await respond(summary, []);
      await openWhatsNew();

      document.body.click();
      await settle();

      expect(panel()).toBeUndefined();
    });

    it('opens from the command palette', async () => {
      await respond(summary, []);

      await runFromPalette("What's new");

      expect(shownVersions()).toEqual(['Unreleased', '0.1.0 2026-11-20']);
    });

    describe('when a newer Release is available', () => {
      const marker = () => all('header [data-testid="update-marker"]')[0];

      afterEach(() => localStorage.clear());

      it('marks the version only when an update is reported', async () => {
        await respond(summary, []);

        expect(marker()).toBeUndefined();

        await restartWith(about, update);

        expect(marker()).toBeDefined();
        expect(versionButton().getAttribute('aria-label')).toContain('update available');
      });

      const notice = () => all('[data-testid="update-notice"]', panel())[0];

      it("opens What's new with the available version, its command and the newer Releases", async () => {
        await respond(summary, []);
        await restartWith(about, update);

        await openWhatsNew();

        expect(text('h3', notice())).toBe('framewise 0.3.0 is available');
        expect(text('pre code', notice())).toBe(
          'uvx --python 3.13 --from framewise-cull[portable]@latest framewise review',
        );
        const releases = all('[data-testid="changelog-version"]', notice());
        expect(releases.map((release) => text('h3', release))).toEqual([
          '0.3.0 2026-12-10',
          '0.2.0 2026-12-01',
        ]);
        expect(text('li', releases[0])).toBe('Update notice in the Review UI');
        expect(text('li strong', releases[0])).toBe('Update notice');
        expect(text('[data-testid="nothing-new-on-platform"]', releases[1])).toBe(
          'Nothing new on Windows in this release',
        );
        expect(shownVersions()).toEqual([
          '0.3.0 2026-12-10',
          '0.2.0 2026-12-01',
          'Unreleased',
          '0.1.0 2026-11-20',
        ]);
      });

      it('copies the command', async () => {
        const writeText = vi.fn().mockResolvedValue(undefined);
        Object.defineProperty(navigator, 'clipboard', { value: { writeText }, configurable: true });
        await respond(summary, []);
        await restartWith(about, update);
        await openWhatsNew();

        all('[data-testid="copy-update-command"]', notice())[0].click();
        await settle();

        expect(writeText).toHaveBeenCalledWith(
          'uvx --python 3.13 --from framewise-cull[portable]@latest framewise review',
        );
        delete (navigator as { clipboard?: unknown }).clipboard;
      });

      it('stays dismissed across a restart until a newer version is reported', async () => {
        await respond(summary, []);
        await restartWith(about, update);
        await openWhatsNew();

        all('[data-testid="dismiss-update"]', notice())[0].click();
        await settle();

        expect(marker()).toBeUndefined();
        expect(localStorage.getItem('framewise.updateDismissedVersion')).toBe('0.3.0');
        expect(text('h3', notice())).toBe('framewise 0.3.0 is available');
        expect(all('[data-testid="dismiss-update"]', notice())).toEqual([]);

        await restartWith(about, update);

        expect(marker()).toBeUndefined();

        await restartWith(about, {
          available: { ...update.available!, version: '0.10.0' },
        });

        expect(marker()).toBeDefined();
      });

      it("adds nothing to What's new without an update", async () => {
        await respond(summary, []);

        await openWhatsNew();

        expect(notice()).toBeUndefined();
      });

      it('leaves the Review UI as it is when the check fails', async () => {
        await respond(summary, []);
        fixture.destroy();
        startAppAwaitingUpdate().flush('boom', { status: 500, statusText: 'Server Error' });
        await respond(summary, []);

        expect(marker()).toBeUndefined();
        expect(versionButton().getAttribute('aria-label')).toBe("framewise 0.1.0, What's new");
        expect(all('[data-testid="disconnected"]')).toEqual([]);

        await openWhatsNew();

        expect(notice()).toBeUndefined();
        expect(shownVersions()).toEqual(['Unreleased', '0.1.0 2026-11-20']);
      });

      it('lets the Review UI work while the check is slow, and marks the version once it answers', async () => {
        await respond(summary, []);
        fixture.destroy();
        const check = startAppAwaitingUpdate();
        await respond(summary, []);

        expect(text('header [data-testid="version"]')).toBe('0.1.0');
        expect(marker()).toBeUndefined();

        check.flush(update);
        await settle();

        expect(marker()).toBeDefined();
      });

      it('shows apart from the unseen-changes badge, and both can show at once', async () => {
        await respond(summary, []);
        localStorage.setItem('framewise.whatsNewSeenVersion', '0.0.9');
        await restartWith(about, update);

        const badge = all('header [data-testid="whats-new-badge"]')[0];
        expect(badge).toBeDefined();
        expect(marker()).toBeDefined();
        expect(marker()).not.toBe(badge);
        expect(marker().className).not.toBe(badge.className);
        expect(versionButton().getAttribute('aria-label')).toBe(
          "framewise 0.1.0, What's new, unseen changes, update available",
        );
      });
    });

    describe('after an upgrade', () => {
      const LAST_SEEN_KEY = 'framewise.whatsNewSeenVersion';
      const badge = () => all('header [data-testid="whats-new-badge"]')[0];

      afterEach(() => {
        vi.restoreAllMocks();
        localStorage.clear();
      });

      it("marks the version until What's new is opened", async () => {
        await respond(summary, []);
        localStorage.setItem(LAST_SEEN_KEY, '0.0.9');
        await restartWith(about);

        expect(badge()).toBeDefined();
        expect(versionButton().getAttribute('aria-label')).toContain('unseen changes');

        await openWhatsNew();

        expect(badge()).toBeUndefined();
        expect(localStorage.getItem(LAST_SEEN_KEY)).toBe('0.1.0');

        await restartWith(about);

        expect(badge()).toBeUndefined();
      });

      it('marks nothing on the first run, and remembers the version from then on', async () => {
        await respond(summary, []);

        expect(badge()).toBeUndefined();
        expect(localStorage.getItem(LAST_SEEN_KEY)).toBe('0.1.0');

        await restartWith({ ...about, version: '0.2.0' });

        expect(badge()).toBeDefined();
      });

      it("marks nothing and still opens What's new without browser storage", async () => {
        vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
          throw new DOMException('denied', 'SecurityError');
        });
        vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
          throw new DOMException('denied', 'SecurityError');
        });
        await respond(summary, []);
        await restartWith(about);

        expect(badge()).toBeUndefined();

        await openWhatsNew();

        expect(shownVersions()).toEqual(['Unreleased', '0.1.0 2026-11-20']);
      });
    });
  });

  describe('without a Session', () => {
    const notFound = { status: 404, statusText: 'Not Found' };

    async function respondWithoutSession(): Promise<void> {
      http.expectOne('/api/session').flush({ detail: 'No Session open' }, notFound);
      http.expectOne('/api/progress').flush({ detail: 'Not Found' }, notFound);
      await settle();
      http.expectOne('/api/groups').flush({ detail: 'Not Found' }, notFound);
      await settle();
    }

    function chooseButton(): HTMLButtonElement | null {
      return (fixture.nativeElement as HTMLElement).querySelector('[data-testid="choose-session"]');
    }

    async function choose(
      result: { opened: boolean } | string,
      failure?: { status: number; statusText: string },
    ): Promise<void> {
      chooseButton()!.click();
      await settle();
      const request = http.expectOne('/api/session/choose');
      expect(request.request.method).toBe('POST');
      request.flush(result, failure);
      await settle();
    }

    it('offers to choose a Session folder instead of the review screen', async () => {
      await respondWithoutSession();

      expect(chooseButton()).not.toBeNull();
      expect(all('[data-testid="open-write-back"]')).toEqual([]);
      expect(all('header .error')).toEqual([]);
    });

    it("shows the running version next to the name, and opens What's new from it", async () => {
      await respondWithoutSession();

      expect(text('header [data-testid="version"]')).toBe('0.1.0');

      all('header [data-testid="version"]')[0].click();
      await settle();

      expect(all('[data-testid="whats-new"] [data-testid="changelog-version"]').length).toBe(2);
    });

    it('tells about a newer Release before a Session is open', async () => {
      await respondWithoutSession();
      fixture.destroy();
      startApp(about, update);
      await respondWithoutSession();

      expect(all('header [data-testid="update-marker"]').length).toBe(1);

      all('header [data-testid="version"]')[0].click();
      await settle();

      expect(text('[data-testid="update-notice"] h3')).toBe('framewise 0.3.0 is available');
    });

    it('opens the chosen Session', async () => {
      await respondWithoutSession();

      await choose({ opened: true });
      await respond(summary, [group(1, [frame(1, 'jpg-only')])]);

      expect(chooseButton()).toBeNull();
      expect(text('.root')).toBe('/Volumes/card/DCIM');
      expect(all('[data-testid="group-tile"]').length).toBe(1);
    });

    it('opens no command palette before a Session is chosen', async () => {
      await respondWithoutSession();

      document.dispatchEvent(new KeyboardEvent('keydown', { key: 'k', metaKey: true }));
      await settle();
      await choose({ opened: true });
      await respond(summary, [group(1, [frame(1, 'jpg-only')])]);

      expect(all('[data-testid="command-palette"]')).toEqual([]);
    });

    it('keeps offering to choose a folder when the dialog is canceled', async () => {
      await respondWithoutSession();

      await choose({ opened: false });

      expect(chooseButton()?.disabled).toBe(false);
      expect(all('[data-testid="choose-session-error"]')).toEqual([]);
    });

    it('says so when the Session could not be opened', async () => {
      await respondWithoutSession();

      await choose('boom', { status: 500, statusText: 'Server Error' });

      expect(text('[data-testid="choose-session-error"]')).toBe('Could not open the Session.');
    });
  });

  describe('Analysis settings', () => {
    const gear = () => all('[data-testid="open-analysis-settings"]')[0];
    const popover = () => all('[data-testid="analysis-settings"]')[0];
    const rows = () =>
      all('[data-testid="capability"]').map((row) =>
        Array.from(row.children)
          .filter((part) => part.getAttribute('data-testid') !== 'alternatives')
          .map((part) => part.textContent?.replace(/\s+/g, ' ').trim())
          .join(' '),
      );

    async function openSettings(): Promise<void> {
      await respond(summary, []);
      gear().click();
      await settle();
    }

    it('shows the Provider in use per Capability, with its version and source', async () => {
      await openSettings();

      expect(gear().getAttribute('aria-label')).toBe('Analysis settings');
      expect(popover().getAttribute('role')).toBe('dialog');
      expect(rows()).toEqual([
        'Fingerprint (grouping) apple-vision-fingerprint v2 · picked automatically',
        'Face detection mediapipe-face-detection v1 · chosen in config.toml',
        'Eye state None · eyes count as unknown',
        'Face quality apple-vision-face-quality v1 · picked automatically',
        'Aesthetics None · aesthetics is left out of the score',
      ]);
    });

    it('lists the Capabilities in the order the Session API sends them', async () => {
      const { fingerprint, aesthetics } = summary.providers;
      await respond({ ...summary, providers: { aesthetics, fingerprint } }, []);
      gear().click();
      await settle();

      expect(rows()).toEqual([
        'Aesthetics None · aesthetics is left out of the score',
        'Fingerprint (grouping) apple-vision-fingerprint v2 · picked automatically',
      ]);
    });

    it('lists the alternatives per Capability, marking those that cannot run here', async () => {
      await openSettings();

      const alternatives = all('[data-testid="capability"]').map((row) =>
        Array.from(row.querySelectorAll('[data-testid="alternative"]')).map((alternative) => ({
          text: alternative.textContent?.replace(/\s+/g, ' ').trim(),
          unavailable: alternative.classList.contains('unavailable'),
        })),
      );
      expect(alternatives).toEqual([
        [],
        [
          { text: 'apple-vision-face-detection v3', unavailable: false },
          {
            text: 'cuda-face-detection v1 · not available on this machine',
            unavailable: true,
          },
        ],
        [{ text: 'mediapipe-eye-state v1 · not available on this machine', unavailable: true }],
        [],
        [],
      ]);
    });

    it("says which signals come from framewise's built-in image maths", async () => {
      await openSettings();

      expect(text('[data-testid="built-in-image-maths"]')).toBe(
        "Sharpness, motion blur, exposure and low and high key come from framewise's built-in image maths.",
      );
    });

    it('ends with where to switch a Provider and when the change applies', async () => {
      await openSettings();

      expect(text('[data-testid="config-path"]')).toBe(
        '/Users/me/Library/Application Support/framewise/config.toml',
      );
      expect(text('[data-testid="config-applies"]')).toBe(
        'A change applies on the next framewise review, which re-analyzes only the Frames it affects.',
      );
    });

    describe('example [providers] entry', () => {
      const example = () => all('[data-testid="config-example"]')[0].textContent;

      async function openSettingsWith(providers: SessionSummary['providers']): Promise<void> {
        await respond({ ...summary, providers }, []);
        gear().click();
        await settle();
      }

      it('switches to the first available alternative of a Capability', async () => {
        await openSettings();

        expect(example()).toBe('[providers]\nface-detection = "apple-vision-face-detection"');
      });

      it('prefers an available Fingerprint alternative', async () => {
        await openSettingsWith({
          ...summary.providers,
          fingerprint: {
            active: { id: 'apple-vision-fingerprint', version: 2, source: 'automatic' },
            alternatives: [
              { id: 'cuda-fingerprint', version: 1, available: false },
              { id: 'mediapipe-fingerprint', version: 1, available: true },
            ],
          },
        });

        expect(example()).toBe('[providers]\nfingerprint = "mediapipe-fingerprint"');
      });

      it('names the Fingerprint Provider in use when no alternative is available', async () => {
        await openSettingsWith({
          fingerprint: {
            active: { id: 'apple-vision-fingerprint', version: 2, source: 'automatic' },
            alternatives: [{ id: 'cuda-fingerprint', version: 1, available: false }],
          },
          'eye-state': { active: null, alternatives: [] },
        });

        expect(example()).toBe('[providers]\nfingerprint = "apple-vision-fingerprint"');
      });
    });

    it('closes only the popover on Escape and gives focus back to the gear', async () => {
      await respond(summary, [group(1, [frame(1, 'jpg-only')])]);
      all('[data-testid="group-tile"]')[0].click();
      await fixture.whenStable();
      gear().click();
      await settle();
      expect(popover().contains(document.activeElement)).toBe(true);

      document.activeElement!.dispatchEvent(
        new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }),
      );
      await settle();

      expect(popover()).toBeUndefined();
      expect(all('[data-testid="group-view"]').length).toBe(1);
      expect(document.activeElement).toBe(gear());
    });

    it('shows no tooltip on the gear when Escape gives focus back to it', async () => {
      await openSettings();
      vi.useFakeTimers();

      document.activeElement!.dispatchEvent(
        new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }),
      );
      await vi.advanceTimersByTimeAsync(TOOLTIP_DELAY_MS);

      expect(document.activeElement).toBe(gear());
      expect(visibleTooltip()).toBeNull();
    });

    it('closes on a click outside it, but not on a click inside it', async () => {
      await openSettings();

      popover().click();
      await settle();
      expect(popover()).toBeDefined();

      document.body.click();
      await settle();
      expect(popover()).toBeUndefined();
      expect(document.activeElement).toBe(gear());
    });

    it('is not offered on the session picker', async () => {
      const notFound = { status: 404, statusText: 'Not Found' };
      http.expectOne('/api/session').flush({ detail: 'No Session open' }, notFound);
      http.expectOne('/api/progress').flush({ detail: 'Not Found' }, notFound);
      await settle();
      http.expectOne('/api/groups').flush({ detail: 'Not Found' }, notFound);
      await settle();

      expect(all('[data-testid="choose-session"]').length).toBe(1);
      expect(gear()).toBeUndefined();
    });
  });

  describe('Keeper budget', () => {
    const judged = [
      group(1, [
        frame(1, 'jpg-only', { verdict: 'winner' }),
        frame(2, 'jpg-only', { verdict: 'keeper' }),
        frame(3, 'jpg-only', { verdict: 'reject' }),
      ]),
      group(4, [frame(4, 'jpg-only', { verdict: 'winner' }), frame(5, 'jpg-only')]),
    ];

    function slider(): HTMLInputElement {
      return fixture.nativeElement.querySelector('[data-testid="keeper-budget"]');
    }

    async function slideTo(percent: number): Promise<void> {
      slider().value = String(percent);
      slider().dispatchEvent(new Event('input'));
      slider().dispatchEvent(new Event('change'));
      await settle();
    }

    it("shows the Session's Keeper budget and the resulting number of Keepers", async () => {
      await respond(summary, judged);

      expect(slider().value).toBe('40');
      expect(text('[data-testid="keeper-budget-percent"]')).toBe('40%');
      expect(text('[data-testid="keeper-count"]')).toBe('2 Keepers · 4 of 5 Frames kept');
    });

    it('shows the slider at a Keeper budget of 0', async () => {
      await respond({ ...summary, keeper_budget: 0 }, judged);

      expect(slider().value).toBe('0');
      expect(text('[data-testid="keeper-budget-percent"]')).toBe('0%');
    });

    it('saves a new Keeper budget and shows the Keepers it results in', async () => {
      await respond(summary, judged);

      await slideTo(20);

      const request = http.expectOne('/api/session');
      expect(request.request.method).toBe('PATCH');
      expect(request.request.body).toEqual({ keeper_budget: 0.2 });
      request.flush({ ...summary, keeper_budget: 0.2 });
      await settle();
      http
        .expectOne((reload) => reload.url.startsWith('/api/groups'))
        .flush([
          group(1, [
            frame(1, 'jpg-only', { verdict: 'winner' }),
            frame(2, 'jpg-only', { verdict: 'reject' }),
            frame(3, 'jpg-only', { verdict: 'reject' }),
          ]),
          group(4, [
            frame(4, 'jpg-only', { verdict: 'winner' }),
            frame(5, 'jpg-only', { verdict: 'reject' }),
          ]),
        ]);
      await settle();

      expect(text('[data-testid="keeper-budget-percent"]')).toBe('20%');
      expect(text('[data-testid="keeper-count"]')).toBe('0 Keepers · 2 of 5 Frames kept');
    });

    it('explains the Keeper budget in its tooltip', async () => {
      await respond(summary, judged);
      vi.useFakeTimers();

      await hover(slider());

      const explanation =
        "Roughly the share of the Session's Frames to keep. Each Group's Winner is kept regardless.";
      expect(tooltipText()).toBe(`Keeper budget ${explanation}`);
      expect(description(slider())).toBe(explanation);
    });

    it('says so when the Keeper budget could not be saved', async () => {
      await respond(summary, judged);

      await slideTo(60);
      http.expectOne('/api/session').flush('boom', { status: 500, statusText: 'Server Error' });
      await settle();

      expect(text('[data-testid="keeper-budget-error"]')).toBe('Could not save the Keeper budget.');
    });
  });

  it('shows a tile per Group with its Frame count', async () => {
    await respond(summary, [
      group(1, [frame(1, 'raw+jpg'), frame(2, 'raw+jpg')]),
      group(3, [frame(3, 'jpg-only')]),
    ]);

    const tiles = all('[data-testid="group-tile"]');

    expect(tiles.map((tile) => tile.querySelector('img')?.getAttribute('src'))).toEqual([
      '/api/frames/1/thumbnail',
      '/api/frames/3/thumbnail',
    ]);
    expect(
      tiles.map((tile) => tile.querySelector('[data-testid="frame-count"]')?.textContent?.trim()),
    ).toEqual(['2 Frames', '1 Frame']);
  });

  it('covers each Group with its Winner, leaving off the Verdict every tile shares', async () => {
    await respond(summary, [
      group(1, [frame(1, 'jpg-only'), frame(2, 'jpg-only', { verdict: 'winner' })]),
    ]);

    const [tile] = all('[data-testid="group-tile"]');

    expect(tile.querySelector('img')?.getAttribute('src')).toBe('/api/frames/2/thumbnail');
    expect(tile.querySelector('[data-testid="verdict-badge"]')).toBeNull();
  });

  it("shows each Group's kept and out Frames on its tile's caption, except for a single Frame", async () => {
    await respond(summary, [
      group(1, [
        frame(1, 'raw+jpg', { verdict: 'winner' }),
        frame(2, 'raw+jpg', { verdict: 'keeper' }),
        frame(3, 'raw+jpg', { verdict: 'reject' }),
        frame(4, 'raw+jpg', { verdict: 'unsure' }),
        frame(5, 'raw+jpg', { verdict: 'reject' }),
      ]),
      group(6, [frame(6, 'raw+jpg', { verdict: 'winner' })]),
    ]);

    expect(
      all('[data-testid="group-tile"]').map((tile) => text('[data-testid="group-makeup"]', tile)),
    ).toEqual(['2 kept · 3 out', '']);
  });

  it('marks JPG-only and RAW-only Frames with their kind on the grid', async () => {
    await respond(summary, [
      group(1, [frame(1, 'raw+jpg', { verdict: 'winner' })]),
      group(2, [frame(2, 'jpg-only', { verdict: 'winner' })]),
      group(3, [frame(3, 'raw-only', { verdict: 'winner' })]),
    ]);

    expect(
      all('[data-testid="group-tile"]').map((tile) => text('[data-testid="kind-badge"]', tile)),
    ).toEqual(['', 'JPG-only', 'RAW-only']);
  });

  it("names each tile after its Frame's file, Verdict and Group size", async () => {
    await respond(summary, [
      group(1, [frame(1, 'jpg-only'), frame(2, 'jpg-only', { verdict: 'winner' })]),
      group(3, [frame(3, 'jpg-only', { verdict: 'unsure' })]),
    ]);

    expect(accessibleNames('[data-testid="group-tile"]').map(({ label }) => label)).toEqual([
      'DSCF0002.JPG, Winner, Group of 2',
      'DSCF0003.JPG, Unsure, Group of 1',
    ]);
  });

  it('shows the score breakdown when hovering a tile', async () => {
    await respond(summary, [
      group(1, [
        frame(1, 'jpg-only', {
          verdict: 'winner',
          scores: { ...SCORES, exposure: 1, aesthetics: null, total: 0.93 },
        }),
      ]),
    ]);

    const title = all('[data-testid="group-tile"] app-frame-tile')[0].getAttribute('title');

    expect(title).toContain('Total 0.93');
    expect(title).toContain('Sharpness 0.90');
    expect(title).toContain('Aesthetics unavailable');
  });

  it('names what the sharpness was measured on in the score breakdown', async () => {
    await respond(summary, [
      group(1, [frame(1, 'jpg-only', { sharpness_measured_on: 'focus-point' })]),
      group(2, [frame(2, 'jpg-only', { sharpness_measured_on: 'faces' })]),
      group(3, [frame(3, 'jpg-only', { sharpness_measured_on: 'frame' })]),
      group(4, [frame(4, 'jpg-only', { sharpness_measured_on: 'subject-mask' })]),
    ]);

    const titles = all('[data-testid="group-tile"] app-frame-tile').map((tile) =>
      tile.getAttribute('title'),
    );

    expect(titles[0]).toContain('Sharpness 0.90 (at focus point)');
    expect(titles[1]).toContain('Sharpness 0.90 (softest face)');
    expect(titles[2]).toContain('Sharpness 0.90\n');
    expect(titles[3]).toContain('Sharpness 0.90 (on subject)');
  });

  it("shows each Frame's Verdict, Reasons and score breakdown in an open Group", async () => {
    await respond(summary, [
      group(1, [
        frame(1, 'jpg-only', { verdict: 'winner' }),
        frame(2, 'jpg-only', {
          verdict: 'reject',
          reasons: [reason('underexposed', 'Underexposed', 'Underexposed 1.5 stops')],
          scores: { ...SCORES, exposure: 0, total: 0.6 },
          signals: {
            sharpness: 0.9,
            motion_blur: 0.05,
            exposure_stops: -1.5,
            low_key: false,
            high_key: false,
            aesthetics: 0,
          },
        }),
      ]),
    ]);
    all('[data-testid="group-tile"]')[0].click();
    await fixture.whenStable();

    const frames = all('[data-testid="group-view"] [data-testid="frame-details"]');
    expect(frames.map((details) => text('[data-testid="verdict-badge"]', details))).toEqual([
      'Winner',
      'Reject',
    ]);
    expect(all('[data-testid="reason"]', frames[0])).toEqual([]);
    expect(
      all('[data-testid="reason"]', frames[1]).map((item) => item.textContent?.trim()),
    ).toEqual(['Underexposed 1.5 stops']);
    const breakdown = text('[data-testid="score-breakdown"]', frames[1]);
    expect(breakdown).toContain('Exposure 0.00');
    expect(breakdown).toContain('-1.5 stops');
    expect(breakdown).toContain('Total 0.60');
  });

  it('filters the Frames by Verdict, counting each Verdict', async () => {
    await respond(summary, [
      group(1, [
        frame(1, 'jpg-only', { verdict: 'winner' }),
        frame(2, 'jpg-only', { verdict: 'reject' }),
        frame(3, 'jpg-only', { verdict: 'reject' }),
      ]),
      group(4, [frame(4, 'jpg-only', { verdict: 'winner' })]),
    ]);

    const select = all('[data-testid="verdict-filter"]')[0] as HTMLSelectElement;
    expect(Array.from(select.options).map((option) => option.textContent?.trim())).toEqual([
      'All Verdicts',
      'Winner (2)',
      'Keeper (0)',
      'Reject (2)',
      'Unsure (0)',
    ]);
    await choose(select, 'reject');

    expect(coverThumbnails()).toEqual(['/api/frames/2/thumbnail', '/api/frames/3/thumbnail']);
  });

  it("shows each filtered Frame's Verdict and the size of the Group it is in", async () => {
    await respond(summary, [
      group(1, [
        frame(1, 'jpg-only', { verdict: 'winner' }),
        frame(2, 'jpg-only', { verdict: 'reject' }),
        frame(3, 'jpg-only', { verdict: 'keeper' }),
      ]),
      group(4, [frame(4, 'jpg-only', { verdict: 'reject' })]),
    ]);
    await choose(all('[data-testid="verdict-filter"]')[0] as HTMLSelectElement, 'reject');

    const tiles = all('[data-testid="group-tile"]');
    expect(tiles.map((tile) => text('[data-testid="verdict-badge"]', tile))).toEqual([
      'Reject',
      'Reject',
    ]);
    expect(tiles.map((tile) => text('[data-testid="frame-count"]', tile))).toEqual([
      'in Group of 3',
      'in Group of 1',
    ]);
    expect(all('[data-testid="group-makeup"]')).toEqual([]);
  });

  it('filters the Frames by Reason', async () => {
    const blur = reason('motion-blur', 'Motion blur');
    await respond(summary, [
      group(1, [
        frame(1, 'jpg-only', { verdict: 'winner' }),
        frame(2, 'jpg-only', { verdict: 'reject', reasons: [blur] }),
        frame(3, 'jpg-only', {
          verdict: 'unsure',
          reasons: [reason('underexposed', 'Underexposed', 'Underexposed 1 stop')],
        }),
      ]),
      group(4, [frame(4, 'jpg-only', { verdict: 'winner', reasons: [blur] })]),
    ]);

    const select = all('[data-testid="reason-filter"]')[0] as HTMLSelectElement;
    expect(Array.from(select.options).map((option) => option.textContent?.trim())).toEqual([
      'All Reasons',
      'Motion blur (2)',
      'Underexposed (1)',
    ]);
    await choose(select, 'motion-blur');

    expect(coverThumbnails()).toEqual(['/api/frames/2/thumbnail', '/api/frames/4/thumbnail']);
  });

  describe('faceted filters', () => {
    const duplicate = reason('weaker-duplicate', 'Weaker duplicate');
    const sharpest = reason('sharpest', 'Sharpest');

    beforeEach(async () => {
      await respond(summary, [
        group(1, [
          frame(1, 'jpg-only', { verdict: 'winner', reasons: [sharpest] }),
          frame(2, 'jpg-only', { verdict: 'reject', reasons: [duplicate] }),
          frame(3, 'jpg-only', { verdict: 'unsure', reasons: [duplicate] }),
        ]),
        group(4, [frame(4, 'jpg-only', { verdict: 'winner', reasons: [sharpest] })]),
      ]);
    });

    function options(testId: string): { label: string; disabled: boolean }[] {
      const select = all(`[data-testid="${testId}"]`)[0] as HTMLSelectElement;
      return Array.from(select.options).map((option) => ({
        label: option.textContent?.trim() ?? '',
        disabled: option.disabled,
      }));
    }

    it('counts each Reason over the Frames with the chosen Verdict', async () => {
      await choose(all('[data-testid="verdict-filter"]')[0] as HTMLSelectElement, 'winner');

      expect(options('reason-filter')).toEqual([
        { label: 'All Reasons', disabled: false },
        { label: 'Sharpest (2)', disabled: false },
        { label: 'Weaker duplicate (0)', disabled: true },
      ]);
    });

    it('counts each Verdict over the Frames with the chosen Reason', async () => {
      await choose(
        all('[data-testid="reason-filter"]')[0] as HTMLSelectElement,
        'weaker-duplicate',
      );

      expect(options('verdict-filter')).toEqual([
        { label: 'All Verdicts', disabled: false },
        { label: 'Winner (0)', disabled: true },
        { label: 'Keeper (0)', disabled: true },
        { label: 'Reject (1)', disabled: false },
        { label: 'Unsure (1)', disabled: false },
      ]);
    });

    it('keeps the chosen options enabled when they count no Frames', async () => {
      await choose(all('[data-testid="verdict-filter"]')[0] as HTMLSelectElement, 'winner');
      await choose(
        all('[data-testid="reason-filter"]')[0] as HTMLSelectElement,
        'weaker-duplicate',
      );

      expect(options('verdict-filter')[1]).toEqual({ label: 'Winner (0)', disabled: false });
      expect(options('reason-filter')[2]).toEqual({
        label: 'Weaker duplicate (0)',
        disabled: false,
      });
    });

    it('says politely when no Frames match, and clears the filters', async () => {
      await choose(all('[data-testid="verdict-filter"]')[0] as HTMLSelectElement, 'winner');
      await choose(
        all('[data-testid="reason-filter"]')[0] as HTMLSelectElement,
        'weaker-duplicate',
      );

      const empty = all('[data-testid="no-matches"]')[0];
      expect(empty.getAttribute('aria-live')).toBe('polite');
      expect(text('[data-testid="no-matches-message"]', empty)).toBe(
        'No Frames match Winner + Weaker duplicate.',
      );
      expect(coverThumbnails()).toEqual([]);

      const clear = all('button', empty).find(
        (button) => button.textContent?.trim() === 'Clear filters',
      );
      clear!.click();
      await fixture.whenStable();

      expect(all('[data-testid="no-matches-message"]')).toEqual([]);
      expect(coverThumbnails()).toEqual(['/api/frames/1/thumbnail', '/api/frames/4/thumbnail']);
      expect((all('[data-testid="verdict-filter"]')[0] as HTMLSelectElement).value).toBe('');
      expect((all('[data-testid="reason-filter"]')[0] as HTMLSelectElement).value).toBe('');
    });
  });

  it('opens the whole Group of a filtered Frame', async () => {
    await respond(summary, [
      group(1, [
        frame(1, 'jpg-only', { verdict: 'winner' }),
        frame(2, 'jpg-only', { verdict: 'reject' }),
      ]),
    ]);
    await choose(all('[data-testid="verdict-filter"]')[0] as HTMLSelectElement, 'reject');

    all('[data-testid="group-tile"]')[0].click();
    await fixture.whenStable();

    expect(openFrameThumbnails()).toEqual(['/api/frames/1/thumbnail', '/api/frames/2/thumbnail']);
  });

  it('opens a Group to show its Frames with their Camera rating but no kind badge', async () => {
    await respond(summary, [
      group(1, [frame(1, 'jpg-only')]),
      group(2, [
        frame(2, 'raw+jpg', { camera_rating: { stars: 1, label: 'Rot' } }),
        frame(3, 'jpg-only'),
        frame(4, 'raw+jpg', { camera_rating: { stars: 0, label: null } }),
      ]),
    ]);

    all('[data-testid="group-tile"]')[1].click();
    await fixture.whenStable();

    const tiles = all('[data-testid="group-view"] [data-testid="frame-tile"]');
    expect(tiles.map((tile) => tile.querySelector('img')?.getAttribute('src'))).toEqual([
      '/api/frames/2/thumbnail',
      '/api/frames/3/thumbnail',
      '/api/frames/4/thumbnail',
    ]);
    expect(all('[data-testid="group-view"] [data-testid="kind-badge"]')).toEqual([]);
    expect(
      tiles.map(
        (tile) => tile.querySelector('[data-testid="camera-rating"]')?.textContent?.trim() ?? null,
      ),
    ).toEqual(['★ Rot', null, null]);
    expect(all('[data-testid="group-tile"]')).toEqual([]);
  });

  it('shows a badge on each face of a Frame in an open Group, placed on its face', async () => {
    await respond(summary, [
      group(1, [
        frame(1, 'jpg-only', {
          verdict: 'unsure',
          faces: [
            face(0.1, 'open', 'sharp'),
            face(0.6, 'closed', 'soft'),
            face(0.8, 'unknown', 'sharp'),
          ],
        }),
      ]),
    ]);
    all('[data-testid="group-tile"]')[0].click();
    await fixture.whenStable();
    await loadImages('[data-testid="group-view"] [data-testid="frame-tile"] img');

    const badges = all('[data-testid="group-view"] [data-testid="face-badge"]');
    expect(badges.map((badge) => badge.textContent?.replace(/\s+/g, ' ').trim())).toEqual([
      'Eyes open · Sharp',
      'Eyes closed · Soft',
      'Sharp',
    ]);
    expect(badges.map((badge) => badge.classList.contains('flagged'))).toEqual([
      false,
      true,
      false,
    ]);
    const { left, top, width, height } = badges[1].style;
    expect([left, top, width, height]).toEqual(['60%', '30%', '20%', '25%']);
  });

  it('fits the picture to the image once it loads, so face badges land on their faces', async () => {
    await respond(summary, [
      group(1, [frame(1, 'jpg-only', { verdict: 'winner', faces: [face(0.1, 'open', 'sharp')] })]),
    ]);
    all('[data-testid="group-tile"]')[0].click();
    await fixture.whenStable();
    const [image] = all('[data-testid="group-view"] [data-testid="frame-tile"] img');

    Object.defineProperty(image, 'naturalWidth', { value: 300 });
    Object.defineProperty(image, 'naturalHeight', { value: 200 });
    image.dispatchEvent(new Event('load'));
    await fixture.whenStable();

    expect(image.parentElement?.style.width).toBe('min(100cqw, 150cqh)');
  });

  it('shows no face badges on the grid of Groups', async () => {
    await respond(summary, [
      group(1, [frame(1, 'jpg-only', { verdict: 'winner', faces: [face(0.1, 'closed', 'soft')] })]),
    ]);

    expect(all('[data-testid="face-badge"]')).toEqual([]);
  });

  it('includes face quality in the score breakdown of a Frame with faces', async () => {
    await respond(summary, [
      group(1, [
        frame(1, 'jpg-only', {
          verdict: 'winner',
          scores: { ...SCORES, face_quality: 0.64 },
          faces: [face(0.1, 'open', 'sharp')],
        }),
        frame(2, 'jpg-only'),
      ]),
    ]);
    all('[data-testid="group-tile"]')[0].click();
    await fixture.whenStable();

    const frames = all('[data-testid="group-view"] [data-testid="frame-details"]');
    expect(text('[data-testid="score-breakdown"]', frames[0])).toContain('Face quality 0.64');
    expect(text('[data-testid="score-breakdown"]', frames[1])).not.toContain('Face quality');
  });

  it('includes the expression in the score breakdown where it is available', async () => {
    await respond(summary, [
      group(1, [
        frame(1, 'jpg-only', {
          verdict: 'winner',
          scores: { ...SCORES, expression: 0.72 },
          faces: [face(0.1, 'open', 'sharp')],
        }),
        frame(2, 'jpg-only'),
      ]),
    ]);
    all('[data-testid="group-tile"]')[0].click();
    await fixture.whenStable();

    const frames = all('[data-testid="group-view"] [data-testid="frame-details"]');
    expect(text('[data-testid="score-breakdown"]', frames[0])).toContain('Expression 0.72');
    expect(text('[data-testid="score-breakdown"]', frames[1])).not.toContain('Expression');
  });

  it('shows the hint a Camera rating gave in the score breakdown', async () => {
    await respond(summary, [
      group(1, [
        frame(1, 'jpg-only', {
          verdict: 'winner',
          camera_rating: { stars: 1, label: null },
          scores: { ...SCORES, camera_rating: 0.05 },
        }),
        frame(2, 'jpg-only'),
      ]),
    ]);
    all('[data-testid="group-tile"]')[0].click();
    await fixture.whenStable();

    const frames = all('[data-testid="group-view"] [data-testid="frame-details"]');
    expect(text('[data-testid="score-breakdown"]', frames[0])).toContain('Camera rating +0.05');
    expect(text('[data-testid="score-breakdown"]', frames[1])).not.toContain('Camera rating');
  });

  it('returns from an open Group to the grid of Groups', async () => {
    await respond(summary, [group(1, [frame(1, 'jpg-only')]), group(2, [frame(2, 'jpg-only')])]);
    all('[data-testid="group-tile"]')[0].click();
    await fixture.whenStable();

    all('[data-testid="back-to-groups"]')[0].click();
    await fixture.whenStable();

    expect(all('[data-testid="group-view"]')).toEqual([]);
    expect(all('[data-testid="group-tile"]').length).toBe(2);
  });

  it('fills the grid in as Frames are analyzed and stops polling once analysis finishes', async () => {
    vi.useFakeTimers();
    const frames = [frame(1, 'jpg-only'), frame(2, 'jpg-only'), frame(3, 'jpg-only')];
    http.expectOne('/api/session').flush(summary);

    await respondToPoll({ frames_done: 1, frames_left: 2, seconds_remaining: 90 }, [
      group(1, [frames[0]]),
    ]);
    expect(all('[data-testid="group-tile"]').length).toBe(1);

    await nextPoll();
    await respondToPoll({ frames_done: 2, frames_left: 1, seconds_remaining: 45 }, [
      group(1, [frames[0]]),
      group(2, [frames[1]]),
    ]);
    expect(all('[data-testid="group-tile"]').length).toBe(2);

    await nextPoll();
    await respondToPoll({ frames_done: 3, frames_left: 0, seconds_remaining: 0 }, [
      group(1, [frames[0]]),
      group(2, [frames[1]]),
      group(3, [frames[2]]),
    ]);
    expect(all('[data-testid="group-tile"]').length).toBe(3);

    await nextPoll();
    http.expectNone('/api/progress');
  });

  it('keeps showing the last Groups while the next ones are fetched during analysis', async () => {
    vi.useFakeTimers();
    http.expectOne('/api/session').flush(summary);
    await respondToPoll({ frames_done: 1, frames_left: 2, seconds_remaining: 90 }, [
      group(1, [frame(1, 'jpg-only')]),
      group(2, [frame(2, 'jpg-only')]),
    ]);

    await nextPoll();
    http
      .expectOne('/api/progress')
      .flush({ frames_done: 2, frames_left: 1, seconds_remaining: 45 });
    await settle();

    expect(all('[data-testid="group-tile"]').length).toBe(2);

    http
      .expectOne((request) => request.url.startsWith('/api/groups'))
      .flush([
        group(1, [frame(1, 'jpg-only')]),
        group(2, [frame(2, 'jpg-only')]),
        group(3, [frame(3, 'jpg-only')]),
      ]);
    await settle();
    expect(all('[data-testid="group-tile"]').length).toBe(3);
  });

  it('keeps an open Group and its Frame open while the next Groups are fetched', async () => {
    vi.useFakeTimers();
    http.expectOne('/api/session').flush(summary);
    await respondToPoll({ frames_done: 2, frames_left: 1, seconds_remaining: 45 }, [
      group(1, [frame(1, 'jpg-only'), frame(2, 'jpg-only')]),
    ]);
    all('[data-testid="group-tile"]')[0].click();
    await settle();

    await nextPoll();
    http.expectOne('/api/progress').flush({ frames_done: 3, frames_left: 0, seconds_remaining: 0 });
    await settle();

    expect(openFrameThumbnails()).toEqual(['/api/frames/1/thumbnail', '/api/frames/2/thumbnail']);

    http
      .expectOne((request) => request.url.startsWith('/api/groups'))
      .flush([group(1, [frame(1, 'jpg-only'), frame(2, 'jpg-only')])]);
    await settle();
  });

  it('keeps an open Group open when an update adds an earlier Frame that changes its id', async () => {
    vi.useFakeTimers();
    http.expectOne('/api/session').flush(summary);
    await respondToPoll({ frames_done: 1, frames_left: 2, seconds_remaining: 90 }, [
      group(2, [frame(2, 'jpg-only')]),
    ]);
    all('[data-testid="group-tile"]')[0].click();
    await settle();

    await nextPoll();
    await respondToPoll({ frames_done: 3, frames_left: 0, seconds_remaining: 0 }, [
      group(1, [frame(1, 'jpg-only'), frame(2, 'jpg-only'), frame(3, 'jpg-only')]),
    ]);

    expect(openFrameThumbnails()).toEqual([
      '/api/frames/1/thumbnail',
      '/api/frames/2/thumbnail',
      '/api/frames/3/thumbnail',
    ]);
  });

  it('keeps showing the Group with the opened Frame when its Frames are split across Groups', async () => {
    vi.useFakeTimers();
    http.expectOne('/api/session').flush(summary);
    await respondToPoll({ frames_done: 2, frames_left: 1, seconds_remaining: 45 }, [
      group(2, [frame(2, 'jpg-only'), frame(3, 'jpg-only')]),
    ]);
    all('[data-testid="group-tile"]')[0].click();
    await settle();

    await nextPoll();
    await respondToPoll({ frames_done: 3, frames_left: 0, seconds_remaining: 0 }, [
      group(1, [frame(1, 'jpg-only'), frame(2, 'jpg-only')]),
      group(3, [frame(3, 'jpg-only')]),
    ]);

    expect(openFrameThumbnails()).toEqual(['/api/frames/1/thumbnail', '/api/frames/2/thumbnail']);
  });

  it('shows Frames done, Frames left and the estimated time remaining while analysis runs', async () => {
    http.expectOne('/api/session').flush(summary);
    await respondToPoll({ frames_done: 12, frames_left: 188, seconds_remaining: 200 }, []);

    expect(text('[data-testid="frames-done"]')).toBe('12');
    expect(text('[data-testid="frames-left"]')).toBe('188');
    expect(text('[data-testid="time-remaining"]')).toBe('about 4 min left');
  });

  it('says the time remaining is being estimated before the first Frame finishes', async () => {
    http.expectOne('/api/session').flush(summary);
    await respondToPoll({ frames_done: 0, frames_left: 3, seconds_remaining: null }, []);

    expect(text('[data-testid="time-remaining"]')).toBe('estimating time left');
  });

  it('still shows the Groups when the analysis progress fails to load', async () => {
    http.expectOne('/api/session').flush(summary);
    http
      .expectOne('/api/progress')
      .flush('boom', { status: 500, statusText: 'Internal Server Error' });
    await settle();
    http
      .expectOne((request) => request.url.startsWith('/api/groups'))
      .flush([group(1, [frame(1, 'jpg-only')]), group(2, [frame(2, 'jpg-only')])]);
    await settle();

    expect(all('[data-testid="group-tile"]').length).toBe(2);
    expect(text('header .error')).toBe('Could not load the analysis progress.');
  });

  it('hides the progress once every Frame is analyzed', async () => {
    await respond(summary, []);

    expect(all('[data-testid="analysis-progress"]')).toEqual([]);
  });

  it('opens the write-back screen only once analysis has finished', async () => {
    vi.useFakeTimers();
    http.expectOne('/api/session').flush(summary);
    await respondToPoll({ frames_done: 1, frames_left: 2, seconds_remaining: 4 }, []);
    const button = () =>
      (fixture.nativeElement as HTMLElement).querySelector<HTMLButtonElement>(
        '[data-testid="open-write-back"]',
      )!;

    expect(button().disabled).toBe(true);

    await nextPoll();
    await respondToPoll({ frames_done: 3, frames_left: 0, seconds_remaining: 0 }, []);
    button().click();
    await settle();

    http.expectOne('/api/write-back');
    http.expectOne('/api/write-back/progress');
    expect(all('[data-testid="write-back"]').length).toBe(1);
    expect(all('[data-testid="group-tile"]')).toEqual([]);
  });

  it('opens the write-back screen from the command palette once analysis has finished', async () => {
    vi.useFakeTimers();
    http.expectOne('/api/session').flush(summary);
    await respondToPoll({ frames_done: 1, frames_left: 2, seconds_remaining: 4 }, []);
    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'k', metaKey: true }));
    await settle();
    expect(paletteCommand('Rating write-back')!.getAttribute('aria-disabled')).toBe('true');
    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'k', metaKey: true }));
    await settle();

    await nextPoll();
    await respondToPoll({ frames_done: 3, frames_left: 0, seconds_remaining: 0 }, []);
    await runFromPalette('Rating write-back');

    http.expectOne('/api/write-back');
    http.expectOne('/api/write-back/progress');
    expect(all('[data-testid="write-back"]').length).toBe(1);
    expect(all('[data-testid="command-palette"]')).toEqual([]);
  });

  it("hides the header's write-back button on the write-back screen until going back", async () => {
    await respond(summary, []);
    all('[data-testid="open-write-back"]')[0].click();
    await settle();
    http.expectOne('/api/write-back');
    http.expectOne('/api/write-back/progress');

    expect(all('[data-testid="open-write-back"]')).toEqual([]);

    all('[data-testid="back-from-write-back"]')[0].click();
    await settle();

    expect(all('[data-testid="open-write-back"]').length).toBe(1);
  });

  it('names how many files the write-back screen reads, one per JPG and two per RAW+JPG Frame, leaving out RAW-only Frames', async () => {
    await respond(summary, []);
    all('[data-testid="open-write-back"]')[0].click();
    await settle();
    http.expectOne('/api/write-back');
    http.expectOne('/api/write-back/progress');

    expect(text('[data-testid="write-back-loading"]')).toBe(
      'Reading the current rating of 5 files…',
    );
  });

  it('opens no command palette on the write-back screen', async () => {
    await respond(summary, []);
    all('[data-testid="open-write-back"]')[0].click();
    await settle();
    http.expectOne('/api/write-back');
    http.expectOne('/api/write-back/progress');

    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'k', metaKey: true }));
    await settle();

    expect(all('[data-testid="command-palette"]')).toEqual([]);
  });

  it('explains Rating write-back in the tooltip of its button', async () => {
    await respond(summary, []);
    vi.useFakeTimers();
    const button = all('[data-testid="open-write-back"]')[0];

    await hover(button);

    const explanation =
      "Previews the star ratings and color labels for your reviewed Verdicts, and writes them into the Frames' files only once you confirm.";
    expect(tooltipText()).toBe(`Rating write-back ${explanation}`);
    expect(description(button)).toBe(explanation);
  });

  it('names the Verdict and Reason filters in their tooltips', async () => {
    await respond(summary, [group(1, [frame(1, 'jpg-only', { verdict: 'winner' })])]);
    vi.useFakeTimers();

    await hover(all('[data-testid="verdict-filter"]')[0]);
    expect(tooltipText()).toBe('Filter by Verdict');
    all('[data-testid="verdict-filter"]')[0].dispatchEvent(new MouseEvent('mouseleave'));

    await hover(all('[data-testid="reason-filter"]')[0]);
    expect(tooltipText()).toBe('Filter by Reason');
  });

  it('virtualizes the grid so a large Session does not render every tile', async () => {
    const groups = Array.from({ length: 400 }, (_, index) =>
      group(index + 1, [frame(index + 1, 'jpg-only')]),
    );
    await respond({ ...summary, total_frames: 400 }, groups);

    const tiles = all('[data-testid="group-tile"]');
    expect(tiles.length).toBeGreaterThan(0);
    expect(tiles.length).toBeLessThan(400);
  });
  describe('keyboard review', () => {
    const groups = (): Group[] => [
      group(1, [
        frame(1, 'jpg-only', { verdict: 'winner' }),
        frame(2, 'jpg-only'),
        frame(3, 'jpg-only', { verdict: 'reject' }),
      ]),
      group(4, [frame(4, 'jpg-only', { verdict: 'winner' })]),
    ];

    async function openFirstGroup(reviewed: Group[] = groups()): Promise<void> {
      await respond(summary, reviewed);
      all('[data-testid="group-tile"]')[0].click();
      await fixture.whenStable();
    }

    async function press(key: string, options: KeyboardEventInit = {}): Promise<void> {
      document.dispatchEvent(new KeyboardEvent('keydown', { key, bubbles: true, ...options }));
      await settle();
    }

    function currentFrameThumbnail(): string | null | undefined {
      return all('[data-testid="frame-details"].current')[0]
        ?.querySelector('img')
        ?.getAttribute('src');
    }

    async function expectGroupsReloaded(reviewed: Group[] = groups()): Promise<void> {
      http.expectOne((request) => request.url.startsWith('/api/groups')).flush(reviewed);
      await settle();
    }

    it('starts on the Frame shown on the opened tile', async () => {
      await openFirstGroup();

      expect(currentFrameThumbnail()).toBe('/api/frames/1/thumbnail');
    });

    const overrideShortcuts: [string, OverrideChange][] = [
      ['1', { stars: 1 }],
      ['2', { stars: 2 }],
      ['3', { stars: 3 }],
      ['4', { stars: 4 }],
      ['5', { stars: 5 }],
      ['0', { stars: null }],
      ['6', { label: 'red' }],
      ['7', { label: 'yellow' }],
      ['8', { label: 'green' }],
      ['9', { label: 'blue' }],
      ['p', { verdict: 'keeper' }],
      ['P', { verdict: 'keeper' }],
      ['x', { verdict: 'reject' }],
    ];

    for (const [key, change] of overrideShortcuts) {
      it(`saves ${JSON.stringify(change)} as an Override when pressing ${key}`, async () => {
        await openFirstGroup();
        await press('ArrowRight');

        await press(key);

        const request = http.expectOne('/api/frames/2/override');
        expect(request.request.method).toBe('PATCH');
        expect(request.request.body).toEqual(change);
        request.flush({});
        await settle();
        await expectGroupsReloaded();
      });
    }

    it('keeps the Winner as the Winner when pressing P on it', async () => {
      await openFirstGroup();

      await press('p');

      expect(http.expectOne('/api/frames/1/override').request.body).toEqual({ verdict: 'winner' });
    });

    it('makes the current Frame the Winner when pressing W', async () => {
      await openFirstGroup();
      await press('ArrowRight');

      await press('w');

      expect(http.expectOne('/api/frames/2/override').request.body).toEqual({ verdict: 'winner' });
    });

    it('saves nothing when pressing W on the Winner', async () => {
      await openFirstGroup();

      await press('w');

      http.expectNone((request) => request.url.includes('/override'));
    });

    it('removes a color label when pressing its key again', async () => {
      await openFirstGroup([
        group(1, [
          frame(1, 'jpg-only', {
            verdict: 'winner',
            override: { verdict: null, stars: null, label: 'red' },
          }),
        ]),
      ]);

      await press('6');

      expect(http.expectOne('/api/frames/1/override').request.body).toEqual({ label: null });
    });

    it('clears the Override when pressing U', async () => {
      await openFirstGroup();

      await press('u');

      const request = http.expectOne('/api/frames/1/override');
      expect(request.request.method).toBe('DELETE');
      request.flush(null);
      await settle();
      await expectGroupsReloaded();
    });

    it('makes a different Frame the Winner', async () => {
      await openFirstGroup();

      all('[data-testid="make-winner"]')[0].click();
      await settle();

      const request = http.expectOne('/api/frames/2/override');
      expect(request.request.method).toBe('PATCH');
      expect(request.request.body).toEqual({ verdict: 'winner' });
    });

    it('says so when an Override could not be saved', async () => {
      await openFirstGroup();

      await press('x');
      http
        .expectOne('/api/frames/1/override')
        .flush('boom', { status: 500, statusText: 'Internal Server Error' });
      await settle();

      expect(text('[data-testid="override-error"]')).toBe('Could not save the Override.');
    });

    it('ignores shortcuts while no Group is open', async () => {
      await respond(summary, groups());

      await press('x');

      http.expectNone('/api/frames/1/override');
    });

    it('moves between Frames with the arrow keys, across Groups', async () => {
      await openFirstGroup();

      await press('ArrowRight');
      expect(currentFrameThumbnail()).toBe('/api/frames/2/thumbnail');
      await press('ArrowRight');
      await press('ArrowRight');
      expect(openFrameThumbnails()).toEqual(['/api/frames/4/thumbnail']);
      expect(currentFrameThumbnail()).toBe('/api/frames/4/thumbnail');
      await press('ArrowRight');
      expect(currentFrameThumbnail()).toBe('/api/frames/4/thumbnail');

      await press('ArrowLeft');
      expect(currentFrameThumbnail()).toBe('/api/frames/3/thumbnail');
    });

    it('steps through the Frames of the current Group with Option and the arrow keys', async () => {
      await openFirstGroup();

      await press('ArrowRight', { altKey: true });
      await press('ArrowRight', { altKey: true });
      expect(currentFrameThumbnail()).toBe('/api/frames/3/thumbnail');
      await press('ArrowRight', { altKey: true });
      expect(currentFrameThumbnail()).toBe('/api/frames/3/thumbnail');
      expect(openFrameThumbnails().length).toBe(3);

      await press('ArrowLeft', { altKey: true });
      expect(currentFrameThumbnail()).toBe('/api/frames/2/thumbnail');
    });

    it('selects a Frame by clicking it', async () => {
      await openFirstGroup();

      all('[data-testid="frame-details"]')[2].click();
      await settle();

      expect(currentFrameThumbnail()).toBe('/api/frames/3/thumbnail');
    });

    it('opens the current Frame in a loupe that zooms to 100%', async () => {
      await openFirstGroup();
      await press('ArrowRight');

      await press('e');
      const image = all('[data-testid="loupe-image"]')[0] as HTMLImageElement;
      expect(image.getAttribute('src')).toBe('/api/frames/2/image');
      expect(text('[data-testid="loupe-zoom"]')).toBe('Fit');

      await press('z');
      expect(text('[data-testid="loupe-zoom"]')).toBe('100%');
      await press('z');
      expect(text('[data-testid="loupe-zoom"]')).toBe('Fit');
    });

    it('shows a badge on each face in the loupe, at fit and at 100%', async () => {
      await openFirstGroup([
        group(1, [
          frame(1, 'jpg-only', {
            verdict: 'unsure',
            faces: [face(0.1, 'open', 'sharp'), face(0.6, 'closed', 'sharp')],
          }),
        ]),
      ]);

      await press('e');
      await loadImages('[data-testid="loupe-image"]');
      const badges = () =>
        all('[data-testid="loupe"] [data-testid="face-badge"]').map((badge) =>
          badge.textContent?.replace(/\s+/g, ' ').trim(),
        );
      expect(badges()).toEqual(['Eyes open · Sharp', 'Eyes closed · Sharp']);

      await press('z');
      expect(badges()).toEqual(['Eyes open · Sharp', 'Eyes closed · Sharp']);
    });

    it("shows the loupe's face badges only once the Frame's image has loaded", async () => {
      await openFirstGroup([
        group(1, [
          frame(1, 'jpg-only', { verdict: 'winner', faces: [face(0.1, 'open', 'sharp')] }),
        ]),
      ]);

      await press('e');
      expect(all('[data-testid="loupe"] [data-testid="face-badge"]')).toEqual([]);

      await loadImages('[data-testid="loupe-image"]');
      expect(all('[data-testid="loupe"] [data-testid="face-badge"]').length).toBe(1);
    });

    it("hides the previous Frame's face badges until the next Frame's image has loaded", async () => {
      await openFirstGroup([
        group(1, [
          frame(1, 'jpg-only', { verdict: 'winner', faces: [face(0.1, 'open', 'sharp')] }),
          frame(2, 'jpg-only', { faces: [face(0.6, 'closed', 'soft')] }),
        ]),
      ]);
      await press('e');
      await loadImages('[data-testid="loupe-image"]');

      await press('ArrowRight');
      expect(all('[data-testid="loupe"] [data-testid="face-badge"]')).toEqual([]);

      await loadImages('[data-testid="loupe-image"]');
      expect(text('[data-testid="loupe"] [data-testid="face-badge"]')).toBe('Eyes closed · Soft');
    });

    it("shows no face badges when the Frame's image fails to load", async () => {
      await openFirstGroup([
        group(1, [
          frame(1, 'jpg-only', { verdict: 'winner', faces: [face(0.1, 'open', 'sharp')] }),
        ]),
      ]);
      await press('e');

      await loadImages('[data-testid="loupe-image"]', 'error');
      http.expectOne('/api/about').flush(about);
      await settle();

      expect(all('[data-testid="loupe"] [data-testid="face-badge"]')).toEqual([]);
    });

    it('moves the loupe between Frames with the arrow keys', async () => {
      await openFirstGroup();
      await press('e');

      await press('ArrowRight');

      expect(all('[data-testid="loupe-image"]')[0].getAttribute('src')).toBe('/api/frames/2/image');
    });

    it("shows the Frame's position in its Group in the loupe caption", async () => {
      await openFirstGroup();
      await press('e');
      expect(text('[data-testid="loupe-position"]')).toBe('1 / 3');

      await press('ArrowRight');
      expect(text('[data-testid="loupe-position"]')).toBe('2 / 3');
    });

    it('closes the loupe with Escape, then the Group', async () => {
      await openFirstGroup();
      await press('e');

      await press('Escape');
      expect(all('[data-testid="loupe-image"]')).toEqual([]);
      expect(all('[data-testid="group-view"]').length).toBe(1);

      await press('Escape');
      expect(all('[data-testid="group-view"]')).toEqual([]);
    });

    it('names the icon-only loupe close button, which closes the loupe', async () => {
      await openFirstGroup();
      await press('e');

      expect(accessibleNames('[data-testid="loupe-close"]')).toEqual([
        { label: 'Close', title: null },
      ]);
      all('[data-testid="loupe-close"]')[0].click();
      await settle();

      expect(all('[data-testid="loupe-image"]')).toEqual([]);
    });

    it('shows the key of the loupe buttons in their tooltips', async () => {
      await openFirstGroup();
      await press('e');
      vi.useFakeTimers();

      await hover(all('[data-testid="loupe-zoom"]')[0]);
      expect(tooltipText()).toBe('Zoom Fit/100% Z');
      expect(visibleTooltip()?.querySelector('.key')?.textContent).toBe('Z');
      all('[data-testid="loupe-zoom"]')[0].dispatchEvent(new MouseEvent('mouseleave'));

      await hover(all('[data-testid="loupe-close"]')[0]);
      expect(tooltipText()).toBe('Close Esc');
    });

    it('shows a tooltip only after a short delay, and hides it on leaving', async () => {
      await openFirstGroup();
      await press('e');
      vi.useFakeTimers();
      const zoom = all('[data-testid="loupe-zoom"]')[0];

      zoom.dispatchEvent(new MouseEvent('mouseenter'));
      await vi.advanceTimersByTimeAsync(TOOLTIP_DELAY_MS - 50);
      expect(visibleTooltip()).toBeNull();
      await vi.advanceTimersByTimeAsync(50);
      expect(tooltipText()).toBe('Zoom Fit/100% Z');

      zoom.dispatchEvent(new MouseEvent('mouseleave'));
      expect(visibleTooltip()).toBeNull();
    });

    it('shows a tooltip when tabbing to a button', async () => {
      await openFirstGroup();
      vi.useFakeTimers();

      document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Tab', bubbles: true }));
      all('[data-testid="back-to-groups"]')[0].focus();
      await vi.advanceTimersByTimeAsync(TOOLTIP_DELAY_MS);

      expect(tooltipText()).toBe('All Groups Esc');
    });

    it('shows a tooltip when Shift+Tab or an arrow key moves focus to a button', async () => {
      await openFirstGroup();
      vi.useFakeTimers();
      const back = all('[data-testid="back-to-groups"]')[0];

      for (const init of [{ key: 'Tab', shiftKey: true }, { key: 'ArrowLeft' }]) {
        back.blur();
        document.dispatchEvent(new KeyboardEvent('keydown', { ...init, bubbles: true }));
        back.focus();
        await vi.advanceTimersByTimeAsync(TOOLTIP_DELAY_MS);

        expect(tooltipText()).toBe('All Groups Esc');
      }
    });

    it('shows no tooltip when a click or the Review UI moves focus to a button', async () => {
      await openFirstGroup();
      vi.useFakeTimers();
      const back = all('[data-testid="back-to-groups"]')[0];

      back.focus();
      await vi.advanceTimersByTimeAsync(TOOLTIP_DELAY_MS);
      expect(visibleTooltip()).toBeNull();

      back.blur();
      document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Tab', bubbles: true }));
      document.dispatchEvent(new PointerEvent('pointerdown', { bubbles: true }));
      back.focus();
      await vi.advanceTimersByTimeAsync(TOOLTIP_DELAY_MS);
      expect(visibleTooltip()).toBeNull();
    });

    it('shows no tooltip when the Review UI moves focus some time after a Tab', async () => {
      await openFirstGroup();
      vi.useFakeTimers();
      const back = all('[data-testid="back-to-groups"]')[0];

      document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Tab', bubbles: true }));
      await vi.advanceTimersByTimeAsync(TOOLTIP_DELAY_MS);
      back.focus();
      await vi.advanceTimersByTimeAsync(TOOLTIP_DELAY_MS);

      expect(visibleTooltip()).toBeNull();
    });

    it('opens the next Group without the loupe after leaving one with the loupe open', async () => {
      await openFirstGroup();
      await press('e');
      all('[data-testid="back-to-groups"]')[0].click();
      await fixture.whenStable();

      all('[data-testid="group-tile"]')[1].click();
      await fixture.whenStable();

      expect(all('[data-testid="loupe-image"]')).toEqual([]);
    });

    describe('command palette', () => {
      const palette = () => all('[data-testid="command-palette"]')[0];
      const search = () => palette().querySelector<HTMLInputElement>('input')!;
      const rows = () =>
        all('[data-testid="command"]').map((row) =>
          Array.from(row.children)
            .map((part) => part.textContent?.trim())
            .join(' '),
        );

      async function openPalette(): Promise<void> {
        await press('k', { metaKey: true });
      }

      async function type(query: string): Promise<void> {
        search().value = query;
        search().dispatchEvent(new Event('input'));
        await settle();
      }

      async function pressInSearch(key: string): Promise<void> {
        search().dispatchEvent(new KeyboardEvent('keydown', { key, bubbles: true }));
        await settle();
      }

      it('opens with Command-K and lists every command with its key', async () => {
        onPlatform(MAC);
        await openFirstGroup();

        await openPalette();

        expect(palette()).toBeDefined();
        expect(rows()).toContain('Mark as Keeper P');
        expect(rows()).toContain('Next Frame in Group ⌥→');
        expect(rows()).toContain('Close Esc');
        expect(rows()).toContain('Make Winner W');
        expect(rows()).toContain('Trash Frame ⌫');
        expect(rows()).toContain('Trash Group');
        expect(rows()).toContain('Trash selected Groups');
        expect(rows()).toContain("What's new");
        expect(rows().length).toBe(33);
      });

      it('names keys the Windows way outside macOS', async () => {
        onPlatform(WINDOWS);
        await openFirstGroup();

        await press('k', { ctrlKey: true });

        expect(rows()).toContain('Next Frame in Group Alt+→');
        expect(rows()).toContain('Trash Frame Delete');
      });

      it('opens from the header button', async () => {
        await respond(summary, groups());

        all('[data-testid="open-command-palette"]')[0].click();
        await settle();

        expect(palette()).toBeDefined();
      });

      it('filters the commands by name as the photographer types', async () => {
        await openFirstGroup();
        await openPalette();

        await type('WINNER');

        expect(rows()).toEqual(['Compare with Winner C', 'Make Winner W']);
      });

      it('runs the highlighted command on Enter, as its key would, and closes', async () => {
        await openFirstGroup();
        await press('ArrowRight');
        await openPalette();

        await type('keeper');
        await pressInSearch('Enter');

        const request = http.expectOne('/api/frames/2/override');
        expect(request.request.body).toEqual({ verdict: 'keeper' });
        expect(all('[data-testid="command-palette"]')).toEqual([]);
        request.flush({});
        await settle();
        await expectGroupsReloaded();
      });

      it('moves the highlight with the arrow keys', async () => {
        await openFirstGroup();
        await openPalette();

        await type('star');
        await pressInSearch('ArrowDown');
        await pressInSearch('ArrowDown');
        await pressInSearch('ArrowUp');
        await pressInSearch('Enter');

        expect(http.expectOne('/api/frames/1/override').request.body).toEqual({ stars: 2 });
      });

      it('runs a command when it is clicked', async () => {
        await openFirstGroup();
        await openPalette();

        all('[data-testid="command"]')
          .find((row) => row.textContent?.includes('Open loupe'))!
          .click();
        await settle();

        expect(all('[data-testid="loupe"]').length).toBe(1);
        expect(all('[data-testid="command-palette"]')).toEqual([]);
      });

      it('grays out commands that do not apply, which then do nothing', async () => {
        await respond(summary, groups());
        await openPalette();

        const keeper = all('[data-testid="command"]').find((row) =>
          row.textContent?.includes('Mark as Keeper'),
        )!;
        expect(keeper.getAttribute('aria-disabled')).toBe('true');

        await type('keeper');
        await pressInSearch('Enter');
        keeper.click();
        await settle();

        http.expectNone((request) => request.url.includes('/override'));
        expect(palette()).toBeDefined();
      });

      it('closes only the palette on Escape, leaving the loupe open', async () => {
        await openFirstGroup();
        await press('e');
        await openPalette();

        await pressInSearch('Escape');

        expect(all('[data-testid="command-palette"]')).toEqual([]);
        expect(all('[data-testid="loupe"]').length).toBe(1);
      });

      it('keeps keyboard focus in the palette', async () => {
        await openFirstGroup();
        await openPalette();
        expect(document.activeElement).toBe(search());

        const tab = new KeyboardEvent('keydown', { key: 'Tab', bubbles: true, cancelable: true });
        search().dispatchEvent(tab);

        expect(tab.defaultPrevented).toBe(true);
      });

      it('runs no Review UI shortcut when focus has left the search', async () => {
        await openFirstGroup();
        await openPalette();
        search().blur();

        await press('x');

        http.expectNone((request) => request.url.includes('/override'));
        expect(palette()).toBeDefined();
      });

      it('gives focus back to where it was when the palette closes', async () => {
        await openFirstGroup();
        const back = all('[data-testid="back-to-groups"]')[0];
        back.focus();
        await openPalette();

        await pressInSearch('Escape');

        expect(document.activeElement).toBe(back);
      });

      it('highlights nothing and runs nothing when no command matches', async () => {
        await openFirstGroup();
        await openPalette();

        await type('no such command');
        await pressInSearch('ArrowDown');
        await pressInSearch('Enter');
        http.expectNone((request) => request.url.includes('/override'));

        await type('reject');
        await pressInSearch('Enter');

        expect(http.expectOne('/api/frames/1/override').request.body).toEqual({
          verdict: 'reject',
        });
      });

      it('runs no shortcut while the photographer types in the search', async () => {
        await openFirstGroup();
        await openPalette();

        await pressInSearch('p');
        await press('x');

        http.expectNone((request) => request.url.includes('/override'));
      });
    });

    describe('Compare loupe', () => {
      function compareSides(): { image: string | null | undefined; verdict: string }[] {
        return all('[data-testid="loupe-side"]').map((side) => ({
          image: side.querySelector('img')?.getAttribute('src'),
          verdict: text('[data-testid="loupe-verdict"]', side),
        }));
      }

      it('shows the current Frame beside the Winner, each with its Verdict and face badges', async () => {
        await openFirstGroup([
          group(1, [
            frame(1, 'jpg-only', { verdict: 'winner', faces: [face(0.1, 'open', 'sharp')] }),
            frame(2, 'jpg-only', { faces: [face(0.6, 'closed', 'soft')] }),
          ]),
        ]);
        await press('ArrowRight');

        await press('c');
        expect(all('[data-testid="loupe"] [data-testid="face-badge"]')).toEqual([]);
        await loadImages('[data-testid="loupe-image"]');

        expect(compareSides()).toEqual([
          { image: '/api/frames/2/image', verdict: 'Keeper' },
          { image: '/api/frames/1/image', verdict: 'Winner' },
        ]);
        expect(
          all('[data-testid="loupe-side"]').map((side) => text('[data-testid="face-badge"]', side)),
        ).toEqual(['Eyes closed · Soft', 'Eyes open · Sharp']);
      });

      it("shows the position on the current Frame's side", async () => {
        await openFirstGroup();
        await press('ArrowRight');

        await press('c');

        expect(
          all('[data-testid="loupe-side"]').map((side) =>
            text('[data-testid="loupe-position"]', side),
          ),
        ).toEqual(['2 / 3', '']);
      });

      it('zooms both sides together', async () => {
        await openFirstGroup();
        await press('c');

        await press('z');

        expect(text('[data-testid="loupe-zoom"]')).toBe('100%');
        expect(all('[data-testid="loupe-side"]').length).toBe(2);
        expect(all('[data-testid="loupe"] app-frame-picture.fit')).toEqual([]);
      });

      it('steps the current Frame within the Group while the Winner stays put', async () => {
        await openFirstGroup();
        await press('c');

        await press('ArrowRight', { altKey: true });
        expect(compareSides().map((side) => side.image)).toEqual([
          '/api/frames/2/image',
          '/api/frames/1/image',
        ]);

        await press('ArrowRight', { altKey: true });
        expect(compareSides().map((side) => side.image)).toEqual([
          '/api/frames/3/image',
          '/api/frames/1/image',
        ]);
      });

      it('keeps plain arrows within the Group while comparing', async () => {
        await openFirstGroup();
        await press('c');

        await press('ArrowRight');
        await press('ArrowRight');
        await press('ArrowRight');

        expect(compareSides().map((side) => side.image)).toEqual([
          '/api/frames/3/image',
          '/api/frames/1/image',
        ]);
      });

      it('lets plain arrows leave the Group again once closed', async () => {
        await openFirstGroup();
        await press('c');
        await press('Escape');

        await press('ArrowRight');
        await press('ArrowRight');
        await press('ArrowRight');

        expect(openFrameThumbnails()).toEqual(['/api/frames/4/thumbnail']);
      });

      it('rates the current Frame', async () => {
        await openFirstGroup();
        await press('c');
        await press('ArrowRight', { altKey: true });

        await press('x');

        const request = http.expectOne('/api/frames/2/override');
        expect(request.request.body).toEqual({ verdict: 'reject' });
        request.flush({});
        await settle();
        await expectGroupsReloaded();
      });

      it('shows the Winner on both sides when it is the current Frame', async () => {
        await openFirstGroup();

        await press('c');

        expect(compareSides()).toEqual([
          { image: '/api/frames/1/image', verdict: 'Winner' },
          { image: '/api/frames/1/image', verdict: 'Winner' },
        ]);
      });

      it('closes with Escape, back to the open Group', async () => {
        await openFirstGroup();
        await press('c');

        await press('Escape');

        expect(all('[data-testid="loupe"]')).toEqual([]);
        expect(all('[data-testid="group-view"]').length).toBe(1);
      });

      it('is listed in the shortcut legend', async () => {
        await openFirstGroup();

        expect(text('[data-testid="group-view"] .keys')).toContain('C compare');
      });
    });

    it("tells the photographer's Overrides apart from framewise's Verdicts", async () => {
      await openFirstGroup([
        group(1, [
          frame(1, 'jpg-only', { verdict: 'winner' }),
          frame(2, 'jpg-only', {
            verdict: 'reject',
            verdict_overridden: true,
            override: { verdict: 'reject', stars: 4, label: 'green' },
          }),
        ]),
      ]);

      const frames = all('[data-testid="frame-details"]');
      expect(all('[data-testid="override-mark"]', frames[0])).toEqual([]);
      expect(text('[data-testid="override-mark"]', frames[1])).toBe('Override');
      expect(text('[data-testid="override-rating"]', frames[1])).toBe('★★★★ Green');
    });
  });

  describe('pinned Winner', () => {
    const groups = (): Group[] => [
      group(1, [
        frame(1, 'jpg-only'),
        frame(2, 'jpg-only', {
          verdict: 'winner',
          reasons: [reason('sharpest', 'Sharpest', 'Sharpest of its Group')],
        }),
        frame(3, 'jpg-only', { verdict: 'reject' }),
      ]),
      group(4, [frame(4, 'jpg-only', { verdict: 'winner' })]),
    ];

    async function openGroup(index: number, reviewed: Group[] = groups()): Promise<void> {
      await respond(summary, reviewed);
      all('[data-testid="group-tile"]')[index].click();
      await fixture.whenStable();
    }

    afterEach(() => localStorage.clear());

    it('names the pinned Winner toggle in its tooltip', async () => {
      await openGroup(0);
      vi.useFakeTimers();

      await hover(all('[data-testid="toggle-pinned-winner"]')[0]);

      expect(tooltipText()).toBe('Hide Winner');
      expect(all('[data-testid="toggle-pinned-winner"]')[0].getAttribute('title')).toBeNull();
    });

    function pinnedWinner(): HTMLElement | undefined {
      return all('[data-testid="pinned-winner"]')[0];
    }

    function pinnedThumbnail(): string | null | undefined {
      return pinnedWinner()?.querySelector('img')?.getAttribute('src');
    }

    it("pins the Group's Winner beside its Frames, which still include the Winner", async () => {
      await openGroup(0);

      const pinned = pinnedWinner()!;
      expect(pinnedThumbnail()).toBe('/api/frames/2/thumbnail');
      expect(text('[data-testid="verdict-badge"]', pinned)).toBe('Winner');
      expect(text('[data-testid="reason"]', pinned)).toBe('Sharpest of its Group');
      expect(text('[data-testid="score-breakdown"]', pinned)).toContain('Total');
      expect(openFrameThumbnails()).toEqual([
        '/api/frames/1/thumbnail',
        '/api/frames/2/thumbnail',
        '/api/frames/3/thumbnail',
      ]);
    });

    it('pins no Winner in a Group of one Frame', async () => {
      await openGroup(1);

      expect(pinnedWinner()).toBeUndefined();
    });

    it('pins the new Winner once another Frame is made Winner', async () => {
      await openGroup(0);

      all('[data-testid="make-winner"]')[0].click();
      await settle();
      http.expectOne('/api/frames/1/override').flush({});
      await settle();
      const [first, second, third] = groups()[0].frames;
      http
        .expectOne((request) => request.url.startsWith('/api/groups'))
        .flush([
          group(1, [
            { ...first, verdict: 'winner', verdict_overridden: true },
            { ...second, verdict: 'keeper', reasons: [] },
            third,
          ]),
          groups()[1],
        ]);
      await settle();

      expect(pinnedThumbnail()).toBe('/api/frames/1/thumbnail');
    });

    it('collapses the pinned Winner and expands it again, remembering the choice', async () => {
      await openGroup(0);

      all('[data-testid="toggle-pinned-winner"]')[0].click();
      await settle();

      expect(pinnedThumbnail()).toBeUndefined();
      expect(all('[data-testid="toggle-pinned-winner"]')[0].getAttribute('aria-expanded')).toBe(
        'false',
      );

      fixture.destroy();
      startApp();
      await openGroup(0);

      expect(pinnedThumbnail()).toBeUndefined();

      all('[data-testid="toggle-pinned-winner"]')[0].click();
      await settle();

      expect(pinnedThumbnail()).toBe('/api/frames/2/thumbnail');
    });
  });

  describe('fixing Groups', () => {
    const groups = (): Group[] => [
      group(1, [frame(1, 'jpg-only', { verdict: 'winner' }), frame(2, 'jpg-only')]),
      group(3, [
        frame(3, 'jpg-only', { verdict: 'winner' }),
        frame(4, 'jpg-only'),
        frame(5, 'jpg-only'),
      ]),
      group(6, [frame(6, 'jpg-only', { verdict: 'winner' })]),
    ];

    async function openGroup(index: number): Promise<void> {
      await respond(summary, groups());
      all('[data-testid="group-tile"]')[index].click();
      await fixture.whenStable();
    }

    function frameDetails(index: number): HTMLElement {
      return all('[data-testid="frame-details"]')[index];
    }

    async function click(element: HTMLElement): Promise<void> {
      element.click();
      await settle();
    }

    async function expectFix(url: string, body: unknown): Promise<void> {
      const request = http.expectOne(url);
      expect(request.request.method).toBe('POST');
      expect(request.request.body).toEqual(body);
      request.flush(null);
      await settle();
      http.expectOne((request) => request.url.startsWith('/api/groups')).flush(groups());
      await settle();
    }

    it('splits a Group at a chosen Frame', async () => {
      await openGroup(1);

      expect(all('[data-testid="split-here"]', frameDetails(0))).toEqual([]);
      await click(all('[data-testid="split-here"]', frameDetails(1))[0]);

      await expectFix('/api/groups/split', { frame_ids: [4, 5] });
    });

    describe('from the command palette', () => {
      it('merges the open Group with the previous or next Group', async () => {
        await openGroup(1);

        await runFromPalette('Merge with previous');
        await expectFix('/api/groups/merge', { frame_ids: [3, 1] });

        await runFromPalette('Merge with next');
        await expectFix('/api/groups/merge', { frame_ids: [3, 6] });
      });

      it('splits the Group at the current Frame', async () => {
        await openGroup(1);
        await click(frameDetails(1));

        await runFromPalette('Split here');

        await expectFix('/api/groups/split', { frame_ids: [4, 5] });
      });

      it('moves the current Frame to the previous or next Group', async () => {
        await openGroup(1);
        await click(frameDetails(1));

        await runFromPalette('Move to previous Group');
        await expectFix('/api/frames/4/move', { to_frame_id: 1 });

        await runFromPalette('Move to next Group');
        await expectFix('/api/frames/4/move', { to_frame_id: 6 });
      });

      it('makes the current Frame the Winner', async () => {
        await openGroup(1);
        await click(frameDetails(2));

        await runFromPalette('Make Winner');

        const request = http.expectOne('/api/frames/5/override');
        expect(request.request.body).toEqual({ verdict: 'winner' });
      });

      it('returns to all Groups', async () => {
        await openGroup(1);

        await runFromPalette('All Groups');
        await fixture.whenStable();

        expect(all('[data-testid="group-view"]')).toEqual([]);
        expect(all('[data-testid="group-tile"]').length).toBe(3);
      });

      it('lists the Group commands without a key, grayed out where they do not apply', async () => {
        await openGroup(0);
        document.dispatchEvent(new KeyboardEvent('keydown', { key: 'k', metaKey: true }));
        await settle();

        const disabled = (label: string) => paletteCommand(label)!.getAttribute('aria-disabled');
        expect(paletteCommand('Merge with next')!.querySelector('.key')).toBeNull();
        expect(disabled('Merge with next')).toBe('false');
        expect(disabled('Move to next Group')).toBe('false');
        expect(disabled('Merge with previous')).toBe('true');
        expect(disabled('Move to previous Group')).toBe('true');
        expect(disabled('Split here')).toBe('true');
        expect(disabled('Make Winner')).toBe('true');

        paletteCommand('Make Winner')!.click();
        await settle();
        http.expectNone((request) => request.url.includes('/override'));
      });
    });

    it('splits off the selected Frames', async () => {
      await openGroup(1);
      const splitSelected = all('[data-testid="split-selected"]')[0] as HTMLButtonElement;
      expect(splitSelected.disabled).toBe(true);

      await click(all('[data-testid="select-frame"]', frameDetails(0))[0]);
      await click(all('[data-testid="select-frame"]', frameDetails(2))[0]);
      expect(text('[data-testid="split-selected"]')).toBe('Split off 2 selected');
      await click(splitSelected);

      await expectFix('/api/groups/split', { frame_ids: [3, 5] });
    });

    it('cannot split off every Frame of a Group', async () => {
      await openGroup(0);

      await click(all('[data-testid="select-frame"]', frameDetails(0))[0]);
      await click(all('[data-testid="select-frame"]', frameDetails(1))[0]);

      expect((all('[data-testid="split-selected"]')[0] as HTMLButtonElement).disabled).toBe(true);
    });

    it('merges a Group with the previous or next Group', async () => {
      await openGroup(1);

      await click(all('[data-testid="merge-previous"]')[0]);
      await expectFix('/api/groups/merge', { frame_ids: [3, 1] });

      await click(all('[data-testid="merge-next"]')[0]);
      await expectFix('/api/groups/merge', { frame_ids: [3, 6] });
    });

    it('offers no merge or move past the first and last Group', async () => {
      await openGroup(0);
      expect(all('[data-testid="merge-previous"]')).toEqual([]);
      expect(all('[data-testid="move-previous"]')).toEqual([]);
      expect(all('[data-testid="merge-next"]').length).toBe(1);

      all('[data-testid="back-to-groups"]')[0].click();
      await fixture.whenStable();
      all('[data-testid="group-tile"]')[2].click();
      await fixture.whenStable();

      expect(all('[data-testid="merge-next"]')).toEqual([]);
      expect(all('[data-testid="move-next"]')).toEqual([]);
    });

    it('names the icon-only Group buttons without a native tooltip', async () => {
      await openGroup(1);

      const names = (selector: string) => accessibleNames(selector).map(({ label }) => label);
      expect(names('[data-testid="back-to-groups"]')).toEqual(['All Groups']);
      expect(names('[data-testid="merge-previous"]')).toEqual(['Merge with previous']);
      expect(names('[data-testid="merge-next"]')).toEqual(['Merge with next']);
      expect(names('[data-testid="split-here"]')).toEqual(['Split here', 'Split here']);
      expect(names('[data-testid="move-previous"]')).toEqual(
        Array(3).fill('Move to previous Group'),
      );
      expect(names('[data-testid="move-next"]')).toEqual(Array(3).fill('Move to next Group'));
      const makeWinner = names('[data-testid="make-winner"]');
      expect(makeWinner.length).toBeGreaterThan(0);
      expect(makeWinner).toEqual(makeWinner.map(() => 'Make Winner'));
      expect(all('[data-testid="group-view"] button[title]')).toEqual([]);
    });

    const groupButtonTooltips: [string, string][] = [
      ['back-to-groups', 'All Groups Esc'],
      ['merge-previous', 'Merge with previous'],
      ['merge-next', 'Merge with next'],
      ['split-here', 'Split here'],
      ['move-previous', 'Move to previous Group'],
      ['move-next', 'Move to next Group'],
      ['make-winner', 'Make Winner W'],
    ];

    for (const [testId, expected] of groupButtonTooltips) {
      it(`shows a "${expected}" tooltip when hovering ${testId}`, async () => {
        await openGroup(1);
        vi.useFakeTimers();

        await hover(all(`[data-testid="${testId}"]`)[0]);

        expect(tooltipText()).toBe(expected);
      });
    }

    it('moves a Frame to the previous or next Group', async () => {
      await openGroup(1);

      await click(all('[data-testid="move-previous"]', frameDetails(1))[0]);
      await expectFix('/api/frames/4/move', { to_frame_id: 1 });

      await click(all('[data-testid="move-next"]', frameDetails(2))[0]);
      await expectFix('/api/frames/5/move', { to_frame_id: 6 });
    });

    it('says so when a Group fix could not be saved', async () => {
      await openGroup(1);

      await click(all('[data-testid="merge-next"]')[0]);
      http
        .expectOne('/api/groups/merge')
        .flush('boom', { status: 422, statusText: 'Unprocessable Entity' });
      await settle();

      expect(text('[data-testid="override-error"]')).toBe('Could not save the Override.');
    });

    it('offers to reset a fixed Group only', async () => {
      await respond(summary, [
        group(1, [frame(1, 'jpg-only', { verdict: 'winner' })]),
        group(2, [frame(2, 'jpg-only', { verdict: 'winner' })], true),
      ]);
      all('[data-testid="group-tile"]')[0].click();
      await fixture.whenStable();
      expect(all('[data-testid="reset-grouping"]')).toEqual([]);

      all('[data-testid="back-to-groups"]')[0].click();
      await fixture.whenStable();
      all('[data-testid="group-tile"]')[1].click();
      await fixture.whenStable();
      await click(all('[data-testid="reset-grouping"]')[0]);

      await expectFix('/api/groups/reset', { frame_ids: [2] });
    });
  });

  describe('Trash', () => {
    const groups = (): Group[] => [
      group(1, [
        frame(1, 'jpg-only', { verdict: 'winner' }),
        frame(2, 'raw+jpg'),
        frame(3, 'jpg-only'),
      ]),
      group(4, [frame(4, 'jpg-only', { verdict: 'winner' })]),
    ];

    async function openGroup(index: number): Promise<void> {
      await respond(summary, groups());
      all('[data-testid="group-tile"]')[index].click();
      await fixture.whenStable();
    }

    async function press(key: string): Promise<void> {
      document.dispatchEvent(new KeyboardEvent('keydown', { key, bubbles: true }));
      await settle();
    }

    async function click(element: HTMLElement): Promise<void> {
      element.click();
      await settle();
    }

    function confirmation(): HTMLElement | undefined {
      return all('[data-testid="trash-confirmation"]')[0];
    }

    function currentFrameThumbnail(): string | null | undefined {
      return all('[data-testid="frame-details"].current')[0]
        ?.querySelector('img')
        ?.getAttribute('src');
    }

    async function confirmTrash(
      frameIds: number[],
      remaining: Group[],
      failed: { path: string; error: string }[] = [],
    ): Promise<void> {
      await click(all('[data-testid="trash-confirm"]')[0]);
      const request = http.expectOne('/api/frames/trash');
      expect(request.request.method).toBe('POST');
      expect(request.request.body).toEqual({ frame_ids: frameIds });
      const trashed = frameIds.filter((id) => !failed.length || id !== frameIds[0]);
      request.flush({ trashed, failed });
      await settle();
      http.expectOne('/api/session').flush(summary);
      http.expectOne((request) => request.url.startsWith('/api/groups')).flush(remaining);
      await settle();
    }

    it('asks before trashing the current Frame with Backspace, then shows the next Frame', async () => {
      await openGroup(0);
      await press('ArrowRight');

      await press('Backspace');

      expect(text('[data-testid="trash-confirmation"] p')).toBe(
        'Move 1 Frame (2 files) to the Trash?',
      );
      expect(text('#trash-note')).toContain('Lightroom will show as missing');
      expect(document.activeElement).toBe(all('[data-testid="trash-confirm"]')[0]);

      await confirmTrash(
        [2],
        [
          group(1, [frame(1, 'jpg-only', { verdict: 'winner' }), frame(3, 'jpg-only')]),
          groups()[1],
        ],
      );

      expect(confirmation()).toBeUndefined();
      expect(currentFrameThumbnail()).toBe('/api/frames/3/thumbnail');
    });

    it('leaves RAW-only Frames out of what a Trash moves, and says they stay', async () => {
      await respond(summary, [
        group(1, [
          frame(1, 'jpg-only', { verdict: 'winner' }),
          frame(2, 'raw+jpg'),
          frame(5, 'raw-only'),
        ]),
      ]);
      all('[data-testid="group-tile"]')[0].click();
      await fixture.whenStable();

      await click(all('[data-testid="trash-group"]')[0]);

      expect(text('[data-testid="trash-confirmation"] p')).toBe(
        'Move 2 Frames (3 files) to the Trash?',
      );
      expect(text('#trash-note')).toContain(
        "1 RAW-only Frame stays: framewise can't trash RAW-only Frames yet.",
      );
      await confirmTrash([1, 2], [group(5, [frame(5, 'raw-only', { verdict: 'winner' })])]);
    });

    it('offers nothing to trash when every Frame is RAW-only', async () => {
      await respond(summary, [group(5, [frame(5, 'raw-only', { verdict: 'winner' })])]);
      all('[data-testid="group-tile"]')[0].click();
      await fixture.whenStable();

      await press('Backspace');

      expect(text('[data-testid="trash-confirmation"] p')).toBe(
        "Nothing to move: framewise can't trash RAW-only Frames yet.",
      );
      expect((all('[data-testid="trash-confirm"]')[0] as HTMLButtonElement).disabled).toBe(true);
      expect(document.activeElement).toBe(all('[data-testid="trash-cancel"]')[0]);
    });

    it('asks to trash with Delete too, and trashes nothing on Escape', async () => {
      await openGroup(0);

      await press('Delete');
      expect(confirmation()).toBeDefined();
      await press('x');
      await press('Escape');

      expect(confirmation()).toBeUndefined();
      expect(all('[data-testid="group-view"]').length).toBe(1);
      http.expectNone('/api/frames/trash');
      http.expectNone((request) => request.url.includes('/override'));
    });

    it('trashes nothing on Cancel', async () => {
      await openGroup(0);
      await press('Backspace');

      await click(all('[data-testid="trash-cancel"]')[0]);

      expect(confirmation()).toBeUndefined();
      http.expectNone('/api/frames/trash');
    });

    it('shows the previous Frame after trashing the last Frame of a Group', async () => {
      await openGroup(0);
      await press('ArrowRight');
      await press('ArrowRight');
      await press('Backspace');

      await confirmTrash(
        [3],
        [group(1, [frame(1, 'jpg-only', { verdict: 'winner' }), frame(2, 'raw+jpg')]), groups()[1]],
      );

      expect(currentFrameThumbnail()).toBe('/api/frames/2/thumbnail');
    });

    it('trashes a whole Group and opens the next one', async () => {
      await openGroup(0);

      await click(all('[data-testid="trash-group"]')[0]);
      expect(text('[data-testid="trash-confirmation"] p')).toBe(
        'Move 3 Frames (4 files) to the Trash?',
      );
      await confirmTrash([1, 2, 3], [groups()[1]]);

      expect(currentFrameThumbnail()).toBe('/api/frames/4/thumbnail');
    });

    it('returns to All Groups after trashing the last Group', async () => {
      await openGroup(1);

      await runFromPalette('Trash Group');
      await confirmTrash([4], [groups()[0]]);

      expect(all('[data-testid="group-view"]')).toEqual([]);
      expect(all('[data-testid="group-tile"]').length).toBe(1);
    });

    it('trashes the selected Frames', async () => {
      await openGroup(0);
      const trashSelected = all('[data-testid="trash-selected"]')[0] as HTMLButtonElement;
      expect(trashSelected.disabled).toBe(true);

      await click(all('[data-testid="select-frame"]')[1]);
      await click(all('[data-testid="select-frame"]')[2]);
      expect(text('[data-testid="trash-selected"]')).toBe('Trash 2 selected');
      await click(trashSelected);

      await confirmTrash(
        [2, 3],
        [group(1, [frame(1, 'jpg-only', { verdict: 'winner' })]), groups()[1]],
      );
    });

    it('says which files could not be moved to the Trash', async () => {
      await openGroup(0);
      await press('Backspace');

      await confirmTrash([1], groups(), [
        { path: 'DSCF0001.JPG', error: 'No Trash on the volume' },
      ]);

      expect(text('[data-testid="trash-error"]')).toBe(
        'Could not move DSCF0001.JPG to the Trash: No Trash on the volume',
      );
      expect(currentFrameThumbnail()).toBe('/api/frames/1/thumbnail');
    });

    describe('selected Groups in All Groups', () => {
      const allGroups = (): Group[] => [
        group(1, [
          frame(1, 'jpg-only', { verdict: 'winner' }),
          frame(2, 'raw+jpg'),
          frame(3, 'jpg-only'),
        ]),
        group(4, [frame(4, 'jpg-only', { verdict: 'winner' })]),
        group(5, [frame(5, 'raw+jpg', { verdict: 'winner' }), frame(6, 'raw+jpg')]),
        group(7, [frame(7, 'jpg-only', { verdict: 'winner' })]),
      ];

      const tiles = () => all('[data-testid="group-tile"]');
      const checkboxes = () => all('[data-testid="select-group"]') as HTMLInputElement[];
      const selectedTiles = () =>
        checkboxes()
          .map((checkbox, index) => (checkbox.checked ? index : -1))
          .filter((index) => index !== -1);
      const trashGroups = () => all('[data-testid="trash-groups"]')[0];

      async function showAllGroups(): Promise<void> {
        await respond(summary, allGroups());
      }

      async function respondToTrash(
        frameIds: number[],
        trashed: number[],
        remaining: Group[],
        failed: { path: string; error: string }[] = [],
      ): Promise<void> {
        const request = http.expectOne('/api/frames/trash');
        expect(request.request.body).toEqual({ frame_ids: frameIds });
        request.flush({ trashed, failed });
        await settle();
        http.expectOne('/api/session').flush(summary);
        http.expectOne((request) => request.url.startsWith('/api/groups')).flush(remaining);
        await settle();
      }

      it('trashes every Frame of the Groups selected by checkbox, Winners included', async () => {
        await showAllGroups();
        expect(trashGroups()).toBeUndefined();

        await click(checkboxes()[0]);
        await click(checkboxes()[2]);
        expect(selectedTiles()).toEqual([0, 2]);
        expect(text('[data-testid="trash-groups"]')).toBe('Trash 2 Groups');
        await click(trashGroups());

        expect(text('[data-testid="trash-confirmation"] p')).toBe(
          'Move 2 Groups (5 Frames, 8 files) to the Trash?',
        );
        expect(text('#trash-note')).toContain('Lightroom will show as missing');
        await click(all('[data-testid="trash-confirm"]')[0]);
        await respondToTrash([1, 2, 3, 5, 6], [1, 2, 3, 5, 6], [allGroups()[1], allGroups()[3]]);

        expect(all('[data-testid="group-view"]')).toEqual([]);
        expect(coverThumbnails()).toEqual(['/api/frames/4/thumbnail', '/api/frames/7/thumbnail']);
        expect(selectedTiles()).toEqual([]);
        expect(trashGroups()).toBeUndefined();
      });

      async function clickWith(element: HTMLElement, init: MouseEventInit): Promise<void> {
        element.dispatchEvent(
          new MouseEvent('click', { bubbles: true, cancelable: true, ...init }),
        );
        await settle();
      }

      it('selects and deselects a Group with Command-click instead of opening it', async () => {
        await showAllGroups();

        await clickWith(tiles()[1], { metaKey: true });
        await clickWith(tiles()[3], { metaKey: true });
        expect(selectedTiles()).toEqual([1, 3]);
        await clickWith(tiles()[1], { metaKey: true });

        expect(selectedTiles()).toEqual([3]);
        expect(text('[data-testid="trash-groups"]')).toBe('Trash 1 Group');
        expect(all('[data-testid="group-view"]')).toEqual([]);
      });

      it('selects every Group in capture order between the last one selected and a Shift-click', async () => {
        await showAllGroups();

        await clickWith(tiles()[3], { metaKey: true });
        await clickWith(tiles()[1], { shiftKey: true });
        expect(selectedTiles()).toEqual([1, 2, 3]);
        await click(trashGroups());

        expect(text('[data-testid="trash-confirmation"] p')).toBe(
          'Move 3 Groups (4 Frames, 6 files) to the Trash?',
        );
        await click(all('[data-testid="trash-confirm"]')[0]);
        await respondToTrash([4, 5, 6, 7], [4, 5, 6, 7], [allGroups()[0]]);
      });

      it('selects a range with a Shift-click on a checkbox too', async () => {
        await showAllGroups();

        await click(checkboxes()[0]);
        await clickWith(checkboxes()[2], { shiftKey: true });

        expect(selectedTiles()).toEqual([0, 1, 2]);
      });

      it('starts a Shift-click range from the last Group selected that is still selected', async () => {
        await showAllGroups();
        await click(checkboxes()[0]);
        await clickWith(tiles()[3], { metaKey: true });
        await clickWith(tiles()[3], { metaKey: true });

        await clickWith(tiles()[2], { shiftKey: true });

        expect(selectedTiles()).toEqual([0, 1, 2]);
      });

      it('only toggles a Group on Shift-click once the selection is cleared', async () => {
        await showAllGroups();
        await click(checkboxes()[0]);
        await click(all('[data-testid="clear-selection"]')[0]);
        await clickWith(tiles()[2], { shiftKey: true });
        expect(selectedTiles()).toEqual([2]);

        await press('Escape');
        await clickWith(checkboxes()[1], { shiftKey: true });

        expect(selectedTiles()).toEqual([1]);
      });

      it('keeps the checkbox of a selected Group ticked when a Shift-click on it selects a range', async () => {
        await showAllGroups();
        await click(checkboxes()[0]);
        await click(checkboxes()[2]);

        await clickWith(checkboxes()[0], { shiftKey: true });

        expect(selectedTiles()).toEqual([0, 1, 2]);
        expect(text('[data-testid="trash-groups"]')).toBe('Trash 3 Groups');
      });

      it('still opens a Group on a plain click, clearing the selection', async () => {
        await showAllGroups();
        await click(checkboxes()[0]);

        await click(tiles()[1]);
        expect(all('[data-testid="group-view"]').length).toBe(1);
        await click(all('[data-testid="back-to-groups"]')[0]);

        expect(all('[data-testid="group-view"]')).toEqual([]);
        expect(selectedTiles()).toEqual([]);
        expect(trashGroups()).toBeUndefined();
      });

      it('clears the selection with Clear selection', async () => {
        await showAllGroups();
        await click(checkboxes()[0]);
        await click(checkboxes()[1]);

        await click(all('[data-testid="clear-selection"]')[0]);

        expect(selectedTiles()).toEqual([]);
        expect(trashGroups()).toBeUndefined();
      });

      it('asks to trash the selected Groups with Backspace or Delete, keeping them selected on Cancel', async () => {
        await showAllGroups();
        await click(checkboxes()[1]);

        await press('Backspace');
        expect(text('[data-testid="trash-confirmation"] p')).toBe(
          'Move 1 Group (1 Frame, 1 file) to the Trash?',
        );
        await click(all('[data-testid="trash-cancel"]')[0]);
        expect(confirmation()).toBeUndefined();
        expect(selectedTiles()).toEqual([1]);

        await press('Delete');
        expect(confirmation()).toBeDefined();
      });

      it('keeps the selection when a click outside the confirmation closes it', async () => {
        await showAllGroups();
        await click(checkboxes()[1]);
        await click(checkboxes()[3]);
        await press('Backspace');

        await click(all('app-trash-confirmation')[0]);

        expect(confirmation()).toBeUndefined();
        expect(selectedTiles()).toEqual([1, 3]);
        expect(text('[data-testid="trash-groups"]')).toBe('Trash 2 Groups');
        http.expectNone('/api/frames/trash');
      });

      it('keeps the selection when Escape closes the confirmation, and clears it on the next Escape', async () => {
        await showAllGroups();
        await click(checkboxes()[0]);
        await press('Backspace');

        await press('Escape');
        expect(confirmation()).toBeUndefined();
        expect(selectedTiles()).toEqual([0]);

        await press('Escape');
        expect(selectedTiles()).toEqual([]);
      });

      it('asks nothing on Backspace in All Groups with nothing selected', async () => {
        await showAllGroups();

        await press('Backspace');

        expect(confirmation()).toBeUndefined();
      });

      it('trashes the selected Groups from the command palette', async () => {
        await showAllGroups();
        document.dispatchEvent(new KeyboardEvent('keydown', { key: 'k', metaKey: true }));
        await settle();
        expect(paletteCommand('Trash selected Groups')?.getAttribute('aria-disabled')).toBe('true');
        await press('Escape');
        await click(checkboxes()[1]);
        await click(checkboxes()[3]);

        await runFromPalette('Trash 2 selected Groups');

        expect(text('[data-testid="trash-confirmation"] p')).toBe(
          'Move 2 Groups (2 Frames, 2 files) to the Trash?',
        );
        await click(all('[data-testid="trash-confirm"]')[0]);
        await respondToTrash([4, 7], [4, 7], [allGroups()[0], allGroups()[2]]);
      });

      it('clears the selection and turns selecting off while a filter is on', async () => {
        await showAllGroups();
        await click(checkboxes()[0]);
        await click(checkboxes()[1]);
        const verdict = all('[data-testid="verdict-filter"]')[0] as HTMLSelectElement;

        await choose(verdict, 'keeper');
        expect(checkboxes()).toEqual([]);
        expect(trashGroups()).toBeUndefined();
        await press('Backspace');
        expect(confirmation()).toBeUndefined();
        await choose(verdict, '');

        expect(checkboxes().length).toBe(4);
        expect(selectedTiles()).toEqual([]);
      });

      it('trashes the Frames counted when the confirmation opened, even if the Groups reload meanwhile', async () => {
        vi.useFakeTimers();
        http.expectOne('/api/session').flush(summary);
        await respondToPoll({ frames_done: 7, frames_left: 2, seconds_remaining: 10 }, allGroups());
        await click(checkboxes()[2]);
        await press('Backspace');

        await nextPoll();
        await respondToPoll({ frames_done: 9, frames_left: 0, seconds_remaining: 0 }, [
          ...allGroups().slice(0, 2),
          group(5, [
            frame(5, 'raw+jpg', { verdict: 'winner' }),
            frame(6, 'raw+jpg'),
            frame(8, 'jpg-only'),
          ]),
          allGroups()[3],
        ]);
        expect(text('[data-testid="trash-confirmation"] p')).toBe(
          'Move 1 Group (2 Frames, 4 files) to the Trash?',
        );
        await click(all('[data-testid="trash-confirm"]')[0]);

        await respondToTrash(
          [5, 6],
          [5, 6],
          [
            ...allGroups().slice(0, 2),
            group(8, [frame(8, 'jpg-only', { verdict: 'winner' })]),
            allGroups()[3],
          ],
        );
      });

      it('keeps a selected Group selected when analysis gives it an earlier Frame and a new id', async () => {
        vi.useFakeTimers();
        http.expectOne('/api/session').flush(summary);
        await respondToPoll({ frames_done: 7, frames_left: 2, seconds_remaining: 10 }, allGroups());
        await click(checkboxes()[2]);

        await nextPoll();
        await respondToPoll({ frames_done: 9, frames_left: 0, seconds_remaining: 0 }, [
          ...allGroups().slice(0, 2),
          group(0, [
            frame(0, 'jpg-only'),
            frame(5, 'raw+jpg', { verdict: 'winner' }),
            frame(6, 'raw+jpg'),
          ]),
          allGroups()[3],
        ]);

        expect(selectedTiles()).toEqual([2]);
      });

      it('drops a selected Group from the selection when analysis merges it with another', async () => {
        vi.useFakeTimers();
        http.expectOne('/api/session').flush(summary);
        await respondToPoll({ frames_done: 7, frames_left: 2, seconds_remaining: 10 }, allGroups());
        await click(checkboxes()[2]);

        await nextPoll();
        await respondToPoll({ frames_done: 9, frames_left: 0, seconds_remaining: 0 }, [
          allGroups()[0],
          group(4, [
            frame(4, 'jpg-only', { verdict: 'winner' }),
            frame(5, 'raw+jpg'),
            frame(6, 'raw+jpg'),
          ]),
          allGroups()[3],
        ]);

        expect(selectedTiles()).toEqual([]);
        expect(trashGroups()).toBeUndefined();
      });

      it('focuses the tile now where the first trashed Group was', async () => {
        await showAllGroups();
        await click(checkboxes()[2]);
        await click(checkboxes()[1]);
        await press('Backspace');
        await click(all('[data-testid="trash-confirm"]')[0]);

        await respondToTrash([4, 5, 6], [4, 5, 6], [allGroups()[0], allGroups()[3]]);

        expect(document.activeElement).toBe(tiles()[1]);
        expect(tiles()[1].getAttribute('aria-label')).toContain('DSCF0007.JPG');
      });

      it('moves focus only once the Groups reload after the Trash, not on an earlier poll', async () => {
        vi.useFakeTimers();
        http.expectOne('/api/session').flush(summary);
        await respondToPoll({ frames_done: 7, frames_left: 2, seconds_remaining: 10 }, allGroups());
        await click(checkboxes()[1]);
        await press('Backspace');
        await click(all('[data-testid="trash-confirm"]')[0]);
        const trash = http.expectOne('/api/frames/trash');
        await nextPoll();
        http.expectOne('/api/progress').flush({
          frames_done: 8,
          frames_left: 1,
          seconds_remaining: 5,
        });
        await settle();
        const groupsBeforeTrash = http.expectOne((request) =>
          request.url.startsWith('/api/groups'),
        );

        trash.flush({ trashed: [4], failed: [] });
        await settle();
        http.expectOne('/api/session').flush(summary);
        groupsBeforeTrash.flush(allGroups());
        await settle();
        expect(tiles()).not.toContain(document.activeElement);

        http
          .expectOne((request) => request.url.startsWith('/api/groups'))
          .flush([allGroups()[0], allGroups()[2], allGroups()[3]]);
        await settle();
        expect(document.activeElement).toBe(tiles()[1]);
        expect(tiles()[1].getAttribute('aria-label')).toContain('DSCF0005.JPG');
      });

      it('focuses the last tile when the trashed Groups were at the end', async () => {
        await showAllGroups();
        await click(checkboxes()[3]);
        await press('Backspace');
        await click(all('[data-testid="trash-confirm"]')[0]);

        await respondToTrash([7], [7], allGroups().slice(0, 3));

        expect(document.activeElement).toBe(tiles()[2]);
      });

      it('keeps the Groups that could not be fully trashed selected, and says which files failed', async () => {
        await showAllGroups();
        await click(checkboxes()[0]);
        await click(checkboxes()[2]);
        await press('Backspace');
        await click(all('[data-testid="trash-confirm"]')[0]);

        await respondToTrash(
          [1, 2, 3, 5, 6],
          [1, 3, 5, 6],
          [group(2, [frame(2, 'raw+jpg', { verdict: 'winner' })]), allGroups()[1], allGroups()[3]],
          [{ path: 'DSCF0002.JPG', error: 'No Trash on the volume' }],
        );

        expect(text('[data-testid="trash-error"]')).toBe(
          'Could not move DSCF0002.JPG to the Trash: No Trash on the volume',
        );
        expect(coverThumbnails()).toEqual([
          '/api/frames/2/thumbnail',
          '/api/frames/4/thumbnail',
          '/api/frames/7/thumbnail',
        ]);
        expect(selectedTiles()).toEqual([0]);
        expect(text('[data-testid="trash-groups"]')).toBe('Trash 1 Group');
      });

      it('offers no Select all', async () => {
        await showAllGroups();

        document.dispatchEvent(new KeyboardEvent('keydown', { key: 'a', metaKey: true }));
        await settle();
        await runFromPaletteIfListed('Select all');

        expect(selectedTiles()).toEqual([]);
      });

      async function runFromPaletteIfListed(label: string): Promise<void> {
        document.dispatchEvent(new KeyboardEvent('keydown', { key: 'k', metaKey: true }));
        await settle();
        expect(paletteCommand(label)).toBeUndefined();
        await press('Escape');
      }
    });
  });

  describe('losing the server', () => {
    const reviewed = (override: Frame['override'] = null): Group[] => [
      group(1, [frame(1, 'jpg-only', { verdict: 'winner', override })]),
    ];

    async function openGroup(): Promise<void> {
      await respond(summary, reviewed());
      all('[data-testid="group-tile"]')[0].click();
      await settle();
    }

    async function loseServer(request: { error(event: ProgressEvent): void }): Promise<void> {
      request.error(new ProgressEvent('error'));
      await settle();
    }

    async function nextReconnectAttempt(): Promise<void> {
      await vi.advanceTimersByTimeAsync(RECONNECT_INTERVAL_MS);
      await settle();
    }

    it('shows a disconnected state saying how to restart the server instead of the Frames', async () => {
      await openGroup();

      document.dispatchEvent(new KeyboardEvent('keydown', { key: 'x', bubbles: true }));
      await settle();
      await loseServer(http.expectOne('/api/frames/1/override'));

      expect(text('[data-testid="disconnected"]')).toContain('Lost the connection to framewise');
      expect(text('[data-testid="disconnected"] code')).toBe('framewise review');
      expect(all('[data-testid="group-view"]')).toEqual([]);
      expect(all('img[src^="/api/frames"]')).toEqual([]);
    });

    it('notices the server is gone when a Frame image fails to load', async () => {
      await respond(summary, reviewed());

      all('[data-testid="group-tile"] img')[0].dispatchEvent(new Event('error'));
      await settle();
      await loseServer(http.expectOne('/api/about'));

      expect(all('[data-testid="disconnected"]').length).toBe(1);
    });

    it('stays connected when a Frame image fails to load but the server answers', async () => {
      await respond(summary, reviewed());

      all('[data-testid="group-tile"] img')[0].dispatchEvent(new Event('error'));
      await settle();
      http.expectOne('/api/about').flush(about);
      await settle();

      expect(all('[data-testid="disconnected"]')).toEqual([]);
    });

    it('notices the server is gone when the photographer returns to an idle tab', async () => {
      await respond(summary, reviewed());

      document.dispatchEvent(new Event('visibilitychange'));
      await settle();
      await loseServer(http.expectOne('/api/about'));

      expect(all('[data-testid="disconnected"]').length).toBe(1);
    });

    it('comes back with the Session as the server stored it once the server is back', async () => {
      vi.useFakeTimers();
      await openGroup();
      document.dispatchEvent(new KeyboardEvent('keydown', { key: 'x', bubbles: true }));
      await settle();
      await loseServer(http.expectOne('/api/frames/1/override'));

      await nextReconnectAttempt();
      await loseServer(http.expectOne('/api/about'));
      expect(all('[data-testid="disconnected"]').length).toBe(1);

      await nextReconnectAttempt();
      http.expectOne('/api/about').flush(about);
      await settle();
      await respond(summary, reviewed());

      expect(all('[data-testid="disconnected"]')).toEqual([]);
      expect(all('[data-testid="group-view"]').length).toBe(1);
      expect(all('[data-testid="frame-tile"] img')[0].getAttribute('src')).toBe(
        '/api/frames/1/thumbnail',
      );
      await nextReconnectAttempt();
      http.expectNone('/api/about');
    });
  });
});

const SCORES: Frame['scores'] = {
  sharpness: 0.9,
  steadiness: 0.95,
  exposure: 1,
  aesthetics: 0.5,
  face_quality: null,
  expression: null,
  camera_rating: 0,
  total: 0.8,
};

function group(id: number, frames: Frame[], fixed = false): Group {
  return { id, frames, fixed };
}

function frame(id: number, kind: Frame['kind'], overrides: Partial<Frame> = {}): Frame {
  return {
    id,
    main_path: kind === 'raw-only' ? `DSCF000${id}.RAF` : `DSCF000${id}.JPG`,
    raw_path: kind === 'jpg-only' ? null : `DSCF000${id}.RAF`,
    kind,
    camera_rating: { stars: null, label: null },
    thumbnail_url: `/api/frames/${id}/thumbnail`,
    image_url: `/api/frames/${id}/image`,
    verdict: 'keeper',
    verdict_overridden: false,
    override: null,
    reasons: [],
    scores: SCORES,
    signals: {
      sharpness: 0.9,
      motion_blur: 0.05,
      exposure_stops: 0,
      low_key: false,
      high_key: false,
      aesthetics: 0,
    },
    sharpness_measured_on: 'frame',
    faces: [],
    ...overrides,
  };
}

function face(x: number, eyes: Face['eyes'], focus: Face['focus']): Face {
  return { box: { x, y: 0.3, width: 0.2, height: 0.25 }, eyes, focus };
}

function reason(code: string, label: string, text = label): Reason {
  return { code, label, text };
}
