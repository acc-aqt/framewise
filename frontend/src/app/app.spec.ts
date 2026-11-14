import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { App, POLL_INTERVAL_MS } from './app';
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
    expect(all('[data-testid="write-back"]').length).toBe(1);
    expect(all('[data-testid="group-tile"]')).toEqual([]);
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

    it('opens the next Group without the loupe after leaving one with the loupe open', async () => {
      await openFirstGroup();
      await press('e');
      all('[data-testid="back-to-groups"]')[0].click();
      await fixture.whenStable();

      all('[data-testid="group-tile"]')[1].click();
      await fixture.whenStable();

      expect(all('[data-testid="loupe-image"]')).toEqual([]);
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
});

const SCORES: Frame['scores'] = {
  sharpness: 0.9,
  steadiness: 0.95,
  exposure: 1,
  aesthetics: 0.5,
  face_quality: null,
  total: 0.8,
};

function group(id: number, frames: Frame[]): Group {
  return { id, frames };
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
