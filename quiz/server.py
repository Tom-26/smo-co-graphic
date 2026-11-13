#!/usr/bin/env python3
"""Standalone commentator quiz console and OBS overlay. Python 3.9+."""
import json, os, re, secrets, threading, time, webbrowser, hashlib, io
from collections import deque
from urllib.request import Request, build_opener, HTTPRedirectHandler
from urllib.parse import parse_qs
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit, unquote

ROOT = Path(__file__).resolve().parent
PHOTO_IMPORT = ROOT.parent / 'import' / 'players.json'
STATE = ROOT / 'data' / 'quiz.json'
lock = threading.RLock()
token = secrets.token_urlsafe(32)
TEAMS = {key: {'label': f'КОМАНДА {i}', 'name': f'Команда {i}', 'accent': accent, 'players': []} for key, i, accent in [('team1', 1, 'red'), ('team2', 2, 'blue')]}

def create_photo_cutout(data):
    # Remove only light, low-chroma pixels connected to the image edge.
    # This is intentionally conservative: clothing and skin are not erased.
    from PIL import Image
    Image.MAX_IMAGE_PIXELS = 12000000
    with Image.open(io.BytesIO(data)) as original:
        original.load()
        image = original.convert('RGBA')
    image.thumbnail((800, 800), Image.Resampling.LANCZOS)
    w, h = image.size
    pixels = image.load()
    seen = bytearray(w*h)
    todo = deque()
    def offer(x, y):
        i=y*w+x
        if seen[i]: return
        seen[i]=1
        r,g,b,a=pixels[x,y]
        if min(r,g,b)>=215 and max(r,g,b)-min(r,g,b)<=36 and a:
            todo.append((x,y))
    for x in range(w): offer(x,0); offer(x,h-1)
    for y in range(h): offer(0,y); offer(w-1,y)
    while todo:
        x,y=todo.popleft(); r,g,b,a=pixels[x,y]
        # Preserve a gradual edge between pale subject pixels and the background.
        alpha=max(0,min(a,int((245-min(r,g,b))*255/30)))
        pixels[x,y]=(r,g,b,alpha)
        if x: offer(x-1,y)
        if x+1<w: offer(x+1,y)
        if y: offer(x,y-1)
        if y+1<h: offer(x,y+1)
    out=io.BytesIO(); image.save(out,format='PNG'); return out.getvalue()

class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs): return None

def validate_teams(value):
    if not isinstance(value, dict): raise ValueError('Проверьте составы команд')
    result = {}
    for key, i, accent in [('team1', 1, 'red'), ('team2', 2, 'blue')]:
        team = value.get(key)
        if not isinstance(team, dict) or not isinstance(team.get('name'), str) or not 1 <= len(team['name'].strip()) <= 60: raise ValueError('Введите название каждой команды')
        rows = team.get('players')
        if not isinstance(rows, list) or len(rows) > 30: raise ValueError('Допустимо до 30 игроков в команде')
        players = []
        for p in rows:
            if not isinstance(p, dict) or not isinstance(p.get('name'), str) or not 1 <= len(p['name'].strip()) <= 80: raise ValueError('Проверьте имя игрока')
            if type(p.get('number')) is not int or not 0 <= p['number'] <= 999: raise ValueError('Номер игрока должен быть от 0 до 999')
            position, photo = p.get('position', ''), p.get('photo_url', '')
            if not isinstance(position, str) or len(position) > 80 or not isinstance(photo, str) or len(photo) > 500 or (photo and not photo.startswith(('https://fhspb.ru/', 'https://rhlspb.ru/'))): raise ValueError('Проверьте позицию и ссылку на фото (fhspb.ru или rhlspb.ru)')
            players.append({'name': p['name'].strip(), 'number': p['number'], 'position': position.strip(), 'photo_url': photo.strip()})
        logo = team.get('logo_url', '')
        if not isinstance(logo, str) or (logo and not re.fullmatch(r'/logos/[0-9a-f]{32}\.(png|jpg|webp)', logo)): raise ValueError('Некорректный логотип команды')
        result[key] = {'label': f'КОМАНДА {i}', 'name': team['name'].strip(), 'accent': accent, 'players': players, 'logo_url': logo}
    return result

