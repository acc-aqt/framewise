import { ComponentFixture, TestBed } from '@angular/core/testing';
import { GroupGrid } from './group-grid';
import { Frame, Group } from './session-api';

describe('Group grid', () => {
  let fixture: ComponentFixture<GroupGrid>;
  let reportWidth: (width: number) => void;

  beforeEach(() => {
    vi.stubGlobal(
      'ResizeObserver',
      class {
        constructor(callback: ResizeObserverCallback) {
          reportWidth = (width) =>
            callback([{ contentRect: { width } } as ResizeObserverEntry], this as never);
        }
        observe(): void {}
        disconnect(): void {}
      },
    );
    fixture = TestBed.createComponent(GroupGrid);
    fixture.componentRef.setInput(
      'groups',
      Array.from({ length: 12 }, (_, index) => group(index + 1)),
    );
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  async function layOutAt(width: number): Promise<HTMLElement[]> {
    await fixture.whenStable();
    reportWidth(width);
    await fixture.whenStable();
    return Array.from((fixture.nativeElement as HTMLElement).querySelectorAll<HTMLElement>('.row'));
  }

  function tilesIn(row: HTMLElement): number {
    return row.querySelectorAll('[data-testid="group-tile"]').length;
  }

  it('fits six Group tiles per row in a wide window', async () => {
    const [row] = await layOutAt(1408);

    expect(tilesIn(row)).toBe(6);
    expect(row.style.height).toBe('200px');
  });

  it('keeps the wide layout in a grid just wider than a portrait window', async () => {
    const [row] = await layOutAt(800);

    expect(tilesIn(row)).toBe(3);
    expect(row.style.height).toBe('200px');
  });

  it('shows two larger Group tiles per row in a narrow window', async () => {
    const [row] = await layOutAt(688);

    expect(tilesIn(row)).toBe(2);
    expect(row.style.height).toBe('280px');
  });
});

function group(id: number): Group {
  return { id, frames: [frame(id)], fixed: false };
}

function frame(id: number): Frame {
  return {
    id,
    jpg_path: `DSCF${String(id).padStart(4, '0')}.JPG`,
    raw_path: null,
    kind: 'jpg-only',
    camera_rating: { stars: null, label: null },
    thumbnail_url: `/api/frames/${id}/thumbnail`,
    image_url: `/api/frames/${id}/image`,
    verdict: 'winner',
    verdict_overridden: false,
    override: null,
    reasons: [],
    scores: {
      sharpness: 0.9,
      steadiness: 0.95,
      exposure: 1,
      aesthetics: 0.5,
      face_quality: null,
      expression: null,
      camera_rating: 0,
      total: 0.8,
    },
    signals: {
      sharpness: 0.9,
      motion_blur: 0.05,
      exposure_stops: 0,
      low_key: false,
      high_key: false,
      aesthetics: 0,
    },
    faces: [],
  };
}
