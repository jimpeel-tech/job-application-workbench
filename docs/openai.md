# OpenAI Setup

OpenAI is an optional hosted AI provider for JAW. You do not need an OpenAI API key to use Smart Capture's deterministic parsing, the default Local Job Description Analysis path, Job Tracker, profile/keybind workflows, or ordinary Jinja-based document composition.

JAW currently uses OpenAI for:

- generative Job Description Analysis when **Generative AI** and **OpenAI** are selected;
- AI generation blocks in Documents when OpenAI is the active generative provider.

Smart Capture's optional AI verification/enrichment and Outlook sync use Ollama rather than OpenAI.

## Before you begin

OpenAI API usage is billed separately from ChatGPT subscriptions such as Plus or Pro. If you want to use OpenAI from JAW, you need an OpenAI API account with API billing configured and an API key.

Useful OpenAI references:

- [Create and manage API keys](https://help.openai.com/en/articles/4936850-where-do-i-find-my-secret-api-key)
- [API key safety](https://help.openai.com/en/articles/5112595-best-practices-for-api-key-safet)
- [ChatGPT billing vs. API billing](https://help.openai.com/en/articles/9039756-managing-billing-settings-on-the-chatgpt-web-and-api-platform)
- [OpenAI API models](https://platform.openai.com/docs/models)

Do not put your API key in JAW source files, templates, `config.toml`, or user-data exports.

## Set `OPENAI_API_KEY` on Windows

JAW reads the OpenAI credential from the Windows environment variable:

```text
OPENAI_API_KEY
```

The recommended setup is to create it as a **User environment variable**:

1. Open **System Properties** in Windows.
2. Open **Advanced** -> **Environment Variables**.
3. Under **User variables**, click **New**.
4. Set **Variable name** to `OPENAI_API_KEY`.
5. Set **Variable value** to your OpenAI API key.
6. Save the dialogs.
7. Fully exit JAW and launch it again.

JAW must be restarted because a running process does not automatically receive environment variables that were added after it started.

You can also set the user variable from PowerShell:

```powershell
[System.Environment]::SetEnvironmentVariable(
    "OPENAI_API_KEY",
    "your-api-key-here",
    "User"
)
```

Be aware that entering a secret directly in a terminal command may leave it in shell history. The Windows Environment Variables UI avoids that particular exposure.

## Configure JAW

After setting the environment variable and restarting JAW:

1. Open JAW **Settings**.
2. Expand **Job Description Analysis**.
3. Select **Generative AI**.
4. Select **OpenAI** as the AI provider.
5. Choose a model.
6. Click **Test connection**.

A successful test confirms that JAW can authenticate to OpenAI and access the selected model without running a full job analysis.

The current OpenAI model choices exposed by JAW are:

| Model | JAW label | Use case |
| --- | --- | --- |
| `gpt-5.6-terra` | GPT-5.6 Terra · balanced | General default when balancing capability and cost |
| `gpt-5.6-luna` | GPT-5.6 Luna · cost-sensitive | Lower-cost/high-volume use |
| `gpt-5.6-sol` | GPT-5.6 Sol · highest capability | More demanding reasoning/generation |

Model availability and pricing are controlled by OpenAI and can change independently of JAW. See OpenAI's current model and pricing documentation before relying on a particular model for cost-sensitive workflows.

## What JAW sends to OpenAI

When OpenAI is selected for **Job Description Analysis**, JAW sends the captured job description together with the Work Experience and capabilities selected for matching so the provider can return structured analysis.

For **Documents** AI generation blocks, JAW sends the generation instructions plus only the structured JAW runtime roots referenced by those instructions. For example, a block that references `work_exp` and `job_ref` sends those evidence objects rather than the entire JAW database.

JAW does not send the `OPENAI_API_KEY` through the browser UI and does not store it in JAW's SQLite database, `config.toml`, exports, or website state. The key is read by the JAW process from the operating-system environment when an OpenAI request is made.

JAW's OpenAI Responses API requests currently set `store: false`. OpenAI's own API data-handling, abuse-monitoring, and retention policies still apply independently of JAW; `store: false` should not be interpreted as a guarantee that the provider retains no request data under every account or policy configuration.

## Cost

OpenAI API usage may incur charges based on the model and amount of input/output processed. ChatGPT subscriptions and OpenAI API billing are separate products.

Use the **Test connection** button to verify credentials/model access before running generative analysis, and review your OpenAI API usage/billing controls if you want to place limits on spend.

## Troubleshooting

### `OPENAI_API_KEY is not available to JAW`

The JAW process cannot see the environment variable.

- Confirm the variable name is exactly `OPENAI_API_KEY`.
- Fully exit JAW and launch it again after creating or changing the variable.
- If you launched JAW from a terminal, open a new terminal after changing persistent environment variables.

### Authentication or API errors

Use **Test connection** and read the returned OpenAI error. Common causes include an invalid/revoked API key, API billing not being configured, account usage limits, or lack of access to the selected model.

### Selected model is unavailable

Choose another OpenAI model offered by JAW and run **Test connection** again. Provider model availability can change independently of a JAW release.

## Related documentation

- [First Run](first-run.md)
- [Installation](installation.md)
- [Ollama Setup](ollama.md)
- [Document Workbench](document-workbench.md)
