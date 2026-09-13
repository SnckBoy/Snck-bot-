#!/usr/bin/env python3
"""Repair the installed Snck runtime so panel and Discord use the same KVM path."""
from pathlib import Path
import re
import sqlite3

ROOT = Path(__file__).resolve().parent

BOT_ROUTE = r'''@bot.command(name='deploy')
async def deploy_cmd(ctx):
    """Deploy a real KVM VPS through the shared panel backend."""
    if getattr(ctx.author, 'bot', False):
        return
    if DEPLOY_ROLE_ID:
        roles = {getattr(role, 'id', 0) for role in getattr(ctx.author, 'roles', [])}
        if DEPLOY_ROLE_ID not in roles and not getattr(ctx.author.guild_permissions, 'administrator', False):
            await ctx.send(embed=create_error_embed('Access Denied', 'You do not have permission to deploy a VPS.'))
            return
    handler = getattr(bot, '_snck_kvm_deploy', None)
    if handler is None:
        await ctx.send(embed=create_error_embed('KVM Backend Offline', 'The KVM integration is not loaded. Restart the Snck Discord bot service.'))
        return
    try:
        await handler(ctx, ctx.author)
    except Exception as exc:
        logger.exception('KVM deploy command failed')
        await ctx.send(embed=create_error_embed('VPS Creation Failed', str(exc)[:3500]))
'''


def patch_bot():
    p = ROOT / 'bot.py'
    if not p.exists(): raise SystemExit('Missing bot.py')
    text = p.read_text(encoding='utf-8')
    pattern = r"@bot\.command\(name=['\"]deploy['\"]\).*?(?=\n@bot\.(?:command|event)\b|\Z)"
    if not re.search(pattern, text, re.S): raise SystemExit('Could not locate deploy command in bot.py')
    text = re.sub(pattern, BOT_ROUTE.rstrip(), text, count=1, flags=re.S)
    anchor = "    # Add local node if not exists\n"
    migration = "    cur.execute('PRAGMA table_info(nodes)')\n    node_columns = {row[1] for row in cur.fetchall()}\n    node_migrations = {'url':'TEXT','location':'TEXT','total_vps':'INTEGER DEFAULT 100','tags':\"TEXT DEFAULT '[]'\",'api_key':'TEXT','is_local':'INTEGER DEFAULT 1'}\n    for col, typ in node_migrations.items():\n        if col not in node_columns:\n            cur.execute(f'ALTER TABLE nodes ADD COLUMN {col} {typ}')\n    if 'uri' in node_columns:\n        cur.execute(\"UPDATE nodes SET url=uri WHERE (url IS NULL OR url='')\")\n"
    if migration not in text:
        if anchor not in text: raise SystemExit('Could not locate nodes schema in bot.py')
        text = text.replace(anchor, migration + anchor, 1)
    p.write_text(text, encoding='utf-8')


def patch_launcher():
    p = ROOT / 'launcher.py'
    if not p.exists(): raise SystemExit('Missing launcher.py')
    text = p.read_text(encoding='utf-8')
    marker = 'mod._do_free_deploy=free_deploy'; binding = 'mod.bot._snck_kvm_deploy=free_deploy'
    if binding not in text:
        if marker not in text: raise SystemExit('Could not locate KVM deploy handler in launcher.py')
        text = text.replace(marker, marker + '\n ' + binding, 1)
    p.write_text(text, encoding='utf-8')


