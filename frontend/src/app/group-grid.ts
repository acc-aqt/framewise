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
  model,
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
  host: {
    '[class.selecting]': 'selected().length > 0',
    '[class.narrow]': 'layout() === narrowLayout',
  },
  template: `
    @if (selected().length > 0) {
      <div class="selection-bar" data-testid="group-selection">
        <button
          type="button"
          class="btn btn-danger"
          data-testid="trash-groups"
          (click)="trash.emit(selected())"
        >
          <app-icon name="trash" [size]="14" />
          Trash {{ groupCount(selected().length) }}
        </button>
        <button
          type="button"
          class="btn btn-ghost"
          data-testid="clear-selection"
          (click)="selected.set([])"
        >
          Clear selection
        </button>
      </div>
    }
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
          <div class="tile">
            <button
              type="button"
              class="group"
              data-testid="group-tile"
              [attr.data-frame-id]="tile.frame.id"
              [attr.aria-label]="tileName(tile)"
              (click)="onTileClick($event, tile)"
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
            @if (!filtering()) {
              <input
                type="checkbox"
                class="select"
                data-testid="select-group"
                [attr.aria-label]="'Select ' + tileName(tile)"
                [checked]="isSelected(tile.group)"
                (click)="onCheckboxClick($event, tile.group)"
              />
            }
          </div>
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
    .selection-bar {
      display: flex;
      align-items: center;
      gap: var(--space-2);
      padding-bottom: var(--space-3);
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
    .tile {
      position: relative;
      display: flex;
      min-width: 0;
    }
    .group {
      flex: 1;
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
    .select {
      position: absolute;
      top: var(--space-2);
      left: var(--space-2);
      margin: 0;
      opacity: 0;
    }
    .tile:hover .select,
    .tile:focus-within .select,
    :host(.selecting) .select,
    :host(.narrow) .select {
      opacity: 1;
    }
    @media (hover: none) {
      .select {
        opacity: 1;
      }
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
  /** The Groups selected to act on, in capture order. Selecting is off while filtering. */
  readonly selected = model<Group[]>([]);
  /** Emits the Frame shown on the clicked tile. */
  readonly open = output<Frame>();
  readonly clearFilters = output<void>();
  /** Groups to move to the Trash, once the photographer confirms. */
  readonly trash = output<Group[]>();

  // A Frame of the Group selected last, where a Shift-click range starts.
  private anchorFrameId: number | null = null;
  private readonly width = signal<number | null>(null);
  protected readonly narrowLayout = NARROW_LAYOUT;
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

  private readonly host = inject<ElementRef<HTMLElement>>(ElementRef).nativeElement;

  constructor() {
    const destroyRef = inject(DestroyRef);
    afterNextRender(() => {
      if (typeof ResizeObserver === 'undefined') {
        return;
      }
      const observer = new ResizeObserver(([entry]) => {
        this.width.set(entry.contentRect.width);
      });
      observer.observe(this.host);
      destroyRef.onDestroy(() => observer.disconnect());
    });
  }

  /** Focuses the tile at this position, or the last tile if there are fewer, keeping the scroll. */
  focusTile(index: number): void {
    const tiles = this.tiles();
    const tile = tiles[Math.min(index, tiles.length - 1)];
    if (tile !== undefined) {
      this.host
        .querySelector<HTMLElement>(`[data-frame-id="${tile.frame.id}"]`)
        ?.focus({ preventScroll: true });
    }
  }

  protected onTileClick(event: MouseEvent, tile: GridTile): void {
    if (!this.filtering() && (event.metaKey || event.ctrlKey)) {
      return this.toggle(tile.group);
    }
    if (!this.filtering() && event.shiftKey) {
      return this.selectRange(tile.group);
    }
    this.open.emit(tile.frame);
  }

  protected onCheckboxClick(event: MouseEvent, group: Group): void {
    // The checkbox shows the selection, so the click doesn't tick it by itself.
    event.preventDefault();
    if (event.shiftKey) {
      this.selectRange(group);
    } else {
      this.toggle(group);
    }
  }

  protected isSelected(group: Group): boolean {
    return this.selected().includes(group);
  }

  protected groupCount(count: number): string {
    return count === 1 ? '1 Group' : `${count} Groups`;
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

  private toggle(group: Group): void {
    const selected = new Set(this.selected());
    if (selected.has(group)) {
      selected.delete(group);
    } else {
      selected.add(group);
      this.anchorFrameId = group.frames[0].id;
    }
    this.select(selected);
  }

  private selectRange(group: Group): void {
    const groups = this.groups();
    const anchor = groups.findIndex((candidate) =>
      candidate.frames.some((frame) => frame.id === this.anchorFrameId),
    );
    if (this.selected().length === 0 || anchor === -1) {
      return this.toggle(group);
    }
    const target = groups.indexOf(group);
    const range = groups.slice(Math.min(anchor, target), Math.max(anchor, target) + 1);
    this.select(new Set([...this.selected(), ...range]));
  }

  private select(selected: Set<Group>): void {
    this.selected.set(this.groups().filter((group) => selected.has(group)));
  }
}

/**
 * The Groups still selected once the Groups change, as when analysis or a Trash reloads them.
 * A Group stays selected while its Frames all come from one selected Group, so it survives
 * gaining Frames or a new id. A Group merged with another, or fully trashed, drops out.
 */
export function stillSelected(before: Group[], selected: Group[], after: Group[]): Group[] {
  if (selected.length === 0) {
    return [];
  }
  const groupOf = new Map<number, Group>();
  for (const group of before) {
    for (const frame of group.frames) {
      groupOf.set(frame.id, group);
    }
  }
  return after.filter((group) => {
    const earlier = new Set(group.frames.map((frame) => groupOf.get(frame.id)));
    earlier.delete(undefined);
    return earlier.size === 1 && selected.includes([...earlier][0]!);
  });
}

function chunk<T>(items: T[], size: number): T[][] {
  const rows: T[][] = [];
  for (let start = 0; start < items.length; start += size) {
    rows.push(items.slice(start, start + size));
  }
  return rows;
}
