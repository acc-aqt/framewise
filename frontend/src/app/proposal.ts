import { Frame, Group, Verdict } from './session-api';

export const VERDICTS: Verdict[] = ['winner', 'keeper', 'reject', 'unsure'];

export const VERDICT_LABELS: Record<Verdict, string> = {
  winner: 'Winner',
  keeper: 'Keeper',
  reject: 'Reject',
  unsure: 'Unsure',
};

export interface ProposalFilter {
  verdict: Verdict | null;
  reason: string | null;
}

export const NO_FILTER: ProposalFilter = { verdict: null, reason: null };

export function isFiltering(filter: ProposalFilter): boolean {
  return filter.verdict !== null || filter.reason !== null;
}

/** Each Reason code found among the Frames, with its label, sorted by label. */
export function reasonLabels(frames: Frame[]): Map<string, string> {
  const labels = new Map<string, string>();
  for (const frame of frames) {
    for (const reason of frame.reasons) {
      labels.set(reason.code, reason.label);
    }
  }
  return new Map([...labels].sort(([, first], [, second]) => first.localeCompare(second)));
}

export function matchesFilter(frame: Frame, filter: ProposalFilter): boolean {
  return (
    (filter.verdict === null || frame.verdict === filter.verdict) &&
    (filter.reason === null || frame.reasons.some((reason) => reason.code === filter.reason))
  );
}

/** A Frame is kept when it is its Group's Winner or a Keeper. */
export function isKept(frame: Frame): boolean {
  return frame.verdict === 'winner' || frame.verdict === 'keeper';
}

export function findWinner(group: Group): Frame | undefined {
  return group.frames.find((frame) => frame.verdict === 'winner');
}

export function winnerOf(group: Group): Frame {
  return findWinner(group) ?? group.frames[0];
}

/**
 * The Groups still selected once the Groups change, as when analysis or a Trash reloads them.
 * A Group stays selected while its Frames that existed before all came from one selected
 * Group, so it survives gaining Frames or a new id. A Group merged with another, or fully
 * trashed, drops out.
 */
export function stillSelected(before: Group[], selected: Group[], after: Group[]): Group[] {
  const groupBefore = new Map<number, Group>();
  for (const group of before) {
    for (const frame of group.frames) {
      groupBefore.set(frame.id, group);
    }
  }
  return after.filter((group) => {
    const earlierGroups = group.frames
      .map((frame) => groupBefore.get(frame.id))
      .filter((earlier) => earlier !== undefined);
    const first = earlierGroups[0];
    return (
      first !== undefined &&
      earlierGroups.every((earlier) => earlier === first) &&
      selected.includes(first)
    );
  });
}

export function scoreBreakdown(frame: Frame): string[] {
  const { scores } = frame;
  return [
    `Total ${score(scores.total)}`,
    `Sharpness ${score(scores.sharpness)}`,
    `Steadiness ${score(scores.steadiness)}`,
    `Exposure ${score(scores.exposure)} (${exposureNote(frame)})`,
    scores.aesthetics === null
      ? 'Aesthetics unavailable'
      : `Aesthetics ${score(scores.aesthetics)}`,
    ...(scores.face_quality === null ? [] : [`Face quality ${score(scores.face_quality)}`]),
    ...(scores.expression === null ? [] : [`Expression ${score(scores.expression)}`]),
    ...(scores.camera_rating > 0 ? [`Camera rating +${score(scores.camera_rating)}`] : []),
  ];
}

function exposureNote(frame: Frame): string {
  const { exposure_stops: stops, low_key: lowKey, high_key: highKey } = frame.signals;
  const notes = [`${stops > 0 ? '+' : ''}${stops.toFixed(1)} stops`];
  if (lowKey) {
    notes.push('low-key');
  }
  if (highKey) {
    notes.push('high-key');
  }
  return notes.join(', ');
}

function score(value: number): string {
  return value.toFixed(2);
}
