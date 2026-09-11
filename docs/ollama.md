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

## 2. Check your GPU memory and choose a model

The most useful hardware number when choosing a local model is **dedicated GPU memory**, also called **VRAM**. More VRAM lets Ollama keep more of the model on the GPU, which is normally much faster than using system memory/CPU for part of the model.

### Find your VRAM on Windows

The simplest method works for NVIDIA, AMD, and Intel GPUs:

1. Press **Ctrl+Shift+Esc** to open **Task Manager**.
2. Open **Performance**.
3. Select **GPU**.
4. Look for **Dedicated GPU memory**.

Use the dedicated-memory value for the table below. Do not add **Shared GPU memory** to it; shared memory comes from normal system RAM and is much slower than VRAM for model inference.

NVIDIA users can also check from PowerShell or Command Prompt:

```powershell
nvidia-smi --query-gpu=name,memory.total --format=csv,noheader
```

### JAW starting points

These are practical starting points rather than hard limits. Exact memory use depends on the model tag/quantization, context length, and Ollama version.

| Dedicated VRAM | Suggested JAW starting point | Guidance |
| ---: | --- | --- |
| 4 GB | `qwen3:4b` | Lightweight option; good place to start on smaller GPUs. |
| 6–8 GB | `qwen3:4b` or `qwen3:8b` | Try 8B for better quality; drop to 4B if it spills heavily into CPU/system RAM. |
| 10–12 GB | `qwen3:8b` or `qwen3:14b` | 14B is JAW's preferred model when it fits well; 10 GB can be tight depending on context. |
| 16 GB | `qwen3:14b` | Strong default for JAW with useful headroom. |
| 24 GB+ | `qwen3:14b` or a larger model such as `qwen3:30b` | Larger models become practical; verify GPU residency and responsiveness before keeping them as your default. |

For reference, Ollama's default Qwen3 downloads are roughly a few GB for 4B, around 5 GB for 8B, around 9 GB for 14B, and around 19 GB for 30B. **Download size is not the same as runtime VRAM use.** Ollama also needs memory for context/KV cache and runtime overhead, so leave some headroom rather than choosing a model whose file size exactly matches your VRAM.

### What if the model is larger than your VRAM?

Ollama can often still run it by placing some model data in normal system memory and doing part of the work on the CPU. That is functional, but usually slower.

For the best JAW experience, prefer a model that stays mostly or entirely on the GPU. A smaller model running at `100% GPU` can feel much faster than a larger model that constantly spills into CPU/system RAM.

Longer context also consumes more memory. Large job descriptions, large document-generation prompts, or a larger configured context window can make a model that normally fits begin to spill.

### Verify the choice with `ollama ps`

After installing a model, load it once:

```powershell
ollama run qwen3:14b "Reply with OK"
```

Then, while the model is still loaded, run:

```powershell
ollama ps
```

Look at the **PROCESSOR** column:

```text
100% GPU
```

is the ideal case for performance. A mixed value such as:

```text
35% CPU / 65% GPU
```

means the model is split between GPU and CPU/system memory. `100% CPU` means Ollama is not using GPU acceleration for that loaded model.

A mixed CPU/GPU result is not an error. If JAW feels slow, however, try the next smaller model and run `ollama ps` again. Test with a normal JAW workload, because memory use can increase with context length.

Official references:

- https://docs.ollama.com/faq
- https://docs.ollama.com/context-length
- https://ollama.com/library/qwen3

## 3. Install a model

For JAW's default model:

```powershell
ollama pull qwen3:14b
```

If your hardware is better suited to another size, install that exact model/tag instead. For example:

```powershell
ollama pull qwen3:8b
```

or:

```powershell
ollama pull qwen3:4b
```

JAW does not impose a Qwen-only allowlist. A smaller model can reduce memory use and improve latency, but may be less reliable at extraction, reasoning, or schema-constrained responses. A larger model may improve output quality but needs more memory and is slower.

Use model names currently offered by Ollama rather than assuming that a particular tag exists. If a different model frequently returns malformed structured output, choose another model rather than treating successful installation alone as compatibility proof.

List the models installed on your machine:

```powershell
ollama ls
```

The exact name shown by `ollama ls` is the name JAW sends to Ollama.

Official references:

- https://docs.ollama.com/cli
- https://ollama.com/library
- https://ollama.com/library/qwen3

## 4. Verify the local API

Ollama normally exposes its API on port `11434`.

From PowerShell:

```powershell
Invoke-RestMethod http://127.0.0.1:11434/api/tags
```

The response should contain the locally installed models.

JAW uses Ollama's `/api/tags` endpoint for model discovery and `/api/chat` for structured inference.

## 5. Choose a model in JAW

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

### JAW feels slow with Ollama

Load the configured model and inspect where it is running:

```powershell
ollama run qwen3:14b "Reply with OK"
ollama ps
```

If **PROCESSOR** shows substantial CPU use, try a smaller model. Also remember that longer context consumes more memory, so test using a representative JAW workflow rather than only a one-line prompt.

### A newly installed model does not appear

In **Smart Capture**, click **Refresh**. In **Job Description Analysis**, reselect **Ollama · local** to refresh the discovered model list. Restarting JAW also refreshes both lists.

### A model connects but generation fails

Connection and model discovery only prove that Ollama can see the model. JAW also relies on structured chat responses. If a model repeatedly produces invalid structured JSON or poor extraction results, select a model with stronger structured-output behavior; `qwen3:14b` remains JAW's default recommendation.
