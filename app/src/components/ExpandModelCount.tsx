export default function ExpandModelCount({
  modelCount,
  context,
}: {
  modelCount: number;
  context: "frontier" | "board";
}) {
  return context === "frontier" ? (
    <>tests {modelCount} frontier models</>
  ) : (
    <>across all {modelCount} board models</>
  );
}
