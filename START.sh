#!/bin/sh
set -u
cd "$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)" || exit 1
py=''
for candidate in python3 python; do
    if command -v "$candidate" >/dev/null 2>&1 && "$candidate" -c 'import sys; sys.exit(sys.version_info < (3, 9))' 2>/dev/null; then py="$candidate"; break; fi
done
if [ -z "$py" ]; then echo 'Нужен Python 3.9 или новее.'; printf 'Нажмите Enter для выхода: '; read -r _; exit 1; fi
exec "$py" scripts/start_all.py
