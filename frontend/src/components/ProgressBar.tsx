import { STAGE_LABELS, STAGE_ORDER } from "../types";
import type { Job, Stage } from "../types";

function stageIndex(stage: Stage): number {
  return STAGE_ORDER.indexOf(stage);
}

export function ProgressBar({ job }: { job: Job }) {
  const current = stageIndex(job.stage);
  const failed = job.status === "failed";

  return (
    <div className="w-full">
      <div className="flex items-center justify-between">
        {STAGE_ORDER.map((stage, idx) => {
          const done = idx < current || job.status === "succeeded";
          const active = idx === current && !failed && job.status !== "succeeded";
          return (
            <div key={stage} className="flex flex-1 flex-col items-center">
              <div className="flex w-full items-center">
                <div
                  className={[
                    "mx-auto flex h-9 w-9 items-center justify-center rounded-full border-2 text-sm font-semibold transition-colors",
                    done
                      ? "border-emerald-500 bg-emerald-500 text-white"
                      : active
                      ? "border-indigo-500 bg-white text-indigo-600"
                      : failed && idx === current
                      ? "border-red-500 bg-red-500 text-white"
                      : "border-slate-300 bg-white text-slate-400",
                  ].join(" ")}
                >
                  {done ? "✓" : idx + 1}
                </div>
              </div>
              <span
                className={[
                  "mt-2 text-center text-xs",
                  active ? "font-semibold text-indigo-600" : "text-slate-500",
                ].join(" ")}
              >
                {STAGE_LABELS[stage]}
              </span>
            </div>
          );
        })}
      </div>

      <div className="mt-4 h-2 w-full overflow-hidden rounded-full bg-slate-200">
        <div
          className={[
            "h-full rounded-full transition-all duration-500",
            failed ? "bg-red-500" : "bg-indigo-500",
          ].join(" ")}
          style={{
            width: `${
              ((current + (job.status === "succeeded" ? 1 : job.progress)) /
                STAGE_ORDER.length) *
              100
            }%`,
          }}
        />
      </div>

      {job.status === "running" && (
        <p className="mt-3 animate-pulse text-center text-sm text-slate-500">
          {STAGE_LABELS[job.stage]}…
        </p>
      )}
    </div>
  );
}
