export const title =
  "xsm: another machine R asked A, then A handed over to B and B to C";

const place = (v: any) =>
  v.holder === "A" ? "A holds its place" : v.holder === "B" ? "A handed over to B" : "A handed over to B, B to C";

// What R's machine does with the answer of the session that now holds A's place.
const verdict = (v: any): string => {
  if (v.holder === "A") return "";
  const need = v.holder === "B" ? [v.t1] : [v.t1, v.t2];
  if (need.some((t: string) => t === "none" || t === "lost")) return "R has no handover news and will pull it";
  if (need.some((t: string) => t === "inflight")) return "R waits for the handover news";
  return "R accepts its answer";
};

const unreplyable = (v: any): boolean => v.asked && !v.qRead && v.origAt !== v.holder;

const question = (v: any): string => {
  if (unreplyable(v)) return "unread question moved away, nobody can reply";
  if (["B", "C"].some((s) => v.ans[s] === "recorded")) return "answer recorded";
  if (["B", "C"].some((s) => v.ans[s] === "unconfirmed")) return "answer recorded, marked unconfirmed";
  if (["B", "C"].some((s) => v.ans[s] === "unconfirmed")) return "answer recorded, handover unconfirmed";
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
      return "R records the answer";
    case "DeliverAnswerPull":
      return "R does not know the handover, asks M1 for the chain and records the answer";
    case "DeliverAnswerUnconfirmed":
      return "R cannot reach M1 and records the answer as unconfirmed";
    case "Confirm":
      return "the handover news arrives and the answer is confirmed";
    case "ConfirmByPull":
      return "R asks M1 again and confirms the answer";
    case "Done":
      return null;
    default:
      return action;
  }
}

export const group = (v: any) =>
  ["B", "C"].some((s) => v.ans[s] === "recorded" || v.ans[s] === "unconfirmed") ? "answered" : "open";

export const colors = { answered: "teal", open: "tan" } as Record<string, string>;
