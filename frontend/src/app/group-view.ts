import { NgTemplateOutlet } from '@angular/common';
import {
  afterRenderEffect,
  ChangeDetectionStrategy,
  Component,
  ElementRef,
  computed,
  inject,
  input,
  output,
  signal,
} from '@angular/core';
import { FrameTile } from './frame-tile';
import { Icon } from './icon';
import { findWinner, scoreBreakdown } from './proposal';
import { Frame, Group } from './session-api';

const SHORTCUT_HINTS = [
  { keys: '1–5', label: 'stars' },
  { keys: '6–9', label: 'labels' },
  { keys: 'P', label: 'keep' },
  { keys: 'X', label: 'reject' },
  { keys: 'U', label: 'clear' },
  { keys: '←→', label: 'Frames' },
  { keys: '⌥←→', label: 'in Group' },
  { keys: 'E', label: 'loupe' },
  { keys: 'Z', label: '100%' },
];

const PINNED_WINNER_COLLAPSED_KEY = 'framewise.pinnedWinnerCollapsed';

function readPinnedWinnerCollapsed(): boolean {
  try {
    return localStorage.getItem(PINNED_WINNER_COLLAPSED_KEY) === 'true';
  } catch {
    return false;
  }
}

function writePinnedWinnerCollapsed(collapsed: boolean): void {
  try {
    localStorage.setItem(PINNED_WINNER_COLLAPSED_KEY, String(collapsed));
  } catch {
    // Without browser storage the choice lasts until the page reloads.
  }
}

