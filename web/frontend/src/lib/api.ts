import type {
  AnalysisJob,
  ExportJob,
  FinalizeUpload,
  Project,
  Quota,
  Rally,
  RallyEdit,
  SignedUrl,
  UploadInitiate,
  User,
} from "./types";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    message: string,
  ) {
    super(message);
  }
}

function errorMessage(value: unknown): string {
  if (
    typeof value === "object" &&
    value !== null &&
    "detail" in value &&
    typeof value.detail === "string"
  ) {
    return value.detail;
  }
  return "Request failed";
}

async function readJson<T>(response: Response): Promise<T> {
  if (!response.ok) {
    let body: unknown;
    try {
      body = await response.json();
    } catch {
      body = null;
    }
    throw new ApiError(response.status, errorMessage(body));
  }
  return (await response.json()) as T;
}

export class ApiClient {
  private accessToken: string | null = null;
  private authEpoch = 0;
  private refreshOperation: {
    epoch: number;
    controller: AbortController;
    promise: Promise<boolean>;
  } | null = null;
  private sessionStateHandler: ((state: "invalidated" | "unavailable") => void) | null = null;

  get token(): string | null {
    return this.accessToken;
  }

  get sessionEpoch(): number {
    return this.authEpoch;
  }

  setToken(token: string | null): void {
    this.accessToken = token;
  }

  setSessionStateHandler(
    handler: ((state: "invalidated" | "unavailable") => void) | null,
  ): void {
    this.sessionStateHandler = handler;
  }

  private advanceAuthEpoch(clearToken: boolean): number {
    this.authEpoch += 1;
    this.refreshOperation?.controller.abort();
    if (clearToken) this.accessToken = null;
    return this.authEpoch;
  }

  private async performRefresh(epoch: number, signal: AbortSignal): Promise<boolean> {
    if (epoch !== this.authEpoch) return false;
    let response: Response;
    try {
      response = await fetch(`${API_URL}/api/v1/auth/refresh`, {
        method: "POST",
        credentials: "include",
        signal,
      });
    } catch (error) {
      if (epoch !== this.authEpoch || signal.aborted) return false;
      this.accessToken = null;
      this.sessionStateHandler?.("unavailable");
      throw error;
    }
    if (epoch !== this.authEpoch) return false;
    if (response.status === 401) {
      this.accessToken = null;
      this.sessionStateHandler?.("invalidated");
      return false;
    }
    if (!response.ok) {
      this.accessToken = null;
      this.sessionStateHandler?.("unavailable");
      await readJson<unknown>(response);
      return false;
    }
    let body: { access_token: string };
    try {
      body = (await response.json()) as { access_token: string };
    } catch (error) {
      if (epoch !== this.authEpoch) return false;
      this.accessToken = null;
      this.sessionStateHandler?.("unavailable");
      throw error;
    }
    if (epoch !== this.authEpoch) return false;
    this.accessToken = body.access_token;
    return true;
  }

  async refresh(): Promise<boolean> {
    const epoch = this.authEpoch;
    if (this.refreshOperation?.epoch === epoch) return this.refreshOperation.promise;
    const controller = new AbortController();
    const refresh = () => this.performRefresh(epoch, controller.signal);
    const pending =
      typeof navigator !== "undefined" && navigator.locks
        ? new Promise<boolean>((resolve, reject) => {
            void navigator.locks
              .request("breakpoint-refresh", { mode: "exclusive" }, async () => {
                try {
                  resolve(await refresh());
                } catch (error) {
                  reject(error);
                }
              })
              .catch(reject);
          })
        : refresh();
    const result = pending.finally(() => {
      if (this.refreshOperation?.promise === result) {
        this.refreshOperation = null;
      }
    });
    this.refreshOperation = { epoch, controller, promise: result };
    return result;
  }

  async request<T>(path: string, init: RequestInit = {}, retry = true): Promise<T> {
    const headers = new Headers(init.headers);
    if (init.body && !headers.has("Content-Type")) {
      headers.set("Content-Type", "application/json");
    }
    if (this.accessToken) headers.set("Authorization", `Bearer ${this.accessToken}`);
    const response = await fetch(`${API_URL}${path}`, {
      ...init,
      headers,
      credentials: "include",
    });
    if (response.status === 401 && retry && (await this.refresh())) {
      return this.request<T>(path, init, false);
    }
    if (response.status === 204) return undefined as T;
    return readJson<T>(response);
  }

  register(email: string) {
    return this.request<{ message: string }>("/api/v1/auth/register", {
      method: "POST",
      body: JSON.stringify({ email }),
    });
  }

  async verifyEmail(token: string, password: string) {
    const epoch = this.advanceAuthEpoch(true);
    const result = await this.request<{ message: string }>("/api/v1/auth/verify-email", {
      method: "POST",
      body: JSON.stringify({ token, password }),
    }, false);
    if (epoch !== this.authEpoch) {
      throw new DOMException("Superseded authentication operation", "AbortError");
    }
    return result;
  }

