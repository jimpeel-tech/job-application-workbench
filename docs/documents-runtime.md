# Documents Runtime Objects

Document Workbench evaluates user-authored Jinja against a deliberately small runtime boundary. This page is the reference for the objects and helpers intended for Templates, Sections, Functions, and Document output filename expressions.

For the authoring model itself, see [Document Workbench](document-workbench.md).

## Runtime roots

JAW exposes five supported runtime roots:

| Root | Shape | Purpose |
| --- | --- | --- |
| `user` | mapping | Active user's profile fields. |
| `job_ref` | mapping | Document-facing fields from the active Generation Context job. |
| `work_exp` | list of mappings | Enabled work-experience records. |
| `cap` | mapping | Document-visible capabilities and enabled Capability Sets. |
| `system` | mapping | Render-time/default values supplied by JAW. |

A simple Template can use them directly:

```jinja
{{ user.full_name }}
{{ job_ref.title }} at {{ job_ref.company }}
{{ system.current_date }}
```

JAW uses strict Jinja evaluation. A missing variable or invalid expression fails visibly instead of silently producing an empty value.

### Template API compatibility

JAW `0.1.1` supports official Template API 1 and Template API 2 packages. Template API 2 is the current runtime contract documented on this page. The contract change relevant to existing template authors is that `work_exp[*].highlights` is now consistently a `list[str]` at the Documents boundary. JAW continues accepting the immutable official `0.1.0` Template API 1 release so existing bundled examples remain selectable during the transition.

## `user`

`user` contains the active user's profile mapping. Common fields include:

```text
user.first_name
user.last_name
user.full_name
user.email
user.phone_number
user.street_address
user.city
user.state
user.zip_code
user.country
user.linkedin
user.github
user.portfolio
user.facebook
user.x
```

`user.full_name` is available to Documents even when it needs to be derived from `first_name` and `last_name` at render time.

Use the runtime debugger when you want to inspect the fields available for the current user:

```jinja
{{ describe(user) }}
```

## `job_ref`

`job_ref` is a stable projection of the job selected by **Generation Context**. It intentionally exposes document-useful fields rather than the entire Job Tracker database record.

Supported fields are:

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

The list-like fields `strong_matches`, `missing_qualifications`, and `concerns` are lists of strings.

### Application questions

`job_ref.questions` is a list of mappings. Each entry has:

```text
question
suggested_answer
submitted_answer
```

Example:

```jinja
{% for item in job_ref.questions %}
Question: {{ item.question }}
{% if item.submitted_answer %}
Answer: {{ item.submitted_answer }}
{% elif item.suggested_answer %}
Suggested: {{ item.suggested_answer }}
{% endif %}
{% endfor %}
```

When **Example Data** is the Generation Context, `job_ref` contains fictional values supplied by JAW. When a tracked job is selected, it is projected from that job.

## `work_exp`

`work_exp` contains only enabled work-experience records for the active user. Common fields include:

```text
item.company
item.title
item.start
item.end
item.highlights
```

The runtime normalizes `item.highlights` to `list[str]`, even though the user's stored Highlights field is editable as text. Each non-empty source line becomes one list item; surrounding whitespace and an optional leading punctuation/symbol bullet marker are removed.

Example:

```jinja
{% for item in work_exp %}
{{ item.title }} — {{ item.company }}
{% for highlight in item.highlights %}
- {{ highlight }}
{% endfor %}
{% endfor %}
```

The same structured `work_exp` representation is available to Functions and to AI generation blocks when the instructions reference it.

## `cap`

`cap` has two primary members:

```text
cap.all
cap.sets
```

### `cap.all`

`cap.all` is the list of document-visible capability records. Each record can contain:

```text
name
type
aliases
rating     # present when a rating exists
```

For example:

```jinja
{% for item in cap.all %}
{{ item.name }}{% if item.rating is defined %} ({{ item.rating }}/5){% endif %}
{% endfor %}
```

### `cap.sets`

