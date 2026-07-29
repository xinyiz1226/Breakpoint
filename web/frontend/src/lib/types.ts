export type JobStatus = "queued" | "running" | "succeeded" | "failed" | "cancelled";

export interface User {
  id: string;
  email: string;
  role: "user" | "admin";
  is_active: boolean;
  is_verified: boolean;
  created_at: string;
}

export interface Project {
  id: string;
  owner_id: string;
  name: string;
  created_at: string;
  updated_at: string;
  has_video: boolean;
  video_asset_status:
    | "upload_initiated"
    | "finalizing"
    | "uploaded"
    | "upload_aborted"
    | "cleanup_pending"
    | null;
}

export interface Quota {
  monthly_analysis_seconds_limit: number;
  monthly_analysis_seconds_used: number;
  monthly_analysis_seconds_remaining: number;
  max_active_analysis_jobs: number;
  active_analysis_job_count: number;
  storage_bytes_limit: number;
  storage_bytes_used: number;
  storage_bytes_remaining: number;
}

export interface AnalysisJob {
  id: string;
  project_id: string;
  video_asset_id: string;
  status: JobStatus;
  progress: number;
  current_step: string | null;
  report_object_key: string | null;
  failure_summary: string | null;
  event_version: number;
  cancel_requested_at: string | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
}

export interface ExportSelection {
  rally_id: string;
  start: number;
  end: number;
}

export interface ExportJob {
  id: string;
  project_id: string;
  status: JobStatus;
  progress: number;
  current_step: string | null;
  event_version: number;
  cancel_requested_at: string | null;
  selection_snapshot: ExportSelection[];
  output_object_key: string | null;
  output_expires_at: string | null;
  failure_summary: string | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
}

export interface JobEvent {
  id: string;
  status: JobStatus;
  progress: number;
  current_step: string | null;
  failure_summary: string | null;
  finished_at: string | null;
}

export interface RallyEdit {
  included: boolean;
  adjusted_start: number | null;
  adjusted_end: number | null;
}

export interface Rally {
  id: string;
  source_index: number;
  start: number;
  end: number;
  score: number;
  features: Record<string, unknown>;
  players: Record<string, unknown> | null;
  report_version: string;
  edit: RallyEdit;
}

export interface UploadPartUrl {
  part_number: number;
  url: string;
  content_length_bytes: number;
}

export interface UploadInitiate {
  video_asset_id: string;
  object_key: string;
  upload_id: string;
  part_urls: UploadPartUrl[];
  expires_in_seconds: number;
}

export interface FinalizeUpload {
  video_asset: {
    id: string;
    status: string;
    retention_expires_at: string | null;
  };
  analysis_job: AnalysisJob;
}

export interface SignedUrl {
  url: string;
  expires_in_seconds: number;
}
