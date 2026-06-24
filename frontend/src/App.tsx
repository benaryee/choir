import { useState } from "react";
import { UploadScreen } from "./components/UploadScreen";
import { ProgressBar } from "./components/ProgressBar";
import { CorrectionScreen } from "./components/CorrectionScreen";
import { PlayerScreen } from "./components/PlayerScreen";
import { useJobStatus } from "./hooks/useJobStatus";

export default function App() {
  const [jobId, setJobId] = useState<string | null>(null);
  const { job, error } = useJobStatus(jobId);

  const reset = () => setJobId(null);

  return (
    <div className="min-h-screen">
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-5xl items-center gap-2 px-4 py-4">
          <span className="text-2xl">🎵</span>
          <h1 className="text-lg font-bold text-slate-800">Dominion Classical Choir Practice App</h1>
        </div>
      </header>

      <main className="py-10">
        {!jobId && <UploadScreen onUploaded={setJobId} />}

        {jobId && job && job.status === "needs_review" && (
          <CorrectionScreen job={job} onSubmitted={() => { /* polling resumes */ }} />
        )}

        {jobId && job && job.status === "succeeded" && (
          <PlayerScreen job={job} onReset={reset} />
        )}

        {jobId &&
          job &&
          (job.status === "queued" || job.status === "running") && (
            <div className="mx-auto max-w-2xl px-4">
              <div className="rounded-xl border border-slate-200 bg-white p-8 shadow-sm">
                <h2 className="mb-6 text-center text-lg font-semibold text-slate-700">
                  Processing “{job.filename}”
                </h2>
                <ProgressBar job={job} />
              </div>
            </div>
          )}

        {jobId && job && job.status === "failed" && (
          <div className="mx-auto max-w-2xl px-4">
            <div className="rounded-xl border border-red-200 bg-red-50 p-6">
              <h2 className="font-semibold text-red-700">Processing failed</h2>
              <pre className="mt-2 max-h-48 overflow-auto whitespace-pre-wrap text-xs text-red-600">
                {job.error}
              </pre>
              <button
                onClick={reset}
                className="mt-4 rounded-lg bg-red-600 px-4 py-2 text-sm font-medium text-white hover:bg-red-700"
              >
                Try another file
              </button>
            </div>
          </div>
        )}

        {jobId && !job && (
          <p className="text-center text-slate-400">Loading job…</p>
        )}

        {error && !job && (
          <p className="mt-4 text-center text-sm text-red-500">{error}</p>
        )}
      </main>
    </div>
  );
}
