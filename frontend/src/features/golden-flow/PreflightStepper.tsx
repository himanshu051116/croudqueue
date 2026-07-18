import { Check, Circle, ShieldAlert } from "lucide-react";
import type { LifecycleState } from "../../types";

const stages: Array<{ key: LifecycleState; label: string }> = [
  { key: "DRAFT", label: "Situation" },
  { key: "CANDIDATE_SELECTED", label: "Candidate" },
  { key: "GUIDANCE_VERIFYING", label: "Guidance" },
  { key: "SEMANTIC_PASSED", label: "Semantic pass" },
  { key: "PREFLIGHT_PASSED", label: "Simulation" },
  { key: "APPROVED", label: "Approval" },
  { key: "PUBLISHED", label: "Publication" },
];

const progressIndex: Record<LifecycleState, number> = {
  DRAFT: 0,
  CANDIDATE_SELECTED: 1,
  GUIDANCE_VERIFYING: 2,
  PREFLIGHT_BLOCKED: 2,
  SEMANTIC_PASSED: 3,
  SIMULATION_RUNNING: 3,
  PREFLIGHT_PASSED: 4,
  APPROVED: 5,
  PUBLISHING: 5,
  PUBLISHED: 6,
};

export function PreflightStepper({ state }: { state: LifecycleState | null }) {
  const current = state ? progressIndex[state] : -1;
  const blocked = state === "PREFLIGHT_BLOCKED";
  return (
    <section className="panel p-4" aria-label="Golden Flow progress">
      <div className="flex items-center justify-between gap-3">
        <div>
          <p className="eyebrow">Golden Flow status</p>
          <p className="mt-1 text-sm font-bold text-slate-900" aria-live="polite">
            {blocked ? "Publication blocked pending targeted repair" : state?.split("_").join(" ") ?? "Loading"}
          </p>
        </div>
        {blocked && <ShieldAlert className="text-red-700" aria-hidden="true" />}
      </div>
      <ol className="mt-4 grid grid-cols-2 gap-2 sm:grid-cols-4 lg:grid-cols-7">
        {stages.map((stage, index) => {
          const complete = index < current || state === "PUBLISHED";
          const active = index === current;
          const failed = blocked && stage.key === "GUIDANCE_VERIFYING";
          return (
            <li
              key={stage.key}
              aria-current={active ? "step" : undefined}
              className={`flex min-w-0 items-center gap-2 rounded-lg border px-3 py-2 text-xs font-bold ${
                failed
                  ? "border-red-300 bg-red-50 text-red-900"
                  : active
                    ? "border-blue-500 bg-blue-50 text-blue-950"
                    : complete
                      ? "border-emerald-200 bg-emerald-50 text-emerald-900"
                      : "border-slate-200 bg-white text-slate-500"
              }`}
            >
              {complete ? <Check size={14} /> : <Circle size={12} />}
              <span className="truncate">{stage.label}</span>
            </li>
          );
        })}
      </ol>
    </section>
  );
}
