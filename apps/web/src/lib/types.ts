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

export interface RecordingMeta {
  id: string;
  recording_id: string;
  sample_rate: number | null;
  center_frequency: number | null;
  data_type: string | null;
  iq_layout: string | null;
  endian: string | null;
  channel_count: number;
  sample_width: string | null;
  is_complex: boolean;
  metadata_source: string | null;
  metadata_confidence: number | null;
  raw_metadata_json: Record<string, unknown> | null;
  created_at: string;
}

export interface Recording {
  id: string;
  original_filename: string;
  file_hash: string;
  file_size: number;
  file_format: string;
  uploaded_by: string;
  status: string;
  duration_seconds: number | null;
  total_samples: number | null;
  created_at: string;
  updated_at: string;
  metadata_entry: RecordingMeta | null;
}

export interface PreviewData {
  samples_real: number[];
  samples_imag: number[];
  sample_rate: number | null;
  total_samples: number;
  preview_count: number;
  stats: { peak_amplitude: number; rms_amplitude: number };
}

export interface Project {
  id: string;
  name: string;
  description: string | null;
  recording_id: string;
  created_by: string;
  status: string;
  selected_start_sample: number | null;
  selected_end_sample: number | null;
  created_at: string;
  updated_at: string;
}

export interface ParameterEstimate {
  id: string;
  project_id: string;
  parameter_name: string;
  value_json: Record<string, unknown>;
  value_type: string;
  confidence: number | null;
  evidence_json: Record<string, unknown> | null;
  source: string;
  created_at: string;
}

export interface Job {
  id: string;
  status: string;
  progress_percent: number;
  current_stage: string | null;
  error_message: string | null;
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
  display_name: string | null;
  role: string;
  is_active: boolean;
}

export interface AuthResponse {
  access_token: string;
  token_type: string;
  user: User;
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
