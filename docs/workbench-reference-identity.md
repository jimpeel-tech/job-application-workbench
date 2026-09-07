# Workbench Reference Identity

This note defines the identity rules for JAW Workbench resources and source references.
It is intentionally narrower than the general Workbench guide: these are invariants that
parsing, editing, persistence, navigation, staging, and rendering must preserve.

## Three separate concepts

```text
visible symbol        reference JID        resource JID
-------------         -------------        ------------
body                  ref_a                sec_1
body                  ref_b                sec_2
```

- **Symbol** is source text. It is case-sensitive and is never identity.
- **Reference JID** (`ref_*`) identifies one durable parent -> child relationship.
- **Resource JID** (`doc_*`, `tpl_*`, `sec_*`, `fn_*`) identifies the resource itself.

The editor may render a bound token as:

```html
<span
  data-wb-syntax-symbol="body"
  data-wb-reference-jid="ref_a"
  data-wb-resource-jid="sec_1"
>body</span>
```

The DOM is not persistence. Those attributes are reconstructed from the Workbench graph.

## Duplicate symbols are valid

Two identical visible references may target different private resources:

```jinja
{{ body }}
{{ body }}
```

```text
occurrence 0 -> ref_a -> sec_1
occurrence 1 -> ref_b -> sec_2
```

Case variants are also independent:

```text
section -> ref_a -> sec_1
Section -> ref_b -> sec_2
SECTION -> ref_c -> sec_3
```

No case folding is permitted when resolving Workbench references.

## Reusing one resource JID is Global-only

A private Section or Function has one durable reference at a time. Independently created
duplicate occurrences therefore receive different private resource JIDs.

A Global resource may intentionally be referenced more than once:

```text
{{ shared }} -> ref_a -> sec_global
{{ shared }} -> ref_b -> sec_global
```

This is the supported way for two occurrences to mean the same resource. Each relationship
still receives its own reference JID so navigation, source position, removal, and diagnostics
can target an exact occurrence.

A staged private resource can be reused because staging removes its inbound reference first.
After reuse it is private/active again and cannot acquire another reference unless it is made
Global.

## Reference order

`sort_order` is occurrence order within the parent source. It is not identity.

Editing source may move a reference while its `ref_*` JID stays unchanged. Browser checkpoint
hints carry the existing reference JID and its shifted source span so reconciliation can retain
identity even when identical symbols make text-only matching ambiguous.

For example, inserting a new duplicate before two existing duplicates should produce:

```text
before
  occurrence 0 -> ref_a -> sec_1
  occurrence 1 -> ref_b -> sec_2

after inserting at the front
  occurrence 0 -> ref_c -> sec_3   # new
  occurrence 1 -> ref_a -> sec_1   # preserved
  occurrence 2 -> ref_b -> sec_2   # preserved
```

The backend may use source comparison as a fallback, but exact reference-JID/span hints are
authoritative when supplied by the editor.

## Explicit structural transitions

Free-form typing updates the working source immediately. Existing bindings are not silently
reinterpreted when an edit changes their structure.

- **Update** keeps the selected reference JID and resource JID, changing the visible binding.
- **Create** creates a new private resource JID and a new reference JID for the edited occurrence.
- **Stage** removes the reference and keeps the unreferenced private resource for reuse.
- **Delete** removes the reference and deletes the unreferenced private resource tree.
- Removing one reference to a Global resource never deletes the Global resource.

A transition targets `ref_*` whenever ambiguity is possible. Symbol lookup is only a fallback
for relationships that are provably unique.

## Section and Function labels

Sections and Functions do not have a second user-facing Name. Their visible label is the
symbol/reference text for the current context; their durable identity is the resource JID.

Templates and Documents remain named resources.

## Rendering

User source is never rewritten on disk to expose JIDs. Compilation happens in memory before
Jinja evaluation.

Conceptually:

```jinja
# user source
{{ body }}
{{ body }}
```

becomes:

```jinja
# internal compiled source
{{ __jaw_ref_a }}
{{ __jaw_ref_b }}
```

Each internal variable is populated from the resource JID bound by that reference. The same
process happens one level down when a Section references Functions.

This keeps normal JAW objects such as `user`, `job_ref`, `work_exp`, `cap`, and `system` in
ordinary Jinja scope while Workbench resource addressing remains JID-based.

## Navigation

Navigation should use the bound reference JID/resource JID already attached to the exact source
occurrence. It must not re-resolve a clicked duplicate by searching for the first matching
symbol.

The same rule applies to context menus, rename actions, Inspector/Relationships context, and
source diagnostics whenever an exact occurrence is available.

## Template identity

A newly created Document receives its own private Template immediately. The starter is default
source text, not a shared system resource. Editing a new Document therefore does not replace or
rename its Template JID.

Template visibility changes are explicit:

- Private -> Global keeps the Template JID.
- Global used by one Document -> Private keeps the Template JID.
- Global used by multiple Documents -> Make Private detaches a new private Template for the
  selected Document while the original Global Template remains for the other Documents.

## Non-goals

The identity model does not require JIDs to appear in user-authored source. It also does not
make source positions permanent identifiers. Positions are transient coordinates used to keep
a durable reference JID attached to the correct occurrence during editing.
