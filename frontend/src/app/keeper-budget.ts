import {
  ChangeDetectionStrategy,
  Component,
  computed,
  input,
  linkedSignal,
  output,
} from '@angular/core';
import { Group } from './session-api';

@Component({
  selector: 'app-keeper-budget',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <label>
      <span>Keeper budget</span>
      <input
        type="range"
        min="0"
        max="100"
        step="5"
        data-testid="keeper-budget"
        [value]="percent()"
        (input)="percent.set(valueOf($event))"
        (change)="changeShare.emit(valueOf($event) / 100)"
      />
      <output data-testid="keeper-budget-percent">{{ percent() }}%</output>
    </label>
    <span class="count" data-testid="keeper-count">
      {{ keeperCount() }} {{ keeperCount() === 1 ? 'Keeper' : 'Keepers' }} · {{ keptCount() }} of
      {{ frameCount() }} Frames kept
    </span>
  `,
  styles: `
    :host {
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      gap: var(--space-3);
      font-size: var(--text-sm);
    }
    label {
      display: flex;
      align-items: center;
      gap: var(--space-2);
      color: var(--color-text-secondary);
    }
    input {
      width: 120px;
      margin: 0;
    }
    output {
      min-width: 4ch;
      color: var(--color-text);
      font-size: var(--text-md);
      font-weight: 600;
    }
    .count {
      color: var(--color-text-muted);
    }
  `,
})
export class KeeperBudget {
  /** The Keeper budget as a share of the Session's Frames, from 0 to 1. */
  readonly share = input.required<number>();
  readonly groups = input.required<Group[]>();
  readonly changeShare = output<number>();

  protected readonly percent = linkedSignal(() => Math.round(this.share() * 100));
  private readonly frames = computed(() => this.groups().flatMap((group) => group.frames));
  protected readonly frameCount = computed(() => this.frames().length);
  protected readonly keeperCount = computed(
    () => this.frames().filter((frame) => frame.verdict === 'keeper').length,
  );
  protected readonly keptCount = computed(
    () =>
      this.frames().filter((frame) => frame.verdict === 'winner' || frame.verdict === 'keeper')
        .length,
  );

  protected valueOf(event: Event): number {
    return Number((event.target as HTMLInputElement).value);
  }
}
