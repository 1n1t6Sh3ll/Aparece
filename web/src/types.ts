export type Label = "OBSERVED_FACT" | "SUPPORTED_HYPOTHESIS" | "UNKNOWN";

export interface Action {
  id: string;
  kind: "missing_attribute" | "checklist" | "description" | "structured_data" | "price" | "language";
  priority: number;
  title: string;
  why: string;
  evidence: Record<string, unknown>;
  label: Label;
  effort: "low" | "med" | "high";
  field: string | null;
  seo_note: string;
}

export interface Fact { field: string; label: string; value: unknown; source_text: string | null; source_location: string | null }
export interface Prediction { value: unknown; confidence: number; model: string }
export interface NotFound { field: string; label: string; peers_with: number; of: number; predicted: Prediction | null }

export interface Summary {
  product_id: string; title: string | null; brand: string | null; product_type: string | null; language: string | null;
  merchant: string | null; price: number | null; currency: string | null; url?: string | null;
}

export interface PricePosition {
  available: boolean; price: number | null; currency: string | null; reason?: string; source?: string;
  peer_count?: number; p25?: number; median?: number; p75?: number; position?: "below" | "within" | "above";
}

export interface Quality {
  score: number; points: { facts: number; description: number; structured_data: number };
  facts_stated: number; facts_checked: number; description_chars: number; description_ref: number; structured_data_flags: number;
}
export type BoardRow = Summary & Quality & { is_you: boolean; link_unverified?: boolean };

export interface Audit {
  product: Summary & { image: string | null; draft: boolean; description?: string };
  notes?: string[];
  /** Present only when the page was read from a Common Crawl copy instead of live. */
  archive?: { source: "common_crawl"; capture_date: string; crawl_id: string; warc_url: string };
  /** Not a shirt: the full audit without a rank (rank.position is null). read_text is what we read the type from. */
  unranked?: { reason: "not_a_shirt"; type: string | null; read_from: string; read_text: string } | null;
  facts: Fact[];
  not_found: NotFound[];
  summary: { facts_found: number; attributes_checked: number; top_median_facts: number | null; top_count: number; top_missing: string[]; price_position: string | null };
  rank: { position: number | null; total: number; peer_data?: boolean; ranked?: boolean; match_step?: string; score: number; components: Quality; formula: string; weights: { facts: number; description: number; structured_data: number } };
  leaderboard: BoardRow[];
  table: { fields: string[]; rows: (Summary & { is_you: boolean; values: Record<string, unknown> })[] };
  context: { language: string | null; currency: string | null; merchant: string | null; dataset_size: number; quality_status: string };
  peers: (Summary & { match_score: number; facts_found: number })[];
  comparison: {
    of: number;
    facts: { target: number; top_median: number | null; of: number };
    description_chars: { target: number; top_median: number | null };
    structured_data: Record<string, { target: boolean; peers_present: number; of: number }>;
    reviews: { target_has_rating: boolean; top_with_rating: number };
  };
  price_position: PricePosition;
  actions: Action[];
  unknowns: string[];
  visibility: {
    available: boolean; models?: string[]; responses?: number; shops?: number; mention_rate?: Record<string, number | null>;
    site?: string | null; site_in_benchmark?: boolean; site_mention_rate?: Record<string, number | null>;
    top_named?: { name: string; answers: number }[];
  };
}
