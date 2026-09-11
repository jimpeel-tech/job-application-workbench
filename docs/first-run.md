# First Run

JAW is local-first and is designed to be useful immediately after installation without requiring an AI provider. The first-run data is intentionally populated so you can explore the interface before entering your own information.

## What appears on first run

A fresh JAW data store starts with a fictional demo user named **Ol Sarge**. The demo profile includes sample contact data, work experience, capabilities, keybinds, reusable answers, and example tracked jobs.

The demo data exists only to make JAW's workflows visible on first launch. It is not intended to be edited into your permanent profile.

For normal use:

1. Open **Manage User** in the upper-right corner.
2. Create a user for yourself.
3. Switch to your new user before entering real profile or application data.

A newly created user starts with its own independent data. JAW keeps each user's profile, capabilities, jobs, document resources, and preferences associated with that user.

## Recommended setup order

You do not need to configure every JAW feature before using it. A practical first setup is:

1. **Create your user** with **Manage User**.
2. Open **User Data** and enter the profile fields you regularly paste into applications.
3. Add your **Work Experience** and the highlights you want available to iterators and Documents.
4. Add or import **Capabilities**, rate them, and choose which ones participate in matching.
5. Review the **Application Assistant** keybinds and enable global hotkeys when you are ready to use them.
6. Try **Smart Capture** on a job description and review the captured fields.
7. Run **Analysis** to save/analyze the job and inspect it in **Job Tracker**.
8. Configure **Tectonic** if you want PDF preview/generation from Documents.
9. Configure **Ollama** or **OpenAI** only if you want optional generative workflows.

JAW's global hotkeys are disabled on startup by default, so installing or launching JAW should not immediately take over application shortcuts.

## AI is optional

New users start in **Local** Job Description Analysis mode. Local analysis performs deterministic extraction and capability matching without sending the job description to Ollama or a hosted provider.

Ollama is optional and is currently useful for:

- optional Smart Capture verification/enrichment;
- generative Job Description Analysis when Ollama is selected as the provider;
- AI generation blocks in Documents when Ollama is the selected generative provider;
- Outlook classification/matching when Outlook sync is explicitly enabled.

OpenAI is also optional for supported generative workflows. When selected, it can provide generative Job Description Analysis and Documents AI generation blocks. Plain Smart Capture parsing, local job analysis, Job Tracker, profile/keybind workflows, and ordinary Jinja-based document composition do not require an AI provider.

See [OpenAI Setup](openai.md) for API-key, billing, model, privacy, and connection-test guidance, or [Ollama Setup](ollama.md) for local-model installation and host configuration.

## PDF generation is optional

Tectonic is required only when JAW needs to compile a Document to PDF. Both **Preview** and **Generate** in Document Workbench compile through Tectonic.

You can use the rest of JAW without Tectonic, including Smart Capture, local/generative job analysis, Job Tracker, capabilities, and the Application Assistant.

See [Tectonic Setup](tectonic.md).

## Your local data

A normal installed Windows copy stores writable state under:

```text
%LOCALAPPDATA%\JAW\
├── config.toml
├── data\
│   └── jaw.db
└── fonts\
```

The SQLite database contains user data such as profiles, jobs, capabilities, application questions, keybind configuration, and Document Workbench resources.

JAW creates and normalizes `config.toml` automatically. The `fonts` directory is the writable location for user-provided document fonts and may not exist until it is needed.

### Source checkout

An editable source checkout intentionally uses the repository root as its application home. Development state is therefore written to ignored paths such as:

```text
<repository>\config.toml
<repository>\data\jaw.db
<repository>\fonts\
```

### Custom application home

Set `JAW_HOME` before starting JAW to use another writable location:

```powershell
$env:JAW_HOME = "D:\JAW"
jaw
```

To persist the setting for your Windows user:

```powershell
[System.Environment]::SetEnvironmentVariable("JAW_HOME", "D:\JAW", "User")
```

Open a new terminal after changing a persistent environment variable.

## A first workflow to try

After creating your own user and adding a small amount of profile/work-history data:

1. Copy or select a job description in the browser.
2. Run **Smart Capture** and review the extracted company, title, location, pay, work arrangement, and description.
3. Run **Analysis** to persist the job.
4. Open **Job Tracker** to review match information and application status.
5. Open **Documents** and select **Example Data** or the tracked job as the Generation Context.
6. Use **Preview** or **Generate** after Tectonic is installed.

In Job Tracker, the **?** help button explains document generation/routing and the `Ctrl+P` shortcut. In Documents, `Ctrl+P` opens the Documents command palette.

## Next steps

- [Installation](installation.md)
- [OpenAI Setup](openai.md)
- [Ollama Setup](ollama.md)
- [Tectonic Setup](tectonic.md)
- [Document Workbench](document-workbench.md)
- [Documents Runtime Objects](documents-runtime.md)
- [Outlook Sync](outlook-sync.md)
