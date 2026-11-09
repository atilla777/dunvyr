#!/usr/bin/env bash
# Dunvyr: запуск backend и frontend одной командой.
#
# По умолчанию оба сервера слушают 0.0.0.0 (осознанный LAN-listener для
# локального MVP). Переопределение: DUNVYR_DEV_HOST=127.0.0.1 make dev.
# Порты: DUNVYR_BACKEND_PORT (8000), DUNVYR_FRONTEND_PORT (5173).
# Остановка Ctrl+C/SIGTERM завершает оба процесса, включая их потомков.

set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd -- "$script_dir/.." && pwd)"
backend_dir="$repo_root/backend"
frontend_dir="$repo_root/frontend"

dev_host="${DUNVYR_DEV_HOST:-0.0.0.0}"
backend_port="${DUNVYR_BACKEND_PORT:-8000}"
frontend_port="${DUNVYR_FRONTEND_PORT:-5173}"

missing=()
if [[ ! -x "$backend_dir/.venv/bin/python" ]]; then
  missing+=("backend/.venv")
fi
if [[ ! -d "$frontend_dir/node_modules" ]]; then
  missing+=("frontend/node_modules")
fi
if (( ${#missing[@]} > 0 )); then
  printf 'Ошибка: не найдены зависимости: %s.\n' "${missing[*]}" >&2
  printf 'Выполни из корня репозитория: make setup\n' >&2
  exit 1
fi

if ! command -v setsid >/dev/null 2>&1; then
  printf 'Ошибка: для корректной остановки процессов нужен setsid (util-linux).\n' >&2
  exit 1
fi

lan_ip=""
lan_ips=()
if command -v ip >/dev/null 2>&1; then
  lan_ip="$(ip -4 route get 1.1.1.1 2>/dev/null |
    awk '{ for (i = 1; i <= NF; i++) if ($i == "src") { print $(i + 1); exit } }')" || true
  while IFS= read -r address; do
    [[ -n "$address" ]] && lan_ips+=("$address")
  done < <(ip -o -4 addr show up scope global 2>/dev/null |
    awk '{ for (i = 1; i <= NF; i++) if ($i == "inet") { split($(i + 1), ip, "/"); print ip[1] } }')
fi
if [[ -z "$lan_ip" ]] && command -v hostname >/dev/null 2>&1; then
  lan_ip="$(hostname -I 2>/dev/null | awk '{ print $1 }')" || true
fi

bind_wildcard=false
show_lan=false
display_host="$dev_host"
case "$dev_host" in
  0.0.0.0 | ::)
    bind_wildcard=true
    show_lan=true
    display_host=127.0.0.1
    ;;
  localhost | 127.0.0.1 | ::1)
    display_host="$dev_host"
    ;;
  *)
    show_lan=true
    display_host="$dev_host"
    ;;
esac

frontend_local_url="http://$display_host:$frontend_port"
backend_local_url="http://$display_host:$backend_port/health"
lan_hosts=()
if [[ "$show_lan" == true ]]; then
  if [[ "$bind_wildcard" == true ]]; then
    lan_hosts=("${lan_ips[@]}")
    if [[ -n "$lan_ip" ]]; then
      lan_hosts+=("$lan_ip")
    fi
  else
    lan_hosts=("$dev_host")
  fi
fi

# Browser origins allowed to call the backend directly. In normal dev the
# browser talks to Vite and /api is proxied, so the Origin header is the
# frontend origin of the page the user opened (LAN, loopback or localhost).
allowed_origin_hosts=("127.0.0.1" "localhost")
if [[ -n "$lan_ip" ]]; then
  lan_ips+=("$lan_ip")
fi
case "$dev_host" in
  localhost | 127.0.0.1 | ::1 | 0.0.0.0 | ::) ;;
  *) lan_ips+=("$dev_host") ;;
esac
for address in "${lan_ips[@]}"; do
  found=false
  for host in "${allowed_origin_hosts[@]}"; do
    if [[ "$host" == "$address" ]]; then
      found=true
      break
    fi
  done
  if [[ "$found" == false ]]; then
    allowed_origin_hosts+=("$address")
  fi
done
allowed_origins=""
for host in "${allowed_origin_hosts[@]}"; do
  origin="http://$host:$frontend_port"
  if [[ -z "$allowed_origins" ]]; then
    allowed_origins="$origin"
  else
    allowed_origins="$allowed_origins,$origin"
  fi
