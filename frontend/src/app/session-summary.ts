import { ChangeDetectionStrategy, Component, input } from '@angular/core';
import { Icon } from './icon';
import { SessionSummary } from './session-api';

@Component({
  selector: 'app-session-summary',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [Icon],
  template: `
    <details class="file-details" data-testid="file-details">
      <summary title="File details">
        <span class="visually-hidden">File details: </span>
        <span class="frames"
          ><b data-testid="total-frames">{{ summary().total_frames }}</b> Frames</span
        ><app-icon name="chevron-down" [size]="12" />
      </summary>
      <div class="panel">
        <dl class="counts">
          <dt>RAW+JPG</dt>
          <dd data-testid="raw-jpg-count">{{ summary().raw_jpg_count }}</dd>
          <dt>JPG-only</dt>
          <dd data-testid="jpg-only-count">{{ summary().jpg_only_count }}</dd>
          <dt>Skipped</dt>
          <dd data-testid="skipped-count">{{ summary().skipped.length }}</dd>
        </dl>
        @if (summary().skipped.length > 0) {
          <p>Skipped RAW files without a matching JPG</p>
          <ul data-testid="skipped-files">
            @for (path of summary().skipped; track path) {
              <li>{{ path }}</li>
            }
          </ul>
        }
      </div>
    </details>
  `,
  styles: `
    :host {
      display: block;
    }
    .file-details {
      position: relative;
    }
    summary {
      display: inline-flex;
      align-items: center;
      gap: var(--space-1);
      border-radius: var(--radius-sm);
      color: var(--color-text-muted);
      font-size: var(--text-sm);
      white-space: nowrap;
      cursor: pointer;
      list-style: none;
    }
    summary::-webkit-details-marker {
      display: none;
    }
    summary:hover,
    .file-details[open] summary {
      color: var(--color-text);
    }
    summary b {
      color: var(--color-text);
      font-size: var(--text-md);
      font-weight: 600;
    }
    .counts {
      display: grid;
      grid-template-columns: auto auto;
      gap: var(--space-1) var(--space-4);
      margin: 0;
    }
    dt {
      color: var(--color-text-muted);
    }
    dd {
      margin: 0;
      color: var(--color-text);
      font-weight: 600;
      text-align: right;
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
      margin: var(--space-3) 0 var(--space-2);
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
