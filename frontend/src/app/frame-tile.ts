import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';
import { scoreBreakdown, VERDICT_LABELS } from './proposal';
import { CameraRating, Frame } from './session-api';

const KIND_BADGES: Record<Frame['kind'], string> = {
  'jpg-only': 'JPG-only',
  'raw+jpg': 'RAW+JPG',
};

@Component({
  selector: 'app-frame-tile',
  changeDetection: ChangeDetectionStrategy.OnPush,
  host: { '[attr.title]': 'breakdown()' },
  template: `
    <img [src]="frame().thumbnail_url" [alt]="frame().jpg_path" loading="lazy" />
    <span class="badge" data-testid="kind-badge">{{ kindBadges[frame().kind] }}</span>
    @if (ratingText(frame().camera_rating); as rating) {
      <span class="rating" data-testid="camera-rating">{{ rating }}</span>
    }
    <span [class]="'verdict ' + frame().verdict" data-testid="verdict-badge">
      {{ verdictLabels[frame().verdict] }}
    </span>
    <span class="caption">{{ frame().jpg_path }}</span>
  `,
  styles: `
    :host {
      position: relative;
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
    .rating,
    .verdict {
      position: absolute;
      padding: 1px 6px;
      border-radius: 3px;
      font-size: 0.7rem;
      background: var(--color-overlay);
    }
    .badge {
      top: 6px;
      left: 6px;
    }
    .rating {
      top: 6px;
      right: 6px;
      color: var(--color-rating);
    }
    .verdict {
      left: 6px;
      bottom: 28px;
      font-weight: 600;
    }
    .winner {
      color: var(--color-winner);
    }
    .keeper {
      color: var(--color-keeper);
    }
    .reject {
      color: var(--color-reject);
    }
    .unsure {
      color: var(--color-unsure);
    }
    .caption {
      padding: 4px 6px;
      font-size: 0.7rem;
      color: var(--color-text-muted);
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }
  `,
})
export class FrameTile {
  readonly frame = input.required<Frame>();

  protected readonly kindBadges = KIND_BADGES;
  protected readonly verdictLabels = VERDICT_LABELS;
  protected readonly breakdown = computed(() => scoreBreakdown(this.frame()).join('\n'));

  protected ratingText(rating: CameraRating): string {
    const stars = '★'.repeat(Math.max(0, rating.stars ?? 0));
    return [stars, rating.label].filter(Boolean).join(' ');
  }
}
