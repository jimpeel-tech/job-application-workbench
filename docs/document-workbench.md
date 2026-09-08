# Document Workbench

JAW Documents is a graph-backed authoring environment for reusable job-application documents. It combines Jinja, LaTeX, structured JAW runtime objects, optional AI generation, and durable resource/reference identity.

## Resource model

```text
Document
  -> Template
      -> Section references owned by the Document graph
          -> Function references owned by the Section graph
```

A new Document immediately owns a private Template. Sections and Functions are reusable resources linked through references.

Resource IDs and reference IDs are internal JIDs:

- resources: `doc_*`, `tpl_*`, `sec_*`, `fn_*`
- references: `ref_*`

Visible source symbols such as `summary` or `experience` are not identity. Duplicate symbols are valid because each occurrence can bind to a different reference JID.

## Workbench layout

The Documents page behaves like a small IDE:

- **Explorer** — Documents, Templates, Sections, and Functions.
- **Editor** — source editing for the active resource.
- **Inspector** — metadata/settings for the active resource.
- **Status bar** — generation context, output directory, and other document controls.

A resource can be opened by Explorer navigation, symbol navigation, or command palette.

## Source and canonical state

Typing changes the resource's **working source**. JAW checkpoints working source so preview/navigation can react without requiring a canonical save after every keystroke.

**Ctrl+S** performs the canonical save.

Structural reconciliation is additive while editing. If you type a new undeclared symbol into a Template, JAW can create the corresponding Section reference. Merely deleting visible source text does not silently destroy a resource/reference; destructive changes go through explicit transitions.

This gives the editor two distinct ideas:

- **working source** — what you are currently editing;
- **canonical resource graph** — durable Documents/resources/references.

## Reference identity

A source token, reference JID, and resource JID are different things.

```text
{{ summary }}
     │
     └─ visible symbol
           │
           └─ ref_... -> sec_...
```

Two `{{ summary }}` tokens can have the same visible symbol while pointing to different references/resources. Symbol matching is case-sensitive because Jinja identifiers are case-sensitive.

Global resources can be reused multiple times through distinct references. Private Sections/Functions are constrained to one inbound owner reference.

The editor does not expose JIDs in portable source. During rendering JAW binds source occurrences to reference JIDs internally so duplicate symbols remain deterministic.

## Structural transitions

When source implies a graph change, JAW uses explicit transitions rather than treating text as the graph itself.

Typical choices include:

- **Update** — reconcile source with the existing resource/reference.
- **Create** — create a new resource/reference for a new symbol.
- **Stage** — remove a private resource from the current graph without immediately deleting it.
- **Delete** — permanently delete an eligible private resource.
- **Remove Global** — remove only this reference while preserving the Global resource.

The exact choices depend on resource type, ownership, visibility, and inbound references.

## Private and Global resources

**Private** resources belong to one local graph/owner context.

**Global** resources are reusable across Documents.

For Templates:

- A new Document owns a private Template.
- Private -> Global keeps the same Template JID.
- Global -> Private with one user keeps the same JID.
- A shared Global Template converted to Private detaches the active Document onto a new private Template instead of mutating the shared source underneath other Documents.

A shared Global Template shares Template source, but the Sections beneath it are still linked through each Document's own Section graph. This prevents two Documents from accidentally sharing all child references merely because they use the same Template source.

## Jinja and JAW Objects

Documents use Jinja for expressions/control flow and a small explicit set of JAW-owned runtime roots.

The current roots are:

| Root | Purpose |
| --- | --- |
| `user` | Active user profile data. |
| `job_ref` | Document-useful fields from the active Generation Context job. |
| `work_exp` | Enabled work-experience records. |
| `cap` | Capability records and user-managed capability sets enabled for Documents. |
| `system` | Runtime values such as the current date/year and document defaults. |

### `job_ref`

Common fields include:

```text
job_ref.company
job_ref.title
job_ref.raw_description
job_ref.questions
job_ref.strong_matches
job_ref.missing_qualifications
job_ref.concerns
job_ref.score
job_ref.summary
```

### `work_exp`

`work_exp` is a list of enabled work-experience records, so normal Jinja list operations apply:

```jinja
{% for item in work_exp %}
{{ item.title }} at {{ item.company }}
{% endfor %}
```

