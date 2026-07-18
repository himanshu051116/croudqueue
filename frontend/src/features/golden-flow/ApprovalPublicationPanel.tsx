import { AlertTriangle, BadgeCheck, RadioTower, ShieldCheck } from "lucide-react";
import type { LifecycleState, PublicationDelivery } from "../../types";

interface Props {
  state: LifecycleState | null;
  expectedBundleHash: string | null;
  decisionBundleHash: string | null;
  approval: {
    approver_role: string;
    approved_at: string;
    approval_note: string | null;
  } | null;
  deliveries: PublicationDelivery[];
  busy: boolean;
  onApprove: () => void;
  onPublish: () => void;
}

export function ApprovalPublicationPanel({
  state,
  expectedBundleHash,
  decisionBundleHash,
  approval,
  deliveries,
  busy,
  onApprove,
  onPublish,
}: Props) {
  const surfaces = [
    ["FAN_APP", "Fan App (EN/ES/FR)"],
    ["PA", "Public Address (EN/ES/FR)"],
    ["SIGNAGE", "Digital Signage (derived)"],
    ["VOLUNTEER_DEVICE", "Volunteer Devices (derived)"],
  ];
  const publishedWithoutEvidence = state === "PUBLISHED" && deliveries.length === 0;

  return (
    <section className="panel p-5" aria-labelledby="approval-title">
      <p className="eyebrow">Human-controlled publication</p>
      <h2 id="approval-title" className="section-title">
        Approval and simulated delivery
      </h2>
      <p className="mt-2 text-sm text-slate-600">
        The server recomputes the evidence bundle under a row lock for the
        simulated supervisor identity. No guidance can publish before approval.
      </p>
      {state === "PREFLIGHT_PASSED" && expectedBundleHash && (
        <button
          type="button"
          className="primary-button mt-4"
          onClick={onApprove}
          disabled={busy}
        >
          <ShieldCheck size={17} /> Approve evidence bundle
        </button>
      )}
      {state === "APPROVED" && (
        <div className="mt-4">
          <div className="flex items-center gap-2 rounded-xl bg-emerald-50 p-4 font-black text-emerald-900">
            <BadgeCheck size={20} /> Decision bundle approved
          </div>
          <button
            type="button"
            className="primary-button mt-4"
            onClick={onPublish}
            disabled={busy}
          >
            <RadioTower size={17} /> Simulate live publication
          </button>
        </div>
      )}
      {approval && (
        <p className="mt-3 text-xs text-slate-500">
          Approved by simulated {approval.approver_role.toLowerCase()} at{" "}
          {new Date(approval.approved_at).toLocaleString()}
          {approval.approval_note ? ` · ${approval.approval_note}` : ""}
        </p>
      )}
      {publishedWithoutEvidence && (
        <div className="mt-5 flex items-start gap-2 rounded-xl border border-red-300 bg-red-50 p-4 text-sm font-bold text-red-900" role="alert">
          <AlertTriangle className="mt-0.5 shrink-0" size={18} />
          Published state has no persisted delivery evidence. Reload or inspect
          the audit record before relying on this state.
        </div>
      )}
      {deliveries.length > 0 && (
        <div className="mt-5">
          <div className="rounded-xl bg-blue-50 p-4 font-black text-blue-950">
            Guidance published — simulated recipient surfaces
          </div>
          <div className="mt-3 grid gap-3 sm:grid-cols-2">
            {surfaces.map(([surface, label]) => {
              const items = deliveries.filter((item) => item.surface === surface);
              const delivered = items.filter((item) => item.status === "DELIVERED");
              return (
                <div
                  key={surface}
                  className="rounded-xl border border-slate-200 bg-slate-50 p-4"
                >
                  <p className="font-bold text-slate-950">{label}</p>
                  <p className="mt-1 text-sm text-emerald-700">
                    {delivered.length}/{items.length} persisted deliveries complete
                  </p>
                </div>
              );
            })}
          </div>
        </div>
      )}
      {(expectedBundleHash || decisionBundleHash) && (
        <details className="mt-4 rounded-lg bg-slate-50 p-3 text-xs">
          <summary className="cursor-pointer font-bold">
            Server bundle hash evidence
          </summary>
          <p className="mt-2 break-all font-mono text-slate-600">
            {decisionBundleHash ?? expectedBundleHash}
          </p>
        </details>
      )}
    </section>
  );
}
