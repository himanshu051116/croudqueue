import type {
  AuditResponse,
  Capabilities,
  RunCreateResult,
  RunDetails,
  Scenario,
  Snapshot,
  VenueTopology,
} from "../types";

async function request<T>(
  path: string,
  init: RequestInit = {},
  sessionId?: string,
): Promise<T> {
  const headers = new Headers(init.headers);
  if (init.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  if (sessionId) headers.set("X-Session-ID", sessionId);
  const response = await fetch(path, { ...init, headers });
  if (!response.ok) {
    const payload = (await response.json().catch(() => ({}))) as { detail?: string };
    throw new Error(payload.detail ?? `Request failed with HTTP ${response.status}`);
  }
  return (await response.json()) as T;
}

export const api = {
  capabilities: () => request<Capabilities>("/api/capabilities"),
  topology: () => request<VenueTopology>("/api/venue/topology"),
  scenarios: () => request<Scenario[]>("/api/venue/scenarios"),
  createRun: (sessionId: string, scenarioKey: string) =>
    request<RunCreateResult>("/api/runs", {
      method: "POST",
      body: JSON.stringify({ session_id: sessionId, scenario_key: scenarioKey }),
    }),
  snapshot: (snapshotId: string, sessionId: string) =>
    request<Snapshot>(`/api/venue/snapshot/${snapshotId}`, {}, sessionId),
  details: (runId: string, sessionId: string) =>
    request<RunDetails>(`/api/runs/${runId}`, {}, sessionId),
  selectCandidate: (runId: string, sessionId: string, candidateId: string) =>
    request<Record<string, unknown>>(
      `/api/runs/${runId}/select-candidate`,
      { method: "POST", body: JSON.stringify({ candidate_id: candidateId }) },
      sessionId,
    ),
  generate: (runId: string, sessionId: string, injectFault: boolean) =>
    request<Record<string, unknown>>(
      `/api/runs/${runId}/generate-guidance`,
      {
        method: "POST",
        body: JSON.stringify({ enable_fault_injection: injectFault }),
      },
      sessionId,
    ),
  repair: (runId: string, sessionId: string) =>
    request<Record<string, unknown>>(
      `/api/runs/${runId}/repair`,
      { method: "POST" },
      sessionId,
    ),
  simulate: (runId: string, sessionId: string) =>
    request<Record<string, unknown>>(
      `/api/runs/${runId}/simulate`,
      { method: "POST" },
      sessionId,
    ),
  approve: (
    runId: string,
    sessionId: string,
    expectedBundleHash: string,
  ) =>
    request<Record<string, unknown>>(
      `/api/runs/${runId}/approve`,
      {
        method: "POST",
        body: JSON.stringify({
          approved_by_user_id: "00000000-0000-4000-8000-000000000026",
          approver_role: "SUPERVISOR",
          approval_note: "Synthetic CrowdCue demonstration evidence reviewed.",
          expected_bundle_hash: expectedBundleHash,
        }),
      },
      sessionId,
    ),
  publish: (runId: string, sessionId: string) =>
    request<{ deliveries: Array<Record<string, unknown>> }>(
      `/api/runs/${runId}/publish`,
      { method: "POST" },
      sessionId,
    ),
  audit: (runId: string, sessionId: string) =>
    request<AuditResponse>(`/api/runs/${runId}/audit`, {}, sessionId),
};
