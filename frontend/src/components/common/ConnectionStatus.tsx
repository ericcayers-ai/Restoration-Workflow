/*
 * Lightweight connection-status indicator. Polls /api/health with
 * exponential backoff when disconnected, steady 10s interval when connected.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { health } from "../../lib/api";

export function ConnectionStatus() {
  const [connected, setConnected] = useState<boolean | null>(null);
  const retriesRef = useRef(0);
  const timerRef = useRef<ReturnType<typeof setTimeout>>();

  const check = useCallback(async () => {
    try {
      const h = await health();
      setConnected(h ? true : false);
      retriesRef.current = 0;
    } catch {
      setConnected(false);
      retriesRef.current = Math.min(retriesRef.current + 1, 8);
    }
    const delay = connected
      ? 10_000
      : Math.min(2000 * (retriesRef.current + 1), 30_000);
    timerRef.current = setTimeout(check, delay);
  }, [connected]);

  useEffect(() => {
    void check();
    return () => clearTimeout(timerRef.current);
  }, [check]);

  if (connected === null) return null;

  const s = 8;
  return (
    <span
      style={{
        display: "inline-block",
        width: s,
        height: s,
        borderRadius: "50%",
        background: connected ? "var(--accent-teal)" : "var(--accent-brick)",
        boxShadow: connected
          ? "0 0 4px var(--accent-teal)"
          : "0 0 4px var(--accent-brick)",
        transition: "background var(--motion-base)",
      }}
      role="status"
      aria-label={connected ? "Server connected" : "Server disconnected"}
      title={connected ? "Connected" : "Disconnected"}
    />
  );
}
