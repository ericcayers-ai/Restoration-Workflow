/*
 * A shared command registry so the command palette (Cmd/Ctrl+K) can reach
 * every action a menu would, from either mode (UI_DESIGN.md section 6 — this
 * is listed under Accessibility, not Phase 6 polish, because keyboard-only
 * operation of the whole app depends on it existing now). Any component can
 * contribute commands with `useRegisterCommands`; they disappear automatically
 * when that component unmounts (e.g. Studio-only actions while in Simple Mode).
 */

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import type { IconName } from "../components/common/Icon";

export interface Command {
  id: string;
  label: string;
  category: string;
  icon?: IconName;
  shortcut?: string;
  run: () => void;
}

interface CommandsContextValue {
  commands: Command[];
  register: (key: string, commands: Command[]) => void;
  unregister: (key: string) => void;
}

const CommandsContext = createContext<CommandsContextValue | null>(null);

export function CommandsProvider({ children }: { children: ReactNode }) {
  const [registry, setRegistry] = useState<Record<string, Command[]>>({});

  const register = useCallback((key: string, commands: Command[]) => {
    setRegistry((prev) => ({ ...prev, [key]: commands }));
  }, []);

  const unregister = useCallback((key: string) => {
    setRegistry((prev) => {
      if (!(key in prev)) return prev;
      const next = { ...prev };
      delete next[key];
      return next;
    });
  }, []);

  const commands = useMemo(() => Object.values(registry).flat(), [registry]);
  const value = useMemo(
    () => ({ commands, register, unregister }),
    [commands, register, unregister],
  );

  return <CommandsContext.Provider value={value}>{children}</CommandsContext.Provider>;
}

function useCommandsContext(): CommandsContextValue {
  const ctx = useContext(CommandsContext);
  if (!ctx) throw new Error("must be used within CommandsProvider");
  return ctx;
}

/** Register a set of commands under `key` for as long as the caller is mounted.
 *  Callers must memoize `commands` (e.g. useMemo) — a new array identity every
 *  render re-registers every render. */
export function useRegisterCommands(key: string, commands: Command[]): void {
  const { register, unregister } = useCommandsContext();
  useEffect(() => {
    register(key, commands);
    return () => unregister(key);
  }, [key, commands, register, unregister]);
}

export function useCommands(): Command[] {
  return useCommandsContext().commands;
}
