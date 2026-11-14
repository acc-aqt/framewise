import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';
import { FramePicture } from './frame-picture';
import { Icon } from './icon';
import { scoreBreakdown, VERDICT_LABELS } from './proposal';
import { CameraRating, ColorLabel, Frame } from './session-api';

const KIND_BADGES: Record<Frame['kind'], string> = {
  'jpg-only': 'JPG-only',
  'raw+jpg': 'RAW+JPG',
};

/** A Frame's thumbnail with its marks; projected content is laid over the image. */
@Component({
  selector: 'app-frame-tile',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [FramePicture, Icon],
  host: { '[attr.title]': 'breakdown()' },
  template: `
    <div class="media">
      <app-frame-picture
        class="picture"
        [src]="frame().thumbnail_url"
        [alt]="frame().jpg_path"
        [faces]="showFaces() ? frame().faces : null"
        [lazy]="true"
      />
      <span class="badge kind" data-testid="kind-badge">{{ kindBadges[frame().kind] }}</span>
      @if (ratingText(frame().camera_rating); as rating) {
        <span class="badge rating" data-testid="camera-rating">{{ rating }}</span>
      }
      <span class="marks">
        <span
          [class]="'badge verdict ' + frame().verdict"
          data-testid="verdict-badge"
          [attr.title]="verdictSource()"
        >
          @if (frame().verdict === 'winner') {
            <app-icon name="crown" [size]="12" />
          } @else {
            <span class="dot"></span>
          }
          {{ verdictLabels[frame().verdict] }}
        </span>
        @if (frame().verdict_overridden) {
          <span class="badge override" data-testid="override-mark">Override</span>
        }
        @if (overrideRating(); as rating) {
          <span class="badge override-rating" data-testid="override-rating">{{ rating }}</span>
        }
      </span>
      <ng-content />
    </div>
    <span class="caption">{{ frame().jpg_path }}</span>
  `,
  styles: `
    :host {
      min-width: 0;
      display: flex;
      flex-direction: column;
      background: var(--color-surface-2);
      border: 1px solid transparent;
      border-radius: var(--radius-md);
      box-shadow: var(--shadow-1);
      overflow: hidden;
      transition: border-color var(--duration-fast) var(--ease-out);
    }
    .media {
      position: relative;
      flex: 1;
      min-height: 0;
      display: flex;
    }
    .picture {
      flex: 1;
      min-width: 0;
    }
    .badge {
      display: inline-flex;
      align-items: center;
      gap: var(--space-1);
      padding: 2px 6px;
      border-radius: var(--radius-sm);
      background: var(--color-overlay);
      font-size: var(--text-xs);
      line-height: 1.3;
      white-space: nowrap;
    }
    .kind,
    .rating,
    .marks {
      position: absolute;
    }
    .kind {
      top: 6px;
      left: 6px;
      color: var(--color-text-secondary);
      font-size: 10px;
      font-weight: 600;
      letter-spacing: 0.04em;
    }
    .rating {
      top: 6px;
      right: 6px;
      color: var(--color-rating);
    }
    .marks {
      left: 6px;
      bottom: 6px;
      display: flex;
      gap: var(--space-1);
    }
    .verdict {
      font-weight: 600;
    }
    .dot {
      width: 6px;
      height: 6px;
      border-radius: var(--radius-pill);
      background: currentColor;
    }
    .override {
      border: 1px solid var(--color-override);
      padding: 1px 5px;
      color: var(--color-override);
    }
    .override-rating {
      color: var(--color-rating);
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
      padding: 6px 8px 7px;
      font-family: var(--font-mono);
      font-size: var(--text-xs);
      color: var(--color-text-muted);
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }
  `,
})
export class FrameTile {
  readonly frame = input.required<Frame>();
  /** Marks each face of the Frame on its image. */
  readonly showFaces = input(false);

  protected readonly kindBadges = KIND_BADGES;
  protected readonly verdictLabels = VERDICT_LABELS;
  protected readonly breakdown = computed(() => scoreBreakdown(this.frame()).join('\n'));

  protected readonly verdictSource = computed(() =>
    this.frame().verdict_overridden ? 'Your Override' : "framewise's Verdict",
  );
  protected readonly overrideRating = computed(() => {
    const override = this.frame().override;
    if (override === null) {
      return '';
    }
    return this.ratingText({ stars: override.stars, label: labelName(override.label) });
  });

  protected ratingText(rating: CameraRating): string {
    const stars = '★'.repeat(Math.max(0, rating.stars ?? 0));
    return [stars, rating.label].filter(Boolean).join(' ');
  }
}

function labelName(label: ColorLabel | null): string | null {
  return label === null ? null : label[0].toUpperCase() + label.slice(1);
}
