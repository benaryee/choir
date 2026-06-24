import { useEffect, useRef } from "react";
import { OpenSheetMusicDisplay } from "opensheetmusicdisplay";
import { VOICE_COLORS } from "../types";
import type { Voice } from "../types";

const INACTIVE_COLOR = "#1e293b";

/**
 * Renders the extracted MusicXML with OpenSheetMusicDisplay and colours the
 * notes of the active voice part. ``voicePartIndex`` maps a voice onto the
 * part/staff index within the score (derived from the detected parts).
 */
export function ScoreView({
  musicXml,
  activeVoice,
  voicePartIndex,
}: {
  musicXml: string;
  activeVoice: Voice;
  voicePartIndex: Partial<Record<Voice, number>>;
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const osmdRef = useRef<OpenSheetMusicDisplay | null>(null);
  const loadedRef = useRef(false);

  // Load the score once.
  useEffect(() => {
    if (!containerRef.current) return;
    const osmd = new OpenSheetMusicDisplay(containerRef.current, {
      autoResize: true,
      drawingParameters: "default",
      drawPartNames: true,
    });
    osmdRef.current = osmd;
    loadedRef.current = false;

    osmd
      .load(musicXml)
      .then(() => {
        loadedRef.current = true;
        colorActive(osmd, activeVoice, voicePartIndex);
        osmd.render();
      })
      .catch(() => {
        /* invalid MusicXML - leave container empty */
      });

    return () => {
      osmdRef.current = null;
      if (containerRef.current) containerRef.current.innerHTML = "";
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [musicXml]);

  // Recolour when the selected voice changes.
  useEffect(() => {
    const osmd = osmdRef.current;
    if (!osmd || !loadedRef.current) return;
    colorActive(osmd, activeVoice, voicePartIndex);
    osmd.render();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeVoice]);

  return <div ref={containerRef} className="w-full overflow-x-auto" />;
}

function colorFor(
  staffIndex: number,
  activeVoice: Voice,
  voicePartIndex: Partial<Record<Voice, number>>
): string {
  if (activeVoice === "full") {
    const entry = Object.entries(voicePartIndex).find(
      ([, idx]) => idx === staffIndex
    );
    return entry ? VOICE_COLORS[entry[0] as Voice] : INACTIVE_COLOR;
  }
  return voicePartIndex[activeVoice] === staffIndex
    ? VOICE_COLORS[activeVoice]
    : INACTIVE_COLOR;
}

function colorActive(
  osmd: OpenSheetMusicDisplay,
  activeVoice: Voice,
  voicePartIndex: Partial<Record<Voice, number>>
) {
  const measureList = osmd.GraphicSheet?.MeasureList;
  if (!measureList) return;
  for (const row of measureList) {
    row.forEach((measure, staffIndex) => {
      if (!measure) return;
      const color = colorFor(staffIndex, activeVoice, voicePartIndex);
      for (const entry of measure.staffEntries) {
        for (const gve of entry.graphicalVoiceEntries) {
          for (const note of gve.notes) {
            if (note.sourceNote) {
              note.sourceNote.NoteheadColor = color;
            }
          }
        }
      }
    });
  }
}
