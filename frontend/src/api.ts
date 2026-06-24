import type { Job, UploadResponse, Voice } from "./types";

const BASE = import.meta.env.VITE_API_BASE ?? "";

export async function uploadScore(
  file: File,
  onProgress?: (fraction: number) => void
): Promise<UploadResponse> {
  return new Promise((resolve, reject) => {
    const form = new FormData();
    form.append("file", file);

    const xhr = new XMLHttpRequest();
    xhr.open("POST", `${BASE}/api/upload`);
    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable && onProgress) onProgress(e.loaded / e.total);
    };
    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        resolve(JSON.parse(xhr.responseText) as UploadResponse);
      } else {
        reject(new Error(xhr.responseText || `Upload failed (${xhr.status})`));
      }
    };
    xhr.onerror = () => reject(new Error("Network error during upload"));
    xhr.send(form);
  });
}

export async function fetchJob(jobId: string): Promise<Job> {
  const res = await fetch(`${BASE}/api/jobs/${jobId}`);
  if (!res.ok) throw new Error(`Failed to fetch job (${res.status})`);
  return (await res.json()) as Job;
}

export async function fetchMusicXml(url: string): Promise<string> {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`Failed to fetch MusicXML (${res.status})`);
  return await res.text();
}

export async function fetchText(url: string): Promise<string> {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`Failed to fetch file (${res.status})`);
  return await res.text();
}

export async function submitCorrections(
  jobId: string,
  corrections: { part_id: string; voice: Voice }[]
): Promise<Job> {
  const res = await fetch(`${BASE}/api/jobs/${jobId}/corrections`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ corrections }),
  });
  if (!res.ok) throw new Error(`Failed to submit corrections (${res.status})`);
  return (await res.json()) as Job;
}
