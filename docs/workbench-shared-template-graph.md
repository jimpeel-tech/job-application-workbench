# Shared Global Template Graph Semantics

A Global Template is one shared Template resource JID and one shared source buffer, but its Section bindings live in each Document's graph.

```text
                 tpl_shared
                 source: {{ body }}
                         |
             +-----------+-----------+
             |                       |
          doc_A                    doc_B
             |                       |
      ref_A -> sec_A          ref_B -> sec_B
```

This is intentional. Sharing a Template means sharing document structure, not forcing every Document to use the same Section resources.

## Source edits

Editing a shared Template changes the one Template source seen by every Document that uses it. Reconciliation therefore runs against every Document graph before the checkpoint/save response is returned.

A new unbound occurrence normally creates one private Section per Document:

```jinja
{{ body }}
{{ closing }}
```

```text
doc_A: ref_A_body -> sec_A_body
       ref_A_close -> sec_A_close

doc_B: ref_B_body -> sec_B_body
       ref_B_close -> sec_B_close
```

The Template source is shared; the `ref_*` and `sec_*` JIDs are not.

## Duplicate occurrence identity

Reference JIDs remain the identity of individual occurrences. If identical occurrences move because source is inserted before them, the active editor supplies reference-JID/span hints.

For a shared Template those hints describe source occurrence identity, so JAW translates them to the corresponding reference JIDs in every other Document graph **before mutating any graph**.

Example:

```text
before
  doc_A: occurrence 0 -> ref_A1
         occurrence 1 -> ref_A2
  doc_B: occurrence 0 -> ref_B1
         occurrence 1 -> ref_B2

after inserting a duplicate at the front
  doc_A: occurrence 0 -> ref_A3 (new)
         occurrence 1 -> ref_A1
         occurrence 2 -> ref_A2
  doc_B: occurrence 0 -> ref_B3 (new)
         occurrence 1 -> ref_B1
         occurrence 2 -> ref_B2
```

The cross-Document correspondence uses the old occurrence order. `sort_order` is not identity; it is only the source occurrence position at that point in time.

## Explicit transitions

Free-form reconciliation remains additive. Missing existing bindings are not silently removed.

When the user explicitly chooses Update/Create/Stage/Delete for a shared Template occurrence, the same source occurrence is applied to each Document graph that uses the Template. Each graph keeps its own reference/resource JIDs unless a Global Section was deliberately reused.

## Rendering

Generation always resolves the shared Template source against the selected Document's graph:

```text
Generate doc_A -> tpl_shared + doc_A references
Generate doc_B -> tpl_shared + doc_B references
```

The renderer never resolves a shared Template through another Document's reference JIDs.

## Invariants

- Template JID/source may be shared.
- Template recovery buffer is shared because it belongs to the Template JID.
- Section reference JIDs are per Document graph.
- Private Section resource JIDs are per Document graph.
- A Global Section may intentionally be reused across Document graphs.
- Duplicate visible symbols remain independent reference occurrences.
- Reference/span hints are translated across shared Document graphs before any graph is mutated.
- Rendering uses the active/selected Document graph only.
