import { NgTemplateOutlet } from '@angular/common';
import {
  ChangeDetectionStrategy,
  Component,
  ElementRef,
  computed,
  effect,
  inject,
  input,
  model,
  OnInit,
  signal,
  untracked,
  viewChild,
} from '@angular/core';
import { About, UpdateCheck } from './about-api';

interface InlinePart {
  kind: 'text' | 'bold' | 'code';
  text: string;
}

const SEEN_VERSION_KEY = 'framewise.whatsNewSeenVersion';
const DISMISSED_UPDATE_KEY = 'framewise.updateDismissedVersion';

function readVersion(key: string): string | null {
  try {
    return localStorage.getItem(key);
  } catch {
    return null;
  }
}

function writeVersion(key: string, version: string): void {
  try {
    localStorage.setItem(key, version);
  } catch {
    // Without browser storage the badge and the update marker only last until a reload.
  }
}

/** Whether release version `a`, such as 0.10.0, is greater than `b`, such as 0.9.0. */
function isNewer(a: string, b: string): boolean {
  const left = a.split('.').map(Number);
  const right = b.split('.').map(Number);
  for (let i = 0; i < Math.max(left.length, right.length); i++) {
    const difference = (left[i] ?? 0) - (right[i] ?? 0);
    if (difference !== 0) {
      return difference > 0;
    }
  }
  return false;
}

const INLINE_FORMATTING = /(\*\*[^*]+\*\*|`[^`]+`)/;

/** Splits a Changelog entry into plain text, **bold** and `code`, the only formatting it has. */
function inlineParts(item: string): InlinePart[] {
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

/**
 * The running version, which opens a popover of the Changelog. After an upgrade a badge marks
 * it until the photographer opens the popover. When a newer Release is available, a ring marks
 * it until dismissed, and the popover opens with how to update and what the update brings.
 */
@Component({
  selector: 'app-whats-new',
  changeDetection: ChangeDetectionStrategy.OnPush,
  host: {
    '(keydown.escape)': 'onEscape($event)',
    '(document:click)': 'onDocumentClick($event)',
  },
  imports: [NgTemplateOutlet],
  template: `
    <button
      #trigger
      type="button"
      class="version"
      data-testid="version"
      aria-haspopup="dialog"
      [attr.aria-expanded]="open()"
      [attr.aria-label]="label()"
      (click)="open.update((isOpen) => !isOpen)"
    >
      {{ about().version }}
      @if (hasUnseenChanges()) {
        <span class="badge" data-testid="whats-new-badge" aria-hidden="true"></span>
      }
      @if (showsUpdateMarker()) {
        <span class="update-marker" data-testid="update-marker" aria-hidden="true"></span>
      }
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
        @if (update(); as update) {
          <section class="update" data-testid="update-notice">
            <h3>framewise {{ update.version }} is available</h3>
            <div class="command">
              <pre><code>{{ update.command }}</code></pre>
              <button
                type="button"
                data-testid="copy-update-command"
                (click)="copyCommand(update.command)"
              >
                {{ copied() ? 'Copied' : 'Copy' }}
              </button>
            </div>
            @if (showsUpdateMarker()) {
              <button type="button" data-testid="dismiss-update" (click)="dismissUpdate()">
                Dismiss until the next Release
              </button>
            }
            @for (entry of update.releases; track entry.version) {
              <ng-container *ngTemplateOutlet="release; context: { $implicit: entry }" />
            }
          </section>
        }
        @for (entry of versions(); track entry.version) {
          <ng-container *ngTemplateOutlet="release; context: { $implicit: entry }" />
        } @empty {
          <p class="meta" data-testid="no-release-notes">No release notes found.</p>
        }
      </div>
    }
    <ng-template #release let-entry>
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
        } @else if (!entry.sections.length) {
          <p class="meta" data-testid="nothing-new-on-platform">
            Nothing new on {{ about().platform }} in this release
          </p>
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
    </ng-template>
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
      display: inline-flex;
      align-items: center;
      gap: var(--space-1);
    }
    .badge {
      width: 6px;
      height: 6px;
      border-radius: 50%;
      background: var(--color-focus);
    }
    .update-marker {
      box-sizing: border-box;
      width: 8px;
      height: 8px;
      border: 2px solid var(--color-focus);
      border-radius: 50%;
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
    .command {
      display: flex;
      align-items: flex-start;
      gap: var(--space-2);
      margin-top: var(--space-2);
    }
    pre {
      flex: 1;
      min-width: 0;
      margin: 0;
      padding: var(--space-1) var(--space-2);
      overflow-x: auto;
      border-radius: var(--radius-md);
      background: var(--color-surface-1);
      font-size: var(--text-xs);
    }
    .update button {
      padding: 2px var(--space-2);
      border: 1px solid var(--color-border-strong);
      border-radius: var(--radius-md);
      background: none;
      color: var(--color-text);
      font-size: var(--text-xs);
      cursor: pointer;
    }
    .update > button {
      margin-top: var(--space-2);
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
export class WhatsNew implements OnInit {
  readonly about = input.required<About>();
  readonly update = input<UpdateCheck['available']>(null);
  readonly open = model(false);

  /** The version at which the photographer last opened What's new. */
  private readonly seenVersion = signal<string | null>(null);
  protected readonly hasUnseenChanges = computed(() => {
    const seen = this.seenVersion();
    return seen !== null && seen !== this.about().version;
  });
  /** The update version the photographer dismissed the marker for. */
  private readonly dismissedUpdate = signal(readVersion(DISMISSED_UPDATE_KEY));
  protected readonly showsUpdateMarker = computed(() => {
    const update = this.update();
    const dismissed = this.dismissedUpdate();
    return update !== null && (dismissed === null || isNewer(update.version, dismissed));
  });
  protected readonly label = computed(
    () =>
      `framewise ${this.about().version}, What's new` +
      (this.hasUnseenChanges() ? ', unseen changes' : '') +
      (this.showsUpdateMarker() ? ', update available' : ''),
  );

  protected readonly versions = computed(() =>
    this.about().changelog.filter(
      (entry) => entry.version !== null || entry.sections.some((section) => section.items.length),
    ),
  );
  protected readonly parts = inlineParts;
  protected readonly copied = signal(false);

  private readonly host = inject<ElementRef<HTMLElement>>(ElementRef).nativeElement;
  private readonly trigger = viewChild.required<ElementRef<HTMLButtonElement>>('trigger');
  private readonly panel = viewChild<ElementRef<HTMLElement>>('panel');

  constructor() {
    // Moves focus into the popover as it opens, so a screen reader announces the dialog.
    effect(() => this.panel()?.nativeElement.focus());
    effect(() => {
      if (this.open()) {
        untracked(() => this.markSeen());
      }
    });
  }

  ngOnInit(): void {
    const seen = readVersion(SEEN_VERSION_KEY);
    // On the first run no note is new to the photographer, so no badge shows.
    if (seen === null) {
      this.markSeen();
    } else {
      this.seenVersion.set(seen);
    }
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

  protected copyCommand(command: string): void {
    navigator.clipboard?.writeText(command).then(
      () => this.copied.set(true),
      () => undefined,
    );
  }

  protected dismissUpdate(): void {
    const version = this.update()?.version;
    if (version) {
      writeVersion(DISMISSED_UPDATE_KEY, version);
      this.dismissedUpdate.set(version);
    }
  }

  private markSeen(): void {
    const version = this.about().version;
    writeVersion(SEEN_VERSION_KEY, version);
    this.seenVersion.set(version);
  }

  private close(): void {
    this.open.set(false);
    this.trigger().nativeElement.focus();
  }
}
