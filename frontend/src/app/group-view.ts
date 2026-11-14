import {
  afterRenderEffect,
  ChangeDetectionStrategy,
  Component,
  ElementRef,
  inject,
  input,
  output,
} from '@angular/core';
import { FrameTile } from './frame-tile';
import { scoreBreakdown } from './proposal';
import { Frame, Group } from './session-api';

@Component({
  selector: 'app-group-view',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [FrameTile],
  host: { 'data-testid': 'group-view' },
  template: `
    <div class="toolbar">
      <button type="button" data-testid="back-to-groups" (click)="back.emit()">← All Groups</button>
      <span>Group of {{ group().frames.length }}</span>
      <span class="keys">
        1–5 stars · 6–9 labels · P keep · X reject · U clear · ←/→ Frames · ⌥←/⌥→ in Group · E loupe
        · Z 100%
      </span>
    </div>
    <div class="frames">
      @for (frame of group().frames; track frame.id) {
        <section
          class="frame"
          data-testid="frame-details"
          [class.current]="frame.id === currentFrameId()"
          (click)="select.emit(frame)"
          (dblclick)="openLoupe.emit(frame)"
        >
          <app-frame-tile class="tile" data-testid="frame-tile" [frame]="frame" />
          @if (frame.verdict !== 'winner') {
            <button
              type="button"
              class="make-winner"
              data-testid="make-winner"
              (click)="makeWinner.emit(frame)"
            >
              Make Winner
            </button>
          }
          @if (frame.reasons.length > 0) {
            <ul class="reasons">
              @for (reason of frame.reasons; track reason.code) {
                <li data-testid="reason">{{ reason.text }}</li>
              }
            </ul>
          }
          <ul class="breakdown" data-testid="score-breakdown">
            @for (line of breakdown(frame); track line) {
              <li>{{ line }}</li>
            }
          </ul>
        </section>
      }
    </div>
  `,
  styles: `
    :host {
      display: flex;
      flex-direction: column;
      height: 100%;
    }
    .toolbar {
      display: flex;
      align-items: center;
      gap: 12px;
      padding-bottom: 8px;
      font-size: 0.85rem;
      color: var(--color-text-secondary);
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
    button:focus-visible {
      outline: 2px solid var(--color-focus);
      outline-offset: 2px;
    }
    .frames {
      flex: 1;
      min-height: 0;
      display: flex;
      gap: 8px;
      padding-bottom: 8px;
      overflow-x: auto;
    }
    .keys {
      margin-left: auto;
      color: var(--color-text-muted);
    }
    .frame {
      flex: 1 0 280px;
      display: flex;
      flex-direction: column;
      gap: 6px;
      padding: 4px;
      border-radius: 6px;
      outline: 2px solid transparent;
    }
    .frame.current {
      outline-color: var(--color-focus);
    }
    .make-winner {
      align-self: flex-start;
      font-size: 0.75rem;
    }
    .tile {
      flex: 1;
      min-height: 0;
    }
    ul {
      margin: 0;
      padding: 0;
      list-style: none;
      font-size: 0.75rem;
    }
    .reasons li {
      color: var(--color-text);
    }
    .breakdown {
      display: flex;
      flex-wrap: wrap;
      gap: 2px 10px;
      color: var(--color-text-muted);
      font-variant-numeric: tabular-nums;
    }
  `,
})
export class GroupView {
  readonly group = input.required<Group>();
  readonly currentFrameId = input<number | null>(null);
  readonly back = output<void>();
  readonly select = output<Frame>();
  readonly openLoupe = output<Frame>();
  readonly makeWinner = output<Frame>();

  protected readonly breakdown = scoreBreakdown;

  constructor() {
    const host = inject<ElementRef<HTMLElement>>(ElementRef).nativeElement;
    afterRenderEffect(() => {
      this.currentFrameId();
      host.querySelector('.current')?.scrollIntoView?.({ block: 'nearest', inline: 'nearest' });
    });
  }
}
