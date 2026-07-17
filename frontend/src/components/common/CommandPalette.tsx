/*
 * Cmd/Ctrl+K, reaching every action a menu would (UI_DESIGN.md section 6).
 * Fully keyboard-driven: arrow keys move the selection, Enter runs it,
 * Escape closes and returns focus to whatever had it before the palette
 * opened — a mouse is never required to reach it or use it.
 */

import { useEffect, useMemo, useRef, useState } from "react";
import { useCommands, type Command } from "../../lib/commands";
import { useT } from "../../lib/i18n";
import { useFocusTrap } from "../../lib/useFocusTrap";
import { Icon } from "./Icon";
import styles from "./CommandPalette.module.css";

export function CommandPalette() {
  const t = useT();
  const commands = useCommands();
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [activeIndex, setActiveIndex] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);
  const close = () => setOpen(false);

  useFocusTrap(open, panelRef, close);

  const results = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (!needle) return commands;
    return commands.filter(
      (c) =>
        c.label.toLowerCase().includes(needle) || c.category.toLowerCase().includes(needle),
    );
  }, [commands, query]);

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      const isModK = (event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k";
      if (isModK) {
        event.preventDefault();
        setOpen((prev) => !prev);
      }
    }
    function onOpenRequest() {
      setOpen(true);
    }
    window.addEventListener("keydown", onKeyDown);
    window.addEventListener("rw:open-commands", onOpenRequest);
    return () => {
      window.removeEventListener("keydown", onKeyDown);
      window.removeEventListener("rw:open-commands", onOpenRequest);
    };
  }, []);

  useEffect(() => {
    if (!open) return;
    setQuery("");
    setActiveIndex(0);
    requestAnimationFrame(() => inputRef.current?.focus());
  }, [open]);

  useEffect(() => {
    setActiveIndex(0);
  }, [query]);

  function runCommand(command: Command) {
    setOpen(false);
    command.run();
  }

  function onInputKeyDown(event: React.KeyboardEvent<HTMLInputElement>) {
    if (event.key === "ArrowDown") {
      event.preventDefault();
      setActiveIndex((i) => Math.min(i + 1, results.length - 1));
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      setActiveIndex((i) => Math.max(i - 1, 0));
    } else if (event.key === "Enter") {
      event.preventDefault();
      const command = results[activeIndex];
      if (command) runCommand(command);
    }
  }

  if (!open) return null;

  return (
    <div
      className={styles.overlay}
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) setOpen(false);
      }}
    >
      <div
        ref={panelRef}
        className={styles.panel}
        role="dialog"
        aria-modal="true"
        aria-label={t("commandPalette.title")}
      >
        <div className={styles.searchRow}>
          <Icon name="command" size={16} />
          <input
            ref={inputRef}
            className={styles.input}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={onInputKeyDown}
            placeholder={t("commandPalette.placeholder")}
            aria-label={t("commandPalette.placeholder")}
            role="combobox"
            aria-expanded="true"
            aria-controls="command-palette-list"
            aria-activedescendant={
              results[activeIndex] ? `command-item-${results[activeIndex].id}` : undefined
            }
          />
        </div>
        {results.length === 0 ? (
          <p className={styles.empty}>{t("commandPalette.empty")}</p>
        ) : (
          <ul className={styles.list} id="command-palette-list" role="listbox">
            {results.map((command, index) => (
              <li
                key={command.id}
                id={`command-item-${command.id}`}
                role="option"
                aria-selected={index === activeIndex}
                className={`${styles.item} ${index === activeIndex ? styles.itemActive : ""}`}
                onMouseEnter={() => setActiveIndex(index)}
                onClick={() => runCommand(command)}
              >
                {command.icon ? <Icon name={command.icon} size={16} /> : null}
                <span>{command.label}</span>
                <span className={styles.category}>{command.shortcut ?? command.category}</span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
