# Ollama Setup

Ollama is optional. JAW's default Job Description Analysis mode is local/deterministic and does not require an AI service. Ollama adds local generative capabilities without sending job content to a hosted AI provider.

JAW's default Ollama configuration is:

```text
Host:  http://127.0.0.1:11434
Model: qwen3:14b
```

`qwen3:14b` is JAW's recommended/default local model, but it is **not hard-coded as the only supported model**. JAW discovers models installed in Ollama and lets you select another one. A model used by JAW must support Ollama's chat API and should behave reliably with structured JSON output; quality and structured-output reliability can vary by model.

## What JAW uses Ollama for

Ollama is not a general requirement for JAW. Its current role depends on the workflow:

| Workflow | Ollama required? | Current behavior |
| --- | --- | --- |
| Smart Capture parsing | No | Deterministic capture works without AI; Ollama can be enabled for optional verification/enrichment. |
| Job Description Analysis — Local | No | Deterministic extraction and capability matching run locally without an AI provider. |
| Job Description Analysis — Generative AI | Optional provider | Select Ollama for local generative analysis, or OpenAI for hosted analysis. |
| Documents — normal Jinja/Sections/Functions | No | Runtime objects and Jinja composition do not require AI. |
| Documents — AI generation blocks | Optional provider | Uses the active user's selected generative provider/model; Ollama is the local option. |
| Outlook sync classification | Yes when Outlook sync is used | Outlook classification has its own Ollama model setting. Outlook sync itself is opt-in. |

The important distinction is that **Local analysis does not mean Ollama**. JAW's Local Job Description Analysis path is deterministic. Ollama is used only when a workflow is configured to perform generative/local-model inference.

## 1. Install Ollama

On Windows, Ollama's current installer can be started from PowerShell:

```powershell
irm https://ollama.com/install.ps1 | iex
```

You can also use the Windows installer from the official Ollama download page:

- https://ollama.com/download/windows

Ollama requires Windows 10 or newer.

## 2. Install a model

For JAW's default model:

```powershell
ollama pull qwen3:14b
```

To use a different model, install the exact model/tag you want through Ollama instead. For example, you may choose another Qwen size when you want a different memory/speed/quality tradeoff. Use the model names currently offered by Ollama rather than assuming a particular tag exists.

List the models installed on your machine:

```powershell
ollama ls
```

The exact name shown by `ollama ls` is the name JAW sends to Ollama.

Official references:

- https://docs.ollama.com/cli
- https://ollama.com/library
- https://ollama.com/library/qwen3

## 3. Verify the local API

Ollama normally exposes its API on port `11434`.

From PowerShell:

```powershell
Invoke-RestMethod http://127.0.0.1:11434/api/tags
```

The response should contain the locally installed models.

JAW uses Ollama's `/api/tags` endpoint for model discovery and `/api/chat` for structured inference.

## 4. Choose a model in JAW

Start JAW:

```powershell
jaw
```

JAW has separate model choices for different workflows.

### Smart Capture

Open **Settings -> Smart Capture**.

1. Choose an Ollama-enabled Capture Analysis mode.
2. Select the desired value under **Ollama model**.
3. If you installed a model while JAW was already open, click **Refresh** to query Ollama again.

The currently configured model is preserved in the list even if Ollama is temporarily offline, so an unavailable server does not silently replace your configuration.

### Job Description Analysis

Open **Settings -> Job Description Analysis**.

1. Select **Generative AI**.
2. Select **Ollama · local** as the provider.
3. Choose any discovered installed model from **Model**.
4. Use **Test connection** to verify that Ollama is reachable and that the selected model is installed.

If you leave Job Description Analysis in **Local** mode, this provider/model selection is not used for the deterministic analysis path.

### Documents

Document Workbench has two distinct layers:

- ordinary Jinja expressions, runtime objects, Sections, and Functions are local template processing and do not require Ollama;
- AI generation blocks inside Sections/Functions use the active user's generative analysis provider/model settings.

For example, a Document containing only expressions such as `{{ user.full_name }}` or `{{ job_ref.company }}` does not invoke Ollama. A generation block such as `<summary>...</>` does.

See [Documents Runtime Objects](documents-runtime.md) and [Document Workbench](document-workbench.md).

### Outlook sync

Outlook classification intentionally has an independent model setting. It defaults to `qwen3:14b` and can be overridden with:

```powershell
$env:JAW_OUTLOOK_OLLAMA_MODEL = "exact-model-name-from-ollama-ls"
```

See [Outlook Sync](outlook-sync.md) for the persistent configuration example.

## Choosing a model

JAW does not impose a Qwen-only allowlist. In practice:

- **Start with `qwen3:14b`** for the configuration JAW is developed around.
- A smaller installed model can reduce memory use and improve latency, but may be less reliable at extraction, reasoning, or schema-constrained responses.
- A larger model may improve output quality but requires more memory and is slower.
- If a different model frequently returns malformed structured output, use another model rather than treating successful installation alone as compatibility proof.

After installing another model, run `ollama ls`, refresh/select it in JAW, then use **Test connection** before relying on it for job analysis or document generation.

## Custom Ollama host

JAW reads `OLLAMA_HOST` when connecting to Ollama. Use this when Ollama is listening somewhere other than the default localhost endpoint.

Current PowerShell session:

```powershell
$env:OLLAMA_HOST = "http://192.168.1.25:11434"
jaw
```

JAW also accepts a host without an explicit scheme and will prepend `http://`:

```powershell
$env:OLLAMA_HOST = "192.168.1.25:11434"
```

To persist the value for your Windows user:

```powershell
[System.Environment]::SetEnvironmentVariable(
    "OLLAMA_HOST",
    "http://192.168.1.25:11434",
    "User"
)
```

Open a new terminal after changing persistent environment variables.

> When `OLLAMA_HOST` points to another computer, content sent for Ollama inference is transmitted to that host. Localhost keeps that traffic on the machine running JAW.

## Troubleshooting

### `Could not reach Ollama`

Verify Ollama is running and the API responds:

```powershell
Invoke-RestMethod http://127.0.0.1:11434/api/tags
```

If you configured `OLLAMA_HOST`, test that host instead.

### Model is not installed

Check the installed models:

```powershell
ollama ls
```

Then either install the configured model or select one that is already installed. To restore JAW's default:

```powershell
ollama pull qwen3:14b
```

### A newly installed model does not appear

In **Smart Capture**, click **Refresh**. In **Job Description Analysis**, reselect **Ollama · local** to refresh the discovered model list. Restarting JAW also refreshes both lists.

### A model connects but generation fails

Connection and model discovery only prove that Ollama can see the model. JAW also relies on structured chat responses. If a model repeatedly produces invalid structured JSON or poor extraction results, select a model with stronger structured-output behavior; `qwen3:14b` remains JAW's default recommendation.
