import type {
  User,
  AuthResponse,
  Recording,
  PreviewData,
  Project,
  ParameterEstimate,
  Job,
  DashboardStats,
} from "./types";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const url = `${API_BASE}${path}`;
  const res = await fetch(url, {
    ...options,
    credentials: "include",
    headers: {
      ...options.headers,
    },
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(body.detail || `Request failed (${res.status})`);
  }
  if (res.status === 204) return undefined as T;
  return res.json();
}

export const authApi = {
  login: (email: string, password: string) =>
    request<AuthResponse>("/api/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password }),
    }),

  register: (email: string, password: string) =>
    request<AuthResponse>("/api/auth/register", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password }),
    }),

  me: () => request<User>("/api/auth/me"),

  logout: () =>
    request<void>("/api/auth/logout", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
    }),
};

export const recordingsApi = {
  list: async (): Promise<Recording[]> => {
    const res = await request<{ items: Recording[]; total: number }>(
      "/api/recordings"
    );
    return res.items;
  },

  get: (id: string) => request<Recording>(`/api/recordings/${id}`),

  delete: (id: string) =>
    request<void>(`/api/recordings/${id}`, { method: "DELETE" }),

  preview: (id: string) =>
    request<PreviewData>(`/api/recordings/${id}/preview`),

  upload: async (formData: FormData): Promise<Recording> => {
    const url = `${API_BASE}/api/recordings/upload`;
    const res = await fetch(url, {
      method: "POST",
      credentials: "include",
      body: formData,
    });
    if (!res.ok) {
      const body = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(body.detail || `Upload failed (${res.status})`);
    }
    return res.json();
  },
};

export const projectsApi = {
  list: async (): Promise<Project[]> => {
    const res = await request<{ items: Project[]; total: number }>(
      "/api/projects"
    );
    return res.items;
  },

  get: (id: string) => request<Project>(`/api/projects/${id}`),

  create: (data: { name?: string; description?: string; recording_id: string }) =>
    request<Project>("/api/projects", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    }),

  analyze: (id: string) =>
    request<Job>(`/api/projects/${id}/estimate-parameters`, {
      method: "POST",
    }),

  parameters: (id: string) =>
    request<ParameterEstimate[]>(`/api/projects/${id}/parameters`),
};

export const jobsApi = {
  get: (id: string) => request<Job>(`/api/jobs/${id}`),
};

export const dashboardApi = {
  stats: () => request<DashboardStats>("/api/dashboard/stats"),
};
