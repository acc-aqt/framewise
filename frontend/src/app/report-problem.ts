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
import { Frame, ProblemReport, ReportImages } from './session-api';

/** The name a saved report gets, such as `framewise-report-2026-11-25.md`. */
export function reportFileName(date: Date): string {
  const day = [date.getFullYear(), date.getMonth() + 1, date.getDate()]
    .map((part) => String(part).padStart(2, '0'))
    .join('-');
  return `framewise-report-${day}.md`;
}

/** The last part of a main file's path, without its folders. */
function fileName(mainPath: string): string {
  return mainPath.slice(mainPath.lastIndexOf('/') + 1);
}

/** A file size the way GitHub's limit is put, such as `4.2 MB`. */
function megabytes(size: number): string {
  return `${(size / 1_000_000).toFixed(1)} MB`;
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
      <label class="option">
        <input
          type="checkbox"
          data-testid="report-include-images"
          [checked]="includeImages()"
          (change)="includeImages.set(!includeImages())"
        />
        Include images
      </label>
      @if (includeImages()) {
        <div class="images">
          <p class="note">
            framewise copies these Frames' images into a folder on this computer and opens it, so
            you can drag them into the GitHub page. Nothing is uploaded.
          </p>
          <ul data-testid="report-image-frames">
            @for (frame of frames(); track frame.id) {
              <li data-testid="report-image-frame">{{ fileName(frame.main_path) }}</li>
            }
          </ul>
        </div>
      }
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
      @if (images(); as prepared) {
        <div class="images" data-testid="report-image-files">
          <p class="note" data-testid="report-images-folder">
            Drag these images into the GitHub page from the folder that just opened:
            {{ prepared.folder }}
          </p>
          <ul>
            @for (file of prepared.files; track file.name) {
              <li data-testid="report-image-file">
                {{ file.name }} <span class="size">{{ megabytes(file.size) }}</span>
                @if (file.too_large) {
                  <span class="too-large" data-testid="report-image-too-large"
                    >Over GitHub's 10 MB limit, share it another way</span
                  >
                }
              </li>
            }
          </ul>
        </div>
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
    .note,
    .status {
      color: var(--color-text-secondary);
      font-size: var(--text-sm);
    }
    .option {
      display: flex;
      align-items: center;
      gap: var(--space-2);
    }
    .images ul {
      margin: var(--space-1) 0 0;
      padding-left: var(--space-4);
      max-height: 160px;
      overflow-y: auto;
      font-size: var(--text-sm);
    }
    .size {
      color: var(--color-text-secondary);
    }
    .too-large {
      color: var(--color-error);
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
  /** The Group's Frames, whose images the report may include. */
  readonly frames = input<readonly Pick<Frame, 'id' | 'main_path'>[]>([]);
  readonly close = output();

  protected readonly text = signal('');
  protected readonly ready = computed(() => this.text().trim() !== '' && !this.working());
  protected readonly working = signal(false);
  protected readonly error = signal<string | null>(null);
  protected readonly status = signal<string | null>(null);
  protected readonly includeImages = signal(false);
  protected readonly images = signal<ReportImages | null>(null);
  protected readonly fileName = fileName;
  protected readonly megabytes = megabytes;

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
    } else {
      tab.opener = null;
      tab.location.href = report.issue_url;
    }
    if (this.includeImages()) {
      await this.prepareImages();
    }
  }

  private async prepareImages(): Promise<void> {
    this.working.set(true);
    try {
      this.images.set(
        await firstValueFrom(
          this.api.prepareImages(this.groupId(), { remove_personal_info: false }),
        ),
      );
    } catch {
      this.error.set('Could not prepare the images.');
    } finally {
      this.working.set(false);
    }
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
    this.images.set(null);
    try {
      return await firstValueFrom(
        this.api.build(this.groupId(), { text: this.text(), include_state: true }),
      );
    } catch {
      this.error.set('Could not build the report.');
      return null;
    } finally {
      this.working.set(false);
    }
  }
}
