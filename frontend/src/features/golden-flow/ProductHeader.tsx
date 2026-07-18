import { Activity, ShieldCheck, Sparkles } from "lucide-react";

interface ProductHeaderProps {
  geminiConfigured: boolean | null;
}

export function ProductHeader({ geminiConfigured }: ProductHeaderProps) {
  const aiLabel =
    geminiConfigured === null
      ? "Generation status loading"
      : geminiConfigured
        ? "Gemini connected"
        : "Controlled fallback ready";

  return (
    <header className="border-b border-slate-200 bg-white/95 px-4 py-4 shadow-sm sm:px-8">
      <div className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <div className="grid h-10 w-10 place-items-center rounded-xl bg-slate-950 text-white">
            <Activity aria-hidden="true" size={22} />
          </div>
          <div>
            <p className="text-xs font-bold uppercase tracking-[0.22em] text-blue-700">
              CrowdCue 26 · Guidance Preflight
            </p>
            <h1 className="text-xl font-black tracking-tight text-slate-950 sm:text-2xl">
              A message can be right for one fan. And wrong for the crowd.
            </h1>
          </div>
        </div>
        <div className="flex flex-wrap gap-2 text-xs font-semibold">
          <span className="status-pill">
            <Sparkles size={14} /> {aiLabel}
          </span>
          <span className="status-pill">
            <ShieldCheck size={14} /> Human approval required
          </span>
        </div>
      </div>
    </header>
  );
}
