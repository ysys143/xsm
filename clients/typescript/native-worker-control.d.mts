export const WORKER_CONTROL_FD: 'XSM_OWNED_CONTROL_FD';
export class WorkerControlError extends Error {}
export class NativeWorkerControl {
  static fromEnvironment(environment?: Record<string, string | undefined>): NativeWorkerControl | undefined;
  constructor(fd: number);
  nativeID?: string;
  bind(nativeID: string): Promise<void>;
  close(): void;
}
