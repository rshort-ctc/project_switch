export const DEFAULT_API_URL = "http://127.0.0.1:8000";

export function validateLocalBackendUrl(rawUrl: string): string {
  const normalized = normalizeApiUrl(rawUrl);
  const parsed = new URL(normalized);
  if (!["http:", "https:"].includes(parsed.protocol)) {
    throw new Error("SWITCH backend URL must use http or https");
  }
  const host = parsed.hostname.toLowerCase();
  const allowed =
    host === "localhost" ||
    host === "127.0.0.1" ||
    host === "::1" ||
    host.endsWith(".local") ||
    host.endsWith(".internal");
  if (!allowed) {
    throw new Error("LOCAL_ONLY blocks non-local SWITCH backend hosts");
  }
  return normalized;
}

export function normalizeApiUrl(apiUrl: string): string {
  return apiUrl.trim().replace(/\/+$/, "") || DEFAULT_API_URL;
}
