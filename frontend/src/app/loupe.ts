import { ChangeDetectionStrategy, Component, input, output } from '@angular/core';
import { FramePicture } from './frame-picture';
import { VERDICT_LABELS } from './proposal';
import { Frame } from './session-api';

export type LoupeZoom = 'fit' | '100%';

@Component({
  selector: 'app-loupe',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [FramePicture],
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
      <span>{{ frame().jpg_path }}</span>
      <span [class]="'verdict ' + frame().verdict">{{ verdictLabels[frame().verdict] }}</span>
      <button type="button" data-testid="loupe-zoom" (click)="toggleZoom.emit()">
        {{ zoom() === '100%' ? '100%' : 'Fit' }}
      </button>
      <button type="button" (click)="close.emit()">Close</button>
    </div>
  `,
  styles: `
    :host {
      position: fixed;
      inset: 0;
      z-index: 10;
      display: flex;
      flex-direction: column;
      background: var(--color-background);
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
      display: flex;
      align-items: center;
      gap: 12px;
      padding: 8px 16px;
      font-size: 0.85rem;
      color: var(--color-text-secondary);
    }
    .verdict {
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
    button {
      padding: 4px 10px;
      border: 1px solid var(--color-border);
      border-radius: 4px;
      background: var(--color-surface);
      color: var(--color-text);
      font: inherit;
      cursor: pointer;
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
