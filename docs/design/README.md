# Handoff: Star Pass — shift creation web UI

## Overview

A browser UI over the `rcrderby/star-pass` CLI. It reviews the CSV that a Google
Calendar collection produces, before those shifts are created in Amplify. One
event per row with its officiating shifts nested beneath, an explanation of
everything that was *not* collected, a preview that checks Amplify first, and a
send that can be walked away from and retried.

The work this hands off is **not only front-end**. The architecture decision is
that the API is the contract and this UI is one client of it; the back-end work
comes first. Read in this order:

1. `claude-code-kickoff.md` — the prompt to start with, covering steps 1–3.
2. `api-and-security-plan.md` — the full plan and security model.
3. `decisions.md` — D1–D17, each with why, what was rejected, and what would make
   us revisit it.
4. `openapi-v1-sketch.yaml` — the v1 surface, written from these screens. A
   checking artifact: FastAPI generates the real spec, and this is deleted then.

## About the design files

`Create Shifts v2 (standalone).html` is a **design reference**, not production
code. It is a self-contained prototype — open it in any browser, no server or
build — that shows intended look and behaviour with mock data and simulated
timing. Do not port it.

The task is to recreate these screens in the target environment using its own
patterns and libraries. There is no front-end codebase yet, so choose the
framework; the prototype is React-flavoured only because of the tool that made
it, and that is not a recommendation. What *is* binding is the visual system
(Nocturne, tokens below), the copy, and the behaviours in this document.

`source/` holds the authoring files behind the prototype. They need the tooling
they were written in and are included for reference only.

## Fidelity

**High-fidelity.** Colours, type, spacing, layout, motion and copy are final.
Recreate them exactly. Every string in the prototype is deliberate — it went
through several rounds specifically to make the counts agree and to remove
jargon. Treat copy as spec, not placeholder.

## Design tokens

From the Nocturne design system. Dark is the default; both themes ship.

**Night (default)**
| Token | Value |
| --- | --- |
| `--color-bg` | `#161826` |
| `--color-surface` | Nocturne surface (one step above bg) |
| `--color-text` | `#e9e9ed` |
| `--color-accent` | `#9184d9` |
| `--color-section` | deep indigo, used only for the nav and header gradient |
| `--color-accent-300` | accent text on dark fills |
| `--color-accent-800` | subtle left borders on surfaces |
| `--color-accent-900` / `--color-accent-200` | role chip fill / role chip text |
| `--color-neutral-600` | unchecked checkbox border |
| `--color-alert` | `#e0848c` |
| `--color-alert-fill` | `#4d2e35` |
| `--color-alert-text` | `#ffe6e8` |

**Day** (`[data-theme="day"]` overrides): bg `#f3f5fe`, surface `#fbfbfe`, text
`#292b31`, accent `#5d5294`, section `#e2e1f6`, accent-300 `#4d4380`, accent-600
`#5d5294`, alert `#a3384a`, alert-fill `#f7dfe2`, alert-text `#6e2130`, divider
`color-mix(in srgb, #292b31 14%, transparent)`, neutral-600 `#b3b7cc`, accent-200
`#3a3268`, accent-800 `#cdc9ea`, accent-900 `#e9e6f9`. Shadows become hairline
rings: `0 0 0 1px #cfd3e5` / `0 0 0 1px #e4e7f5, 0 6px 18px rgba(41,43,49,.10)` /
`0 0 0 1px #cfd3e5, 0 16px 40px rgba(41,43,49,.16)`.

Theme is `auto | day | night`; auto follows `prefers-color-scheme`. Switching
crossfades for 300ms (`data-theming="1"` applies a transition to everything, then
clears).

**Type.** Inter throughout (`--font-heading` / `--font-body`), weights 400–600,
never heavier. Interface sizes: 15px run label, 14px row title, 13px body and
inputs, 12px meta, 11–11.5px notes, 10–10.5px micro. Column headers 11px
uppercase, `letter-spacing:.08em`. Numbers, times, ids, paths and env vars are
monospace with `font-variant-numeric: tabular-nums`.

