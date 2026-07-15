declare global {
  interface Window {
    // Injected at container start from $VITE_API_URL / $VITE_INGESTION_URL by
    // pwa/docker-entrypoint.sh (see /config.js). Absent in local dev, where
    // import.meta.env takes over.
    __APP_CONFIG__?: { API_URL?: string; INGESTION_URL?: string };
  }
}

const API =
  window.__APP_CONFIG__?.API_URL ||
  import.meta.env.VITE_API_URL ||
  "http://localhost:8000";

// Public ingestion base for brochure cover images + documents. Empty in prod
// unless configured (feature stays off — cards just show the placeholder).
const INGESTION =
  window.__APP_CONFIG__?.INGESTION_URL ||
  import.meta.env.VITE_INGESTION_URL ||
  (import.meta.env.DEV ? "http://localhost:8003" : "");

export const brochureImageUrl = (slug: string): string | null =>
  INGESTION ? `${INGESTION}/policies/${slug}/brochure` : null;

export const brochureDocUrl = (slug: string): string | null =>
  INGESTION ? `${INGESTION}/policies/${slug}/document` : null;

// crypto.randomUUID() only exists in a secure context (HTTPS or localhost), so
// it throws over plain HTTP to a LAN IP (e.g. a NAS at http://192.168.x.x). Fall
// back to getRandomValues (available in insecure contexts), then to a non-crypto
// id — a chat session id needs to be unique, not unguessable.
export function newSessionId(): string {
  const c = globalThis.crypto;
  if (c?.randomUUID) return c.randomUUID();
  if (c?.getRandomValues) {
    const b = c.getRandomValues(new Uint8Array(16));
    b[6] = (b[6] & 0x0f) | 0x40;
    b[8] = (b[8] & 0x3f) | 0x80;
    const h = Array.from(b, (x) => x.toString(16).padStart(2, "0"));
    return `${h[0]}${h[1]}${h[2]}${h[3]}-${h[4]}${h[5]}-${h[6]}${h[7]}-${h[8]}${h[9]}-${h[10]}${h[11]}${h[12]}${h[13]}${h[14]}${h[15]}`;
  }
  return `s-${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`;
}

export interface ProductLine {
  code: string;
  name: string;
  policy_count: number;
}

export interface Recommendation {
  slug: string;
  name: string;
  insurer_name: string;
  premium_min: string | number | null;
  premium_max: string | number | null;
  premium_frequency: string | null;
  currency: string;
  summary: string;
  // Structured since the writer classifies each reason; strings still tolerated
  // (older payloads / guided-mode fallbacks) and normalized in the UI.
  match_reasons: (MatchReason | string)[];
  match_strength?: "strong" | "partial";
  exclusions: string[];
  verified_at: string | null;
  source_url: string | null;
  coverage?: Record<string, unknown> | null;
}

export interface MatchReason {
  text: string;
  kind: "match" | "gap";
}

export type Recommendations = Record<string, Recommendation[]>;

export interface Question {
  text: string;
  input_type: "choice" | "number" | "text";
  options: string[] | null;
}

export interface AgentEvent {
  event: "profile_update" | "question" | "recommendations" | "message" | "error" | "done";
  data: unknown;
}

export async function fetchProductLines(): Promise<ProductLine[]> {
  const response = await fetch(`${API}/product-lines`);
  if (!response.ok) throw new Error(`product-lines failed: ${response.status}`);
  return response.json();
}

export interface Comparison {
  policies: string[];
  not_found: string[];
  comparison: Record<string, Record<string, unknown>>;
}

export async function fetchComparison(slugs: string[]): Promise<Comparison> {
  const response = await fetch(`${API}/compare?slugs=${slugs.join(",")}`);
  if (!response.ok) throw new Error(`compare failed: ${response.status}`);
  return response.json();
}

export async function streamChat(
  sessionId: string,
  message: string,
  mode: "freeform" | "guided",
  onEvent: (event: AgentEvent) => void,
): Promise<void> {
  const response = await fetch(`${API}/chat`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ session_id: sessionId, message, mode }),
  });
  if (!response.ok || !response.body) {
    throw new Error(`chat failed: ${response.status}`);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    let boundary = buffer.indexOf("\n\n");
    while (boundary >= 0) {
      const frame = buffer.slice(0, boundary);
      buffer = buffer.slice(boundary + 2);
      let event = "message";
      let data = "";
      for (const line of frame.split("\n")) {
        if (line.startsWith("event: ")) event = line.slice(7).trim();
        else if (line.startsWith("data: ")) data += line.slice(6);
      }
      onEvent({
        event: event as AgentEvent["event"],
        data: data ? JSON.parse(data) : {},
      });
      boundary = buffer.indexOf("\n\n");
    }
  }
}
