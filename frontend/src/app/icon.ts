import { ChangeDetectionStrategy, Component, input } from '@angular/core';

export type IconName =
  | 'alert'
  | 'arrow-left'
  | 'arrow-right'
  | 'chevron-down'
  | 'close'
  | 'crown'
  | 'folder'
  | 'layers'
  | 'merge-next'
  | 'merge-previous'
  | 'reset'
  | 'scissors'
  | 'zoom';

/** A decorative stroke icon (paths from Lucide, ISC licence). Give its button an aria-label. */
@Component({
  selector: 'app-icon',
  changeDetection: ChangeDetectionStrategy.OnPush,
  host: { 'aria-hidden': 'true' },
  template: `
    <svg
      [attr.width]="size()"
      [attr.height]="size()"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      stroke-width="1.75"
      stroke-linecap="round"
      stroke-linejoin="round"
    >
      @switch (name()) {
        @case ('alert') {
          <svg:circle cx="12" cy="12" r="10" />
          <svg:path d="M12 8v4" />
          <svg:path d="M12 16h.01" />
        }
        @case ('arrow-left') {
          <svg:path d="m12 19-7-7 7-7" />
          <svg:path d="M19 12H5" />
        }
        @case ('arrow-right') {
          <svg:path d="M5 12h14" />
          <svg:path d="m12 5 7 7-7 7" />
        }
        @case ('chevron-down') {
          <svg:path d="m6 9 6 6 6-6" />
        }
        @case ('close') {
          <svg:path d="M18 6 6 18" />
          <svg:path d="m6 6 12 12" />
        }
        @case ('crown') {
          <svg:path
            d="M11.562 3.266a.5.5 0 0 1 .876 0L15.39 8.87a1 1 0 0 0 1.516.294L21.183 5.5a.5.5 0 0 1 .798.519l-2.834 10.246a1 1 0 0 1-.956.734H5.81a1 1 0 0 1-.957-.734L2.02 6.02a.5.5 0 0 1 .798-.519l4.276 3.664a1 1 0 0 0 1.516-.294z"
          />
          <svg:path d="M5 21h14" />
        }
        @case ('folder') {
          <svg:path
            d="M20 20a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-7.9a2 2 0 0 1-1.69-.9L9.6 3.9A2 2 0 0 0 7.93 3H4a2 2 0 0 0-2 2v13a2 2 0 0 0 2 2Z"
          />
        }
        @case ('layers') {
          <svg:path
            d="m12.83 2.18a2 2 0 0 0-1.66 0L2.6 6.08a1 1 0 0 0 0 1.83l8.58 3.91a2 2 0 0 0 1.66 0l8.58-3.9a1 1 0 0 0 0-1.83Z"
          />
          <svg:path d="m22 17.65-9.17 4.16a2 2 0 0 1-1.66 0L2 17.65" />
          <svg:path d="m22 12.65-9.17 4.16a2 2 0 0 1-1.66 0L2 12.65" />
        }
        @case ('merge-next') {
          <svg:path d="M17 12H3" />
          <svg:path d="m11 18 6-6-6-6" />
          <svg:path d="M21 5v14" />
        }
        @case ('merge-previous') {
          <svg:path d="M3 19V5" />
          <svg:path d="m13 6-6 6 6 6" />
          <svg:path d="M7 12h14" />
        }
        @case ('reset') {
          <svg:path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8" />
          <svg:path d="M3 3v5h5" />
        }
        @case ('scissors') {
          <svg:circle cx="6" cy="6" r="3" />
          <svg:path d="M8.12 8.12 12 12" />
          <svg:path d="M20 4 8.12 15.88" />
          <svg:circle cx="6" cy="18" r="3" />
          <svg:path d="M14.8 14.8 20 20" />
        }
        @case ('zoom') {
          <svg:circle cx="11" cy="11" r="8" />
          <svg:path d="m21 21-4.3-4.3" />
        }
      }
    </svg>
  `,
  styles: `
    :host {
      display: inline-flex;
      flex: none;
    }
  `,
})
export class Icon {
  readonly name = input.required<IconName>();
  readonly size = input(16);
}
