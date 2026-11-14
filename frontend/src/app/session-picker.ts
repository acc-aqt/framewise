import { HttpClient } from '@angular/common/http';
import { ChangeDetectionStrategy, Component, inject, output, signal } from '@angular/core';
import { firstValueFrom } from 'rxjs';
import { Icon } from './icon';

@Component({
  selector: 'app-session-picker',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [Icon],
  template: `
    <div class="badge">
      <app-icon name="folder" [size]="28" />
    </div>
    <h2>No Session is open yet.</h2>
    <p class="explanation">A Session is all the Frames from one shoot, culled together.</p>
    <button
      type="button"
      class="btn btn-primary"
      data-testid="choose-session"
      [disabled]="choosing()"
      (click)="choose()"
    >
      <app-icon name="folder" [size]="14" />
      Choose Session folder…
    </button>
    @if (choosing()) {
      <p class="hint">Choose the folder in the Finder dialog.</p>
    }
    @if (failed()) {
      <p class="error-message" data-testid="choose-session-error">
        <app-icon name="alert" [size]="14" />
        Could not open the Session.
      </p>
    }
  `,
  styles: `
    :host {
      flex: 1;
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      gap: var(--space-3);
      padding: var(--space-6) var(--space-4);
      text-align: center;
    }
    .badge {
      display: flex;
      align-items: center;
      justify-content: center;
      width: 64px;
      height: 64px;
      margin-bottom: var(--space-2);
      border: 1px solid var(--color-border);
      border-radius: var(--radius-lg);
      background: var(--color-surface-2);
      color: var(--color-text-secondary);
    }
    h2 {
      margin: 0;
      font-size: var(--text-xl);
      font-weight: 600;
    }
    p {
      margin: 0;
    }
    .explanation {
      margin-bottom: var(--space-3);
      color: var(--color-text-muted);
    }
    .hint {
      color: var(--color-text-muted);
      font-size: var(--text-sm);
    }
  `,
})
export class SessionPicker {
  readonly opened = output<void>();

  private readonly http = inject(HttpClient);

  protected readonly choosing = signal(false);
  protected readonly failed = signal(false);

  protected async choose(): Promise<void> {
    this.choosing.set(true);
    this.failed.set(false);
    try {
      const result = await firstValueFrom(
        this.http.post<{ opened: boolean }>('/api/session/choose', null),
      );
      if (result.opened) {
        this.opened.emit();
      }
    } catch {
      this.failed.set(true);
    } finally {
      this.choosing.set(false);
    }
  }
}
