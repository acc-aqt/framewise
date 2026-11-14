import {
  ChangeDetectionStrategy,
  Component,
  ElementRef,
  computed,
  inject,
  input,
  output,
} from '@angular/core';
import { FramePicture } from './frame-picture';
import { Icon } from './icon';
import { VERDICT_LABELS } from './proposal';
import { Frame } from './session-api';

export type LoupeZoom = 'fit' | '100%';

@Component({
  selector: 'app-loupe',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [FramePicture, Icon],
  host: { 'data-testid': 'loupe', role: 'dialog', '[attr.aria-label]': 'label()' },
  template: `
    <div class="sides">
      @for (frame of frames(); track $index) {
        <section class="side" data-testid="loupe-side">
          <div
            #stage
            class="stage"
            [class.actual-size]="zoom() === '100%'"
            (click)="toggleZoom.emit()"
            (scroll)="alignStages(stage)"
          >
            <app-frame-picture
              class="picture"
              imageTestId="loupe-image"
              [src]="frame.image_url"
              [alt]="frame.jpg_path"
              [faces]="frame.faces"
              [fit]="zoom() === 'fit'"
            />
          </div>
          <div class="caption">
            <span [class]="'verdict ' + frame.verdict" data-testid="loupe-verdict">
              <span class="dot"></span>
              {{ verdictLabels[frame.verdict] }}
            </span>
            <span class="file">{{ frame.jpg_path }}</span>
          </div>
        </section>
      }
    </div>
    <div class="bar">
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
    .sides {
      flex: 1;
      min-height: 0;
      display: flex;
      gap: 2px;
    }
    .side {
      position: relative;
      flex: 1;
      min-width: 0;
      display: flex;
    }
    .stage {
      flex: 1;
      min-width: 0;
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
    .caption {
      position: absolute;
      top: var(--space-3);
      left: var(--space-3);
      max-width: calc(100% - 2 * var(--space-3));
      display: flex;
      align-items: center;
      gap: var(--space-2);
      padding: var(--space-1) var(--space-3) var(--space-1) var(--space-1);
      border-radius: var(--radius-pill);
      background: color-mix(in srgb, var(--color-surface-1) 85%, transparent);
      backdrop-filter: blur(8px);
      pointer-events: none;
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
      padding: var(--space-2);
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
  /** One Frame, or the current Frame and the Group's Winner to compare side by side. */
  readonly frames = input.required<Frame[]>();
  readonly zoom = input.required<LoupeZoom>();
  readonly toggleZoom = output<void>();
  readonly close = output<void>();

  protected readonly verdictLabels = VERDICT_LABELS;
  protected readonly label = computed(() =>
    this.frames()
      .map((frame) => frame.jpg_path)
      .join(' and '),
  );

  private readonly host = inject<ElementRef<HTMLElement>>(ElementRef).nativeElement;

  /** Scrolls every side to where `source` is, so at 100% they show the same region. */
  protected alignStages(source: HTMLElement): void {
    for (const stage of this.host.querySelectorAll<HTMLElement>('.stage')) {
      if (stage !== source) {
        stage.scrollLeft = source.scrollLeft;
        stage.scrollTop = source.scrollTop;
      }
    }
  }
}
