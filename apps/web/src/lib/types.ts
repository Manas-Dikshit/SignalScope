export type Source =
  | "metadata"
  | "user_supplied"
  | "measured"
  | "estimated"
  | "hypothesis"
  | "unknown";

export interface Estimate {
  name: string;
  value: number | string | null;
  unit: string | null;
  source: Source;
  confidence: number | null;
  evidence: string[];
  alternatives: Estimate[];
  warnings: string[];
}

export interface RecordingMetadata {
  sample_rate: Estimate;
  center_frequency: Estimate | null;
  is_complex: boolean;
  channel_count: number;
  sample_dtype: string;
  duration_seconds: number | null;
  total_samples: number;
  extra: Record<string, unknown>;
}

export interface Recording {
  id: string;
  filename: string;
  name: string;
  format: string;
  file_size: number;
  created_at: string;
  metadata: RecordingMetadata;
  user_id: string;
}

export interface PreviewData {
  waveform: { time: number[]; real: number[]; imag: number[] };
  psd: { frequency: number[]; power: number[] };
  waterfall: {
    frequency: number[];
    time: number[];
    spectrogram: number[][];
  };
  scatter: { real: number[]; imag: number[] };
}

export interface Project {
  id: string;
  name: string;
  recording_id: string;
  recording: Recording | null;
  created_at: string;
  updated_at: string;
  parameter_estimates: Estimate[];
  status: "idle" | "analyzing" | "completed" | "failed";
}

export interface Job {
  id: string;
  status: "pending" | "running" | "completed" | "failed";
  project_id: string;
  created_at: string;
  updated_at: string;
  result: Record<string, unknown> | null;
  error: string | null;
}

export interface DashboardStats {
  recording_count: number;
  project_count: number;
  recent_recordings: Recording[];
  recent_projects: Project[];
  running_jobs: Job[];
}

export interface User {
  id: string;
  email: string;
}

export interface AuthResponse {
  user: User;
  access_token: string;
}

export interface RawIQOptions {
  dtype: string;
  layout: string;
  endian: string;
  sample_rate_hz: number | null;
  center_frequency_hz: number | null;
}

export interface WavOptions {
  stereo_mode: string;
}

export interface UploadPayload {
  file: File;
  format: "wav" | "raw_iq" | "sigmf";
  name?: string;
  raw_iq_options?: RawIQOptions;
  wav_options?: WavOptions;
  sigmf_meta?: File;
}
