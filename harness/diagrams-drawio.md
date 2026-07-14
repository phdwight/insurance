# Diagrams (.drawio) — author, then render and verify

## Principle

A diagram is documentation and follows the same rule as docs: it must tell the
same true story as the code, and it must be **readable**. Hand-authored diagram
XML is not trustworthy until you've looked at the rendered image.

## The render-and-verify loop

After editing a `.drawio`, export it to PNG and actually look at it — then
iterate. Don't ship XML you haven't seen rendered.

```bash
# drawio-desktop CLI (brew install drawio, or the app's bundled binary)
drawio -x -f png --no-sandbox --scale 1.2 -o /tmp/out.png path/to/diagram.drawio
```

Open the PNG, check it against the layout rules below, fix, re-render. Two or
three passes is normal. Common defects only visible in the render: a label
sitting on top of a box, an edge routed straight through a node, and edges
bunching into an unreadable tangle.

**After moving a node, re-check every edge — not just the ones you edited.** A
node relocated into an existing edge's path is the easy miss: an edge that exits
a box at mid-height travels at that height and will pass straight through any
node you later place in its row. Scan the whole picture each pass, not only the
part you touched. (Semantics count too: don't dash an always-on edge if the
legend says dashed means optional.)

## Layout rules (what "readable" means)

- **No edge crosses through a box.** Route skip-edges around nodes — a lane above
  the top row, a lane below the bottom row, or a clear side corridor.
- **No label sits on a box.** Put edge labels on clear straight segments in empty
  space; stagger parallel edges so their labels don't collide.
- **Size the gap to the label.** A short edge between two adjacent boxes whose
  label is wider than the gap will overflow onto the boxes — space the nodes so
  each edge's label has room, and give the whole layout breathing room rather
  than packing it tight.
- **Crossings in open space are fine**; crossings over nodes or labels are not.
  A shared datastore/3rd-party fan-in will always create some open crossings —
  minimize, don't obsess.
- **Group related nodes** in dashed frames (e.g. "internal services",
  "third-party APIs") drawn behind the nodes.
- **Encode meaning consistently** — a stable color per role (client / service /
  data / third-party), solid = always-on, dashed = optional/conditional. Explain
  it in a one-line legend.
- **Prune for clarity.** Drop a low-value node if it clutters the picture, and
  note the omission in the legend rather than cramming everything in.

## Keep it in sync

Update the diagram in the **same commit** as the code or flow it depicts (see
`docs-in-sync.md`). A diagram that lags the code is worse than no diagram.

**On this project:** diagrams live in `docs/*.drawio` — `architecture.drawio`
(high-level components), `agent-graph.drawio` (the LangGraph agent),
`ingestion-pipeline.drawio` (the ingestion flow). Each is kept current with the
implementation.
