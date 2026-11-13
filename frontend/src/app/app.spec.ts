import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { App } from './app';
import { Frame, Group, SessionSummary } from './session-api';

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

  afterEach(() => http.verify());

  function text(selector: string): string {
    return (
      (fixture.nativeElement as HTMLElement).querySelector(selector)?.textContent?.trim() ?? ''
    );
  }

  function all(selector: string, root?: HTMLElement): HTMLElement[] {
    return Array.from(
      (root ?? (fixture.nativeElement as HTMLElement)).querySelectorAll<HTMLElement>(selector),
    );
  }

  async function respond(session: SessionSummary, groups: Group[]): Promise<void> {
    http.expectOne('/api/session').flush(session);
    http.expectOne('/api/groups').flush(groups);
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

  it('shows a tile per Group with its first Frame as cover and its Frame count', async () => {
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

  it('opens a Group to show its Frames side by side with kind badge and Camera rating', async () => {
    await respond(summary, [
      group(1, [frame(1, 'jpg-only')]),
      group(2, [
        frame(2, 'raw+jpg', { stars: 1, label: 'Rot' }),
        frame(3, 'jpg-only'),
        frame(4, 'raw+jpg', { stars: 0, label: null }),
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

  it('returns from an open Group to the grid of Groups', async () => {
    await respond(summary, [group(1, [frame(1, 'jpg-only')]), group(2, [frame(2, 'jpg-only')])]);
    all('[data-testid="group-tile"]')[0].click();
    await fixture.whenStable();

    all('[data-testid="back-to-groups"]')[0].click();
    await fixture.whenStable();

    expect(all('[data-testid="group-view"]')).toEqual([]);
    expect(all('[data-testid="group-tile"]').length).toBe(2);
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
});

function group(id: number, frames: Frame[]): Group {
  return { id, frames };
}

function frame(
  id: number,
  kind: Frame['kind'],
  camera_rating: Frame['camera_rating'] = { stars: null, label: null },
): Frame {
  return {
    id,
    jpg_path: `DSCF000${id}.JPG`,
    raw_path: kind === 'raw+jpg' ? `DSCF000${id}.RAF` : null,
    kind,
    camera_rating,
    thumbnail_url: `/api/frames/${id}/thumbnail`,
  };
}
