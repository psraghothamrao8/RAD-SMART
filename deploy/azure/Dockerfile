# The RAD-SMART demonstration server as one container: CARE's API (gunicorn)
# with the plugin and the engine, Redis as CARE's cache, and nginx serving both
# frontends on port 8080. deploy.sh prepares the build context (.build/): CARE's
# frontend source, the plugin's frontend build, the plugin and the engine. The
# database is outside.
ARG BASE=radsmart-care-base

# CARE's frontend is built on Linux, as in its own Dockerfile: on Windows its icon
# tree-shaking globs no files, and every page then fails on a missing icon. The API
# is same-origin and there are no build-time plugins; PUBLIC_URL only fills og:url.
FROM node:22-bookworm-slim AS care-fe
WORKDIR /app
ENV NODE_OPTIONS="--max-old-space-size=4096"
COPY care_fe/package.json care_fe/package-lock.json ./
RUN npm install --ignore-scripts
COPY care_fe/ ./
ARG PUBLIC_URL
RUN npm run postinstall \
  && REACT_CARE_API_URL="" REACT_ENABLED_APPS="" REACT_PUBLIC_URL="$PUBLIC_URL" npm run build

FROM ${BASE}

USER root
RUN apt-get update && apt-get install --no-install-recommends -y nginx redis-server \
  && rm -rf /var/lib/apt/lists/* /etc/nginx/sites-enabled/default

# Editable installs, as in development: the engine reads poc/data/ beside its package.
COPY --chown=django:django engine/ /plugins/radsmart_engine/
COPY --chown=django:django plugin/ /plugins/care_radsmart/
RUN pip install --no-cache-dir -e /plugins/radsmart_engine -e /plugins/care_radsmart

COPY settings.py /app/config/settings/radsmart_azure.py
COPY nginx.conf /etc/nginx/nginx.conf
COPY --chmod=0755 entrypoint.sh guard.py /srv/
COPY --from=care-fe --chown=django:django /app/build/ /srv/www/
COPY --chown=django:django www/ /srv/www/

ENV DJANGO_SETTINGS_MODULE=config.settings.radsmart_azure \
    ADDITIONAL_PLUGS='[{"name":"care_radsmart","package_name":"/plugins/care_radsmart","version":"","configs":{"RADSMART_DEMO":true,"RADSMART_MACHINES":"VERSA:Versa HD"}}]'

# Static files and translations at build time, so a cold start only starts the
# servers. Loading the settings writes a throwaway signing key; the server's own
# comes from JWKS_BASE64.
RUN DATABASE_URL=postgres://build@localhost/build python manage.py collectstatic --noinput -v 0 \
  && DATABASE_URL=postgres://build@localhost/build python manage.py compilemessages -v 0 \
  && rm -f /app/jwks.b64.txt

USER django
EXPOSE 8080
HEALTHCHECK NONE
ENTRYPOINT ["/srv/entrypoint.sh"]
