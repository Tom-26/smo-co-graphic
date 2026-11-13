#!/bin/sh
cd "$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)" || exit 1
if ! docker compose up -d --build; then
  echo 'Обычная сборка не удалась. Пробую загрузить открытый образ без сохранённых учётных данных Docker.'
  docker_endpoint=$(docker context inspect --format '{{.Endpoints.docker.Host}}' 2>/dev/null) || docker_endpoint=''
  if [ -z "$docker_endpoint" ]; then
    echo 'Не удалось определить подключение к Docker Desktop. Проверьте, что Docker Desktop запущен.'
    read -r _
    exit 1
  fi
  temporary_docker_config=$(mktemp -d "${TMPDIR:-/tmp}/smo-docker.XXXXXXXX") || exit 1
  trap 'rm -rf "$temporary_docker_config"' EXIT HUP INT TERM
  original_docker_config=${DOCKER_CONFIG:-"$HOME/.docker"}
  if [ -d "$original_docker_config/cli-plugins" ]; then
    ln -s "$original_docker_config/cli-plugins" "$temporary_docker_config/cli-plugins"
  fi
  if ! DOCKER_CONFIG="$temporary_docker_config" DOCKER_HOST="$docker_endpoint" docker compose up -d --build; then
    echo 'Не удалось запустить приложение. Проверьте подключение к интернету и сообщения Docker выше.'
    read -r _
    exit 1
  fi
fi
echo 'Пульт: http://127.0.0.1:18770/control.html'
echo 'Графика OBS: http://127.0.0.1:18770/overlay.html'
open http://127.0.0.1:18770/control.html
