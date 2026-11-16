import { pluralize } from './pluralize';
import { ColorLabel, Group } from './session-api';

/**
 * What a command does. The keyed ones follow Lightroom Classic's shortcuts; the rest run
 * only from the command palette.
 */
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
  | { kind: 'close' }
  | { kind: 'allGroups' }
  | { kind: 'merge'; by: -1 | 1 }
  | { kind: 'splitHere' }
  | { kind: 'move'; by: -1 | 1 }
  | { kind: 'makeWinner' }
  | { kind: 'trash' }
  | { kind: 'trashGroup' }
  | { kind: 'trashGroups' }
  | { kind: 'writeBack' };

/** What the Review UI is showing, which decides the commands that apply. */
export interface CommandContext {
  frameOpen: boolean;
  hasPreviousGroup: boolean;
  hasNextGroup: boolean;
  /** Whether the current Frame is not its Group's first, so the Group can be split there. */
  canSplitHere: boolean;
  /** Whether the current Frame is not already its Group's Winner. */
  canMakeWinner: boolean;
  /** How many Groups are selected in All Groups. */
  selectedGroupCount: number;
  writeBackAvailable: boolean;
}

/** Something the photographer can do, with the key that does it and when it applies. */
export interface Command {
  id: string;
  label: string;
  /** The label once the context is known, such as one counting what the command acts on. */
  contextLabel?: (context: CommandContext) => string;
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

function paletteCommand(
  id: string,
  label: string,
  shortcut: Shortcut,
  appliesTo: (context: CommandContext) => boolean,
): Command {
  return { id, label, shortcut, appliesTo };
}

const STAR_COMMANDS: Command[] = [1, 2, 3, 4, 5].map((stars) =>
  frameCommand(`stars-${stars}`, pluralize(stars, 'star'), String(stars), String(stars), {
    kind: 'stars',
    stars,
  }),
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
  paletteCommand('all-groups', 'All Groups', { kind: 'allGroups' }, whenFrameOpen),
  paletteCommand(
    'merge-previous',
    'Merge with previous',
    { kind: 'merge', by: -1 },
    (context) => context.hasPreviousGroup,
  ),
  paletteCommand(
    'merge-next',
    'Merge with next',
    { kind: 'merge', by: 1 },
    (context) => context.hasNextGroup,
  ),
  paletteCommand(
    'split-here',
    'Split here',
    { kind: 'splitHere' },
    (context) => context.canSplitHere,
  ),
  paletteCommand(
    'move-previous',
    'Move to previous Group',
    { kind: 'move', by: -1 },
    (context) => context.hasPreviousGroup,
  ),
  paletteCommand(
    'move-next',
    'Move to next Group',
    { kind: 'move', by: 1 },
    (context) => context.hasNextGroup,
  ),
  {
    id: 'make-winner',
    label: 'Make Winner',
    key: 'W',
    eventKey: 'w',
    shortcut: { kind: 'makeWinner' },
    appliesTo: (context) => context.canMakeWinner,
  },
  frameCommand('trash', 'Trash Frame', '⌫', 'Backspace', { kind: 'trash' }),
  paletteCommand('trash-group', 'Trash Group', { kind: 'trashGroup' }, whenFrameOpen),
  {
    id: 'trash-groups',
    label: 'Trash selected Groups',
    contextLabel: ({ selectedGroupCount: count }) =>
      count === 0 ? 'Trash selected Groups' : `Trash ${pluralize(count, 'selected Group')}`,
    shortcut: { kind: 'trashGroups' },
    appliesTo: (context) => context.selectedGroupCount > 0,
  },
  paletteCommand(
    'write-back',
    'Rating write-back',
    { kind: 'writeBack' },
    (context) => context.writeBackAvailable,
  ),
];

export function commandById(id: string): Command {
  const command = COMMANDS.find((candidate) => candidate.id === id);
  if (command === undefined) {
    throw new Error(`Unknown command: ${id}`);
  }
  return command;
}

export function commandLabel(command: Command, context: CommandContext): string {
  return command.contextLabel?.(context) ?? command.label;
}

const IS_MAC = typeof navigator !== 'undefined' && /Mac|iPhone|iPad/.test(navigator.userAgent);

/** The key that opens the command palette, as the photographer sees it. */
export const PALETTE_KEY = IS_MAC ? '⌘K' : 'Ctrl+K';

export function isPaletteKey(event: KeyboardEvent): boolean {
  return (event.metaKey || event.ctrlKey) && !event.altKey && event.key.toLowerCase() === 'k';
}

export function shortcutFor(event: KeyboardEvent): Shortcut | null {
  if (event.metaKey || event.ctrlKey || isTypingInto(event.target)) {
    return null;
  }
  // Delete trashes like Backspace, as in Lightroom Classic.
  const key =
    event.key === 'Delete'
      ? 'Backspace'
      : event.key.length === 1
        ? event.key.toLowerCase()
        : event.key;
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

/**
 * The id of the Frame to show once the Frames in `trashedIds` have left the Session: the
 * current Frame if it stays, else the next Frame left in its Group, else the previous one,
 * else the first Frame of the next Group. Null returns to All Groups.
 */
export function frameAfterTrash(
  groups: Group[],
  currentId: number,
  trashedIds: readonly number[],
): number | null {
  const trashed = new Set(trashedIds);
  if (!trashed.has(currentId)) {
    return currentId;
  }
  const index = groups.findIndex((group) => group.frames.some((frame) => frame.id === currentId));
  if (index === -1) {
    return null;
  }
  const frames = groups[index].frames;
  const at = frames.findIndex((frame) => frame.id === currentId);
  const left = (candidates: typeof frames) => candidates.find((frame) => !trashed.has(frame.id));
  const next =
    left(frames.slice(at + 1)) ??
    left(frames.slice(0, at).reverse()) ??
    groups
      .slice(index + 1)
      .flatMap((group) => group.frames)
      .find((frame) => !trashed.has(frame.id));
  return next?.id ?? null;
}

function isTypingInto(target: EventTarget | null): boolean {
  return (
    target instanceof HTMLInputElement ||
    target instanceof HTMLSelectElement ||
    target instanceof HTMLTextAreaElement
  );
}
