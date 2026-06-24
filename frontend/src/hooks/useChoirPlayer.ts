import { useCallback, useEffect, useRef, useState } from "react";
import * as Tone from "tone";
import type { Voice } from "../types";

const STEMS: Voice[] = ["soprano", "alto", "tenor", "bass"];

const ACTIVE_GAIN = 1.0;
const BACKGROUND_GAIN = 0.2; // practice mode: other parts at 20%

/**
 * Plays the four voice stems in sync via Tone.Transport. Switching the active
 * part only adjusts gains, so playback never loses its position and the swap is
 * seamless. Selecting "full" plays every part at full volume.
 */
export function useChoirPlayer(audio: Partial<Record<Voice, string>>) {
  const playersRef = useRef<Map<Voice, Tone.Player>>(new Map());
  const gainsRef = useRef<Map<Voice, Tone.Gain>>(new Map());
  const [ready, setReady] = useState(false);
  const [isPlaying, setIsPlaying] = useState(false);
  const [active, setActive] = useState<Voice>("full");

  // (Re)build the player graph whenever the audio set changes.
  useEffect(() => {
    let cancelled = false;
    const available = STEMS.filter((v) => audio[v]);
    if (available.length === 0) {
      setReady(false);
      return;
    }

    const players = new Map<Voice, Tone.Player>();
    const gains = new Map<Voice, Tone.Gain>();

    const loaders = available.map(
      (voice) =>
        new Promise<void>((resolve) => {
          const gain = new Tone.Gain(ACTIVE_GAIN).toDestination();
          const player = new Tone.Player({
            url: audio[voice]!,
            onload: () => resolve(),
          }).connect(gain);
          player.sync().start(0);
          players.set(voice, player);
          gains.set(voice, gain);
        })
    );

    Promise.all(loaders).then(() => {
      if (cancelled) {
        players.forEach((p) => p.dispose());
        gains.forEach((g) => g.dispose());
        return;
      }
      playersRef.current = players;
      gainsRef.current = gains;
      setReady(true);
    });

    return () => {
      cancelled = true;
      Tone.getTransport().stop();
      Tone.getTransport().cancel();
      players.forEach((p) => p.dispose());
      gains.forEach((g) => g.dispose());
      setReady(false);
      setIsPlaying(false);
    };
  }, [audio]);

  const applyGains = useCallback((voice: Voice) => {
    gainsRef.current.forEach((gain, stem) => {
      const target =
        voice === "full" || stem === voice ? ACTIVE_GAIN : BACKGROUND_GAIN;
      gain.gain.rampTo(target, 0.08);
    });
  }, []);

  const selectVoice = useCallback(
    (voice: Voice) => {
      setActive(voice);
      applyGains(voice);
    },
    [applyGains]
  );

  const play = useCallback(async () => {
    await Tone.start();
    applyGains(active);
    Tone.getTransport().start();
    setIsPlaying(true);
  }, [active, applyGains]);

  const pause = useCallback(() => {
    Tone.getTransport().pause();
    setIsPlaying(false);
  }, []);

  const stop = useCallback(() => {
    Tone.getTransport().stop();
    setIsPlaying(false);
  }, []);

  const toggle = useCallback(() => {
    if (isPlaying) pause();
    else void play();
  }, [isPlaying, pause, play]);

  return { ready, isPlaying, active, selectVoice, play, pause, stop, toggle };
}
