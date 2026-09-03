FROM python:3.12-slim

WORKDIR /app

# Installer uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Copier les fichiers de dépendances et installer
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

# Copier le reste du projet, y compris db.sqlite3
COPY . .

# Collecter les fichiers statiques
RUN uv run python manage.py collectstatic --noinput

EXPOSE 8000

CMD ["uv", "run", "python", "manage.py", "runserver", "0.0.0.0:8000"]