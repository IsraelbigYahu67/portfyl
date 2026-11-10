// The "or" rule between alternative ways to prove identity (Google vs.
// e-mail and password). Purely decorative, so it is hidden from assistive tech.
import { useT } from "../../i18n/I18nProvider";

export default function AuthMethodDivider() {
  const t = useT();
  return (
    <div className="flex items-center gap-3 text-xs text-muted" aria-hidden="true">
      <span className="h-px flex-1 bg-hairline" />
      {t("or")}
      <span className="h-px flex-1 bg-hairline" />
    </div>
  );
}
