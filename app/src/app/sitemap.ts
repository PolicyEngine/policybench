import type { MetadataRoute } from "next";

import rawData from "../data-summary.json";
import { listModels } from "../lib/modelPage";
import { notes } from "../notes";
import type { DashboardBundle } from "../types";

export default function sitemap(): MetadataRoute.Sitemap {
  const modelEntries = listModels(rawData as DashboardBundle).map((id) => ({
    url: `https://policybench.org/model/${id}`,
    changeFrequency: "monthly" as const,
    priority: 0.6,
  }));
  const noteEntries = notes.map((note) => ({
    url: `https://policybench.org/notes/${note.slug}`,
    changeFrequency: "monthly" as const,
    priority: 0.5,
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
    {
      url: "https://policybench.org/notes",
      changeFrequency: "weekly",
      priority: 0.7,
    },
    {
      url: "https://policybench.org/expand",
      changeFrequency: "monthly",
      priority: 0.5,
    },
    ...noteEntries,
    ...modelEntries,
  ];
}
