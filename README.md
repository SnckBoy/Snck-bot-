# 🤖 Snck Bot

**Snck Bot** is a Discord bot for managing VPS/LXC containers from Discord.

It is designed to make VPS management simple: install the bot, connect it to your Discord server, configure a node, and use the bot's commands to manage supported VPS/container tasks.

> **Important:** The Discord bot itself can run on Ubuntu, Debian, or GitHub Codespaces. Actual VPS/LXC creation needs a real, properly configured Linux node with the required virtualization privileges. A normal Codespace is **not** a production VPS node.

## ✨ What can Snck Bot do?

- 🖥️ Manage VPS/LXC containers
- 🚀 Create and manage supported VPS instances
- ▶️ Start, stop, and inspect containers
- 💾 Apply RAM, CPU, and disk limits
- 🐧 Select supported operating systems
- ⏰ Track VPS expiration
- 👥 Share VPS access where supported
- 🔌 Support port-forwarding information
- 🌐 Work with local or configured remote nodes
- 💿 Store management data in SQLite
- 🔄 Automatically restart with systemd on supported Linux systems
- ☁️ Run the Discord control bot in GitHub Codespaces/non-systemd environments

---

## 🚀 One-Command Install

On Ubuntu/Debian, run:

```bash
curl -fsSL https://raw.githubusercontent.com/SnckBoy/Snck-bot-/main/install.sh | bash
```

If your shell requires root for package installation:

```bash
curl -fsSL https://raw.githubusercontent.com/SnckBoy/Snck-bot-/main/install.sh | sudo bash
```

### 🔐 Installer setup

The installer now asks for **only one value**:

```text
Discord Bot Token:
```

The prompt is read from the terminal, so it works correctly with the `curl | bash` one-command installer. The token is not printed while you type it.

After the token is entered, the installer automatically:

1. Installs Python and required system packages.
2. Installs LXD when Snap is available.
3. Adds the installation user to the `lxd` group.
4. Initializes a minimal local LXD configuration when needed.
5. Downloads the current Snck Bot files.
6. Creates an isolated Python virtual environment.
7. Installs the Python dependencies.
8. Validates `bot.py` and `launcher.py` syntax.
9. Verifies the Discord token with Discord's application API.
10. Detects the Discord application's owner and registers that account as the main admin.
11. Starts the bot with systemd when available, otherwise background mode.
12. Restarts the bot automatically after crashes/reboots when systemd is available.

> **Security:** Never paste the bot token into chat, GitHub, screenshots, or public files. If a token is exposed, reset it in the Discord Developer Portal.

---

## 🔑 Discord Bot Setup

Create a Discord application and bot in the Discord Developer Portal before running the installer.

The bot needs the gateway intents required by the source, including:

- **Message Content Intent**
- **Server Members Intent** when required by the bot features you use

Invite the bot to your Discord server with the permissions required by its commands.

### Finding Discord IDs

The installer does not ask for a user ID. The Discord application owner is detected automatically after the token is validated.

For commands that specifically require a role or channel ID, enable Discord Developer Mode and copy the required ID from Discord.

---

## 🖥️ VPS / LXC Node Setup

There are two different parts to understand:

### 1. Discord Bot

The bot is the Discord control layer. It can run on a normal Linux VPS or in GitHub Codespaces.

### 2. VPS/LXC Node

The node is the machine that actually performs container/VPS operations.

For local VPS/LXC operations, the node needs the appropriate:

- Linux environment
- LXC/LXD support
- Storage pool
- Network/bridge configuration
- CPU/RAM/disk resources
- Container permissions
- Firewall/network configuration
- Privileges to create, start, stop, inspect, and delete containers

The installer attempts to prepare LXD automatically on Ubuntu/Debian. A VPS provider may still restrict nested/container virtualization; in that case the host must support LXD/LXC operations.

For remote nodes, the corresponding node-agent/API must also be configured and reachable by the bot.

> **Codespaces note:** Codespaces is useful for developing or running the Discord bot, but it should not be treated as a production virtualization node.

---

## 📁 Installation Location

The installer normally creates:

```text
~/snck-bot/
├── bot.py
├── launcher.py
├── requirements.txt
├── .env
├── .env.example
├── .venv/
├── install.log
├── bot.log          # non-systemd mode
├── bot.pid          # non-systemd mode
└── database files   # created by the bot when needed
```

The `.env` file contains the bot token and is protected with restrictive permissions.

**Never upload or commit `.env` to GitHub.**

---

## ▶️ Managing Snck Bot

### Check systemd status

```bash
sudo systemctl status snck-discord-bot
```

