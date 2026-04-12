const API_BASE = typeof window !== "undefined" ? `${window.location.origin}/api` : "/api";

let _authToken: string | null = null;

export function setAuthToken(token: string | null) {
  _authToken = token;
  if (token) {
    if (typeof window !== "undefined") {
      sessionStorage.setItem("fg_token", token);
    }
  } else {
    if (typeof window !== "undefined") {
      sessionStorage.removeItem("fg_token");
    }
  }
}

export function getAuthToken(): string | null {
  if (_authToken) return _authToken;
  if (typeof window !== "undefined") {
    _authToken = sessionStorage.getItem("fg_token");
  }
  return _authToken;
}

export class AuthExpiredError extends Error {
  constructor() {
    super("Token expired or invalid");
    this.name = "AuthExpiredError";
  }
}

export async function fetchAPI<T = any>(path: string, init?: RequestInit): Promise<T> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  const token = getAuthToken();
  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }
  const res = await fetch(`${API_BASE}${path}`, {
    headers,
    ...init,
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    const detail: string = body.detail || body.error?.message || `API error: ${res.status}`;
    // 401 means token expired/invalid — clear stale token and signal re-auth
    if (res.status === 401) {
      setAuthToken(null);
      throw new AuthExpiredError();
    }
    throw new Error(detail);
  }
  return res.json();
}

export function apiURL(path: string): string {
  return `${API_BASE}${path}`;
}