### `cap`

`cap.all` contains the document-visible capability records.

User-managed Capability Sets that have Documents enabled appear under `cap.sets` using a normalized key, for example:

```jinja
{% for item in cap.sets.platform_sre %}
{{ item.name }}
{% endfor %}
```

A capability record can include fields such as `name`, `type`, `aliases`, and `rating` when a rating exists.

### Debugging the runtime

Workbench exposes small runtime helpers:

```jinja
{{ describe() }}
{{ describe(job_ref) }}
{{ dump(job_ref) }}
```

- `describe()` shows the supported runtime roots and helpers.
- `describe(value)` describes the shape of a known value.
- `dump(value)` prints JSON-friendly runtime data.
- `csv(items)` joins a sequence as comma-separated text.

These are especially useful while building a new Template.

## LaTeX escaping

Normal values inserted through the final Template boundary are automatically escaped for LaTeX.

For example, user/job text containing `&`, `%`, `_`, or other TeX metacharacters should normally be inserted directly:

```jinja
{{ job_ref.summary }}
```

Use `latex_raw(...)` only when the value is trusted LaTeX that you intentionally want Tectonic to interpret:

```jinja
{{ latex_raw(my_trusted_latex) }}
```

Do not use `latex_raw` simply to work around escaping; it deliberately bypasses the safety boundary.

## Section Content Shape

A Section can be configured in the Inspector as:

- **Paragraphs**
- **List**

The rendered Section still behaves like normal text when inserted directly, but it is also iterable.

### Paragraphs

Paragraph shape splits rendered content on blank lines:

```jinja
{% for paragraph in summary %}
\par {{ paragraph }}
{% endfor %}
```

### List

List shape treats each non-empty rendered line as an item and strips a leading `- ` when present:

```jinja
{% for item in accomplishments %}
\item {{ item }}
{% endfor %}
```

This lets one Section provide both a complete rendered string and structured iteration to its parent Template.

## Functions

Functions are reusable Jinja/generation logic owned by or referenced from a Section.

A Function can return normal rendered text:

```jinja
{% if job_ref.company %}
Target company: {{ job_ref.company }}
{% endif %}
```

A Function reference can be used as a value or called:

```jinja
{{ helper }}
{{ helper() }}
```

Functions are evaluated lazily and memoized during one render. Function cycles are rejected.

## AI generation blocks

Sections and Functions can contain JAW generation blocks.

### Text

```jinja
<summary>
Write a concise professional summary for {{ job_ref.title }} using only the supplied candidate and job evidence.
</>

{{ summary }}
```

`<name>...</>` and `<name:text>...</>` create a text value.

### List

```jinja
<bullets:list>
Create three concise resume bullets using {{ work_exp }} and {{ job_ref }} as evidence.
</>

{% for bullet in bullets %}
- {{ bullet }}
{% endfor %}
```

`<name:list>...</>` creates a native list of strings.

Generation blocks:

- emit no text themselves;
- make the generated value available to later Jinja;
- cannot be nested;
- must be closed with `</>`;
- use schema-constrained text/list responses;
- send only the structured runtime roots actually referenced by the generation instructions.

JAW instructs the provider to use only supplied evidence and not invent candidate experience, qualifications, ratings, measurements, or job facts.

### Providers

Document generation currently supports:

- **Ollama** — local generation; default model `qwen3:14b`.
- **OpenAI** — hosted generation; requires `OPENAI_API_KEY`.

Document Functions inherit the active user's analysis provider/model settings.

See [Ollama setup](ollama.md) for local-model installation and configuration.

## Generation Context

Generation Context controls which job data populates `job_ref`.

The available modes are:

- **Automatic — Latest tracked job** — use the newest tracked job.
- **Example Data** — use JAW's bundled fictional example data; useful for authoring and testing.
- **Selected Job** — pin generation to one tracked job.

The current context appears in the Documents status bar. Click it to change the selection, or use **Ctrl+P -> Documents: Set Generation Context…**.

If Automatic is selected but there are no tracked jobs, choose Example Data or add a job before generating job-dependent content.

## Command palette

While Documents is active:

- **Ctrl+P** opens the Documents command palette.
- **Ctrl+Shift+P** opens **Go to Item** directly.

The command palette currently exposes:

