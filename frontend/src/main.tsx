import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "./styles/tokens.css";
import "./styles/global.css";
import { App } from "./App";
import { PreferencesProvider, usePreferences } from "./lib/preferences";
import { I18nProvider } from "./lib/i18n";
import { CommandsProvider } from "./lib/commands";
import { WeightDownloadsProvider } from "./lib/useWeightDownloads";
import { ToastProvider } from "./components/common/Toast";
import { ErrorBoundary } from "./components/common/ErrorBoundary";
import type { ReactNode } from "react";

function LocaleBridge({ children }: { children: ReactNode }) {
  const { locale } = usePreferences();
  return <I18nProvider locale={locale}>{children}</I18nProvider>;
}

const container = document.getElementById("root");
if (!container) throw new Error("#root element is missing from index.html");

createRoot(container).render(
  <StrictMode>
    <ErrorBoundary>
      <PreferencesProvider>
        <LocaleBridge>
          <CommandsProvider>
            <WeightDownloadsProvider>
              <ToastProvider>
                <App />
              </ToastProvider>
            </WeightDownloadsProvider>
          </CommandsProvider>
        </LocaleBridge>
      </PreferencesProvider>
    </ErrorBoundary>
  </StrictMode>,
);
