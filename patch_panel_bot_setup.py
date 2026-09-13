#!/usr/bin/env python3
"""Patch the canonical Snck panel with a production Discord bot setup page.

The patch is intentionally tolerant of formatting differences in the generated
panel so installer updates do not fail just because route/import spacing changed.
"""
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parent
TARGET = ROOT / "snck_panel.py"

NEW_ROUTE = r"""@app.route('/bot',methods=['GET','POST'])
@admin_required
def bot():
    'Configure, verify and start the Discord bot from the panel.'
    if request.method == 'POST':
        token = request.form.get('token', '').strip()
        client_id = request.form.get('client_id', '').strip()
        guild_id = request.form.get('guild_id', '').strip()
        public_key = request.form.get('public_key', '').strip()
        if not token:
            flash('Enter a Discord bot token.')
            return redirect(url_for('bot'))
        try:
            response = requests.get(
                'https://discord.com/api/v10/oauth2/applications/@me',
                headers={'Authorization': f'Bot {token}', 'User-Agent': 'SnckBot/8.1'},
                timeout=15,
            )
            if response.status_code in (401, 403):
                flash('Discord rejected the bot token. Check the token and try again.')
                return redirect(url_for('bot'))
            response.raise_for_status()
            app_data = response.json()
        except requests.RequestException as exc:
            flash(f'Could not contact Discord: {str(exc)[:220]}')
            return redirect(url_for('bot'))
        detected_client_id = str(app_data.get('id') or '')
        bot_user = app_data.get('bot') or {}
        bot_name = app_data.get('name') or bot_user.get('username') or 'Discord Bot'
        if not detected_client_id:
            flash('Discord did not return an application ID.')
            return redirect(url_for('bot'))
        if client_id and client_id != detected_client_id:
            flash('Client ID does not match the supplied bot token.')
            return redirect(url_for('bot'))
        client_id = detected_client_id
        env = BASE / '.env'
        existing = {}
        if env.exists():
            for line in env.read_text().splitlines():
                if '=' in line and not line.lstrip().startswith('#'):
                    key, value = line.split('=', 1)
                    existing[key.strip()] = value
        existing['DISCORD_TOKEN'] = token
        existing['DISCORD_CLIENT_ID'] = client_id
        existing['DISCORD_GUILD_ID'] = guild_id
        if public_key:
            existing['DISCORD_PUBLIC_KEY'] = public_key
        existing.setdefault('BOT_NAME', 'Snck Discord VPS Deploy Bot')
        existing.setdefault('PREFIX', '!')
        env.write_text('\n'.join(f'{k}={v}' for k, v in existing.items()) + '\n')
        os.chmod(env, 0o600)
        os.environ['DISCORD_TOKEN'] = token
        os.environ['DISCORD_CLIENT_ID'] = client_id
        os.environ['DISCORD_GUILD_ID'] = guild_id
        if public_key:
            os.environ['DISCORD_PUBLIC_KEY'] = public_key
        try:
            if os.getenv('SNCK_CODESPACE') == '1':
                subprocess.run(['pkill', '-f', 'python.*launcher.py'], check=False,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                python_bin = BASE / '.venv' / 'bin' / 'python'
                if not python_bin.exists():
                    python_bin = BASE / 'venv' / 'bin' / 'python'
                log_dir = BASE / '.codespace'
                log_dir.mkdir(exist_ok=True)
                log = open(log_dir / 'bot.log', 'a')
                subprocess.Popen([str(python_bin), str(BASE / 'launcher.py')], cwd=str(BASE),
                                 stdout=log, stderr=log, start_new_session=True)
                status = 'starting'
            else:
                result = subprocess.run(['systemctl', 'restart', 'snck-discord-bot'],
                                        capture_output=True, text=True, timeout=20)
                if result.returncode != 0:
                    raise RuntimeError(result.stderr.strip() or 'systemd restart failed')
                status = 'restarted'
            flash(f'Discord bot verified as {bot_name} (Client ID {client_id}) and {status}.')
        except Exception as exc:
            flash(f'Bot credentials saved, but automatic start failed: {str(exc)[:240]}')
        return redirect(url_for('bot'))

    token_configured = bool(os.getenv('DISCORD_TOKEN', '').strip())
    client_id = os.getenv('DISCORD_CLIENT_ID', '').strip()
    guild_id = os.getenv('DISCORD_GUILD_ID', '').strip()
    bot_status = 'NOT CONFIGURED'
    if token_configured:
        try:
            if os.getenv('SNCK_CODESPACE') == '1':
                check = subprocess.run(['pgrep', '-f', 'python.*launcher.py'], capture_output=True)
                bot_status = 'ONLINE' if check.returncode == 0 else 'OFFLINE'
            else:
                check = subprocess.run(['systemctl', 'is-active', 'snck-discord-bot'], capture_output=True, text=True)
                bot_status = 'ONLINE' if check.stdout.strip() == 'active' else 'OFFLINE'
        except Exception:
            bot_status = 'UNKNOWN'
    invite = ''
    if client_id:
        invite = 'https://discord.com/oauth2/authorize?client_id=' + client_id + '&scope=bot%20applications.commands&permissions=8'
    invite_html = f'<p><a href="{html.escape(invite)}" target="_blank" rel="noopener">Open Discord Bot Invite</a></p>' if invite else ''
    status_class = 'ok' if bot_status == 'ONLINE' else 'bad' if bot_status == 'OFFLINE' else 'warn'
    body = f'''<div class="hero"><div class="title">Discord Bot</div><p class="muted">Connect, verify and start your Snck Discord VPS bot.</p></div>
<div class="grid"><div class="card stat"><div class="muted">Connection</div><div class="value {status_class}">{bot_status}</div></div><div class="card stat"><div class="muted">Application ID</div><div class="value">{html.escape(client_id or 'Not set')}</div></div></div>
<div class="card"><form method="post"><label>Bot Token</label><input type="password" name="token" autocomplete="new-password" placeholder="Paste your Discord bot token" required><label>Client / Application ID (optional)</label><input name="client_id" inputmode="numeric" value="{html.escape(client_id)}" placeholder="Auto-detected from token"><label>Guild / Server ID (optional)</label><input name="guild_id" inputmode="numeric" value="{html.escape(guild_id)}" placeholder="Your Discord server ID"><label>Public Key (optional)</label><input type="password" name="public_key" autocomplete="off" placeholder="Only needed for interaction webhooks"><div class="actions"><button>Verify and Start Bot</button></div></form><p class="muted small">The token is validated directly with Discord, stored only in the VPS .env file with restricted permissions, and never displayed back in the panel.</p>{invite_html}</div>'''
    return render_template_string(LAYOUT, title='Discord Bot', body=body)

"""


