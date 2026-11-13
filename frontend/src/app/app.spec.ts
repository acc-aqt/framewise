import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { App } from './app';
import { Frame, SessionSummary } from './session-api';

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

  async function respond(session: SessionSummary, frames: Frame[]): Promise<void> {
    http.expectOne('/api/session').flush(session);
    http.expectOne('/api/frames').flush(frames);
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

  it('shows a tile per Frame with its kind badge and Camera rating', async () => {
    await respond(summary, [
      frame(1, 'raw+jpg', { stars: 1, label: 'Rot' }),
      frame(2, 'jpg-only', { stars: null, label: null }),
      frame(3, 'raw+jpg', { stars: 0, label: null }),
    ]);

    const tiles = Array.from(
      (fixture.nativeElement as HTMLElement).querySelectorAll<HTMLElement>(
        '[data-testid="frame-tile"]',
      ),
    );

    expect(
      tiles.map((tile) => tile.querySelector('[data-testid="kind-badge"]')?.textContent?.trim()),
    ).toEqual(['RAW+JPG', 'JPG-only', 'RAW+JPG']);
    expect(
      tiles.map(
        (tile) => tile.querySelector('[data-testid="camera-rating"]')?.textContent?.trim() ?? null,
      ),
    ).toEqual(['★ Rot', null, null]);
    expect(tiles[1].querySelector('img')?.getAttribute('src')).toBe('/api/frames/2/thumbnail');
  });

  it('virtualizes the grid so a large Session does not render every tile', async () => {
    const frames = Array.from({ length: 400 }, (_, index) =>
      frame(index + 1, 'jpg-only', { stars: null, label: null }),
    );
    await respond({ ...summary, total_frames: 400 }, frames);

    const tiles = (fixture.nativeElement as HTMLElement).querySelectorAll(
      '[data-testid="frame-tile"]',
    );
    expect(tiles.length).toBeGreaterThan(0);
    expect(tiles.length).toBeLessThan(400);
  });
});

function frame(id: number, kind: Frame['kind'], camera_rating: Frame['camera_rating']): Frame {
  return {
    id,
    jpg_path: `DSCF000${id}.JPG`,
    raw_path: kind === 'raw+jpg' ? `DSCF000${id}.RAF` : null,
    kind,
    camera_rating,
    thumbnail_url: `/api/frames/${id}/thumbnail`,
  };
}
