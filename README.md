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

## 🚀 Quick Install

### Ubuntu / Debian

The easiest method is the one-command installer:

```bash
curl -fsSL https://raw.githubusercontent.com/SnckBoy/Snck-bot-/main/install.sh | bash
```

If your system requires root privileges:

```bash
curl -fsSL https://raw.githubusercontent.com/SnckBoy/Snck-bot-/main/install.sh | sudo bash
```

The installer will:

1. Check/install required Ubuntu/Debian packages.
2. Download the bot files.
3. Create a Python virtual environment.
4. Install Python dependencies.
5. Ask for your Discord bot configuration.
6. Create a protected `.env` file.
7. Check that `bot.py` is valid Python.
8. Start the bot automatically.
9. Use systemd when available, or a background process when systemd is unavailable.

### 📦 What will the installer ask?

You will be asked for:

- **Discord Bot Token** — your bot's secret token.
- **Main Admin Discord User ID** — your Discord user ID.
- **VPS IP/hostname** — optional public IP/hostname used by the bot.
- **Deploy Role ID** — optional Discord role allowed to use self-service deployment.
- **Deploy RAM** — default: `16 GB`.
- **Deploy CPU** — default: `3 cores`.
- **Deploy Disk** — default: `80 GB`.
- **Per-user VPS limit** — default: `1`.
- **Global VPS slot limit** — default: `0` (unlimited).

You can normally press **Enter** to use a displayed default value.

---

## 🔑 Discord Bot Setup

Before installing, create a Discord application and bot in the Discord Developer Portal.

Make sure the bot has the intents required by the source, including:

- **Message Content Intent**
- **Server Members Intent**

Invite the bot to your Discord server with only the permissions it actually needs.

### Finding Discord IDs

If the installer asks for a user or role ID:

1. Open Discord settings.
2. Enable **Developer Mode**.
3. Right-click the user or role.
4. Select **Copy User ID** or **Copy Role ID**.
5. Paste the numeric ID into the installer.

---

## 🖥️ VPS / LXC Node Setup

There are two different parts to understand:

### 1. Discord Bot

The bot is the Discord control layer. It can run on a normal Linux VPS or in GitHub Codespaces.

### 2. VPS/LXC Node

The node is the machine that actually performs container/VPS operations.

For local VPS/LXC operations, the node needs the appropriate:

- Linux environment
- LXC/LXD support required by the bot
- Storage pool
- Network/bridge configuration
- CPU/RAM/disk resources
- Container permissions
- Firewall/network configuration
- Privileges to create, start, stop, inspect, and delete containers

For remote nodes, the corresponding node-agent/API must also be configured and reachable by the bot.

> **Codespaces note:** Codespaces is useful for developing or running the Discord bot, but it should not be treated as a production virtualization node.

---

## 📁 Installation Location

The installer normally creates:

```text
~/snck-bot/
├── bot.py
├── requirements.txt
├── .env
├── .env.example
├── .venv/
├── install.log
├── bot.log          # non-systemd mode
├── bot.pid          # non-systemd mode
└── database files   # created by the bot when needed
```

The `.env` file contains your secret configuration and is protected with restrictive permissions.

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

---

## ☁️ GitHub Codespaces / Non-Systemd

If systemd is unavailable, the installer starts Snck Bot as a background process.

View the log:

```bash
tail -f ~/snck-bot/bot.log
```

Stop the bot:

```bash
kill "$(cat ~/snck-bot/bot.pid)"
```

Start it manually:

```bash
cd ~/snck-bot
./start.sh
```

Remember that a Codespace may stop or reset, so it is not a replacement for a persistent production VPS node.

---

## ⚙️ Configuration

The most important settings are:

| Setting | Meaning | Default |
|---|---|---:|
| `DISCORD_TOKEN` | Discord bot token | Required |
| `MAIN_ADMIN_ID` | Main administrator's Discord ID | Required |
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
- Message Content Intent is enabled.
- Server Members Intent is enabled if required.
- The bot is actually in your Discord server.
- The bot has the permissions needed for the command.
- `MAIN_ADMIN_ID` contains the correct numeric Discord user ID.

### VPS creation does not work

Check the node rather than only the Discord bot. Make sure the node has the required LXC/LXD installation, storage, networking, permissions, and resources.

---

## 🔄 Updating

Before updating, back up your `.env` and any important database data.

For a manual installation:

```bash
cd ~/snck-bot
curl -fsSL https://raw.githubusercontent.com/SnckBoy/Snck-bot-/main/bot.py -o bot.py
curl -fsSL https://raw.githubusercontent.com/SnckBoy/Snck-bot-/main/requirements.txt -o requirements.txt
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m py_compile bot.py
```

Then restart the bot:

```bash
sudo systemctl restart snck-discord-bot
```

If systemd is unavailable, use `./start.sh` after stopping the previous process.

---

## 🔐 Security

**Keep your secrets private.**

Never commit or publicly share:

- Discord bot tokens
- Passwords
- API keys
- `.env`
- Database files containing sensitive data
- Private logs containing credentials

If your Discord bot token is exposed, regenerate it immediately in the Discord Developer Portal.

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

Create your local configuration:

```bash
cp .env.example .env
chmod 600 .env
```

Then configure `.env` and run:

```bash
python bot.py
```

---

## 📌 Important Notes

- Snck Bot is a Discord management/control bot; it does not magically turn a normal Codespace into a VPS virtualization host.
- Actual container/VPS provisioning requires a suitable privileged node.
- Use only infrastructure and accounts you are authorized to manage.
- Always protect your Discord token and other credentials.

---

## 📄 License

No license is currently published for this repository. Add an explicit license before redistributing Snck Bot.

---

## 🔗 Repository

**Snck Bot:**

https://github.com/SnckBoy/Snck-bot-
