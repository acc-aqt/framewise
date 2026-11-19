import { ChangeDetectionStrategy, Component, computed, inject, input, signal } from '@angular/core';
import { FaceBadges } from './face-badges';
import { ServerConnection } from './server-connection';
import { Face } from './session-api';

/**
 * A Frame's image, optionally with a badge on each face. Fitted, it fills as much of the host as
 * its aspect ratio allows; otherwise it shows at its natural size. Either way the picture is
 * exactly the size of the image, so face badges land on their faces. Face badges wait for the
 * image to load, so they never show over an empty or still-loading picture.
 */
@Component({
  selector: 'app-frame-picture',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [FaceBadges],
  host: { '[class.fit]': 'fit()' },
  template: `
    <div
      class="picture"
      [style.aspect-ratio]="fit() ? aspectRatio() : null"
      [style.width]="fit() ? fittedWidth() : null"
      [style.height]="fit() && aspectRatio() !== null ? 'auto' : null"
    >
      <img
        [src]="src()"
        [alt]="alt()"
        [attr.loading]="lazy() ? 'lazy' : null"
        [attr.data-testid]="imageTestId()"
        (load)="imageLoaded($event)"
        (error)="connection.check()"
      />
      @if (badgedFaces(); as faces) {
        <app-face-badges [faces]="faces" />
      }
    </div>
  `,
  styles: `
    :host {
      display: flex;
    }
    :host(.fit) {
      align-items: center;
      justify-content: center;
      container-type: size;
    }
    .picture {
      position: relative;
      margin: auto;
    }
    :host(.fit) .picture {
      width: 100%;
      height: 100%;
    }
    img {
      display: block;
    }
    :host(.fit) img {
      width: 100%;
      height: 100%;
      object-fit: contain;
    }
  `,
})
export class FramePicture {
  readonly src = input.required<string>();
  readonly alt = input.required<string>();
  /** The faces to mark, or null to mark none. */
  readonly faces = input<Face[] | null>(null);
  readonly fit = input(true);
  readonly lazy = input(false);
  readonly imageTestId = input<string | null>(null);

  protected readonly connection = inject(ServerConnection);

  /** The image's width over its height, once loaded. */
  protected readonly aspectRatio = signal<number | null>(null);
  protected readonly fittedWidth = computed(() => {
    const ratio = this.aspectRatio();
    return ratio === null ? null : `min(100cqw, ${ratio * 100}cqh)`;
  });

  /** The image whose load last finished, so a new image hides the previous one's badges. */
  private readonly loadedSrc = signal<string | null>(null);
  protected readonly badgedFaces = computed(() =>
    this.loadedSrc() === this.src() ? this.faces() : null,
  );

  protected imageLoaded(event: Event): void {
    this.loadedSrc.set(this.src());
    const image = event.target as HTMLImageElement;
    if (image.naturalWidth > 0 && image.naturalHeight > 0) {
      this.aspectRatio.set(image.naturalWidth / image.naturalHeight);
    }
  }
}
