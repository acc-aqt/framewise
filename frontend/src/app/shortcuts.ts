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

/** What the Review UI is showing, which decides the commands that apply. */
export interface CommandContext {
  frameOpen: boolean;
}

/** Something the photographer can do, with the key that does it and when it applies. */
export interface Command {
  id: string;
  label: string;
  /** The key as the photographer sees it, e.g. "P" or "⌥→". */
  key?: string;
  /** The `KeyboardEvent.key` that runs the command, matched case-insensitively. */
  eventKey?: string;
  /** Whether the key is pressed with Option (Alt). */
  alt?: boolean;
  explanation?: string;
  shortcut: Shortcut;
  appliesTo: (context: CommandContext) => boolean;
}

const whenFrameOpen = (context: CommandContext): boolean => context.frameOpen;

function frameCommand(
  id: string,
  label: string,
  key: string,
  eventKey: string,
  shortcut: Shortcut,
  alt = false,
): Command {
  return { id, label, key, eventKey, alt, shortcut, appliesTo: whenFrameOpen };
}

const STAR_COMMANDS: Command[] = [1, 2, 3, 4, 5].map((stars) =>
  frameCommand(
    `stars-${stars}`,
    stars === 1 ? '1 star' : `${stars} stars`,
    String(stars),
    String(stars),
    { kind: 'stars', stars },
  ),
);

const LABEL_COMMANDS: Command[] = (
  [
    ['6', 'red', 'Red'],
    ['7', 'yellow', 'Yellow'],
    ['8', 'green', 'Green'],
    ['9', 'blue', 'Blue'],
  ] as const
).map(([key, label, name]) =>
  frameCommand(`label-${label}`, `${name} label`, key, key, { kind: 'label', label }),
);

export const COMMANDS: readonly Command[] = [
  frameCommand('keep', 'Mark as Keeper', 'P', 'p', { kind: 'keep' }),
  frameCommand('reject', 'Mark as Reject', 'X', 'x', { kind: 'reject' }),
  frameCommand('clear', 'Clear Override', 'U', 'u', { kind: 'clear' }),
  ...STAR_COMMANDS,
  frameCommand('stars-none', 'No stars', '0', '0', { kind: 'stars', stars: null }),
  ...LABEL_COMMANDS,
  frameCommand('next-frame', 'Next Frame', '→', 'ArrowRight', {
    kind: 'step',
    by: 1,
    withinGroup: false,
  }),
  frameCommand('previous-frame', 'Previous Frame', '←', 'ArrowLeft', {
    kind: 'step',
    by: -1,
    withinGroup: false,
  }),
  frameCommand(
    'next-frame-in-group',
    'Next Frame in Group',
    '⌥→',
    'ArrowRight',
    { kind: 'step', by: 1, withinGroup: true },
    true,
  ),
  frameCommand(
    'previous-frame-in-group',
    'Previous Frame in Group',
    '⌥←',
    'ArrowLeft',
    { kind: 'step', by: -1, withinGroup: true },
    true,
  ),
  frameCommand('loupe', 'Open loupe', 'E', 'e', { kind: 'loupe' }),
  frameCommand('compare', 'Compare with Winner', 'C', 'c', { kind: 'compare' }),
  frameCommand('zoom', 'Zoom Fit/100%', 'Z', 'z', { kind: 'zoom' }),
  frameCommand('close', 'Close', 'Esc', 'Escape', { kind: 'close' }),
];

export function commandById(id: string): Command {
  const command = COMMANDS.find((candidate) => candidate.id === id);
  if (command === undefined) {
    throw new Error(`Unknown command: ${id}`);
  }
  return command;
}

export function shortcutFor(event: KeyboardEvent): Shortcut | null {
  if (event.metaKey || event.ctrlKey || isTypingInto(event.target)) {
    return null;
  }
  const key = event.key.length === 1 ? event.key.toLowerCase() : event.key;
  const command = COMMANDS.find(
    (candidate) => candidate.eventKey === key && (candidate.alt ?? false) === event.altKey,
  );
  return command?.shortcut ?? null;
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
