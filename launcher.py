#!/usr/bin/env python3
"""Snck Bot launcher and UI bootstrap.

The installer remains token-only. This launcher validates the Discord token,
detects the application owner, seeds the owner as the main admin, loads the
existing bot, installs the Snck customer-panel bridge, and applies the premium
VPS management UI before starting it.
"""
from __future__ import annotations
import asyncio
import json
import os
import sqlite3
import sys
from datetime import datetime
from functools import partial
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

API_URL = "https://discord.com/api/v10/oauth2/applications/@me"

def fetch_application(token: str) -> dict:
    request = Request(API_URL, headers={"Authorization": f"Bot {token}", "User-Agent": "SnckBot/2.0"})
    try:
        with urlopen(request, timeout=15) as response: payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        if exc.code in (401, 403): raise RuntimeError("Discord rejected the bot token. Reset the token in the Developer Portal and run the installer again.") from exc
        raise RuntimeError(f"Discord API returned HTTP {exc.code}.") from exc
    except URLError as exc: raise RuntimeError(f"Could not reach Discord: {exc.reason}") from exc
    except Exception as exc: raise RuntimeError(f"Could not validate the Discord application: {exc}") from exc
    return payload

def owner_id(application: dict) -> str | None:
    owner = application.get("owner") or {}
    if owner.get("id"): return str(owner["id"])
    team = application.get("team") or {}
    if team.get("owner_user_id"): return str(team["owner_user_id"])
    for member in team.get("members") or []:
        user = member.get("user") or {}
        if user.get("id") and member.get("membership_state") == 2: return str(user["id"])
    return None

def seed_admin(admin_id: str) -> None:
    db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "vps.db")
    with sqlite3.connect(db_path) as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS admins (user_id TEXT PRIMARY KEY)")
        conn.execute("INSERT OR IGNORE INTO admins (user_id) VALUES (?)", (admin_id,))
        conn.commit()

