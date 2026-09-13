#!/usr/bin/env python3
"""Snck Bot launcher: validates Discord application and installs the KVM bridge."""
from __future__ import annotations
import asyncio, json, os, sqlite3, sys
from functools import partial
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
API_URL='https://discord.com/api/v10/oauth2/applications/@me'

def fetch_application(token):
 r=Request(API_URL,headers={'Authorization':f'Bot {token}','User-Agent':'SnckBot/3.0'})
 try:
  with urlopen(r,timeout=15) as x:return json.loads(x.read().decode())
 except HTTPError as e:
  if e.code in (401,403): raise RuntimeError('Discord rejected the bot token.') from e
  raise RuntimeError(f'Discord API returned HTTP {e.code}.') from e
 except URLError as e: raise RuntimeError(f'Could not reach Discord: {e.reason}') from e
 except Exception as e: raise RuntimeError(f'Could not validate the Discord application: {e}') from e

def owner_id(a):
 o=a.get('owner') or {}; t=a.get('team') or {}
 if o.get('id'): return str(o['id'])
 if t.get('owner_user_id'): return str(t['owner_user_id'])
 for m in t.get('members') or []:
  u=m.get('user') or {}
  if u.get('id') and m.get('membership_state')==2:return str(u['id'])
 return None

def seed_admin(admin_id):
 p=os.path.join(os.path.dirname(os.path.abspath(__file__)),'vps.db')
 with sqlite3.connect(p) as c:
  c.execute('CREATE TABLE IF NOT EXISTS admins (user_id TEXT PRIMARY KEY)')
  c.execute('INSERT OR IGNORE INTO admins VALUES (?)',(admin_id,)); c.commit()

