"use client";

import Link from "next/link";
import { useState, type FormEvent } from "react";
import { Tag } from "@/components/Records";
import { Empty, ErrorState, Loading, PageHeader, StaleBanner, TableWrap } from "@/components/States";
import { ActionNote, Tabs } from "@/components/Ui";
import { api, qs } from "@/lib/api";
import { dateOnly } from "@/lib/format";
import { useAction } from "@/lib/useAction";
import { useApi } from "@/lib/useApi";
import { DuplicateReview, type Duplicate } from "@/components/Duplicates";

type Person = { id: string; full_name: string; role_title: string | null; organisation: string | null; state: string; state_label: string;
                relationship_owner: string | null; next_action: string | null; next_action_due: string | null; last_verified_at: string | null;
                linkedin_profile_url: string | null; linkedin_search_url: string; opportunities: number; possible_routes: number; last_engagement: string | null };
type Page = { items: Person[]; total: number; states: Record<string, string> };
type StateTab = "" | "research_candidate" | "identity_confirmed" | "existing_relationship" | "introduction_available";

const STATE_TONE: Record<string, string> = { existing_relationship: "b-good", introduction_available: "b-good", identity_confirmed: "b-info",
                                                    research_candidate: "b-warn" };

export default function RelationshipsPage() {
  const [tab, setTab] = useState<StateTab>("");
  const [q, setQ] = useState("");
  const [actions, setActions] = useState(false);
  const r = useApi<Page>(`/people${qs({ states: tab, q, has_action: actions ? "true" : undefined, limit: 100 })}`);
  return (
    <>
      <PageHeader eyebrow="Relationships" title="People, relationships and introduction routes"
                  description="Every person ATLAS has found or the team has added, with the evidence for who they are, why they matter, who at WFC knows them and who could introduce us. A public association between two people is never treated as a relationship." />
      <Tabs<StateTab> label="Research status" value={tab} onChange={setTab} tabs={[
        { id: "", label: "Everyone" }, { id: "research_candidate", label: "Research candidates" }, { id: "identity_confirmed", label: "Identity and role confirmed" },
        { id: "existing_relationship", label: "Existing relationship" }, { id: "introduction_available", label: "Introduction available" }]} />
      <div className="filters">
        <label className="field">Search<input className="input" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Name, role or organisation" /></label>
        <label className="field inline"><input type="checkbox" checked={actions} onChange={(e) => setActions(e.target.checked)} /> With a next action</label>
      </div>
      {r.stale && <StaleBanner onRetry={r.reload} />}
      {r.status === "loading" && <Loading what="people" />}
      {r.status === "error" && !r.data && <ErrorState error={r.error} onRetry={r.reload} />}
      {r.data && (r.data.items.length === 0 ? <Empty title="No people yet">Open an opportunity and choose Research relationships, or add a person below.</Empty> : (
        <TableWrap label="People">
          <table><thead><tr><th>Person</th><th>Organisation</th><th>Status</th><th>Relationship owner</th><th>Opportunities</th><th>Next action</th><th>LinkedIn</th></tr></thead>
            <tbody>{r.data.items.map((p) => (
              <tr key={p.id}>
                <td><Link href={`/relationships/${p.id}`}>{p.full_name}</Link><div className="small muted">{p.role_title ?? "role not established"}</div></td>
                <td>{p.organisation ?? <span className="muted">Not established</span>}</td>
                <td><Tag text={p.state_label} tone={STATE_TONE[p.state]} />{p.possible_routes > 0 && p.state !== "introduction_available" &&
                  <div className="small muted">{p.possible_routes} possible route(s)</div>}</td>
                <td className="small">{p.relationship_owner ?? <span className="muted">Not recorded</span>}</td>
                <td className="num">{p.opportunities}</td>
                <td className="small">{p.next_action ?? <span className="muted">None</span>}{p.next_action_due && <div className="muted">due {dateOnly(p.next_action_due)}</div>}</td>
                <td className="small">{p.linkedin_profile_url ? <a href={p.linkedin_profile_url} target="_blank" rel="noreferrer noopener">Confirmed profile</a>
                  : <a href={p.linkedin_search_url} target="_blank" rel="noreferrer noopener">Search</a>}</td>
              </tr>
            ))}</tbody></table>
        </TableWrap>
      ))}
      <Duplicates onChanged={r.reload} />
      <AddPerson onAdded={r.reload} />
    </>
  );
}

function Duplicates({ onChanged }: { onChanged: () => void }) {
  const d = useApi<{ items: Duplicate[] }>("/people/duplicates?status=open");
  if (!d.data) return null;
  return (
    <div id="duplicates" style={{ marginTop: 16 }}>
      {/* always the same component, so its confirmation stays visible after the last pair is resolved */}
      <DuplicateReview items={d.data.items} title="Possible duplicates" onChanged={() => { d.reload(); onChanged(); }} />
    </div>
  );
}

function AddPerson({ onAdded }: { onAdded: () => void }) {
  const [f, setF] = useState({ full_name: "", role_title: "", organisation_label: "", source_url: "" });
  const a = useAction();
  async function submit(e: FormEvent) {
    e.preventDefault();
    const body = { full_name: f.full_name, role_title: f.role_title || null, organisation_label: f.organisation_label || null,
                   source_url: f.source_url || null, source_note: f.source_url ? null : "added by a reviewer" };
    if (await a.run(() => api.post("/people", body), "Person added as a research candidate")) {
      setF({ full_name: "", role_title: "", organisation_label: "", source_url: "" }); onAdded();
    }
  }
  return (
    <section className="panel" aria-label="Add a person" style={{ marginTop: 16 }}>
      <h2>Add a person</h2>
      <form className="form-grid" onSubmit={submit}>
        <label className="field">Full name<input className="input" required minLength={3} value={f.full_name} onChange={(e) => setF({ ...f, full_name: e.target.value })} /></label>
        <label className="field">Role or title<input className="input" value={f.role_title} onChange={(e) => setF({ ...f, role_title: e.target.value })} /></label>
        <label className="field">Organisation<input className="input" value={f.organisation_label} onChange={(e) => setF({ ...f, organisation_label: e.target.value })} /></label>
        <label className="field">Source URL (optional)<input className="input" value={f.source_url} onChange={(e) => setF({ ...f, source_url: e.target.value })} /></label>
        <div className="actions"><button className="btn btn-primary" type="submit" disabled={a.busy}>Add</button></div>
      </form>
      <ActionNote state={a} />
    </section>
  );
}