state = {'questions': [], 'index': 0, 'selected': -1, 'revealed': False, 'visible': False, 'revision': 0, 'display': 'none', 'vote': {'players': [], 'winner': -1}, 'teams': TEAMS, 'fans': {'team1': 0, 'team2': 0, 'name1': 'Красная машина', 'name2': 'Звезда ЮЗ'}, 'player': None, 'clip': None, 'roster_started_at': 0}

def validate_library(value):
    if not isinstance(value, list) or len(value) > 100: raise ValueError('Допустимо до 100 команд')
    result = []
    seen = set()
    for item in value:
        if not isinstance(item, dict) or not isinstance(item.get('id'), str) or not re.fullmatch(r'[a-zA-Z0-9_-]{1,64}', item['id']) or item['id'] in seen: raise ValueError('Некорректный идентификатор команды')
        seen.add(item['id'])
        team = validate_teams({'team1': item, 'team2': item})['team1']
        result.append({'id': item['id'], 'name': team['name'], 'players': team['players'], 'logo_url': team['logo_url']})
    return result

def initial_library(teams):
    return [{'id': 'existing' + str(i), 'name': teams['team'+str(i)]['name'], 'players': teams['team'+str(i)]['players'], 'logo_url': teams['team'+str(i)].get('logo_url','')} for i in (1, 2)]

state['team_library'] = initial_library(state['teams'])

def validate_tournament(value):
    if not isinstance(value, dict): raise ValueError('Проверьте таблицу')
    names = value.get('names')
    results = value.get('results')
    if not isinstance(names, list) or len(names) != 5 or any(not isinstance(n, str) or not 1 <= len(n.strip()) <= 40 for n in names): raise ValueError('Введите пять названий команд (до 40 символов)')
    if not isinstance(results, dict): raise ValueError('Проверьте результаты')
    clean = {}
    for i in range(5):
        for j in range(i + 1, 5):
            key = f'{i}-{j}'; winner = results.get(key, -1)
            if type(winner) is not int or winner not in (-1, i, j): raise ValueError('Выберите победителя пары')
            clean[key] = winner
    points = value.get('points_per_win', 2)
    if type(points) is not int or not 0 <= points <= 10: raise ValueError('Очки за победу: от 0 до 10')
    return {'names': [n.strip() for n in names], 'results': clean, 'points_per_win': points}

DEFAULT_TOURNAMENT = {'names': [f'Команда {i}' for i in range(1, 6)], 'results': {}}
state['tournament'] = DEFAULT_TOURNAMENT

def validate_fans(value):
    if not isinstance(value, dict): raise ValueError('Введите количество болельщиков')
    counts = {}
    for team in ('team1', 'team2'):
        count = value.get(team)
        if type(count) is not int or not 0 <= count <= 1000000: raise ValueError('Количество болельщиков должно быть от 0 до 1000000')
        counts[team] = count
    for key, default in (('name1', 'Красная машина'), ('name2', 'Звезда ЮЗ')):
        name = value.get(key, default)
        if not isinstance(name, str) or not name.strip() or len(name.strip()) > 60: raise ValueError('Введите название каждой команды (до 60 символов)')
        counts[key] = name.strip()
    return counts

def validate_vote(value):
    if not isinstance(value, dict) or not isinstance(value.get('players'), list) or len(value['players']) > 8: raise ValueError('Допустимо до 8 игроков')
    players = []
    for row in value['players']:
        if not isinstance(row, dict) or not isinstance(row.get('name'), str) or not row['name'].strip() or len(row['name'].strip()) > 80: raise ValueError('Введите имя игрока длиной до 80 символов')
        votes = row.get('votes')
        if type(votes) is not int or not 0 <= votes <= 1000000: raise ValueError('Число голосов должно быть от 0 до 1000000')
        players.append({'name': row['name'].strip(), 'votes': votes})
    winner = value.get('winner', -1)
    if type(winner) is not int or not -1 <= winner < len(players): raise ValueError('Выберите игрока из списка')
    return {'players': players, 'winner': winner}