def install_kvm_commands(mod):
 from kvm_discord_bridge import ensure_schema, node_uri, deploy, start, stop, reboot, delete, stats
 ensure_schema()

 async def refresh():
  mod.vps_data=mod.get_vps_data()
  return mod.vps_data

 async def kvm_create_flow(ctx,user,os_version,node_id,ram,cpu,disk):
  await refresh(); node=mod.get_node(node_id)
  if not node: raise RuntimeError(f'Node {node_id} not found')
  uid=str(user.id); base=mod.sanitize_username_for_container(user.name.lower())[:24] or 'user'
  with mod.get_db() as c:
   next_id=(c.execute('SELECT COALESCE(MAX(id),0)+1 FROM vps').fetchone()[0])
  name=f'{base}-vps-{next_id}'; password=mod.generate_strong_password(); expiry=(mod.datetime.now()+mod.timedelta(days=mod.DEFAULT_VPS_EXPIRATION_DAYS)).isoformat()
  await deploy(name,ram,cpu,disk,password,os_version,node.get('storage') or '/var/lib/libvirt/images',node_uri(node))
  vid=mod.get_db().execute('SELECT COALESCE(MAX(id),0) FROM vps').fetchone()[0]+1
  # Persist using the bot's existing schema writer so panel and bot share records.
  vps={'id':vid,'container_name':name,'node_id':node_id,'ram':f'{ram}GB','cpu':str(cpu),'storage':f'{disk}GB','config':f'{ram}GB RAM / {cpu} CPU / {disk}GB Disk','os_version':os_version,'status':'running','suspended':False,'whitelisted':False,'suspension_history':[],'created_at':mod.datetime.now().isoformat(),'shared_with':[],'expiration_date':expiry,'root_password':password}
  mod.vps_data.setdefault(uid,[]).append(vps); mod.save_vps_data_immediate(); await refresh()
  return name,password,vid

 async def os_select(self,interaction):
  if str(interaction.user.id)!=str(self.ctx.author.id):
   await interaction.response.send_message(embed=mod.create_error_embed('Access Denied','Only the command author can select the OS.'),ephemeral=True); return
  os_version=self.select.values[0]
  for child in self.children: child.disabled=True
  await interaction.response.edit_message(view=self)
  try:
   name,password,vid=await kvm_create_flow(self.ctx,self.user,os_version,self.node_id,self.ram,self.cpu,self.disk)
   e=mod.create_success_embed('VPS Created','The KVM VPS is running and synchronized with the web panel.')
   mod.add_field(e,'VPS ID',f'#{vid}',True); mod.add_field(e,'Container',f'`{name}`',True); mod.add_field(e,'OS',os_version,True)
   mod.add_field(e,'Resources',f'{self.ram}GB RAM / {self.cpu} CPU / {self.disk}GB Disk',False)
   await interaction.followup.send(embed=e)
   try: await self.user.send(f'Snck VPS `{name}` is ready. Root password: `{password}`')
   except Exception: pass
  except Exception as exc:
   mod.logger.exception('KVM create failed')
   await interaction.followup.send(embed=mod.create_error_embed('VPS Creation Failed',str(exc)[:3500]))
  finally: mod._deploying_users.discard(str(self.user.id))

 mod.OSSelectView.select_os=os_select

 async def free_deploy(ctx,user,os_version,node_id):
  name,password,vid=await kvm_create_flow(ctx,user,os_version,node_id,mod.DEPLOY_RAM,mod.DEPLOY_CPU,mod.DEPLOY_DISK)
  e=mod.create_success_embed('VPS Deployed',f'KVM VPS `{name}` is ready and visible in the web panel.')
  mod.add_field(e,'VPS ID',f'#{vid}',True); mod.add_field(e,'Owner',user.mention,True); mod.add_field(e,'OS',os_version,True)
  mod.add_field(e,'Resources',f'{mod.DEPLOY_RAM}GB RAM / {mod.DEPLOY_CPU} CPU / {mod.DEPLOY_DISK}GB Disk',False)
  try: await user.send(f'Snck VPS `{name}` is ready. Root password: `{password}`')
  except Exception: pass
  await ctx.send(embed=e)
 mod._do_free_deploy=free_deploy

 async def manage_embed(self,index):
  await refresh(); v=self.vps_list[index]; node=mod.get_node(v.get('node_id',1)); s=await stats(v['container_name'],node_uri(node))
  color=0x10b981 if s['status']=='running' else 0xef4444
  e=mod.create_embed(f'VPS Management - {index+1}',f"Managing `{v['container_name']}`",color)
  mod.add_field(e,'Status',f"`{s['status'].upper()}`",True); mod.add_field(e,'IP',f"`{s['ip'] or 'pending'}`",True)
  mod.add_field(e,'Resources',f"RAM: `{v.get('ram')}`\nCPU: `{v.get('cpu')}`\nDisk: `{v.get('storage')}`\nOS: `{v.get('os_version','ubuntu:24.04')}`",False)
  return e
 mod.ManageView.create_vps_embed=manage_embed

 async def manage_action(self,interaction,action):
  try: await interaction.response.defer(ephemeral=True)
  except Exception:return
  if str(interaction.user.id)!=str(self.user_id) and not self.is_admin:
   await interaction.followup.send(embed=mod.create_error_embed('Access Denied','This is not your VPS.'),ephemeral=True);return
  if self.selected_index is None:self.selected_index=0
  actual=self.actual_index if self.is_shared else self.indices[self.selected_index]
  await refresh(); owner=str(self.owner_id); v=mod.vps_data.get(owner,[])[actual]; node=mod.get_node(v.get('node_id',1)); uri=node_uri(node); name=v['container_name']
  try:
   if action=='start': await start(name,uri); v['status']='running'
   elif action=='stop': await stop(name,uri); v['status']='stopped'
   elif action=='stats':
    s=await stats(name,uri); await interaction.followup.send(embed=mod.create_info_embed('Live VPS Statistics',f"`{name}`\nStatus: `{s['status']}`\nIP: `{s['ip'] or 'pending'}`"),ephemeral=True); return
   elif action=='tmate' or action=='sshx':
    s=await stats(name,uri); await interaction.followup.send(embed=mod.create_info_embed('VPS Connection',f"VPS IP: `{s['ip'] or 'pending'}`\nUse the root credentials from deployment."),ephemeral=True); return
   elif action=='reinstall':
    await interaction.followup.send(embed=mod.create_info_embed('Reinstall','Use the panel Reinstall action for a KVM OS reinstall.'),ephemeral=True); return
   else:
    await interaction.followup.send(embed=mod.create_info_embed('Not Available',f'`{action}` is not supported by the KVM adapter.'),ephemeral=True); return
   mod.save_vps_data_immediate(); await refresh()
   await interaction.followup.send(embed=mod.create_success_embed('VPS Updated',f'`{name}` is now `{v["status"]}`.'),ephemeral=True)
  except Exception as exc: await interaction.followup.send(embed=mod.create_error_embed('VPS Operation Failed',str(exc)[:3500]),ephemeral=True)
 mod.ManageView.action_callback=manage_action

 async def restart(ctx,name):
  await refresh(); node=mod.get_node(mod.find_node_id_for_container(name))
  try:
   await reboot(name,node_uri(node)); await refresh()
   await ctx.send(embed=mod.create_success_embed('VPS Restarted',f'`{name}` restarted successfully.'))
  except Exception as exc: await ctx.send(embed=mod.create_error_embed('Restart Failed',str(exc)[:3500]))
 cmd=mod.bot.get_command('restart-vps')
 if cmd: cmd.callback=restart

 async def vps_stats(ctx,name):
  await refresh(); node=mod.get_node(mod.find_node_id_for_container(name))
  try:
   s=await stats(name,node_uri(node)); await ctx.send(embed=mod.create_info_embed(f'VPS Statistics - {name}',f"Status: `{s['status']}`\nIP: `{s['ip'] or 'pending'}`"))
  except Exception as exc: await ctx.send(embed=mod.create_error_embed('Statistics Failed',str(exc)[:3500]))
 cmd=mod.bot.get_command('vps-stats')
 if cmd: cmd.callback=vps_stats

 async def delete_vps(ctx,user,number,*,reason='No reason'):
  await refresh(); uid=str(user.id); items=mod.vps_data.get(uid,[])
  if number<1 or number>len(items): await ctx.send(embed=mod.create_error_embed('Invalid VPS','Invalid VPS number.')); return
  v=items[number-1]; node=mod.get_node(v.get('node_id',1));
  try:
   await delete(v['container_name'],node_uri(node),node.get('storage') or '/var/lib/libvirt/images')
   with mod.get_db() as c:
    c.execute('DELETE FROM vps WHERE id=?',(v.get('id'),)); c.execute('DELETE FROM port_forwards WHERE vps_container=?',(v['container_name'],)); c.commit()
   await refresh(); await ctx.send(embed=mod.create_success_embed('VPS Deleted',f"`{v['container_name']}` deleted."))
  except Exception as exc: await ctx.send(embed=mod.create_error_embed('Delete Failed',str(exc)[:3500]))
 cmd=mod.bot.get_command('delete-vps')
 if cmd: cmd.callback=delete_vps

 # Customer commands always refresh from the shared SQLite database.
 for name in ('myvps','manage','vpsinfo','vps-uptime'):
  cmd=mod.bot.get_command(name)
  if cmd:
   old=cmd.callback
   async def wrapped(ctx,*args,_old=old,**kwargs):
    await refresh(); return await _old(ctx,*args,**kwargs)
   cmd.callback=wrapped

def load_panel_bridge(mod):
 async def setup_hook():
  original=getattr(mod.bot,'_snck_original_setup_hook',None)
  if original: await original()
  try: await mod.bot.load_extension('snck_panel_bridge')
  except Exception as exc: print(f'[Snck] Panel bridge failed: {exc}',file=sys.stderr)
 if not hasattr(mod.bot,'_snck_original_setup_hook'):
  mod.bot._snck_original_setup_hook=mod.bot.setup_hook
 mod.bot.setup_hook=setup_hook

def main():
 token=os.getenv('DISCORD_TOKEN','').strip()
 if not token: print('[Snck] DISCORD_TOKEN is missing.',file=sys.stderr); return 1
 try:
  app=fetch_application(token); admin=owner_id(app)
  if not admin: print('[Snck] Could not determine Discord application owner.',file=sys.stderr); return 1
  os.environ['MAIN_ADMIN_ID']=admin; seed_admin(admin)
 except RuntimeError as e: print(f'[Snck] {e}',file=sys.stderr); return 1
 import bot as mod
 load_panel_bridge(mod)
 install_kvm_commands(mod)
 print('[Snck] KVM Discord integration loaded.')
 mod.bot.run(token)
 return 0
if __name__=='__main__': raise SystemExit(main())
