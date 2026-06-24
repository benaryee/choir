import { useEffect, useState } from "react";
import { fetchText } from "../api";

/**
 * Fetches and renders the whole-piece tonic sol-fa document as monospaced text
 * so the colon/bar rhythm grid stays aligned.
 */
export function SolfaView({ url }: { url: string }) {
  const [text, setText] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setText(null);
    setError(null);
    fetchText(url)
      .then((t) => !cancelled && setText(t))
      .catch((e) => !cancelled && setError((e as Error).message));
    return () => {
      cancelled = true;
    };
  }, [url]);

  if (error) return <p className="p-8 text-center text-red-500">{error}</p>;
  if (text === null)
    return <p className="p-8 text-center text-slate-400">Loading sol-fa…</p>;

  return (
    <pre className="overflow-x-auto whitespace-pre rounded-lg bg-slate-50 p-4 font-mono text-sm leading-7 text-slate-800">
      {text}
    </pre>
  );
}
