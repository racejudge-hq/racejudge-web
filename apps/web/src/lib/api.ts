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

// ---------------------------------------------------------------------------
// Search
// ---------------------------------------------------------------------------

export interface SearchResult {
  doc_id: string;
  title: string;
  season: number;
  published_at: string | null;
  score: number;
  snippet: string;
}

export async function searchDecisions(
  q: string,
  season?: number,
  limit = 20,
): Promise<SearchResult[]> {
  const url = new URL(`${API_BASE}/v1/search`);
  url.searchParams.set("q", q);
  if (season) url.searchParams.set("season", String(season));
  url.searchParams.set("limit", String(limit));
  const res = await fetch(url.toString(), { cache: "no-store" });
  if (!res.ok) throw new Error(`GET /v1/search failed: ${res.status}`);
  return res.json();
}

// ---------------------------------------------------------------------------
// Annotations
// ---------------------------------------------------------------------------

export interface AnnotationStats {
  total_annotations: number;
  triplet_pairs: number;
  target_pairs: number;
  progress_pct: number;
  by_annotator: Record<string, number>;
}

export async function getAnnotationStats(): Promise<AnnotationStats> {
  const res = await fetch(`${API_BASE}/v1/annotations/stats/summary`, {
    next: { revalidate: 30 },
  });
  if (!res.ok) throw new Error(`GET /v1/annotations/stats/summary failed: ${res.status}`);
  return res.json();
}
