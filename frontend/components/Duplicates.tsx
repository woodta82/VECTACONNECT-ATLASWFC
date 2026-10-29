"use client";

import Link from "next/link";
import { Tag } from "@/components/Records";
import { ActionNote } from "@/components/Ui";
import { api } from "@/lib/api";
import { label } from "@/lib/format";
import { useAction } from "@/lib/useAction";

type DupPerson = { id: string; full_name: string; role_title: string | null; organisation: string | null; origin: string; evidence: number;
                   opportunities: { id: string; title: string }[] | null; state: string | null };
export type Duplicate = { id: string; reason: string; status: string; a: DupPerson; b: DupPerson; merge_id: string | null };

/** Possible duplicates: the same name where the organisation is unknown or differs. Nothing is merged automatically; a merge
 *  keeps every piece of evidence and can be undone. */
export function DuplicateReview({ items, onChanged, title }: { items: Duplicate[]; onChanged: () => void; title: string }) {
  const a = useAction();
  return (
    <section className="panel" aria-label={title}>
      <h2>{title}</h2>
      <ActionNote state={a} />
      {items.length === 0 && <p className="muted">None to review. Records that share a name are listed here when their organisation is unknown or
        differs; nothing is merged automatically.</p>}
      <ul className="list-plain">{items.map((d) => (
        <li key={d.id} className="small">
          <div><Tag text={d.status === "open" ? "To review" : label(d.status)} tone={d.status === "open" ? "b-warn" : "b-none"} /> {d.reason}</div>
          <div className="grid grid-2">{[d.a, d.b].map((x) => (
            <div key={x.id}><Link href={`/relationships/${x.id}`}>{x.full_name}</Link> · {x.role_title ?? "title not established"} · {x.organisation ?? "organisation not established"}
              <div className="muted">{x.evidence} evidence record(s) · found by {label(x.origin)}{(x.opportunities ?? []).length ? ` · ${(x.opportunities ?? []).map((o) => o.title).join(", ")}` : ""}</div>
              {d.status === "open" && <button type="button" className="btn btn-small" disabled={a.busy}
                onClick={() => a.run(() => api.post(`/people/duplicates/${d.id}/merge`, { keep_id: x.id, note: "same person (reviewed)" }), "Merged: it can be undone").then(onChanged)}>
                Same person: keep this record</button>}</div>))}</div>
          {d.status === "open" && <button type="button" className="btn btn-ghost btn-small" disabled={a.busy}
            onClick={() => a.run(() => api.post(`/people/duplicates/${d.id}/dismiss`, { note: "different people (reviewed)" }), "Kept as different people").then(onChanged)}>
            Different people</button>}
          {d.status === "merged" && d.merge_id && <button type="button" className="btn btn-ghost btn-small" disabled={a.busy}
            onClick={() => a.run(() => api.post(`/people/merges/${d.merge_id}/undo`), "Merge undone").then(onChanged)}>Undo merge</button>}
        </li>))}</ul>
    </section>
  );
}
