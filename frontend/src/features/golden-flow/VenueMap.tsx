import type { Snapshot, VenueTopology } from "../../types";

interface VenueMapProps {
  topology: VenueTopology | null;
  snapshot: Snapshot | null;
  scenarioName: string;
}

export function VenueMap({ topology, snapshot, scenarioName }: VenueMapProps) {
  if (!topology) {
    return <section className="panel min-h-[360px] animate-pulse" aria-label="Loading venue map" />;
  }
  const nodesById = new Map(Object.values(topology.nodes).map((node) => [node.id, node]));
  const gateCPressure = snapshot?.nodes_state["node-gate-c"]?.pressure ?? 0.78;
  const liftOffline = snapshot?.assets_state["asset-lift-d2"]?.status === "OFFLINE";
  const textState = [
    `Synthetic ${topology.name} topology for ${scenarioName}.`,
    `Gate C pressure is ${Math.round(gateCPressure * 100)} percent.`,
    liftOffline
      ? "Lift D2 is unavailable. The asset-dependent route is interrupted."
      : "Lift D2 is operational.",
    "A dashed blue path identifies the protected accessible route.",
  ].join(" ");

  return (
    <section className="panel overflow-hidden" aria-labelledby="venue-map-title">
      <div className="flex flex-wrap items-start justify-between gap-3 border-b border-slate-200 p-4">
        <div>
          <p className="eyebrow">Synthetic live venue state</p>
          <h2 id="venue-map-title" className="section-title">Aurora Stadium</h2>
          <p className="mt-1 text-sm text-slate-600">Backend topology · {topology.reference_version}</p>
        </div>
        <div className="flex flex-wrap gap-3 text-xs font-semibold text-slate-600" aria-label="Map legend">
          <span><span className="mr-1 inline-block w-5 border-t-2 border-dashed border-blue-600" /> Protected path</span>
          <span><span className="mr-1 inline-block w-5 border-t-2 border-dashed border-amber-600" /> Asset-dependent</span>
          <span><span className="mr-1 inline-block h-2 w-2 rounded-full bg-red-600" /> High pressure</span>
        </div>
      </div>
      <div className="bg-slate-50 p-3 sm:p-5">
        <svg viewBox="0 0 600 400" role="img" aria-labelledby="venue-map-title venue-map-desc" className="h-auto w-full">
          <desc id="venue-map-desc">{textState}</desc>
          <rect x="145" y="65" width="310" height="245" rx="76" fill="#fff" stroke="#cbd5e1" strokeWidth="4" />
          <rect x="210" y="112" width="180" height="150" rx="50" fill="#f8fafc" stroke="#e2e8f0" strokeWidth="3" />
          {Object.entries(topology.edges).map(([key, edge]) => {
            const source = nodesById.get(edge.source_id);
            const target = nodesById.get(edge.target_id);
            if (!source || !target) return null;
            const closed = snapshot?.edges_state[key]?.is_active === false || edge.is_active === false;
            const routeProtected = edge.protected;
            const liftDependent = topology.routes["route-lift-dependent"]?.waypoints.some(
              (_waypoint, index, points) =>
                index < points.length - 1 &&
                points[index] === source.stable_key &&
                points[index + 1] === target.stable_key,
            );
            return (
              <line
                key={key}
                x1={source.x}
                y1={source.y}
                x2={target.x}
                y2={target.y}
                stroke={closed ? "#dc2626" : routeProtected ? "#2563eb" : liftDependent ? "#d97706" : "#cbd5e1"}
                strokeWidth={routeProtected ? 4 : 2.5}
                strokeDasharray={closed ? "4 5" : routeProtected || liftDependent ? "8 5" : undefined}
                opacity={closed ? 0.75 : 1}
              />
            );
          })}
          {Object.entries(topology.nodes).map(([key, node]) => {
            const highPressure = key === "node-gate-c" && gateCPressure >= 0.8;
            const isGate = node.node_type.toUpperCase().includes("GATE");
            return (
              <g key={key} data-testid={`venue-node-${key}`}>
                {highPressure && <circle cx={node.x} cy={node.y} r="29" fill="#fee2e2" stroke="#ef4444" strokeWidth="2" />}
                <circle cx={node.x} cy={node.y} r={isGate ? 14 : 8} fill={isGate ? "#0f172a" : "#fff"} stroke="#64748b" strokeWidth="2" />
                <text x={node.x} y={node.y + (isGate ? 31 : 22)} textAnchor="middle" fontSize="11" fontWeight="700" fill="#334155">
                  {node.name}
                </text>
                {highPressure && (
                  <text x={node.x} y={node.y - 24} textAnchor="middle" fontSize="12" fontWeight="800" fill="#b91c1c">
                    {Math.round(gateCPressure * 100)}%
                  </text>
                )}
              </g>
            );
          })}
          <g data-testid="lift-d2-status">
            <rect x="408" y="167" width="62" height="32" rx="8" fill={liftOffline ? "#fee2e2" : "#dcfce7"} stroke={liftOffline ? "#dc2626" : "#16a34a"} strokeWidth="2" />
            <text x="439" y="187" textAnchor="middle" fontSize="11" fontWeight="800" fill={liftOffline ? "#991b1b" : "#166534"}>
              Lift D2 {liftOffline ? "OFF" : "ON"}
            </text>
          </g>
        </svg>
      </div>
      <details className="border-t border-slate-200 p-4 text-sm text-slate-700">
        <summary className="cursor-pointer font-bold text-slate-900">Text alternative for the venue map</summary>
        <p className="mt-2" data-testid="venue-text-alternative">{textState}</p>
      </details>
    </section>
  );
}
