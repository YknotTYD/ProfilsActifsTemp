FROM python:3.12-slim

WORKDIR /app

# Installer uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Copier les fichiers de dépendances et installer les dépendances externes uniquement
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# Copier le reste du projet, y compris db.sqlite3
COPY . .

# Réinstaller pour inclure le projet lui-même maintenant que le code est présent
RUN uv sync --frozen --no-dev

# Collecter les fichiers statiques
RUN uv run python manage.py collectstatic --noinput

EXPOSE 8000

CMD ["sh", "-c", "uv run python manage.py migrate --noinput && uv run python manage.py runserver 0.0.0.0:8000"]