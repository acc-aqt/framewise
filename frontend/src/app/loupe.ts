import { ChangeDetectionStrategy, Component, input, output } from '@angular/core';
import { FramePicture } from './frame-picture';
import { Icon } from './icon';
import { VERDICT_LABELS } from './proposal';
import { Frame } from './session-api';

export type LoupeZoom = 'fit' | '100%';

@Component({
  selector: 'app-loupe',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [FramePicture, Icon],
  host: { 'data-testid': 'loupe', role: 'dialog', '[attr.aria-label]': 'frame().jpg_path' },
  template: `
    <div class="stage" [class.actual-size]="zoom() === '100%'" (click)="toggleZoom.emit()">
      <app-frame-picture
        class="picture"
        imageTestId="loupe-image"
        [src]="frame().image_url"
        [alt]="frame().jpg_path"
        [faces]="frame().faces"
        [fit]="zoom() === 'fit'"
      />
    </div>
    <div class="bar">
      <span class="file">{{ frame().jpg_path }}</span>
      <span [class]="'verdict ' + frame().verdict">
        <span class="dot"></span>
        {{ verdictLabels[frame().verdict] }}
      </span>
      <button type="button" class="btn" data-testid="loupe-zoom" (click)="toggleZoom.emit()">
        <app-icon name="zoom" [size]="14" />
        {{ zoom() === '100%' ? '100%' : 'Fit' }}
      </button>
      <button
        type="button"
        class="btn btn-icon"
        data-testid="loupe-close"
        aria-label="Close"
        title="Close"
        (click)="close.emit()"
      >
        <app-icon name="close" />
      </button>
    </div>
  `,
  styles: `
    :host {
      position: fixed;
      inset: 0;
      z-index: 10;
      display: flex;
      flex-direction: column;
      background: var(--color-loupe);
    }
    .stage {
      flex: 1;
      min-height: 0;
      display: flex;
      overflow: hidden;
      cursor: zoom-in;
    }
    .picture {
      flex: 1;
      min-width: 0;
      min-height: 0;
    }
    .stage.actual-size {
      overflow: auto;
      cursor: zoom-out;
    }
    .stage.actual-size .picture {
      flex: none;
      margin: auto;
    }
    .bar {
      position: absolute;
      bottom: var(--space-5);
      left: 50%;
      transform: translateX(-50%);
      max-width: calc(100% - 2 * var(--space-4));
      display: flex;
      align-items: center;
      gap: var(--space-3);
      padding: var(--space-2) var(--space-2) var(--space-2) var(--space-4);
      border: 1px solid var(--color-border);
      border-radius: var(--radius-lg);
      background: color-mix(in srgb, var(--color-surface-1) 90%, transparent);
      box-shadow: var(--shadow-2);
      backdrop-filter: blur(8px);
    }
    .file {
      min-width: 0;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
      color: var(--color-text-muted);
      font-family: var(--font-mono);
      font-size: var(--text-xs);
    }
    .verdict {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      padding: 2px var(--space-2);
      border-radius: var(--radius-pill);
      font-size: var(--text-sm);
      font-weight: 600;
      white-space: nowrap;
    }
    .dot {
      width: 6px;
      height: 6px;
      border-radius: var(--radius-pill);
      background: currentColor;
    }
    .winner {
      color: var(--color-winner);
      background: var(--color-winner-tint);
    }
    .keeper {
      color: var(--color-keeper);
      background: var(--color-keeper-tint);
    }
    .reject {
      color: var(--color-reject);
      background: var(--color-reject-tint);
    }
    .unsure {
      color: var(--color-unsure);
      background: var(--color-unsure-tint);
    }
  `,
})
export class Loupe {
  readonly frame = input.required<Frame>();
  readonly zoom = input.required<LoupeZoom>();
  readonly toggleZoom = output<void>();
  readonly close = output<void>();

  protected readonly verdictLabels = VERDICT_LABELS;
}
