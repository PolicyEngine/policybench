import Link from "next/link";

import ExpandModelCount from "./ExpandModelCount";

export function FrontierCoverageCopy({ modelCount }: { modelCount: number }) {
  return (
    <>
      The{" "}
      <Link href="/" className="text-primary hover:underline">
        public board
      </Link>{" "}
      <ExpandModelCount modelCount={modelCount} context="frontier" /> on 100
      real households.
    </>
  );
}

export function BoardCoverageCopy({ modelCount }: { modelCount: number }) {
  return (
    <>
      One program family: SNAP, Medicaid, child care, or tax credits, {" "}
      <ExpandModelCount modelCount={modelCount} context="board" />.
    </>
  );
}
