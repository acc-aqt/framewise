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
      margin-top: 0.75rem;
      font-size: 0.85rem;
      color: var(--color-text-secondary);
    }
    progress {
      width: 100%;
      max-width: 24rem;
    }
    p {
      margin: 0.25rem 0 0;
      font-variant-numeric: tabular-nums;
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
