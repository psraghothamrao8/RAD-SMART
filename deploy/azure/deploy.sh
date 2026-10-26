#!/usr/bin/env bash
# Host the RAD-SMART demonstration on Azure using only services an Azure for
# Students subscription gets free (see README.md beside this file).
#
#   bash deploy/azure/deploy.sh <step> ...
#
#   create    resource group, container registry, PostgreSQL, Container Apps environment (once)
#   build     both frontends and the image, with local Docker
#   init      fill a copy of the database in the local development stack and upload it
#             (migrations, CARE's fixtures, the demonstration data, kept Sarvam answers,
#             new random passwords); run again to start the data afresh
#   upload    only the last part of init: send the local copy to the server again
#   push      push the image and create or update the app
#   webhook   point the Telegram bot at the app
#   job       push the image; the daily job (05:30 IST): migrations, fresh demonstration data, the guard's check
#   reseed    run the daily job now and wait for it (after a plugin update: it migrates)
#   status    address, whether it is public, replicas, awake hours, recent job runs
#   pause / resume   take the app off the internet by hand, or put it back
#   all       create build init push webhook job
#   down      delete everything in the resource group (asks first)
#
# Run it in Git Bash from a clone of this repository, signed in with `az login`, with the
# development stack (workspace/restore.sh) running: `init` and `webhook` use its containers.
#
#   WORKSPACE   the CARE workspace (default <repo>/../care-workspace/scaffold); secrets are read
#               from its git-ignored .agent/.env, and this script keeps its own in .agent/azure.env
#               and the demonstration logins in .agent/azure-logins.txt. None is printed.
#   RG, LOC     resource group and region (default radsmart-demo, uaenorth: Azure for Students
#               allows only some regions, and Container Apps is not in Central India)
set -euo pipefail
export MSYS_NO_PATHCONV=1      # Git Bash must not rewrite /plugins/... or /subscriptions/... arguments

HERE="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd -- "$HERE/../.." && pwd)"
BUILD="$HERE/.build"
native() { if command -v cygpath >/dev/null 2>&1; then cygpath -m "$1"; else printf '%s' "$1"; fi; }
WIN_AZ="/c/Program Files/Microsoft SDKs/Azure/CLI2/wbin"
[[ -d "$WIN_AZ" ]] && PATH="$WIN_AZ:$PATH"

# shellcheck source=../../workspace/pins.env
source "$REPO/workspace/pins.env"
WORKSPACE="${WORKSPACE:-$(cd -- "$REPO/.." && pwd)/care-workspace/scaffold}"
AGENT="$WORKSPACE/.agent"
PROJECT="${PROJECT:-care_radsmart_dev}"
BACKEND="$PROJECT-backend-1"; DB="$PROJECT-db-1"; REDIS="$PROJECT-redis-1"

RG="${RG:-radsmart-demo}"
LOC="${LOC:-uaenorth}"
CAE="${CAE:-radsmart-env}"
APP="${APP:-radsmart}"
JOB="${JOB:-radsmart-reseed}"
AWAKE_HOURS="${AWAKE_HOURS:-85}"                 # of the 100 free hours a month at 0.5 vCPU / 1 GiB
SARVAM_DAILY_CHARS="${SARVAM_DAILY_CHARS:-6000}" # Sarvam spending caps for the public server
SARVAM_TOTAL_CHARS="${SARVAM_TOTAL_CHARS:-40000}"
CENSUS="${CENSUS:-60}"
OPEN_DEMO="${OPEN_DEMO:-True}"                  # the one-click front door at /try/ (tryout.py)

log() { printf '\n== %s\n' "$*"; }
need() { command -v "$1" >/dev/null 2>&1 || { echo "missing prerequisite: $1" >&2; exit 1; }; }
need az; need docker; need git

SUB_ID="$(az account show --query id -o tsv)"
SUFFIX="$(printf '%s' "$SUB_ID" | tr -d '-' | cut -c1-6)"
ACR="${ACR:-radsmart$SUFFIX}"
PG="${PG:-radsmart-db-$SUFFIX}"
APP_ID="/subscriptions/$SUB_ID/resourceGroups/$RG/providers/Microsoft.App/containerApps/$APP"
JOB_ID="/subscriptions/$SUB_ID/resourceGroups/$RG/providers/Microsoft.App/jobs/$JOB"

