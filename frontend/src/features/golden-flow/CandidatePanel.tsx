import { CheckCircle2, CircleX, Route } from "lucide-react";
import type { Candidate } from "../../types";

interface CandidatePanelProps {
  candidates: Candidate[];
  selectedCandidateId: string | null;
  disabled: boolean;
  onSelect: (candidate: Candidate) => void;
}

export function CandidatePanel({ candidates, selectedCandidateId, disabled, onSelect }: CandidatePanelProps) {
  return (
    <section className="panel p-5" aria-labelledby="candidate-title">
      <p className="eyebrow">Candidate precheck</p>
      <h2 id="candidate-title" className="section-title">Choose a viable intervention</h2>
      <p className="mt-2 text-sm text-slate-600">Preliminary ordering uses deterministic topology and accessibility checks. Dynamic flow comparison runs later.</p>
      <div className="mt-4 grid gap-3">
        {candidates.map((candidate) => {
          const selected = candidate.id === selectedCandidateId || candidate.selected;
          return (
            <button
              key={candidate.id}
              type="button"
              disabled={disabled || !candidate.is_viable}
              onClick={() => onSelect(candidate)}
              className={`rounded-xl border p-4 text-left transition focus-visible:ring-2 focus-visible:ring-blue-600 ${
                selected
                  ? "border-blue-600 bg-blue-50"
                  : candidate.is_viable
                    ? "border-slate-200 bg-white hover:border-blue-300"
                    : "cursor-not-allowed border-red-200 bg-red-50/70"
              }`}
            >
              <div className="flex items-start justify-between gap-4">
                <div className="flex gap-3">
                  <span className={`mt-0.5 grid h-8 w-8 place-items-center rounded-lg ${candidate.is_viable ? "bg-emerald-100 text-emerald-700" : "bg-red-100 text-red-700"}`}>
                    {candidate.is_viable ? <CheckCircle2 size={18} /> : <CircleX size={18} />}
                  </span>
                  <div>
                    <p className="font-bold text-slate-950">{candidate.title}</p>
                    <p className="mt-1 text-xs uppercase tracking-wide text-slate-500">
                      {candidate.is_viable ? `Viable · preliminary rank ${candidate.preliminary_rank ?? "—"}` : "Rejected"}
                    </p>
                  </div>
                </div>
                <Route size={18} className="text-slate-400" aria-hidden="true" />
              </div>
              {candidate.rejections?.map((rejection) => (
                <p key={rejection.reason_code} className="mt-3 rounded-lg bg-white/75 px-3 py-2 text-sm text-red-800">
                  <strong>{rejection.reason_code}:</strong> {rejection.message}
                </p>
              ))}
            </button>
          );
        })}
      </div>
    </section>
  );
}
