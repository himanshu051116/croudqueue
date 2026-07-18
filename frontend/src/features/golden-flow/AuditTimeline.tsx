import { CheckCircle2, Clock3 } from "lucide-react";
import type { AuditResponse } from "../../types";

export function AuditTimeline({ audit }: { audit: AuditResponse | null }) {
  return (
    <section className="panel p-5" aria-labelledby="audit-title">
      <div className="flex items-center justify-between gap-3">
        <div>
          <p className="eyebrow">Authoritative PostgreSQL evidence</p>
          <h2 id="audit-title" className="section-title">Audit timeline</h2>
        </div>
        {audit?.chain_valid && <span className="flex items-center gap-1 text-xs font-bold text-emerald-700"><CheckCircle2 size={15} /> Hash chain valid</span>}
      </div>
      {!audit?.events.length ? (
        <p className="mt-4 text-sm text-slate-500">Audit events appear as the Golden Flow progresses.</p>
      ) : (
        <ol className="mt-5 space-y-3">
          {audit.events.map((event) => (
            <li key={event.id} className="grid grid-cols-[32px_1fr] gap-3">
              <span className="grid h-8 w-8 place-items-center rounded-full bg-slate-100 text-slate-600"><Clock3 size={15} /></span>
              <div className="rounded-xl border border-slate-200 bg-slate-50 p-3">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <p className="font-bold text-slate-950">{event.event_type.split("_").join(" ")}</p>
                  <time className="text-xs text-slate-500">#{event.sequence_number} · {new Date(event.created_at).toLocaleTimeString()}</time>
                </div>
                <p className="mt-2 truncate font-mono text-[10px] text-slate-400">{event.event_hash}</p>
              </div>
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}