- Set Generation Context
- Go to Item
- Document Routing
- Word Wrap
- Output Directory
- Reset Layout

## Preview and Generate

Both operations render the current **working buffers**, including unsaved edits.

### Preview

**Preview**:

- runs the full Jinja/Function/generation pipeline;
- compiles through Tectonic;
- opens the PDF in a reusable browser preview window;
- does not write the PDF to the output directory.

If the browser blocks the preview window, allow popups for the local JAW site.

### Generate

**Generate** performs the same render and also writes the PDF to disk.

The default destination is:

```text
%USERPROFILE%\Downloads
```

Use the **Output** status-bar control or **Ctrl+P -> Output Directory** to choose another location. A custom output directory must be an absolute path.

The Document's **Output** field in the Inspector controls its filename pattern. New Documents default to:

```jinja
{{ user.full_name }} - Document Name.pdf
```

JAW sanitizes invalid filename characters and ensures the final output uses `.pdf`.

If another program has the generated PDF locked, JAW can still update the preview but may be unable to replace the file. Close the PDF in the other application and generate again.

## Job Tracker document routing

Document Routing is separate from editing a single active Document. It lets Job Tracker choose one or more output Documents based on the tracked job title.

Open **Ctrl+P -> Document Routing** to configure:

- ordered routing rules;
- title keywords for each rule;
- one or more output Documents per rule;
- fallback Documents when no rule matches.

Routing is user-defined; JAW does not hard-code management, architecture, or other role categories.

From Job Tracker, document generation uses the selected tracked job as context and can generate every Document assigned by the matching route.

## Template repository

JAW can download reusable example packages from the official `jimpeel-tech/jaw-templates` repository. Cloning a package creates normal private Workbench resources with new local JIDs; the repository never stores your JAW resource/reference IDs.

The initial repository includes:

- **Basic Document** — minimal Template -> Section -> Function example.
- **Document Tour** — guided tour of Workbench composition and Jinja.
- **JAW Object Examples** — deterministic examples for `user`, `job_ref`, `work_exp`, `cap`, `system`, and authoring helpers. It makes no AI calls.
- **Cover Letter** — job-aware cover letter; its body Section uses the active Ollama/OpenAI model, so AI generation must be configured before Preview/Generate.

For the object examples, choose **Generation Context -> Example Data** if you want a fully populated fictional context without adding your own job/profile data first.

Repository behavior is intentionally separate from the core authoring model. You can use Document Workbench fully without downloading the example repository.

## Deleting resources

Deletion is explicit and dependency-aware.

- Deleting a Document can also delete its exclusive private Template and private child resources.
- Global/shared resources are preserved when deleting a Document.
- A Template cannot be deleted while Documents still use it.
- A Section or Function cannot be deleted while it is still referenced.
- Removing a Global reference preserves the Global resource.

Read the delete dialog before confirming; it lists the private resources that will be permanently removed.

## Troubleshooting

### Tectonic was not found

See [Tectonic setup](tectonic.md). JAW checks `JAW_TECTONIC_PATH`, normal `PATH`, and `%USERPROFILE%\.local\bin\tectonic.exe`.

### Ollama generation fails

Confirm Ollama is running and the selected model is installed. See [Ollama setup](ollama.md).

### `OPENAI_API_KEY is not available to JAW`

A Function is configured to use OpenAI but the JAW process does not have `OPENAI_API_KEY` in its environment. Configure the key or select Ollama/local generation instead.

### Jinja syntax error

Correct the indicated Template/Section/Function source. Structural transitions are validated before mutation, so an invalid edit should not partially alter the resource graph.

### Missing runtime variable

Use:

```jinja
{{ describe() }}
```

or inspect **JAW Objects** to verify the supported runtime path. Current roots are `user`, `job_ref`, `work_exp`, `cap`, and `system`.

### Preview works but Generate cannot replace the PDF

The target file is probably open in another application. Close it and retry.

## Architecture references

For contributors or anyone debugging resource identity, these notes document the underlying invariants:

- [Reference identity](workbench-reference-identity.md)
- [Shared Global Template graph semantics](workbench-shared-template-graph.md)

The user-facing rule is simpler: source symbols are readable presentation text; JAW preserves durable resource/reference identity behind the scenes so reuse, duplicates, renames, and shared Templates remain predictable.
