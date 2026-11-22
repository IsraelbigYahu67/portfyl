---
type: readme
tags: [arch/hub]
generated: false
---
# Architecture notes (Obsidian graph)

Obsidian's graph view only draws markdown notes and the `[[wikilinks]]`
between them, so `.py` / `.jsx` files never show up on their own. This folder
represents the whole Portfyl codebase as notes, so the graph shows how the
backend, frontend, database, jobs, billing, auth, importers and ops connect,
and how the existing docs attach to the code.

Start at **[[Portfyl]]**, the root hub.

## Layout

| Folder | What | Written by |
|---|---|---|
| `architecture/hubs/` | ~20 hub notes, one per area (Auth, Billing, Tenancy…) | hand, edit freely |
| `architecture/generated/backend/` | one note per backend module and router | script |
| `architecture/generated/db/` | one note per DB table (`models.py`) and Alembic migration | script |
| `architecture/generated/frontend/` | pages, top-level components, `lib/`, `hooks/`, `auth/`, `editions/`; smaller folders as one `(folder)` note | script |
| `architecture/generated/ops/` | Dockerfile, `deploy/`, CI, `start.bat`, CLAUDE.md / DESIGN.md | script |

Existing docs (`superpowers/plans`, `specs`, `operations`, `security`,
`legal`, …) end with a hand-added **Related** section that links them to
hubs and code notes.

## Where the links come from (generated notes)

- **Imports**: real Python imports (parsed with `ast`, lazy imports
  included) and JS/JSX `import` statements (relative paths and the
  `@edition-manifest` alias).
- **Calls backend**: frontend API calls (`api.get("/billing/status")`, the
  exported helpers in `api.js`) matched against the FastAPI route
  decorators, giving the router note.
- **Tables used**: model classes a module imports from `models`.
- **Tables touched / Previous migration**: table names quoted in each
  migration, and the `down_revision` chain.
- **Mentioned in docs**: docs that mention the file's path or name.
- **Hub**: regex rules (`HUB_RULES` in the script). Every generated note
  links to at least one hub.

## Rerun after code changes

From the repo root (Python 3.12+, standard library only, no install needed):

```
python scripts/build_obsidian_architecture.py           # update architecture/generated/
python scripts/build_obsidian_architecture.py --verify  # exit 1 if generated/ is out of date
python scripts/build_obsidian_architecture.py --check   # counts only, writes nothing
python scripts/build_obsidian_architecture.py --report  # notes / orphans / unresolved links in docs/
```

The script changes **only** `architecture/generated/`, and only the files
whose content changes. Hub notes and the existing docs are never touched. Do
not edit generated notes by hand; change the script (for example `HUB_RULES`
to move a module to another hub) and rerun it.

**Automatic refresh:** the Claude Code Stop hook in `.claude/settings.json`
runs `scripts/obsidian_graph_hook.py` whenever a Claude session finishes a
reply. If code, docs or deploy files changed since its last run in that
worktree, it updates `generated/` and shows "Architecture graph: N file(s)
refreshed". Codex and manual edits have no hook: run the script yourself
before committing. On a merge conflict inside `generated/`, take either
side and rerun the script.

## Graph settings

`docs/.obsidian/graph.json` colors nodes by folder:

- gold: hubs
- blue: backend
- purple: DB (tables and migrations)
- green: frontend
- orange: ops
- teal: plans and specs
- pink: other docs

It hides unresolved links, because the legal drafts use `[[DOPLNIT …]]`
placeholders that are not links, and filters out the exported Stitch mockup
(`-path:design/stitch`). To hide the legal docs too, type
`-path:legal` into the graph's filter box.