  async login(email: string, password: string): Promise<User> {
    const epoch = this.advanceAuthEpoch(true);
    const result = await this.request<{ access_token: string; user: User }>(
      "/api/v1/auth/login",
      { method: "POST", body: JSON.stringify({ email, password }) },
      false,
    );
    if (epoch !== this.authEpoch) {
      throw new DOMException("Superseded authentication operation", "AbortError");
    }
    this.accessToken = result.access_token;
    return result.user;
  }

  async logout(): Promise<void> {
    const epoch = this.advanceAuthEpoch(false);
    try {
      await this.request("/api/v1/auth/logout", { method: "POST" }, false);
    } finally {
      if (epoch === this.authEpoch) this.accessToken = null;
    }
  }

  forgotPassword(email: string) {
    return this.request<{ message: string }>("/api/v1/auth/forgot-password", {
      method: "POST",
      body: JSON.stringify({ email }),
    });
  }

  async resetPassword(token: string, password: string) {
    const epoch = this.advanceAuthEpoch(true);
    const result = await this.request<{ message: string }>("/api/v1/auth/reset-password", {
      method: "POST",
      body: JSON.stringify({ token, new_password: password }),
    }, false);
    if (epoch !== this.authEpoch) {
      throw new DOMException("Superseded authentication operation", "AbortError");
    }
    return result;
  }

  listProjects = () => this.request<Project[]>("/api/v1/projects");
  getProject = (id: string) => this.request<Project>(`/api/v1/projects/${id}`);
  createProject = (name: string) =>
    this.request<Project>("/api/v1/projects", {
      method: "POST",
      body: JSON.stringify({ name }),
    });
  deleteProject = (id: string) =>
    this.request<void>(`/api/v1/projects/${id}`, { method: "DELETE" });
  getQuota = () => this.request<Quota>("/api/v1/quota/me");
  getAnalysis = (id: string) =>
    this.request<AnalysisJob>(`/api/v1/projects/${id}/analysis`);
  cancelAnalysis = (id: string) =>
    this.request<AnalysisJob>(`/api/v1/projects/${id}/analysis/cancel`, {
      method: "POST",
    });
  retryAnalysis = (id: string) =>
    this.request<AnalysisJob>(`/api/v1/projects/${id}/analysis/retry`, {
      method: "POST",
    });
  getRallies = (id: string) =>
    this.request<Rally[]>(`/api/v1/projects/${id}/rallies`);
  updateRally = (projectId: string, rallyId: string, edit: RallyEdit) =>
    this.request<RallyEdit>(`/api/v1/projects/${projectId}/rallies/${rallyId}`, {
      method: "PATCH",
      body: JSON.stringify(edit),
    });
  createExport = (id: string) =>
    this.request<ExportJob>(`/api/v1/projects/${id}/exports`, { method: "POST" });
  getExport = (projectId: string, exportId: string) =>
    this.request<ExportJob>(`/api/v1/projects/${projectId}/exports/${exportId}`);
  cancelExport = (projectId: string, exportId: string) =>
    this.request<ExportJob>(
      `/api/v1/projects/${projectId}/exports/${exportId}/cancel`,
      { method: "POST" },
    );
  retryExport = (projectId: string, exportId: string) =>
    this.request<ExportJob>(
      `/api/v1/projects/${projectId}/exports/${exportId}/retry`,
      { method: "POST" },
    );
  sourceUrl = (id: string) =>
    this.request<SignedUrl>(`/api/v1/projects/${id}/video/signed-url`);
  exportUrl = (projectId: string, exportId: string) =>
    this.request<SignedUrl>(
      `/api/v1/projects/${projectId}/exports/${exportId}/signed-url`,
    );
  initiateUpload = (
    projectId: string,
    input: {
      filename: string;
      content_type: string;
      size_bytes: number;
      duration_seconds: number;
      part_count: number;
    },
  ) =>
    this.request<UploadInitiate>(`/api/v1/projects/${projectId}/uploads`, {
      method: "POST",
      body: JSON.stringify(input),
    });
  finalizeUpload = (
    projectId: string,
    assetId: string,
    input: {
      idempotency_key: string;
      parts: { part_number: number; etag: string }[];
    },
    signal?: AbortSignal,
  ) =>
    this.request<FinalizeUpload>(
      `/api/v1/projects/${projectId}/uploads/${assetId}/finalize`,
      { method: "POST", body: JSON.stringify(input), signal },
    );
  abortUpload = (projectId: string, assetId: string) =>
    this.request<{ status: "aborted" | "cleanup_pending" }>(
      `/api/v1/projects/${projectId}/uploads/${assetId}/abort`,
      { method: "POST" },
    );
}

export const api = new ApiClient();
export { API_URL };
