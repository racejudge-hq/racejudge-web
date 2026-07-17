"use client";

import dynamic from "next/dynamic";
import type { ConsistencyRow } from "./ConsistencyChartsInner";

// Plotly touches `window` at import time, so load the charts client-side only.
const Inner = dynamic(() => import("./ConsistencyChartsInner"), {
  ssr: false,
  loading: () => (
    <div className="h-80 flex items-center justify-center text-sm text-gray-500">
      Loading charts…
    </div>
  ),
});

export default function ConsistencyCharts({ data }: { data: ConsistencyRow[] }) {
  return <Inner data={data} />;
}