**Radius** 8px (`--radius-md`); small controls 3–7px. **Spacing** is Nocturne's
0.7× density scale — the screen is dense on purpose. **Rules** fade at both ends:
`linear-gradient(to right, transparent, var(--color-divider) 48px, var(--color-divider) calc(100% - 48px), transparent)`.

**Focus** is never the browser default: `2px solid var(--color-accent)` with
`outline-offset: 2px` on every interactive element.

## Screens

### 1. Review — "Shifts to create" (default)

The main screen. Header, then banners, then a toolbar, then the table.

- **Header** sits on a `--color-section` gradient fading to transparent at 78%.
  Left: run picker (a button opening a 340px popover of runs, each with label,
  collected-at, event count and a sent/not-sent pill), the send-status pill when
  a send has happened, and the two-tab segmented control (Shifts to create / Not
  collected + count). Under it: run meta line, and a revision picker
  ("Revision 2 of 2") opening a 330px popover with a revert action per revision
  and "Save a revision now". Right: "Collect again" (secondary) and "Preview
  shifts" (primary).
- **Banners**, stacked, each 11px 14px padding, `--radius-md`, 3px left border:
  sent (accent), already-in-Amplify (accent-600), blockers (alert, with a
  "Show only these" filter toggle), fuzzy matches (accent-600, same toggle).
- **Toolbar**: select-all checkbox, 290px search field, "Showing N of M" when
  filtered, a changes tag, and a "Change log" toggle that opens a 340px card at
  the right.
- **Selection toolbar** replaces the toolbar when rows are selected: count, "Set
  opportunity for all" select, 15 min earlier / later, "Usual slots", "Remove",
  "Clear selection".
- **Table** — `role="table"`, `aria-colcount="8"`, a `rowgroup` per day.
  Columns: `24px minmax(300px,700px) 240px 128px 128px 108px 32px 0.25fr`, gap
  14px. Header row is 8 `columnheader`s (the three empty ones carry aria-labels).
  A day header is its own row with one cell spanning 8; clicking it collapses the
  group by animating `grid-template-rows: 1fr → 0fr` over 260ms.
  Each event is two rows: the main row of 8 cells, then a details row of one cell
  spanning 8 holding the role sub-rows (`440px 250px 130px 110px`, gap 14px).
  Row cards: `--color-surface`, `--shadow-sm`, 3px left border — accent-800
  normally, accent when selected, alert when the event has no opportunity.
  Cells: checkbox (16px, `role="checkbox"` + `aria-checked`); title block (title,
  "RCR Calendar times", match note, duplicate note); opportunity select;
  shift start and shift end (each an input plus an offset note, focusing opens a
  132px time popover in 15-minute steps across the full day, keyboard ↑↓ nudges
  by 15 and Enter closes); length with a cap note; remove; undo-changes.
  Role sub-rows: an elbow icon, the Amplify title as a chip, an external link to
  the opportunity, the shift time, a slots input, and an "edited, undo" affordance.
- When the table is wider than the window: a 44px fade at the right edge and a
  one-line hint above it.

### 2. Not collected

Everything in the window that will not become a shift, grouped by reason with an
explanation per group: outside the calendar search, excluded by title, all day,
untitled. Only the first group's rows are addable ("Add to run"); every row can be
noted for the model. A final section, "Noted for the model", lists what has been
noted with its source and a way to remove the note.

### 3. Preview

Two columns. Left: heading, a "Nothing sent yet" tag, a summary line, then a
table of opportunity / new shifts / slots / dates — grouped by **Amplify
opportunity**, never by category, because several categories share one need id.
Rows carry a note naming shifts already in Amplify that will be skipped. Below:
the send button (labelled with the count), "Back to review", the duplicate-check
spinner or its failure state, a blocked-reason line, and the no-undo warning.
Right: a "Checks" card (duplicate check, blockers, invalid times, repeated rows,
capped lengths, change count) and the change log.

### 4. Confirm dialog

Opens over Preview. 540px card, `role="dialog"`, `aria-modal="true"`. Restates the
count in the title, the run and window, the summary line, a per-opportunity
breakdown, the no-undo warning, then "Create N shifts" and "Cancel". Focus moves
in on open, Tab cycles inside, Escape closes, focus returns to the trigger.

