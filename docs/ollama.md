# Ollama Setup

Ollama is optional. JAW can capture and parse job descriptions without it, but Ollama enables local generative-AI verification and analysis without sending job content to a hosted AI provider.

JAW's default Ollama configuration is:

```text
Host:  http://127.0.0.1:11434
Model: qwen3:14b
```

## 1. Install Ollama

On Windows, Ollama's current installer can be started from PowerShell:

```powershell
irm https://ollama.com/install.ps1 | iex
```

You can also use the Windows installer from the official Ollama download page:

- https://ollama.com/download/windows

Ollama requires Windows 10 or newer.

## 2. Install JAW's default model

JAW defaults to `qwen3:14b`.

```powershell
ollama pull qwen3:14b
```

The current Ollama package for `qwen3:14b` is approximately 9.3 GB, so the initial download may take some time.

Verify that the model is installed:

```powershell
ollama ls
```

You should see `qwen3:14b` in the model list.

Official references:

- https://docs.ollama.com/cli
- https://ollama.com/library/qwen3:14b

## 3. Verify the local API

Ollama normally exposes its API on port `11434`.

From PowerShell:

```powershell
Invoke-RestMethod http://127.0.0.1:11434/api/tags
```

The response should contain the locally installed models.

JAW uses Ollama's `/api/tags` endpoint for model discovery and `/api/chat` for structured inference.

## 4. Configure JAW

Start JAW:

```powershell
jaw
```

In JAW's Smart Capture settings, select an Ollama-enabled analysis mode and use `qwen3:14b` unless you intentionally want another installed model.

JAW's connection test verifies both conditions:

1. the Ollama API is reachable;
2. the configured model is installed.

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

> When `OLLAMA_HOST` points to another computer, job content sent for Ollama analysis is transmitted to that host. Localhost keeps that traffic on the machine running JAW.

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

Then install JAW's default model if needed:

```powershell
ollama pull qwen3:14b
```

### Use a different model

Install the model with Ollama first, then configure the same exact model name in JAW. JAW treats a configured model as unavailable when it does not appear in Ollama's local model list.
