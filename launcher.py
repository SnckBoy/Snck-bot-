#!/usr/bin/env python3
"""Snck Bot launcher and UI bootstrap."""
from __future__ import annotations
import asyncio,json,os,sqlite3,sys
from functools import partial
from urllib.error import HTTPError,URLError
from urllib.request import Request,urlopen
API_URL="https://discord.com/api/v10/oauth2/applications/@me"
def fetch_application(token):
 r=Request(API_URL,headers={"Authorization":f"Bot {token}","User-Agent":"SnckBot/2.0"})
 try:
  with urlopen(r,timeout=15) as x:return json.loads(x.read().decode())
 except HTTPError as e:
  if e.code in (401,403):raise RuntimeError("Discord rejected the bot token.") from e
  raise RuntimeError(f"Discord API returned HTTP {e.code}.") from e
 except URLError as e:raise RuntimeError(f"Could not reach Discord: {e.reason}") from e
 except Exception as e:raise RuntimeError(f"Could not validate the Discord application: {e}") from e
def owner_id(a):
 o=a.get("owner") or {}; t=a.get("team") or {}
 if o.get("id"):return str(o["id"])
 if t.get("owner_user_id"):return str(t["owner_user_id"])
 for m in t.get("members") or []:
  u=m.get("user") or {}
  if u.get("id") and m.get("membership_state")==2:return str(u["id"])
 return None
def seed_admin(admin_id):
 p=os.path.join(os.path.dirname(os.path.abspath(__file__)),"vps.db")
 with sqlite3.connect(p) as c:c.execute("CREATE TABLE IF NOT EXISTS admins (user_id TEXT PRIMARY KEY)");c.execute("INSERT OR IGNORE INTO admins VALUES (?)",(admin_id,));c.commit()
def _premium_embed_helpers(mod):
 View=mod.ManageView; original_action=View.action_callback
 async def premium_action_callback(self,interaction,action):
  if str(interaction.user.id)!=str(self.user_id) and not self.is_admin:
   await interaction.response.send_message(embed=mod.create_error_embed("Access Denied","You cannot manage this VPS."),ephemeral=True);return
  if action=="restart":
   await interaction.response.defer(ephemeral=True)
   try:
    idx=self.actual_index if self.is_shared else self.indices[self.selected_index];v=mod.vps_data[self.owner_id][idx];node=v.get("node_id",1)
    if v.get("status")!="running":await interaction.followup.send(embed=mod.create_error_embed("Cannot Restart","The VPS is stopped. Use Start instead."),ephemeral=True);return
    await mod.execute_lxc(v["container_name"],f"restart {v['container_name']}",node_id=node);v["status"]="running";mod.save_vps_data_immediate();await interaction.followup.send(embed=mod.create_success_embed("VPS Restarted",f"`{v['container_name']}` restarted successfully."),ephemeral=True)
   except Exception as e:await interaction.followup.send(embed=mod.create_error_embed("Restart Failed",str(e)[:1000]),ephemeral=True)
   return
  await original_action(self,interaction,action)
 def premium_add_action_buttons(self):
  self.clear_items()
  def add(label,style,action,row):
   b=mod.discord.ui.Button(label=label,style=style,row=row);b.callback=partial(self.action_callback,action=action);self.add_item(b)
  for label,style,action in [("Start",mod.discord.ButtonStyle.success,"start"),("Stop",mod.discord.ButtonStyle.secondary,"stop"),("Restart",mod.discord.ButtonStyle.primary,"restart"),("Refresh",mod.discord.ButtonStyle.secondary,"refresh"),("Stats",mod.discord.ButtonStyle.secondary,"stats"),("Reinstall",mod.discord.ButtonStyle.danger,"reinstall"),("SSH",mod.discord.ButtonStyle.primary,"tmate"),("SSHX",mod.discord.ButtonStyle.primary,"sshx"),("Password",mod.discord.ButtonStyle.secondary,"password"),("Network",mod.discord.ButtonStyle.secondary,"network"),("Ports",mod.discord.ButtonStyle.secondary,"ports")]:add(label,style,action,0 if action in {"start","stop","restart","refresh","stats"} else 1)
 View.action_callback=premium_action_callback;View.add_action_buttons=premium_add_action_buttons
def load_panel_bridge(bot_module):
 async def setup_hook():
  original=getattr(bot_module.bot,"_snck_original_setup_hook",None)
  if original:await original()
  try:await bot_module.bot.load_extension("snck_panel_bridge")
  except Exception as exc:print(f"[Snck] Customer panel bridge failed: {exc}",file=sys.stderr)
 if not hasattr(bot_module.bot,"_snck_original_setup_hook"):bot_module.bot._snck_original_setup_hook=bot_module.bot.setup_hook
 bot_module.bot.setup_hook=setup_hook
def main():
 token=os.getenv("DISCORD_TOKEN","").strip()
 if not token:print("[Snck] DISCORD_TOKEN is missing.",file=sys.stderr);return 1
 try:
  app=fetch_application(token);admin=owner_id(app)
  if not admin:print("[Snck] Could not determine the Discord application owner.",file=sys.stderr);return 1
  os.environ["MAIN_ADMIN_ID"]=admin;seed_admin(admin);print(f"[Snck] Discord application verified: {app.get('name','Unknown')}");print(f"[Snck] Application owner registered as main admin: {admin}")
 except RuntimeError as e:print(f"[Snck] {e}",file=sys.stderr);return 1
 import bot as bot_module
 load_panel_bridge(bot_module);_premium_embed_helpers(bot_module);print("[Snck] Customer panel bridge loaded.");bot_module.bot.run(token);return 0
if __name__=="__main__":raise SystemExit(main())
