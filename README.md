# 🧰 MCP Box

**MCP Box** (inspired by [Docker Hub](https://hub.docker.com)) helps you discover, deploy, and test MCPs in isolated sandboxes. It includes:

- A friendly CLI to initialize metadata, run security scans, push to a registry (S3), search, and configure popular AI clients (VS Code, Cursor, Windsurf, Claude, ChatGPT)
- A FastAPI backend to list/get/create MCP servers with optional pricing and security reports
- An AWS Lambda worker that executes MCP servers on demand directly from their Git repositories

Built with Python (FastAPI, Click), S3 (registry), and optional scanners.

Why this project:

- There’s no centralized MCP registry to discover all MCPs, and many lack clear usage docs.
- MCPs on our platform pass a 5‑step security/quality check (SonarQube, Bandit, GitGuardian) to reduce vulnerabilities and promote best practices.
- Unlike MCPs that run locally on your machine, MCP servers here execute in sandboxed environments and return responses securely.

For setup and deployment, see [docs/INSTALL.md](docs/INSTALL.md).

## Key Features

- **Central MCP Registry**: S3‑backed registry with per‑server JSON for easy discovery and portability.
- **Sandboxed Execution**: MCP servers run in isolated environments and return responses securely.
- **Security Pipeline (5‑step)**: SonarQube, Bandit, and GitGuardian checks with a unified report.
- **One‑Command Publish**: `mcpbox push` scans, discovers tools, and uploads a unified record to S3.
- **Client Auto‑Config**: `mcpbox pull --client cursor|vscode|...` writes correct MCP config pointing to the Lambda endpoint.
- **Terminal Runner**: `mcpbox run --name <server>` starts an interactive prompt against the Lambda executor.
- **Tool Discovery**: Regex‑based discovery across Python code and optional Node `package.json` definitions.

> NOTE: The Lambda executor currently supports Python + Npm MCP servers.

## 🗂️ Project Structure

```text
.
├── docs/                       # Documentation (see INSTALL.md)
├── src/
│   └── mcpbox/
│       ├── cli/                # CLI: init, auth, push, pull, run, search, inspect, test
│       │   ├── commands/       # CLI subcommands
│       │   └── scanners/       # SonarCloud, Bandit, ggshield, tool-discovery
│       ├── server/             # FastAPI app + routes
│       │   ├── routes/         # servers, payment, auth
│       │   └── templates/      # Landing page
│       └── shared/             # Config, models, S3 utils
├── lambda.py                   # AWS Lambda handler (executor)
├── main.py                     # Local dev server entry
├── pyproject.toml              # Project metadata & extras
├── Dockerfile                  # Server container
├── docker-compose.yaml         # Optional local stack
└── tests/                      # Tests (placeholder)
```

##

## 🌐 HTTP API (Server)

Base path: `/api/v1`

- **Servers**

  - `GET /servers/{name}` – get a server by name
  - `GET /servers` – list all servers
  - `POST /servers` – create a server (see schemas in `mcpbox.shared.models`)
  - `PUT /servers/{name}` – update an existing server (partial updates supported)
  - `DELETE /servers/{name}` – remove a server from the registry

- **Payment**

  - `POST /payment/create-order` – create a Razorpay order for server purchase
  - `POST /payment/verify-payment` – verify Razorpay payment signature
  - `GET /payment/payment-status/{payment_id}` – get payment status from Razorpay

- **Other**
  - `GET /health` – config + S3 readiness
  - `GET /docs` – OpenAPI docs

## 💻 CLI Commands

The MCP Box CLI provides commands to initialize, publish, discover, and configure MCP servers.

### `mcpbox init`

Initialize a new `mcpbox.json` configuration file for your MCP server.

**Usage:**

```bash
mcpbox init
```

**What it does:**

- Creates `mcpbox.json` in the current directory
- Prompts for server metadata (name, version, description, author, language, license, entrypoint)
- Optionally adds pricing information
- Extracts repository information from GitHub URLs

**Example:**

```bash
$ mcpbox init
Initialize MCP Box Configuration
==================================================
Repository URL (GitHub): https://github.com/user/my-mcp
Server name: my-mcp
Version: 1.0.0
Description: My awesome MCP server
...
```

### `mcpbox push`

Publish an MCP server to the registry with comprehensive security scanning.

**Usage:**

```bash
mcpbox push [--name NAME] [--force]
```

**Options:**

- `--name NAME` – MCP server name (reads from `mcpbox.json` if not provided)
- `--force` – Force overwrite if server already exists

**What it does:**

1. Runs SonarQube analysis (creates project, scans code quality)
2. Discovers MCP tools via regex patterns in Python/Node.js code
3. Runs GitGuardian secret scan
4. Runs Bandit Python security scan
5. Generates unified security report
6. Uploads server metadata to S3 registry

**Example:**

```bash
$ mcpbox push --name my-mcp
Pushing server: my-mcp
Running SonarCloud analysis...
Running additional scanners...
Uploading to S3...
Push complete
```

### `mcpbox pull`

Pull an MCP server from the registry and configure it for your AI client.

**Usage:**

```bash
mcpbox pull --name NAME --client CLIENT
```

**Options:**

- `--name NAME` – MCP server name to pull (required)
- `--client CLIENT` – Target client: `vscode`, `cursor`, `windsurf`, `claude`, or `chatgpt` (required)

**What it does:**

- Fetches server metadata from S3
- Writes client-specific MCP configuration file
- Configures the client to use the Lambda executor endpoint

**Example:**

```bash
$ mcpbox pull --name my-mcp --client cursor
Fetching server 'my-mcp' from S3 bucket...
Success!
Server 'my-mcp' added to Cursor MCP config
Location: ~/.cursor/mcp.json
```

### `mcpbox run`

Start an interactive terminal session to test an MCP server.

**Usage:**

```bash
mcpbox run --name NAME
```

**Options:**

- `--name NAME` – MCP server name to run (required)

**What it does:**

- Connects to the Lambda executor
- Provides an interactive prompt to send requests to the MCP server
- Displays JSON responses

**Example:**

```bash
$ mcpbox run --name my-mcp
Connecting to MCP executor: https://lambda-url/my-mcp
Type 'exit' or 'quit' to end. Press Enter on empty line to continue.
> What tools are available?
{
  "tools": ["tool1", "tool2", "tool3"]
}
```

### `mcpbox search`

List all available MCP servers in the registry.

**Usage:**

```bash
mcpbox search
```

**What it does:**

- Lists all servers from S3 registry
- Shows repository URL, tool count, description, and security status

**Example:**

```bash
$ mcpbox search
======================================================================
Available MCP Servers (5 found)
======================================================================

[my-mcp]
   Repository: https://github.com/user/my-mcp
   Tools: 3
   Description: My awesome MCP server
   Security: All scans passed
```

### `mcpbox inspect`

Open the repository URL for a registered MCP server in your browser.

**Usage:**

```bash
mcpbox inspect --name NAME
```

**Options:**

- `--name NAME` – MCP server name to inspect (required)

**What it does:**

- Fetches server metadata from S3
- Opens the repository URL in your default browser

**Example:**

```bash
$ mcpbox inspect --name my-mcp
Fetching server 'my-mcp' from S3 bucket...
Opening repository: https://github.com/user/my-mcp
Done.
```

### `mcpbox test`

Test an MCP server directly from a repository URL without registry registration or security checks.

**Usage:**

```bash
mcpbox test --url URL --client CLIENT [--entrypoint FILE] [--lang LANGUAGE]
```

**Options:**

- `--url URL` – Repository URL of the MCP server (required)
- `--client CLIENT` – Target client: `vscode`, `cursor`, `windsurf`, `claude`, or `chatgpt` (required)
- `--entrypoint FILE` – Entrypoint file (default: `main.py`)
- `--lang LANGUAGE` – Language (default: `python`)

**What it does:**

- Bypasses S3 registry and security scanning
- Configures client to use Lambda executor with direct repo URL
- Useful for testing MCPs before publishing

**Example:**

```bash
$ mcpbox test --url https://github.com/user/my-mcp --client cursor
⚠️  TEST MODE - No Security Checks
This server is being tested directly and has NOT gone through:
  • Security scanning (SonarQube, Bandit, GitGuardian)
  • Quality checks
  • Registry validation
```

## 📜 License

This project is licensed under the [MIT License](LICENSE).

## 👥 Authors

**Core Contributors:**

- [Areeb Ahmed](https://github.com/areebahmeddd)
- [Amartya Anand](https://github.com/amarr07)
- [Arush Verma](https://github.com/arush3218)
- [Devansh Aryan](https://github.com/devansharyan123)

**Acknowledgments:**

- [Shivansh Karan](https://github.com/spacetesla)
- [Rishi Chirchi](https://github.com/rishichirchi)
- [Avantika Kesarwani](https://github.com/avii09)
