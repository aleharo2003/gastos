"""Despliega el commit validado en los tres servicios del entorno de test."""

import argparse
import json
import os
from pathlib import Path
import re
import sys
import time
from dataclasses import dataclass
from html.parser import HTMLParser
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

API_URL = "https://api.render.com/v1"
PENDING = {"created", "queued", "build_in_progress", "pre_deploy_in_progress", "update_in_progress"}
FAILED = {"build_failed", "pre_deploy_failed", "update_failed", "canceled", "deactivated"}


class DeployError(Exception):
    """Error operativo que se puede mostrar sin revelar credenciales."""


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


@dataclass
class Response:
    status: int
    headers: dict
    body: bytes

    def json(self):
        try:
            return json.loads(self.body)
        except (ValueError, UnicodeError) as error:
            raise DeployError("La respuesta no contiene JSON válido.") from error


def request(url, *, method="GET", headers=None, data=None):
    # La misma prohibición protege las peticiones autenticadas y las públicas.
    opener = build_opener(NoRedirect())
    req = Request(url, data=data, headers=headers or {}, method=method)
    try:
        try:
            response = opener.open(req, timeout=30)
        except HTTPError as error:
            response = error
        with response:
            body = response.read(2_000_001)
            if len(body) > 2_000_000:
                raise DeployError("La respuesta supera el límite de tamaño.")
            return Response(response.status, {k.lower(): v for k, v in response.headers.items()}, body)
    except (URLError, OSError, TimeoutError) as error:
        raise DeployError("No se pudo completar la solicitud HTTP.") from error


class Render:
    def __init__(self, token):
        self.token = token

    def call(self, method, path, data=None):
        # Nunca se envía esta autorización a las direcciones públicas.
        headers = {"Authorization": f"Bearer {self.token}", "Accept": "application/json"}
        payload = None
        if data is not None:
            headers["Content-Type"] = "application/json"
            payload = json.dumps(data).encode()
        attempts = 3 if method == "GET" else 1
        for attempt in range(attempts):
            try:
                response = request(f"{API_URL}{path}", method=method, headers=headers, data=payload)
            except DeployError as error:
                if method == "POST":
                    raise DeployError("Render pudo aceptar el despliegue. Revisar su panel antes de reintentar.") from error
                if attempt == attempts - 1:
                    raise
            else:
                if method == "GET" and (response.status == 429 or response.status >= 500):
                    if attempt == attempts - 1:
                        raise DeployError(f"Render no está disponible: HTTP {response.status}.")
                else:
                    if response.status not in (200, 201, 202):
                        detail = " Revisar Render antes de reintentar." if method == "POST" else ""
                        raise DeployError(f"La solicitud a Render terminó con HTTP {response.status}.{detail}")
                    return response
            time.sleep(2 * (attempt + 1))
        raise DeployError("No se recibió una respuesta de Render.")

    def get(self, path):
        response = self.call("GET", path)
        if response.status != 200:
            raise DeployError("Render no devolvió el recurso solicitado.")
        value = response.json()
        if not isinstance(value, dict):
            raise DeployError("Render no devolvió un objeto JSON.")
        return value

    def start(self, service_id, commit):
        response = self.call("POST", f"/services/{service_id}/deploys", {"commitId": commit})
        try:
            data = response.json()
        except DeployError:
            data = None
        if not isinstance(data, dict) or not re.fullmatch(r"dep-[a-zA-Z0-9]+", str(data.get("id", ""))):
            raise DeployError("Render pudo aceptar o encolar el despliegue sin devolver su ID. Revisar el panel antes de reintentar.")
        return data["id"]


def origin(value):
    if not isinstance(value, str):
        raise DeployError("La configuración necesita direcciones HTTPS públicas sin ruta.")
    try:
        parts = urlsplit(value)
    except ValueError as error:
        raise DeployError("La configuración contiene una dirección inválida.") from error
    if parts.scheme != "https" or not parts.netloc or parts.username or parts.password or parts.path not in ("", "/") or parts.query or parts.fragment:
        raise DeployError("La configuración necesita direcciones HTTPS públicas sin ruta.")
    return value.rstrip("/")


def load_config(path, environ):
    try:
        config = json.loads(path.read_text(encoding="utf8"))
        services = config["services"]
        if config["branch"] != "main" or config["repository"] != f"https://github.com/{environ['GITHUB_REPOSITORY']}":
            raise DeployError("El repositorio o la rama de destino no coincide con este workflow.")
        if [s["name"] for s in services] != ["api", "bff", "web"]:
            raise DeployError("El orden de servicios debe ser API, BFF y web.")
        for service in services:
            service["url"] = origin(service["url"])
            service["id"] = environ.get(service["id_variable"], "")
            if not re.fullmatch(r"srv-[a-zA-Z0-9]+", service["id"]):
                raise DeployError(f"Falta un ID de servicio válido en {service['id_variable']}.")
        if len({s["id"] for s in services}) != 3 or len({s["url"] for s in services}) != 3:
            raise DeployError("Los tres servicios deben tener IDs y direcciones diferentes.")
        return config
    except (KeyError, TypeError, ValueError, OSError) as error:
        raise DeployError("No se pudo leer la configuración del entorno de test.") from error


