/*
 * Consumes the per-job WebSocket (ARCHITECTURE.md section 2): one stream,
 * one source of truth for both the Simple Mode status line and Studio
 * Mode's per-node progress fill.
 *
 * A fresh subscribe always replays the job's full event history before
 * streaming new events (see backend api/jobs.py JobManager.subscribe) — the
 * job-level terminal event (node_id "") is always the last thing sent, then
 * the socket closes. That makes an unexpected close *before* a terminal
 * event both detectable and safe to recover from: reconnecting just replays
 * the same history again, so this hook resets its local event log on each
 * (re)connect rather than trying to dedupe a partial stream.
 */

import { useEffect, useRef, useState } from "react";
import { jobEventsUrl } from "./api";
import type { ProgressEvent } from "./types";

export type NodeEvent = ProgressEvent;

const MAX_RECONNECT_ATTEMPTS = 3;
const RECONNECT_DELAY_MS = 500;

export interface JobEventsState {
  events: ProgressEvent[];
  byNode: Record<string, ProgressEvent>;
  terminal: boolean;
  connectionLost: boolean;
}

const EMPTY_STATE: JobEventsState = {
  events: [],
  byNode: {},
  terminal: false,
  connectionLost: false,
};

export function useJobEvents(jobId: string | null): JobEventsState {
  const [state, setState] = useState<JobEventsState>(EMPTY_STATE);

  // Mutable, not state: reconnect bookkeeping must not itself trigger renders.
  const attemptsRef = useRef(0);
  const terminalRef = useRef(false);

  useEffect(() => {
    if (!jobId) {
      setState(EMPTY_STATE);
      return;
    }

    let cancelled = false;
    let socket: WebSocket | null = null;
    let reconnectTimer: ReturnType<typeof setTimeout> | null = null;
    attemptsRef.current = 0;
    terminalRef.current = false;
    setState(EMPTY_STATE);

    function connect() {
      socket = new WebSocket(jobEventsUrl(jobId as string));

      socket.onmessage = (message) => {
        if (cancelled) return;
        const event = JSON.parse(message.data as string) as ProgressEvent;
        if (event.node_id === "" && (event.status === "done" || event.status === "error")) {
          terminalRef.current = true;
        }
        setState((prev) => ({
          events: [...prev.events, event],
          byNode: { ...prev.byNode, [event.node_id]: event },
          terminal: terminalRef.current,
          connectionLost: false,
        }));
      };

      socket.onclose = () => {
        if (cancelled || terminalRef.current) return;
        if (attemptsRef.current >= MAX_RECONNECT_ATTEMPTS) {
          setState((prev) => ({ ...prev, connectionLost: true }));
          return;
        }
        attemptsRef.current += 1;
        reconnectTimer = setTimeout(() => {
          if (!cancelled) {
            setState(EMPTY_STATE); // full replay is coming; discard the partial log
            connect();
          }
        }, RECONNECT_DELAY_MS);
      };
    }

    connect();

    return () => {
      cancelled = true;
      if (reconnectTimer) clearTimeout(reconnectTimer);
      socket?.close();
    };
  }, [jobId]);

  return state;
}
