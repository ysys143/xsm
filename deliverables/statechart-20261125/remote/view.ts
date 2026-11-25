export const title =
  "xsm: another machine R asked A, then A handed over to B and B to C";

const place = (v: any) =>
  v.holder === "A" ? "A holds its place" : v.holder === "B" ? "A handed over to B" : "A handed over to B, B to C";

// What R's machine does with the answer of the session that now holds A's place.
const verdict = (v: any): string => {
  if (v.holder === "A") return "";
  const need = v.holder === "B" ? [v.t1] : [v.t1, v.t2];
  if (need.some((t: string) => t === "none" || t === "lost")) return "R will never accept its answer";
  if (need.some((t: string) => t === "inflight")) return "R waits for the handover news";
  return "R accepts its answer";
};

const unreplyable = (v: any): boolean =>
  v.asked && !v.qRead &&
  ((v.recLocal === "A" && v.holder !== "A") || (v.recLocal === "B" && v.holder === "C"));

const question = (v: any): string => {
  if (unreplyable(v)) return "unread question moved away, nobody can reply";
  const done = ["B", "C"].some((s) => v.ans[s] === "recorded");
  if (done) return "answer recorded";
  if (!v.asked) return "no question yet";
  if (["B", "C"].some((s) => v.ans[s] === "inflight")) return "R waits for an answer";
  if (["B", "C"].some((s) => v.ans[s] === "refused")) return "answer refused";
  return "R waits for an answer";
};

export const state = (v: any) => {
  const verdictText = unreplyable(v) ? "" : verdict(v);
  return [place(v), verdictText ? `${verdictText}; ${question(v)}` : question(v)].join(".");
};

export function step(action: string, from: any, to: any): string | null {
  const who = (a: any, b: any) => ["B", "C"].find((s) => a.ans[s] !== b.ans[s]) as string;
  switch (action) {
    case "HandOver1":
      if (to.asked && !to.qRead && to.recLocal === "A")
        return "the person approves while A has not read R's question; M1 tells R's machine";
      return to.t1 === "inflight"
        ? "the person approves; M1 tells R's machine"
        : "the person approves; M1 has no reason to tell R's machine";
    case "HandOver2":
      return to.t2 === "inflight" ? "B hands over to C; M1 tells R's machine"
        : "B hands over to C; M1 has no reason to tell R's machine";
    case "DeliverT1":
    case "DeliverT2":
      return "R's machine keeps the handover news";
    case "LoseT1":
    case "LoseT2":
      return "the handover news is lost on the way (no retry)";
    case "Ask":
      return from.holder === "A" ? "R asks A" : "R asks A's old address";
    case "Answer":
      return `${who(from, to) === "B" ? "B" : "C"} answers R`;
    case "Stranger":
      return "a session outside A's chain answers R";
    case "DeliverAnswer":
      return to.ans[who(from, to)] === "recorded" ? "R records the answer" : "R refuses the answer";
    case "Resend":
      return "the sender sends the answer again, same id";
    case "Done":
      return null;
    default:
      return action;
  }
}

export const group = (v: any) =>
  ["B", "C"].some((s) => v.ans[s] === "recorded") ? "answered" : "open";

export const colors = { answered: "teal", open: "tan" } as Record<string, string>;
