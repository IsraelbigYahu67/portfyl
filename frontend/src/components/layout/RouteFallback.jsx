import { Loader2 } from 'lucide-react';
export default function RouteFallback() {
  return <div role="status" className="flex min-h-48 items-center justify-center gap-2 text-muted">
    <Loader2 size={20} className="animate-spin" aria-hidden="true" />Loading page…
  </div>;
}
