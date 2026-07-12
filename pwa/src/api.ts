const API = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

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
  match_reasons: string[];
  exclusions: string[];
  verified_at: string | null;
  source_url: string | null;
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
