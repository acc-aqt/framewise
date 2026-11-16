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
  isKept,
  matchesFilter,
  NO_FILTER,
  ProposalFilter,
  reasonLabels,
  VERDICT_LABELS,
  winnerOf,
} from './proposal';
import { Frame, Group } from './session-api';

// A grid about as narrow as a portrait window gets fewer, larger tiles, so the Frame name and
// counts stay readable; wider grids keep the layout they always had.
const WIDE_LAYOUT = { minTileWidth: 220, rowHeight: 200 };
const NARROW_LAYOUT = { minTileWidth: 300, rowHeight: 280 };
const NARROW_GRID_BELOW_PX = 760;

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
    <cdk-virtual-scroll-viewport [itemSize]="layout().rowHeight" class="viewport">
      <div
        *cdkVirtualFor="let row of rows()"
        class="row"
        [style.height.px]="layout().rowHeight"
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
      padding: var(--space-1) var(--space-2);
      border-radius: var(--radius-sm);
      background: var(--color-overlay);
      color: var(--color-text);
      font-size: var(--text-xs);
      font-variant-numeric: tabular-nums;
      line-height: 1;
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

  private readonly width = signal<number | null>(null);
  protected readonly layout = computed(() => {
    const width = this.width();
    return width !== null && width < NARROW_GRID_BELOW_PX ? NARROW_LAYOUT : WIDE_LAYOUT;
  });
  protected readonly columns = computed(() => {
    const width = this.width();
    return width === null ? 4 : Math.max(1, Math.floor(width / this.layout().minTileWidth));
  });
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
    const frames = this.groups().flatMap((group) => group.frames);
    const reasonLabel = reason === null ? null : reasonLabels(frames).get(reason);
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
        this.width.set(entry.contentRect.width);
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
    const kept = group.frames.filter(isKept).length;
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
