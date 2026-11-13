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

export interface Frame {
  id: number;
  jpg_path: string;
  raw_path: string | null;
  kind: 'jpg-only' | 'raw+jpg';
  camera_rating: CameraRating;
  thumbnail_url: string;
}
