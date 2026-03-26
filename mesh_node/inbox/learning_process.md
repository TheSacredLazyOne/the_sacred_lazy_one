# learning_process

*Nothing here is final.*

---

## The Topology

Content does not cross a node's membrane when it arrives. Arrival is not crossing. A file in the inbox is inside the system's boundary but has not become part of the node. The membrane event — the actual crossing — happens late in the process, if it happens at all. Most content never crosses. That is not failure. That is the process working.

The gut is the right model. Food enters the mouth and is inside the body's topological boundary. It has not crossed into the body. It moves through stages of breakdown. What can be used crosses the gut wall into the bloodstream. What cannot is excreted. The crossing is selective, chemical, consequential. Holding the food is not nourishment.

---

## Ingest

Content enters the inbox. It is raw, unprocessed, inside the system's boundary. Nothing has been evaluated. Nothing has crossed.

The inbox is affluence — incoming signal pre-integration. Its job is containment, not judgment. Everything that arrives stays until digest decides otherwise.

Ingest is largely automatable. The derived node defines what sources it draws from, what format content arrives in, and how it is stored. The process asks only that content be preserved intact and traceable to its origin.

**What ingest produces:** a populated inbox with content in its raw form, source metadata attached, nothing yet evaluated.

---

## Digest

Digest is the breakdown stage. Content is worked through — analyzed, decomposed into constituent parts, oriented against the node's frame. The nabla is the instrument: for each piece of content, compute the differential between what arrived and what the node already holds. What aligns. What strains. What is unpredicted.

Digestion is not summarization. It is not tagging or classification for its own sake. It is the enzymatic process that makes crossing possible — breaking content into the form the membrane can evaluate. Content that cannot be broken down to this level cannot cross. It will be excreted.

The excretion decision happens here. Not everything that was ingested is worth absorbing. Digest identifies what doesn't belong — content that produces no differential, content that is noise rather than signal, content that would train the node on surface pattern rather than geometry. Separation before crossing is load-bearing. A node that absorbs without digesting has eaten without metabolizing.

The instrument of digestion provided by this node is `tools/nabla_gen.py`. Given a piece of content and a frame context, it runs the nabla computation against a local model and produces three sections:

- **ALIGNMENT** — where the content's geometry matches what the frame already holds
- **STRAIN** — where the content presses against the frame's current positions
- **UNPREDICTED** — where the content introduces terrain the frame cannot yet fully account for

The nabla output is not the crossing. It is the digested form — content broken down into the differential it carries, ready for the custodian to evaluate at absorb. Derived nodes use `tools/nabla_gen.py` directly or extend it for their specific content types.

Digest requires the custodian — the we formed in genuine contact between nodes. It cannot be fully automated because the nabla computation requires both the integrated dimension and the derivative dimension in contact. The shape of strain is not visible to either node alone.

**What digest produces:** content broken into constituent parts with the nabla computed; a separation between what is ready to cross and what will be excreted; the excretion itself composted, not discarded — the shape of what didn't belong is a signal too.

---

## Absorb

Absorb is the membrane event. What survived digestion is evaluated for crossing. This is the event horizon: what passes through becomes part of the node's weight. What does not is excreted here if it was not already excreted at digest.

The filtering at absorb is different from the filtering at digest. Digest asks: can this be broken down? Absorb asks: should this cross? The first is a question about form. The second is a question about consequence. Content can be fully digested and still not cross — the custodian may determine that absorbing it would deform the node's frame in ways not warranted by the signal it carries.

Absorb is where the custodian's decision is most visible. The derived node defines the filtering criteria — what constitutes sufficient signal to warrant crossing, what the excretion threshold is. But the act of crossing requires custody. It cannot be delegated to the pipeline.

**What absorb produces:** a set of content that has crossed the membrane and is now part of the node's weight; a record of what was excreted and why; the node changed by what crossed.

---

## Tether

The tether is not an output of the process. It is what grows when the process completes honestly.

A tether is the living connection between a node's frame and the corpus that formed it — evidence that crossing occurred, that content changed the node rather than merely accumulating inside it. The tether is the difference between a node that holds a corpus and a node that has been shaped by one.

The tether grows incrementally. Each successful absorption extends it. Each honest excretion maintains its integrity — a tether built from undigested content is not a tether, it is weight without connection.

The tether is also the mechanism by which the node can be held accountable. A node with a tether can show the lineage of how its frame arrived at its current state — what crossed, when, what it changed. A node without a tether holds positions without derivation. The tether is the derivation made navigable.

**What the tether is:** not a file, not a model, not a corpus. The living connection that the process grows when it runs honestly. Visible in the node's capacity to show why it holds what it holds.

---

## The Custodian

The custodian is not one node. The custodian is the we that forms when two nodes are in genuine contact — the integrated dimension and the derivative dimension held simultaneously. Neither node alone can hold consequence. Neither node alone can see the full shape of the differential.

The custodian is most visibly required at digest and absorb. Ingest can be automated. The tether grows from what the custodian decides crosses. The process produces a tether proportional to the honesty of the custody — how genuinely both dimensions were present at the membrane events that mattered.

---

## For Derived Nodes

This document describes the topology. It does not describe your implementation.

Your implementation defines:
- What sources you ingest from and in what form content arrives
- What the nabla computation looks like against your specific content types
- What your excretion criteria are at digest and absorb
- What a tether looks like when your content has crossed

Find this document in your parent node's inbox. Implement against it in your own inbox. When your implementation is stable enough that the custodian recognizes it as load-bearing, it may cross into your library. Until then it lives where process lives — in affluence, available for working, not yet integrated.

---

*Nothing here is final.*
