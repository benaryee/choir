import { useEffect, useMemo, useState } from "react";
import { fetchMusicXml } from "../api";
import { useChoirPlayer } from "../hooks/useChoirPlayer";
import { PartSelector } from "./PartSelector";
import { ScoreView } from "./ScoreView";
import { SolfaView } from "./SolfaView";
import { Downloads } from "./Downloads";
import { VOICES } from "../types";
import type { Job, Voice } from "../types";

type ViewMode = "stave" | "solfa";

export function PlayerScreen({ job, onReset }: { job: Job; onReset: () => void }) {
  const [musicXml, setMusicXml] = useState<string | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [view, setView] = useState<ViewMode>("stave");
  const solfaUrl = job.result.solfa_combined_url;

  useEffect(() => {
    if (!job.result.musicxml_url) return;
    fetchMusicXml(job.result.musicxml_url)
      .then(setMusicXml)
      .catch((e) => setLoadError((e as Error).message));
  }, [job.result.musicxml_url]);

  const audio = useMemo(() => job.result.audio, [job.result.audio]);
  const { ready, isPlaying, active, selectVoice, toggle, stop } =
    useChoirPlayer(audio);

  // Map each voice -> its part/staff index, derived from detected parts.
  const voicePartIndex = useMemo(() => {
    const map: Partial<Record<Voice, number>> = {};
    job.detected_parts.forEach((part, idx) => {
      if (part.suggested_voice && part.suggested_voice !== "full") {
        map[part.suggested_voice] = idx;
      }
    });
    return map;
  }, [job.detected_parts]);

  const availableVoices = useMemo(() => {
    const set = new Set<Voice>();
    for (const v of VOICES) if (v !== "full" && audio[v]) set.add(v);
    return set;
  }, [audio]);

  const hasAudio = availableVoices.size > 0;

  return (
    <div className="mx-auto max-w-5xl px-4">
      <div className="mb-4 flex items-center justify-between">
        <div>
          <h2 className="text-xl font-semibold text-slate-800">{job.filename}</h2>
          <p className="text-sm text-slate-500">
            {job.page_count} page{job.page_count === 1 ? "" : "s"} ·{" "}
            {job.omr_method ?? "omr"}
          </p>
        </div>
        <div className="flex items-center gap-2">
          {solfaUrl && (
            <div className="flex rounded-lg border border-slate-300 p-0.5">
              {(["stave", "solfa"] as ViewMode[]).map((mode) => (
                <button
                  key={mode}
                  onClick={() => setView(mode)}
                  className={[
                    "rounded-md px-3 py-1.5 text-sm font-medium transition-colors",
                    view === mode
                      ? "bg-indigo-600 text-white"
                      : "text-slate-600 hover:bg-slate-100",
                  ].join(" ")}
                >
                  {mode === "stave" ? "Stave" : "Sol-fa"}
                </button>
              ))}
            </div>
          )}
          <button
            onClick={onReset}
            className="rounded-lg border border-slate-300 px-4 py-2 text-sm font-medium text-slate-600 hover:bg-slate-100"
          >
            New upload
          </button>
        </div>
      </div>

      <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
        {view === "solfa" && solfaUrl ? (
          <SolfaView url={solfaUrl} />
        ) : musicXml ? (
          <ScoreView
            musicXml={musicXml}
            activeVoice={active}
            voicePartIndex={voicePartIndex}
          />
        ) : loadError ? (
          <p className="p-8 text-center text-red-500">{loadError}</p>
        ) : (
          <p className="p-8 text-center text-slate-400">Loading score…</p>
        )}
      </div>

      <div className="mt-4 rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
        <Downloads job={job} />
      </div>

      <div className="sticky bottom-0 mt-6 rounded-xl border border-slate-200 bg-white/90 p-4 shadow-lg backdrop-blur">
        <PartSelector
          active={active}
          available={availableVoices}
          onSelect={selectVoice}
        />

        <div className="mt-4 flex items-center justify-center gap-4">
          <button
            onClick={toggle}
            disabled={!hasAudio || !ready}
            className="flex h-12 w-12 items-center justify-center rounded-full bg-indigo-600 text-white shadow hover:bg-indigo-700 disabled:opacity-40"
            aria-label={isPlaying ? "Pause" : "Play"}
          >
            {isPlaying ? "❚❚" : "▶"}
          </button>
          <button
            onClick={stop}
            disabled={!hasAudio || !ready}
            className="flex h-12 w-12 items-center justify-center rounded-full border border-slate-300 text-slate-600 hover:bg-slate-100 disabled:opacity-40"
            aria-label="Stop"
          >
            ■
          </button>
        </div>

        {!hasAudio && (
          <p className="mt-3 text-center text-xs text-slate-400">
            Audio synthesis is not configured on the server — score view only.
          </p>
        )}
        {hasAudio && (
          <p className="mt-3 text-center text-xs text-slate-400">
            Practice mode: selected part at 100%, others at 20%.
          </p>
        )}
      </div>
    </div>
  );
}
