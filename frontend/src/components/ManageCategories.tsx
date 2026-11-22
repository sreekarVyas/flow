import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api, type Category, type Rule } from "../api";
import { KIND_LABEL, useCategories } from "../categories";

const inputClass =
  "rounded-lg border border-line bg-surface px-2.5 py-1.5 text-base focus:border-stamp focus:outline-none";
const linkClass = "text-sm font-medium text-stamp hover:underline disabled:opacity-50";

function useInvalidate() {
  const qc = useQueryClient();
  return () => {
    qc.invalidateQueries({ queryKey: ["categories"] });
    qc.invalidateQueries({ queryKey: ["categorySummary"] });
    qc.invalidateQueries({ queryKey: ["rules"] });
  };
}

function EditRow({ cat, onDone }: { cat: Category; onDone: () => void }) {
  const invalidate = useInvalidate();
  const [name, setName] = useState(cat.name);
  const [icon, setIcon] = useState(cat.icon ?? "");
  const save = useMutation({
    mutationFn: () => api.updateCategory(cat.id, { name: name.trim(), icon: icon.trim() || null }),
    onSuccess: () => {
      invalidate();
      onDone();
    },
  });
  return (
    <form
      className="flex flex-wrap items-center gap-2 py-1.5"
      onSubmit={(e) => {
        e.preventDefault();
        if (name.trim()) save.mutate();
      }}
    >
      <input aria-label="Emoji" value={icon} onChange={(e) => setIcon(e.target.value)} className={`${inputClass} w-14 text-center`} />
      <input aria-label="Name" value={name} onChange={(e) => setName(e.target.value)} className={`${inputClass} min-w-0 flex-1`} autoFocus />
      <button type="submit" className={linkClass} disabled={save.isPending || !name.trim()}>
        Save
      </button>
      <button type="button" className="text-sm text-ink-muted hover:underline" onClick={onDone}>
        Cancel
      </button>
      {save.error && <p className="w-full text-sm text-out">{save.error.message}</p>}
    </form>
  );
}

function CatLine({ cat, top }: { cat: Category; top?: boolean }) {
  const invalidate = useInvalidate();
  const [editing, setEditing] = useState(false);
  const hide = useMutation({
    mutationFn: () => api.updateCategory(cat.id, { archived: !cat.archived }),
    onSuccess: invalidate,
  });
  if (editing) return <EditRow cat={cat} onDone={() => setEditing(false)} />;
  return (
    <div className={`flex items-center justify-between gap-3 py-1.5 ${cat.archived ? "opacity-60" : ""}`}>
      <span className={`min-w-0 truncate ${top ? "font-semibold" : ""}`}>
        <span aria-hidden className="mr-1.5">
          {cat.icon ?? "•"}
        </span>
        {cat.name}
        {cat.archived && <span className="ml-2 text-sm font-normal text-ink-muted">Hidden</span>}
      </span>
      <span className="flex shrink-0 gap-3">
        <button type="button" className={linkClass} onClick={() => setEditing(true)}>
          Edit
        </button>
        <button type="button" className={linkClass} onClick={() => hide.mutate()} disabled={hide.isPending}>
          {cat.archived ? "Show" : "Hide"}
        </button>
      </span>
    </div>
  );
}

function AddCategory({ parent }: { parent: Category | null }) {
  const invalidate = useInvalidate();
  const [open, setOpen] = useState(false);
  const [name, setName] = useState("");
  const [icon, setIcon] = useState("");
  const add = useMutation({
    mutationFn: () => api.createCategory({ name: name.trim(), parent_id: parent?.id ?? null, icon: icon.trim() || null }),
    onSuccess: () => {
      invalidate();
      setName("");
      setIcon("");
      setOpen(false);
    },
  });
  if (!open) {
    return (
      <button type="button" className={`${linkClass} py-1.5`} onClick={() => setOpen(true)}>
        {parent ? `Add to ${parent.name}` : "Add a top-level category"}
      </button>
    );
  }
  return (
    <form
      className="flex flex-wrap items-center gap-2 py-1.5"
      onSubmit={(e) => {
        e.preventDefault();
        if (name.trim()) add.mutate();
      }}
    >
      <input aria-label="Emoji" placeholder="🙂" value={icon} onChange={(e) => setIcon(e.target.value)} className={`${inputClass} w-14 text-center`} />
      <input
        aria-label="New category name"
        placeholder={parent ? `New in ${parent.name}` : "New category"}
        value={name}
        onChange={(e) => setName(e.target.value)}
        className={`${inputClass} min-w-0 flex-1`}
        autoFocus
      />
      <button type="submit" className={linkClass} disabled={add.isPending || !name.trim()}>
        Add
      </button>
      <button type="button" className="text-sm text-ink-muted hover:underline" onClick={() => setOpen(false)}>
        Cancel
      </button>
      {add.error && <p className="w-full text-sm text-out">{add.error.message}</p>}
    </form>
  );
}

