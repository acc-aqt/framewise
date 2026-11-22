import { ChangeDetectionStrategy, Component } from '@angular/core';
import { Icon } from './icon';

@Component({
  selector: 'app-disconnected',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [Icon],
  host: { 'data-testid': 'disconnected', role: 'alert' },
  template: `
    <div class="badge">
      <app-icon name="alert" [size]="28" />
    </div>
    <h2>Lost the connection to framewise.</h2>
    <p class="explanation">
      The review server has stopped. Start it again in a terminal with
      <code>framewise review</code> and this page reconnects on its own.
    </p>
    <p class="hint">Your Overrides are kept. Reconnecting…</p>
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
      border: 1px solid var(--color-error-border);
      border-radius: var(--radius-lg);
      background: var(--color-error-tint);
      color: var(--color-error);
    }
    h2 {
      margin: 0;
      font-size: var(--text-xl);
      font-weight: 600;
    }
    p {
      margin: 0;
      max-width: 48ch;
    }
    .explanation {
      color: var(--color-text-secondary);
    }
    code {
      font-family: var(--font-mono);
      color: var(--color-text);
    }
    .hint {
      color: var(--color-text-muted);
      font-size: var(--text-sm);
    }
  `,
})
export class Disconnected {}
