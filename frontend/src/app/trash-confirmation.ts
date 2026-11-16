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
import { Frame } from './session-api';

/** Asks before Frames go to the Trash. Enter confirms, as the confirm button has focus. */
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
        You can restore them from the Trash. Frames already imported into Lightroom will show as
        missing there.
      </p>
      <div class="actions">
        <button
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

  protected readonly question = computed(() => {
    const frames = this.frames();
    const files = frames.reduce((sum, frame) => sum + (frame.kind === 'raw+jpg' ? 2 : 1), 0);
    const frameCount = count(frames.length, 'Frame');
    const fileCount = count(files, 'file');
    const groupCount = this.groupCount();
    return groupCount === null
      ? `Move ${frameCount} (${fileCount}) to the Trash?`
      : `Move ${count(groupCount, 'Group')} (${frameCount}, ${fileCount}) to the Trash?`;
  });

  private readonly confirmButton =
    viewChild.required<ElementRef<HTMLButtonElement>>('confirmButton');

  constructor() {
    afterNextRender(() => this.confirmButton().nativeElement.focus());
  }
}

function count(n: number, noun: string): string {
  return n === 1 ? `1 ${noun}` : `${n} ${noun}s`;
}
