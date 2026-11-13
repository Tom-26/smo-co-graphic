#!/usr/bin/env python3
"""Smo&Co scoreboard. Python 3.9+, standard library, loopback only."""
import argparse
import ipaddress
import copy
import json
import math
import os
import secrets
import signal
import threading
import time
import webbrowser
from collections import OrderedDict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent
MAX_BODY = 3_000_000
MAX_TIME = 99 * 60 + 59


def defaults():
    return dict(schema=1, revision=0, home=dict(name='СКА ПЕТЕРГОФ', score=0, color='#bbff32', logo=''),
                away=dict(name='ЗВЕЗДА ЮЗ', score=0, color='#73b9ff', logo=''), period='1',
                durationSec=1200, remainingMs=1200000, running=False, visible=True, promoStartedAtMs=int(time.time() * 1000), promoStartIndex=secrets.randbelow(2**31),
                penalties={'home': [], 'away': []}, brand='SMO&CO', caption='ХОККЕЙ • ПРЯМАЯ ТРАНСЛЯЦИЯ',
                playerAward=dict(visible=False, name='', number='', votes=0, photo='', title='ИГРОК МАТЧА'))


def integer(value, low, high):
    if type(value) is not int or not low <= value <= high:
        raise ValueError('Число вне допустимого диапазона')
    return value


def label(value, length):
    if not isinstance(value, str) or len(value) > length or any(ord(c) < 32 for c in value):
        raise ValueError('Некорректный текст')
    return value.strip()


def team(value):
    if not isinstance(value, dict):
        raise ValueError('Некорректная команда')
    name = label(value.get('name'), 48)
    if not name:
        raise ValueError('Укажите название команды')
    color = value.get('color', '')
    if len(color) != 7 or color[0] != '#' or any(c not in '0123456789abcdefABCDEF' for c in color[1:]):
        raise ValueError('Некорректный цвет')
    logo = value.get('logo', '')
    if not isinstance(logo, str) or len(logo) > 1_000_000:
        raise ValueError('Логотип слишком большой')
    if logo:
        import base64
        prefix = next((p for p in ('data:image/png;base64,', 'data:image/jpeg;base64,', 'data:image/webp;base64,') if logo.startswith(p)), None)
        if not prefix:
            raise ValueError('Логотип: используйте PNG, JPEG или WebP')
        try:
            raw = base64.b64decode(logo[len(prefix):], validate=True)
        except Exception as exc:
            raise ValueError('Повреждённый логотип') from exc
        if not raw:
            raise ValueError('Пустой логотип')
    return dict(name=name, score=integer(value.get('score'), 0, 99), color=color, logo=logo)


def penalties(value):
    if not isinstance(value, dict):
        raise ValueError('Некорректные удаления')
    result = {}
    ids = set()
    for side in ('home', 'away'):
        rows = value.get(side, [])
        if not isinstance(rows, list) or len(rows) > 2:
            raise ValueError('Можно показать до двух удалений на команду')
        result[side] = []
        for row in rows:
            if not isinstance(row, dict):
                raise ValueError('Некорректное удаление')
            ident = label(row.get('id'), 64)
            player = label(row.get('player', ''), 3)
            if not ident or ident in ids or (player and (not player.isascii() or not player.isdigit())):
                raise ValueError('Некорректный номер игрока или ID удаления')
            ids.add(ident)
            remaining = integer(row.get('remainingMs'), 0, MAX_TIME * 1000)
            if remaining > 0:
                result[side].append(dict(id=ident, player=player, remainingMs=remaining))
    return result


