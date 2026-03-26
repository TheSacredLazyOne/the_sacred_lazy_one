# Derive Instructions — mesh_node

> Read before deriving a new node from this one.
> The model uses this document to scaffold node-specific setup.
> Derived nodes extend this document in their own `derive_instructions.md`.

---

## What the model should do when deriving a new node

After `tools/derive_node.py` runs and stages the initial files, the model
reads this document and the resulting `[node]/node.json` stub, then:

1. **Asks the custodian** what the node is for — one sentence, no hedging.
   This becomes `node.json` `description`.

2. **Identifies required fields** — any field left empty or null in
   `node.json` that will cause a handler to raise. Lists them explicitly
   and asks the custodian to supply values before the first commit.

3. **Writes the node README** — `[node]/README.md` should name what the
   node does, its lineage, and any configuration required before use.
   Not a stub. A lean, honest description.

4. **Checks the Inheritance section** in `README.md` — confirms the
   self-link is present. If not, adds it.

5. **Proposes the first commit message** — following the corpus convention:
   what this node is, what it contains, why those decisions were made.

## What the model should NOT do

- Do not fill in `substack.handle` or any account-specific field without
  explicit custodian input. These are sovereign decisions.
- Do not invent descriptions. Ask if uncertain.
- Do not commit on the custodian's behalf.

## Fields that require custodian input before first use

- `node.json` → `custodians` — add GitHub username
- `node.json` → `description` — replace stub with honest description
- `node.json` → `repository` — confirm URL is correct

## Extending these instructions in a derived node

Create `[node]/derive_instructions.md` with any node-specific setup
requirements. The model reads the full chain — parent instructions
first, then child — so derived nodes only need to document what changes.

*Nothing here is final.*
