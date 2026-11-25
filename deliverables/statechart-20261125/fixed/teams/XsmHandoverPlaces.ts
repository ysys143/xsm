export const title = "xsm handover when A is in several teams (fixed)";

const names = (xs: string[]) => (xs.length ? xs.join(" and ") : "no team");

export const state = (v: any) => {
  const a = Object.keys(v.aIn).filter((t) => v.aIn[t]).sort();
  const m = [...v.moved].sort();
  const s = [...v.swapped].sort();
  const k = [...v.skipped].sort();
  const base = `A in ${names(a)}; boards moved in ${names(m)}; B took A's place in ${names(s)}` + (k.length ? `; skipped (A had left): ${names(k)}` : "");
  const lead = v.phase === "done" ? "Handover done" : v.phase === "idle" ? "Not started" : "Running";
  return `${lead}: ${base}`;
};

export const group = (v: any) =>
  v.phase !== "done" ? "running" : (JSON.stringify([...v.moved].sort()) === JSON.stringify([...v.swapped].sort()) && !Object.values(v.aIn).some(Boolean)) ? "clean" : "split";
export const colors = { running: "blue", clean: "teal", split: "orange" } as Record<string, string>;

export function step(action: string, from: any, to: any): string | null {
  switch (action) {
    case "Begin":
      return "the handover is recorded and lists A's teams once";
    case "MoveTeam":
      return to.skipped.length > from.skipped.length
        ? "a team A has left meanwhile is skipped"
        : "A's items in one team move to B and B takes A's place there";
    case "Finish":
      return "the handover is finished";
    case "OutsideAdds":
      return "someone adds A to another team, B is added instead";
    case "OutsideRemoves":
      return "someone removes A from a team";
    case "Done":
      return null;
    default:
      return action;
  }
}
