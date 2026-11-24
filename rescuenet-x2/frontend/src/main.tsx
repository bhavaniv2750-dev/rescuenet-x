import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
// Fonts and map styles are bundled locally: nothing essential is fetched from a CDN at runtime.
import "@fontsource/inter/400.css";
import "@fontsource/inter/500.css";
import "@fontsource/inter/600.css";
import "@fontsource/inter/700.css";
import "@fontsource/jetbrains-mono/400.css";
import "@fontsource/jetbrains-mono/700.css";
import "leaflet/dist/leaflet.css";
import "./design/tokens.css";
import "./index.css";
import "./theme.css";
import "./design/ui.css";
import "./design/shell.css";
import App from "./App";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>
);