def validate_question(q):
    if not isinstance(q, dict): raise ValueError('Некорректный вопрос')
    title = q.get('title', '').strip() if isinstance(q.get('title'), str) else ''
    opts = q.get('options')
    if not title or len(title) > 180: raise ValueError('Введите вопрос длиной до 180 символов')
    if not isinstance(opts, list) or not 2 <= len(opts) <= 6 or any(not isinstance(x, str) or not x.strip() or len(x.strip()) > 100 for x in opts):
        raise ValueError('Нужно от 2 до 6 вариантов, до 100 символов каждый')
    correct = q.get('correct')
    if type(correct) is not int or not 0 <= correct < len(opts): raise ValueError('Выберите правильный ответ')
    return {'title': title, 'options': [x.strip() for x in opts], 'correct': correct}

def restore_missing_photos(teams, library):
    # Only restore unambiguous matches; existing photos and other fields are untouched.
    try:
        source = json.loads(PHOTO_IMPORT.read_text(encoding='utf-8'))
        candidates = {}
        for row in source.get('players', []):
            if not isinstance(row, dict): continue
            name, number, photo = row.get('player_name'), row.get('number'), row.get('photo_url')
            if not isinstance(name, str) or type(number) is not int or not isinstance(photo, str) or not photo.startswith(('https://fhspb.ru/', 'https://rhlspb.ru/')): continue
            candidates.setdefault((name.strip().casefold(), number), set()).add(photo)
        for team in list(teams.values()) + library:
            for player in team['players']:
                photos = candidates.get((player['name'].strip().casefold(), player['number']), set())
                if not player.get('photo_url') and len(photos) == 1: player['photo_url'] = next(iter(photos))
    except (OSError, ValueError, TypeError, AttributeError):
        pass

def validate(saved):
    if not isinstance(saved, dict): raise ValueError('Некорректный файл квиза')
    questions = saved.get('questions', [])
    if not isinstance(questions, list) or len(questions) > 100: raise ValueError('Слишком много вопросов')
    questions = [validate_question(q) for q in questions]
    index = saved.get('index', 0); selected = saved.get('selected', -1)
    if type(index) is not int or not (0 <= index < max(1, len(questions))): raise ValueError('Некорректный номер вопроса')
    if type(selected) is not int or not -1 <= selected < (len(questions[index]['options']) if questions else 0): raise ValueError('Некорректный выбранный ответ')
    if any(type(saved.get(k, False)) is not bool for k in ('visible', 'revealed')): raise ValueError('Некорректное состояние')
    vote = validate_vote(saved.get('vote', {'players': [], 'winner': -1}))
    fans = validate_fans(saved.get('fans', {'team1': 0, 'team2': 0}))
    teams = validate_teams(saved.get('teams', TEAMS))
    player = saved.get('player')
    library = validate_library(saved.get('team_library', initial_library(teams)))
    restore_missing_photos(teams, library)
    if isinstance(player, dict) and 'library_id' in player:
        team = next ( (t for t in library if t['id'] == player['library_id']), None)
        if not team or type(player.get('index')) is not int or not 0 <= player['index'] < len(team['players']): player = None
    else:
        if not isinstance(player, dict) or player.get('team') not in TEAMS or type(player.get('index')) is not int or not 0 <= player['index'] < len(teams[player['team']]['players']): player = None
    clip = saved.get('clip')
    if not isinstance(clip, dict) or not isinstance(clip.get('file'), str) or not re.fullmatch(r'[0-9a-f]{32}\.(mp4|webm)', clip['file']): clip = None
    display = saved.get('display', 'quiz' if saved.get('visible',False) and questions else 'none')
    if display not in ('none','quiz','vote','winner','team1','team2','fans','player','clip','tournament'): raise ValueError('Некорректный режим эфира')
    if display == 'clip': display = 'none'  # Не запускать видео автоматически после перезапуска.
    if display == 'player' and player is None: display = 'none'
    if (display == 'quiz' and not questions) or (display == 'vote' and not vote['players']) or (display == 'winner' and vote['winner'] < 0): display = 'none'
    return {'questions': questions, 'index': index, 'selected': selected, 'revealed': saved.get('revealed',False), 'visible': display == 'quiz', 'revision': 0, 'display': display, 'vote': vote, 'teams': teams, 'fans': fans, 'player': player, 'clip': clip, 'roster_started_at': time.time() if display in ('team1', 'team2') else 0, 'tournament': validate_tournament(saved.get('tournament', DEFAULT_TOURNAMENT)), 'team_library': library}

