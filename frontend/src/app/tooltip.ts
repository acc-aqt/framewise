import { DOCUMENT } from '@angular/common';
import { Directive, ElementRef, OnDestroy, effect, inject, input } from '@angular/core';

export const TOOLTIP_DELAY_MS = 400;

/** What a tooltip says: a name, optionally the key that does the same, and a short explanation. */
export interface TooltipContent {
  label: string;
  key?: string;
  explanation?: string;
}

const GAP_PX = 6;
const EDGE_PX = 8;
let nextId = 0;

/**
 * Shows a tooltip after a short delay when its host is hovered or gets keyboard focus.
 * An explanation also describes the host to assistive technology via aria-describedby.
 */
@Directive({
  selector: '[appTooltip]',
  host: {
    '(mouseenter)': 'scheduleShow()',
    '(focus)': 'onFocus()',
    '(mouseleave)': 'hide()',
    '(blur)': 'hide()',
    '(pointerdown)': 'onPointerDown()',
    '(document:keydown.escape)': 'hide()',
  },
})
export class Tooltip implements OnDestroy {
  readonly appTooltip = input.required<string | TooltipContent>();

  private readonly host = inject<ElementRef<HTMLElement>>(ElementRef).nativeElement;
  private readonly document = inject(DOCUMENT);
  private readonly element = this.document.createElement('div');
  private timer: ReturnType<typeof setTimeout> | undefined;
  // A click focuses the host too, which shouldn't show the tooltip the click just hid.
  private pointerDown = false;

  constructor() {
    this.element.className = 'tooltip';
    this.element.setAttribute('role', 'tooltip');
    this.element.hidden = true;
    this.document.body.appendChild(this.element);

    effect(() => this.render(this.content()));
  }

  ngOnDestroy(): void {
    this.hide();
    this.element.remove();
  }

  protected scheduleShow(): void {
    clearTimeout(this.timer);
    this.timer = setTimeout(() => this.show(), TOOLTIP_DELAY_MS);
  }

  protected onFocus(): void {
    if (!this.pointerDown) {
      this.scheduleShow();
    }
    this.pointerDown = false;
  }

  protected onPointerDown(): void {
    this.pointerDown = true;
    this.hide();
  }

  protected hide(): void {
    clearTimeout(this.timer);
    this.element.hidden = true;
  }

  private content(): TooltipContent {
    const content = this.appTooltip();
    return typeof content === 'string' ? { label: content } : content;
  }

  private render({ label, key, explanation }: TooltipContent): void {
    this.element.replaceChildren();
    const name = this.document.createElement('span');
    name.className = 'tooltip-label';
    name.textContent = label;
    this.element.appendChild(name);
    if (key !== undefined) {
      const chip = this.document.createElement('kbd');
      chip.className = 'key';
      chip.textContent = key;
      this.element.appendChild(chip);
    }
    if (explanation === undefined) {
      this.host.removeAttribute('aria-describedby');
      return;
    }
    const description = this.document.createElement('span');
    description.className = 'tooltip-explanation';
    description.id = `tooltip-explanation-${nextId++}`;
    description.textContent = explanation;
    this.element.appendChild(description);
    this.host.setAttribute('aria-describedby', description.id);
  }

  private show(): void {
    this.element.hidden = false;
    const host = this.host.getBoundingClientRect();
    const tooltip = this.element.getBoundingClientRect();
    const viewportWidth = this.document.documentElement.clientWidth || window.innerWidth;
    const viewportHeight = this.document.documentElement.clientHeight || window.innerHeight;
    const centred = host.left + host.width / 2 - tooltip.width / 2;
    const left = Math.max(EDGE_PX, Math.min(centred, viewportWidth - tooltip.width - EDGE_PX));
    const below = host.bottom + GAP_PX;
    const top =
      below + tooltip.height > viewportHeight ? host.top - GAP_PX - tooltip.height : below;
    this.element.style.left = `${left}px`;
    this.element.style.top = `${Math.max(EDGE_PX, top)}px`;
  }
}
