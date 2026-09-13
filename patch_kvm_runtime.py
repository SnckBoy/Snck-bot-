#!/usr/bin/env python3
"""Repair the installed Snck runtime so panel and Discord use the same KVM path."""
from pathlib import Path
import re

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


def replace_once(text: str, old: str, new: str, label: str, required: bool = False) -> str:
    if old not in text:
        if required:
            raise SystemExit(f'Could not locate {label}')
        return text
    return text.replace(old, new, 1)


def patch_bot():
    p = ROOT / 'bot.py'
    if not p.exists():
        raise SystemExit('Missing bot.py')
    text = p.read_text(encoding='utf-8')
    pattern = r"@bot\.command\(name=['\"]deploy['\"]\).*?(?=\n@bot\.(?:command|event)\b|\Z)"
    if re.search(pattern, text, re.S):
        text = re.sub(pattern, BOT_ROUTE.rstrip(), text, count=1, flags=re.S)
    else:
        raise SystemExit('Could not locate deploy command in bot.py')
    p.write_text(text, encoding='utf-8')


def patch_launcher():
    p = ROOT / 'launcher.py'
    if not p.exists():
        raise SystemExit('Missing launcher.py')
    text = p.read_text(encoding='utf-8')
    marker = 'mod._do_free_deploy=free_deploy'
    binding = 'mod.bot._snck_kvm_deploy=free_deploy'
    if binding not in text:
        if marker not in text:
            raise SystemExit('Could not locate KVM deploy handler in launcher.py')
        text = text.replace(marker, marker + '\n ' + binding, 1)
    p.write_text(text, encoding='utf-8')


def patch_panel():
    p = ROOT / 'snck_panel.py'
    if not p.exists():
        raise SystemExit('Missing snck_panel.py')
    text = p.read_text(encoding='utf-8')

    # Panel v2 stores the node connection field as `uri`, while the Discord
    # database schema historically calls it `url`. Use either without raising
    # KeyError, and keep deployment image selection deterministic.
    old = "pw=secrets.token_urlsafe(12);vm_create=name,ram,cpu,disk,pw\n   from kvm import create as real_create;real_create(name,ram,cpu,disk,pw,storage=n['storage'],uri=n['url']);real_start= start;real_start(name,n['url'])"
    new = "pw=secrets.token_urlsafe(12);node_uri=str(n['uri'] if 'uri' in n.keys() else (n['url'] if 'url' in n.keys() else '') or '');osver=request.form.get('os_version','ubuntu:24.04').strip() or 'ubuntu:24.04'\n   from kvm import create as real_create;real_create(name,ram,cpu,disk,pw,image={'ubuntu:20.04':'https://cloud-images.ubuntu.com/focal/current/focal-server-cloudimg-amd64.img','ubuntu:22.04':'https://cloud-images.ubuntu.com/jammy/current/jammy-server-cloudimg-amd64.img','ubuntu:24.04':'https://cloud-images.ubuntu.com/noble/current/noble-server-cloudimg-amd64.img'}.get(osver,'https://cloud-images.ubuntu.com/noble/current/noble-server-cloudimg-amd64.img'),storage=n['storage'],uri=node_uri);start(name,node_uri)"
    if old in text:
        text = text.replace(old, new, 1)
    else:
        # Handle the already-patched/simple variant as well.
        text = text.replace("uri=n['url'] or ''", "uri=str(n['uri'] if 'uri' in n.keys() else (n['url'] if 'url' in n.keys() else '') or '')", 1)
        text = text.replace("uri=n['url']", "uri=str(n['uri'] if 'uri' in n.keys() else (n['url'] if 'url' in n.keys() else '') or '')", 1)
        text = text.replace("start(name,n['url'] or '')", "start(name,str(n['uri'] if 'uri' in n.keys() else (n['url'] if 'url' in n.keys() else '') or ''))", 1)
    p.write_text(text, encoding='utf-8')


def patch_panel_login():
    p = ROOT / 'snck_panel.py'
    if not p.exists():
        raise SystemExit('Missing snck_panel.py')
    text = p.read_text(encoding='utf-8')
    old = "r=user_for(u)\n  if r and secrets.compare_digest(h,r['password_hash']):"
    new = "with db(USERS) as c: r=c.execute('SELECT * FROM panel_users WHERE username=? AND active=1',(u,)).fetchone()\n  if r and secrets.compare_digest(h,r['password_hash']):"
    if old in text:
        text = text.replace(old, new, 1)
    p.write_text(text, encoding='utf-8')


def main():
    patch_bot()
    patch_launcher()
    patch_panel()
    patch_panel_login()
    print('Snck KVM runtime repair applied.')


if __name__ == '__main__':
    main()
