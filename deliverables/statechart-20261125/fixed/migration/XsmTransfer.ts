export const title = "xsm: a DM at A while the person moves A's place to B";

function at(v: any, s: string): string {
  const st = v.st[s], rs = v.rs[s];
  switch (st) {
    case "none": return "no copy";
    case "moved": return "moved to B";
    case "acked": return "confirmed";
    case "shown": return "shown, not confirmed";
    case "claimed":
      switch (rs) {
        case "toHold": case "toRelease": return "reader is holding it back";
        case "toReceipt": case "toHandoff": return "reader is about to show it";
        case "dead": return "reader failed mid-way, claim stuck";
        default: return "claimed";
      }
    default:
      if (rs === "dead") return "reader failed mid-way";
      return v.rc === "held" || v.ds === "held" ? "waiting, held" : "waiting";
  }
}

const migLabel: Record<string, string> = {
  none: "not started", fenced: "A fenced", messages: "DMs copied to B",
  held: "held list moved", committed: "committed",
};

export const state = (v: any) => ({
  Migration: migLabel[v.mig],
  AtA: at(v, "A"),
  AtB: at(v, "B"),
  HeldList: v.he === "none" ? "no held entry" : v.he === "A" ? "held entry bound to A" : "held entry bound to B",
  Receipt: v.rc === "none" ? "no receipt" : v.rc === "held" ? "receipt: held" : "receipt: delivered",
});

export function step(action: string, from: any, to: any): string | null {
  const side = (a: any, b: any) => (a.st.A !== b.st.A || a.rs.A !== b.rs.A ? "A" : "B");
  switch (action) {
    case "ReaderClaims": return `${side(from, to)}'s reader takes the DM`;
    case "HoldWrites": return `${side(from, to)}'s gate refuses it and keeps a held copy`;
    case "ReleaseHeld": return to.rs[side(from, to)] === "dead" ? "the reader's release is refused" : `${side(from, to)}'s reader puts it back as held`;
    case "WritesReceipt": return `${side(from, to)}'s gate passes it and writes a delivered receipt`;
    case "RecordsHandoff": return to.rs[side(from, to)] === "dead" ? "recording the handoff is refused" : `${side(from, to)}'s reader shows it to its model`;
    case "Acks": return `${side(from, to)} confirms it`;
    case "HookHolds": return "A's hook refuses the DM and keeps a held copy";
    case "Fence": return "the person approves the move; A is fenced";
    case "Transfers": return "xsm copies A's unconfirmed DMs to B";
    case "MovesHeld": return "xsm moves A's held list to B";
    case "Commits": return "the move is committed";
    case "Done": return null;
    default: return action;
  }
}
