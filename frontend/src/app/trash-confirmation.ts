import {
  afterNextRender,
  ChangeDetectionStrategy,
  Component,
  computed,
  ElementRef,
  input,
  output,
  viewChild,
} from '@angular/core';
import { pluralize } from './pluralize';
import { Frame } from './session-api';

/** The Frames a Trash moves: RAW-only Frames stay, as framewise can't trash them yet (#151). */
export function trashableFrames(frames: Frame[]): Frame[] {
  return frames.filter((frame) => frame.kind !== 'raw-only');
}

/**
 * Asks before Frames go to the Trash. Enter confirms, as the confirm button has focus. When every
 * Frame is RAW-only there is nothing to move, so only Cancel is offered.
 */
@Component({
  selector: 'app-trash-confirmation',
  changeDetection: ChangeDetectionStrategy.OnPush,
  host: { '(click)': 'cancel.emit()' },
  template: `
    <div
      class="panel"
      role="alertdialog"
      aria-modal="true"
      aria-labelledby="trash-question"
      aria-describedby="trash-note"
      data-testid="trash-confirmation"
      (click)="$event.stopPropagation()"
    >
      <p id="trash-question" class="question">{{ question() }}</p>
      <p id="trash-note" class="note">
        @if (trashable().length > 0) {
          You can restore them from the Trash. Frames already imported into Lightroom will show as
          missing there.
        }
        @if (rawOnlyNotice(); as notice) {
          {{ notice }}
        }
      </p>
      <div class="actions">
        <button
          #cancelButton
          type="button"
          class="btn btn-ghost"
          data-testid="trash-cancel"
          (click)="cancel.emit()"
        >
          Cancel
        </button>
        <button
          #confirmButton
          type="button"
          class="btn btn-danger"
          data-testid="trash-confirm"
          [disabled]="trashable().length === 0"
          (click)="confirm.emit()"
        >
          Move to Trash
        </button>
      </div>
    </div>
  `,
  styles: `
    :host {
      position: fixed;
      inset: 0;
      z-index: 50;
      display: flex;
      justify-content: center;
      align-items: flex-start;
      padding: 20vh var(--space-4) var(--space-4);
      background: var(--color-overlay);
    }
    .panel {
      display: flex;
      flex-direction: column;
      gap: var(--space-2);
      width: min(420px, 100%);
      padding: var(--space-4);
      border: 1px solid var(--color-border-strong);
      border-radius: var(--radius-lg);
      background: var(--color-surface-2);
      box-shadow: var(--shadow-1);
    }
    p {
      margin: 0;
    }
    .question {
      font-weight: 600;
    }
    .note {
      color: var(--color-text-secondary);
      font-size: var(--text-sm);
    }
    .actions {
      display: flex;
      justify-content: flex-end;
      gap: var(--space-2);
      margin-top: var(--space-2);
    }
  `,
})
export class TrashConfirmation {
  readonly frames = input.required<Frame[]>();
  /** How many Groups the Frames make up, when whole Groups are being trashed. */
  readonly groupCount = input<number | null>(null);
  readonly confirm = output();
  readonly cancel = output();

  protected readonly trashable = computed(() => trashableFrames(this.frames()));

  protected readonly question = computed(() => {
    const frames = this.trashable();
    if (frames.length === 0) {
      return "Nothing to move: framewise can't trash RAW-only Frames yet.";
    }
    const files = frames.reduce((sum, frame) => sum + (frame.kind === 'raw+jpg' ? 2 : 1), 0);
    const frameCount = pluralize(frames.length, 'Frame');
    const fileCount = pluralize(files, 'file');
    const groupCount = this.groupCount();
    return groupCount === null
      ? `Move ${frameCount} (${fileCount}) to the Trash?`
      : `Move ${pluralize(groupCount, 'Group')} (${frameCount}, ${fileCount}) to the Trash?`;
  });

  protected readonly rawOnlyNotice = computed(() => {
    const rawOnly = this.frames().length - this.trashable().length;
    if (rawOnly === 0 || this.trashable().length === 0) {
      return null;
    }
    const stay = rawOnly === 1 ? 'stays' : 'stay';
    return `${pluralize(rawOnly, 'RAW-only Frame')} ${stay}: framewise can't trash RAW-only Frames yet.`;
  });

  private readonly confirmButton =
    viewChild.required<ElementRef<HTMLButtonElement>>('confirmButton');
  private readonly cancelButton = viewChild.required<ElementRef<HTMLButtonElement>>('cancelButton');

  constructor() {
    afterNextRender(() => {
      const button = this.trashable().length > 0 ? this.confirmButton() : this.cancelButton();
      button.nativeElement.focus();
    });
  }
}
