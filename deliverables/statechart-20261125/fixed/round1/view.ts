export const title = "xsm: a DM, a question and a handover from A to B";

function dm(v: any): string {
  const at = v.dmAt as string;
  const gate = at === "A" ? "A's gate" : "B's gate";
  switch (v.dmState) {
    case "pending":
      if (v.dmHeld) return at === "A" ? "DM held by A's gate" : "DM held, moved to B still held";
      return at === "A" ? "DM waiting at A" : "DM moved to B, waiting";
    case "shown":
      return at === "A" ? "DM shown to A, not confirmed" : "DM shown to B, not confirmed";
    default:
      return at === "A" ? "DM confirmed by A" : "DM confirmed by B";
  }
}

function answer(v: any): string {
  const rec = v.qReplied;
  switch (v.r) {
    case "unsent":
      return v.qAsker === "A" ? "No answer yet" : "No answer yet, question is B's";
    case "atA":
      return rec ? "Answer at A, recorded" : "Answer waiting at A";
    case "atB":
      return rec ? "Answer at B, recorded" : "Answer waiting at B";
    case "usedA":
      return rec ? "Answer read by A, recorded" : "Answer read by A, question open";
    case "usedB":
      return "Answer read by B, recorded";
    default:
      return rec ? "Answer in the letter, recorded" : "Answer only in the letter, question open";
  }
}

function hand(v: any): string {
  switch (v.hStep) {
    case "none":
      return "A holds its place";
    case "questions":
      return "Handing over: questions moved";
    case "begun":
      return "Handing over: record written, A's address leads to B";
    case "originals":
      return "Handing over: A's originals moved to B";
    default:
      return v.letterRead ? "B read the letter" : "B holds A's place";
  }
}

const waitLabel: Record<string, string> = {
  waiting: "A waits",
  answered: "Wait ended: answered",
  timedOut: "Wait ended: timeout",
};

export const state = (v: any) => ({
  DM: dm(v),
  Wait: waitLabel[v.wait],
  Answer: answer(v),
  Handover: hand(v),
});

export function step(action: string, from: any, to: any): string | null {
  switch (action) {
    case "GateHolds":
      return from.dmAt === "A" ? "A's gate refuses the DM" : "B's gate refuses the DM";
    case "Take":
      return from.dmAt === "A" ? "A reads the DM" : "B reads the DM";
    case "Ack":
      return from.dmAt === "A" ? "A confirms it" : "B confirms it";
    case "Release":
      return "A's output fails";
    case "LeaseExpires":
      return null; // no visible change; Recover shows the effect
    case "Recover":
      return "the 120 s lease runs out";
    case "PReplies":
      return "P answers";
    case "Poll":
      return "the asker checks its question";
    case "TakeReply":
      return to.r === "usedA" ? "A reads the answer" : "B reads the answer";
    case "WaitAnswered":
      return "the answer ends the wait";
    case "WaitTimesOut":
      return "the wait times out";
    case "HandOverQuestions":
      return "the person approves the handover; the questions move to B";
    case "HandOverBegin":
      return "the handover record is written";
    case "HandOverOriginals":
      return "A's unread DMs and answers move to B";
    case "HandOverRecorded":
      return "the handover is recorded";
    case "BReadsLetter":
      return "B reads the letter";
    case "Done":
      return null;
    default:
      return action;
  }
}
