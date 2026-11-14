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
  face_quality: number | null;
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

export type ColorLabel = 'red' | 'yellow' | 'green' | 'blue' | 'purple';

/** The photographer's Override of a Frame. A field left null keeps framewise's judgement. */
export interface Override {
  verdict: Verdict | null;
  stars: number | null;
  label: ColorLabel | null;
}

/** The Override fields to change. A field sent as null is cleared; one left out is kept. */
export type OverrideChange = Partial<Override>;

export interface FaceBox {
  x: number;
  y: number;
  width: number;
  height: number;
}

/** A face in a Frame, its box a fraction of the Frame measured from the top left. */
export interface Face {
  box: FaceBox;
  eyes: 'open' | 'closed' | 'unknown';
  focus: 'sharp' | 'soft';
}

export interface Frame {
  id: number;
  jpg_path: string;
  raw_path: string | null;
  kind: 'jpg-only' | 'raw+jpg';
  camera_rating: CameraRating;
  thumbnail_url: string;
  image_url: string;
  /** The photographer's Verdict if they overrode it, otherwise framewise's. */
  verdict: Verdict;
  verdict_overridden: boolean;
  override: Override | null;
  reasons: Reason[];
  scores: Scores;
  signals: Signals;
  faces: Face[];
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
