import { useCallback, useEffect, useState } from "react";

export async function api(path, options = {}) {
  const response = await fetch("/api" + path, { cache: "no-store", ...options });
  const body = await response.json();
  if (!response.ok) throw new Error(body.error || "The local service is unavailable.");
  return body;
}

export function useResource(path, poll = false) {
  const [result, setResult] = useState({});
  const [revision, setRevision] = useState(0);
  const refresh = useCallback(() => setRevision(value => value + 1), []);
  useEffect(() => {
    if (!path) return;
    const controller = new AbortController();
    let timer;
    async function load() {
      try {
        const data = await api(path, { signal: AbortSignal.any([controller.signal, AbortSignal.timeout(7000)]) });
        if (!controller.signal.aborted) setResult({ path, data });
      } catch (error) {
        if (!controller.signal.aborted) setResult(previous => ({
          path, data: previous.path === path ? previous.data : undefined, error: error.message,
        }));
      } finally {
        if (poll && !controller.signal.aborted) timer = setTimeout(load, 2000);
      }
    }
    load();
    return () => {
      controller.abort();
      clearTimeout(timer);
    };
  }, [path, poll, revision]);
  return { ...(result.path === path ? result : {}), refresh };
}