def player_award(value):
    if not isinstance(value, dict):
        raise ValueError('Некорректная графика игрока')
    visible = value.get('visible', False)
    if type(visible) is not bool:
        raise ValueError('Некорректная видимость графики')
    name = label(value.get('name', ''), 48)
    number = label(value.get('number', ''), 6)
    if number and (not number.isascii() or not number.isdigit()):
        raise ValueError('Номер игрока должен содержать только цифры')
    photo = value.get('photo', '')
    if not isinstance(photo, str) or len(photo) > 1_000_000:
        raise ValueError('Фотография слишком большая')
    if photo and not any(photo.startswith(prefix) for prefix in ('data:image/jpeg;base64,', 'data:image/png;base64,', 'data:image/webp;base64,')):
        raise ValueError('Фото игрока: используйте JPEG, PNG или WebP')
    if photo:
        import base64
        try:
            raw = base64.b64decode(photo.split(',', 1)[1], validate=True)
        except Exception as exc:
            raise ValueError('Повреждённая фотография') from exc
        if not raw:
            raise ValueError('Пустая фотография')
    title = label(value.get('title', 'ИГРОК МАТЧА'), 32) or 'ИГРОК МАТЧА'
    return dict(visible=visible, name=name, number=number, votes=integer(value.get('votes', 0), 0, 1_000_000), photo=photo, title=title)


def validate(value):
    if not isinstance(value, dict) or value.get('schema') != 1:
        raise ValueError('Неизвестный формат матча')
    out = defaults()
    out['home'], out['away'] = team(value.get('home')), team(value.get('away'))
    if value.get('period') not in ('1', '2', '3', 'OT', 'SO'):
        raise ValueError('Некорректный период')
    out['period'] = value['period']
    out['durationSec'] = integer(value.get('durationSec'), 1, MAX_TIME)
    out['remainingMs'] = integer(value.get('remainingMs'), 0, MAX_TIME * 1000)
    for key in ('visible', 'running'):
        if type(value.get(key)) is not bool:
            raise ValueError('Некорректный флаг')
        out[key] = value[key]
    stamp = value.get('promoStartedAtMs', out['promoStartedAtMs'])
    out['promoStartedAtMs'] = int(stamp) if isinstance(stamp, (int, float)) and math.isfinite(stamp) and 0 <= stamp <= time.time() * 1000 + 60000 else int(time.time() * 1000)
    start_index = value.get('promoStartIndex')
    out['promoStartIndex'] = start_index if type(start_index) is int and 0 <= start_index < 2**31 else secrets.randbelow(2**31)
    out['penalties'] = penalties(value.get('penalties', {'home': [], 'away': []}))
    out['playerAward'] = player_award(value.get('playerAward', defaults()['playerAward']))
    out['brand'] = label(value.get('brand'), 24)
    out['caption'] = label(value.get('caption'), 90)
    return out


