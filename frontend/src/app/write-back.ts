import { NgTemplateOutlet } from '@angular/common';
import { HttpClient, httpResource } from '@angular/common/http';
import {
  ChangeDetectionStrategy,
  Component,
  computed,
  effect,
  inject,
  input,
  output,
  signal,
} from '@angular/core';
import { firstValueFrom } from 'rxjs';
import { Icon } from './icon';
import { pluralize } from './pluralize';
import { VERDICT_LABELS } from './proposal';
import {
  ColorLabel,
  WriteBackDryRun,
  WriteBackFile,
  WriteBackProgress,
  WriteBackRating,
  WriteBackResult,
} from './session-api';
import { Tooltip, TooltipContent } from './tooltip';

const PROGRESS_POLL_INTERVAL_MS = 500;

interface Outcome {
  ok: boolean;
  summary: string;
  failed: WriteBackResult['failed'];
}

@Component({
  selector: 'app-write-back',
  changeDetection: ChangeDetectionStrategy.OnPush,
  host: { 'data-testid': 'write-back' },
  imports: [Icon, NgTemplateOutlet, Tooltip],
  template: `
    <div class="toolbar">
      <button
        type="button"
        class="btn btn-ghost"
        data-testid="back-from-write-back"
        (click)="back.emit()"
      >
        <app-icon name="arrow-left" [size]="14" />
        All Groups
      </button>
      <h2>Rating write-back</h2>
    </div>
    @if (working()) {
      <div class="working" role="status" data-testid="write-back-progress">
        @if (progressValue(); as progress) {
          <progress [value]="progress.files_done" [max]="progress.files_total"></progress>
        } @else {
          <progress></progress>
        }
        <p>{{ activity() }}: {{ progressText() }}</p>
      </div>
    } @else if (dryRun.isLoading()) {
      <div class="working" role="status" data-testid="write-back-loading">
        <progress></progress>
        <p>Reading the current rating of {{ filesToRead() }}…</p>
      </div>
    }
    @if (dryRun.error()) {
      <p class="error-message">
        <app-icon name="alert" [size]="14" />
        Could not load the write-back preview.
      </p>
    } @else if (dryRun.hasValue()) {
      @if (dryRun.value().notice; as notice) {
        <p class="notice" data-testid="write-back-notice">{{ notice }}</p>
      }
      @if (dryRun.value().raw_only_notice; as notice) {
        <p class="notice" data-testid="write-back-raw-only-notice">{{ notice }}</p>
      }
      @if (outcome(); as outcome) {
        <div class="outcome">
          <p class="result" [class.failed]="!outcome.ok" data-testid="write-back-result">
            {{ outcome.summary }}
          </p>
          @if (outcome.failed.length > 0) {
            <ul class="failures" data-testid="write-back-failures">
              @for (failure of outcome.failed; track failure.path) {
                <li>
                  <span class="path">{{ failure.path }}</span>: {{ failure.error }}
                </li>
              }
            </ul>
          }
        </div>
      }
      <div class="actions" data-testid="write-back-actions">
        <p class="count" data-testid="write-back-count">
          {{ changing().length }} of {{ dryRun.value().files.length }} files change.
        </p>
        @if (confirming() === 'write') {
          <div class="confirmation" role="alertdialog" data-testid="write-back-confirmation">
            <p>
              Write ratings and color labels into {{ changing().length }} files? Only the rating and
              label change, and you can undo it.
            </p>
            <div class="confirmation-actions">
              <button
                type="button"
                class="btn btn-ghost"
                data-testid="write-back-cancel"
                (click)="confirming.set(null)"
              >
                Cancel
              </button>
              <button
                type="button"
                class="btn btn-primary"
                data-testid="write-back-confirm"
                [disabled]="working()"
                (click)="apply()"
              >
                Write to {{ changing().length }} files
              </button>
            </div>
          </div>
        } @else {
          <button
            type="button"
            class="btn btn-primary"
            data-testid="write-back-apply"
            [disabled]="working() || changing().length === 0"
            [appTooltip]="writeTooltip"
            (click)="confirming.set('write')"
          >
            Write ratings…
          </button>
        }
        @if (dryRun.value().can_undo) {
          <button
            type="button"
            class="btn"
            data-testid="write-back-undo"
            [disabled]="working()"
            [appTooltip]="undoTooltip"
            (click)="undo()"
          >
            <app-icon name="reset" [size]="14" />
            Undo write-back
          </button>
        }
        @if (confirming() === 'reset') {
          <div
            class="confirmation reset"
            role="alertdialog"
            data-testid="session-reset-confirmation"
          >
            <p>
              Reset the Session? Ratings framewise wrote are restored in the files, and all
              Overrides, fixed Groups and the Keeper budget are cleared. The analysis is kept.
            </p>
            <div class="confirmation-actions">
              <button
                type="button"
                class="btn btn-ghost"
                data-testid="session-reset-cancel"
                (click)="confirming.set(null)"
              >
                Cancel
              </button>
              <button
                type="button"
                class="btn btn-primary"
                data-testid="session-reset-confirm"
                [disabled]="working()"
                [appTooltip]="resetTooltip"
                (click)="reset()"
              >
                Reset Session
              </button>
            </div>
          </div>
        } @else {
          <button
            type="button"
            class="btn btn-ghost reset"
            data-testid="session-reset"
            [disabled]="working()"
            [appTooltip]="resetTooltip"
            (click)="confirming.set('reset')"
          >
            Reset Session…
          </button>
        }
      </div>
      <div class="files">
        <table>
          <thead>
            <tr>
              <th>File</th>
              <th>Verdict</th>
              <th>Now</th>
              <th>After</th>
            </tr>
          </thead>
          <tbody>
            @for (file of dryRun.value().files; track file.path) {
              <tr data-testid="write-back-file" [class.unchanged]="!changes(file)">
                <td class="file">
                  <span class="path">{{ file.path }}</span>
                  @if (file.written_to !== file.path) {
                    <span class="path target" data-testid="write-back-target">
                      → {{ file.written_to }}
                    </span>
                  }
                </td>
                <td>
                  <span [class]="'verdict ' + file.verdict">{{ verdictLabels[file.verdict] }}</span>
                </td>
                <td class="rating old">
                  <ng-container *ngTemplateOutlet="rating; context: { $implicit: file.old }" />
                </td>
                <td class="rating new">
                  <ng-container *ngTemplateOutlet="rating; context: { $implicit: file.new }" />
                </td>
              </tr>
            }
          </tbody>
        </table>
      </div>
    }
    <ng-template #rating let-rating>
      {{ stars(rating) }}
      @if (rating.label; as label) {
        <span class="label" data-testid="color-label">
          @if (labelColor(label); as color) {
            <span class="swatch" data-testid="color-swatch" [attr.data-color]="color"></span>
          }
          {{ label }}
        </span>
      }
    </ng-template>
  `,
  styles: `
    :host {
      display: flex;
      flex-direction: column;
      gap: var(--space-3);
      height: 100%;
      padding-bottom: var(--space-4);
      box-sizing: border-box;
      font-size: var(--text-md);
    }
    .toolbar,
    .actions {
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      gap: var(--space-3);
    }
    .toolbar {
      gap: var(--space-2);
    }
    h2 {
      margin: 0;
      font-size: var(--text-lg);
      font-weight: 600;
    }
    p {
      margin: 0;
    }
    .notice {
      padding: var(--space-2) var(--space-3);
      border: 1px solid var(--color-border);
      border-radius: var(--radius-md);
      background: var(--color-surface-1);
      color: var(--color-text-secondary);
      font-size: var(--text-sm);
    }
    .outcome {
      display: flex;
      flex-direction: column;
      gap: var(--space-2);
    }
    .result {
      display: flex;
      align-items: center;
      gap: var(--space-2);
      padding: var(--space-2) var(--space-3);
      border-radius: var(--radius-md);
      background: var(--color-keeper-tint);
      font-size: var(--text-sm);
    }
    .result::before {
      content: '';
      width: var(--space-2);
      height: var(--space-2);
      border-radius: var(--radius-pill);
      background: var(--color-keeper);
    }
    .result.failed {
      background: var(--color-error-tint);
      color: var(--color-error);
    }
    .result.failed::before {
      background: var(--color-error);
    }
    .failures {
      display: flex;
      flex-direction: column;
      gap: var(--space-1);
      margin: 0;
      padding: var(--space-2) var(--space-3) var(--space-2) var(--space-6);
      border: 1px solid var(--color-error-border);
      border-radius: var(--radius-md);
      background: var(--color-error-tint);
      color: var(--color-error);
      font-size: var(--text-sm);
    }
    .count {
      color: var(--color-text-secondary);
    }
    .reset {
      margin-left: auto;
    }
    .working {
      display: flex;
      flex-direction: column;
      gap: var(--space-2);
      padding: var(--space-2) var(--space-3);
      border: 1px solid var(--color-border);
      border-radius: var(--radius-md);
      background: var(--color-surface-1);
      color: var(--color-text-secondary);
      font-size: var(--text-sm);
    }
    .working progress {
      width: 100%;
      height: 4px;
      accent-color: var(--color-text-secondary);
    }
    .confirmation {
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      gap: var(--space-3);
      padding: var(--space-2) var(--space-3);
      border: 1px solid var(--color-border-strong);
      border-radius: var(--radius-lg);
      background: var(--color-surface-2);
      box-shadow: var(--shadow-1);
    }
    .confirmation-actions {
      display: flex;
      gap: var(--space-2);
    }
    .files {
      flex: 1;
      min-height: 0;
      overflow: auto;
      border: 1px solid var(--color-border);
      border-radius: var(--radius-lg);
      background: var(--color-surface-1);
    }
    table {
      border-collapse: collapse;
      width: 100%;
    }
    th,
    td {
      padding: var(--space-2) var(--space-3);
      border-bottom: 1px solid var(--color-border);
      text-align: left;
      white-space: nowrap;
    }
    @media (width < 600px) {
      th,
      td {
        padding-inline: var(--space-2);
      }
    }
    tbody tr:last-child td {
      border-bottom: none;
    }
    th {
      position: sticky;
      top: 0;
      z-index: 1;
      background: var(--color-surface-2);
      color: var(--color-text-muted);
      font-size: var(--text-xs);
      font-weight: 600;
      letter-spacing: 0.06em;
      text-transform: uppercase;
    }
    .file {
      white-space: normal;
      overflow-wrap: anywhere;
    }
    .path {
      font-family: var(--font-mono);
      font-size: var(--text-sm);
    }
    .target {
      display: block;
      color: var(--color-text-muted);
      font-size: var(--text-xs);
    }
    .rating {
      white-space: normal;
      font-variant-numeric: tabular-nums;
    }
    .rating.old {
      color: var(--color-text-muted);
    }
    .rating.new {
      color: var(--color-rating);
      font-weight: 600;
    }
    .label {
      display: inline-flex;
      align-items: center;
      gap: var(--space-1);
      margin-left: var(--space-1);
      color: var(--color-text);
    }
    .swatch {
      flex: none;
      width: 10px;
      height: 10px;
      border-radius: 2px;
    }
    .swatch[data-color='red'] {
      background: var(--color-label-red);
    }
    .swatch[data-color='yellow'] {
      background: var(--color-label-yellow);
    }
    .verdict {
      display: inline-flex;
      align-items: center;
      gap: var(--space-2);
    }
    .verdict::before {
      content: '';
      width: var(--space-2);
      height: var(--space-2);
      border-radius: var(--radius-pill);
    }
    .verdict.winner::before {
      background: var(--color-winner);
    }
    .verdict.keeper::before {
      background: var(--color-keeper);
    }
    .verdict.reject::before {
      background: var(--color-reject);
    }
    .verdict.unsure::before {
      background: var(--color-unsure);
    }
    .unchanged td,
    .unchanged .rating.new,
    .unchanged .label {
      color: var(--color-text-muted);
      font-weight: normal;
    }
  `,
})
export class WriteBackView {
  /** How many files the Session holds, when the Session summary is known. */
  readonly fileCount = input<number | null>(null);
  readonly back = output<void>();
  /** The Session was reset, so its Groups, Overrides and Keeper budget have changed. */
  readonly sessionReset = output<void>();