@Component({
  selector: 'app-group-view',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [FrameTile, Icon, NgTemplateOutlet],
  host: { 'data-testid': 'group-view' },
  template: `
    <div class="toolbar">
      <button
        type="button"
        class="btn btn-icon"
        data-testid="back-to-groups"
        aria-label="All Groups"
        title="All Groups"
        (click)="back.emit()"
      >
        <app-icon name="arrow-left" />
      </button>
      <h2 class="heading">Group of {{ group().frames.length }}</h2>
      <button
        type="button"
        class="btn"
        data-testid="split-selected"
        [disabled]="!canSplitSelected()"
        (click)="splitSelected()"
      >
        <app-icon name="scissors" [size]="14" />
        Split off {{ selected().length }} selected
      </button>
      @if (hasPrevious() || hasNext()) {
        <div class="merge" role="group" aria-label="Merge">
          @if (hasPrevious()) {
            <button
              type="button"
              class="btn btn-icon btn-ghost"
              data-testid="merge-previous"
              aria-label="Merge with previous"
              title="Merge with previous"
              (click)="merge.emit(-1)"
            >
              <app-icon name="merge-previous" [size]="14" />
            </button>
          }
          <span class="merge-caption" aria-hidden="true">Merge</span>
          @if (hasNext()) {
            <button
              type="button"
              class="btn btn-icon btn-ghost"
              data-testid="merge-next"
              aria-label="Merge with next"
              title="Merge with next"
              (click)="merge.emit(1)"
            >
              <app-icon name="merge-next" [size]="14" />
            </button>
          }
        </div>
      }
      @if (group().fixed) {
        <button
          type="button"
          class="btn btn-ghost"
          data-testid="reset-grouping"
          (click)="resetGrouping.emit()"
        >
          <app-icon name="reset" [size]="14" />
          Reset grouping
        </button>
      }
      <span class="keys">
        @for (hint of shortcutHints; track hint.label) {
          <span class="hint"
            ><kbd>{{ hint.keys }}</kbd> {{ hint.label }}</span
          >
        }
      </span>
    </div>
    <ng-template #frameInfo let-frame>
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
    </ng-template>
    <div class="body">
      @if (pinnedWinner(); as winner) {
        <aside
          class="pinned frame"
          data-testid="pinned-winner"
          aria-label="Winner"
          [class.collapsed]="pinnedWinnerCollapsed()"
        >
          <button
            type="button"
            class="btn btn-ghost toggle"
            data-testid="toggle-pinned-winner"
            [attr.aria-expanded]="!pinnedWinnerCollapsed()"
            [attr.aria-label]="pinnedWinnerToggleLabel()"
            [title]="pinnedWinnerToggleLabel()"
            (click)="togglePinnedWinner()"
          >
            <app-icon name="crown" [size]="14" />
            @if (!pinnedWinnerCollapsed()) {
              <span class="toggle-label">Winner</span>
            }
            <app-icon class="chevron" name="chevron-down" [size]="14" />
          </button>
          @if (!pinnedWinnerCollapsed()) {
            <app-frame-tile class="tile" [frame]="winner" [showFaces]="true" />
            <ng-container *ngTemplateOutlet="frameInfo; context: { $implicit: winner }" />
          }
        </aside>
      }
      <div class="frames">
        @for (frame of group().frames; track frame.id) {
          <section
            class="frame"
            data-testid="frame-details"
            [class.current]="frame.id === currentFrameId()"
            (click)="select.emit(frame)"
            (dblclick)="openLoupe.emit(frame)"
          >
            <app-frame-tile
              class="tile"
              data-testid="frame-tile"
              [frame]="frame"
              [showFaces]="true"
            />
            <ng-container *ngTemplateOutlet="frameInfo; context: { $implicit: frame }" />
            <div class="actions">
              <label class="select">
                <input
                  type="checkbox"
                  data-testid="select-frame"
                  [checked]="selectedIds().has(frame.id)"
                  (change)="toggleSelected(frame)"
                />
                Select
              </label>
              @if (!$first) {
                <button
                  type="button"
                  class="btn btn-icon btn-ghost"
                  data-testid="split-here"
                  aria-label="Split here"
                  title="Split here"
                  (click)="splitAt($index)"
                >
                  <app-icon name="scissors" [size]="14" />
                </button>
              }
              @if (hasPrevious()) {
                <button
                  type="button"
                  class="btn btn-icon btn-ghost"
                  data-testid="move-previous"
                  aria-label="Move to previous Group"
                  title="Move to previous Group"
                  (click)="move.emit({ frame, by: -1 })"
                >
                  <app-icon name="arrow-left" [size]="14" />
                </button>
              }
              @if (hasNext()) {
                <button
                  type="button"
                  class="btn btn-icon btn-ghost"
                  data-testid="move-next"
                  aria-label="Move to next Group"
                  title="Move to next Group"
                  (click)="move.emit({ frame, by: 1 })"
                >
                  <app-icon name="arrow-right" [size]="14" />
                </button>
              }
              @if (frame.verdict !== 'winner') {
                <button
                  type="button"
                  class="btn btn-icon make-winner"
                  data-testid="make-winner"
                  aria-label="Make Winner"
                  title="Make Winner"
                  (click)="makeWinner.emit(frame)"
                >
                  <app-icon name="crown" [size]="14" />
                </button>
              }
            </div>
          </section>
        }
      </div>
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
      flex-wrap: wrap;
      align-items: center;
      gap: var(--space-2);
      padding: var(--space-3) 0;
      border-bottom: 1px solid var(--color-border);
    }
    .heading {
      margin: 0 var(--space-2) 0 var(--space-1);
      font-size: var(--text-lg);
      font-weight: 600;
    }
    .merge {
      display: inline-flex;
      align-items: center;
      gap: var(--space-1);
      padding: 0 var(--space-1);
      border: 1px solid var(--color-border-strong);
      border-radius: var(--radius-md);
    }
    .merge .btn {
      height: calc(var(--control-height) - 6px);
      width: calc(var(--control-height) - 6px);
    }
    .merge-caption {
      color: var(--color-text-muted);
      font-size: var(--text-xs);
    }
    .keys {
      display: flex;
      flex-wrap: wrap;
      gap: var(--space-1) var(--space-3);
      margin-left: auto;
      color: var(--color-text-muted);
      font-size: var(--text-xs);
    }
    .hint {
      white-space: nowrap;
    }
    kbd {
      display: inline-block;
      min-width: 1.4em;
      margin-right: 2px;
      padding: 0 var(--space-1);
      border: 1px solid var(--color-border-strong);
      border-bottom-width: 2px;
      border-radius: var(--radius-sm);
      color: var(--color-text-secondary);
      font-family: var(--font-sans);
      font-size: 10px;
      line-height: 1.6;
      text-align: center;
    }
    .body {
      flex: 1;
      min-height: 0;
      display: flex;
      gap: var(--space-3);
    }
    .frame.pinned {
      flex: 0 0 clamp(250px, 30%, 420px);
      overflow-y: auto;
      margin: var(--space-3) 0 var(--space-2);
      outline-color: var(--color-winner);
    }
    .frame.pinned.collapsed {
      flex-basis: auto;
    }
    .toggle {
      align-self: stretch;
      justify-content: flex-start;
      gap: var(--space-1);
      color: var(--color-winner);
    }
    .pinned.collapsed .toggle {
      flex-direction: column;
    }
    .toggle-label {
      margin-right: auto;
      font-weight: 600;
    }
    .chevron {
      transform: rotate(90deg);
    }
    .pinned.collapsed .chevron {
      transform: rotate(-90deg);
    }
    .frames {
      flex: 1;
      min-width: 0;
      display: flex;
      gap: var(--space-3);
      padding: var(--space-3) 2px var(--space-2);
      overflow-x: auto;
    }
    .frame {
      flex: 1 0 250px;
      display: flex;
      flex-direction: column;
      gap: var(--space-2);
      padding: var(--space-2);
      border-radius: var(--radius-lg);
      background: var(--color-surface-1);
      outline: 2px solid transparent;
      transition: outline-color var(--duration-fast) var(--ease-out);
    }
    .frame.current {
      outline-color: var(--color-focus);
    }
    .tile {
      flex: 1;
      min-height: 0;
    }
    ul {
      margin: 0;
      padding: 0;
      list-style: none;
    }
    .reasons {
      font-size: var(--text-sm);
      color: var(--color-text-secondary);
    }
    .breakdown {
      display: flex;
      flex-wrap: wrap;
      gap: 2px var(--space-3);
      font-size: var(--text-xs);
      color: var(--color-text-muted);
      font-variant-numeric: tabular-nums;
    }
    .actions {
      display: flex;
      align-items: center;
      gap: var(--space-1);
      margin-top: auto;
      padding-top: var(--space-2);
      border-top: 1px solid var(--color-border);
    }
    .select {
      display: inline-flex;
      align-items: center;
      gap: var(--space-1);
      margin-right: auto;
      color: var(--color-text-secondary);
      font-size: var(--text-sm);
      cursor: pointer;
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
  readonly hasPrevious = input(false);
  readonly hasNext = input(false);
  /** Frames to split off the Group into a Group of their own. */
  readonly split = output<Frame[]>();
  /** Merges the Group with the previous (-1) or next (1) Group. */
  readonly merge = output<-1 | 1>();
  /** Moves a Frame to the previous (-1) or next (1) Group. */
  readonly move = output<{ frame: Frame; by: -1 | 1 }>();
  /** Hands the fixed Group back to framewise's grouping. */
  readonly resetGrouping = output();

  protected readonly breakdown = scoreBreakdown;
  protected readonly shortcutHints = SHORTCUT_HINTS;
  protected readonly selectedIds = signal<ReadonlySet<number>>(new Set());
  protected readonly selected = computed(() =>
    this.group().frames.filter((frame) => this.selectedIds().has(frame.id)),
  );
  protected readonly pinnedWinner = computed(() =>
    this.group().frames.length > 1 ? findWinner(this.group()) : undefined,
  );
  protected readonly pinnedWinnerCollapsed = signal(readPinnedWinnerCollapsed());
  protected readonly pinnedWinnerToggleLabel = computed(() =>
    this.pinnedWinnerCollapsed() ? 'Show Winner' : 'Hide Winner',
  );
  protected readonly canSplitSelected = computed(
    () => this.selected().length > 0 && this.selected().length < this.group().frames.length,
  );

  protected toggleSelected(frame: Frame): void {
    this.selectedIds.update((ids) => {
      const updated = new Set(ids);
      if (!updated.delete(frame.id)) {
        updated.add(frame.id);
      }
      return updated;
    });
  }

  protected togglePinnedWinner(): void {
    this.pinnedWinnerCollapsed.update((collapsed) => !collapsed);
    writePinnedWinnerCollapsed(this.pinnedWinnerCollapsed());
  }

  protected splitAt(index: number): void {
    this.split.emit(this.group().frames.slice(index));
  }

  protected splitSelected(): void {
    this.split.emit(this.selected());
    this.selectedIds.set(new Set());
  }

  constructor() {
    const host = inject<ElementRef<HTMLElement>>(ElementRef).nativeElement;
    afterRenderEffect(() => {
      this.currentFrameId();
      host.querySelector('.current')?.scrollIntoView?.({ block: 'nearest', inline: 'nearest' });
    });
  }
}
