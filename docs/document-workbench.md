# Document Workbench

Document Workbench is JAW's source-driven document authoring environment. It combines reusable Jinja/LaTeX resources, job/profile data, optional AI generation, and Tectonic PDF rendering.

The Workbench is designed around normal source files rather than a form-based document builder: edit a Template, split reusable content into Sections and Functions, preview the current working state, then generate a PDF.

## Core model

A Document is the output definition. It points to one Template, and that Template references Sections. Sections may reference Functions.

```text
Document
  -> Template
       -> Section
            -> Function
```

The four resource types have different jobs:

| Resource | Purpose |
| --- | --- |
| Document | Names an output, selects its Template, and defines the PDF filename pattern. |
| Template | Owns the top-level Jinja/LaTeX source for a Document. |
| Section | Reusable document content referenced from a Template. |
| Function | Reusable Jinja/generation logic referenced from a Section. |

Every new Document receives its own normal **Private Template immediately**. The starter LaTeX is only default source text; there is no shared immutable starter Template and no clone-on-first-edit behavior.

A new Document starts approximately like this:

```latex
\documentclass[10pt,letterpaper]{article}
\usepackage[letterpaper,margin=0.75in]{geometry}
\pagestyle{empty}
\begin{document}
{{ section }}
\end{document}
```

JAW creates a private `section` resource for that reference as part of the new Document graph.

## Quick start

1. Open **Documents** in the JAW web interface.
2. Click **+ New Document** and give it a useful name such as `Resume` or `Cover Letter`.
3. Select the Document in **Explorer**.
4. Edit the **Template** source and use Jinja references such as `{{ section }}` for reusable content.
5. Open the referenced Section and add its content.
6. Choose a **Generation Context** from the status bar if you want to test with Example Data or a particular tracked job.
7. Click **Preview** to render without writing a PDF to disk.
8. Click **Generate** to render and write the PDF to the configured output directory.

Tectonic is required for PDF rendering. See [Tectonic setup](tectonic.md).

## Workbench layout

The Workbench uses an IDE-style layout.

### Top bar

- **+ New Document** creates a Document with a new private Template.
- Document tabs let you keep multiple Documents open.
- **Preview** renders the active Document without writing the PDF to disk.
- **Generate** renders the active Document and writes the PDF.

Closing a tab closes the view only; it does not delete the resource.

### Left side

- **Explorer** — Documents and the resources currently attached to them.
- **Global Templates** — reusable Templates available across Documents.
- **Inspector** — editable properties for the current selection.
- **Relationships** — inbound and outbound resource relationships.
- **Metadata** — internal resource metadata useful for inspection/debugging.

### Center editors

The center has independent editor panes for:

- **Template**
- **Sections**
- **Functions**

Opening a reference from source opens its linked resource in the appropriate pane.

### Right side

- **JAW Objects** — runtime data available to document source.
- **Global Sections** — reusable Sections.
- **Global Functions** — reusable Functions.
- **Orphans** — staged private resources that are no longer attached but have been preserved for reuse.

Resources and JAW objects can be inserted into source from these palettes.

### Status bar

The status bar includes:

- **Context** — current Generation Context.
- **Output** — generated PDF destination; defaults to Downloads.
- **Wrap** — editor word-wrap toggle.

Workbench layout, wrapping, and output-directory preferences are browser-local settings.

## Names, symbols, and references

Documents and Templates are named resources. Sections and Functions intentionally do **not** have a separate user-facing Name field; they are identified in context by their reference symbol.

For example:

```jinja
{{ summary }}
{{ experience }}
```

`summary` and `experience` are visible symbols. They are source text, not permanent identity.

This matters because JAW allows duplicate visible symbols. Two occurrences of `{{ body }}` can refer to two different private Sections. Internally JAW tracks each occurrence with a durable reference identity while keeping those IDs out of user-authored source.

You normally do not need to think about the internal IDs. The practical rules are:

- Renaming a symbol does not replace the underlying resource.
- Moving a reference does not replace the underlying resource.
- Duplicate visible symbols are valid.
- Global resources can be referenced from more than one place.
- JAW preserves occurrence identity while editing and rewrites references internally during rendering.

For implementation details, see [Reference identity](workbench-reference-identity.md).

## Editing, recovery, and saving

Workbench distinguishes the **working source** from the **saved source**.

As you type, the browser keeps the live editor value and JAW checkpoints dirty source after a short pause. Those recovery buffers are stored separately from the canonical saved resource, so unsaved work can survive a JAW restart.

Press **Ctrl+S** to make the current editor content the saved canonical source.