def patch():
    if not TARGET.exists():
        raise SystemExit(f"Missing target: {TARGET}")
    text = TARGET.read_text()

    if 'import requests' not in text:
        lines = text.splitlines()
        insert_at = 0
        for i, line in enumerate(lines):
            if line.startswith('import ') or line.startswith('from '):
                insert_at = i + 1
        lines.insert(insert_at, 'import requests')
        text = '\n'.join(lines) + ('\n' if text.endswith('\n') else '')

    pattern = re.compile(
        r"@app\.route\(\s*['\"]/?bot['\"][^\n]*\)\s*\n.*?(?=\n@app\.route\(\s*['\"]/?license-info['\"])",
        re.S,
    )
    match = pattern.search(text)
    if not match:
        start = re.search(r"@app\.route\(\s*['\"]/?bot['\"]", text)
        end = re.search(r"@app\.route\(\s*['\"]/?license-info['\"]", text)
        if not start or not end or start.start() >= end.start():
            raise SystemExit('Could not locate /bot and /license-info routes in canonical panel.')
        text = text[:start.start()] + NEW_ROUTE + '\n' + text[end.start():]
    else:
        text = text[:match.start()] + NEW_ROUTE + text[match.end():]

    TARGET.write_text(text)
    print('Snck Discord bot setup patch applied.')


if __name__ == '__main__':
    patch()