  private readonly http = inject(HttpClient);
  protected readonly dryRun = httpResource<WriteBackDryRun>(() => '/api/write-back');
  protected readonly confirming = signal<'write' | 'reset' | null>(null);
  protected readonly busy = signal(false);
  protected readonly progress = httpResource<WriteBackProgress>(() => '/api/write-back/progress');
  /** Files are being written, by this page or by a write-back still running after a reload. */
  protected readonly working = computed(
    () => this.busy() || (this.progress.hasValue() && this.progress.value().running),
  );
  protected readonly activity = signal('Writing files');
  /** The progress once the number of files to write is known. */
  protected readonly progressValue = computed(() => {
    const progress = this.progress.hasValue() ? this.progress.value() : null;
    if (progress === null || !progress.running || progress.files_total === null) {
      return null;
    }
    return { files_done: progress.files_done, files_total: progress.files_total };
  });
  protected readonly progressText = computed(() => {
    const progress = this.progressValue();
    if (progress === null) {
      return 'reading the current ratings…';
    }
    return `${progress.files_done} of ${pluralize(progress.files_total, 'file')}`;
  });
  protected readonly filesToRead = computed(() => {
    const count = this.fileCount();
    return count === null ? 'every file' : pluralize(count, 'file');
  });
  protected readonly outcome = signal<Outcome | null>(null);
  protected readonly changing = computed(() =>
    this.dryRun.hasValue() ? this.dryRun.value().files.filter((file) => this.changes(file)) : [],
  );
  protected readonly verdictLabels = VERDICT_LABELS;
  protected readonly writeTooltip: TooltipContent = {
    label: 'Write ratings',
    explanation:
      "Writes each Frame's reviewed Verdict into its files as a star rating and color label that Lightroom Classic reads on import.",
  };
  protected readonly undoTooltip: TooltipContent = {
    label: 'Undo write-back',
    explanation:
      'Restores the rating and color label each file had before framewise first wrote to it, and removes the sidecars it created; your Overrides stay.',
  };
  protected readonly resetTooltip: TooltipContent = {
    label: 'Reset Session',
    explanation:
      "Restores the ratings framewise wrote and clears every Override and the Keeper budget, so you review framewise's Proposal afresh; the analysis is kept.",
  };