User-managed Capability Sets that have **Documents** enabled appear under `cap.sets`.

Set names are normalized to lower-snake Jinja keys. For example, a set named `Software Engineering` is normally available as:

```text
cap.sets.software_engineering
```

If normalized set names collide, JAW adds a numeric suffix such as `_2` to keep the runtime keys unique. The **JAW Objects** palette and `describe(cap)` are the authoritative ways to inspect the current keys.

A set value is a list of capability mappings, not an object with a single `.name` property. To render just the names:

```jinja
{% for item in cap.sets.software_engineering %}
{{ item.name }}
{% endfor %}
```

Or as comma-separated text:

```jinja
{{ csv(cap.sets.software_engineering | map(attribute='name') | list) }}
```

Do not use:

```jinja
{{ csv(cap.sets.software_engineering.name) }}
```

because `software_engineering` is a list of capability records.

## `system`

`system` holds render-time/default values supplied by JAW. Current job-backed generation includes:

```text
system.current_date
system.current_year
system.greeting
system.signoff
```

`current_date` and `current_year` are refreshed at render time. Example Data supplies corresponding fictional/default values for authoring.

Example:

```jinja
{{ system.current_date }}

{{ system.greeting }}
```

## Helpers

Documents also expose a small set of helpers.

### `csv(items)`

Join a sequence as comma-separated text:

```jinja
{{ csv(['Python', 'PostgreSQL', 'AWS']) }}
```

When the sequence contains mappings, select the desired field first:

```jinja
{{ csv(cap.all | map(attribute='name') | list) }}
```

### `describe([value])`

Describe the supported runtime or the shape of one runtime value:

```jinja
{{ describe() }}
{{ describe(job_ref) }}
{{ describe(work_exp) }}
{{ describe(cap) }}
```

`describe()` is useful while authoring because it reports runtime roots, helpers, record counts, and known field shapes without exposing Python implementation details.

### `dump(value)`

Pretty-print a runtime value as JSON-friendly text:

```jinja
{{ dump(job_ref) }}
```

Use this for debugging a Template or Section, then remove it from the finished document.

### `latex_raw(value)`

Insert a value as trusted LaTeX without normal text escaping:

```jinja
{{ latex_raw(my_trusted_latex) }}
```

Normal user/job text should **not** be wrapped in `latex_raw`. JAW automatically escapes text at the final Template boundary so characters such as `&`, `%`, and `_` do not accidentally become TeX syntax.

## Generation Context

Generation Context determines the values behind the runtime roots, especially `job_ref`.

Available modes are:

- **Automatic — Latest tracked job** — use the newest tracked job.
- **Example Data** — use JAW's bundled fictional context.
- **Selected Job** — pin generation to a specific tracked job.

Change the context from the Documents status bar or with:

```text
Ctrl+P -> Documents: Set Generation Context…
```

Example Data is useful when building a Template before you have tracked jobs or when you want predictable fictional values during authoring.

## AI generation blocks and evidence

Sections and Functions can use JAW generation blocks. The instructions can reference the same runtime roots, for example:

```jinja
<summary>
Write a concise professional summary for {{ job_ref.title }} using only
{{ work_exp }} and {{ cap }} as candidate evidence.
</>

{{ summary }}
```

JAW sends only the structured runtime roots referenced by the generation instructions. AI generation is optional; ordinary Jinja expressions and Sections/Functions do not require Ollama or OpenAI.

## Runtime debugging checklist

When an expression does not behave as expected:

1. Use `{{ describe() }}` to confirm the supported roots.
2. Use `{{ describe(the_value) }}` to check its shape.
3. Use `{{ dump(the_value) }}` when you need the actual current data.
4. Remember that Capability Sets are lists of records.
5. Remember that `work_exp[*].highlights` is a list of strings at the Documents boundary.
6. Verify the current Generation Context before assuming `job_ref` is the job you expected.

See [Document Workbench](document-workbench.md) for resource relationships, Sections, Functions, generation blocks, routing, preview, and PDF generation.