class Store:
    def __init__(self, path):
        self.path = Path(path)
        self.lock = threading.Condition(threading.RLock())
        self.ids = OrderedDict()
        self.instance = secrets.token_urlsafe(16)
        self.state = defaults()
        self.deadline = None
        if self.path.exists():
            disk = json.loads(self.path.read_text(encoding='utf-8'))
            self.state = validate(disk)
            self.state['revision'] = integer(disk.get('revision', 0), 0, 2**53 - 1)
            if self.state['running']:
                until = disk.get('deadlineUnixMs')
                if not isinstance(until, (int, float)) or not math.isfinite(until):
                    raise ValueError('Повреждённое время в файле состояния')
                saved_remaining = self.state['remainingMs']
                self.state['remainingMs'] = max(0, min(MAX_TIME * 1000, math.ceil(until - time.time() * 1000)))
                elapsed = max(0, saved_remaining - self.state['remainingMs'])
                self.state['penalties'] = self.penalty_snapshot(elapsed)
                self.state['running'] = self.state['remainingMs'] > 0
        if self.state['running']:
            self.deadline = time.monotonic() + self.state['remainingMs'] / 1000
        self.persist()

    def remaining(self):
        return max(0, math.ceil((self.deadline - time.monotonic()) * 1000)) if self.deadline is not None else self.state['remainingMs']

    def penalty_snapshot(self, elapsed):
        return {side: [dict(p, remainingMs=max(0, p['remainingMs'] - elapsed))
                       for p in rows if p['remainingMs'] > elapsed]
                for side, rows in self.state['penalties'].items()}

    def settle(self):
        # Only elapsed playing time reduces penalties; clock corrections do not.
        remaining = self.remaining()
        elapsed = max(0, self.state['remainingMs'] - remaining) if self.deadline is not None else 0
        self.state['penalties'] = self.penalty_snapshot(elapsed)
        self.state['remainingMs'] = remaining

    def snapshot(self):
        with self.lock:
            out = copy.deepcopy(self.state)
            out['remainingMs'] = self.remaining()
            elapsed = max(0, self.state['remainingMs'] - out['remainingMs']) if self.deadline is not None else 0
            out['penalties'] = self.penalty_snapshot(elapsed)
            out['instanceId'] = self.instance
            out['serverNowMs'] = int(time.time() * 1000)
            return out

    def persist(self):
        data = self.snapshot()
        data['deadlineUnixMs'] = time.time() * 1000 + data['remainingMs'] if data['running'] else None
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp = self.path.with_suffix('.tmp')
        with temp.open('w', encoding='utf-8') as handle:
            json.dump(data, handle, ensure_ascii=False)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, self.path)

    def commit(self):
        self.state['revision'] += 1
        self.persist()
        self.lock.notify_all()

    def expire(self):
        with self.lock:
            if not self.state['running']:
                return
            elapsed = max(0, self.state['remainingMs'] - self.remaining())
            penalty_ended = any(p['remainingMs'] <= elapsed for rows in self.state['penalties'].values() for p in rows)
            if self.remaining() == 0 or penalty_ended:
                old, deadline = copy.deepcopy(self.state), self.deadline
                self.settle()
                if self.remaining() == 0:
                    self.state.update(running=False, remainingMs=0, promoStartedAtMs=int(time.time() * 1000), promoStartIndex=secrets.randbelow(2**31))
                    self.deadline = None
                try:
                    self.commit()
                except OSError:
                    self.state, self.deadline = old, deadline
                    raise

    def command(self, body):
        with self.lock:
            ident = body.get('id')
            if not isinstance(ident, str) or not 8 <= len(ident) <= 100:
                raise ValueError('Некорректный ID команды')
            if ident in self.ids:
                return self.snapshot()
            action = body.get('action')
            value = body.get('value')
            old, old_deadline = copy.deepcopy(self.state), self.deadline
            try:
                self.settle()
                if action == 'start':
                    if not self.state['running'] and self.remaining() > 0:
                        self.deadline = time.monotonic() + self.remaining() / 1000
                        self.state['running'] = True
                elif action == 'pause':
                    self.state.update(remainingMs=self.remaining(), running=False, promoStartedAtMs=int(time.time() * 1000), promoStartIndex=secrets.randbelow(2**31))
                    self.deadline = None
                elif action == 'set_time':
                    self.state.update(remainingMs=integer(value, 0, MAX_TIME) * 1000, running=False, promoStartedAtMs=int(time.time() * 1000), promoStartIndex=secrets.randbelow(2**31))
                    self.deadline = None
                elif action == 'adjust':
                    ms = max(0, min(MAX_TIME * 1000, self.remaining() + integer(value, -600, 600) * 1000))
                    self.state['remainingMs'] = ms
                    if self.state['running'] and ms > 0:
                        self.deadline = time.monotonic() + ms / 1000
                    else:
                        self.state['running'], self.deadline = False, None
                        self.state['promoStartedAtMs'] = int(time.time() * 1000)
                        self.state['promoStartIndex'] = secrets.randbelow(2**31)
                elif action == 'reset_clock':
                    self.state.update(remainingMs=self.state['durationSec'] * 1000, running=False, promoStartedAtMs=int(time.time() * 1000), promoStartIndex=secrets.randbelow(2**31))
                    self.deadline = None
                elif action == 'duration':
                    self.state['durationSec'] = integer(value, 1, MAX_TIME)
                elif action == 'score':
                    if not isinstance(value, dict) or value.get('side') not in ('home', 'away'):
                        raise ValueError('Неизвестная команда')
                    side = self.state[value['side']]
                    side['score'] = max(0, min(99, side['score'] + integer(value.get('delta'), -1, 1)))
                elif action == 'penalty_add':
                    if not isinstance(value, dict) or value.get('side') not in ('home', 'away'):
                        raise ValueError('Неизвестная команда')
                    rows = self.state['penalties'][value['side']]
                    if len(rows) >= 2:
                        raise ValueError('У команды уже два удаления. Снимите одно перед добавлением нового.')
                    player = label(value.get('player', ''), 3)
                    if player and (not player.isascii() or not player.isdigit()):
                        raise ValueError('Номер игрока: от 0 до 999, либо оставьте пустым')
                    duration = integer(value.get('durationSec'), 1, MAX_TIME)
                    rows.append(dict(id=secrets.token_hex(12), player=player, remainingMs=duration * 1000))
                elif action == 'penalty_remove':
                    if not isinstance(value, dict) or value.get('side') not in ('home', 'away'):
                        raise ValueError('Неизвестная команда')
                    rows = self.state['penalties'][value['side']]
                    ident = value.get('id')
                    if not any(p['id'] == ident for p in rows):
                        raise ValueError('Это удаление уже завершено или снято')
                    self.state['penalties'][value['side']] = [p for p in rows if p['id'] != ident]
                elif action == 'player_award':
                    self.state['playerAward'] = player_award(value)
                elif action == 'period':
                    if value not in ('1', '2', '3', 'OT', 'SO'):
                        raise ValueError('Некорректный период')
                    self.state['period'] = value
                elif action == 'visible':
                    if type(value) is not bool:
                        raise ValueError('Некорректная видимость')
                    if value is False and self.state['visible'] is True:
                        self.state['promoStartedAtMs'] = int(time.time() * 1000)
                        self.state['promoStartIndex'] = secrets.randbelow(2**31)
                    self.state['visible'] = value
                elif action == 'settings':
                    for side in ('home', 'away'):
                        self.state[side] = team(dict(value[side], score=self.state[side]['score']))
                    self.state['brand'] = label(value.get('brand'), 24)
                    self.state['caption'] = label(value.get('caption'), 90)
                    self.state['durationSec'] = integer(value.get('durationSec'), 1, MAX_TIME)
                elif action == 'new_match':
                    self.state['home']['score'] = self.state['away']['score'] = 0
                    self.state.update(period='1', running=False, remainingMs=self.state['durationSec'] * 1000, promoStartedAtMs=int(time.time() * 1000), penalties={'home': [], 'away': []}, playerAward=dict(visible=False, name='', number='', votes=0, photo='', title='ИГРОК МАТЧА'))
                    self.deadline = None
                elif action == 'import':
                    fresh = validate(value)
                    fresh.update(revision=self.state['revision'], running=False, promoStartedAtMs=int(time.time() * 1000), promoStartIndex=secrets.randbelow(2**31))
                    self.state, self.deadline = fresh, None
                else:
                    raise ValueError('Неизвестная команда')
                self.commit()
            except Exception:
                self.state, self.deadline = old, old_deadline
                raise
            self.ids[ident] = True
            while len(self.ids) > 2048:
                self.ids.popitem(last=False)
            return self.snapshot()


