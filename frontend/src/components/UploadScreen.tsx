import { useCallback, useRef, useState } from "react";
import { uploadScore } from "../api";

const ACCEPT = ".pdf,.jpg,.jpeg,.png,.tif,.tiff,.bmp,.sol,.solfa,.txt";

export function UploadScreen({ onUploaded }: { onUploaded: (jobId: string) => void }) {
  const [dragging, setDragging] = useState(false);
  const [uploadFraction, setUploadFraction] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const handleFile = useCallback(
    async (file: File) => {
      setError(null);
      setUploadFraction(0);
      try {
        const res = await uploadScore(file, setUploadFraction);
        onUploaded(res.job_id);
      } catch (e) {
        setError((e as Error).message);
        setUploadFraction(null);
      }
    },
    [onUploaded]
  );

  const onDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setDragging(false);
      const file = e.dataTransfer.files?.[0];
      if (file) handleFile(file);
    },
    [handleFile]
  );

  return (
    <div className="mx-auto max-w-2xl px-4">
      <div
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
        onClick={() => inputRef.current?.click()}
        className={[
          "flex cursor-pointer flex-col items-center justify-center rounded-2xl border-2 border-dashed p-16 text-center transition-colors",
          dragging
            ? "border-indigo-500 bg-indigo-50"
            : "border-slate-300 bg-white hover:border-indigo-400",
        ].join(" ")}
      >
        <svg
          className="mb-4 h-12 w-12 text-indigo-500"
          fill="none"
          viewBox="0 0 24 24"
          strokeWidth={1.5}
          stroke="currentColor"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            d="M3 16.5v2.25A2.25 2.25 0 0 0 5.25 21h13.5A2.25 2.25 0 0 0 21 18.75V16.5m-13.5-9L12 3m0 0 4.5 4.5M12 3v13.5"
          />
        </svg>
        <p className="text-lg font-medium text-slate-700">
          Drag &amp; drop a score, or click to browse
        </p>
        <p className="mt-1 text-sm text-slate-400">
          Sheet music (PDF, JPG, PNG) or a Tonic Sol-fa file (.sol, .solfa, .txt)
        </p>
        <input
          ref={inputRef}
          type="file"
          accept={ACCEPT}
          className="hidden"
          onChange={(e) => {
            const file = e.target.files?.[0];
            if (file) handleFile(file);
          }}
        />
      </div>

      {uploadFraction !== null && (
        <div className="mt-6">
          <div className="h-2 w-full overflow-hidden rounded-full bg-slate-200">
            <div
              className="h-full rounded-full bg-indigo-500 transition-all"
              style={{ width: `${Math.round(uploadFraction * 100)}%` }}
            />
          </div>
          <p className="mt-2 text-center text-sm text-slate-500">
            Uploading… {Math.round(uploadFraction * 100)}%
          </p>
        </div>
      )}

      {error && (
        <p className="mt-4 rounded-lg bg-red-50 p-3 text-center text-sm text-red-600">
          {error}
        </p>
      )}
    </div>
  );
}