### 5. Collecting

Run id and start time in a strip at the top, then four steps (read, filter,
match, write) each showing pending / running / done / failed with a detail line.
While running: "Leave this running" and "Cancel", with a line explaining that
leaving does not stop it and the run appears under Runs while it works. On
failure: a sanitized message, "Try again", "Back to the run", and a copyable
reference id.

### 6. Sending

Heading and status pill, a progress bar with "N of M opportunities", then a row
per opportunity (waiting / sending / N created / failed) with a skip note and, on
failure, a sanitized error and copyable reference. Below: "Retry the N that
failed" and "Back to the run" — never disabled, because walking away is allowed.

### 7. Collect drawer

452px, right side, over a scrim, slides in over 220ms
(`cubic-bezier(.22,.7,.3,1)`). Calendar segmented control, window presets (this
month / next month / custom), first and last day date inputs, a timezone note, a
summary panel showing the resolved window and the environment line, notes on what
the search does and does not collect, a replace-warning when the run has edits,
then "Collect events" and "Cancel". Same focus-trap behaviour as the dialog.

### 8. Settings

Read-only. Credentials (label, masked value ending in four characters, status,
Test; mounted path beneath; a note that a test makes one real call and is allowed
once a minute) — **no way to write a credential**. Then Configuration as a
name / value / source table, then "Where state lives" with retention stated.

### 9. Empty state

When there are no runs: what a run is, the three steps, and one button into the
drawer.

## Interactions and behaviour

- **Motion** has three levels (off / subtle / smooth) driving `data-motion`, and
  is disabled entirely under `prefers-reduced-motion`. Keyframes: `omFade` .2s,
  `omFadeUp` .18–.2s (7px rise), `omPop` .14–.18s (5px + .98 scale), `omDrawer`
  .22s, `omSpin` 1s linear. Controls transition background, shadow, border and
  colour over 160ms.
- **Escape** closes, in order: confirm dialog, time picker, popovers, drawer,
  selection.
- **Click outside** closes popovers and time pickers.
- **Scroll position** is remembered per run and view, and reset when the run
  changes.
- Editing **saves as you go**; every change appends to the change log.
- **Duplicate check** runs when a run opens, when Preview opens, again inside the
  send, and after a send finishes. It is per-shift identity, never a count.
- **Send** is gated by the dialog, is idempotent per shift, and a retry covers
  only what failed.
- **Collecting again** replaces the run and warns with the number of changes that
  will be lost.

## State

Server-owned (see the OpenAPI sketch): runs, revisions, events, the change log,
job status and steps, the sent record, duplicate-check results, unmatched-title
notes, config, credential status.

Client-only: theme (`auto|day|night`) and resolved system scheme, current view,
search text, blocker and fuzzy filters, collapsed day groups, selection, which
time picker is open, popover open flags, change-log panel visibility, drawer
draft (calendar, preset, first and last day), and copied-reference feedback.

Nothing about identity, time or duplicate safety is client-derived: run ids are
server-minted, windows are league dates resolved by the service, and duplicate
identity comes from Amplify.

## Assets

None. All iconography is [Phosphor Icons](https://phosphoricons.com) (regular
weight); type is Inter from Google Fonts. No images, no logos, no illustrations.
The prototype's data is mock: real calendar names, opportunity titles and need ids
from the repository, with invented events.

## Files

- `Create Shifts v2 (standalone).html` — the prototype. Open in a browser.
- `screenshots/` — ten captures of the live prototype, in flow order:
  review (night), review (day), Not collected, Preview, the send confirmation,
  sending, partly sent, the collect drawer, collecting, Settings. Captured at
  ~924px wide, so they show the layout at a narrower width than the 1440px the
  design targets — the HTML is the reference for proportions, the screenshots for
  colour, density and copy. The empty state is not among them: it is behind a
  tweak in the authoring tool rather than a reachable route.
- `api-and-security-plan.md`, `decisions.md`, `openapi-v1-sketch.yaml`,
  `claude-code-kickoff.md` — the plan, the decision record, the API surface, and
  the prompt to start from.
- `source/` — authoring files behind the prototype. Reference only.
