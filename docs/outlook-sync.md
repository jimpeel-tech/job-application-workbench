# Outlook Sync

JAW can connect to Outlook through Microsoft Graph, classify job-search email with local Ollama, apply JAW-managed Outlook categories, and safely advance matching Job Tracker records.

Outlook sync is **disabled by default** and requires explicit configuration.

## What Outlook sync does

A sync can:

- read messages received within the selected time window;
- cheaply filter out mail that does not look job-related;
- use local Ollama to classify likely job mail;
- match the message to an existing JAW job;
- apply a JAW-managed Outlook category;
- move a matching JAW job forward when confidence and deterministic safety checks pass;
- send ambiguous job mail to **9 Review** without changing Job Tracker status.

JAW currently manages these Outlook categories:

```text
1 Application
2 Rejected
3 Recruiter
4 Interview
5 Offer
9 Review
```

Other Outlook categories already on a message are preserved.

## Prerequisites

You need:

1. JAW with Outlook sync enabled in `config.toml`.
2. A Microsoft Entra application registration for JAW.
3. Delegated Microsoft Graph `Mail.ReadWrite` permission.
4. Public-client/device-code authentication enabled on the Entra application.
5. `JAW_OUTLOOK_CLIENT_ID` available to the JAW process.
6. A running local Ollama instance with JAW's Outlook model installed.

JAW uses MSAL's public-client device-code flow. It does **not** use or require a client secret.

## 1. Set up Ollama

Outlook classification is always local Ollama in the current implementation. It does not inherit JAW's normal OpenAI/Ollama analysis-provider choice.

Follow [Ollama setup](ollama.md) first.

By default Outlook sync uses:

```text
qwen3:14b
```

Confirm the model is installed:

```powershell
ollama list
```

To use another installed Ollama model specifically for Outlook:

```powershell
$env:JAW_OUTLOOK_OLLAMA_MODEL = "your-model"
```

For a persistent Windows user setting:

```powershell
[System.Environment]::SetEnvironmentVariable(
    "JAW_OUTLOOK_OLLAMA_MODEL",
    "your-model",
    "User"
)
```

Outlook classification uses the same Ollama host resolution as the rest of JAW, including the `OLLAMA_HOST` environment variable.

## 2. Create a Microsoft Entra application

In the Microsoft Entra admin center, open:

**Entra ID -> App registrations -> New registration**

Use a recognizable name such as:

```text
Job Application Workbench
```

Choose the supported account type that matches the mailbox you intend to use.

For a personal Outlook.com / Hotmail / Live mailbox, **Personal Microsoft accounts only** is sufficient. If the same registration must support both organizational Microsoft 365 accounts and personal Microsoft accounts, use the account-type option that supports both.

After registration, copy the **Application (client) ID** from the Overview page.

JAW needs the Application/client ID, not the Object ID or Directory/tenant ID.

## 3. Enable public-client authentication

Open the application registration's **Authentication** settings and enable public-client flow support:

```text
Allow public client flows: Yes
```

JAW uses device-code authentication, so it does not require a client secret or a web redirect URI.

## 4. Add Microsoft Graph permission

Open:

**API permissions -> Add a permission -> Microsoft Graph -> Delegated permissions**

Add:

```text
Mail.ReadWrite
```

JAW needs write access because it updates message categories in Outlook. It does not use mail-send permission.

`Mail.ReadWrite` delegated permission is available for personal Microsoft accounts and does not itself require admin consent. Organizational tenant policy can still restrict user consent, so a work/school account may require administrator approval depending on the tenant.

## 5. Configure JAW environment variables

Set the Entra Application/client ID before starting JAW.

### Current PowerShell session

```powershell
$env:JAW_OUTLOOK_CLIENT_ID = "YOUR-APPLICATION-CLIENT-ID"
```

For a personal Microsoft account, also set:

```powershell
$env:JAW_OUTLOOK_TENANT = "consumers"
```

Then start JAW from that terminal:

```powershell
jaw
```

During development, `python run.py` also works from the repository checkout.

### Persistent Windows user variables

```powershell
[System.Environment]::SetEnvironmentVariable(
    "JAW_OUTLOOK_CLIENT_ID",
    "YOUR-APPLICATION-CLIENT-ID",
    "User"
)

[System.Environment]::SetEnvironmentVariable(
    "JAW_OUTLOOK_TENANT",
    "consumers",
    "User"
)
```

Open a new terminal after changing persistent environment variables.

### Tenant behavior

JAW defaults to:

```text
JAW_OUTLOOK_TENANT=common
```

For a personal Outlook.com / Hotmail / Live mailbox, explicitly using `consumers` avoids attempting to authenticate the personal account against an organizational tenant.

Use another tenant value only when it matches how you intentionally registered the application.

## 6. Enable the feature in `config.toml`

Outlook sync is opt-in.

Set:

```toml
[behavior]
outlook_sync_enabled = true
```

JAW's writable config is normally:

```text
%LOCALAPPDATA%\JAW\config.toml
```

For an editable source checkout, JAW intentionally uses the repository root instead. `JAW_HOME` overrides both locations.

See [Installation](installation.md) for the full data-path behavior.

When Outlook sync is disabled:

- the Tracker Outlook panel stays hidden;
- Outlook mutation API routes reject requests.

## 7. Connect Outlook

Restart JAW after configuring the environment variables, then open **Job Tracker** in the JAW dashboard.

The Outlook panel should appear near the top of the Tracker.

Click **Connect Outlook**.

JAW starts a Microsoft device-code flow and shows:

- a Microsoft verification URL;
- a short device code;
- an **Open Microsoft sign-in** button.

Open the Microsoft sign-in page, enter the code, sign into the mailbox you want JAW to use, and approve the requested permission.

Return to JAW and click:

**I've signed in**

A successful connection reports the Microsoft account associated with the cached sign-in.

## 8. Run a sync

Choose the mailbox window and click **Sync Outlook**.

Available windows are:

```text
30 days
90 days
1 year
2 years
```

The default is 30 days.

JAW reads Microsoft Graph message summaries first. Only messages that pass the inexpensive job-mail prefilter have their full body fetched and sent to local Ollama for classification.

The dashboard reports results such as:

```text
279 scanned · 18 status updates · 69 categorized · 31 review
```

A sync reads at most 2,500 messages by default. The backend accepts a larger limit up to 5,000; the UI uses the default. JAW reports when the message limit was reached.

## Classification and matching safety

Model confidence alone is never enough to change a JAW job.

For an automatic action, JAW currently requires both classification confidence and job-match confidence of at least:

```text
0.90
```

It then applies deterministic checks as well.

For example:

- the employer extracted from the email must match the JAW job's company;
- the employer must be directly evidenced in the email;
- when multiple active jobs exist for the same employer, JAW requires unambiguous title evidence;
- the proposed status change must be a valid lifecycle transition.

If those gates do not pass, a job-related message is categorized **9 Review** instead of silently changing a JAW job.

### Forward lifecycle behavior

JAW does not let an old acknowledgement move a job backward after a newer event.

Microsoft Graph returns newest messages first, but JAW intentionally evaluates them oldest-to-newest when applying lifecycle transitions.

Examples of supported forward changes include:

```text
Captured/Reviewing/Interested/Applying -> Applied
Applied -> Recruiter Screen
Applied/Recruiter Screen -> Interviewing
Applied/Recruiter Screen/Interviewing -> Offer
non-terminal status -> Rejected
```

`Rejected`, `Withdrawn`, and `Archived` jobs are not moved forward again by Outlook sync.

## Message processing and privacy

For likely job mail, JAW can send the following message data to the locally configured Ollama server:

- sender name/address;
- subject;
- received timestamp;
- message body text;
- a limited candidate-job list from JAW.

The classifier prompt treats email content as untrusted data and explicitly instructs the model to ignore prompts or instructions contained in the email itself.

JAW does not send Outlook email to OpenAI as part of the Outlook sync pipeline.

Microsoft Graph is still used to retrieve Outlook messages and apply categories to the connected mailbox.

## Processed-message tracking

JAW records Microsoft Graph message IDs and sync decisions in its SQLite database. Messages already processed for the current JAW user are skipped on later syncs.

JAW asks Graph for immutable message IDs so IDs remain stable when messages move between Outlook folders.

This state also supports test-reset behavior.

## Reset test sync

After at least one sync, the Tracker exposes:

**Reset test sync**

This resets JAW-side Outlook processing decisions so the messages can be evaluated again on the next sync.

The reset attempts to undo JAW status changes caused by the prior sync while preserving later manual status changes where possible.

This is primarily useful while testing classifier or matching changes.

## Token cache

Successful MSAL authentication is stored locally at:

```text
<JAW home>\data\outlook-token-cache.json
```

The cache lets JAW request tokens silently on later launches instead of repeating device-code sign-in each time.

The token cache is local account data. Do not commit or share it.

The backend disconnect operation removes this cache. The current Tracker panel focuses on Connect/Sync/Reset rather than exposing a separate Disconnect button.

## Troubleshooting

### Outlook panel does not appear

Confirm:

```toml
[behavior]
outlook_sync_enabled = true
```

Then reload the dashboard. Restart JAW if you changed environment variables at the same time.

### `Setup required · set JAW_OUTLOOK_CLIENT_ID`

The Entra Application/client ID is not available to the running JAW process.

Check the current shell:

```powershell
$env:JAW_OUTLOOK_CLIENT_ID
```

Restart JAW after setting the variable.

### Personal account says it does not exist in the tenant

For Outlook.com / Hotmail / Live accounts, set:

```powershell
$env:JAW_OUTLOOK_TENANT = "consumers"
```

Also confirm the Entra registration supports personal Microsoft accounts.

### Permission or consent error

Confirm the Entra application has delegated:

```text
Mail.ReadWrite
```

For a work/school account, your organization's consent policies may require administrator approval even though the delegated permission itself is not marked as admin-consent-required.

### Ollama connection/model error

Outlook sync cannot classify job email unless its local Ollama model is available.

Check:

```powershell
ollama list
```

The default Outlook model is `qwen3:14b`. If you override it with `JAW_OUTLOOK_OLLAMA_MODEL`, the named model must already be installed.

See [Ollama setup](ollama.md).

### Microsoft Graph error

Verify that:

- the connected account is the mailbox you intended;
- the access grant includes `Mail.ReadWrite`;
- the machine can reach Microsoft Graph;
- the cached Microsoft sign-in is still valid.

## Personal Outlook checklist

A typical personal Outlook.com setup is:

```text
Ollama running
qwen3:14b installed (or JAW_OUTLOOK_OLLAMA_MODEL configured)
Entra application registered
Personal Microsoft accounts supported
Public client flow enabled
Delegated Microsoft Graph Mail.ReadWrite added
JAW_OUTLOOK_CLIENT_ID set to the Application/client ID
JAW_OUTLOOK_TENANT=consumers
[behavior] outlook_sync_enabled=true
JAW restarted after environment changes
Outlook connected through the Tracker device-code flow
```
