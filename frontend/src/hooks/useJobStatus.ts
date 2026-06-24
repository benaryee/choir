import { useEffect, useRef, useState } from "react";
import { fetchJob } from "../api";
import type { Job } from "../types";

const TERMINAL = new Set(["succeeded", "failed"]);

/**
 * Polls the backend for a job's status until it reaches a terminal state.
 * `needs_review` keeps polling so the UI auto-resumes once the user submits
 * corrections and the server flips the job back to `running`.
 */
export function useJobStatus(jobId: string | null, intervalMs = 1500) {
  const [job, setJob] = useState<Job | null>(null);
  const [error, setError] = useState<string | null>(null);
  const timer = useRef<number | null>(null);

  useEffect(() => {
    if (!jobId) return;
    let cancelled = false;

    const poll = async () => {
      try {
        const next = await fetchJob(jobId);
        if (cancelled) return;
        setJob(next);
        if (!TERMINAL.has(next.status)) {
          timer.current = window.setTimeout(poll, intervalMs);
        }
      } catch (e) {
        if (cancelled) return;
        setError((e as Error).message);
        timer.current = window.setTimeout(poll, intervalMs * 2);
      }
    };

    poll();
    return () => {
      cancelled = true;
      if (timer.current) window.clearTimeout(timer.current);
    };
  }, [jobId, intervalMs]);

  return { job, error, setJob };
}
