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

export function matchesFilter(frame: Frame, filter: ProposalFilter): boolean {
  return (
    (filter.verdict === null || frame.verdict === filter.verdict) &&
    (filter.reason === null || frame.reasons.some((reason) => reason.code === filter.reason))
  );
}

export function winnerOf(group: Group): Frame {
  return group.frames.find((frame) => frame.verdict === 'winner') ?? group.frames[0];
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
