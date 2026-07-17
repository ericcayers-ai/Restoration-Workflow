import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "./styles/tokens.css";
import "./styles/global.css";
import { App } from "./App";
import { PreferencesProvider } from "./lib/preferences";
import { I18nProvider } from "./lib/i18n";
import { CommandsProvider } from "./lib/commands";
import { WeightDownloadsProvider } from "./lib/useWeightDownloads";

const container = document.getElementById("root");
if (!container) throw new Error("#root element is missing from index.html");

createRoot(container).render(
  <StrictMode>
    <PreferencesProvider>
      <I18nProvider>
        <CommandsProvider>
          <WeightDownloadsProvider>
            <App />
          </WeightDownloadsProvider>
        </CommandsProvider>
      </I18nProvider>
    </PreferencesProvider>
  </StrictMode>,
);
