"use client";

import dynamic from "next/dynamic";
import type { CircuitPoint } from "./CircuitMapInner";

// MapLibre needs the browser (window/DOM), so load it client-side only.
const Inner = dynamic(() => import("./CircuitMapInner"), {
  ssr: false,
  loading: () => (
    <div className="h-[520px] flex items-center justify-center text-sm text-gray-500 border border-gray-200 dark:border-gray-800 rounded-lg">
      Loading map…
    </div>
  ),
});

export default function CircuitMap({ points }: { points: CircuitPoint[] }) {
  return <Inner points={points} />;
}

export type { CircuitPoint };
