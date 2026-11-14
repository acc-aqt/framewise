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
import { isFiltering, matchesFilter, NO_FILTER, ProposalFilter, winnerOf } from './proposal';
import { Frame, Group } from './session-api';

const TILE_WIDTH_PX = 220;
const ROW_HEIGHT_PX = 200;

interface GridTile {
  frame: Frame;
  group: Group;
}

@Component({
  selector: 'app-group-grid',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [ScrollingModule, FrameTile],
  template: `
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
            [attr.aria-label]="'Open Group of ' + frameCount(tile.group)"
            (click)="open.emit(tile.frame)"
          >
            <app-frame-tile class="cover" [frame]="tile.frame" />
            <span class="count" data-testid="frame-count">{{ frameCount(tile.group) }}</span>
          </button>
        }
      </div>
    </cdk-virtual-scroll-viewport>
  `,
  styles: `
    :host {
      display: block;
      height: 100%;
    }
    .viewport {
      height: 100%;
    }
    .row {
      display: grid;
      gap: 8px;
      padding-bottom: 8px;
      box-sizing: border-box;
    }
    .group {
      position: relative;
      display: flex;
      min-width: 0;
      padding: 0;
      border: 0;
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
    .count {
      position: absolute;
      right: 6px;
      bottom: 28px;
      padding: 1px 6px;
      border-radius: 3px;
      font-size: 0.7rem;
      background: var(--color-overlay);
    }
  `,
})
export class GroupGrid {
  readonly groups = input.required<Group[]>();
  readonly filter = input<ProposalFilter>(NO_FILTER);
  /** Emits the Frame shown on the clicked tile. */
  readonly open = output<Frame>();

  protected readonly rowHeight = ROW_HEIGHT_PX;
  protected readonly columns = signal(4);
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
    return group.frames.length === 1 ? '1 Frame' : `${group.frames.length} Frames`;
  }
}

function chunk<T>(items: T[], size: number): T[][] {
  const rows: T[][] = [];
  for (let start = 0; start < items.length; start += size) {
    rows.push(items.slice(start, start + size));
  }
  return rows;
}
