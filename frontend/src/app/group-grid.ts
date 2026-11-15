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
  output,
  signal,
} from '@angular/core';
import { FrameTile } from './frame-tile';
import { Icon } from './icon';
import {
  isFiltering,
  matchesFilter,
  NO_FILTER,
  ProposalFilter,
  VERDICT_LABELS,
  winnerOf,
} from './proposal';
import { Frame, Group, Verdict } from './session-api';

const TILE_WIDTH_PX = 220;
const ROW_HEIGHT_PX = 200;
const KEPT_VERDICTS: Verdict[] = ['winner', 'keeper'];

interface GridTile {
  frame: Frame;
  group: Group;
}

@Component({
  selector: 'app-group-grid',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [ScrollingModule, FrameTile, Icon],
  template: `
    <div class="no-matches" data-testid="no-matches" aria-live="polite">
      @if (filtering() && tiles().length === 0) {
        <p data-testid="no-matches-message">No Frames match {{ activeFilters() }}.</p>
        <button type="button" class="btn" (click)="clearFilters.emit()">Clear filters</button>
      }
    </div>
    <cdk-virtual-scroll-viewport [itemSize]="rowHeight" class="viewport">
      <div
        *cdkVirtualFor="let row of rows()"
        class="row"
        [style.height.px]="rowHeight"
        [style.grid-template-columns]="'repeat(' + columns() + ', 1fr)'"
      >
        @for (tile of row; track tile.frame.id) {
          <button
            type="button"
            class="group"
            data-testid="group-tile"
            [attr.aria-label]="tileName(tile)"
            (click)="open.emit(tile.frame)"
          >
            <app-frame-tile class="cover" [frame]="tile.frame" [showVerdict]="filtering()">
              <span tile-mark class="count" data-testid="frame-count">
                <app-icon name="layers" [size]="12" />
                {{ frameCount(tile.group) }}
              </span>
              @if (!filtering() && tile.group.frames.length > 1) {
                <span tile-caption class="makeup" data-testid="group-makeup">
                  {{ makeup(tile.group) }}
                </span>
              }
            </app-frame-tile>
          </button>
        }
      </div>
    </cdk-virtual-scroll-viewport>
  `,
  styles: `
    :host {
      display: flex;
      flex-direction: column;
      height: 100%;
    }
    .no-matches {
      display: flex;
      flex-direction: column;
      align-items: center;
      gap: var(--space-3);
      color: var(--color-text-secondary);
    }
    .no-matches:not(:empty) {
      padding: var(--space-6) 0;
    }
    .no-matches p {
      margin: 0;
    }
    .viewport {
      flex: 1;
    }
    .row {
      display: grid;
      gap: var(--space-3);
      padding-bottom: var(--space-3);
      box-sizing: border-box;
    }
    .group {
      display: flex;
      min-width: 0;
      padding: 0;
      border: 0;
      border-radius: var(--radius-md);
      background: none;
      color: inherit;
      font: inherit;
      text-align: inherit;
      cursor: pointer;
    }
    .group:focus-visible {
      outline: 2px solid var(--color-focus);
      outline-offset: 2px;
    }
    .cover {
      flex: 1;
    }
    .group:hover .cover {
      border-color: var(--color-border-strong);
    }
    .makeup {
      flex: none;
      font-variant-numeric: tabular-nums;
    }
    .count {
      margin-left: auto;
      display: inline-flex;
      align-items: center;
      gap: var(--space-1);
      padding: 2px 6px;
      border-radius: var(--radius-sm);
      background: var(--color-overlay);
      color: var(--color-text);
      font-size: var(--text-xs);
      font-variant-numeric: tabular-nums;
      line-height: 1.3;
      white-space: nowrap;
    }
  `,
})
export class GroupGrid {
  readonly groups = input.required<Group[]>();
  readonly filter = input<ProposalFilter>(NO_FILTER);
  /** Emits the Frame shown on the clicked tile. */
  readonly open = output<Frame>();
  readonly clearFilters = output<void>();

  protected readonly rowHeight = ROW_HEIGHT_PX;
  protected readonly columns = signal(4);
  protected readonly filtering = computed(() => isFiltering(this.filter()));
  // Each Group's Winner stands for it, but a filter lists every matching Frame on its own tile.
  protected readonly tiles = computed<GridTile[]>(() => {
    const filter = this.filter();
    if (!isFiltering(filter)) {
      return this.groups().map((group) => ({ frame: winnerOf(group), group }));
    }
    return this.groups().flatMap((group) =>
      group.frames
        .filter((frame) => matchesFilter(frame, filter))
        .map((frame) => ({ frame, group })),
    );
  });
  protected readonly activeFilters = computed(() => {
    const { verdict, reason } = this.filter();
    const reasonLabel = this.groups()
      .flatMap((group) => group.frames.flatMap((frame) => frame.reasons))
      .find((candidate) => candidate.code === reason)?.label;
    return [verdict && VERDICT_LABELS[verdict], reasonLabel].filter(Boolean).join(' + ');
  });
  protected readonly rows = computed(() => chunk(this.tiles(), this.columns()));

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

  protected frameCount(group: Group): string {
    if (this.filtering()) {
      return `in Group of ${group.frames.length}`;
    }
    return group.frames.length === 1 ? '1 Frame' : `${group.frames.length} Frames`;
  }

  protected tileName({ frame, group }: GridTile): string {
    return `${frame.jpg_path}, ${VERDICT_LABELS[frame.verdict]}, Group of ${group.frames.length}`;
  }

  protected makeup(group: Group): string {
    const kept = group.frames.filter((frame) => KEPT_VERDICTS.includes(frame.verdict)).length;
    return `${kept} kept · ${group.frames.length - kept} out`;
  }
}

function chunk<T>(items: T[], size: number): T[][] {
  const rows: T[][] = [];
  for (let start = 0; start < items.length; start += size) {
    rows.push(items.slice(start, start + size));
  }
  return rows;
}
