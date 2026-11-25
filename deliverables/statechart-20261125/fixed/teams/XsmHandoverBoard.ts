export const title = "xsm handover: what happens to A's board item owner/A";

function heads(v: any): number[] {
  const nodes: number[] = v.nodes;
  const builtOn = new Set<number>();
  for (const n of nodes) for (const p of v.par[n] ?? []) builtOn.add(p);
  return nodes.filter((n) => !builtOn.has(n));
}

function item(v: any): string {
  const hs = heads(v);
  const notes = hs.filter((n) => v.kind[n] === "n").length;
  const content = hs.length - notes;
  if (hs.length === 1) return notes ? "owner/A says: handed over to B" : "owner/A holds one version";
  if (notes === 0) return `owner/A shows ${content} versions at once`;
  return `owner/A shows the handover note beside ${content} unforwarded version${content > 1 ? "s" : ""}`;
}

function owner(v: any): string {
  const carried: number[] = v.carried;
  if (v.skipped) return v.reported ? "owner/B gets nothing (item was in conflict, reported)" : "owner/B gets nothing (item was in conflict)";
  if (!carried.length) return "owner/B not written yet";
  const unseen = heads(v).filter((n) => v.kind[n] === "c" && !carried.includes(n));
  return unseen.length ? "owner/B written, but misses a later version" : "owner/B holds A's items";
}

const phaseLabel: Record<string, string> = {
  idle: "A has not started",
  shown: "A has read the board",
  snapped: "A took the list of items",
  moved: "A wrote owner/B",
  forwarded: "A closed owner/A",
  rechecked: "A looked at owner/A again",
  recorded: "A wrote handover/A",
};

export const state = (v: any) =>
  `${phaseLabel[v.phase]}: ${item(v)}` + (v.phase === "idle" || v.phase === "shown" || v.phase === "snapped" && !v.skipped ? "" : `; ${owner(v)}`);

export const group = (v: any) => {
  const closed = heads(v).every((n: number) => v.kind[n] === "n");
  return v.phase === "recorded" ? (closed ? "closed" : "left") : "running";
};
export const colors = { running: "blue", closed: "teal", left: "orange" } as Record<string, string>;

export function step(action: string, from: any, to: any): string | null {
  switch (action) {
    case "AReadsBoard":
      return "A reads the board";
    case "ASnapshot":
      return to.skipped ? "A lists the items [one has two versions]" : "A lists the items";
    case "AWritesNewOwner":
      return to.skipped ? "A leaves the conflicted item alone" : "A copies owner/A into owner/B";
    case "AForwardsOldItem":
      return "A overwrites owner/A with 'handed over'";
    case "ARechecks":
      return to.carried.length > from.carried.length ? "A finds a later version, carries it to owner/B and closes owner/A again" : "A checks owner/A again";
    case "ARecordsHandover":
      return from.skipped ? "A writes the handover/A item and names the skipped item" : "A writes the handover/A item";
    case "MWritesItem":
      return "a member writes owner/A";
    case "Done":
      return null;
    default:
      return action;
  }
}
