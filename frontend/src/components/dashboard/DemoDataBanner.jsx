import { Link } from "react-router-dom";
import { Info } from "lucide-react";

import { intendedBroker } from "../../lib/signupIntent";
import { useT } from "../../i18n/I18nProvider";

// Shown on the demo portfolio only: the numbers are sample data, and the way
// out is one tap, straight to the import of the broker the visitor named.
export default function DemoDataBanner({ portfolio }) {
  const t = useT();
  if (!portfolio?.brokers?.includes("demo")) return null;
  const broker = intendedBroker();
  const to = broker ? `/import?broker=${encodeURIComponent(broker)}` : "/import";

  return (
    <div role="status" className="card flex flex-wrap items-center justify-between gap-x-4 gap-y-3 animate-fade-up">
      <p className="flex items-center gap-2 text-sm font-semibold text-ink">
        <Info size={16} aria-hidden="true" className="shrink-0 text-brand" />
        {t("You're looking at sample data.")}
      </p>
      <Link to={to} className="btn-primary inline-flex min-h-11 items-center text-sm">
        {t("Import your own portfolio")}
      </Link>
    </div>
  );
}
