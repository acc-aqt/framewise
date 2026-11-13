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
import { Group } from './session-api';

const TILE_WIDTH_PX = 220;
const ROW_HEIGHT_PX = 200;

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
        @for (group of row; track group.id) {
          <button
            type="button"
            class="group"
            data-testid="group-tile"
            [attr.aria-label]="'Open Group of ' + frameCount(group)"
            (click)="open.emit(group.id)"
          >
            <app-frame-tile class="cover" [frame]="group.frames[0]" />
            <span class="count" data-testid="frame-count">{{ frameCount(group) }}</span>
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
  readonly open = output<number>();

  protected readonly rowHeight = ROW_HEIGHT_PX;
  protected readonly columns = signal(4);
  protected readonly rows = computed(() => chunk(this.groups(), this.columns()));

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