If the working content becomes identical to the saved source, JAW clears the unnecessary recovery buffer.

Both **Preview** and **Generate** use the current working editor buffers. You do not have to save first to test a change.

### Additive reconciliation

Normal editing is deliberately conservative. When you add a new unresolved Workbench reference, JAW can create and attach the corresponding private resource. Removing source text, however, does not silently delete existing resource identity or content.

Destructive or identity-changing operations are explicit. This prevents an intermediate edit from accidentally destroying reusable content.

## Reference changes

When a source edit changes the structure around an existing reference, Workbench uses explicit transitions rather than guessing what you intended.

The important behaviors are:

- **Update** — keep the existing resource and its content/children, but update the reference/symbol.
- **Create** — create a new private resource for the new reference.
- **Stage** — remove the old private reference while preserving the resource in **Orphans** for later reuse.
- **Delete** — remove the private resource permanently; private descendants may be deleted with it.
- **Remove Global reference** — unlink the occurrence but preserve the Global resource.

Invalid Jinja or ambiguous structural edits are rejected before the graph is changed.

### Renaming

Use the resource/reference context menu:

- **Rename Symbol…** for a Private Section or Function.
- **Rename Reference…** for an occurrence of a Global Section or Function.

A Global resource keeps its reusable canonical identity while each usage can have its own reference symbol.

### Orphans

**Orphans** are staged private Sections or Functions that are no longer attached to a parent. Their content is preserved.

Drag or insert an orphan back into a valid parent to reuse it. Reusing an orphan activates it again as a private resource.

Switching a Document to a different Template is an explicit structural operation. Private Sections no longer represented by the new Template are staged; Global Sections are simply unlinked.

## Private and Global resources

**Private** means the resource belongs to one current parent context. **Global** means the resource is intentionally reusable.

Sections and Functions can be changed between Private and Global from the Inspector/context menu. Templates use the resource context menu for visibility changes.

### Templates

Template visibility follows these rules:

- Private -> Global keeps the same Template identity.
- A Global Template used by one Document can become Private in place.
- If a Global Template is shared by multiple Documents, **Make Private** for one Document detaches that Document to a new private Template while leaving the shared Global Template in place for the others.

A Global Template shares **Template source**, not the entire child graph. Each Document using the Template normally keeps its own Section references and private Section resources.

```text
                 shared Template
                 {{ body }}
                    |
             +------+------+
             |             |
          Document A    Document B
             |             |
          body A          body B
```

Editing shared Template source reconciles each Document graph using that Template. Rendering always resolves the selected Document's own graph.

See [Shared Global Template graph semantics](workbench-shared-template-graph.md) for the detailed invariants.

## Jinja basics

Template, Section, and Function source uses Jinja syntax.

### Insert a value

```jinja
{{ user.full_name }}
{{ job_ref.company }}
```

### Conditional

```jinja
{% if job_ref.summary %}
{{ job_ref.summary }}
{% endif %}
```

### Loop

```jinja
{% for item in work_exp %}
{{ item.title }} — {{ item.company }}
{% endfor %}
```

### Default value

```jinja
{{ job_ref.title | default('Target Role') }}
```

JAW uses strict Jinja evaluation. Missing variables and invalid syntax fail visibly rather than silently producing misleading output.

## JAW runtime objects

User-authored Documents have five supported runtime roots:

| Root | Contents |
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

`work_exp` is a list of enabled work-experience records. Common fields include `company`, `title`, `start`, `end`, and `highlights`.

At the Documents runtime boundary, `item.highlights` is always a `list[str]`. JAW preserves the user's stored Highlights text unchanged; the runtime projection splits it by line, trims surrounding whitespace, drops empty lines, and removes an optional leading punctuation/symbol list marker. One non-empty source line becomes one highlight.

```jinja
{% for item in work_exp %}
{{ item.title }} at {{ item.company }}
{% for highlight in item.highlights %}
- {{ highlight }}
{% endfor %}
{% endfor %}
```

This same structured list is supplied to Functions and AI generation when `work_exp` is referenced as evidence.

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
{{ describe(work_exp) }}
{{ dump(job_ref) }}
```

- `describe()` shows the supported runtime roots and helpers.
- `describe(value)` describes the shape of a known value. For populated `work_exp`, Highlights is reported as `highlights: list[str]`.
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

JAW also includes Template Repository support for importing/updating reusable Template definitions. Repository Templates become normal Workbench resources once installed; the same Private/Global and reference-graph rules apply inside JAW.

Repository behavior is intentionally separate from the core authoring model. You can use Document Workbench fully without configuring a Template Repository.

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
