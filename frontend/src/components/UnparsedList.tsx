import { useQuery } from "@tanstack/react-query";
import { api } from "../api";
import { relative } from "../format";

export function UnparsedList({ month, onClose }: { month: string; onClose: () => void }) {
  const q = useQuery({ queryKey: ["unknown", month], queryFn: () => api.unknownEmails(month) });
  return (
    <section className="rounded-xl bg-white p-4 shadow-sm ring-1 ring-slate-200 dark:bg-slate-900 dark:ring-slate-800">
      <div className="mb-2 flex items-center justify-between">
        <h2 className="font-semibold">Emails that need a parser</h2>
        <button onClick={onClose} className="text-sm text-slate-500 hover:underline">
          Close
        </button>
      </div>
      <p className="mb-3 text-xs text-slate-500">
        No parser matched these. Run <code>uv run python -m app.ingest.survey</code> to see their bodies.
      </p>
      {q.isPending && <p className="text-sm text-slate-500">Loading…</p>}
      {q.error && <p className="text-sm text-rose-600">{q.error.message}</p>}
      <ul className="space-y-2 text-sm">
        {q.data?.map((e) => (
          <li key={e.id} className="border-t border-slate-100 pt-2 dark:border-slate-800">
            <div className="font-medium">{e.subject || "(no subject)"}</div>
            <div className="text-xs text-slate-500">
              {e.sender} · {relative(e.received_at)}
              {e.parse_error && <span className="text-rose-600"> · {e.parse_error}</span>}
            </div>
          </li>
        ))}
      </ul>
    </section>
  );
}
