export interface SessionSummary {
  root: string;
  total_frames: number;
  jpg_only_count: number;
  raw_jpg_count: number;
  skipped: string[];
}

export interface CameraRating {
  stars: number | null;
  label: string | null;
}

export type Verdict = 'winner' | 'keeper' | 'reject' | 'unsure';

export interface Reason {
  code: string;
  label: string;
  text: string;
}

export interface Scores {
  sharpness: number;
  steadiness: number;
  exposure: number;
  aesthetics: number | null;
  total: number;
}

export interface Signals {
  sharpness: number;
  motion_blur: number;
  exposure_stops: number;
  low_key: boolean;
  high_key: boolean;
  aesthetics: number | null;
}

export interface Frame {
  id: number;
  jpg_path: string;
  raw_path: string | null;
  kind: 'jpg-only' | 'raw+jpg';
  camera_rating: CameraRating;
  thumbnail_url: string;
  verdict: Verdict;
  reasons: Reason[];
  scores: Scores;
  signals: Signals;
}

export interface Group {
  id: number;
  frames: Frame[];
}

export interface AnalysisProgress {
  frames_done: number;
  frames_left: number;
  seconds_remaining: number | null;
}
