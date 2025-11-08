# 🧰 MCP Box

**MCP Box** helps you discover, deploy, and test MCPs in isolated sandboxes. It includes:

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
- **HTTP API**: FastAPI routes for listing, fetching, and creating MCP records; health check and Swagger docs.
- **Razorpay Payments**: Required payment flow to create/verify orders and fetch payment status.
- **Lambda Executor**: Fetch repo ZIP, install deps to `/tmp`, run entrypoint, and stream response.

> NOTE: The Lambda executor currently supports Python + Npm MCP servers.

## 🗂️ Project Structure

```text
.
├── docs/                       # Documentation (see INSTALL.md)
├── src/
│   └── mcpbox/
│       ├── cli/                # CLI: init, push, pull, search, inspect, scanners
│       │   ├── commands/       # CLI subcommands
│       │   └── scanners/       # SonarCloud, Bandit, ggshield, discovery
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

  - `GET /servers` – list all servers
  - `GET /servers/{name}` – get a server by name
  - `POST /servers` – create a server (see schemas in `mcpbox.shared.models`)
  - `PUT /servers/{name}` – update an existing server (partial updates supported)
  - `DELETE /servers/{name}` – remove a server from the registry

- **Payment**

  - `POST /payment/create-order`
  - `POST /payment/verify-payment`
  - `GET /payment/payment-status/{payment_id}`

- **Other**
  - `GET /health` – config + S3 readiness
  - `GET /docs` – OpenAPI docs

## 📜 License

This project is licensed under the [MIT License](LICENSE).

## 👥 Authors

- [Areeb Ahmed](https://github.com/areebahmeddd)
- [Amartya Anand](https://github.com/amarr07)
- [Arush Verma](https://github.com/arush3218)
- [Devansh Aryan](https://github.com/devansharyan123)
