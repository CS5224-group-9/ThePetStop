"""AWS Lambda entry points. Both run from the same container image.

- `api` serves Django behind API Gateway (HTTP API, payload format 2.0).
- `manage` runs an allow-listed management command, e.g. invoked by the deploy
  workflow with `{"command": "migrate"}`.
"""

import io

from apig_wsgi import make_lambda_handler
from django.core.management import call_command

from config.wsgi import application

api = make_lambda_handler(application)

MANAGE_COMMANDS = {"migrate", "showmigrations", "check"}


def manage(event, context):
    command = event.get("command")
    if command not in MANAGE_COMMANDS:
        raise ValueError(f"Command not allowed: {command!r}")
    out = io.StringIO()
    call_command(command, *event.get("args", []), stdout=out, stderr=out)
    return {"command": command, "output": out.getvalue()}
