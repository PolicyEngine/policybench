import type { NextConfig } from "next";

// Note URLs that moved. The BBCE note, first published September 23, was
// republished as of October 5 on release dashboard-data-20260930; its old URL
// stays a permanent link to it.
export const noteRedirects = [
  {
    source: "/notes/2026-09-23-five-snap-households-bbce",
    destination: "/notes/2026-10-05-five-snap-households-bbce",
    permanent: true,
  },
];

const nextConfig: NextConfig = {
  reactStrictMode: true,
  async redirects() {
    return noteRedirects;
  },
};

export default nextConfig;
