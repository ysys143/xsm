export const title = "xsm handover: the team record on two machines (fixed)";

const orgWord = (n: number) => (n === 1 ? "from X" : "from Y");

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
      const m = xChanged ? "X" : yChanged ? "Y" : "";
      if (!m) return "a machine ignores the record (echo, or the other record wins)";
      const o = m === "X" ? "Y" : "X";
      return to.msgs.length >= from.msgs.length
        ? `${m} takes ${o}'s record and applies its own change on top again`
        : `${m} takes ${o}'s record`;
    }
    case "Done":
      return null;
    default:
      return action;
  }
}
