import { I18nProvider } from "../../../i18n/I18nProvider";
import { APP_CLAY_SCOPE } from "./appClayScope";

// The wrapper every live mini demo draws inside: the app's own Clay tokens on
// one element (so the real components look as they do in the app) and the
// app's dictionary for the page's language (so their inner labels read in
// Czech or German). The language is only applied here, never saved. Landing
// styles for headings, paragraphs and links do not reach in (see Welcome.css).
export default function AppScope({ language, children }) {
  return (
    <div className="welcome-minidemo-app font-sans text-ink bg-surface" style={APP_CLAY_SCOPE}>
      <I18nProvider initial={language}>{children}</I18nProvider>
    </div>
  );
}