  constructor() {
    effect((onCleanup) => {
      if (!this.working() || this.progress.isLoading()) {
        return;
      }
      const timer = setTimeout(() => this.progress.reload(), PROGRESS_POLL_INTERVAL_MS);
      onCleanup(() => clearTimeout(timer));
    });
  }

  protected changes(file: WriteBackFile): boolean {
    return file.old.stars !== file.new.stars || file.old.label !== file.new.label;
  }

  protected stars(rating: WriteBackRating): string {
    return rating.stars === null ? 'No rating' : `${rating.stars}★`;
  }

  /** The color a Lightroom label name stands for in the dry run's label set. */
  protected labelColor(label: string): ColorLabel | null {
    const labelSet = this.dryRun.hasValue() ? this.dryRun.value().label_set : null;
    if (labelSet?.red === label) {
      return 'red';
    }
    if (labelSet?.yellow === label) {
      return 'yellow';
    }
    return null;
  }

  protected async apply(): Promise<void> {
    await this.run('/api/write-back', 'Writing ratings', 'Wrote');
  }

  protected async undo(): Promise<void> {
    await this.run('/api/write-back/undo', 'Restoring ratings', 'Restored');
  }

  protected async reset(): Promise<void> {
    const reset = await this.run(
      '/api/session/reset',
      'Resetting the Session',
      'Reset the Session and restored',
      'Reset failed.',
    );
    if (reset) {
      this.sessionReset.emit();
    }
  }

  /** Posts to `url` and reports the outcome. Returns whether the request succeeded. */
  private async run(
    url: string,
    activity: string,
    verb: string,
    failure = 'Rating write-back failed.',
  ): Promise<boolean> {
    this.activity.set(activity);
    this.busy.set(true);
    this.confirming.set(null);
    this.progress.reload();
    try {
      const result = await firstValueFrom(this.http.post<WriteBackResult>(url, null));
      this.outcome.set({
        ok: true,
        summary: `${verb} ${pluralize(result.written.length, 'file')}.`,
        failed: result.failed,
      });
      return true;
    } catch {
      this.outcome.set({ ok: false, summary: failure, failed: [] });
      return false;
    } finally {
      this.busy.set(false);
      this.activity.set('Writing files');
      this.progress.reload();
      this.dryRun.reload();
    }
  }
}
