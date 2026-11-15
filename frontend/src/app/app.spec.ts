import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { App, POLL_INTERVAL_MS } from './app';
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
  total_frames: 3,
  jpg_only_count: 1,
  raw_jpg_count: 2,
  skipped: ['100LEICA/L1000009-Pano.dng'],
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

describe('Review UI', () => {
  let fixture: ComponentFixture<App>;
  let http: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      imports: [App],
      providers: [provideHttpClient(), provideHttpClientTesting()],
    });
    http = TestBed.inject(HttpTestingController);
    fixture = TestBed.createComponent(App);
    TestBed.tick();
  });

  afterEach(() => {
    http.verify();
    vi.useRealTimers();
  });

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

  function all(selector: string, root?: HTMLElement): HTMLElement[] {
    return Array.from(
      (root ?? (fixture.nativeElement as HTMLElement)).querySelectorAll<HTMLElement>(selector),
    );
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

  it('shows the Session summary counts', async () => {
    await respond(summary, []);

    expect(text('[data-testid="total-frames"]')).toBe('3');
    expect(text('[data-testid="jpg-only-count"]')).toBe('1');
    expect(text('[data-testid="raw-jpg-count"]')).toBe('2');
    expect(text('[data-testid="skipped-count"]')).toBe('1');
    expect(text('[data-testid="skipped-files"]')).toContain('100LEICA/L1000009-Pano.dng');
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

    it('keeps offering to choose a folder when the dialog is cancelled', async () => {
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
        'A change applies on the next framewise review, which re-analyses only the Frames it affects.',
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

  it('covers each Group with its Winner and shows its Verdict', async () => {
    await respond(summary, [
      group(1, [frame(1, 'jpg-only'), frame(2, 'jpg-only', { verdict: 'winner' })]),
    ]);

    const [tile] = all('[data-testid="group-tile"]');

    expect(tile.querySelector('img')?.getAttribute('src')).toBe('/api/frames/2/thumbnail');
    expect(text('[data-testid="verdict-badge"]', tile)).toBe('Winner');
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

  it('opens a Group to show its Frames side by side with kind badge and Camera rating', async () => {
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
    expect(
      tiles.map((tile) => tile.querySelector('[data-testid="kind-badge"]')?.textContent?.trim()),
    ).toEqual(['RAW+JPG', 'JPG-only', 'RAW+JPG']);
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

  it('fills the grid in as Frames are analysed and stops polling once analysis finishes', async () => {
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

  it('hides the progress once every Frame is analysed', async () => {
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
      const badges = () =>
        all('[data-testid="loupe"] [data-testid="face-badge"]').map((badge) =>
          badge.textContent?.replace(/\s+/g, ' ').trim(),
        );
      expect(badges()).toEqual(['Eyes open · Sharp', 'Eyes closed · Sharp']);

      await press('z');
      expect(badges()).toEqual(['Eyes open · Sharp', 'Eyes closed · Sharp']);
    });

    it('moves the loupe between Frames with the arrow keys', async () => {
      await openFirstGroup();
      await press('e');

      await press('ArrowRight');

      expect(all('[data-testid="loupe-image"]')[0].getAttribute('src')).toBe('/api/frames/2/image');
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
        await openFirstGroup();

        await openPalette();

        expect(palette()).toBeDefined();
        expect(rows()).toContain('Mark as Keeper P');
        expect(rows()).toContain('Next Frame in Group ⌥→');
        expect(rows()).toContain('Close Esc');
        expect(rows()).toContain('Make Winner W');
        expect(rows().length).toBe(29);
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

      it('greys out commands that do not apply, which then do nothing', async () => {
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

        expect(compareSides()).toEqual([
          { image: '/api/frames/2/image', verdict: 'Keeper' },
          { image: '/api/frames/1/image', verdict: 'Winner' },
        ]);
        expect(
          all('[data-testid="loupe-side"]').map((side) => text('[data-testid="face-badge"]', side)),
        ).toEqual(['Eyes closed · Soft', 'Eyes open · Sharp']);
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
      fixture = TestBed.createComponent(App);
      TestBed.tick();
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

      it('lists the Group commands without a key, greyed out where they do not apply', async () => {
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
});

const SCORES: Frame['scores'] = {
  sharpness: 0.9,
  steadiness: 0.95,
  exposure: 1,
  aesthetics: 0.5,
  face_quality: null,
  camera_rating: 0,
  total: 0.8,
};

function group(id: number, frames: Frame[], fixed = false): Group {
  return { id, frames, fixed };
}

function frame(id: number, kind: Frame['kind'], overrides: Partial<Frame> = {}): Frame {
  return {
    id,
    jpg_path: `DSCF000${id}.JPG`,
    raw_path: kind === 'raw+jpg' ? `DSCF000${id}.RAF` : null,
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
