/*
 * The app shell: mode switch (Simple | Studio), the two screens (both stay
 * mounted — hidden, not unmounted, when inactive — so switching modes never
 * discards a half-built Studio pipeline), theme/scale controls, and the
 * command palette. "Both modes share one engine — Simple Mode is not a
 * stripped-down separate app" (ROADMAP.md vision) is why "Open in Studio"
 * is just state lifted to this level, not a page navigation.
 */

import { useMemo, useRef, useState } from "react";
import { SimpleMode } from "./components/simple/SimpleMode";
import { StudioMode, type StudioHandoff } from "./components/studio/StudioMode";
import { CommandPalette } from "./components/common/CommandPalette";
import { ScaleControl, ThemeToggle } from "./components/common/PreferencesBar";
import { SettingsPanel } from "./components/common/SettingsPanel";
import { Icon } from "./components/common/Icon";
import { useRegisterCommands } from "./lib/commands";
import { useT } from "./lib/i18n";
import type { PipelineJson } from "./lib/types";
import styles from "./App.module.css";

type Mode = "simple" | "studio";

const OPEN_COMMANDS_EVENT = "rw:open-commands";

function modKeyLabel(): string {
  if (typeof navigator === "undefined") return "Ctrl";
  return /Mac|iPhone|iPad|iPod/i.test(navigator.platform) ? "⌘" : "Ctrl";
}

export function App() {
  const t = useT();
  const [mode, setMode] = useState<Mode>("simple");
  const [handoff, setHandoff] = useState<StudioHandoff | null>(null);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const handoffCounter = useRef(0);
  const shortcut = `${modKeyLabel()}+K`;

  function openInStudio(pipeline: PipelineJson, file: File) {
    handoffCounter.current += 1;
    setHandoff({ pipeline, file, token: handoffCounter.current });
    setMode("studio");
  }

  const commands = useMemo(
    () => [
      {
        id: "app.switch-simple",
        label: t("app.switchToSimple"),
        category: "General",
        icon: "aperture" as const,
        run: () => setMode("simple"),
      },
      {
        id: "app.switch-studio",
        label: t("app.switchToStudio"),
        category: "General",
        icon: "flow" as const,
        run: () => setMode("studio"),
      },
      {
        id: "app.open-settings",
        label: t("settings.open"),
        category: "General",
        icon: "settings" as const,
        run: () => setSettingsOpen(true),
      },
    ],
    [t],
  );
  useRegisterCommands("app-shell", commands);

  return (
    <div className={styles.app}>
      <header className={styles.topBar}>
        <div className={styles.brand}>
          <Icon name="aperture" size={16} className={styles.brandIcon} aria-hidden />
          <span className={styles.title}>{t("app.title")}</span>
        </div>
        <div className={styles.modeSwitch} role="tablist" aria-label={t("app.modeSwitch")}>
          <button
            type="button"
            role="tab"
            aria-selected={mode === "simple"}
            className={mode === "simple" ? styles.modeActive : styles.modeTab}
            onClick={() => setMode("simple")}
          >
            {t("app.modeSimple")}
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={mode === "studio"}
            className={mode === "studio" ? styles.modeActive : styles.modeTab}
            onClick={() => setMode("studio")}
          >
            {t("app.modeStudio")}
          </button>
        </div>
        <div className={styles.spacer} />
        <div className={styles.utilities}>
          <button
            type="button"
            className={styles.iconButton}
            onClick={() => window.dispatchEvent(new Event(OPEN_COMMANDS_EVENT))}
            aria-label={t("commandPalette.title")}
            title={`${t("commandPalette.title")} (${shortcut})`}
          >
            <Icon name="command" size={14} />
            <kbd className={styles.commandHint}>{shortcut}</kbd>
          </button>
          <span className={styles.divider} aria-hidden />
          <ThemeToggle />
          <ScaleControl />
          <button
            type="button"
            className={styles.iconButton}
            onClick={() => setSettingsOpen(true)}
            aria-label={t("settings.open")}
            title={t("settings.open")}
          >
            <Icon name="settings" size={16} />
          </button>
        </div>
      </header>

      <main className={styles.main}>
        {/* Both stay mounted (state-preserving mode switch); `display: none`
            is set inline so it always wins over `.modePane`'s own
            `display: flex` — the `hidden` attribute alone does NOT do this,
            since an author rule setting `display` on the same element beats
            the `[hidden]` user-agent style at equal specificity. */}
        <div className={styles.modePane} style={{ display: mode === "simple" ? "flex" : "none" }}>
          <SimpleMode onOpenInStudio={openInStudio} />
        </div>
        <div className={styles.modePane} style={{ display: mode === "studio" ? "flex" : "none" }}>
          <StudioMode handoff={handoff} />
        </div>
      </main>

      <CommandPalette />
      <SettingsPanel open={settingsOpen} onClose={() => setSettingsOpen(false)} />
    </div>
  );
}
