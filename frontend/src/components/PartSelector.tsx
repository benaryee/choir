import { VOICES, VOICE_COLORS, VOICE_LABELS } from "../types";
import type { Voice } from "../types";

export function PartSelector({
  active,
  available,
  onSelect,
}: {
  active: Voice;
  available: Set<Voice>;
  onSelect: (voice: Voice) => void;
}) {
  return (
    <div className="flex flex-wrap justify-center gap-3">
      {VOICES.map((voice) => {
        const enabled = voice === "full" || available.has(voice);
        const selected = active === voice;
        return (
          <button
            key={voice}
            disabled={!enabled}
            onClick={() => onSelect(voice)}
            className={[
              "min-w-[5.5rem] rounded-full px-5 py-2 text-sm font-semibold shadow-sm transition-all",
              selected ? "scale-105 text-white shadow-md" : "text-slate-600",
              enabled ? "cursor-pointer" : "cursor-not-allowed opacity-40",
            ].join(" ")}
            style={{
              backgroundColor: selected ? VOICE_COLORS[voice] : "#ffffff",
              border: `2px solid ${VOICE_COLORS[voice]}`,
            }}
          >
            {VOICE_LABELS[voice]}
          </button>
        );
      })}
    </div>
  );
}
