import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { AlertCircle, ArrowRight, LoaderCircle, RefreshCw } from "lucide-react";

import { api } from "./lib/api";
import type {
  AuditResponse,
  Candidate,
  Capabilities,
  RunCreateResult,
  RunDetails,
  Scenario,
  Snapshot,
  VenueTopology,
} from "./types";
import { ApprovalPublicationPanel } from "./features/golden-flow/ApprovalPublicationPanel";
import { AuditTimeline } from "./features/golden-flow/AuditTimeline";
import { CandidatePanel } from "./features/golden-flow/CandidatePanel";
import { GuidancePanel } from "./features/golden-flow/GuidancePanel";
import { ProductHeader } from "./features/golden-flow/ProductHeader";
import { PreflightStepper } from "./features/golden-flow/PreflightStepper";
import { SimulationPanel } from "./features/golden-flow/SimulationPanel";
import { VenueMap } from "./features/golden-flow/VenueMap";

const SESSION_STORAGE_KEY = "crowdcue-session-id";
const CURRENT_RUN_STORAGE_KEY = "crowdcue-current-run";

interface StoredRun {
  runId: string;
  snapshotId: string;
  scenarioKey: string;
}

function getSessionId(): string {
  const current = sessionStorage.getItem(SESSION_STORAGE_KEY);
  if (current) return current;
  const created = crypto.randomUUID();
  sessionStorage.setItem(SESSION_STORAGE_KEY, created);
  return created;
}