# ------------------------------------------------------------------ secrets
# Generated once and kept in the workspace's git-ignored .agent/azure.env.
secrets() {
  mkdir -p "$AGENT"
  if [[ ! -f "$AGENT/azure.env" ]]; then
    local base; base="$(base_image)"
    docker image inspect "$base" >/dev/null 2>&1 || build_base
    umask 077
    {
      echo "PG_PASSWORD='Rs9-$(openssl rand -hex 16)'"
      echo "DJANGO_SECRET_KEY='$(openssl rand -base64 48 | tr -d '\n/+=')'"
      echo "JWKS_BASE64='$(docker run --rm --entrypoint python "$base" -c \
        'from care.utils.jwks.generate_jwk import generate_encoded_jwks; print(generate_encoded_jwks())')'"
    } > "$AGENT/azure.env"
  fi
  set -a
  # shellcheck disable=SC1091
  [[ -f "$AGENT/.env" ]] && source "$AGENT/.env"
  # shellcheck disable=SC1091
  source "$AGENT/azure.env"
  set +a
  DATABASE_URL="postgres://careadmin:$PG_PASSWORD@$PG.postgres.database.azure.com:5432/care?sslmode=require"
}
remember() {   # remember KEY VALUE: add or replace a line in azure.env
  grep -v "^$1=" "$AGENT/azure.env" > "$AGENT/azure.env.new" || true
  echo "$1='$2'" >> "$AGENT/azure.env.new"
  mv "$AGENT/azure.env.new" "$AGENT/azure.env"
}

fqdn() {
  local domain
  domain="$(az containerapp env show -g "$RG" -n "$CAE" --query properties.defaultDomain -o tsv)"
  printf '%s.%s' "$APP" "$domain"
}

# The local machine may reach the database only while a step needs it.
open_db() {
  local ip; ip="$(curl -fsS https://api.ipify.org)"
  az postgres flexible-server firewall-rule create -g "$RG" -s "$PG" -n deploy-local \
    --start-ip-address "$ip" --end-ip-address "$ip" -o none
  trap close_db EXIT
}
close_db() {
  az postgres flexible-server firewall-rule delete -g "$RG" -s "$PG" -n deploy-local --yes -o none || true
}

# ------------------------------------------------------------------- create
create() {
  secrets
  log "Resource group $RG ($LOC)"
  az group create -n "$RG" -l "$LOC" -o none
  log "Container registry $ACR (Standard: one is free for 12 months)"
  az acr show -n "$ACR" -o none 2>/dev/null ||
    az acr create -g "$RG" -n "$ACR" -l "$LOC" --sku Standard --admin-enabled true -o none
  log "PostgreSQL $PG (Burstable B1ms, 32 GB, no high availability or geo-backup: free for 12 months)"
  if ! az postgres flexible-server show -g "$RG" -n "$PG" -o none 2>/dev/null; then
    az postgres flexible-server create -g "$RG" -n "$PG" -l "$LOC" --tier Burstable --sku-name Standard_B1ms \
      --storage-size 32 --storage-type Premium_LRS --storage-auto-grow Disabled --version 17 \
      --zonal-resiliency Disabled --backup-retention 7 --geo-redundant-backup Disabled \
      --admin-user careadmin --admin-password "$PG_PASSWORD" --public-access 0.0.0.0 --yes -o none
  fi
  az postgres flexible-server parameter set -g "$RG" -s "$PG" -n azure.extensions -v PG_TRGM -o none
  az postgres flexible-server db show -g "$RG" -s "$PG" -n care -o none 2>/dev/null ||
    az postgres flexible-server db create -g "$RG" -s "$PG" -n care -o none
  # Workload profiles, but only the built-in Consumption one: with no Dedicated profile there
  # is no plan management fee. The mode is set through the API because `az containerapp env
  # create` now makes an "Express" environment, which has no jobs and no system-assigned
  # identity, and this needs both. No logs destination is given, so there is no Log Analytics.
  log "Container Apps environment $CAE (Consumption profile only, no Log Analytics)"
  if ! az containerapp env show -g "$RG" -n "$CAE" -o none 2>/dev/null; then
    az rest --method put -o none \
      --url "https://management.azure.com/subscriptions/$SUB_ID/resourceGroups/$RG/providers/Microsoft.App/managedEnvironments/$CAE?api-version=2026-07-01" \
      --body "{\"location\": \"$LOC\", \"properties\": {\"environmentMode\": \"WorkloadProfiles\", \"zoneRedundant\": false,
        \"workloadProfiles\": [{\"name\": \"Consumption\", \"workloadProfileType\": \"Consumption\"}]}}"
    until [[ "$(az containerapp env show -g "$RG" -n "$CAE" --query properties.provisioningState -o tsv)" == Succeeded ]]; do
      sleep 15
    done
  fi
  echo "The app will be at https://$(fqdn)"
}

