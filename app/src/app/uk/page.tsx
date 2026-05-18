import type { Metadata } from "next";
import App from "../../App";

export const metadata: Metadata = {
  title: "United Kingdom",
};

export default function UnitedKingdomPage() {
  return <App initialView="uk" />;
}
