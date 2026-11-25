export const title = "xsm handover: the team record on two machines";

const orgWord = (n: number) => (n === 0 ? "created here" : n === 1 ? "last received from X" : "last received from Y");

function team(r: any): string {
  const seat = r.hand ? "B leads, A is out" : "A leads";
  return (r.ext ? `${seat}, Y's change in` : seat) + ` (${orgWord(r.org)})`;
}

export const state = (v: any) =>
  `X: ${team(v.rec.X)}; Y: ${team(v.rec.Y)}; ` + (v.msgs.length === 0 ? "no record in flight" : `${v.msgs.length} in flight`);

export const group = (v: any) =>
  v.msgs.length === 0 && v.rec.X.hand !== v.rec.Y.hand ? "split" : v.msgs.length === 0 && v.rec.X.hand ? "settled" : "open";
export const colors = { split: "orange", settled: "teal", open: "blue" } as Record<string, string>;

export function step(action: string, from: any, to: any): string | null {
  switch (action) {
    case "HandOver":
      return "X hands A's seat to B and sends the team";
    case "YChanges":
      return "Y changes the team and sends it";
    case "Receives": {
      const xChanged = JSON.stringify(from.rec.X) !== JSON.stringify(to.rec.X);
      const yChanged = JSON.stringify(from.rec.Y) !== JSON.stringify(to.rec.Y);
      if (xChanged) return "X takes Y's record, replacing its own";
      if (yChanged) return "Y takes X's record, replacing its own";
      return "a machine refuses the record as not newer";
    }
    case "Done":
      return null;
    default:
      return action;
  }
}
