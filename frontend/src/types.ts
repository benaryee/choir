export type Stage =
  | "uploading"
  | "processing"
  | "reading_score"
  | "generating_audio"
  | "ready";

export const STAGE_ORDER: Stage[] = [
  "uploading",
  "processing",
  "reading_score",
  "generating_audio",
  "ready",
];

export const STAGE_LABELS: Record<Stage, string> = {
  uploading: "Uploading",
  processing: "Processing",
  reading_score: "Reading score",
  generating_audio: "Generating audio",
  ready: "Ready",
};

export type JobStatus =
  | "queued"
  | "running"
  | "needs_review"
  | "succeeded"
  | "failed";

export type Voice = "soprano" | "alto" | "tenor" | "bass" | "full";

export const VOICES: Voice[] = ["soprano", "alto", "tenor", "bass", "full"];

export const VOICE_LABELS: Record<Voice, string> = {
  soprano: "Soprano",
  alto: "Alto",
  tenor: "Tenor",
  bass: "Bass",
  full: "Full Choir",
};

export const VOICE_COLORS: Record<Voice, string> = {
  soprano: "#e11d48",
  alto: "#7c3aed",
  tenor: "#0891b2",
  bass: "#15803d",
  full: "#d97706",
};

export interface DetectedPart {
  id: string;
  label: string;
  suggested_voice: Voice | null;
  confidence: number;
}

export interface JobResult {
  musicxml_url: string | null;
  audio: Partial<Record<Voice, string>>;
  solfa: Partial<Record<Voice, string>>;
  solfa_combined_url: string | null;
}

export interface Job {
  id: string;
  status: JobStatus;
  stage: Stage;
  progress: number;
  filename: string;
  page_count: number;
  omr_method: string | null;
  omr_confidence: number | null;
  detected_parts: DetectedPart[];
  page_image_urls: string[];
  result: JobResult;
  error: string | null;
  created_at: number;
  updated_at: number;
}

export interface UploadResponse {
  job_id: string;
  status: JobStatus;
  stage: Stage;
}
