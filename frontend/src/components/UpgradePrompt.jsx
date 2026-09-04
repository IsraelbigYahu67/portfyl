import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { LockKeyhole, X } from "lucide-react";


export default function UpgradePrompt() {
  const [denial, setDenial] = useState(null);

  useEffect(() => {
    const show = (event) => setDenial(event.detail || { code: "plan_upgrade_required" });
    window.addEventListener("portfyl:entitlement-denied", show);
    return () => window.removeEventListener("portfyl:entitlement-denied", show);
  }, []);

  if (!denial) return null;
  const readOnly = denial.code === "resource_read_only";
  const quota = denial.code === "quota_exceeded";
  return (
    <div className="fixed bottom-5 right-5 z-50 max-w-sm rounded-xl border border-brand/40 bg-surface-card p-4 shadow-xl">
      <button
        type="button"
        aria-label="Dismiss upgrade prompt"
        onClick={() => setDenial(null)}
        className="absolute right-3 top-3 text-muted hover:text-ink"
      >
        <X size={15} />
      </button>
      <div className="flex gap-3 pr-5">
        <LockKeyhole size={19} className="mt-0.5 shrink-0 text-brand" />
        <div>
          <p className="font-semibold">
            {readOnly ? "This item is read-only on your plan" : quota ? "Plan limit reached" : "Upgrade required"}
          </p>
          <p className="mt-1 text-sm text-muted">
            Your data is preserved. Review plan access and limits to continue using this action.
          </p>
          <Link
            to="/pricing"
            onClick={() => setDenial(null)}
            className="mt-3 inline-flex rounded-lg bg-brand px-3 py-2 text-sm font-semibold text-black"
          >
            Compare plans
          </Link>
        </div>
      </div>
    </div>
  );
}
