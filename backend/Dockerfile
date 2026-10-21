# Lambda container image for the Django API. Built and pushed to ECR by CDK
# (infra/lib/api-stack.ts), which picks the handler: config.lambda_handler.api
# for requests, config.lambda_handler.manage for migrations.
FROM public.ecr.aws/lambda/python:3.13

COPY --from=ghcr.io/astral-sh/uv:0.12.23 /uv /bin/uv

# Dependencies first, so code changes reuse this layer
COPY pyproject.toml uv.lock ./
RUN uv export --frozen --no-dev --no-emit-project --no-hashes -o requirements.txt \
    && uv pip install --no-cache --target "${LAMBDA_TASK_ROOT}" -r requirements.txt \
    && rm requirements.txt

COPY . "${LAMBDA_TASK_ROOT}"

CMD ["config.lambda_handler.api"]
