import { ChangeDetectionStrategy, Component, input } from '@angular/core';
import { Face } from './session-api';

const EYES_LABELS: Record<Face['eyes'], string | null> = {
  open: 'Eyes open',
  closed: 'Eyes closed',
  unknown: null,
};

const FOCUS_LABELS: Record<Face['focus'], string> = {
  sharp: 'Sharp',
  soft: 'Soft',
};

/** Marks each face of a Frame. Place it over an element sized exactly like the Frame's image. */
@Component({
  selector: 'app-face-badges',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    @for (face of faces(); track $index) {
      <div
        class="face"
        data-testid="face-badge"
        [class.flagged]="isFlagged(face)"
        [style.left.%]="face.box.x * 100"
        [style.top.%]="face.box.y * 100"
        [style.width.%]="face.box.width * 100"
        [style.height.%]="face.box.height * 100"
      >
        <span class="label">{{ label(face) }}</span>
      </div>
    }
  `,
  styles: `
    :host {
      position: absolute;
      inset: 0;
      pointer-events: none;
    }
    .face {
      position: absolute;
      border: 1px solid var(--color-keeper);
      border-radius: var(--radius-sm);
      box-shadow: 0 0 0 1px var(--color-overlay);
    }
    .face.flagged {
      border: 1.5px solid var(--color-unsure);
    }
    .label {
      position: absolute;
      top: 100%;
      left: 50%;
      transform: translateX(-50%);
      margin-top: var(--space-1);
      padding: 1px 5px;
      border-radius: var(--radius-sm);
      background: var(--color-overlay);
      color: var(--color-keeper);
      font-size: 10px;
      font-weight: 500;
      line-height: 1.4;
      white-space: nowrap;
    }
    .flagged .label {
      color: var(--color-unsure);
    }
  `,
})
export class FaceBadges {
  readonly faces = input.required<Face[]>();

  protected isFlagged(face: Face): boolean {
    return face.eyes === 'closed' || face.focus === 'soft';
  }

  protected label(face: Face): string {
    return [EYES_LABELS[face.eyes], FOCUS_LABELS[face.focus]].filter(Boolean).join(' · ');
  }
}
