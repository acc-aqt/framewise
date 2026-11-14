import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';
import { AnalysisProgress } from './session-api';

@Component({
  selector: 'app-analysis-progress',
  changeDetection: ChangeDetectionStrategy.OnPush,
  host: { 'data-testid': 'analysis-progress', role: 'status' },
  template: `
    <progress [value]="progress().frames_done" [max]="total()"></progress>
    <p>
      Analysing: <span data-testid="frames-done">{{ progress().frames_done }}</span> Frames done,
      <span data-testid="frames-left">{{ progress().frames_left }}</span> left,
      <span data-testid="time-remaining">{{ timeRemaining() }}</span>
    </p>
  `,
  styles: `
    :host {
      display: block;
      color: var(--color-text-secondary);
      font-size: var(--text-sm);
    }
    /* Spans the whole header, which is the nearest positioned ancestor. */
    progress {
      position: absolute;
      right: 0;
      bottom: 0;
      left: 0;
      display: block;
      width: 100%;
      height: 2px;
      border: 0;
      background: var(--color-border);
      appearance: none;
    }
    progress::-webkit-progress-bar {
      background: var(--color-border);
    }
    progress::-webkit-progress-value {
      background: var(--color-text-secondary);
      transition: width var(--duration-base) var(--ease-out);
    }
    progress::-moz-progress-bar {
      background: var(--color-text-secondary);
    }
    p {
      margin: 0;
      white-space: nowrap;
    }
  `,
})
export class AnalysisProgressView {
  readonly progress = input.required<AnalysisProgress>();
  protected readonly total = computed(
    () => this.progress().frames_done + this.progress().frames_left,
  );
  protected readonly timeRemaining = computed(() => {
    const seconds = this.progress().seconds_remaining;
    if (seconds === null) {
      return 'estimating time left';
    }
    if (seconds < 60) {
      return 'less than a minute left';
    }
    return `about ${Math.ceil(seconds / 60)} min left`;
  });
}