### Restart

```bash
sudo systemctl restart snck-discord-bot
```

### Stop

```bash
sudo systemctl stop snck-discord-bot
```

### Start

```bash
sudo systemctl start snck-discord-bot
```

### View live logs

```bash
sudo journalctl -u snck-discord-bot -f
```

### Non-systemd logs

```bash
tail -f ~/snck-bot/bot.log
```

---

## ⚙️ Configuration

Most settings have safe defaults. Advanced settings can still be changed in `~/snck-bot/.env` after installation.

| Setting | Meaning | Default |
|---|---|---:|
| `DISCORD_TOKEN` | Discord bot token | Required |
| `MAIN_ADMIN_ID` | Main admin; auto-detected by launcher | `0` before launch |
| `YOUR_SERVER_IP` | Public server IP/hostname | Optional |
| `BOT_NAME` | Bot name | `Snck` |
| `PREFIX` | Command prefix | `!` |
| `VPS_USER_ROLE_ID` | Existing VPS-user role ID | `0` |
| `DEFAULT_STORAGE_POOL` | LXC storage pool | `default` |
| `DEPLOY_ROLE_ID` | Role allowed to self-deploy | `0` |
| `DEPLOY_RAM` | Self-deploy RAM in GB | `16` |
| `DEPLOY_CPU` | Self-deploy CPU cores | `3` |
| `DEPLOY_DISK` | Self-deploy disk in GB | `80` |
| `VPS_DEPLOY_LIMIT` | VPS limit per user | `1` |
| `DEPLOY_SLOT` | Global VPS limit | `0` = unlimited |
| `DEFAULT_VPS_EXPIRATION_DAYS` | Default VPS lifetime | `30` |
| `EXPIRATION_WARNING_DAYS` | Expiration warning period | `1` |

---

## 🛠️ Troubleshooting

### Installer fails

Check the installer log:

```bash
cat ~/snck-bot/install.log
```

### Bot starts and then stops

Systemd:

```bash
sudo journalctl -u snck-discord-bot -n 100 --no-pager
```

Non-systemd:

```bash
cat ~/snck-bot/bot.log
```

### Bot is online but commands do not work

Check:

- The Discord bot token is correct.
- The required gateway intents are enabled.
- The bot is actually in your Discord server.
- The bot has the permissions needed for the command.
- The application owner was detected in the startup log.

### VPS creation does not work

Check the node rather than only the Discord bot. Make sure the node has the required LXC/LXD installation, storage, networking, permissions, and resources. Also check:

```bash
lxc info
lxc list
```

If LXD itself is unavailable, the VPS deployment commands cannot create local containers.

---

## 🔄 Updating

Back up `.env` and `vps.db` before updating.

For a manual installation:

```bash
cd ~/snck-bot
curl -fsSL https://raw.githubusercontent.com/SnckBoy/Snck-bot-/main/bot.py -o bot.py
curl -fsSL https://raw.githubusercontent.com/SnckBoy/Snck-bot-/main/launcher.py -o launcher.py
curl -fsSL https://raw.githubusercontent.com/SnckBoy/Snck-bot-/main/requirements.txt -o requirements.txt
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m py_compile bot.py launcher.py
```

Then restart:

```bash
sudo systemctl restart snck-discord-bot
```

---

## 📋 Requirements

### Basic bot requirements

- Ubuntu or Debian recommended for the installer
- Python **3.10+**
- Internet access
- Discord application/bot
- A Discord server where the bot can be invited

### VPS/LXC requirements

Additional virtualization requirements are needed for actual VPS/container management. The exact requirements depend on the node setup and the LXC/LXD functionality being used.

Python dependencies are defined in:

```text
requirements.txt
```

Current core dependencies include:

- `discord.py`
- `python-dotenv`
- `requests`

---

## 🧑‍💻 Development

Clone the repository:

```bash
git clone https://github.com/SnckBoy/Snck-bot-.git
cd Snck-bot-
```

Create a virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Install dependencies:

```bash
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Create local configuration:

```bash
cp .env.example .env
chmod 600 .env
```

Then configure `DISCORD_TOKEN` and run:

```bash
./start.sh
```

---

## 📌 Important Notes

- Snck Bot is a Discord management/control bot; it does not magically turn a normal Codespace into a VPS virtualization host.
- Actual container/VPS provisioning requires a suitable privileged node.
- Use only infrastructure and accounts you are authorized to manage.
- Protect your Discord token and other credentials.

---

## 🔗 Repository

**Snck Bot:**

https://github.com/SnckBoy/Snck-bot-
