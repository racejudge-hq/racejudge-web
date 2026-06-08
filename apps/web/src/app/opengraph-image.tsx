import { ImageResponse } from "next/og";

export const runtime = "edge";
export const size    = { width: 1200, height: 630 };
export const contentType = "image/png";

export default function OGImage() {
  return new ImageResponse(
    (
      <div
        style={{
          background: "#0a0a0a",
          width: "100%",
          height: "100%",
          display: "flex",
          flexDirection: "column",
          alignItems: "flex-start",
          justifyContent: "center",
          padding: "72px 80px",
          fontFamily: "sans-serif",
          position: "relative",
        }}
      >
        {/* Red accent bar */}
        <div
          style={{
            position: "absolute",
            top: 0,
            left: 0,
            width: "8px",
            height: "100%",
            background: "#dc2626",
          }}
        />

        {/* Wordmark */}
        <div
          style={{
            display: "flex",
            alignItems: "baseline",
            gap: "0px",
            marginBottom: "28px",
          }}
        >
          <span
            style={{
              fontSize: "80px",
              fontWeight: 800,
              color: "#ffffff",
              letterSpacing: "-2px",
              lineHeight: 1,
            }}
          >
            RACE
          </span>
          <span
            style={{
              fontSize: "80px",
              fontWeight: 800,
              color: "#dc2626",
              letterSpacing: "-2px",
              lineHeight: 1,
            }}
          >
            JUDGE
          </span>
        </div>

        {/* Tagline */}
        <div
          style={{
            fontSize: "28px",
            color: "#a3a3a3",
            fontWeight: 400,
            lineHeight: 1.4,
            maxWidth: "860px",
            marginBottom: "48px",
          }}
        >
          The Stewards&apos; Precedent Engine
        </div>

        {/* Stat pills */}
        <div style={{ display: "flex", gap: "20px" }}>
          {[
            ["1,085", "decisions indexed"],
            ["2019–2025", "seasons covered"],
            ["7 penalty classes", "ML prediction"],
          ].map(([num, label]) => (
            <div
              key={num}
              style={{
                display: "flex",
                flexDirection: "column",
                padding: "14px 24px",
                background: "#18181b",
                border: "1px solid #27272a",
                borderRadius: "8px",
                gap: "4px",
              }}
            >
              <span style={{ fontSize: "22px", fontWeight: 700, color: "#ffffff" }}>
                {num}
              </span>
              <span style={{ fontSize: "14px", color: "#71717a" }}>{label}</span>
            </div>
          ))}
        </div>

        {/* Domain */}
        <div
          style={{
            position: "absolute",
            bottom: "48px",
            right: "72px",
            fontSize: "18px",
            color: "#52525b",
            fontWeight: 500,
          }}
        >
          racejudge.com
        </div>
      </div>
    ),
    { ...size },
  );
}