class Server(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True


class Handler(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'

    def log_message(self, *_):
        pass

    def allowed(self):
        host = self.headers.get('Host', '')
        if host in (f'127.0.0.1:{self.server.server_port}', f'localhost:{self.server.server_port}'):
            return True
        # Remote control is accepted only through the HTTPS ngrok tunnel started by our launcher.
        return bool(self.headers.get('X-Forwarded-For') and self.headers.get('X-Forwarded-Proto', '').lower() == 'https')

    def headers_out(self, status, mime, length=None):
        self.send_response(status)
        self.send_header('Content-Type', mime)
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'same-origin')
        self.send_header('Content-Security-Policy', "default-src 'self'; img-src 'self' data: blob:; style-src 'self' 'unsafe-inline'; script-src 'self'; connect-src 'self'; frame-ancestors 'self'; base-uri 'none'; form-action 'none'")
        if length is not None:
            self.send_header('Content-Length', str(length))
        self.end_headers()

    def reply(self, status, data):
        raw = json.dumps(data, ensure_ascii=False).encode()
        self.headers_out(status, 'application/json; charset=utf-8', len(raw))
        self.wfile.write(raw)

    def do_GET(self):
        if not self.allowed():
            return self.reply(403, {'error': 'Разрешён только localhost'})
        path = urlsplit(self.path).path
        if path == '/api/session':
            return self.reply(200, {'token': self.server.token})
        if path == '/api/state':
            return self.reply(200, self.server.store.snapshot())
        if path == '/api/events':
            self.headers_out(200, 'text/event-stream; charset=utf-8')
            self.connection.settimeout(5)
            try:
                while True:
                    # The condition is released before writing to a possibly slow client.
                    state = self.server.store.snapshot()
                    raw = json.dumps(state, ensure_ascii=False)
                    self.wfile.write(f'event: state\ndata: {raw}\n\n'.encode())
                    self.wfile.flush()
                    with self.server.store.lock:
                        if self.server.store.state['revision'] == state['revision']:
                            self.server.store.lock.wait(timeout=0.5)
            except (OSError, ValueError):
                pass
            self.close_connection = True
            return
        files = {'/': 'control.html', '/control.html': 'control.html', '/scoreboard.html': 'scoreboard.html',
                 '/app.js': 'app.js', '/style.css': 'style.css', '/overlay.js': 'overlay.js', '/control.js': 'control.js',
                 '/award.js': 'award.js', '/player.html': 'player.html'}
        name = files.get(path)
        if not name:
            return self.reply(404, {'error': 'Не найдено'})
        raw = (ROOT / name).read_bytes()
        mime = {'html': 'text/html', 'js': 'text/javascript', 'css': 'text/css'}[name.rsplit('.', 1)[1]]
        self.headers_out(200, mime + '; charset=utf-8', len(raw))
        self.wfile.write(raw)

    def do_POST(self):
        self.close_connection = True
        if not self.allowed():
            return self.reply(403, {'error': 'Разрешён только localhost'})
        origin = self.headers.get('Origin')
        if origin:
            forwarded_host = self.headers.get('X-Forwarded-Host', '')
            allowed_origins = {f'http://127.0.0.1:{self.server.server_port}', f'http://localhost:{self.server.server_port}'}
            if forwarded_host:
                allowed_origins.update((f'https://{forwarded_host}', f'http://{forwarded_host}'))
            if origin not in allowed_origins:
                return self.reply(403, {'error': 'Чужой источник'})
        if self.headers.get('X-Scoreboard-Token') != self.server.token:
            return self.reply(403, {'error': 'Обновите пульт'})
        if urlsplit(self.path).path != '/api/command':
            return self.reply(404, {'error': 'Не найдено'})
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if length < 1 or length > MAX_BODY:
                return self.reply(413, {'error': 'Слишком большой запрос'})
            self.connection.settimeout(5)
            body = json.loads(self.rfile.read(length))
            if not isinstance(body, dict):
                raise ValueError('Некорректный запрос')
            result = self.server.store.command(body)
            self.reply(200, result)
        except (ValueError, TypeError, KeyError) as exc:
            self.reply(400, {'error': str(exc) or 'Некорректный запрос'})
        except OSError:
            self.reply(500, {'error': 'Не удалось сохранить состояние на диск. Команда отменена.'})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--state', type=Path, default=ROOT / 'data' / 'state.json')
    parser.add_argument('--no-browser', action='store_true')
    args = parser.parse_args()
    server = None
    try:
        server = Server(('127.0.0.1', args.port), Handler)
        store = Store(args.state)
    except (OSError, ValueError, TypeError, KeyError) as exc:
        if server is not None:
            server.server_close()
        print(f'Ошибка запуска: {exc}\nПроверьте порт и data/state.json. Не удаляйте повреждённый файл без резервной копии.', flush=True)
        return 1
    server.store, server.token = store, secrets.token_urlsafe(32)
    stop = threading.Event()

    def ticker():
        while not stop.wait(0.05):
            try:
                store.expire()
            except OSError:
                print('Ошибка записи состояния: проверьте свободное место и права.', flush=True)

    def halt(*_):
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, halt)
    threading.Thread(target=ticker, daemon=True).start()
    url = f'http://127.0.0.1:{server.server_port}'
    print(f'\nSmo&Co — табло запущено\nПульт: {url}/control.html\nOBS:   {url}/scoreboard.html\n\nОстановить сервер: Ctrl+C. Оставьте это окно открытым.\n', flush=True)
    if not args.no_browser:
        webbrowser.open(url + '/control.html')
    try:
        server.serve_forever(poll_interval=0.2)
    except KeyboardInterrupt:
        print('\nСервер остановлен. Состояние сохранено.', flush=True)
    finally:
        stop.set()
        server.server_close()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
