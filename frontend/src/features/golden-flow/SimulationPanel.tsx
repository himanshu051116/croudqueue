import { BarChart3, CheckCircle2 } from "lucide-react";
import type { LifecycleState, SimulationResult } from "../../types";

interface SimulationPanelProps {
  state: LifecycleState | null;
  simulation: SimulationResult | null;
  busy: boolean;
  onSimulate: () => void;
}

export function SimulationPanel({ state, simulation, busy, onSimulate }: SimulationPanelProps) {
  return (
    <section className="panel p-5" aria-labelledby="simulation-title">
      <p className="eyebrow">Synthetic paired flow stress</p>
      <h2 id="simulation-title" className="section-title">200 shared-condition samples</h2>
      <p className="mt-2 text-sm text-slate-600">Transparent aggregate queue model. This is not a certified pedestrian-safety simulator.</p>
      {state === "SEMANTIC_PASSED" && (
        <button type="button" className="primary-button mt-4" onClick={onSimulate} disabled={busy}>
          <BarChart3 size={17} /> Run 200-sample paired simulation
        </button>
      )}
      {simulation && (
        <div className="mt-5">
          <div className={`flex items-center gap-2 rounded-xl p-4 font-black ${simulation.verdict === "PASS" ? "bg-emerald-50 text-emerald-900" : simulation.verdict === "REVIEW" ? "bg-amber-50 text-amber-900" : "bg-red-50 text-red-900"}`}>
            <CheckCircle2 size={20} /> Simulation verdict: {simulation.verdict}
          </div>
          <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            {[
              ["Maximum queue", simulation.baseline.maximum_queue, simulation.intervention.maximum_queue],
              ["Overload frequency", `${Math.round(simulation.baseline.overload_frequency * 100)}%`, `${Math.round(simulation.intervention.overload_frequency * 100)}%`],
              ["Unfinished demand", simulation.baseline.unfinished_demand, simulation.intervention.unfinished_demand],
              ["Clearance minutes", simulation.baseline.clearance_time_minutes, simulation.intervention.clearance_time_minutes],
            ].map(([label, baseline, intervention]) => (
              <div key={String(label)} className="rounded-xl border border-slate-200 bg-slate-50 p-4">
                <p className="text-xs font-bold uppercase tracking-wide text-slate-500">{label}</p>
                <p className="mt-2 text-sm text-slate-500">Baseline <strong className="text-slate-900">{String(baseline)}</strong></p>
                <p className="text-sm text-slate-500">Intervention <strong className="text-blue-700">{String(intervention)}</strong></p>
              </div>
            ))}
          </div>
          <p className="mt-4 text-sm text-slate-700">{simulation.explanation}</p>
          <p className="mt-2 font-mono text-[10px] text-slate-400">Sample set: {simulation.sample_set_id}</p>
        </div>
      )}
    </section>
  );
}
