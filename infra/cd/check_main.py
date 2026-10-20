"""Evita iniciar una entrega si main avanzó mientras se ejecutaba CI."""

import argparse
import os
import re
import sys

from deploy_render import DeployError, request, summary


def current_main(repository, token):
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository) or not token:
        raise DeployError("Falta el repositorio o la credencial de lectura de GitHub.")
    response = request(
        f"https://api.github.com/repos/{repository}/git/ref/heads/main",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
    )
    if response.status != 200:
        raise DeployError(f"No se pudo consultar main en GitHub: HTTP {response.status}.")
    data = response.json()
    ref_object = data.get("object") if isinstance(data, dict) else None
    commit = ref_object.get("sha") if isinstance(ref_object, dict) else None
    if not isinstance(commit, str) or not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise DeployError("GitHub no devolvió un SHA válido para main.")
    return commit


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--commit", required=True)
    args = parser.parse_args()
    try:
        if not re.fullmatch(r"[0-9a-f]{40}", args.commit):
            raise DeployError("Se necesita el SHA completo del commit validado.")
        latest = current_main(os.getenv("GITHUB_REPOSITORY", ""), os.getenv("GITHUB_TOKEN", ""))
        deploy = latest == args.commit
        output_path = os.getenv("GITHUB_OUTPUT")
        if not output_path:
            raise DeployError("Falta el archivo de resultados de GitHub Actions.")
        with open(output_path, "a", encoding="utf8") as output:
            output.write(f"deploy={'true' if deploy else 'false'}\n")
        if deploy:
            print("El commit validado sigue siendo el último de main.")
        else:
            print("main avanzó durante CI: se omite esta entrega sin modificar Render.")
            summary(f"Entrega omitida: main avanzó de `{args.commit}` a `{latest}` durante CI.")
    except (DeployError, OSError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
