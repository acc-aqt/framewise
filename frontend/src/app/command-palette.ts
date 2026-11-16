import {
  afterNextRender,
  ChangeDetectionStrategy,
  Component,
  ElementRef,
  computed,
  input,
  output,
  signal,
  OnDestroy,
  viewChild,
} from '@angular/core';
import { Command, CommandContext, commandLabel } from './shortcuts';

/** Lists every command with its key, so the photographer can find, run and learn them. */
@Component({
  selector: 'app-command-palette',
  changeDetection: ChangeDetectionStrategy.OnPush,
  host: { 'data-testid': 'command-palette', '(click)': 'close.emit()' },
  template: `
    <div
      class="panel"
      role="dialog"
      aria-modal="true"
      aria-label="Commands"
      (click)="$event.stopPropagation()"
    >
      <input
        #search
        type="text"
        role="combobox"
        aria-controls="command-list"
        aria-expanded="true"
        aria-label="Search commands"
        placeholder="Search commands"
        autocomplete="off"
        [attr.aria-activedescendant]="highlightedId()"
        (input)="setQuery(search.value)"
        (keydown)="onKeydown($event)"
      />
      <ul id="command-list" role="listbox" aria-label="Commands">
        @for (command of matches(); track command.id; let index = $index) {
          <li
            role="option"
            data-testid="command"
            [id]="'command-' + command.id"
            [class.highlighted]="index === highlighted()"
            [attr.aria-selected]="index === highlighted()"
            [attr.aria-disabled]="!command.appliesTo(context())"
            (mouseenter)="highlighted.set(index)"
            (click)="choose(command)"
          >
            <span class="label">{{ label(command) }}</span>
            @if (command.key) {
              <kbd class="key">{{ command.key }}</kbd>
            }
          </li>
        } @empty {
          <li class="empty">No matching commands</li>
        }
      </ul>
    </div>
  `,
  styles: `
    :host {
      position: fixed;
      inset: 0;
      z-index: 50;
      display: flex;
      justify-content: center;
      align-items: flex-start;
      padding: 12vh var(--space-4) var(--space-4);
      background: var(--color-overlay);
    }
    .panel {
      display: flex;
      flex-direction: column;
      width: min(480px, 100%);
      max-height: 70vh;
      border: 1px solid var(--color-border-strong);
      border-radius: var(--radius-lg);
      background: var(--color-surface-2);
      box-shadow: var(--shadow-2);
      overflow: hidden;
    }
    input {
      padding: var(--space-3) var(--space-4);
      border: 0;
      border-bottom: 1px solid var(--color-border);
      background: transparent;
      color: var(--color-text);
      font: inherit;
      font-size: var(--text-lg);
      outline: none;
    }
    ul {
      margin: 0;
      padding: var(--space-1);
      list-style: none;
      overflow-y: auto;
    }
    li {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: var(--space-3);
      padding: var(--space-2) var(--space-3);
      border-radius: var(--radius-md);
      font-size: var(--text-md);
      cursor: pointer;
    }
    li.highlighted {
      background: var(--color-surface-3);
    }
    li[aria-disabled='true'] {
      color: var(--color-text-muted);
      cursor: default;
    }
    li.empty {
      color: var(--color-text-muted);
      cursor: default;
    }
  `,
})
export class CommandPalette implements OnDestroy {
  readonly commands = input.required<readonly Command[]>();
  readonly context = input.required<CommandContext>();
  readonly run = output<Command>();
  readonly close = output();

  private readonly query = signal('');
  protected readonly highlighted = signal(0);
  protected readonly matches = computed(() => {
    const query = this.query().trim().toLowerCase();
    return this.commands().filter((command) => this.label(command).toLowerCase().includes(query));
  });
  protected readonly highlightedId = computed(() => {
    const command = this.matches()[this.highlighted()];
    return command === undefined ? null : `command-${command.id}`;
  });

  private readonly search = viewChild.required<ElementRef<HTMLInputElement>>('search');
  private readonly focusedBefore = document.activeElement;

  constructor() {
    afterNextRender(() => this.search().nativeElement.focus());
  }

  ngOnDestroy(): void {
    if (this.focusedBefore instanceof HTMLElement && this.focusedBefore.isConnected) {
      this.focusedBefore.focus();
    }
  }

  protected label(command: Command): string {
    return commandLabel(command, this.context());
  }

  protected setQuery(query: string): void {
    this.query.set(query);
    this.highlighted.set(0);
  }

  protected onKeydown(event: KeyboardEvent): void {
    if (['ArrowDown', 'ArrowUp', 'Enter', 'Escape', 'Tab'].includes(event.key)) {
      // The palette owns these keys, so neither focus nor the Review UI's shortcuts act on them.
      event.preventDefault();
      event.stopPropagation();
    }
    switch (event.key) {
      case 'ArrowDown':
        return this.moveHighlight(1);
      case 'ArrowUp':
        return this.moveHighlight(-1);
      case 'Enter': {
        const command = this.matches()[this.highlighted()];
        return command === undefined ? undefined : this.choose(command);
      }
      case 'Escape':
        return this.close.emit();
    }
  }

  protected choose(command: Command): void {
    if (command.appliesTo(this.context())) {
      this.run.emit(command);
    }
  }

  private moveHighlight(by: 1 | -1): void {
    const last = this.matches().length - 1;
    if (last < 0) {
      return;
    }
    this.highlighted.update((index) => Math.min(last, Math.max(0, index + by)));
  }
}
