import { useState } from "react";
import { submitCorrections } from "../api";
import { VOICES, VOICE_COLORS, VOICE_LABELS } from "../types";
import type { Job, Voice } from "../types";

/**
 * Manual correction UI shown when OMR confidence is low. The detected parts are
 * listed beside the user's page image so they can confirm or fix voice labels
 * before the pipeline continues.
 */
export function CorrectionScreen({
  job,
  onSubmitted,
}: {
  job: Job;
  onSubmitted: () => void;
}) {
  const [assignments, setAssignments] = useState<Record<string, Voice>>(() => {
    const init: Record<string, Voice> = {};
    for (const p of job.detected_parts) {
      init[p.id] = p.suggested_voice ?? "soprano";
    }
    return init;
  });
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async () => {
    setSubmitting(true);
    setError(null);
    try {
      await submitCorrections(
        job.id,
        Object.entries(assignments).map(([part_id, voice]) => ({ part_id, voice }))
      );
      onSubmitted();
    } catch (e) {
      setError((e as Error).message);
      setSubmitting(false);
    }
  };

  return (
    <div className="mx-auto max-w-5xl px-4">
      <div className="mb-6 rounded-xl bg-amber-50 p-4 text-amber-800">
        <p className="font-semibold">We need your help reading this score.</p>
        <p className="text-sm">
          Confidence was low
          {job.omr_confidence != null
            ? ` (${Math.round(job.omr_confidence * 100)}%)`
            : ""}
          . Confirm the voice for each detected part.
        </p>
      </div>

      <div className="grid gap-6 md:grid-cols-2">
        <div className="space-y-3">
          {job.detected_parts.map((part) => (
            <div
              key={part.id}
              className="rounded-lg border border-slate-200 bg-white p-4"
            >
              <div className="flex items-center justify-between">
                <span className="font-medium text-slate-700">{part.label}</span>
                <span className="text-xs text-slate-400">
                  {Math.round(part.confidence * 100)}% conf.
                </span>
              </div>
              <div className="mt-3 flex flex-wrap gap-2">
                {VOICES.filter((v) => v !== "full").map((voice) => {
                  const selected = assignments[part.id] === voice;
                  return (
                    <button
                      key={voice}
                      onClick={() =>
                        setAssignments((a) => ({ ...a, [part.id]: voice }))
                      }
                      className="rounded-full px-3 py-1 text-sm font-medium transition-colors"
                      style={{
                        backgroundColor: selected ? VOICE_COLORS[voice] : "#f1f5f9",
                        color: selected ? "white" : "#475569",
                      }}
                    >
                      {VOICE_LABELS[voice]}
                    </button>
                  );
                })}
              </div>
            </div>
          ))}
        </div>

        <div className="space-y-3">
          {job.page_image_urls.map((url, i) => (
            <img
              key={url}
              src={url}
              alt={`Page ${i + 1}`}
              className="w-full rounded-lg border border-slate-200 bg-white"
            />
          ))}
        </div>
      </div>

      {error && (
        <p className="mt-4 rounded-lg bg-red-50 p-3 text-sm text-red-600">{error}</p>
      )}

      <div className="mt-6 flex justify-end">
        <button
          onClick={submit}
          disabled={submitting}
          className="rounded-lg bg-indigo-600 px-6 py-2 font-semibold text-white hover:bg-indigo-700 disabled:opacity-50"
        >
          {submitting ? "Continuing…" : "Confirm parts & continue"}
        </button>
      </div>
    </div>
  );
}
