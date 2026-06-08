import type { MetadataRoute } from "next";

const SITE_URL = process.env.NEXT_PUBLIC_SITE_URL ?? "https://racejudge.com";

const STATIC_ROUTES = [
  { path: "",            priority: 1.0,  changeFrequency: "daily"   as const },
  { path: "/decisions",  priority: 0.9,  changeFrequency: "daily"   as const },
  { path: "/precedents", priority: 0.9,  changeFrequency: "daily"   as const },
  { path: "/predict",    priority: 0.8,  changeFrequency: "weekly"  as const },
  { path: "/consistency",priority: 0.8,  changeFrequency: "weekly"  as const },
  { path: "/guidelines", priority: 0.7,  changeFrequency: "monthly" as const },
  { path: "/live",       priority: 0.6,  changeFrequency: "hourly"  as const },
  { path: "/review",     priority: 0.7,  changeFrequency: "weekly"  as const },
  { path: "/api",        priority: 0.5,  changeFrequency: "monthly" as const },
];

export default function sitemap(): MetadataRoute.Sitemap {
  const now = new Date();
  return STATIC_ROUTES.map(({ path, priority, changeFrequency }) => ({
    url:              `${SITE_URL}${path}`,
    lastModified:     now,
    changeFrequency,
    priority,
  }));
}
