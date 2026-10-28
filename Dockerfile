FROM ghcr.io/prefix-dev/pixi:0.83.0-bookworm AS builder
ARG EXAMPLE

WORKDIR "/app"
COPY "${EXAMPLE}/pixi.toml" "${EXAMPLE}/pixi.lock" ./

RUN pixi config set --local run-post-link-scripts insecure
RUN pixi install --locked --environment default

# The download tasks use curl, which isn't in the project environments.
COPY "${EXAMPLE}/" .
RUN if pixi task list --environment default 2>/dev/null | grep -qw download; then \
        apt-get update && apt-get install -y --no-install-recommends curl \
        && pixi run --frozen download; \
    fi

FROM debian:bookworm-slim
ARG EXAMPLE

COPY --from=builder /etc/ssl/certs/ca-certificates.crt /etc/ssl/certs/ca-certificates.crt
COPY --from=builder /usr/local/bin/pixi /usr/local/bin/pixi

WORKDIR "/app"
COPY --from=builder "/app/." .

EXPOSE 5006
CMD ["pixi", "run", "--frozen", "dashboard"]
