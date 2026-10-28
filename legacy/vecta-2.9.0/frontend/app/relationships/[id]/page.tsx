"use client";

import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { api, REGION_LABELS, type Contact, type Interaction, type InteractionType } from "@/lib/api";
import PageHeader from "../../components/PageHeader";

export default function ContactDetail() {
  const { id } = useParams<{ id: string }>();
  const [contact, setContact] = useState<Contact | null>(null);
  const [interactions, setInteractions] = useState<Interaction[]>([]);
  const [entryText, setEntryText] = useState("");
  const [entryType, setEntryType] = useState<InteractionType>("note");
  const [entryDueAt, setEntryDueAt] = useState("");
  const [drafting, setDrafting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  function loadContact() {
    api
      .contact(id)
      .then((c) => {
        setContact(c);
        setLoadError(null);
      })
      .catch((e) => setLoadError(e instanceof Error ? e.message : "Failed to load contact"));
    api.contactInteractions(id).then(setInteractions).catch(() => {});
  }

  useEffect(() => {
    loadContact();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  async function addEntry() {
    if (!entryText.trim()) return;
    await api.createInteraction({
      contact_id: id,
      type: entryType,
      content: entryText.trim(),
      due_at: entryType === "task" && entryDueAt ? new Date(entryDueAt).toISOString() : null,
    });
    setEntryText("");
    setEntryDueAt("");
    loadContact();
  }

  async function toggleTaskDone(interactionId: string, completed: boolean) {
    await api.markTaskComplete(interactionId, completed);
    loadContact();
  }

  async function draft() {
    setDrafting(true);
    setError(null);
    try {
      await api.draftOutreach(id, contact?.opportunity_id ?? undefined);
      loadContact();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Draft failed");
    } finally {
      setDrafting(false);
    }
  }

  async function markSent(interactionId: string) {
    await api.markInteractionSent(interactionId);
    loadContact();
  }

  if (loadError) {
    return (
      <div className="panel p-5" style={{ borderColor: "var(--danger)" }} role="alert">
        <p className="text-sm font-semibold mb-1" style={{ color: "var(--danger)" }}>
          Couldn&apos;t load this contact
        </p>
        <p className="text-sm text-muted mb-3">{loadError}</p>
        <button onClick={loadContact} className="btn btn-secondary text-xs">
          Try again
        </button>
      </div>
    );
  }
  if (!contact) return <p className="text-sm text-muted">Loading…</p>;

  const subtitle = [contact.role ?? "Role unknown", contact.organisation_name, contact.region ? REGION_LABELS[contact.region] : null]
    .filter(Boolean)
    .join(" · ");

  return (
    <div>
      <PageHeader
        eyebrow="Relationship Intelligence"
        title={contact.name}
        description={subtitle}
        back={{ label: "Back to directory", href: "/relationships" }}
      />

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
        <div className="lg:col-span-2 space-y-5">
          <div className="panel p-5">
            {contact.connection_path && (
              <p className="text-sm text-muted mb-2.5">
                <span className="text-accent font-medium">Approach: </span>
                {contact.connection_path}
              </p>
            )}
            {contact.opportunity_title && (
              <p className="text-sm text-muted mb-2.5">
                <span className="text-accent font-medium">Linked opportunity: </span>
                {contact.opportunity_title}
              </p>
            )}
            {contact.linkedin_search_url && (
              <a href={contact.linkedin_search_url} target="_blank" rel="noreferrer" className="btn-ghost text-xs -ml-2">
                Search on LinkedIn →
              </a>
            )}
          </div>

          <div className="panel p-5">
            <div className="flex items-center justify-between mb-3">
              <h2 className="text-sm font-semibold text-main">Outreach &amp; interactions</h2>
              <button onClick={draft} disabled={drafting} className="btn btn-secondary text-xs">
                {drafting ? "Drafting…" : "Draft outreach message"}
              </button>
            </div>
            {error && (
              <p role="alert" className="text-sm mb-3" style={{ color: "var(--danger)" }}>
                {error}
              </p>
            )}
            <div className="space-y-2.5 mb-4">
              {interactions.length === 0 && <p className="text-sm text-muted">No interactions logged yet.</p>}
              {interactions.map((i) => (
                <div key={i.id} className="panel-raised p-3">
                  <div className="flex items-center justify-between mb-1">
                    <span className="badge badge-neutral capitalize">
                      {i.type} {i.draft && !i.sent ? "· draft" : i.sent ? "· sent" : ""}
                      {i.type === "task" && i.completed ? " · done" : ""}
                    </span>
                    <div className="flex items-center gap-3">
                      {i.type === "task" && !i.completed && (
                        <button onClick={() => toggleTaskDone(i.id, true)} className="btn-ghost text-xs">
                          Mark done
                        </button>
                      )}
                      {i.type === "task" && i.completed && (
                        <button onClick={() => toggleTaskDone(i.id, false)} className="btn-ghost text-xs">
                          Undo
                        </button>
                      )}
                      {i.draft && !i.sent && (
                        <button onClick={() => markSent(i.id)} className="btn-ghost text-xs">
                          Mark as sent
                        </button>
                      )}
                    </div>
                  </div>
                  {i.type === "task" && i.due_at && (
                    <p className="text-xs text-muted mb-1">
                      Due {new Date(i.due_at).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" })}
                    </p>
                  )}
                  <p className="text-sm text-main whitespace-pre-line mt-2">{i.content}</p>
                </div>
              ))}
            </div>
            <div className="flex flex-wrap gap-2 mb-2">
              <div className="field">
                <label htmlFor="entry-type" className="field-label">Type</label>
                <select
                  id="entry-type"
                  value={entryType}
                  onChange={(e) => setEntryType(e.target.value as InteractionType)}
                  className="input"
                  style={{ padding: "0.45rem 0.6rem", fontSize: "0.8rem" }}
                >
                  <option value="note">Note</option>
                  <option value="task">Task</option>
                  <option value="meeting">Meeting</option>
                  <option value="message">Message</option>
                </select>
              </div>
              {entryType === "task" && (
                <div className="field">
                  <label htmlFor="entry-due" className="field-label">Due date</label>
                  <input
                    id="entry-due"
                    type="date"
                    value={entryDueAt}
                    onChange={(e) => setEntryDueAt(e.target.value)}
                    className="input"
                    style={{ padding: "0.45rem 0.6rem", fontSize: "0.8rem" }}
                  />
                </div>
              )}
            </div>
            <div className="field">
              <label htmlFor="note-input" className="field-label">
                {entryType === "task" ? "What needs doing?" : "Log a note, call, or task"}
              </label>
              <div className="flex gap-2">
                <input
                  id="note-input"
                  value={entryText}
                  onChange={(e) => setEntryText(e.target.value)}
                  placeholder="What happened?"
                  className="input flex-1"
                  onKeyDown={(e) => e.key === "Enter" && addEntry()}
                />
                <button onClick={addEntry} className="btn btn-primary">
                  Add
                </button>
              </div>
            </div>
          </div>
        </div>

        <div className="panel p-5 h-fit">
          <h2 className="text-sm font-semibold text-main mb-3">Relevance</h2>
          <div className="flex items-baseline gap-2 mb-2">
            <span className="text-3xl font-semibold text-accent font-display">{contact.relevance_score}</span>
            <span className="text-muted text-sm">/ 100</span>
          </div>
          <div
            className="h-1.5 rounded-full mb-4"
            style={{ background: "var(--panel-raised)" }}
            role="progressbar"
            aria-valuenow={contact.relevance_score}
            aria-valuemin={0}
            aria-valuemax={100}
            aria-label="Relevance score"
          >
            <div className="h-1.5 rounded-full" style={{ width: `${contact.relevance_score}%`, background: "var(--accent)" }} />
          </div>
          <p className="text-xs text-muted">Source: {contact.source === "ai_research" ? "AI research" : "Manual"}</p>
        </div>
      </div>
    </div>
  );
}
