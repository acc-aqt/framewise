import { ChangeDetectionStrategy, Component, input } from '@angular/core';
import { CameraRating, Frame } from './session-api';

const KIND_BADGES: Record<Frame['kind'], string> = {
  'jpg-only': 'JPG-only',
  'raw+jpg': 'RAW+JPG',
};

@Component({
  selector: 'app-frame-tile',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <img [src]="frame().thumbnail_url" [alt]="frame().jpg_path" loading="lazy" />
    <span class="badge" data-testid="kind-badge">{{ kindBadges[frame().kind] }}</span>
    @if (ratingText(frame().camera_rating); as rating) {
      <span class="rating" data-testid="camera-rating">{{ rating }}</span>
    }
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

  protected ratingText(rating: CameraRating): string {
    const stars = '★'.repeat(Math.max(0, rating.stars ?? 0));
    return [stars, rating.label].filter(Boolean).join(' ');
  }
}
