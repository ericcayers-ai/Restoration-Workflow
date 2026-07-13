/*
 * Undo/redo stack for Studio Mode canvas edits (ROADMAP.md Phase 6).
 */

import { useCallback, useState } from "react";

export function useUndoRedo<T>(initial: T, limit = 48) {
  const [present, setPresent] = useState<T>(initial);
  const [past, setPast] = useState<T[]>([]);
  const [future, setFuture] = useState<T[]>([]);

  const commit = useCallback(
    (next: T | ((prev: T) => T)) => {
      setPresent((prev) => {
        const value = typeof next === "function" ? (next as (p: T) => T)(prev) : next;
        setPast((p) => [...p.slice(-(limit - 1)), prev]);
        setFuture([]);
        return value;
      });
    },
    [limit],
  );

  const undo = useCallback(() => {
    setPast((p) => {
      if (p.length === 0) return p;
      const previous = p[p.length - 1]!;
      setFuture((f) => [present, ...f]);
      setPresent(previous);
      return p.slice(0, -1);
    });
  }, [present]);

  const redo = useCallback(() => {
    setFuture((f) => {
      if (f.length === 0) return f;
      const next = f[0]!;
      setPast((p) => [...p, present]);
      setPresent(next);
      return f.slice(1);
    });
  }, [present]);

  const reset = useCallback((value: T) => {
    setPast([]);
    setFuture([]);
    setPresent(value);
  }, []);

  return { present, commit, undo, redo, reset, canUndo: past.length > 0, canRedo: future.length > 0 };
}
