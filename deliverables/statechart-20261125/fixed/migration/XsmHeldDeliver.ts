export const title = "xsm: two DMs to A (DM1 out of scope), A's gate, and the held deliver command";

function one(v: any, m: string): string {
  const st = v.st[m], rc = v.rc[m], ds = v.ds[m];
  const yes = v.yes[m], hl = v.hl[m], shows = v.shows[m], holds = v.holds[m];
  if (st === "acked") return yes ? "person said yes; consumed" : "confirmed by A";
  if (st === "shown") return shows > 1 ? "shown to A again, not confirmed" : "shown to A, not confirmed";
  // pending
  if (hl) return holds > 1 ? "held again, waiting for the person's yes" : "held, waiting for the person's yes";
  if (yes) return holds > 1 ? "person said yes, then it was held again" : "person said yes; the original is still pending";
  if (rc === "held") return "held";
  if (rc === "delivered") return "delivered, original pending";
  return ds === "held" ? "held (inbox)" : "waiting at A";
}

export const state = (v: any) => ({
  DM1: one(v, "1"),
  DM2: one(v, "2"),
  Scope: v.open ? "link opened" : "no link",
});

export function step(action: string, from: any, to: any): string | null {
  const m = (a: any, b: any) => { for (const k of ["1","2"]) if (JSON.stringify(a.st[k])!==JSON.stringify(b.st[k]) || a.rc[k]!==b.rc[k] || a.hl[k]!==b.hl[k]) return k; return "?"; };
  const k = m(from, to);
  switch (action) {
    case "HookHolds": return `A's hook holds DM${k}`;
    case "HookShows": return `A's hook shows DM${k}`;
    case "InboxTakes": return to.hl[k] ? `A's inbox holds DM${k}` : `A's inbox shows DM${k}`;
    case "HeldDeliver": return `person says yes: held deliver DM${k}`;
    case "Ack": return `A confirms DM${k}`;
    case "GateOpens": return "the person links the sessions";
    case "Done": return null;
    default: return action;
  }
}