# -------------------------------------------------------------------- build
base_image() { printf 'radsmart-care-base:%s' "${CARE_REF:0:7}"; }
build_base() {
  log "CARE's production image at ${CARE_REF:0:7} (from a clean export: no local keys or files)"
  git -C "$(native "$WORKSPACE/care")" archive --format=tar "$CARE_REF" |
    docker build -f docker/prod.Dockerfile --target runtime --build-arg APP_VERSION="${CARE_REF:0:7}" \
      -t "$(base_image)" -
}
build() {
  need npm; need tar
  local url base tag
  url="https://$(fqdn)"; base="$(base_image)"
  docker image inspect "$base" >/dev/null 2>&1 || build_base
  rm -rf "$BUILD"; mkdir -p "$BUILD/care_fe" "$BUILD/www/plugins/radsmart" "$BUILD/engine" "$BUILD/plugin"

  log "CARE frontend source at ${CARE_FE_REF:0:7} (a clean export; the image builds it on Linux)"
  git -C "$(native "$WORKSPACE/care_fe")" archive --format=tar "$CARE_FE_REF" | tar -C "$BUILD/care_fe" -xf -

  log "Plugin frontend, served from /plugins/radsmart/"
  (cd "$REPO/app/care_radsmart_fe" &&
    npm run build -- --base /plugins/radsmart/ --outDir "$(native "$BUILD/www/plugins/radsmart")" --emptyOutDir)

  log "Plugin and engine sources (the working tree, without caches)"
  tar -C "$REPO/poc" --exclude=__pycache__ --exclude='*.egg-info' -cf - pyproject.toml radsmart data |
    tar -C "$BUILD/engine" -xf -
  tar -C "$REPO/app/care_radsmart" --exclude=__pycache__ --exclude='*.egg-info' --exclude=tests \
    -cf - setup.py MANIFEST.in README.md care_radsmart | tar -C "$BUILD/plugin" -xf -
  cp "$HERE"/{Dockerfile,nginx.conf,entrypoint.sh,guard.py,settings.py} "$BUILD/"
  sed -i 's/\r$//' "$BUILD"/{nginx.conf,entrypoint.sh,guard.py,settings.py}   # CRLF from a Windows editor breaks the shebang

  tag="$(date +%Y%m%d-%H%M)"
  log "Image $ACR.azurecr.io/radsmart:$tag"
  docker build --build-arg BASE="$base" --build-arg PUBLIC_URL="$url" -t "$ACR.azurecr.io/radsmart:$tag" "$(native "$BUILD")"
  echo "$tag" > "$HERE/.tag"
}
image() { printf '%s.azurecr.io/radsmart:%s' "$ACR" "$(cat "$HERE/.tag")"; }

