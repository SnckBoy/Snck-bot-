# Snck KVM Panel + Discord VPS Deploy Bot

This repository is the GitHub upload source for the Snck KVM panel and integrated Discord VPS deployment bot.

## Upload layout

```text
Snck-bot-/
├── akvm.py                 # KVM/QEMU panel + integrated Discord bot
├── requirements.txt        # Python dependencies
├── install.sh              # Interactive one-command installer
├── restart.sh              # Service restart helper
├── show_license.py         # Snck license/install identity helper
├── README.md
├── LICENSE
└── .gitignore
```

## One-command installer

```bash
curl -fsSL "https://raw.githubusercontent.com/SnckBoy/Snck-bot-/main/install.sh?$(date +%s)" | bash
```

The installer opens the menu first. Nothing is installed until option `1` is selected.

```text
[1] Install Snck KVM Panel + Discord Bot
[2] Update Snck KVM Panel
[3] Uninstall Snck KVM Panel
[4] Check Live Status
[0] Exit
```

After selecting `1`, it installs the KVM/QEMU dependencies, creates the Python environment, installs requirements, and starts the panel service.

## GitHub upload

Upload the project files to the repository root. Do not upload secrets, `.env` files, databases, virtual environments, logs, or private SSH keys.

The repository should contain the installer at exactly:

```text
install.sh
```

so the raw URL above works.

## Discord bot

The Discord bot is integrated with the panel. Configure the Discord bot from the panel's administrator settings after installation. Keep the bot token private and never commit it to GitHub.

## KVM requirements

The host must expose hardware virtualization for KVM acceleration. The installer checks KVM availability and installs QEMU/KVM tooling. If KVM acceleration is unavailable, QEMU may fall back to software emulation, which is substantially slower.

## License

The project uses the **Snck License** identity. Generated license/install identifiers use the `SNCK-` prefix.
