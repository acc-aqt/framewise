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
      gap: 12px;
      margin-top: 8px;
      font-size: 0.85rem;
    }
    label {
      display: flex;
      align-items: center;
      gap: 8px;
    }
    input:focus-visible {
      outline: 2px solid var(--color-focus);
      outline-offset: 2px;
    }
    output {
      min-width: 3ch;
      font-variant-numeric: tabular-nums;
    }
    .count {
      color: var(--color-text-secondary);
      font-variant-numeric: tabular-nums;
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
