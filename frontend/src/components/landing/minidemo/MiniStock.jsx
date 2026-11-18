import AppScope from "./AppScope";

// Placeholder body of the "Stock" mini demo; the live content (the app's own
// components on the sample data) arrives in plan section S3. No numbers and
// no charts here, so this chunk stays light.
export default function MiniStock({ language, copy }) {
  return (
    <AppScope language={language}>
      <div className="card p-5"><p className="text-muted">{copy.loading}</p></div>
    </AppScope>
  );
}
