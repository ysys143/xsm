export const title = "xsm: a DM, a question and a handover from A to B";

const seenB = (v: any) => (v.dmSeen as string[]).includes("B");

function dm(v: any): string {
  switch (v.dmState) {
    case "pending":
      return v.dmHeld ? "DM held by A's gate" : "DM waiting at A";
    case "shown":
      return "DM shown to A, not confirmed";
    case "acked":
      return "DM confirmed by A";
    default:
      if (seenB(v)) return v.dmHeld ? "Held DM read by B" : "DM read by B";
      return v.dmHeld ? "Held DM in the letter" : "DM in the letter";
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
    case "unread":
      return "Handing over: unread DMs moved";
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
      return "A's gate refuses the DM";
    case "Take":
      return "A reads the DM";
    case "Ack":
      return "A confirms it";
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
      return "the person approves the handover";
    case "HandOverUnread":
      return "unread DMs go into the letter";
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
