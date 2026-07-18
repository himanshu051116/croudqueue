import { AlertTriangle, CheckCircle2, Languages, Wrench } from "lucide-react";
import type { Diagnostic, GuidanceVariant, LifecycleState } from "../../types";

interface GuidancePanelProps {
  variants: GuidanceVariant[];
  diagnostics: Diagnostic[];
  state: LifecycleState | null;
  gir: Record<string, unknown> | null;
  provenance: Record<string, unknown> | null;
  injectFault: boolean;
  faultInjectionAvailable: boolean;
  busy: boolean;
  onInjectFaultChange: (value: boolean) => void;
  onGenerate: () => void;
  onRepair: () => void;
}

const languageLabel: Record<string, string> = { en: "English", es: "Español", fr: "Français" };

export function GuidancePanel({
  variants,
  diagnostics,
  state,
  gir,
  provenance,
  injectFault,
  faultInjectionAvailable,
  busy,
  onInjectFaultChange,
  onGenerate,
  onRepair,
}: GuidancePanelProps) {
  const blocked = state === "PREFLIGHT_BLOCKED";
  const canGenerate = state === "CANDIDATE_SELECTED";
  return (
    <section className="panel p-5" aria-labelledby="guidance-title">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="eyebrow">Zero-trust GenAI pipeline</p>
          <h2 id="guidance-title" className="section-title">Multilingual guidance verification</h2>
          <p className="mt-2 max-w-2xl text-sm text-slate-600">The GIR remains authoritative. Final rendered text is independently reverse-compiled before approval.</p>
        </div>
        <label className="flex items-center gap-2 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-sm font-semibold text-amber-950">
          <input
            type="checkbox"
            checked={injectFault}
            onChange={(event) => onInjectFaultChange(event.target.checked)}
            disabled={!canGenerate || busy || !faultInjectionAvailable}
          />
          Simulate semantic drift
        </label>
      </div>
      <p className="mt-2 text-xs font-semibold text-amber-800">{faultInjectionAvailable ? "Deliberate demonstration defect: omit only the Spanish Fan App mobility-assistance clause." : "Demo fault injection is disabled by server configuration."}</p>

      {(gir || provenance) && (
        <div className="mt-4 grid gap-3 lg:grid-cols-2">
          {provenance && (
            <div className="rounded-xl border border-slate-200 bg-slate-50 p-4 text-sm">
              <p className="font-black text-slate-950">Generation provenance</p>
              <p className="mt-1 text-slate-600">
                Provider: <strong>{String(provenance.provider ?? "unknown")}</strong> · Model: {String(provenance.model ?? "not called")}
              </p>
              <p className="mt-1 text-xs text-slate-500">
                Live requests {String(provenance.successful_request_count ?? 0)}/{String(provenance.request_count ?? 0)}
                {provenance.safe_error_code ? ` · ${String(provenance.safe_error_code)}` : ""}
              </p>
            </div>
          )}
          {gir && (
            <details className="rounded-xl border border-slate-200 bg-slate-50 p-4 text-sm">
              <summary className="cursor-pointer font-black text-slate-950">Authoritative Guidance Intermediate Representation</summary>
              <pre className="mt-3 max-h-72 overflow-auto whitespace-pre-wrap break-words text-xs text-slate-600">{JSON.stringify(gir, null, 2)}</pre>
            </details>
          )}
        </div>
      )}

      {canGenerate && (
        <button className="primary-button mt-4" type="button" onClick={onGenerate} disabled={busy}>
          <Languages size={17} /> Generate &amp; verify guidance
        </button>
      )}

      {blocked && (
        <div className="mt-5 rounded-xl border-2 border-red-300 bg-red-50 p-4" role="alert">
          <div className="flex items-center gap-2 font-black text-red-900"><AlertTriangle size={20} /> Semantic preflight blocked</div>
          {diagnostics.filter((item) => item.blocking).map((diagnostic) => (
            <div key={diagnostic.id ?? diagnostic.code} className="mt-3 rounded-lg bg-white p-3 text-sm text-red-900">
              <p className="font-mono font-bold">{diagnostic.code}</p>
              <p>{diagnostic.message}</p>
            </div>
          ))}
          <button className="primary-button mt-4 bg-red-700 hover:bg-red-800" type="button" onClick={onRepair} disabled={busy}>
            <Wrench size={17} /> Execute targeted repair
          </button>
        </div>
      )}

      {state === "SEMANTIC_PASSED" && (
        <div className="mt-5 flex items-center gap-2 rounded-xl border border-emerald-200 bg-emerald-50 p-4 font-bold text-emerald-900" role="status">
          <CheckCircle2 size={20} /> Semantic verification passed
        </div>
      )}

      {variants.length > 0 && (
        <div className="mt-5 grid gap-3 md:grid-cols-2 xl:grid-cols-3">
          {variants.map((variant) => (
            <article key={`${variant.language}-${variant.channel}-${variant.version}`} className={`rounded-xl border p-4 ${variant.language === "es" && variant.channel === "fan_app" && blocked ? "border-red-300 bg-red-50" : "border-slate-200 bg-slate-50"}`}>
              <div className="flex items-center justify-between gap-2">
                <h3 className="font-black text-slate-950">{languageLabel[variant.language]} · {variant.channel === "fan_app" ? "Fan App" : "PA"}</h3>
                <span className="rounded-full bg-white px-2 py-1 text-[10px] font-bold uppercase text-slate-500">v{variant.version}</span>
              </div>
              <p className="mt-3 whitespace-pre-line text-sm leading-6 text-slate-700">{variant.rendered_text}</p>
              <p className="mt-3 truncate font-mono text-[10px] text-slate-400">{variant.content_hash}</p>
            </article>
          ))}
        </div>
      )}
    </section>
  );
}
