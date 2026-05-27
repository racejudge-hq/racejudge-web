/**
 * Typed client for the RACEJUDGE FastAPI backend.
 * In Next.js, call from Server Components or Route Handlers — not client components.
 */

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export interface Decision {
  doc_id: string;
  title: string;
  pdf_url: string;
  season: number;
  published_at: string | null;
  char_count: number;
  needs_ocr: boolean;
  parsed_at: string;
}

export interface DecisionDetail extends Decision {
  raw_text: string;
  sha256_hash: string;
  r2_key: string;
}

export async function getDecisions(params?: {
  season?: number;
  q?: string;
  limit?: number;
  offset?: number;
}): Promise<Decision[]> {
  const url = new URL(`${API_BASE}/v1/decisions`);
  if (params?.season) url.searchParams.set("season", String(params.season));
  if (params?.q)      url.searchParams.set("q", params.q);
  if (params?.limit)  url.searchParams.set("limit", String(params.limit));
  if (params?.offset) url.searchParams.set("offset", String(params.offset));

  const res = await fetch(url.toString(), { next: { revalidate: 60 } });
  if (!res.ok) throw new Error(`GET /v1/decisions failed: ${res.status}`);
  return res.json();
}

export async function getDecision(docId: string): Promise<DecisionDetail> {
  const res = await fetch(`${API_BASE}/v1/decisions/${docId}`, {
    next: { revalidate: 3600 },
  });
  if (!res.ok) throw new Error(`GET /v1/decisions/${docId} failed: ${res.status}`);
  return res.json();
}
