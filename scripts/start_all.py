#!/usr/bin/env python3
"""Start the commentator console and optionally expose it over ngrok."""
import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(line_buffering=True)


def free_port(start):
    for port in range(start, start + 100):
        with socket.socket() as sock:
            try:
                sock.bind(('127.0.0.1', port))
                return port
            except OSError:
                continue
    raise RuntimeError(f'Не найден свободный порт рядом с {start}')


def local_ip():
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(('192.0.2.1', 9))
            return sock.getsockname()[0]
    except OSError:
        return '127.0.0.1'


def ngrok_config_path(executable):
    result = subprocess.run([executable, 'config', 'check'], capture_output=True, text=True)
    if result.returncode:
        return None
    marker = 'Valid configuration file at '
    for line in (result.stdout + result.stderr).splitlines():
        if marker in line:
            path = Path(line.split(marker, 1)[1].strip())
            return path if path.is_file() else None
    return None


def tunnel_urls(api_port, wanted_ports, process):
    url = f'http://127.0.0.1:{api_port}/api/tunnels'
    until = time.monotonic() + 45
    while time.monotonic() < until:
        if process.poll() is not None:
            raise RuntimeError('ngrok завершился. Проверьте аккаунт и настройки ngrok.')
        try:
            with urllib.request.urlopen(url, timeout=1) as response:
                rows = json.load(response).get('tunnels', [])
            found = {}
            for row in rows:
                addr = str(row.get('config', {}).get('addr', ''))
                for port in wanted_ports:
                    if addr.endswith(':' + str(port)) and row.get('public_url', '').startswith('https://'):
                        found[port] = row['public_url']
            if len(found) == len(wanted_ports):
                return found
        except (OSError, ValueError, urllib.error.URLError):
            pass
        time.sleep(.5)
    raise RuntimeError('ngrok запущен, но ссылки не появились за 45 секунд.')


def stop_all(processes):
    for process in processes:
        if process.poll() is None:
            process.terminate()
    for process in processes:
        if process.poll() is None:
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()


def main():
    python = sys.executable
    quiz_port = free_port(18770)
    quiz_dir = ROOT / 'quiz'
    (quiz_dir / 'data').mkdir(parents=True, exist_ok=True)
    processes = []
    tempdir = None
    try:
        quiz = subprocess.Popen([python, str(quiz_dir / 'server.py'), '--port', str(quiz_port), '--no-browser'])
        processes.append(quiz)
        time.sleep(.8)
        if quiz.poll() is not None:
            raise RuntimeError('Не удалось запустить пульт комментатора; смотрите сообщение выше.')
        quiz_local = f'http://127.0.0.1:{quiz_port}'
        print('\nSmo&Co: пульт комментатора запущен.')
        print(f'Графика для OBS на этом компьютере: {quiz_local}/overlay.html')
        print('Пульт комментатора на этом компьютере: ' + quiz_local + '/control.html')

        use_ngrok = '--ngrok' in sys.argv[1:]
        ngrok = shutil.which('ngrok') if use_ngrok else None
        default_config = ngrok_config_path(ngrok) if ngrok else None
        if not use_ngrok:
            print('Локальный режим: подключение через ngrok не требуется.')
        elif not ngrok:
            print('\nУдалённый доступ не включён: установите ngrok и настройте аккаунт.')
        elif not default_config:
            print('\nУдалённый доступ не включён: настройте ngrok один раз командой ngrok config add-authtoken ВАШ_ТОКЕН.')
        else:
            api_port = free_port(4040)
            tempdir = tempfile.TemporaryDirectory(prefix='smo-ngrok-')
            config_path = Path(tempdir.name) / 'endpoints.json'
            config = {
                'version': '3',
                'agent': {'web_addr': f'127.0.0.1:{api_port}'},
                'endpoints': [
                    {
                        'name': 'smo-quiz',
                        'upstream': {'url': f'127.0.0.1:{quiz_port}'},
                    },
                ],
            }
            config_path.write_text(json.dumps(config, ensure_ascii=False), encoding='utf-8')
            config_path.chmod(0o600)
            tunnel = subprocess.Popen([ngrok, 'start', 'smo-quiz', '--config', str(default_config), '--config', str(config_path)], stdout=None, stderr=None)
            processes.append(tunnel)
            try:
                urls = tunnel_urls(api_port, [quiz_port], tunnel)
                print('\nОПЕРАТОРУ КВИЗА ОТПРАВЬТЕ:')
                print(f'Пульт квиза и лучшего игрока: {urls[quiz_port]}/control.html')
                print(f'Графика квиза и голосования для OBS: {urls[quiz_port]}/overlay.html')
                print('Вход без логина и пароля. Любой, у кого есть ссылка на пульт, сможет управлять квизом.')
                print('Ссылки работают, пока открыто это окно.')
            except Exception as exc:
                print(f'\nУдалённый доступ не запустился: {exc}')
                print('Локальный пульт продолжает работать; оставьте это окно открытым.')
                stop_all([tunnel])
                processes.remove(tunnel)
        webbrowser.open(quiz_local + '/control.html')
        print('\nНе закрывай это окно во время эфира. Для остановки нажми Ctrl+C.\n')
        while True:
            if quiz.poll() is not None:
                raise RuntimeError('Пульт завершился. Перезапусти комплект.')
            if use_ngrok and len(processes) > 1 and processes[-1].poll() is not None:
                print('Удалённая ссылка отключилась. Локальный пульт продолжает работать.')
                processes.pop()
            time.sleep(.5)
    except KeyboardInterrupt:
        print('\nОстанавливаю пульт комментатора и удалённую ссылку…')
    except Exception as exc:
        print(f'\nОшибка запуска: {exc}')
        return 1
    finally:
        stop_all(processes)
        if tempdir:
            tempdir.cleanup()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
