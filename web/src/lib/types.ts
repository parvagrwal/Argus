export interface EvidenceItem {
  id?: string;
  claim?: string;
  source?: string;
  ref?: string;
  type?: string;
  supports?: string;
  entity_ids?: string[];
  timestamp?: string;
  confidence?: number;
}

export interface FeatureContribution {
  feature: string;
  direction?: string;
  weight?: number;
}

export interface ConfidenceBreakdown {
  base_classifier_probability?: number;
  adjusted_probability?: number;
  features?: Record<string, number>;
  weights?: Record<string, number>;
  bias?: number;
  logit?: number;
  probability?: number;
  cold_start_capped?: boolean;
  rule_adjustments?: Array<{ rule: string; delta: number; rationale?: string }>;
  top_contributing_features?: FeatureContribution[];
}

export interface DecisionItem {
  round?: number;
  probability?: number;
  rule_fired?: string;
  independent_evidence?: number;
  continue_investigating?: boolean;
  note?: string;
  action?: string;
  route?: string;
  reason?: string;
  confidence?: number;
  rule_citations?: string[];
  automated?: boolean;
  timestamp?: string;
}

export interface UncertaintyData {
  confidence_interval?: [number, number];
  epistemic_vs_aleatoric?: string;
  key_unknowns?: string[];
  [key: string]: unknown;
}

export interface NextBestActionItem {
  initial_action?: string;
  final_action?: string;
  what_changed?: string;
  value_of_information?: number;
  simulated_evidence_used?: string[];
  action?: string;
  route?: string;
  reason?: string;
}

export interface SarData {
  file?: boolean;
  filing_recommended?: boolean;
  reason?: string;
  narrative?: string;
  subjects?: string[];
  subject_entities?: string[];
  filing_priority?: string;
  grounds?: string[];
  total_amount_usd?: number;
  activity_dates?: string[];
}

export interface ToolCallItem {
  step?: number;
  tool?: string;
  query_name?: string;
  query_type?: string;
  params?: Record<string, unknown>;
  args?: Record<string, unknown> | string;
  rows?: number;
  latency_ms?: number;
  result_summary?: string;
  timestamp?: string;
  ts?: string;
}

export interface CaseInternal {
  case_id?: string;
  opened_at?: string;
  status?: string;
  trigger_type?: string;
  trigger_text?: string;
  flagged_risk_score?: number;
  verdict?: "fraud" | "legitimate" | "uncertain" | string;
  fraud_probability?: number;
  pattern?: string;
  pattern_description?: string;
  affected_txn_ids?: string[];
  first_suspicious_txn_id?: string;
  connected_card_ids?: string[];
  connected_device_profiles?: string[];
  exposure_usd?: number;
  evidence?: EvidenceItem[];
  confidence_breakdown?: ConfidenceBreakdown;
  decisions?: DecisionItem[];
  uncertainty?: UncertaintyData | string;
  similar_prior_cases?: string[];
  summary?: string;
  written_to_graph?: boolean;
  graph_case_id?: string;
}

export interface InternalRecord {
  schema_version?: string;
  answer?: unknown;
  trigger_type?: string;
  trigger_text?: string;
  opened_at?: string;
  flagged_txn_id?: string;
  card_id?: string;
  customer_id?: string;
  flagged_risk_score?: number;
  tool_trace?: ToolCallItem[];
  confidence_breakdown?: ConfidenceBreakdown;
  decisions?: DecisionItem[];
  uncertainty?: UncertaintyData | string;
  simulated_evidence?: unknown;
  verdict?: string;
}

export interface EconomicsData {
  probability: number;
  exposure_usd: number;
  at_risk_usd: number;
  next_query?: string;
  expected_logit_gain?: number;
  expected_probability_shift?: number;
  value_of_information_usd?: number;
  cost_of_delay_gate_usd?: number;
  continue_gathering?: boolean;
  reading?: string;
}

export interface CounterfactualFlip {
  feature: string;
  original_value: string | number;
  flip_to: string | number;
  new_decision?: string;
  plausibility?: string;
}

export interface CounterfactualData {
  flips?: CounterfactualFlip[];
  sentence?: string;
}

export interface MetaData {
  fixture?: string;
  recorded_at?: string;
  source?: string;
  pipeline?: string;
}

export interface CaseBundle {
  answer: {
    case_id: string;
    case: CaseInternal;
    evidence_requests?: unknown[];
    next_best_actions?: NextBestActionItem[] | {
      initial?: NextBestActionItem[];
      final?: NextBestActionItem[];
      what_changed?: string;
    };
    sar?: SarData;
    stop_reason?: string;
    tool_calls?: number | ToolCallItem[];
    tokens?: number;
    latency_s?: number;
  };
  internal_record?: InternalRecord;
  economics?: EconomicsData;
  counterfactual?: CounterfactualData;
  meta?: MetaData;
}

export interface AblationRecord {
  p_with_memory: number;
  p_without_memory: number;
  verdict_with: string;
  verdict_without: string;
  delta_p: number;
  verdict_changed: boolean;
}

export type AblationMap = Record<string, AblationRecord>;
