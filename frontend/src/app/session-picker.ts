import { HttpClient } from '@angular/common/http';
import { ChangeDetectionStrategy, Component, inject, output, signal } from '@angular/core';
import { firstValueFrom } from 'rxjs';

@Component({
  selector: 'app-session-picker',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <p>No Session is open yet.</p>
    <button type="button" data-testid="choose-session" [disabled]="choosing()" (click)="choose()">
      Choose Session folder…
    </button>
    @if (choosing()) {
      <p class="hint">Choose the folder in the Finder dialog.</p>
    }
    @if (failed()) {
      <p class="error" data-testid="choose-session-error">Could not open the Session.</p>
    }
  `,
  styles: `
    :host {
      display: flex;
      flex-direction: column;
      align-items: center;
      gap: 8px;
      padding: 48px 16px;
    }
    p {
      margin: 0;
    }
    button {
      padding: 6px 14px;
      border: 1px solid var(--color-border);
      border-radius: 4px;
      background: var(--color-surface);
      color: var(--color-text);
      font: inherit;
      cursor: pointer;
    }
    button:disabled {
      cursor: default;
      opacity: 0.5;
    }
    button:focus-visible {
      outline: 2px solid var(--color-focus);
      outline-offset: 2px;
    }
    .hint {
      font-size: 0.85rem;
      color: var(--color-text-muted);
    }
    .error {
      color: var(--color-error);
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