# --------------------------------------------------------------------- init
dexec() { docker exec -i -e DATABASE_URL="$LOCAL_COPY" -e REDIS_URL=redis://redis:6379/5 \
  -e CELERY_BROKER_URL=redis://redis:6379/5 "$BACKEND" "$@"; }
init() {
  secrets
  local dev facility
  dev="$(docker exec "$BACKEND" printenv DATABASE_URL)"
  LOCAL_COPY="${dev%/*}/care_azure"
  log "A fresh copy in the local stack (database care_azure; Redis database 5 for its cache)"
  docker exec "$DB" sh -c 'dropdb -U "$POSTGRES_USER" --if-exists care_azure && createdb -U "$POSTGRES_USER" care_azure'
  dexec python manage.py migrate --noinput -v 0
  dexec python manage.py load_fixtures > /dev/null
  facility="$(dexec python manage.py shell -v 0 -c \
    "from care.facility.models import Facility; print(Facility.objects.get(name='FACILITY WITH PATIENTS').external_id)" |
    tail -n 1 | tr -d '\r')"
  remember RADSMART_FACILITY "$facility"
  log "Demonstration data for facility $facility"
  dexec python manage.py radsmart_demo --facility "$facility" --user care-doctor --census "$CENSUS"
  log "Sarvam answers kept in development, so the server does not pay for them again"
  docker exec "$BACKEND" python manage.py radsmart_sarvam --export /tmp/radsmart-answers.jsonl
  dexec python manage.py radsmart_sarvam --import /tmp/radsmart-answers.jsonl
  docker exec "$BACKEND" rm -f /tmp/radsmart-answers.jsonl
  log "New passwords (kept in $AGENT/azure-logins.txt)"
  (umask 077; dexec python manage.py shell -v 0 < "$HERE/site.py" |
    tr -d '\r' | sed -n 's/^LOGIN //p' > "$AGENT/azure-logins.txt")
  echo "$(wc -l < "$AGENT/azure-logins.txt") logins written"
  upload
}
upload() {   # the local copy (care_azure) replaces the server's database
  secrets
  log "Upload to $PG"
  open_db
  docker exec "$DB" sh -c 'pg_dump -U "$POSTGRES_USER" -Fc -d care_azure -f /tmp/care_azure.dump'
  docker exec -e TARGET="$DATABASE_URL" "$DB" sh -c \
    'pg_restore --clean --if-exists --no-owner --no-acl --no-comments -d "$TARGET" /tmp/care_azure.dump; s=$?
     rm -f /tmp/care_azure.dump; exit $s' || { echo "pg_restore reported errors (above)" >&2; exit 1; }
  close_db; trap - EXIT
  docker exec "$DB" sh -c 'dropdb -U "$POSTGRES_USER" --if-exists care_azure'
  docker exec "$REDIS" redis-cli -n 5 flushdb > /dev/null
}

