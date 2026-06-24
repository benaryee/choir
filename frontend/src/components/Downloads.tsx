import { VOICES, VOICE_LABELS } from "../types";
import type { Job, Voice } from "../types";

function DownloadLink({ href, label }: { href: string; label: string }) {
  return (
    <a
      href={href}
      download
      className="rounded-full border border-slate-300 bg-white px-3 py-1 text-xs font-medium text-slate-600 hover:border-indigo-400 hover:text-indigo-600"
    >
      ↓ {label}
    </a>
  );
}

/**
 * Download links for everything the pipeline produced: the stave (MusicXML),
 * the whole-piece tonic sol-fa, and per-voice audio + sol-fa.
 */
export function Downloads({ job }: { job: Job }) {
  const { musicxml_url, solfa_combined_url, audio, solfa } = job.result;
  const voices = VOICES.filter((v) => v !== "full") as Voice[];

  const hasPerVoice = voices.some((v) => audio[v] || solfa[v]);
  if (!musicxml_url && !solfa_combined_url && !hasPerVoice) return null;

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-xs font-semibold uppercase tracking-wide text-slate-400">
          Score
        </span>
        {musicxml_url && (
          <DownloadLink href={musicxml_url} label="Stave (MusicXML)" />
        )}
        {solfa_combined_url && (
          <DownloadLink href={solfa_combined_url} label="Tonic Sol-fa" />
        )}
      </div>

      {hasPerVoice && (
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-xs font-semibold uppercase tracking-wide text-slate-400">
            Parts
          </span>
          {voices.map((voice) => (
            <span key={voice} className="flex items-center gap-1">
              {audio[voice] && (
                <DownloadLink
                  href={audio[voice]!}
                  label={`${VOICE_LABELS[voice]} MP3`}
                />
              )}
              {solfa[voice] && (
                <DownloadLink
                  href={solfa[voice]!}
                  label={`${VOICE_LABELS[voice]} Sol-fa`}
                />
              )}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}
