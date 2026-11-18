import {
  ChangeDetectionStrategy,
  Component,
  ElementRef,
  computed,
  effect,
  inject,
  input,
  model,
  viewChild,
} from '@angular/core';
import { About } from './about-api';

interface InlinePart {
  kind: 'text' | 'bold' | 'code';
  text: string;
}

const INLINE_FORMATTING = /(\*\*[^*]+\*\*|`[^`]+`)/;

/** Splits a Changelog entry into plain text, **bold** and `code`, the only formatting it has. */
export function inlineParts(item: string): InlinePart[] {
  return item
    .split(INLINE_FORMATTING)
    .filter((part) => part !== '')
    .map((part) => {
      if (part.startsWith('**') && part.endsWith('**') && part.length > 4) {
        return { kind: 'bold', text: part.slice(2, -2) };
      }
      if (part.startsWith('`') && part.endsWith('`') && part.length > 2) {
        return { kind: 'code', text: part.slice(1, -1) };
      }
      return { kind: 'text', text: part };
    });
}

/** The running version, which opens a popover of the Changelog. */
@Component({
  selector: 'app-whats-new',
  changeDetection: ChangeDetectionStrategy.OnPush,
  host: {
    '(keydown.escape)': 'onEscape($event)',
    '(document:click)': 'onDocumentClick($event)',
  },
  template: `
    <button
      #trigger
      type="button"
      class="version"
      data-testid="version"
      aria-haspopup="dialog"
      [attr.aria-expanded]="open()"
      [attr.aria-label]="'framewise ' + about().version + ', What\\'s new'"
      (click)="open.update((isOpen) => !isOpen)"
    >
      {{ about().version }}
    </button>
    @if (open()) {
      <div
        #panel
        class="popover"
        tabindex="-1"
        role="dialog"
        aria-label="What's new"
        data-testid="whats-new"
      >
        <h2>What's new</h2>
        @for (entry of versions(); track entry.version) {
          <section data-testid="changelog-version">
            <h3>
              @if (entry.version; as version) {
                {{ version }} <span class="meta">{{ entry.date }}</span>
              } @else {
                Unreleased
              }
            </h3>
            @if (!entry.version) {
              <p class="meta">On main, not in a Release yet.</p>
            }
            @for (section of entry.sections; track $index) {
              @if (section.heading) {
                <h4>{{ section.heading }}</h4>
              }
              <ul>
                @for (item of section.items; track $index) {
                  <li>
                    @for (part of parts(item); track $index) {
                      @switch (part.kind) {
                        @case ('bold') {
                          <strong>{{ part.text }}</strong>
                        }
                        @case ('code') {
                          <code>{{ part.text }}</code>
                        }
                        @default {
                          {{ part.text }}
                        }
                      }
                    }
                  </li>
                }
              </ul>
            }
          </section>
        } @empty {
          <p class="meta" data-testid="no-release-notes">No release notes found.</p>
        }
      </div>
    }
  `,
  styles: `
    :host {
      position: relative;
      display: inline-flex;
    }
    .version {
      padding: 2px var(--space-1);
      border: 0;
      border-radius: var(--radius-md);
      background: none;
      color: var(--color-text-muted);
      font-family: var(--font-mono);
      font-size: var(--text-xs);
      cursor: pointer;
    }
    .version:hover,
    .version[aria-expanded='true'] {
      background: var(--color-surface-2);
      color: var(--color-text);
    }
    .popover {
      position: absolute;
      top: calc(100% + var(--space-2));
      left: 0;
      z-index: 40;
      box-sizing: border-box;
      width: min(440px, calc(100vw - 2 * var(--space-4)));
      max-height: min(70vh, 560px);
      overflow-y: auto;
      padding: var(--space-3) var(--space-4);
      border: 1px solid var(--color-border-strong);
      border-radius: var(--radius-lg);
      background: var(--color-surface-2);
      box-shadow: var(--shadow-2);
      font-size: var(--text-sm);
    }
    .popover:focus {
      outline: none;
    }
    h2 {
      margin: 0 0 var(--space-3);
      font-size: var(--text-md);
      font-weight: 600;
    }
    section + section {
      margin-top: var(--space-3);
      padding-top: var(--space-3);
      border-top: 1px solid var(--color-border);
    }
    h3 {
      margin: 0;
      font-size: var(--text-sm);
      font-weight: 600;
    }
    h4 {
      margin: var(--space-2) 0 0;
      color: var(--color-text-secondary);
      font-size: var(--text-xs);
      font-weight: 600;
    }
    p {
      margin: var(--space-1) 0 0;
    }
    ul {
      margin: var(--space-1) 0 0;
      padding-left: var(--space-4);
      color: var(--color-text-secondary);
    }
    li + li {
      margin-top: var(--space-1);
    }
    code {
      font-family: var(--font-mono);
    }
    strong {
      color: var(--color-text);
      font-weight: 600;
    }
    .meta {
      color: var(--color-text-muted);
      font-weight: 400;
    }
  `,
})
export class WhatsNew {
  readonly about = input.required<About>();
  readonly open = model(false);

  protected readonly versions = computed(() =>
    this.about().changelog.filter(
      (entry) => entry.version !== null || entry.sections.some((section) => section.items.length),
    ),
  );
  protected readonly parts = inlineParts;

  private readonly host = inject<ElementRef<HTMLElement>>(ElementRef).nativeElement;
  private readonly trigger = viewChild.required<ElementRef<HTMLButtonElement>>('trigger');
  private readonly panel = viewChild<ElementRef<HTMLElement>>('panel');

  constructor() {
    // Moves focus into the popover as it opens, so a screen reader announces the dialog.
    effect(() => this.panel()?.nativeElement.focus());
  }

  protected onEscape(event: Event): void {
    if (this.open()) {
      // Keeps the Review UI from also treating Escape as closing the open Group.
      event.stopPropagation();
      this.close();
    }
  }

  protected onDocumentClick(event: MouseEvent): void {
    if (this.open() && !this.host.contains(event.target as Node)) {
      this.close();
    }
  }

  private close(): void {
    this.open.set(false);
    this.trigger().nativeElement.focus();
  }
}
