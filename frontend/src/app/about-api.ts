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
  /** Newest first. Empty when the Changelog is missing or out of shape. */
  changelog: ChangelogVersion[];
}
