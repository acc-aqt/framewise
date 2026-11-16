/** Counts a noun, as in "1 Frame" or "3 Frames". */
export function pluralize(count: number, noun: string): string {
  return count === 1 ? `1 ${noun}` : `${count} ${noun}s`;
}