def patch_panel():
    p = ROOT / 'snck_panel.py'
    if not p.exists(): raise SystemExit('Missing snck_panel.py')
    text = p.read_text(encoding='utf-8')
    old = "pw=secrets.token_urlsafe(12);vm_create=name,ram,cpu,disk,pw\n   from kvm import create as real_create;real_create(name,ram,cpu,disk,pw,storage=n['storage'],uri=n['url']);real_start= start;real_start(name,n['url'])"
    new = "pw=secrets.token_urlsafe(12);node_uri=str(n['uri'] if 'uri' in n.keys() else (n['url'] if 'url' in n.keys() else '') or '');osver=request.form.get('os_version','ubuntu:24.04').strip() or 'ubuntu:24.04'\n   from kvm import create as real_create;real_create(name,ram,cpu,disk,pw,image={'ubuntu:20.04':'https://cloud-images.ubuntu.com/focal/current/focal-server-cloudimg-amd64.img','ubuntu:22.04':'https://cloud-images.ubuntu.com/jammy/current/jammy-server-cloudimg-amd64.img','ubuntu:24.04':'https://cloud-images.ubuntu.com/noble/current/noble-server-cloudimg-amd64.img'}.get(osver,'https://cloud-images.ubuntu.com/noble/current/noble-server-cloudimg-amd64.img'),storage=n['storage'],uri=node_uri);start(name,node_uri)"
    if old in text:
        text = text.replace(old, new, 1)
    else:
        text = text.replace("uri=n['url'] or ''", "uri=str(n['uri'] if 'uri' in n.keys() else (n['url'] if 'url' in n.keys() else '') or '')", 1)
        text = text.replace("uri=n['url']", "uri=str(n['uri'] if 'uri' in n.keys() else (n['url'] if 'url' in n.keys() else '') or '')", 1)
        text = text.replace("start(name,n['url'] or '')", "start(name,str(n['uri'] if 'uri' in n.keys() else (n['url'] if 'url' in n.keys() else '') or ''))", 1)

    marker = "  c.execute('INSERT OR IGNORE INTO settings VALUES(\\'license\\',?)',(MASTER_LICENSE,));"
    if marker in text and 'shared_schema_columns' not in text:
        injected = "  # shared_schema_columns\n  ncols={r[1] for r in c.execute('PRAGMA table_info(nodes)').fetchall()}\n  node_migrations={'location':'TEXT','total_vps':'INTEGER DEFAULT 100','tags':\"TEXT DEFAULT '[]'\",'api_key':'TEXT','url':'TEXT','is_local':'INTEGER DEFAULT 1'}\n  for col,typ in node_migrations.items():\n   if col not in ncols: c.execute(f'ALTER TABLE nodes ADD COLUMN {col} {typ}')\n  c.execute(\"UPDATE nodes SET url=uri WHERE 'uri' IN (SELECT name FROM pragma_table_info('nodes')) AND (url IS NULL OR url='')\")\n  vcols={r[1] for r in c.execute('PRAGMA table_info(vps)').fetchall()}\n  migrations={'container_name':'TEXT','storage':\"TEXT DEFAULT ''\",'config':\"TEXT DEFAULT ''\",'os_version':\"TEXT DEFAULT 'ubuntu:24.04'\",'suspended':\"INTEGER DEFAULT 0\",'whitelisted':\"INTEGER DEFAULT 0\",'shared_with':\"TEXT DEFAULT '[]'\",'suspension_history':\"TEXT DEFAULT '[]'\",'expiration_date':'TEXT DEFAULT NULL'}\n  for col,typ in migrations.items():\n   if col not in vcols: c.execute(f'ALTER TABLE vps ADD COLUMN {col} {typ}')\n  c.execute(\"UPDATE vps SET container_name=name WHERE (container_name IS NULL OR container_name='') AND name IS NOT NULL\")\n  c.execute(\"UPDATE vps SET storage=CAST(disk AS TEXT)||'GB' WHERE (storage IS NULL OR storage='') AND disk IS NOT NULL\")\n  c.execute(\"UPDATE vps SET config=CAST(ram AS TEXT)||'MB RAM / '||CAST(cpu AS TEXT)||' CPU / '||CAST(disk AS TEXT)||'GB Disk' WHERE (config IS NULL OR config='')\")\n"
        text = text.replace(marker, injected + marker, 1)
    p.write_text(text, encoding='utf-8')


def patch_panel_login():
    p = ROOT / 'snck_panel.py'
    if not p.exists(): raise SystemExit('Missing snck_panel.py')
    text = p.read_text(encoding='utf-8')
    old = "r=user_for(u)\n  if r and secrets.compare_digest(h,r['password_hash']):"
    new = "with db(USERS) as c: r=c.execute('SELECT * FROM panel_users WHERE username=? AND active=1',(u,)).fetchone()\n  if r and secrets.compare_digest(h,r['password_hash']):"
    if old in text: text = text.replace(old, new, 1)
    p.write_text(text, encoding='utf-8')


def main():
    patch_bot(); patch_launcher(); patch_panel(); patch_panel_login()
    print('Snck KVM runtime repair applied.')

if __name__ == '__main__': main()