export default function App() {
  const [sessionId] = useState(getSessionId);
  const [topology, setTopology] = useState<VenueTopology | null>(null);
  const [capabilities, setCapabilities] = useState<Capabilities | null>(null);
  const [scenarios, setScenarios] = useState<Scenario[]>([]);
  const [scenarioKey, setScenarioKey] = useState("gate_convergence");
  const [createdRun, setCreatedRun] = useState<RunCreateResult | null>(null);
  const [details, setDetails] = useState<RunDetails | null>(null);
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null);
  const [audit, setAudit] = useState<AuditResponse | null>(null);
  const [injectFault, setInjectFault] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const initializationStarted = useRef(false);

  const selectedScenario = useMemo(
    () => scenarios.find((scenario) => scenario.key === scenarioKey),
    [scenarioKey, scenarios],
  );
  const state = details?.lifecycle_state ?? createdRun?.lifecycle_state ?? null;
  const candidates = details?.candidates ?? createdRun?.candidates ?? [];

  const refreshEvidence = useCallback(
    async (runId: string, snapshotId?: string) => {
      const [nextDetails, nextAudit] = await Promise.all([
        api.details(runId, sessionId),
        api.audit(runId, sessionId),
      ]);
      setDetails(nextDetails);
      setAudit(nextAudit);
      const resolvedSnapshot = snapshotId ?? createdRun?.snapshot_id;
      if (resolvedSnapshot) setSnapshot(await api.snapshot(resolvedSnapshot, sessionId));
    },
    [createdRun?.snapshot_id, sessionId],
  );

  const beginRun = useCallback(
    async (nextScenarioKey: string) => {
      setBusy(true);
      setError(null);
      setDetails(null);
      setAudit(null);
      try {
        const run = await api.createRun(sessionId, nextScenarioKey);
        sessionStorage.setItem(
          CURRENT_RUN_STORAGE_KEY,
          JSON.stringify({
            runId: run.run_id,
            snapshotId: run.snapshot_id,
            scenarioKey: nextScenarioKey,
          } satisfies StoredRun),
        );
        setCreatedRun(run);
        setSnapshot(await api.snapshot(run.snapshot_id, sessionId));
        setAudit(await api.audit(run.run_id, sessionId));
      } catch (caught) {
        setError(caught instanceof Error ? caught.message : "Unable to start the run.");
      } finally {
        setBusy(false);
      }
    },
    [sessionId],
  );

  useEffect(() => {
    if (initializationStarted.current) return;
    initializationStarted.current = true;

    async function loadApplication() {
      try {
        const [nextTopology, nextScenarios, nextCapabilities] = await Promise.all([
          api.topology(),
          api.scenarios(),
          api.capabilities(),
        ]);
        setTopology(nextTopology);
        setScenarios(nextScenarios);
        setCapabilities(nextCapabilities);

        const storedRaw = sessionStorage.getItem(CURRENT_RUN_STORAGE_KEY);
        if (storedRaw) {
          try {
            const stored = JSON.parse(storedRaw) as StoredRun;
            const [storedDetails, storedSnapshot, storedAudit] = await Promise.all([
              api.details(stored.runId, sessionId),
              api.snapshot(stored.snapshotId, sessionId),
              api.audit(stored.runId, sessionId),
            ]);
            setScenarioKey(stored.scenarioKey);
            setCreatedRun({
              run_id: stored.runId,
              session_id: sessionId,
              scenario_key: stored.scenarioKey,
              lifecycle_state: storedDetails.lifecycle_state,
              snapshot_id: stored.snapshotId,
              canonical_input_hash: storedDetails.snapshot_hash,
              candidates: storedDetails.candidates,
            });
            setDetails(storedDetails);
            setSnapshot(storedSnapshot);
            setAudit(storedAudit);
            return;
          } catch {
            sessionStorage.removeItem(CURRENT_RUN_STORAGE_KEY);
          }
        }
        await beginRun("gate_convergence");
      } catch (caught) {
        setError(
          caught instanceof Error ? caught.message : "Unable to load CrowdCue.",
        );
      }
    }

    void loadApplication();
  }, [beginRun, sessionId]);

  async function execute(action: () => Promise<unknown>) {
    if (!createdRun) return;
    setBusy(true);
    setError(null);
    try {
      await action();
      await refreshEvidence(createdRun.run_id, createdRun.snapshot_id);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "The action failed.");
    } finally {
      setBusy(false);
    }
  }

  function changeScenario(next: string) {
    setScenarioKey(next);
    void beginRun(next);
  }

  function selectCandidate(candidate: Candidate) {
    if (!createdRun) return;
    void execute(() =>
      api.selectCandidate(createdRun.run_id, sessionId, candidate.id),
    );
  }

  async function publish() {
    if (!createdRun) return;
    setBusy(true);
    setError(null);
    try {
      await api.publish(createdRun.run_id, sessionId);
      await refreshEvidence(createdRun.run_id, createdRun.snapshot_id);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Publication failed.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="min-h-screen bg-slate-100 text-slate-950">
      <ProductHeader geminiConfigured={capabilities?.gemini.configured ?? null} />
      <main className="mx-auto max-w-7xl space-y-5 px-4 py-6 sm:px-8">
        <section className="panel grid gap-4 p-5 lg:grid-cols-[1fr_1.2fr]">
          <div>
            <p className="eyebrow">The operational gap</p>
            <h2 className="text-2xl font-black tracking-tight sm:text-3xl">
              Gate C congested <ArrowRight className="inline" size={20} /> “Use Gate A” <ArrowRight className="inline" size={20} /> new bottleneck
            </h2>
            <p className="mt-3 text-sm leading-6 text-slate-600">
              CrowdCue tests an instruction as an operational state change—not only as text. Capacity, routes, assets and protected constraints remain deterministic.
            </p>
          </div>
          <div className="rounded-xl border border-blue-200 bg-blue-50 p-4">
            <p className="text-xs font-bold uppercase tracking-[0.18em] text-blue-700">Synthetic prototype disclosure</p>
            <p className="mt-2 text-sm text-blue-950">All venue states, response assumptions and publication events are synthetic. CrowdCue is not a certified pedestrian-safety simulator and does not connect to FIFA systems.</p>
          </div>
        </section>

        {error && (
          <div className="flex items-start gap-3 rounded-xl border border-red-300 bg-red-50 p-4 text-red-900" role="alert">
            <AlertCircle className="mt-0.5 shrink-0" size={20} />
            <div><p className="font-bold">Action could not be completed</p><p className="text-sm">{error}</p></div>
          </div>
        )}

        <PreflightStepper state={state} />

        <section className="grid gap-5 lg:grid-cols-[minmax(0,1.45fr)_minmax(320px,0.75fr)]">
          <VenueMap topology={topology} snapshot={snapshot} scenarioName={selectedScenario?.name ?? "Gate C convergence"} />
          <div className="panel p-5">
            <p className="eyebrow">01 · Live scenario</p>
            <h2 className="section-title">Choose the operational pressure</h2>
            <div className="mt-4 grid gap-2">
              {scenarios.map((scenario) => (
                <button
                  type="button"
                  key={scenario.key}
                  onClick={() => changeScenario(scenario.key)}
                  disabled={busy}
                  className={`rounded-xl border px-4 py-3 text-left text-sm font-bold ${scenario.key === scenarioKey ? "border-blue-600 bg-blue-50 text-blue-950" : "border-slate-200 bg-white text-slate-700 hover:border-blue-300"}`}
                >
                  {scenario.name}
                </button>
              ))}
            </div>
            <div className="mt-5 border-t border-slate-200 pt-5">
              <p className="eyebrow">02 · Operational intent</p>
              <p className="mt-2 font-bold text-slate-950">{selectedScenario?.description}</p>
              <dl className="mt-3 space-y-2 text-sm text-slate-600">
                <div><dt className="inline font-bold text-slate-800">Objective: </dt><dd className="inline">{selectedScenario?.default_intent.objective}</dd></div>
                <div><dt className="inline font-bold text-slate-800">Target: </dt><dd className="inline">{selectedScenario?.default_intent.target}</dd></div>
                <div><dt className="inline font-bold text-slate-800">Audience: </dt><dd className="inline">{selectedScenario?.default_intent.affected_audience}</dd></div>
              </dl>
            </div>
            <button type="button" className="secondary-button mt-5" onClick={() => beginRun(scenarioKey)} disabled={busy}>
              <RefreshCw size={16} /> Reset scenario
            </button>
          </div>
        </section>

        <CandidatePanel
          candidates={candidates}
          selectedCandidateId={details?.selected_candidate_id ?? null}
          disabled={busy || state !== "DRAFT"}
          onSelect={selectCandidate}
        />

        <GuidancePanel
          variants={details?.variants ?? []}
          diagnostics={details?.diagnostics ?? []}
          state={state}
          gir={details?.gir ?? null}
          provenance={details?.generation_provenance ?? null}
          injectFault={injectFault}
          faultInjectionAvailable={capabilities?.demo_fault_injection_enabled ?? false}
          busy={busy}
          onInjectFaultChange={setInjectFault}
          onGenerate={() => createdRun && void execute(() => api.generate(createdRun.run_id, sessionId, injectFault))}
          onRepair={() => createdRun && void execute(() => api.repair(createdRun.run_id, sessionId))}
        />

        <SimulationPanel
          state={state}
          simulation={details?.simulation ?? null}
          busy={busy}
          onSimulate={() => createdRun && void execute(() => api.simulate(createdRun.run_id, sessionId))}
        />

        <ApprovalPublicationPanel
          state={state}
          expectedBundleHash={details?.expected_bundle_hash ?? null}
          decisionBundleHash={details?.decision_bundle_hash ?? null}
          approval={details?.approval ?? null}
          deliveries={details?.publication_deliveries ?? []}
          busy={busy}
          onApprove={() => details?.expected_bundle_hash && createdRun && void execute(() => api.approve(createdRun.run_id, sessionId, details.expected_bundle_hash!))}
          onPublish={() => void publish()}
        />

        <AuditTimeline audit={audit} />

        {busy && (
          <div className="fixed bottom-4 right-4 flex items-center gap-2 rounded-full bg-slate-950 px-4 py-2 text-sm font-bold text-white shadow-xl" role="status" aria-live="polite">
            <LoaderCircle className="animate-spin" size={17} /> CrowdCue is processing
          </div>
        )}
      </main>
      <footer className="border-t border-slate-200 bg-white px-4 py-4 text-center text-xs text-slate-500">
        CrowdCue 26 hackathon prototype · Synthetic venue and response assumptions · Human approval required
      </footer>
    </div>
  );
}
