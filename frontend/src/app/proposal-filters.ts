import { ChangeDetectionStrategy, Component, computed, input, model } from '@angular/core';
import { Icon } from './icon';
import { NO_FILTER, ProposalFilter, VERDICT_LABELS, VERDICTS } from './proposal';
import { Group, Verdict } from './session-api';

interface ReasonOption {
  code: string;
  label: string;
  count: number;
}

@Component({
  selector: 'app-proposal-filters',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [Icon],
  template: `
    <label class="filter" [class.active]="filter().verdict !== null">
      <span class="visually-hidden">Verdict</span>
      <select data-testid="verdict-filter" (change)="setVerdict($event)">
        <option value="" [selected]="filter().verdict === null">All Verdicts</option>
        @for (option of verdictOptions(); track option.verdict) {
          <option [value]="option.verdict" [selected]="filter().verdict === option.verdict">
            {{ option.label }} ({{ option.count }})
          </option>
        }
      </select>
      <app-icon class="chevron" name="chevron-down" [size]="14" />
    </label>
    <label class="filter" [class.active]="filter().reason !== null">
      <span class="visually-hidden">Reason</span>
      <select data-testid="reason-filter" (change)="setReason($event)">
        <option value="" [selected]="filter().reason === null">All Reasons</option>
        @for (option of reasonOptions(); track option.code) {
          <option [value]="option.code" [selected]="filter().reason === option.code">
            {{ option.label }} ({{ option.count }})
          </option>
        }
      </select>
      <app-icon class="chevron" name="chevron-down" [size]="14" />
    </label>
  `,
  styles: `
    :host {
      display: flex;
      align-items: center;
      gap: var(--space-2);
      padding: var(--space-3) 0;
    }
    .filter {
      position: relative;
      display: inline-flex;
      align-items: center;
    }
    select {
      height: var(--control-height);
      padding: 0 calc(var(--space-2) + 14px + var(--space-2)) 0 var(--space-3);
      border: 1px solid var(--color-border);
      border-radius: var(--radius-md);
      background: var(--color-surface-1);
      color: var(--color-text-secondary);
      font: inherit;
      font-size: var(--text-sm);
      appearance: none;
      cursor: pointer;
      transition:
        background-color var(--duration-fast) var(--ease-out),
        border-color var(--duration-fast) var(--ease-out),
        color var(--duration-fast) var(--ease-out);
    }
    select:hover {
      border-color: var(--color-border-strong);
    }
    select:focus-visible {
      outline: 2px solid var(--color-focus);
      outline-offset: 2px;
    }
    .active select {
      border-color: var(--color-border-strong);
      background: var(--color-surface-3);
      color: var(--color-text);
      font-weight: 600;
    }
    .chevron {
      position: absolute;
      right: var(--space-2);
      display: flex;
      color: var(--color-text-muted);
      pointer-events: none;
    }
    .active .chevron {
      color: var(--color-text);
    }
    .visually-hidden {
      position: absolute;
      width: 1px;
      height: 1px;
      overflow: hidden;
      clip-path: inset(50%);
      white-space: nowrap;
    }
  `,
})
export class ProposalFilters {
  readonly groups = input.required<Group[]>();
  readonly filter = model<ProposalFilter>(NO_FILTER);

  private readonly frames = computed(() => this.groups().flatMap((group) => group.frames));
  protected readonly verdictOptions = computed(() =>
    VERDICTS.map((verdict) => ({
      verdict,
      label: VERDICT_LABELS[verdict],
      count: this.frames().filter((frame) => frame.verdict === verdict).length,
    })),
  );
  protected readonly reasonOptions = computed(() => {
    const options = new Map<string, ReasonOption>();
    for (const frame of this.frames()) {
      for (const reason of frame.reasons) {
        const count = (options.get(reason.code)?.count ?? 0) + 1;
        options.set(reason.code, { code: reason.code, label: reason.label, count });
      }
    }
    return [...options.values()].sort((first, second) => first.label.localeCompare(second.label));
  });

  protected setVerdict(event: Event): void {
    const value = (event.target as HTMLSelectElement).value;
    this.filter.update((filter) => ({ ...filter, verdict: (value || null) as Verdict | null }));
  }

  protected setReason(event: Event): void {
    const value = (event.target as HTMLSelectElement).value;
    this.filter.update((filter) => ({ ...filter, reason: value || null }));
  }
}
