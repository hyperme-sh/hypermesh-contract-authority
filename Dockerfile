FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim@sha256:531f855bda2c73cd6ef67d56b733b357cea384185b3022bd09f05e002cd144ca AS build
WORKDIR /app
COPY pyproject.toml uv.lock LICENSE ./
COPY src src
RUN uv sync --frozen --no-dev --no-editable
FROM python:3.13-slim-bookworm@sha256:281d39ff02e3b389401586134ff9e6572954687822a58055ec07a60ded4e0b7f
COPY --from=build /app/.venv /app/.venv
RUN mkdir /data && chmod 700 /data && chown 10001:10001 /data
USER 10001:10001
ENTRYPOINT ["/app/.venv/bin/hypermesh-contract-authority"]