def _premium_embed_helpers(mod):
    View = mod.ManageView
    original_action = View.action_callback
    def _owner_and_vps(self, interaction):
        if str(interaction.user.id) != str(self.user_id) and not self.is_admin: return None, None, None
        if self.selected_index is None: return None, None, None
        actual_idx = self.actual_index if self.is_shared else self.indices[self.selected_index]
        owner_list = mod.vps_data.get(self.owner_id, [])
        if actual_idx < 0 or actual_idx >= len(owner_list): return None, None, None
        return actual_idx, owner_list[actual_idx], str(self.owner_id)
    async def premium_action_callback(self, interaction, action):
        actual_idx, target_vps, owner_id = _owner_and_vps(self, interaction)
        if target_vps is None:
            await interaction.response.send_message(embed=mod.create_error_embed("Access Denied", "You cannot manage this VPS or it no longer exists."), ephemeral=True); return
        suspended = target_vps.get("suspended", False)
        if suspended and not self.is_admin and action not in {"stats", "network", "ports"}:
            await interaction.response.send_message(embed=mod.create_error_embed("VPS Suspended", "This VPS is suspended. Contact an admin to restore access."), ephemeral=True); return
        container = target_vps["container_name"]; node_id = target_vps.get("node_id", 1)
        if action in {"network", "ports"}:
            await interaction.response.defer(ephemeral=True)
            try:
                if action == "network":
                    networks = await asyncio.wait_for(mod.get_container_networks(container, node_id), timeout=15)
                    embed = mod.create_embed("Network Overview", f"Live network interfaces for `{container}`", mod.COLOR_NETWORK)
                    text = "\n".join(f"**{iface}** → `{addr}`" for iface, addr in sorted(networks.items())) if networks else "No usable IPv4 interface was detected."
                    mod.add_field(embed, "Interfaces", text, False); mod.add_field(embed, "VPS", f"`{container}`", True)
                else:
                    forwards = [f for f in mod.get_user_forwards(owner_id) if f.get("vps_container") == container]
                    embed = mod.create_embed("Port Center", f"Active forwards for `{container}`", mod.COLOR_NETWORK)
                    text = "\n".join(f"#{f['id']} `{f['host_port']}` → `{f['vps_port']}`" for f in forwards[:12]) or "No port forwards configured."
                    mod.add_field(embed, "Active Forwards", text, False)
                await interaction.followup.send(embed=embed, ephemeral=True)
            except Exception as exc: await interaction.followup.send(embed=mod.create_error_embed("Operation Failed", str(exc)[:1000]), ephemeral=True)
            return
        if action == "password":
            if self.is_shared and not self.is_admin:
                await interaction.response.send_message(embed=mod.create_error_embed("Access Denied", "Only the VPS owner can regenerate the root password."), ephemeral=True); return
            await interaction.response.defer(ephemeral=True)
            try:
                new_password = mod.generate_strong_password(); ok, result = await mod.configure_ssh(container, node_id, new_password)
                if not ok: raise RuntimeError(str(result))
                embed = mod.create_success_embed("Password Rotated", f"A new root password was generated for `{container}`."); mod.add_field(embed, "New Password", f"`{new_password}`", False)
                await interaction.followup.send(embed=embed, ephemeral=True)
            except Exception as exc: await interaction.followup.send(embed=mod.create_error_embed("Password Rotation Failed", str(exc)[:1000]), ephemeral=True)
            return
        if action == "restart":
            await interaction.response.defer(ephemeral=True)
            if target_vps.get("status") != "running": await interaction.followup.send(embed=mod.create_error_embed("Cannot Restart", "The VPS is stopped. Use Start instead."), ephemeral=True); return
            try:
                await mod.execute_lxc(container, f"restart {container}", node_id=node_id); target_vps["status"] = "running"; target_vps["suspended"] = False; mod.save_vps_data_immediate(); await mod.recreate_port_forwards(container)
                await interaction.followup.send(embed=mod.create_success_embed("VPS Restarted", f"`{container}` restarted successfully."), ephemeral=True)
            except Exception as exc: await interaction.followup.send(embed=mod.create_error_embed("Restart Failed", str(exc)[:1000]), ephemeral=True)
            return
        if action == "refresh":
            await interaction.response.defer()
            try:
                new_embed = await self.create_vps_embed(self.selected_index); await interaction.edit_original_response(embed=new_embed, view=self)
            except Exception as exc: await interaction.followup.send(embed=mod.create_error_embed("Refresh Failed", str(exc)[:1000]), ephemeral=True)
            return
        await original_action(self, interaction, action)
    def premium_add_action_buttons(self):
        self.clear_items()
        def add(label, style, action, row):
            button = mod.discord.ui.Button(label=label, style=style, row=row); button.callback = partial(self.action_callback, action=action); self.add_item(button)
        add("Start", mod.discord.ButtonStyle.success, "start", 0); add("Stop", mod.discord.ButtonStyle.secondary, "stop", 0); add("Restart", mod.discord.ButtonStyle.primary, "restart", 0); add("Refresh", mod.discord.ButtonStyle.secondary, "refresh", 0); add("Stats", mod.discord.ButtonStyle.secondary, "stats", 0)
        add("Reinstall", mod.discord.ButtonStyle.danger, "reinstall", 1); add("SSH", mod.discord.ButtonStyle.primary, "tmate", 1); add("SSHX", mod.discord.ButtonStyle.primary, "sshx", 1); add("Password", mod.discord.ButtonStyle.secondary, "password", 1); add("Network", mod.discord.ButtonStyle.secondary, "network", 1); add("Ports", mod.discord.ButtonStyle.secondary, "ports", 2)
    View.action_callback = premium_action_callback; View.add_action_buttons = premium_add_action_buttons

def load_panel_bridge(bot_module):
    """Load the Discord -> Snck customer portal account bridge."""
    async def setup_hook():
        original = getattr(bot_module.bot, "_snck_original_setup_hook", None)
        if original: await original()
        try: await bot_module.bot.load_extension("panel_bridge")
        except Exception as exc: print(f"[Snck] Panel bridge failed to load: {exc}", file=sys.stderr)
    if not hasattr(bot_module.bot, "_snck_original_setup_hook"):
        bot_module.bot._snck_original_setup_hook = bot_module.bot.setup_hook
    bot_module.bot.setup_hook = setup_hook

def main() -> int:
    token = os.getenv("DISCORD_TOKEN", "").strip()
    if not token: print("[Snck] DISCORD_TOKEN is missing.", file=sys.stderr); return 1
    try:
        application = fetch_application(token); admin = owner_id(application)
        if not admin: print("[Snck] Could not determine the Discord application owner.", file=sys.stderr); return 1
        os.environ["MAIN_ADMIN_ID"] = admin; seed_admin(admin)
        print(f"[Snck] Discord application verified: {application.get('name', 'Unknown')}"); print(f"[Snck] Application owner registered as main admin: {admin}")
    except RuntimeError as exc: print(f"[Snck] {exc}", file=sys.stderr); return 1
    try:
        import bot as bot_module
        load_panel_bridge(bot_module); _premium_embed_helpers(bot_module); print("[Snck] Customer panel bridge and premium VPS UI loaded."); bot_module.bot.run(token)
    except Exception as exc: print(f"[Snck] Bot startup failed: {exc}", file=sys.stderr); raise
    return 0
if __name__ == "__main__": raise SystemExit(main())
