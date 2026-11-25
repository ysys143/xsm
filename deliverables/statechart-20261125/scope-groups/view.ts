export const title = "xsm: a question group of two, A hands over to B, P answers late";

const carries = (v: any) => ["team", "repo_B_same", "link_B_covered"].includes(v.basis);
const KIDS = ["1", "2"];

function groupView(v: any): { status: string; shown: number } {
  const h = v.handed ? "B" : "A";
  const refusedRow = (i: string) => v.kidOwner[i] !== h;
  const answered = KIDS.filter((i) => !refusedRow(i) && v.kid[i] === "final");
  const ended = KIDS.filter((i) => refusedRow(i) || v.kid[i] === "final");
  let status: string;
  if (v.groupOwner !== h) status = "refused";
  else if (answered.length === 2) status = "final";
  else if (answered.length > 0) status = ended.length < 2 ? "reply_received" : "replied";
  else if (ended.length === 2) status = "refused";
  else status = "pending";
  return { status, shown: answered.length };
}

export const state = (v: any): string => {
  const g = groupView(v);
  const final = KIDS.filter((i) => v.kid[i] === "final").length;
  const view = "group view: " + g.status + ", showing " + g.shown + " of the " + final + " final answer" + (final === 1 ? "" : "s") + " given";
  if (!v.handed) {
    return "A holds its place, " + final + " of 2 answered; " + view;
  }
  const refused = (v.refused as number[]).length;
  const stayed = KIDS.filter((i) => v.kid[i] === "final" && v.kidOwner[i] === "A").length;
  const late = final - stayed;
  const waiting = 2 - final - refused;
  const parts = [] as string[];
  if (stayed) parts.push(stayed + " answered before the handover, record left with A");
  if (late) parts.push(late + " answered since, recorded for B");
  if (refused) parts.push(refused + " late answer" + (refused === 1 ? "" : "s") + " refused as out of scope");
  if (waiting) parts.push(waiting + " still waiting");
  return "B holds the place; " + parts.join(", ") + "; " + view;
};

export function step(action: string, from: any, to: any): string | null {
  if (action === "Done") return null;
  if (action === "HandOver")
    return "the person approves the handover " + (carries(to) ? "[P may talk to B]" : "[P may not talk to B]");
  if (!from.handed) return "P answers a question";
  const added = (to.refused as number[]).length > (from.refused as number[]).length;
  return added ? "P answers late: the send is refused, out of scope" : "P answers late: it reaches B";
}
