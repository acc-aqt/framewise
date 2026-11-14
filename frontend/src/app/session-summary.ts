import { ChangeDetectionStrategy, Component, input } from '@angular/core';
import { Icon } from './icon';
import { SessionSummary } from './session-api';

@Component({
  selector: 'app-session-summary',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [Icon],
  template: `
    <dl class="counts">
      <div>
        <dt>Frames</dt>
        <dd data-testid="total-frames">{{ summary().total_frames }}</dd>
      </div>
      <div>
        <dt>JPG-only</dt>
        <dd data-testid="jpg-only-count">{{ summary().jpg_only_count }}</dd>
      </div>
      <div>
        <dt>RAW+JPG</dt>
        <dd data-testid="raw-jpg-count">{{ summary().raw_jpg_count }}</dd>
      </div>
      <div>
        <dt>
          @if (summary().skipped.length > 0) {
            <details class="skipped">
              <summary title="Skipped RAW files without a matching JPG">
                Skipped<app-icon name="chevron-down" [size]="12" />
              </summary>
              <div class="panel">
                <p>Skipped RAW files without a matching JPG</p>
                <ul data-testid="skipped-files">
                  @for (path of summary().skipped; track path) {
                    <li>{{ path }}</li>
                  }
                </ul>
              </div>
            </details>
          } @else {
            Skipped
          }
        </dt>
        <dd data-testid="skipped-count">{{ summary().skipped.length }}</dd>
      </div>
    </dl>
  `,
  styles: `
    :host {
      display: block;
    }
    .counts {
      display: flex;
      flex-wrap: wrap;
      gap: var(--space-4);
      margin: 0;
    }
    .counts > div {
      display: flex;
      flex-direction: row-reverse;
      align-items: baseline;
      gap: var(--space-1);
    }
    dt {
      color: var(--color-text-muted);
      font-size: var(--text-sm);
    }
    dd {
      margin: 0;
      font-size: var(--text-md);
      font-weight: 600;
    }
    .skipped {
      position: relative;
    }
    summary {
      display: inline-flex;
      align-items: center;
      gap: var(--space-1);
      border-radius: var(--radius-sm);
      cursor: pointer;
      list-style: none;
    }
    summary::-webkit-details-marker {
      display: none;
    }
    summary:hover,
    .skipped[open] summary {
      color: var(--color-text);
    }
    .panel {
      position: absolute;
      top: calc(100% + var(--space-2));
      left: 0;
      z-index: 10;
      width: max-content;
      max-width: min(480px, 80vw);
      max-height: 320px;
      overflow: auto;
      padding: var(--space-3);
      border: 1px solid var(--color-border-strong);
      border-radius: var(--radius-md);
      background: var(--color-surface-2);
      box-shadow: var(--shadow-2);
      color: var(--color-text-secondary);
    }
    .panel p {
      margin: 0 0 var(--space-2);
      color: var(--color-text-muted);
    }
    ul {
      margin: 0;
      padding: 0;
      list-style: none;
      font-family: var(--font-mono);
      font-size: var(--text-xs);
      line-height: 1.6;
    }
  `,
})
export class SessionSummaryView {
  readonly summary = input.required<SessionSummary>();
}
