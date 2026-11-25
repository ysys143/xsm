export const title =
  "xsm: concurrent handovers. A holds the team place and asked a question that is still open";

const WORD: Record<string, string> = { AtoB: "A to B", AtoC: "A to C", BtoA: "B to A", BtoC: "B to C" };
const PHASE: Record<string, string> = {
  idle: "not started",
  refused: "refused, nothing changed",
  checked: "holds the lock, passed its check",
  begun: "record written",
  teams: "team seat moved",
  questions: "pending question moved",
  recorded: "done, lock released",
};

// handover.successor_identity: walk the records (at most 8, with a seen set).
function resolve(rec: Record<string, string>, start: string): string {
  const seen = new Set<string>();
  let cur = start;
  let last = "none";
  for (let i = 0; i < 8; i++) {
    if (seen.has(cur)) break;
    seen.add(cur);
    const next = rec[cur];
    if (!next || next === "none") break;
    cur = last = next;
  }
  return last;
}

function addressOfA(v: any): string {
  const r = resolve(v.rec, "A");
  const dest = r === "none" ? "A" : r;
  return dest === "A" && r !== "none" ? "DMs to A loop back to A" : `DMs to A reach ${dest}`;
}

export const state = (v: any) => {
  const out: Record<string, string> = {};
  for (const p of Object.keys(v.pc)) out[`Handover ${WORD[p]}`] = PHASE[v.pc[p]];
  const seats = (v.seats as string[]).slice().sort().join(" and ");
  out["Team"] = `members: ${seats}; lead seat: ${v.lead}`;
  const recs = Object.keys(v.rec).filter((s) => v.rec[s] !== "none");
  out["Records"] = recs.length ? recs.map((s) => `${s} handed to ${v.rec[s]}`).join(", ") : "no handover record";
  out["Address"] = recs.length ? addressOfA(v) : "DMs to A reach A";
  out["Question"] =
    v.reply === "recorded"
      ? `late answer stored for ${v.replyAt}`
      : v.reply === "refused"
        ? `late answer sent to ${v.replyAt}, not stored: the question is ${v.qSender}'s`
        : `open, asked by ${v.qSender}`;
  return out;
};

export function step(action: string, from: any, to: any): string | null {
  if (action === "Done") return null;
  if (action === "PeerAnswers") {
    return to.reply === "recorded" ? "the peer's late answer arrives and is stored"
      : "the peer's late answer arrives and is refused";
  }
  const p = Object.keys(to.pc).find((k) => to.pc[k] !== from.pc[k]) as string;
  const w = WORD[p];
  switch (action) {
    case "Check":
      return to.pc[p] === "refused"
        ? `the person approves ${w} and it is refused (already handed over, or a cycle)`
        : `the person approves ${w}; it takes the lock and passes its check`;
    case "Begin": return `${w} writes its handover record`;
    case "Teams": return `${w} moves the team seat`;
    case "Questions": return `${w} moves the pending question`;
    case "Finish": return `${w} finishes and releases the lock`;
    default: return action;
  }
}

export const group = (v: any) => {
  const inflight = Object.values(v.pc).some((x: any) => ["checked", "begun", "teams", "questions"].includes(x));
  if (v.reply !== "unsent") return "answered";
  return inflight ? "running" : "idle";
};
export const colors = { idle: "blue", running: "orange", answered: "teal" };
