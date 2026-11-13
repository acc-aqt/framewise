import { ChangeDetectionStrategy, Component, input } from '@angular/core';
import { SessionSummary } from './session-api';

@Component({
  selector: 'app-session-summary',
  changeDetection: ChangeDetectionStrategy.OnPush,
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
        <dt>Skipped</dt>
        <dd data-testid="skipped-count">{{ summary().skipped.length }}</dd>
      </div>
    </dl>
    @if (summary().skipped.length > 0) {
      <details class="skipped">
        <summary>Skipped RAW files without a matching JPG</summary>
        <ul data-testid="skipped-files">
          @for (path of summary().skipped; track path) {
            <li>{{ path }}</li>
          }
        </ul>
      </details>
    }
  `,
  styles: `
    :host {
      display: block;
    }
    .counts {
      display: flex;
      flex-wrap: wrap;
      gap: 1.5rem;
      margin: 0;
    }
    .counts div {
      display: flex;
      flex-direction: column-reverse;
    }
    dt {
      font-size: 0.75rem;
      color: #9aa0a6;
      text-transform: uppercase;
      letter-spacing: 0.05em;
    }
    dd {
      margin: 0;
      font-size: 1.5rem;
      font-variant-numeric: tabular-nums;
    }
    .skipped {
      margin-top: 0.5rem;
      font-size: 0.85rem;
      color: #c4c7c5;
    }
  `,
})
export class SessionSummaryView {
  readonly summary = input.required<SessionSummary>();
}
