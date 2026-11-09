import { Loader2 } from 'lucide-react';
import { useT } from '../../i18n/I18nProvider';
export default function RouteFallback() {
  const t = useT();
  return <div role="status" className="flex min-h-48 items-center justify-center gap-2 text-muted">
    <Loader2 size={20} className="animate-spin" aria-hidden="true" />{t("Loading page…")}
  </div>;
}
