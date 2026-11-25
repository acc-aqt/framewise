export interface ChangelogSection {
  /** The subheading, or null for the entries before any subheading. */
  heading: string | null;
  /** Entries in plain text, with **bold** and `code` as the only formatting. */
  items: string[];
}

export interface ChangelogVersion {
  /** Null for the changes not yet in a Release. */
  version: string | null;
  /** The Release date as YYYY-MM-DD, or null for Unreleased. */
  date: string | null;
  sections: ChangelogSection[];
}

export interface About {
  version: string;
  /** The photographer's platform: macOS, Linux or Windows. */
  platform: string;
  /**
   * Newest first, with only the entries for the platform. Empty when the Changelog is missing
   * or out of shape.
   */
  changelog: ChangelogVersion[];
}

export interface UpdateCheck {
  /** Null when there is no update to show, including when the check is off or failed. */
  available: {
    /** The newest Release. */
    version: string;
    /** The exact command to update this install on this platform. */
    command: string;
    /** Every Release newer than the running one, newest first, filtered to the platform. */
    releases: ChangelogVersion[];
  } | null;
}
