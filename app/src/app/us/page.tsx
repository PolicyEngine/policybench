import type { Metadata } from "next";
import App from "../../App";

export const metadata: Metadata = {
  title: "United States",
};

export default function UnitedStatesPage() {
  return <App initialView="us" />;
}
