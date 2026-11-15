import {
  ChangeDetectionStrategy,
  Component,
  ElementRef,
  computed,
  effect,
  inject,
  input,
  signal,
  viewChild,
} from '@angular/core';
import { Icon } from './icon';
import { ActiveProvider, AlternativeProvider, ProviderLineup } from './session-api';
import { Tooltip } from './tooltip';

interface CapabilityRow {
  capability: string;
  label: string;
  active: ActiveProvider | null;
  alternatives: AlternativeProvider[];
  /** What it means for the photographer that no Provider serves the Capability. */
  noneMeans: string | null;
}

const CAPABILITY_TEXTS: Record<string, { label: string; noneMeans: string | null }> = {
  // Fingerprint is mandatory, so framewise refuses to start without its Provider.
  fingerprint: { label: 'Fingerprint (grouping)', noneMeans: null },
  'face-detection': { label: 'Face detection', noneMeans: 'no faces are detected' },
  'eye-state': { label: 'Eye state', noneMeans: 'eyes count as unknown' },
  'face-quality': { label: 'Face quality', noneMeans: 'face quality is left out of the score' },
  aesthetics: { label: 'Aesthetics', noneMeans: 'aesthetics is left out of the score' },
};

const SOURCES: Record<ActiveProvider['source'], string> = {
  automatic: 'picked automatically',
  config: 'chosen in config.toml',
};

/** A gear that opens a read-only popover of the Providers that new analyses use. */
@Component({
  selector: 'app-analysis-settings',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [Icon, Tooltip],
  host: {
    '(keydown.escape)': 'onEscape($event)',
    '(document:click)': 'onDocumentClick($event)',
  },
  template: `
    <button
      #gear
      type="button"
      class="btn btn-icon btn-ghost"
      data-testid="open-analysis-settings"
      aria-label="Analysis settings"
      aria-haspopup="dialog"
      [attr.aria-expanded]="open()"
      appTooltip="Analysis settings"
      (click)="open.update((isOpen) => !isOpen)"
    >
      <app-icon name="settings" />
    </button>
    @if (open()) {
      <div
        #panel
        class="popover"
        tabindex="-1"
        role="dialog"
        aria-label="Analysis settings"
        data-testid="analysis-settings"
      >
        <h2>Analysis settings</h2>
        <dl>
          @for (row of rows(); track row.capability) {
            <div class="capability" data-testid="capability">
              <dt>{{ row.label }}</dt>
              <dd>
                @if (row.active; as active) {
                  <code>{{ active.id }}</code>
                  <span class="meta"> v{{ active.version }} · {{ sources[active.source] }}</span>
                } @else {
                  None
                  @if (row.noneMeans) {
                    <span class="meta"> · {{ row.noneMeans }}</span>
                  }
                }
              </dd>
              @if (row.alternatives.length) {
                <dd class="alternatives" data-testid="alternatives">
                  <ul>
                    @for (alternative of row.alternatives; track alternative.id) {
                      <li data-testid="alternative" [class.unavailable]="!alternative.available">
                        <code>{{ alternative.id }}</code>
                        <span class="meta"> v{{ alternative.version }}</span>
                        @if (!alternative.available) {
                          <span class="meta"> · not available on this machine</span>
                        }
                      </li>
                    }
                  </ul>
                </dd>
              }
            </div>
          }
        </dl>
        <p class="built-in" data-testid="built-in-image-maths">
          Sharpness, motion blur, exposure and low and high key come from framewise's built-in image
          maths.
        </p>
        <footer class="config">
          <p>To switch a Provider, edit</p>
          <code class="path" data-testid="config-path">{{ configPath() }}</code>
          <pre data-testid="config-example">{{ configExample() }}</pre>
          <p data-testid="config-applies">
            A change applies on the next <code>framewise review</code>, which re-analyses only the
            Frames it affects.
          </p>
        </footer>
      </div>
    }
  `,
  styles: `
    :host {
      position: relative;
      display: inline-flex;
    }
    .popover {
      position: absolute;
      top: calc(100% + var(--space-2));
      right: 0;
      z-index: 40;
      box-sizing: border-box;
      width: min(420px, calc(100vw - 2 * var(--space-4)));
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
    dl {
      display: flex;
      flex-direction: column;
      gap: var(--space-3);
      margin: 0;
    }
    dt {
      color: var(--color-text-secondary);
    }
    dd {
      margin: var(--space-1) 0 0;
      color: var(--color-text);
    }
    code {
      font-family: var(--font-mono);
    }
    .built-in {
      margin: var(--space-4) 0 0;
      padding-top: var(--space-3);
      border-top: 1px solid var(--color-border);
      color: var(--color-text-muted);
    }
    .config {
      display: flex;
      flex-direction: column;
      gap: var(--space-2);
      margin-top: var(--space-3);
      padding-top: var(--space-3);
      border-top: 1px solid var(--color-border);
      color: var(--color-text-muted);
    }
    .config p {
      margin: 0;
    }
    .path {
      overflow-wrap: anywhere;
      color: var(--color-text);
    }
    pre {
      margin: 0;
      padding: var(--space-2) var(--space-3);
      border-radius: var(--radius-md);
      background: var(--color-surface-1);
      color: var(--color-text);
      font-family: var(--font-mono);
      white-space: pre-wrap;
    }
    .meta {
      color: var(--color-text-muted);
    }
    .alternatives ul {
      margin: var(--space-1) 0 0;
      padding-left: var(--space-4);
      color: var(--color-text-secondary);
    }
    .unavailable {
      opacity: 0.55;
    }
  `,
})
export class AnalysisSettings {
  readonly providers = input.required<ProviderLineup>();
  readonly configPath = input.required<string>();

  protected readonly open = signal(false);
  protected readonly sources = SOURCES;
  protected readonly rows = computed<CapabilityRow[]>(() =>
    Object.entries(this.providers()).map(([capability, { active, alternatives }]) => ({
      capability,
      label: CAPABILITY_TEXTS[capability]?.label ?? capability,
      noneMeans: CAPABILITY_TEXTS[capability]?.noneMeans ?? null,
      active,
      alternatives,
    })),
  );

  /** Switches to an available alternative, so copying the example changes something. */
  protected readonly configExample = computed(() => {
    const [capability, id] = this.exampleChoice();
    return `[providers]\n${capability} = "${id}"`;
  });

  private readonly exampleChoice = computed((): [string, string] => {
    const providers = this.providers();
    const capabilities = ['fingerprint', ...Object.keys(providers)];
    for (const capability of capabilities) {
      const alternative = providers[capability]?.alternatives.find((other) => other.available);
      if (alternative) {
        return [capability, alternative.id];
      }
    }
    return ['fingerprint', providers['fingerprint']?.active?.id ?? '<provider-id>'];
  });

  private readonly host = inject<ElementRef<HTMLElement>>(ElementRef).nativeElement;
  private readonly gear = viewChild.required<ElementRef<HTMLButtonElement>>('gear');
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
    this.gear().nativeElement.focus();
  }
}