def persist():
    STATE.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATE.with_suffix('.tmp')
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding='utf-8')
    os.replace(tmp, STATE)

def update(body):
    global state
    with lock:
        old = state.copy(); state = state.copy(); state['questions'] = state['questions'].copy()
        try:
            action, value = body.get('action'), body.get('value')
            if action == 'library_save':
                state['team_library'] = validate_library(value)
                if state.get('player') and 'library_id' in state['player']:
                    state['player'] = None
                    if state['display'] == 'player': state['display'] = 'none'
            elif action == 'tournament_save':
                state['tournament'] = validate_tournament(value)
            elif action == 'tournament_display':
                if type(value) is not bool: raise ValueError('Некорректный режим')
                if value: state.update(display='tournament', visible=False)
                elif state['display'] == 'tournament': state['display'] = 'none'
            elif action == 'teams_save':
                state['teams'] = validate_teams(value)
                state['player'] = None
                if state['display'] == 'player': state['display'] = 'none'
                state['fans'] = dict(state['fans'], name1=state['teams']['team1']['name'], name2=state['teams']['team2']['name'])
            elif action == 'save':
                q = validate_question(value.get('question')); idx = value.get('index')
                if idx is None:
                    if len(state['questions']) >= 100: raise ValueError('Максимум 100 вопросов')
                    state['questions'].append(q); state['index'] = len(state['questions'])-1
                elif type(idx) is int and 0 <= idx < len(state['questions']):
                    state['questions'][idx] = q; state['index'] = idx
                else: raise ValueError('Вопрос не найден')
                state.update(selected=-1, revealed=False)
            elif action == 'navigate':
                if type(value) is not int or not 0 <= value < len(state['questions']): raise ValueError('Вопрос не найден')
                state.update(index=value, selected=-1, revealed=False)
            elif action == 'select':
                if not state['questions'] or type(value) is not int or not 0 <= value < len(state['questions'][state['index']]['options']): raise ValueError('Ответ не найден')
                if state['revealed']: raise ValueError('Ответ уже открыт. Сначала сбросьте выбор.')
                state['selected'] = value
            elif action == 'reveal':
                if not state['questions']: raise ValueError('Добавьте вопрос')
                state['revealed'] = True
            elif action == 'reset': state.update(selected=-1, revealed=False)
            elif action == 'visible':
                if type(value) is not bool or (value and not state['questions']): raise ValueError('Добавьте вопрос перед показом')
                state['visible'] = value
                state['display'] = 'quiz' if value else 'none'
            elif action == 'vote_save':
                state['vote'] = validate_vote(value)
                if state.get('display') == 'winner' and state['vote']['winner'] < 0: state['display'] = 'none'
                if state.get('display') == 'vote' and not state['vote']['players']: state['display'] = 'none'
            elif action == 'vote_display':
                if value not in ('none', 'vote', 'winner'): raise ValueError('Некорректный режим эфира')
                vote = state.get('vote', {'players': [], 'winner': -1})
                if value == 'vote' and len(vote['players']) < 2: raise ValueError('Добавьте минимум двух игроков')
                if value == 'winner' and vote['winner'] < 0: raise ValueError('Выберите победителя')
                state['display'] = value
                state['visible'] = False
            elif action == 'clip_display':
                if value is False:
                    if state.get('display') == 'clip': state['display'] = 'none'
                elif isinstance(value, str) and re.fullmatch(r'[0-9a-f]{32}\.(mp4|webm)', value) and (ROOT / 'data' / 'videos' / value).is_file():
                    state['clip'] = {'file': value, 'play_id': secrets.token_hex(16)}
                    state['display'] = 'clip'
                    state['visible'] = False
                else: raise ValueError('Сначала загрузите видео')
            elif action == 'player_display':
                if value is False:
                    state['display'] = 'none'
                elif isinstance(value, dict) and isinstance(value.get('library_id'), str):
                    team = next((t for t in state['team_library'] if t['id'] == value['library_id']), None)
                    if not team or type(value.get('index')) is not int or not 0 <= value['index'] < len(team['players']): raise ValueError('Выберите игрока')
                    state['player'] = {'library_id': team['id'], 'index': value['index']}
                    state['display'] = 'player'
                elif isinstance(value, dict) and value.get('team') in TEAMS and type(value.get('index')) is int and 0 <= value['index'] < len(state['teams'][value['team']]['players']):
                    state['player'] = {'team': value['team'], 'index': value['index']}
                    state['display'] = 'player'
                else: raise ValueError('Выберите игрока')
                state['visible'] = False
            elif action == 'fans_display':
                if value is False:
                    state['display'] = 'none'
                else:
                    state['fans'] = validate_fans(value)
                    state['display'] = 'fans'
                state['visible'] = False
            elif action == 'roster_display':
                if value not in ('none', 'team1', 'team2'): raise ValueError('Выберите команду для показа')
                state['roster_started_at'] = time.time() if value != 'none' else 0
                state['display'] = value
                state['visible'] = False
            elif action == 'delete':
                if not state['questions']: raise ValueError('Вопрос не найден')
                state['questions'].pop(state['index']); state.update(index=min(state['index'], max(0,len(state['questions'])-1)),selected=-1,revealed=False)
                if not state['questions']:
                    state['visible'] = False
                    if state.get('display') == 'quiz': state['display'] = 'none'
            else: raise ValueError('Неизвестная команда')
            state['revision'] += 1; persist(); return state.copy()
        except Exception:
            state = old; raise