# --------------------------------------------------------------------- push
env_common() {
  local host="$1"
  ENV_COMMON=(
    "DATABASE_URL=secretref:database-url" "DJANGO_SECRET_KEY=secretref:django-secret-key"
    "JWKS_BASE64=secretref:jwks" "REDIS_URL=redis://127.0.0.1:6379"
    "DJANGO_ALLOWED_HOSTS=[\"$host\",\"localhost\",\"127.0.0.1\"]"
    "CSRF_TRUSTED_ORIGINS=[\"https://$host\"]" "CORS_ALLOWED_ORIGINS=[\"https://$host\"]"
    "DJANGO_SECURE_SSL_REDIRECT=False" "USE_SMS=False" "RADSMART_PUBLIC_URL=https://$host"
    "RADSMART_APP_ID=$APP_ID" "RADSMART_AWAKE_HOURS=$AWAKE_HOURS"
  )
  SECRETS_COMMON=("database-url=$DATABASE_URL" "django-secret-key=$DJANGO_SECRET_KEY" "jwks=$JWKS_BASE64")
}
registry() {
  REGISTRY=(--registry-server "$ACR.azurecr.io" --registry-username "$ACR"
    --registry-password "$(az acr credential show -n "$ACR" --query 'passwords[0].value' -o tsv)")
}
grant() {   # grant <principal id>: let an identity open or close the app's ingress (guard.py)
  local i
  for i in 1 2 3 4 5 6; do      # a new identity takes a little while to be known
    az role assignment create --assignee-object-id "$1" --assignee-principal-type ServicePrincipal \
      --role Contributor --scope "$APP_ID" -o none && return 0
    sleep 20
  done
  return 1
}
ship() {   # the built image into the registry, for the app and the job alike
  log "Push $(image)"
  az acr login -n "$ACR" > /dev/null
  docker push -q "$(image)"
}
push() {
  secrets
  local host img
  host="$(fqdn)"; img="$(image)"
  ship
  env_common "$host"; registry
  local env=("${ENV_COMMON[@]}" "GUNICORN_WORKERS=2"
    "RADSMART_SARVAM_DAILY_CHARS=$SARVAM_DAILY_CHARS" "RADSMART_SARVAM_TOTAL_CHARS=$SARVAM_TOTAL_CHARS"
    "RADSMART_OPEN_DEMO=$OPEN_DEMO" "RADSMART_DEMO_FACILITY=$RADSMART_FACILITY" "RADSMART_CENSUS=$CENSUS")
  local sec=("${SECRETS_COMMON[@]}")
  [[ -n "${SARVAM_API_KEY:-}" ]] && { sec+=("sarvam-api-key=$SARVAM_API_KEY"); env+=("SARVAM_API_KEY=secretref:sarvam-api-key"); }
  if [[ -n "${RADSMART_TELEGRAM_TOKEN:-}" && -n "${RADSMART_TELEGRAM_SECRET:-}" ]]; then
    sec+=("telegram-token=$RADSMART_TELEGRAM_TOKEN" "telegram-secret=$RADSMART_TELEGRAM_SECRET")
    env+=("RADSMART_TELEGRAM_TOKEN=secretref:telegram-token" "RADSMART_TELEGRAM_SECRET=secretref:telegram-secret")
  fi
  if az containerapp show -g "$RG" -n "$APP" -o none 2>/dev/null; then
    log "Update $APP"
    az containerapp secret set -g "$RG" -n "$APP" --secrets "${sec[@]}" -o none
    az containerapp update -g "$RG" -n "$APP" --image "$img" --set-env-vars "${env[@]}" -o none
  else
    log "Create $APP (0.5 vCPU, 1 GiB, 0 to 1 replicas: it sleeps when nobody uses it)"
    az containerapp create -g "$RG" -n "$APP" --environment "$CAE" --workload-profile-name Consumption \
      --image "$img" "${REGISTRY[@]}" \
      --ingress external --target-port 8080 --transport auto \
      --cpu 0.5 --memory 1.0Gi --min-replicas 0 --max-replicas 1 --system-assigned \
      --secrets "${sec[@]}" --env-vars "${env[@]}" -o none
    grant "$(az containerapp show -g "$RG" -n "$APP" --query identity.principalId -o tsv)"
  fi
  # Keep the registry small: the newest three images.
  az acr repository show-tags -n "$ACR" --repository radsmart --orderby time_desc -o tsv | tail -n +4 |
    while read -r old; do az acr repository delete -n "$ACR" --image "radsmart:$old" --yes -o none; done
  echo "https://$host"
}

# ------------------------------------------------------------------ webhook
webhook() {
  log "Telegram posts updates to https://$(fqdn)"
  docker exec "$BACKEND" python manage.py radsmart_telegram --webhook "https://$(fqdn)"
}

