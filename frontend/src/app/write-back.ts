import { HttpClient, httpResource } from '@angular/common/http';
import {
  ChangeDetectionStrategy,
  Component,
  computed,
  effect,
  inject,
  output,
  signal,
} from '@angular/core';
import { firstValueFrom } from 'rxjs';
import { Icon } from './icon';
import { VERDICT_LABELS } from './proposal';
import {
  WriteBackDryRun,
  WriteBackFile,
  WriteBackProgress,
  WriteBackRating,
  WriteBackResult,
} from './session-api';

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
  imports: [Icon],
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
        <p>Reading the current rating of every file…</p>
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
      <div class="actions">
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
            (click)="undo()"
          >
            <app-icon name="reset" [size]="14" />
            Undo write-back
          </button>
        }
        @if (confirming() === 'reset') {
          <div class="confirmation" role="alertdialog" data-testid="session-reset-confirmation">
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
                (click)="reset()"
              >
                Reset Session
              </button>
            </div>
          </div>
        } @else {
          <button
            type="button"
            class="btn btn-ghost"
            data-testid="session-reset"
            [disabled]="working()"
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
              <th>Written to</th>
              <th>Verdict</th>
              <th>Now</th>
              <th>After</th>
            </tr>
          </thead>
          <tbody>
            @for (file of dryRun.value().files; track file.path) {
              <tr data-testid="write-back-file" [class.unchanged]="!changes(file)">
                <td class="path">{{ file.path }}</td>
                <td class="path">{{ file.written_to }}</td>
                <td>
                  <span [class]="'verdict ' + file.verdict">{{ verdictLabels[file.verdict] }}</span>
                </td>
                <td class="rating old">{{ describe(file.old) }}</td>
                <td class="rating new">{{ describe(file.new) }}</td>
              </tr>
            }
          </tbody>
        </table>
      </div>
    }
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
    .path {
      font-family: var(--font-mono);
      font-size: var(--text-sm);
    }
    .rating {
      font-variant-numeric: tabular-nums;
    }
    .rating.old {
      color: var(--color-text-muted);
    }
    .rating.new {
      color: var(--color-rating);
      font-weight: 600;
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
    .unchanged .rating.new {
      color: var(--color-text-muted);
      font-weight: normal;
    }
  `,
})
export class WriteBackView {
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
    return `${progress.files_done} of ${files(progress.files_total)}`;
  });
  protected readonly outcome = signal<Outcome | null>(null);
  protected readonly changing = computed(() =>
    this.dryRun.hasValue() ? this.dryRun.value().files.filter((file) => this.changes(file)) : [],
  );
  protected readonly verdictLabels = VERDICT_LABELS;

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

  protected describe(rating: WriteBackRating): string {
    const stars = rating.stars === null ? 'No rating' : `${rating.stars}★`;
    return rating.label === null ? stars : `${stars} ${rating.label}`;
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
        summary: `${verb} ${files(result.written.length)}.`,
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

function files(count: number): string {
  return count === 1 ? '1 file' : `${count} files`;
}
