"use client";

import { useEffect, useRef } from "react";
import * as d3 from "d3";
import createPlotlyComponent from "react-plotly.js/factory";
import Plotly from "plotly.js-dist-min";

const Plot = createPlotlyComponent(Plotly);

export interface ConsistencyRow {
  infraction_category: string;
  season: number;
  total: number;
  nfa_pct: number;
  rep_pct: number;
  time_penalty_pct: number;
  grid_dt_pct: number;
  dsq_pct: number;
  avg_penalty_points: number;
}

const PENALTY_SERIES: { key: keyof ConsistencyRow; label: string; color: string }[] = [
  { key: "nfa_pct", label: "No action", color: "#6b7280" },
  { key: "rep_pct", label: "Reprimand", color: "#eab308" },
  { key: "time_penalty_pct", label: "Time penalty", color: "#f97316" },
  { key: "grid_dt_pct", label: "Grid / drive-through", color: "#ef4444" },
  { key: "dsq_pct", label: "Disqualification", color: "#7f1d1d" },
];

function label(s: string) {
  return s.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

/** Plotly stacked bar: penalty-type distribution per infraction (latest season). */
function PenaltyMix({ data }: { data: ConsistencyRow[] }) {
  const latest = Math.max(...data.map((r) => r.season));
  const rows = data.filter((r) => r.season === latest);
  const cats = rows.map((r) => label(r.infraction_category));

  const traces = PENALTY_SERIES.map((s) => ({
    type: "bar" as const,
    name: s.label,
    x: cats,
    y: rows.map((r) => r[s.key] as number),
    marker: { color: s.color },
    hovertemplate: `%{x}<br>${s.label}: %{y}%<extra></extra>`,
  }));

  return (
    <Plot
      data={traces}
      layout={{
        barmode: "stack",
        title: { text: `Penalty mix by infraction — ${latest}`, font: { size: 15 } },
        height: 360,
        margin: { t: 40, r: 10, b: 80, l: 40 },
        paper_bgcolor: "rgba(0,0,0,0)",
        plot_bgcolor: "rgba(0,0,0,0)",
        font: { color: "#9ca3af", size: 11 },
        legend: { orientation: "h", y: -0.25 },
        yaxis: { ticksuffix: "%", gridcolor: "rgba(128,128,128,0.15)" },
        xaxis: { tickangle: -20 },
      }}
      config={{ displayModeBar: false, responsive: true }}
      style={{ width: "100%" }}
      useResizeHandler
    />
  );
}

/** D3 heatmap: average penalty points by infraction (rows) × season (cols). */
function SeverityHeatmap({ data }: { data: ConsistencyRow[] }) {
  const ref = useRef<SVGSVGElement | null>(null);

  useEffect(() => {
    if (!ref.current) return;
    const seasons = [...new Set(data.map((r) => r.season))].sort((a, b) => a - b);
    const infractions = [...new Set(data.map((r) => r.infraction_category))];
    const cell = 46;
    const left = 150;
    const top = 24;
    const w = left + seasons.length * cell + 20;
    const h = top + infractions.length * cell + 10;

    const svg = d3.select(ref.current);
    svg.selectAll("*").remove();
    svg.attr("viewBox", `0 0 ${w} ${h}`).attr("width", "100%").attr("height", h);

    const maxPts = d3.max(data, (d) => d.avg_penalty_points) ?? 2;
    const color = d3.scaleSequential(d3.interpolateOrRd).domain([0, maxPts]);
    const get = (inf: string, s: number) =>
      data.find((d) => d.infraction_category === inf && d.season === s)?.avg_penalty_points;

    seasons.forEach((s, i) =>
      svg.append("text").attr("x", left + i * cell + cell / 2).attr("y", top - 8)
        .attr("text-anchor", "middle").attr("font-size", 11).attr("fill", "#9ca3af").text(String(s)),
    );

    infractions.forEach((inf, r) => {
      svg.append("text").attr("x", left - 8).attr("y", top + r * cell + cell / 2 + 4)
        .attr("text-anchor", "end").attr("font-size", 11).attr("fill", "#9ca3af").text(label(inf));
      seasons.forEach((s, c) => {
        const v = get(inf, s);
        const g = svg.append("g");
        g.append("rect").attr("x", left + c * cell).attr("y", top + r * cell)
          .attr("width", cell - 3).attr("height", cell - 3).attr("rx", 3)
          .attr("fill", v == null ? "rgba(128,128,128,0.1)" : color(v));
        g.append("title").text(`${label(inf)} ${s}: ${v == null ? "n/a" : v.toFixed(1)} pts`);
        if (v != null)
          g.append("text").attr("x", left + c * cell + (cell - 3) / 2)
            .attr("y", top + r * cell + (cell - 3) / 2 + 4).attr("text-anchor", "middle")
            .attr("font-size", 10).attr("fill", v > maxPts * 0.6 ? "#fff" : "#1f2937")
            .text(v.toFixed(1));
      });
    });
  }, [data]);

  return (
    <div>
      <h3 className="text-sm font-semibold mb-2 text-gray-700 dark:text-gray-300">
        Average penalty points (severity)
      </h3>
      <svg ref={ref} role="img" aria-label="Penalty severity heatmap" />
    </div>
  );
}

export default function ConsistencyChartsInner({ data }: { data: ConsistencyRow[] }) {
  if (!data.length) return null;
  return (
    <div className="space-y-10">
      <PenaltyMix data={data} />
      <SeverityHeatmap data={data} />
    </div>
  );
}
