import { ColorLabel, Group } from './session-api';

/** What a key does in an open Group, following Lightroom Classic's shortcuts. */
export type Shortcut =
  | { kind: 'stars'; stars: number | null }
  | { kind: 'label'; label: ColorLabel }
  | { kind: 'keep' }
  | { kind: 'reject' }
  | { kind: 'clear' }
  | { kind: 'step'; by: 1 | -1; withinGroup: boolean }
  | { kind: 'loupe' }
  | { kind: 'compare' }
  | { kind: 'zoom' }
  | { kind: 'close' };

const LABEL_KEYS: Record<string, ColorLabel> = {
  '6': 'red',
  '7': 'yellow',
  '8': 'green',
  '9': 'blue',
};

const LETTER_SHORTCUTS: Record<string, Shortcut> = {
  p: { kind: 'keep' },
  x: { kind: 'reject' },
  u: { kind: 'clear' },
  e: { kind: 'loupe' },
  c: { kind: 'compare' },
  z: { kind: 'zoom' },
};

export function shortcutFor(event: KeyboardEvent): Shortcut | null {
  if (event.metaKey || event.ctrlKey || isTypingInto(event.target)) {
    return null;
  }
  if (event.key === 'ArrowRight' || event.key === 'ArrowLeft') {
    return { kind: 'step', by: event.key === 'ArrowRight' ? 1 : -1, withinGroup: event.altKey };
  }
  if (event.altKey) {
    return null;
  }
  if (event.key === 'Escape') {
    return { kind: 'close' };
  }
  if (/^[0-5]$/.test(event.key)) {
    const stars = Number(event.key);
    return { kind: 'stars', stars: stars === 0 ? null : stars };
  }
  if (event.key in LABEL_KEYS) {
    return { kind: 'label', label: LABEL_KEYS[event.key] };
  }
  return LETTER_SHORTCUTS[event.key.toLowerCase()] ?? null;
}

/**
 * The id of the Frame `by` steps from `frameId`, in the order the Groups show their Frames.
 * Stops at the first and last Frame rather than wrapping around.
 */
export function stepFrom(
  groups: Group[],
  frameId: number,
  by: 1 | -1,
  withinGroup: boolean,
): number {
  const frames = withinGroup
    ? (groups.find((group) => group.frames.some((frame) => frame.id === frameId))?.frames ?? [])
    : groups.flatMap((group) => group.frames);
  const index = frames.findIndex((frame) => frame.id === frameId);
  if (index === -1) {
    return frameId;
  }
  return frames[Math.min(frames.length - 1, Math.max(0, index + by))].id;
}

function isTypingInto(target: EventTarget | null): boolean {
  return (
    target instanceof HTMLInputElement ||
    target instanceof HTMLSelectElement ||
    target instanceof HTMLTextAreaElement
  );
}
