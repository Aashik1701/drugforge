import React, { useMemo, useState } from 'react';
import { Info } from 'lucide-react';

/**
 * The recall-vs-budget frontier as a hand-rolled SVG (no charting dependency --
 * recharts is not installed, and a ~1 KB SVG matches the backend's own
 * funnel.frontier.py which also emits SVG). Lets the user SEE the trade-off
 * before picking N: how many of the docking baseline's true top hits a given
 * docking budget recovers.
 *
 * Y axis = molecules of the baseline top-10 recovered. Two curves:
 *   recall@10 literal   (primary metric, thick)
 *   recall@5  literal   (secondary, thin)
 * Vertical marker at the recommended operating point. Click the plot to set N.
 */
const W = 640;
const H = 240;
const PAD = { l: 40, r: 16, t: 16, b: 34 };
const PW = W - PAD.l - PAD.r;
const PH = H - PAD.t - PAD.b;

export default function FrontierChart({
  rows,
  selectedN,
  onSelectN,
  recommendedN = 10,
  setSize = 45,
}) {
  const [hoverN, setHoverN] = useState(null);

  const xmax = rows?.length ? rows[rows.length - 1].N : setSize;
  const x = (n) => PAD.l + (PW * n) / xmax;
  const y = (v) => PAD.t + PH * (1 - v / 10);

  const path = useMemo(() => {
    if (!rows?.length) return { r10: '', r5: '' };
    const line = (key) => rows.map((r) => `${x(r.N).toFixed(1)},${y(r[key]).toFixed(1)}`).join(' ');
    return { r10: line('recall10_literal'), r5: line('recall5_literal') };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [rows, xmax]);

  const rowAt = (n) => rows?.find((r) => r.N === n) || null;
  const active = rowAt(hoverN) || rowAt(selectedN);

  const handlePointer = (evt) => {
    if (!onSelectN) return;
    const svg = evt.currentTarget;
    const rect = svg.getBoundingClientRect();
    const px = ((evt.clientX - rect.left) / rect.width) * W;
    const n = Math.round(((px - PAD.l) / PW) * xmax);
    onSelectN(Math.min(xmax, Math.max(1, n)));
  };

  if (!rows) {
    return (
      <div className="flex items-start gap-3 rounded-xl border border-amber-500/30 bg-amber-500/10 p-4 text-sm text-amber-700 dark:text-amber-300">
        <Info className="mt-0.5 h-4 w-4 shrink-0" />
        <div>
          <p className="font-medium">No cached frontier curve for this set.</p>
          <p className="mt-1 text-amber-600/90 dark:text-amber-400/90">
            The trade-off preview needs a pre-computed baseline (the offline
            <code className="mx-1 rounded bg-black/10 px-1 dark:bg-white/10">funnel.frontier</code>
            tool). You can still choose N below; you just won't see how much a
            given budget recovers until the run finishes.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div>
      <svg
        viewBox={`0 0 ${W} ${H}`}
        className="w-full cursor-crosshair select-none"
        role="img"
        aria-label="Recall versus docking budget frontier"
        onMouseMove={(e) => {
          const rect = e.currentTarget.getBoundingClientRect();
          const px = ((e.clientX - rect.left) / rect.width) * W;
          const n = Math.round(((px - PAD.l) / PW) * xmax);
          setHoverN(Math.min(xmax, Math.max(1, n)));
        }}
        onMouseLeave={() => setHoverN(null)}
        onClick={handlePointer}
      >
        {/* grid + y labels */}
        {[0, 2, 4, 6, 8, 10].map((v) => (
          <g key={v}>
            <line x1={PAD.l} x2={PAD.l + PW} y1={y(v)} y2={y(v)} className="stroke-gray-200 dark:stroke-gray-700" strokeWidth="1" />
            <text x={PAD.l - 6} y={y(v) + 3} textAnchor="end" className="fill-gray-400 text-[9px]">{v}</text>
          </g>
        ))}
        {/* x labels */}
        {Array.from({ length: Math.floor(xmax / 10) + 1 }, (_, i) => i * 10).filter((n) => n > 0 || xmax < 10).map((n) => (
          <text key={n} x={x(n)} y={H - 18} textAnchor="middle" className="fill-gray-400 text-[9px]">{n}</text>
        ))}
        <text x={PAD.l + PW / 2} y={H - 4} textAnchor="middle" className="fill-gray-400 text-[9px]">
          docking budget N  (Vina jobs = 4 x N)
        </text>

        {/* recommended-N marker */}
        {recommendedN <= xmax && (
          <g>
            <line x1={x(recommendedN)} x2={x(recommendedN)} y1={PAD.t} y2={PAD.t + PH}
              className="stroke-emerald-500/70" strokeWidth="1.5" strokeDasharray="4 3" />
            <text x={x(recommendedN)} y={PAD.t + 9} textAnchor="middle" className="fill-emerald-600 text-[9px] font-medium">
              recommended
            </text>
          </g>
        )}

        {/* curves */}
        <polyline points={path.r5} fill="none" className="stroke-violet-400" strokeWidth="1.5" />
        <polyline points={path.r10} fill="none" className="stroke-teal-400" strokeWidth="2.5" />

        {/* selected N */}
        {selectedN != null && selectedN <= xmax && (
          <line x1={x(selectedN)} x2={x(selectedN)} y1={PAD.t} y2={PAD.t + PH}
            className="stroke-gray-500 dark:stroke-gray-300" strokeWidth="1.25" />
        )}
        {active && (
          <>
            <circle cx={x(active.N)} cy={y(active.recall10_literal)} r="3.5" className="fill-teal-400" />
            <circle cx={x(active.N)} cy={y(active.recall5_literal)} r="3" className="fill-violet-400" />
          </>
        )}
      </svg>

      <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-[11px] text-gray-500 dark:text-gray-400">
        <span className="flex items-center gap-1.5"><span className="inline-block h-0.5 w-4 bg-teal-400" /> recall@10 literal (primary)</span>
        <span className="flex items-center gap-1.5"><span className="inline-block h-0.5 w-4 bg-violet-400" /> recall@5 literal</span>
        {active && (
          <span className="ml-auto font-mono text-gray-700 dark:text-gray-200">
            N={active.N}: recovers {active.recall10_literal}/10 top-10 &amp; {active.recall5_literal}/5 top-5
            &nbsp;·&nbsp; {active.jobs} jobs
            {active.speedup_vs_full != null && <> &nbsp;·&nbsp; {active.speedup_vs_full}x faster than docking all</>}
          </span>
        )}
      </div>
    </div>
  );
}