const MATCH_LABEL: Record<Rule["match_field"], string> = {
  payee: "Payee is",
  name_contains: "Name contains",
  vpa_contains: "UPI ID contains",
};

function RuleRow({ rule }: { rule: Rule }) {
  const invalidate = useInvalidate();
  const { byId } = useCategories();
  const [armed, setArmed] = useState(false);
  const del = useMutation({ mutationFn: () => api.deleteRule(rule.id), onSuccess: invalidate });
  const info = rule.category_id != null ? byId.get(rule.category_id) : undefined;
  return (
    <li className="flex items-center justify-between gap-3 py-2">
      <span className="min-w-0 text-sm">
        <span className="block truncate">
          <span className="text-ink-muted">{MATCH_LABEL[rule.match_field]} </span>
          <span className="font-medium">{rule.match_value}</span>
        </span>
        <span className="block truncate text-ink-muted">
          {info ? (
            <>
              <span aria-hidden>{info.icon}</span> {info.path}
            </>
          ) : null}
          {rule.kind && <>{info ? ", " : ""}marked {KIND_LABEL[rule.kind].toLowerCase()}</>}
        </span>
      </span>
      <button
        type="button"
        onClick={() => (armed ? del.mutate() : setArmed(true))}
        onBlur={() => setArmed(false)}
        disabled={del.isPending}
        className={`shrink-0 text-sm font-medium hover:underline ${armed ? "text-out" : "text-stamp"}`}
      >
        {armed ? "Tap again to delete" : "Delete"}
      </button>
    </li>
  );
}

export function ManageCategories({ onBack }: { onBack: () => void }) {
  const { tree, query } = useCategories();
  const rules = useQuery({ queryKey: ["rules"], queryFn: api.rules });
  const [tab, setTab] = useState<"categories" | "rules">("categories");
  const [ruleSearch, setRuleSearch] = useState("");

  const learned = rules.data?.filter((r) => r.source === "learned") ?? [];
  const q = ruleSearch.trim().toUpperCase();
  const seed = (rules.data ?? []).filter((r) => r.source === "seed" && (!q || r.match_value.includes(q)));

  return (
    <div className="space-y-4">
      <header className="flex items-center gap-3">
        <button type="button" onClick={onBack} className="rounded-lg border border-line bg-surface px-3 py-1.5 text-sm font-medium">
          Back
        </button>
        <h1 className="text-2xl font-bold">Categories & rules</h1>
      </header>

      <div className="flex gap-2" role="tablist">
        {(["categories", "rules"] as const).map((t) => (
          <button
            key={t}
            role="tab"
            aria-selected={tab === t}
            onClick={() => setTab(t)}
            className={
              "rounded-full border px-3 py-1 text-sm font-medium " +
              (tab === t ? "border-ink bg-ink text-paper" : "border-line bg-surface text-ink hover:bg-surface-2")
            }
          >
            {t === "categories" ? "Categories" : `Rules${rules.data ? ` (${rules.data.length})` : ""}`}
          </button>
        ))}
      </div>

      {tab === "categories" && (
        <section className="space-y-3">
          <p className="text-sm text-ink-muted">
            Hidden categories leave the picker. Transactions already tagged with them keep their tag.
          </p>
          {query.isPending && <p className="text-sm text-ink-muted">Loading…</p>}
          {tree.map((p) => (
            <div key={p.id} className="rounded-xl border border-line bg-surface px-3 py-1.5">
              <CatLine cat={p} top />
              <div className="ml-6 border-l-2 border-line pl-3">
                {p.children.map((c) => (
                  <CatLine key={c.id} cat={c} />
                ))}
                <AddCategory parent={p} />
              </div>
            </div>
          ))}
          <AddCategory parent={null} />
        </section>
      )}

      {tab === "rules" && (
        <section className="space-y-4">
          <p className="text-sm text-ink-muted">
            Rules tag new payments. When you tag a payment by hand, Flow saves a rule for that payee. The longest
            matching name wins.
          </p>
          {rules.error && <p className="text-sm text-out">Could not load rules: {rules.error.message}</p>}
          <div className="rounded-xl border border-line bg-surface px-3 py-2">
            <h2 className="font-semibold">Learned from your tags</h2>
            {learned.length ? (
              <ul className="divide-y divide-line">{learned.map((r) => <RuleRow key={r.id} rule={r} />)}</ul>
            ) : (
              <p className="py-2 text-sm text-ink-muted">None yet. Tag a payment by hand and its payee shows up here.</p>
            )}
          </div>
          <div className="rounded-xl border border-line bg-surface px-3 py-2">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <h2 className="font-semibold">Built-in</h2>
              <input
                type="search"
                value={ruleSearch}
                onChange={(e) => setRuleSearch(e.target.value)}
                placeholder="Search names"
                aria-label="Search built-in rules"
                className={`${inputClass} w-40 py-1 text-sm`}
              />
            </div>
            <ul className="divide-y divide-line">{seed.map((r) => <RuleRow key={r.id} rule={r} />)}</ul>
          </div>
        </section>
      )}
    </div>
  );
}
