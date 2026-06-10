import type { MetadataRoute } from "next";

export default function sitemap(): MetadataRoute.Sitemap {
  return [
    {
      url: "https://policybench.org/",
      changeFrequency: "weekly",
      priority: 1,
    },
    {
      url: "https://policybench.org/paper",
      changeFrequency: "monthly",
      priority: 0.7,
    },
  ];
}
