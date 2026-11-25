export const title = "xsm handover when A is in several teams";

const names = (xs: string[]) => (xs.length ? xs.join(" and ") : "no team");

export const state = (v: any) => {
  const a = Object.keys(v.aIn).filter((t) => v.aIn[t]).sort();
  const m = [...v.moved].sort();
  const s = [...v.swapped].sort();
  const base = `A in ${names(a)}; boards moved in ${names(m)}; B took A's place in ${names(s)}`;
  const lead = v.phase === "done" ? "Handover done" : v.phase === "aborted" ? "Handover stopped by an error" : v.phase === "idle" ? "Not started" : "Running";
  return `${lead}: ${base}`;
};

export const group = (v: any) =>
  v.phase === "aborted" ? "split" : v.phase !== "done" ? "running" : (JSON.stringify([...v.moved].sort()) === JSON.stringify([...v.swapped].sort()) && !Object.values(v.aIn).some(Boolean)) ? "clean" : "split";
export const colors = { running: "blue", clean: "teal", split: "orange" } as Record<string, string>;

export function step(action: string, from: any, to: any): string | null {
  switch (action) {
    case "StartBoards":
      return "the handover lists A's teams for the boards";
    case "MoveBoard":
      return "A's items in one team are moved to B";
    case "StartTeams":
      return "the handover lists A's teams again";
    case "SwapPlace":
      return "B takes A's place in one team";
    case "Abort":
      return "A's items cannot be moved: A has left that team";
    case "Finish":
      return "the handover is recorded";
    case "OutsideAdds":
      return "someone adds A to another team";
    case "OutsideRemoves":
      return "someone removes A from a team";
    case "Done":
      return null;
    default:
      return action;
  }
}
