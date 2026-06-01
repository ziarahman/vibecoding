/**
 * types.ts
 * Mirror of the backend Pydantic schemas (schemas.py). Keep in sync.
 */

export type VeracityStatus =
  | "VERIFIED"
  | "SPECULATIVE"
  | "CONTRADICTED"
  | "PENDING";

export type SignalCategory =
  | "S1_FILING"
  | "PRICE_RANGE"
  | "ROADSHOW"
  | "PRICING"
  | "LISTING"
  | "WITHDRAWAL"
  | "RUMOR"
  | "OTHER";

export interface EvidenceItem {
  source: string;
  url?: string | null;
  summary: string;
  supports_claim: boolean;
  is_primary_source: boolean;
  retrieved_at: string;
}

export interface Signal {
  id: number;
  company_name: string;
  ticker?: string | null;
  exchange?: string | null;
  category: SignalCategory;
  status: VeracityStatus;
  confidence: number;

  valuation_usd?: number | null;
  price_range_low?: number | null;
  price_range_high?: number | null;
  shares_offered?: number | null;
  projected_date?: string | null;

  headline_claim: string;
  raw_quote?: string | null;

  source_title?: string | null;
  source_url?: string | null;
  source_name?: string | null;

  reasoning?: string | null;
  key_supporting_points: string[];
  key_contradicting_points: string[];
  evidence: EvidenceItem[];

  discovered_at: string;
  updated_at: string;
}

export interface PaginatedSignals {
  items: Signal[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

export interface StatsSummary {
  total_tracked: number;
  verified: number;
  speculative: number;
  contradicted: number;
  pending: number;
  last_scan_at?: string | null;
}

export interface ScanResult {
  status: string;
  documents_discovered: number;
  claims_extracted: number;
  signals_upserted: number;
  duration_seconds: number;
  detail?: string | null;
}

export interface SignalQuery {
  status?: VeracityStatus;
  category?: string;
  search?: string;
  sort_by?: "discovered_at" | "confidence" | "company_name" | "updated_at";
  sort_dir?: "asc" | "desc";
  page?: number;
  page_size?: number;
}
