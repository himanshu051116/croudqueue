
export interface Capabilities {
  supported_languages: string[];
  generated_channels: string[];
  publication_surfaces: string[];
  gemini: {
    model: string;
    configured: boolean;
    server_side_only: boolean;
  };
  demo_fault_injection_enabled: boolean;
  synthetic_prototype: boolean;
}

export type LifecycleState =
  | "DRAFT"
  | "CANDIDATE_SELECTED"
  | "GUIDANCE_VERIFYING"
  | "PREFLIGHT_BLOCKED"
  | "SEMANTIC_PASSED"
  | "SIMULATION_RUNNING"
  | "PREFLIGHT_PASSED"
  | "APPROVED"
  | "PUBLISHING"
  | "PUBLISHED";

export interface VenueNode {
  id: string;
  name: string;
  node_type: string;
  capacity: number;
  stable_key: string;
  x: number;
  y: number;
}

export interface VenueEdge {
  id: string;
  venue_id: string;
  source_id: string;
  target_id: string;
  capacity: number;
  travel_time_seconds: number;
  stable_key: string;
  is_active: boolean;
  protected: boolean;
}

export interface VenueRoute {
  id: string;
  venue_id: string;
  waypoints: string[];
  stable_key: string;
  protected: boolean;
  required_assets: string[];
}

export interface VenueTopology {
  venue_id: string;
  name: string;
  reference_version: string;
  nodes: Record<string, VenueNode>;
  edges: Record<string, VenueEdge>;
  assets: Record<string, { id: string; stable_key: string; asset_type: string; status: string }>;
  routes: Record<string, VenueRoute>;
}

export interface Scenario {
  key: string;
  name: string;
  description: string;
  default_intent: {
    objective: string;
    target: string;
    affected_audience: string;
    constraints: Record<string, unknown>;
    excluded_cohorts: string[];
  };
}

export interface Candidate {
  id: string;
  candidate_key: string;
  title: string;
  cohort_id: string;
  destination_id?: string;
  route_id?: string;
  is_viable: boolean;
  preliminary_rank: number | null;
  selected?: boolean;
  rejections?: Array<{
    reason_code: string;
    message: string;
    affected_route_id?: string | null;
    affected_edge_key?: string | null;
    affected_asset_key?: string | null;
  }>;
}

export interface RunCreateResult {
  run_id: string;
  session_id: string;
  scenario_key: string;
  lifecycle_state: LifecycleState;
  snapshot_id: string;
  canonical_input_hash: string;
  candidates: Candidate[];
}

export interface Snapshot {
  id: string;
  session_id: string;
  scenario_key: string;
  reference_data_version: string;
  canonical_input_hash: string;
  timestamp: string;
  nodes_state: Record<string, { pressure?: number; status?: string }>;
  edges_state: Record<string, { is_active?: boolean }>;
  assets_state: Record<string, { status?: string }>;
}

export interface GuidanceVariant {
  id?: string;
  language: "en" | "es" | "fr";
  channel: "fan_app" | "pa";
  version: number;
  audience_action: string;
  route_clause: string;
  fallback_clause: string;
  protection_clause: string;
  validity_clause: string;
  optional_explanation?: string | null;
  rendered_text: string;
  content_hash: string;
}

export interface Diagnostic {
  id?: string;
  code: string;
  stage: string;
  severity: string;
  message: string;
  blocking: boolean;
  resolved_at?: string | null;
  details?: Record<string, unknown>;
}

export interface FlowMetrics {
  maximum_queue: number;
  overload_frequency: number;
  unfinished_demand: number;
  clearance_time_minutes: number;
}

export interface SimulationResult {
  sample_set_id: string;
  seed: number;
  sample_count: number;
  paired: boolean;
  baseline: FlowMetrics;
  intervention: FlowMetrics;
  protected_route_violations: number;
  failure_frequency: number;
  wilson_95_lower: number;
  wilson_95_upper: number;
  verdict: "PASS" | "REVIEW" | "BLOCK";
  explanation: string;
  samples_hash: string;
  result_hash: string;
}

export interface RunDetails {
  run_id: string;
  session_id: string;
  scenario_key: string;
  lifecycle_state: LifecycleState;
  run_version: number;
  selected_candidate_id: string | null;
  snapshot_hash: string;
  gir: Record<string, unknown> | null;
  candidates: Candidate[];
  generation_provenance: Record<string, unknown> | null;
  variants: GuidanceVariant[];
  diagnostics: Diagnostic[];
  simulation: SimulationResult | null;
  approval: {
    approved_by_user_id: string;
    approver_role: string;
    run_version: number;
    bundle_hash: string;
    approval_note: string | null;
    approved_at: string;
  } | null;
  publication_batch: {
    id: string;
    status: string;
    started_at: string;
    completed_at: string | null;
  } | null;
  publication_deliveries: PublicationDelivery[];
  expected_bundle_hash: string | null;
  decision_bundle_hash: string | null;
}

export interface AuditEvent {
  id: string;
  sequence_number: number;
  event_type: string;
  payload: Record<string, unknown>;
  created_at: string;
  event_hash: string;
}

export interface AuditResponse {
  run_id: string;
  chain_scope: "session";
  session_event_count: number;
  chain_valid: boolean;
  events: AuditEvent[];
}

export interface PublicationDelivery {
  surface: string;
  language: string;
  status: string;
  variant_id: string | null;
  delivered_at: string | null;
}
