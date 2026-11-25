import {
  afterNextRender,
  ChangeDetectionStrategy,
  Component,
  computed,
  ElementRef,
  inject,
  input,
  output,
  signal,
  viewChild,
} from '@angular/core';
import { firstValueFrom } from 'rxjs';
import { ReportApi } from './report-api';
import { ProblemReport } from './session-api';

/** The name a saved report gets, such as `framewise-report-2026-11-25.md`. */
export function reportFileName(date: Date): string {
  const day = [date.getFullYear(), date.getMonth() + 1, date.getDate()]
    .map((part) => String(part).padStart(2, '0'))
    .join('-');
  return `framewise-report-${day}.md`;
}

/**
 * Lets the photographer describe a judging problem in one Group and send it as a Problem report:
 * on a prefilled GitHub new-issue page they submit themselves, or copied or saved to send any
 * other way.
 */
@Component({
  selector: 'app-report-problem',
  changeDetection: ChangeDetectionStrategy.OnPush,
  host: { '(click)': 'close.emit()' },
  template: `
    <div
      class="panel"
      role="dialog"
      aria-modal="true"
      aria-labelledby="report-heading"
      data-testid="report-problem"
      (click)="$event.stopPropagation()"
    >
      <h2 id="report-heading" class="heading">Report a problem</h2>
      <label class="field">
        <span>What did you expect instead?</span>
        <textarea
          #textField
          rows="5"
          data-testid="report-text"
          [value]="text()"
          (input)="text.set(textField.value)"
        ></textarea>
      </label>
      <label class="check" data-testid="report-include-state">
        <input
          type="checkbox"
          data-testid="report-include-state-box"
          [checked]="includeState()"
          (change)="includeState.set(!includeState())"
        />
        Include Group state
      </label>
      <p class="note">
        Open on GitHub shows the report on a new issue page, where you can edit it before you submit
        it. Nothing is sent until you do.
      </p>
      @if (error(); as message) {
        <p class="error-message" role="alert" data-testid="report-error">{{ message }}</p>
      }
      @if (status(); as message) {
        <p class="status" role="status" data-testid="report-status">{{ message }}</p>
      }
      <div class="actions">
        <button
          type="button"
          class="btn btn-ghost"
          data-testid="report-cancel"
          (click)="close.emit()"
        >
          Cancel
        </button>
        <button
          type="button"
          class="btn"
          data-testid="report-copy"
          [disabled]="!ready()"
          (click)="copyReport()"
        >
          Copy report
        </button>
        <button
          type="button"
          class="btn"
          data-testid="report-save"
          [disabled]="!ready()"
          (click)="saveReport()"
        >
          Save report
        </button>
        <button
          type="button"
          class="btn btn-primary"
          data-testid="report-open-github"
          [disabled]="!ready()"
          (click)="openOnGitHub()"
        >
          Open on GitHub
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
      padding: 15vh var(--space-4) var(--space-4);
      background: var(--color-overlay);
    }
    .panel {
      display: flex;
      flex-direction: column;
      gap: var(--space-3);
      width: min(520px, 100%);
      padding: var(--space-4);
      border: 1px solid var(--color-border-strong);
      border-radius: var(--radius-lg);
      background: var(--color-surface-2);
      box-shadow: var(--shadow-1);
    }
    .heading {
      margin: 0;
      font-size: var(--text-md);
      font-weight: 600;
    }
    p {
      margin: 0;
    }
    .field {
      display: flex;
      flex-direction: column;
      gap: var(--space-1);
    }
    textarea {
      padding: var(--space-2);
      border: 1px solid var(--color-border-strong);
      border-radius: var(--radius-md);
      background: var(--color-surface-1);
      color: inherit;
      font: inherit;
      resize: vertical;
    }
    .check {
      display: flex;
      align-items: center;
      gap: var(--space-2);
    }
    .note,
    .status {
      color: var(--color-text-secondary);
      font-size: var(--text-sm);
    }
    .actions {
      display: flex;
      justify-content: flex-end;
      gap: var(--space-2);
    }
  `,
})
export class ReportProblem {
  /** The Group to report on, identified by its first Frame's id. */
  readonly groupId = input.required<number>();
  readonly close = output();

  protected readonly text = signal('');
  /** Whether the report carries the Group's Verdicts, Scores and Overrides after the text. */
  protected readonly includeState = signal(true);
  protected readonly ready = computed(() => this.text().trim() !== '' && !this.working());
  protected readonly working = signal(false);
  protected readonly error = signal<string | null>(null);
  protected readonly status = signal<string | null>(null);

  private readonly api = inject(ReportApi);
  private readonly textField = viewChild.required<ElementRef<HTMLTextAreaElement>>('textField');

  constructor() {
    afterNextRender(() => this.textField().nativeElement.focus());
  }

  protected async openOnGitHub(): Promise<void> {
    // Opened before the report is built, while the click still allows opening a tab.
    const tab = window.open('', '_blank');
    const report = await this.build();
    if (report === null) {
      tab?.close();
      return;
    }
    if (tab === null) {
      window.open(report.issue_url, '_blank', 'noopener');
      return;
    }
    tab.opener = null;
    tab.location.href = report.issue_url;
  }

  protected async copyReport(): Promise<void> {
    const report = await this.build();
    if (report === null) {
      return;
    }
    await navigator.clipboard.writeText(report.body);
    this.status.set('Report copied to the clipboard.');
  }

  protected async saveReport(): Promise<void> {
    const report = await this.build();
    if (report === null) {
      return;
    }
    const fileName = reportFileName(new Date());
    const url = URL.createObjectURL(new Blob([report.body], { type: 'text/markdown' }));
    const link = document.createElement('a');
    link.href = url;
    link.download = fileName;
    link.click();
    URL.revokeObjectURL(url);
    this.status.set(`Report saved as ${fileName}.`);
  }

  private async build(): Promise<ProblemReport | null> {
    this.working.set(true);
    this.error.set(null);
    this.status.set(null);
    try {
      return await firstValueFrom(
        this.api.build(this.groupId(), { text: this.text(), include_state: this.includeState() }),
      );
    } catch {
      this.error.set('Could not build the report.');
      return null;
    } finally {
      this.working.set(false);
    }
  }
}
