import { HttpClient, httpResource } from '@angular/common/http';
import {
  ChangeDetectionStrategy,
  Component,
  computed,
  inject,
  output,
  signal,
} from '@angular/core';
import { firstValueFrom } from 'rxjs';
import { VERDICT_LABELS } from './proposal';
import { WriteBackDryRun, WriteBackFile, WriteBackRating, WriteBackResult } from './session-api';

interface Outcome {
  summary: string;
  failed: WriteBackResult['failed'];
}

@Component({
  selector: 'app-write-back',
  changeDetection: ChangeDetectionStrategy.OnPush,
  host: { 'data-testid': 'write-back' },
  template: `
    <div class="toolbar">
      <button type="button" data-testid="back-from-write-back" (click)="back.emit()">
        ← All Groups
      </button>
      <h2>Rating write-back</h2>
    </div>
    @if (dryRun.error()) {
      <p class="error">Could not load the write-back preview.</p>
    } @else if (dryRun.hasValue()) {
      @if (dryRun.value().notice; as notice) {
        <p class="notice" data-testid="write-back-notice">{{ notice }}</p>
      }
      @if (outcome(); as outcome) {
        <div class="outcome">
          <p data-testid="write-back-result">{{ outcome.summary }}</p>
          @if (outcome.failed.length > 0) {
            <ul class="error" data-testid="write-back-failures">
              @for (failure of outcome.failed; track failure.path) {
                <li>{{ failure.path }}: {{ failure.error }}</li>
              }
            </ul>
          }
        </div>
      }
      <div class="actions">
        <p data-testid="write-back-count">
          {{ changing().length }} of {{ dryRun.value().files.length }} files change.
        </p>
        @if (confirming()) {
          <div class="confirmation" role="alertdialog" data-testid="write-back-confirmation">
            <p>
              Write ratings and color labels into {{ changing().length }} files? Only the rating and
              label change, and you can undo it.
            </p>
            <button
              type="button"
              class="primary"
              data-testid="write-back-confirm"
              [disabled]="busy()"
              (click)="apply()"
            >
              Write to {{ changing().length }} files
            </button>
            <button type="button" data-testid="write-back-cancel" (click)="confirming.set(false)">
              Cancel
            </button>
          </div>
        } @else {
          <button
            type="button"
            data-testid="write-back-apply"
            [disabled]="busy() || changing().length === 0"
            (click)="confirming.set(true)"
          >
            Write ratings…
          </button>
        }
        @if (dryRun.value().can_undo) {
          <button type="button" data-testid="write-back-undo" [disabled]="busy()" (click)="undo()">
            Undo write-back
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
                <td>{{ file.path }}</td>
                <td>{{ file.written_to }}</td>
                <td>{{ verdictLabels[file.verdict] }}</td>
                <td>{{ describe(file.old) }}</td>
                <td>{{ describe(file.new) }}</td>
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
      height: 100%;
      font-size: 0.85rem;
    }
    .toolbar,
    .actions,
    .confirmation {
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      gap: 12px;
    }
    .toolbar {
      padding-bottom: 8px;
    }
    h2 {
      margin: 0;
      font-size: 1rem;
    }
    p {
      margin: 0;
    }
    .notice {
      color: var(--color-unsure);
      padding-bottom: 8px;
    }
    .outcome {
      padding-bottom: 8px;
    }
    .actions {
      padding-bottom: 8px;
    }
    .confirmation {
      padding: 8px 12px;
      border: 1px solid var(--color-unsure);
      border-radius: 4px;
    }
    button {
      padding: 4px 10px;
      border: 1px solid var(--color-border);
      border-radius: 4px;
      background: var(--color-surface);
      color: var(--color-text);
      font: inherit;
      cursor: pointer;
    }
    button.primary {
      border-color: var(--color-unsure);
    }
    button:disabled {
      cursor: default;
      opacity: 0.5;
    }
    button:focus-visible {
      outline: 2px solid var(--color-focus);
      outline-offset: 2px;
    }
    .files {
      flex: 1;
      min-height: 0;
      overflow: auto;
    }
    table {
      border-collapse: collapse;
      width: 100%;
    }
    th,
    td {
      padding: 4px 8px;
      text-align: left;
      border-bottom: 1px solid var(--color-border);
    }
    th {
      position: sticky;
      top: 0;
      background: var(--color-background);
      color: var(--color-text-muted);
      font-weight: normal;
    }
    .unchanged {
      color: var(--color-text-muted);
    }
    .error {
      color: var(--color-error);
    }
    ul {
      margin: 4px 0 0;
      padding-left: 16px;
    }
  `,
})
export class WriteBackView {
  readonly back = output<void>();

  private readonly http = inject(HttpClient);
  protected readonly dryRun = httpResource<WriteBackDryRun>(() => '/api/write-back');
  protected readonly confirming = signal(false);
  protected readonly busy = signal(false);
  protected readonly outcome = signal<Outcome | null>(null);
  protected readonly changing = computed(() =>
    this.dryRun.hasValue() ? this.dryRun.value().files.filter((file) => this.changes(file)) : [],
  );
  protected readonly verdictLabels = VERDICT_LABELS;

  protected changes(file: WriteBackFile): boolean {
    return file.old.stars !== file.new.stars || file.old.label !== file.new.label;
  }

  protected describe(rating: WriteBackRating): string {
    const stars = rating.stars === null ? 'No rating' : `${rating.stars}★`;
    return rating.label === null ? stars : `${stars} ${rating.label}`;
  }

  protected apply(): Promise<void> {
    return this.run('/api/write-back', 'Wrote');
  }

  protected undo(): Promise<void> {
    return this.run('/api/write-back/undo', 'Restored');
  }

  private async run(url: string, verb: string): Promise<void> {
    this.busy.set(true);
    this.confirming.set(false);
    try {
      const result = await firstValueFrom(this.http.post<WriteBackResult>(url, null));
      this.outcome.set({
        summary: `${verb} ${files(result.written.length)}.`,
        failed: result.failed,
      });
    } catch {
      this.outcome.set({ summary: 'Rating write-back failed.', failed: [] });
    } finally {
      this.busy.set(false);
      this.dryRun.reload();
    }
  }
}

function files(count: number): string {
  return count === 1 ? '1 file' : `${count} files`;
}
