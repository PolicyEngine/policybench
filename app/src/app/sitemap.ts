import type { MetadataRoute } from "next";

import rawData from "../data-summary.json";
import { listModels } from "../lib/modelPage";
import type { DashboardBundle } from "../types";

export default function sitemap(): MetadataRoute.Sitemap {
  const modelEntries = listModels(rawData as DashboardBundle).map((id) => ({
    url: `https://policybench.org/model/${id}`,
    changeFrequency: "monthly" as const,
    priority: 0.6,
  }));
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
    ...modelEntries,
  ];
}
