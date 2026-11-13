import { ScrollingModule } from '@angular/cdk/scrolling';
import {
  afterNextRender,
  ChangeDetectionStrategy,
  Component,
  computed,
  DestroyRef,
  ElementRef,
  inject,
  input,
  signal,
} from '@angular/core';
import { CameraRating, Frame } from './session-api';

const TILE_WIDTH_PX = 220;
const ROW_HEIGHT_PX = 200;
const KIND_BADGES: Record<Frame['kind'], string> = {
  'jpg-only': 'JPG-only',
  'raw+jpg': 'RAW+JPG',
};

@Component({
  selector: 'app-frame-grid',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [ScrollingModule],
  template: `
    <cdk-virtual-scroll-viewport [itemSize]="rowHeight" class="viewport">
      <div
        *cdkVirtualFor="let row of rows()"
        class="row"
        [style.height.px]="rowHeight"
        [style.grid-template-columns]="'repeat(' + columns() + ', 1fr)'"
      >
        @for (frame of row; track frame.id) {
          <figure class="tile" data-testid="frame-tile">
            <img [src]="frame.thumbnail_url" [alt]="frame.jpg_path" loading="lazy" />
            <span class="badge" data-testid="kind-badge">{{ kindBadges[frame.kind] }}</span>
            @if (ratingText(frame.camera_rating); as rating) {
              <span class="rating" data-testid="camera-rating">{{ rating }}</span>
            }
            <figcaption>{{ frame.jpg_path }}</figcaption>
          </figure>
        }
      </div>
    </cdk-virtual-scroll-viewport>
  `,
  styles: `
    :host {
      display: block;
      height: 100%;
    }
    .viewport {
      height: 100%;
    }
    .row {
      display: grid;
      gap: 8px;
      padding-bottom: 8px;
      box-sizing: border-box;
    }
    .tile {
      position: relative;
      margin: 0;
      min-width: 0;
      display: flex;
      flex-direction: column;
      background: var(--color-surface);
      border-radius: 4px;
      overflow: hidden;
    }
    img {
      flex: 1;
      min-height: 0;
      width: 100%;
      object-fit: contain;
    }
    .badge,
    .rating {
      position: absolute;
      top: 6px;
      padding: 1px 6px;
      border-radius: 3px;
      font-size: 0.7rem;
      background: var(--color-overlay);
    }
    .badge {
      left: 6px;
    }
    .rating {
      right: 6px;
      color: var(--color-rating);
    }
    figcaption {
      padding: 4px 6px;
      font-size: 0.7rem;
      color: var(--color-text-muted);
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }
  `,
})
export class FrameGrid {
  readonly frames = input.required<Frame[]>();

  protected readonly rowHeight = ROW_HEIGHT_PX;
  protected readonly kindBadges = KIND_BADGES;
  protected readonly columns = signal(4);
  protected readonly rows = computed(() => chunk(this.frames(), this.columns()));

  constructor() {
    const host = inject<ElementRef<HTMLElement>>(ElementRef).nativeElement;
    const destroyRef = inject(DestroyRef);
    afterNextRender(() => {
      if (typeof ResizeObserver === 'undefined') {
        return;
      }
      const observer = new ResizeObserver(([entry]) => {
        this.columns.set(Math.max(1, Math.floor(entry.contentRect.width / TILE_WIDTH_PX)));
      });
      observer.observe(host);
      destroyRef.onDestroy(() => observer.disconnect());
    });
  }

  protected ratingText(rating: CameraRating): string {
    const stars = '★'.repeat(Math.max(0, rating.stars ?? 0));
    return [stars, rating.label].filter(Boolean).join(' ');
  }
}

function chunk<T>(items: T[], size: number): T[][] {
  const rows: T[][] = [];
  for (let start = 0; start < items.length; start += size) {
    rows.push(items.slice(start, start + size));
  }
  return rows;
}
