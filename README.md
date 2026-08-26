# Snck Bot

Snck Bot is a Discord-based VPS management bot for provisioning and managing Linux containers through a local LXC host or configured remote node. The bot stores management data in SQLite and loads runtime configuration from a protected `.env` file.

> **Important:** Discord bot operation can run in GitHub Codespaces, but production VPS/LXC creation requires a properly configured VPS or node with the required privileges, LXC/LXD support, networking, storage, and kernel capabilities. A normal Codespace must not be treated as a production virtualization node.

## Features

Snck Bot includes Discord-based VPS creation and management, resource limits for RAM, CPU, and disk, operating-system selection, expiration tracking, sharing and administrative controls, port-forwarding support, SQLite persistence, local and remote node support, and automatic restart behavior when installed as a systemd service.

## Requirements

You need a Discord application and bot token, Python 3.10 or newer, outbound network access, and a Discord server where the bot can be invited. For local VPS/LXC operations, the host must also provide LXC/LXD and the privileges required to create, start, stop, inspect, and delete containers. Remote nodes require the bot’s corresponding node-agent/API setup and valid network access.

The current Python dependencies are listed in [`requirements.txt`](requirements.txt): `discord.py`, `python-dotenv`, and `requests`.

## One-command installation

On Ubuntu or Debian, run the following command. The installer downloads the project files, installs operating-system prerequisites, creates an isolated virtual environment, installs Python dependencies, prompts for configuration, validates the source, and starts the bot.

```bash
curl -fsSL https://raw.githubusercontent.com/SnckBoy/Snck-bot-/main/install.sh | bash
```

If root privileges are required for package installation or systemd registration, use:

```bash
curl -fsSL https://raw.githubusercontent.com/SnckBoy/Snck-bot-/main/install.sh | sudo bash
```

The application is installed under `~/snck-bot` for a normal user, or under the invoking user’s home directory when run through `sudo`. The installer creates `.venv`, `.env`, `bot.log` or a systemd journal, and the SQLite database at runtime.

## Manual Ubuntu/Debian installation

To install from a clone instead of the one-command installer, use:

```bash
git clone https://github.com/SnckBoy/Snck-bot-.git
cd Snck-bot
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
cp .env.example .env
chmod 600 .env
$EDITOR .env
python -m py_compile bot.py
python bot.py
```

Do not place a real token in the repository or commit `.env`.

## Configuration

The installer asks for the core values below and writes them to `.env` without echoing the Discord token. Values not requested interactively can be adjusted in `.env` before starting the bot.

| Variable | Purpose | Example/default |
|---|---|---|
| `DISCORD_TOKEN` | Discord bot token; keep secret | Required |
| `BOT_NAME` | Bot identity used by the bot | `Snck` |
| `PREFIX` | Command prefix | `!` |
| `MAIN_ADMIN_ID` | Discord user ID of the main administrator | Required |
| `YOUR_SERVER_IP` | Public IP or hostname used for port-forwarding information | Optional |
| `VPS_USER_ROLE_ID` | Existing Discord role ID for VPS users | `0` |
| `DEFAULT_STORAGE_POOL` | Local LXC storage pool | `default` |
| `DEPLOY_ROLE_ID` | Role allowed to use self-service `!deploy`; `0` disables it | `0` |
| `DEPLOY_RAM` | RAM allocated to self-service deployments, in GB | `16` |
| `DEPLOY_CPU` | CPU cores allocated to self-service deployments | `3` |
| `DEPLOY_DISK` | Disk allocated to self-service deployments, in GB | `80` |
| `VPS_DEPLOY_LIMIT` | Maximum self-service VPS count per user | `1` |
| `DEPLOY_SLOT` | Global self-service VPS limit; `0` means unlimited | `0` |
| `DEFAULT_VPS_EXPIRATION_DAYS` | Default VPS lifetime | `30` |
| `EXPIRATION_WARNING_DAYS` | Warning period before expiration | `1` |
| `BOT_VERSION` | Displayed bot version | `1.0` |
| `BOT_DEVELOPER` | Displayed developer name | `Snck` |
| `BOT_THUMBNAIL_URL` / `BOT_ICON_URL` | Optional branding image URLs | Empty |

Use numeric Discord IDs rather than names. In Discord, enable Developer Mode, right-click the relevant user or role, and select **Copy User ID** or **Copy Role ID**.

## Discord Developer Portal setup

In the Discord Developer Portal, open the bot’s application and enable the privileged intents required by the source: **Message Content Intent** and **Server Members Intent**. Invite the bot with the permissions required for its commands, including sending messages, embedding links, managing roles where applicable, and responding to interactions. Follow the principle of least privilege and avoid granting Administrator unless it is genuinely required by your deployment.

## Starting and managing the bot

For a manual installation, start the bot from the application directory:

```bash
./start.sh
```

The launcher expects `.venv` beside `bot.py`. On a systemd installation, use:

```bash
sudo systemctl status snck-discord-bot
sudo systemctl restart snck-discord-bot
sudo systemctl stop snck-discord-bot
sudo systemctl start snck-discord-bot
```

View systemd logs with:

```bash
sudo journalctl -u snck-discord-bot -f
```

In Codespaces or another non-systemd environment, the installer uses a safe background process. View its logs and status with:

```bash
tail -f ~/snck-bot/bot.log
kill "$(cat ~/snck-bot/bot.pid)"       # stop
cd ~/snck-bot && ./start.sh             # start manually
```

## Updating

Back up `.env` and any important database data before updating. Then fetch the latest source, reinstall dependencies, validate the source, and restart the service:

```bash
cd ~/snck-bot
cp .env ../snck-bot.env.backup
curl -fsSL https://raw.githubusercontent.com/SnckBoy/Snck-bot-/main/bot.py -o bot.py
curl -fsSL https://raw.githubusercontent.com/SnckBoy/Snck-bot-/main/requirements.txt -o requirements.txt
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m py_compile bot.py
sudo systemctl restart snck-discord-bot 2>/dev/null || ./start.sh
```

If you update from Git, use `git pull` instead of downloading individual files and review changes before restarting.

## VPS/LXC node requirements

The bot’s VPS features execute local LXC commands or call configured remote nodes. A production node must therefore have the necessary LXC/LXD packages, storage pool, bridge/network configuration, container nesting and privilege settings, firewall rules, sufficient RAM/CPU/disk, and permission to manage containers. Remote-node configuration additionally requires the node URL, API key, reachable ports, and the separate node-agent/API component expected by the bot.

Codespaces is suitable for developing or running the Discord control plane when systemd is unavailable. It normally does not provide the privileged virtualization environment, stable public networking, or persistent infrastructure required for production LXC provisioning.

## Security

Never commit `.env`, Discord tokens, passwords, API keys, database files, logs, or process IDs. The repository’s `.gitignore` excludes these runtime artifacts, and the installer sets `.env` to mode `600`. If a token is ever exposed, immediately regenerate it in the Discord Developer Portal. Do not paste tokens into issues, chat logs, screenshots, or public documentation.

## Troubleshooting

If installation fails, inspect `~/snck-bot/install.log`. If the bot starts and then exits, inspect `bot.log` or the systemd journal. A missing token, disabled Discord intents, invalid numeric Discord IDs, unavailable LXC commands, insufficient node privileges, or unreachable remote-node configuration are common causes.

## License

No license has been published in this repository yet. Add an explicit license before redistributing the project.