def preflight(render, config):
    # Verificar los tres destinos antes de modificar el primero.
    for service in config["services"]:
        actual = render.get(f"/services/{service['id']}")
        auto = actual.get("autoDeployTrigger")
        disabled = auto == "off" if auto is not None else actual.get("autoDeploy") == "no"
        repo = str(actual.get("repo", "")).rstrip("/").removesuffix(".git")
        if (actual.get("id") != service["id"] or actual.get("type") != service["type"]
                or repo != config["repository"] or actual.get("branch") != config["branch"]
                or not disabled or origin(actual.get("serviceDetails", {}).get("url", "")) != service["url"]):
            raise DeployError(f"{service['name']}: revisar ID, tipo, repositorio, rama, URL y Auto-Deploy Off en Render.")


def wait_live(render, service, deploy_id, commit, timeout=900):
    deadline = time.monotonic() + timeout
    previous = None
    while True:
        data = render.get(f"/services/{service['id']}/deploys/{deploy_id}")
        if data.get("id") != deploy_id:
            raise DeployError("Render respondió con otro identificador de despliegue.")
        status = data.get("status")
        if status != previous:
            print(f"{service['name']}: {deploy_id} → {status}", flush=True)
            previous = status
        observed = (data.get("commit") or {}).get("id")
        if observed is not None and observed != commit:
            raise DeployError(f"{service['name']}: el despliegue corresponde a otro commit.")
        if status == "live":
            if observed != commit:
                raise DeployError(f"{service['name']}: falta el commit del despliegue activo.")
            return
        if status in FAILED or status not in PENDING:
            raise DeployError(f"{service['name']}: el despliegue terminó sin éxito ({status}).")
        if time.monotonic() >= deadline:
            raise DeployError(f"{service['name']}: se agotó la espera. Revisar {deploy_id} en Render antes de reintentar.")
        time.sleep(15)


def public_response(url, check, *, frontend_origin=None, timeout=180):
    headers = {"Cache-Control": "no-cache"}
    if frontend_origin:
        headers["Origin"] = frontend_origin
    deadline = time.monotonic() + timeout
    while True:
        try:
            response = request(url, headers=headers)
            if response.status == 200 and check(response):
                return response
        except (DeployError, ValueError, UnicodeError, KeyError):
            pass
        if time.monotonic() >= deadline:
            raise DeployError(f"La verificación pública no pasó: {url}")
        time.sleep(5)


class ModuleScripts(HTMLParser):
    def __init__(self):
        super().__init__()
        self.sources = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "script" and attrs.get("type") == "module" and attrs.get("src"):
            self.sources.append(attrs["src"])


def verify_public(service, commit, frontend_origin):
    base = service["url"]
    if service["name"] in ("api", "bff"):
        public_response(base + "/health", lambda r: r.json() == {"status": "ok"})
        public_response(base + "/version", lambda r: r.json() == {"commit": commit})
    if service["name"] == "bff":
        public_response(base + "/api/hello", lambda r: (
            r.json() == {"message": "Hola desde FastAPI"}
            and r.headers.get("access-control-allow-origin") == frontend_origin
            and "access-control-allow-credentials" not in r.headers
        ), frontend_origin=frontend_origin)
    if service["name"] == "web":
        public_response(base + "/version.json", lambda r: r.json() == {"commit": commit})
        page = public_response(base + "/", lambda r: (
            "text/html" in r.headers.get("content-type", "") and b"<app-root" in r.body
        ))
        parser = ModuleScripts()
        parser.feed(page.body.decode("utf8"))
        scripts = [urljoin(base + "/", src) for src in parser.sources]
        scripts = [src for src in scripts if urlsplit(src).netloc == urlsplit(base).netloc and urlsplit(src).scheme == "https"]
        if not scripts:
            raise DeployError("El HTML de Angular no contiene un módulo JavaScript del sitio.")
        public_response(scripts[0], lambda r: (
            bool(r.body) and r.headers.get("content-type", "").split(";")[0] in ("application/javascript", "text/javascript")
        ))


def summary(text):
    path = os.getenv("GITHUB_STEP_SUMMARY")
    if path:
        with open(path, "a", encoding="utf8") as output:
            output.write(text + "\n")


def rollout(render, config, commit):
    preflight(render, config)
    summary(f"## Despliegue de test\n\nCommit: `{commit}`\n")
    for service in config["services"]:
        print(f"{service['name']}: iniciar despliegue del commit {commit}", flush=True)
        deploy_id = render.start(service["id"], commit)
        summary(f"- {service['name']}: despliegue `{deploy_id}` solicitado.")
        wait_live(render, service, deploy_id, commit)
        verify_public(service, commit, config["services"][2]["url"])
        summary(f"  - Estado live y comprobación pública correctos: {service['url']}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--commit", required=True)
    args = parser.parse_args()
    try:
        if not re.fullmatch(r"[0-9a-f]{40}", args.commit):
            raise DeployError("Se necesita el SHA completo del commit validado.")
        token = os.getenv("RENDER_API_KEY", "")
        if not token:
            raise DeployError("Falta RENDER_API_KEY en los secrets del environment test.")
        config = load_config(Path(__file__).with_name("render-test.json"), os.environ)
        rollout(Render(token), config, args.commit)
    except DeployError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        summary(f"\nFalló la entrega: {error}\n\nRevisar Render antes de reintentar. No se ejecutó rollback automático.")
        return 1
    print("OK: los tres servicios de test ejecutan el commit validado.", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