done

printf '\nDunvyr dev\n'
printf '  Frontend: %s\n' "$frontend_local_url"
printf '  Backend:  %s\n' "$backend_local_url"
printed_lan_hosts=()
for lan_host in "${lan_hosts[@]}"; do
  found=false
  for host in "${printed_lan_hosts[@]}"; do
    if [[ "$host" == "$lan_host" ]]; then
      found=true
      break
    fi
  done
  [[ "$found" == true ]] && continue
  printed_lan_hosts+=("$lan_host")
  printf '  LAN:      http://%s:%s\n' "$lan_host" "$frontend_port"
  printf '            http://%s:%s/health\n' "$lan_host" "$backend_port"
done
if [[ "$show_lan" == true ]] && (( ${#printed_lan_hosts[@]} == 0 )); then
  printf '  LAN:      адрес не определён; проверь сетевой интерфейс (ip addr)\n'
fi

printf '\nПредупреждения:\n'
if [[ "$bind_wildcard" == true ]]; then
  printf '  * Listener 0.0.0.0 (все интерфейсы). Firewall должен открывать порты %s и %s только для доверенной LAN.\n' "$backend_port" "$frontend_port"
else
  printf '  * Listener %s. Доступ из LAN не открыт.\n' "$dev_host"
fi
printf '  * Обычный HTTP допустим только в доверенной LAN; для доступа из интернета обязателен HTTPS.\n'
printf '  * Cookie сессии: HttpOnly, SameSite=Lax; Secure выключен для локального HTTP.\n'
printf '    За HTTPS включи DUNVYR_COOKIE_SECURE=1.\n'
printf '  * Backend применяет Alembic-миграции к файлу backend/dunvyr.db при старте\n'
printf '    (DUNVYR_AUTO_MIGRATE=1): база создаётся миграциями, а не create_all.\n'
printf '  * Разрешённые Origin для API (DUNVYR_ALLOWED_ORIGINS): %s\n' "$allowed_origins"
printf '    Браузер работает с API same-origin через Vite-прокси /api → %s.\n' "http://$display_host:$backend_port"
printf '\nСерверы запущены. Ctrl+C остановит оба.\n\n'

backend_pid=""
frontend_pid=""

process_alive() {
  local pid="$1"
  kill -0 -- "-$pid" 2>/dev/null || kill -0 "$pid" 2>/dev/null
}

cleanup() {
  local status=$?
  trap - EXIT INT TERM

  if [[ -n "$frontend_pid" || -n "$backend_pid" ]]; then
    printf '\nОстанавливаю dev-серверы...\n' >&2
  fi

  local pid
  for pid in "$frontend_pid" "$backend_pid"; do
    [[ -n "$pid" ]] || continue
    kill -TERM -- "-$pid" 2>/dev/null || kill -TERM "$pid" 2>/dev/null || true
  done

  local attempts=0
  while (( attempts < 50 )); do
    local alive=false
    for pid in "$frontend_pid" "$backend_pid"; do
      [[ -n "$pid" ]] || continue
      if process_alive "$pid"; then
        alive=true
      fi
    done
    if [[ "$alive" == false ]]; then
      break
    fi
    sleep 0.2
    attempts=$((attempts + 1))
  done

  for pid in "$frontend_pid" "$backend_pid"; do
    [[ -n "$pid" ]] || continue
    kill -KILL -- "-$pid" 2>/dev/null || true
  done

  wait 2>/dev/null || true
  exit "$status"
}

trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

(
  cd "$backend_dir"
  DUNVYR_ALLOWED_ORIGINS="$allowed_origins" \
  DUNVYR_AUTO_MIGRATE=1 \
  exec setsid mise exec -- uv run uvicorn \
    --factory dunvyr.main:create_app \
    --host "$dev_host" \
    --port "$backend_port"
) &
backend_pid=$!

(
  cd "$frontend_dir"
  DUNVYR_DEV_HOST="$dev_host" \
  DUNVYR_BACKEND_ORIGIN="http://$display_host:$backend_port" \
  exec setsid mise exec -- npm run dev -- --port "$frontend_port"
) &
frontend_pid=$!

set +e
wait -n "$backend_pid" "$frontend_pid"
exit_status=$?
set -e

printf '\nОдин из dev-процессов завершился (код %s); останавливаю второй.\n' "$exit_status" >&2
exit 1