# ---------------------------------------------------------------------- job
job() {
  secrets
  [[ -n "${RADSMART_FACILITY:-}" ]] || { echo "run init first" >&2; exit 1; }
  ship
  env_common "$(fqdn)"; registry
  local env=("${ENV_COMMON[@]}" "RADSMART_FACILITY=$RADSMART_FACILITY" "RADSMART_CENSUS=$CENSUS")
  if az containerapp job show -g "$RG" -n "$JOB" -o none 2>/dev/null; then
    log "Update $JOB"
    az containerapp job secret set -g "$RG" -n "$JOB" --secrets "${SECRETS_COMMON[@]}" -o none
    az containerapp job update -g "$RG" -n "$JOB" --image "$(image)" --set-env-vars "${env[@]}" -o none
  else
    log "Create $JOB (every day at 00:00 UTC, 05:30 IST)"
    az containerapp job create -g "$RG" -n "$JOB" --environment "$CAE" --workload-profile-name Consumption \
      --image "$(image)" "${REGISTRY[@]}" \
      --trigger-type Schedule --cron-expression "0 0 * * *" --replica-timeout 1800 --replica-retry-limit 0 \
      --parallelism 1 --replica-completion-count 1 --cpu 0.5 --memory 1.0Gi --mi-system-assigned \
      --secrets "${SECRETS_COMMON[@]}" --env-vars "${env[@]}" --args reseed -o none
    grant "$(az containerapp job show -g "$RG" -n "$JOB" --query identity.principalId -o tsv)"
  fi
}

reseed() {
  log "Run $JOB now"
  local run state
  run="$(az containerapp job start -g "$RG" -n "$JOB" --query name -o tsv | tr -d '\r')"
  while state="$(az containerapp job execution show -g "$RG" -n "$JOB" --job-execution-name "$run" \
      --query properties.status -o tsv | tr -d '\r')"; [[ "$state" == Running || "$state" == Processing ]]; do
    sleep 15
  done
  echo "$run: $state"
  [[ "$state" == Succeeded ]]
}

# ------------------------------------------------------------------- status
status() {
  secrets
  local public paused img
  IFS='|' read -r public paused img < <(az containerapp show -g "$RG" -n "$APP" -o tsv --query \
    "[properties.configuration.ingress.external, tags.\"radsmart-paused\", properties.template.containers[0].image]" |
    tr -d '\r' | paste -sd '|')   # one value a line; an empty tag must stay a field
  echo "address:  https://$(fqdn)"
  echo "public:   $public (paused by hand: ${paused:-no})"
  echo "image:    $img"
  echo "replicas: $(az containerapp replica list -g "$RG" -n "$APP" --query 'length(@)' -o tsv 2>/dev/null || echo 0)"
  open_db
  docker exec -e TARGET="$DATABASE_URL" -e SQL="SELECT round(coalesce(sum(seconds), 0) / 3600.0, 1) FROM radsmart_awake
    WHERE day > (now() at time zone 'utc')::date - 31" "$DB" sh -c 'psql "$TARGET" -tAc "$SQL"' 2>/dev/null |
    sed "s/.*/awake:    & of $AWAKE_HOURS h in the last 31 days/" || echo "awake:    nothing counted yet"
  close_db; trap - EXIT
  az containerapp job execution list -g "$RG" -n "$JOB" --query "[:3].{start:properties.startTime, status:properties.status}" -o table 2>/dev/null || true
}
paused() {   # paused yes|no: the tag the daily job reads. Only the tags are sent: `az resource
             # tag` writes the whole app back, which fails on secrets Azure never returns.
  az rest --method patch -o none --url "https://management.azure.com$APP_ID?api-version=2024-03-01" \
    --body "{\"tags\": {\"radsmart-paused\": \"$1\"}}"
}
pause() {
  paused yes
  az containerapp ingress update -g "$RG" -n "$APP" --type internal -o none
  echo "The app is internal: nothing outside reaches it, and it sleeps. 'resume' puts it back."
}
resume() {
  paused no
  az containerapp ingress update -g "$RG" -n "$APP" --type external -o none
  echo "The app is public at https://$(fqdn) (the guard closes it again if the 31-day allowance is used up)."
}
down() {
  read -r -p "Delete resource group $RG and everything in it? Type its name: " answer
  [[ "$answer" == "$RG" ]] || { echo "Nothing deleted."; exit 1; }
  az group delete -n "$RG" --yes
}

[[ $# -gt 0 ]] || { sed -n '2,30p' "$0"; exit 2; }
for step in "$@"; do
  case "$step" in
    create|build|init|upload|push|webhook|job|reseed|status|pause|resume|down) "$step" ;;
    all) create; build; init; push; webhook; job ;;
    *) echo "unknown step: $step" >&2; exit 2 ;;
  esac
done