class Server(ThreadingHTTPServer): daemon_threads = True; allow_reuse_address = True
class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args): pass
    def output(self, status, content, mime):
        self.send_response(status); self.send_header('Content-Type',mime); self.send_header('Content-Length',str(len(content))); self.send_header('Cache-Control','no-store'); self.send_header('X-Content-Type-Options','nosniff'); self.send_header('Content-Security-Policy',"default-src 'self'; style-src 'self'; script-src 'self'; connect-src 'self'; img-src 'self' https://fhspb.ru https://rhlspb.ru data:; media-src 'self'; base-uri 'none'; form-action 'none'"); self.end_headers(); self.wfile.write(content)
    def allowed(self):
        host=self.headers.get('Host','')
        if host in (f'localhost:{self.server.server_port}',f'127.0.0.1:{self.server.server_port}'): return True
        return bool(self.headers.get('X-Forwarded-For') and self.headers.get('X-Forwarded-Proto','').lower() == 'https')
    def json(self, code, obj): self.output(code,json.dumps(obj,ensure_ascii=False).encode(),'application/json; charset=utf-8')
    def do_GET(self):
        if not self.allowed(): return self.json(403,{'error':'Только локальный доступ'})
        path=urlsplit(self.path).path
        if path == '/api/player-cutout':
            query = parse_qs(urlsplit(self.path).query)
            url = query.get('url', [''])[0]
            with lock:
                teams = list(state.get('teams', {}).values()) + state.get('team_library', [])
                permitted = any(p.get('photo_url') == url for t in teams for p in t.get('players', []))
            parsed = urlsplit(url)
            if not permitted or parsed.scheme != 'https' or parsed.netloc not in ('rhlspb.ru', 'fhspb.ru'):
                return self.json(404, {'error':'Фото не найдено'})
            try:
                key=hashlib.sha256(url.encode()).hexdigest()
                folder=ROOT/'data'/'photo-cutouts'; target=folder/(key+'.png')
                if target.is_file(): return self.output(200,target.read_bytes(),'image/png')
                request=Request(url, headers={'User-Agent':'Mozilla/5.0'})
                with build_opener(NoRedirect()).open(request, timeout=8) as response:
                    data=response.read(8*1024*1024+1)
                    if len(data)>8*1024*1024: raise ValueError('Фото слишком большое')
                cutout=create_photo_cutout(data)
                folder.mkdir(parents=True,exist_ok=True)
                tmp=folder/(key+'.'+secrets.token_hex(8)+'.tmp')
                try:
                    tmp.write_bytes(cutout); os.replace(tmp,target)
                finally: tmp.unlink(missing_ok=True)
                return self.output(200,cutout,'image/png')
            except Exception:
                return self.json(404, {'error':'Не удалось обработать фото'})
        if path.startswith('/logos/'):
            name = path.removeprefix('/logos/')
            if not re.fullmatch(r'[0-9a-f]{32}\.(png|jpg|webp)', name): return self.json(404, {'error':'Не найдено'})
            file = ROOT / 'data' / 'logos' / name
            if not file.is_file(): return self.json(404, {'error':'Не найдено'})
            try: return self.output(200, file.read_bytes(), {'png':'image/png','jpg':'image/jpeg','webp':'image/webp'}[name.rsplit('.',1)[1]])
            except OSError: return self.json(404, {'error':'Не найдено'})
        if path.startswith('/media/'):
            name = path.removeprefix('/media/')
            if not re.fullmatch(r'[0-9a-f]{32}\.(mp4|webm)', name): return self.json(404, {'error':'Не найдено'})
            file = ROOT / 'data' / 'videos' / name
            if not file.is_file(): return self.json(404, {'error':'Не найдено'})
            size=file.stat().st_size; start=0; end=size-1; status=200
            r=self.headers.get('Range')
            if r:
                match=re.fullmatch(r'bytes=(\d+)-(\d*)', r)
                if not match or int(match.group(1))>=size:
                    self.send_response(416); self.send_header('Content-Range',f'bytes */{size}'); self.end_headers(); return
                start=int(match.group(1)); end=min(int(match.group(2)) if match.group(2) else end,end); status=206
                if end < start: self.send_error(416); return
            self.send_response(status); self.send_header('Content-Type','video/mp4' if name.endswith('.mp4') else 'video/webm'); self.send_header('Accept-Ranges','bytes'); self.send_header('Content-Length',str(end-start+1)); self.send_header('Cache-Control','no-store')
            if status==206: self.send_header('Content-Range',f'bytes {start}-{end}/{size}')
            self.end_headers()
            with file.open('rb') as f:
                f.seek(start); remaining=end-start+1
                while remaining:
                    chunk=f.read(min(65536,remaining))
                    if not chunk: break
                    try: self.wfile.write(chunk)
                    except (BrokenPipeError,ConnectionResetError): break
                    remaining-=len(chunk)
            return
        if path == '/api/clips':
            folder = ROOT / 'data' / 'videos'
            rows = []
            if folder.exists():
                for f in sorted(folder.iterdir(), key=lambda f: f.stat().st_mtime, reverse=True):
                    if not f.is_file() or not re.fullmatch(r'[0-9a-f]{32}\.(mp4|webm)', f.name): continue
                    meta = f.with_suffix(f.suffix + '.name')
                    try: name = meta.read_text(encoding='utf-8') if meta.is_file() else 'Ранее загруженное видео · ' + f.name[:8]
                    except (OSError, UnicodeError): name = 'Видео · ' + f.name[:8]
                    rows.append({'file': f.name, 'name': name})
            return self.json(200, rows)
        if path == '/cup-background.png': return self.output(200, (ROOT / 'cup-background.png').read_bytes(), 'image/png')
        if path == '/api/session': return self.json(200,{'token':token})
        if path == '/api/state':
            with lock: return self.json(200,state)
        files={'/':'control.html','/control.html':'control.html','/overlay.html':'overlay.html','/style.css':'style.css','/control.js':'control.js','/overlay.js':'overlay.js','/teams.html':'teams.html','/teams.js':'teams.js','/standings.js':'standings.js','/tournament.html':'tournament.html','/tournament.js':'tournament.js','/players.html':'players.html','/players.js':'players.js'}
        if path not in files: return self.json(404,{'error':'Не найдено'})
        name=files[path]; return self.output(200,(ROOT/name).read_bytes(),{'html':'text/html','css':'text/css','js':'text/javascript'}[name.rsplit('.',1)[1]]+'; charset=utf-8')
    def do_POST(self):
        origin=self.headers.get('Origin')
        forwarded_host=self.headers.get('X-Forwarded-Host','')
        allowed_origins=(None, f'http://127.0.0.1:{self.server.server_port}', f'http://localhost:{self.server.server_port}', f'https://{forwarded_host}', f'http://{forwarded_host}')
        if not self.allowed() or self.headers.get('X-Quiz-Token') != token or origin not in allowed_origins: return self.json(403,{'error':'Нет доступа'})
        if urlsplit(self.path).path == '/api/logo-upload':
            try:
                length=int(self.headers.get('Content-Length','0')); mime=self.headers.get('Content-Type','').split(';')[0].lower()
                if not 0 < length <= 2*1024*1024: return self.json(400,{'error':'Логотип должен быть не больше 2 МБ'})
                data=self.rfile.read(length)
                if len(data) != length: raise ValueError('Загрузка прервалась')
                if mime == 'image/png' and data.startswith(b'\x89PNG\r\n\x1a\n'): ext='png'
                elif mime == 'image/jpeg' and data.startswith(b'\xff\xd8\xff'): ext='jpg'
                elif mime == 'image/webp' and data.startswith(b'RIFF') and data[8:12] == b'WEBP': ext='webp'
                else: return self.json(400,{'error':'Выберите PNG, JPEG или WebP'})
                folder=ROOT/'data'/'logos'; folder.mkdir(parents=True,exist_ok=True)
                name=secrets.token_hex(16)+'.'+ext
                (folder/name).write_bytes(data)
                return self.json(200,{'logo_url':'/logos/'+name})
            except (OSError,ValueError): return self.json(400,{'error':'Не удалось загрузить логотип'})
        if urlsplit(self.path).path == '/api/clip-upload':
            try:
                length=int(self.headers.get('Content-Length','0')); mime=self.headers.get('Content-Type','').split(';')[0].lower()
                ext={'video/mp4':'mp4','video/webm':'webm'}.get(mime)
                if not ext or not 0 < length <= 100*1024*1024: return self.json(400,{'error':'Нужен MP4 или WebM до 100 МБ'})
                folder=ROOT/'data'/'videos'; folder.mkdir(parents=True,exist_ok=True)
                name=secrets.token_hex(16)+'.'+ext; target=folder/name
                try:
                    with target.open('wb') as out:
                        remaining=length
                        while remaining:
                            chunk=self.rfile.read(min(65536,remaining))
                            if not chunk: raise ValueError('Загрузка прервалась')
                            out.write(chunk); remaining-=len(chunk)
                except Exception:
                    target.unlink(missing_ok=True); raise
                label=unquote(self.headers.get('X-Clip-Name', 'Видео'))[:200].replace('\n',' ').replace('\r',' ').strip() or 'Видео'
                try: target.with_suffix(target.suffix + '.name').write_text(label, encoding='utf-8')
                except OSError:
                    target.unlink(missing_ok=True); raise
                return self.json(200,{'file':name,'name':label})
            except (OSError,ValueError): return self.json(400,{'error':'Не удалось загрузить видео'})
        if urlsplit(self.path).path != '/api/command': return self.json(404,{'error':'Не найдено'})
        try:
            length=int(self.headers.get('Content-Length','0'))
            if not 0 < length <= 50000: raise ValueError('Некорректный размер запроса')
            body=json.loads(self.rfile.read(length)); return self.json(200,update(body))
        except (ValueError,TypeError,KeyError,AttributeError) as e: return self.json(400,{'error':str(e)})
        except OSError: return self.json(500,{'error':'Не удалось сохранить квиз'})

def main():
    global state
    import argparse
    p=argparse.ArgumentParser(); p.add_argument('--port',type=int,default=8770); p.add_argument('--no-browser',action='store_true'); p.add_argument('--host', default='127.0.0.1'); args=p.parse_args()
    if STATE.exists(): state=validate(json.loads(STATE.read_text(encoding='utf-8')))
    server=Server((args.host,args.port),Handler); url=f'http://127.0.0.1:{server.server_port}'
    print(f'Пульт комментатора: {url}/control.html\nИсточник OBS: {url}/overlay.html\nОставьте это окно открытым.',flush=True)
    if not args.no_browser: webbrowser.open(url+'/control.html')
    try: server.serve_forever()
    except KeyboardInterrupt: pass
    finally: server.server_close()
if __name__=='__main__': main()
