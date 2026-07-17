"use client";

import { useEffect, useRef } from "react";
import maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";

export interface CircuitPoint {
  name: string;
  country: string;
  lngLat: [number, number];
  count?: number;
}

export default function CircuitMapInner({ points }: { points: CircuitPoint[] }) {
  const ref = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);

  useEffect(() => {
    if (!ref.current || mapRef.current) return;
    const map = new maplibregl.Map({
      container: ref.current,
      style: {
        version: 8,
        sources: {
          osm: {
            type: "raster",
            tiles: ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"],
            tileSize: 256,
            attribution: "© OpenStreetMap contributors",
          },
        },
        layers: [{ id: "osm", type: "raster", source: "osm" }],
      },
      center: [12, 30],
      zoom: 1.25,
    });
    map.addControl(new maplibregl.NavigationControl(), "top-right");
    mapRef.current = map;

    const maxCount = Math.max(1, ...points.map((p) => p.count ?? 1));
    for (const p of points) {
      const size = 12 + 24 * ((p.count ?? 1) / maxCount);
      const el = document.createElement("div");
      Object.assign(el.style, {
        width: `${size}px`,
        height: `${size}px`,
        background: "rgba(225,6,0,0.72)",
        border: "2px solid #fff",
        borderRadius: "50%",
        cursor: "pointer",
        boxShadow: "0 0 0 1px rgba(0,0,0,0.25)",
      });
      new maplibregl.Marker({ element: el })
        .setLngLat(p.lngLat)
        .setPopup(
          new maplibregl.Popup({ offset: 12 }).setHTML(
            `<strong>${p.name}</strong><br/>${p.country}` +
              (p.count != null ? `<br/>${p.count} incidents` : ""),
          ),
        )
        .addTo(map);
    }

    return () => {
      map.remove();
      mapRef.current = null;
    };
  }, [points]);

  return (
    <div
      ref={ref}
      className="w-full h-[520px] rounded-lg overflow-hidden border border-gray-200 dark:border-gray-800"
    />
  );
}
