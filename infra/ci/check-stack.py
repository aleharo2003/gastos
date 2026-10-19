"""Comprueba el contrato HTTP de Gastos mediante el proxy o la API directa."""

import argparse
import json
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.request import ProxyHandler, Request, build_opener

SUCCESS_MESSAGE = "Hola desde FastAPI"
ERROR_MESSAGE = "No se pudo consultar FastAPI"


def read_response(url: str) -> tuple[int, str, bytes]:
    # La prueba accede a servicios locales, sin usar un proxy de Internet.
    opener = build_opener(ProxyHandler({}))
    request = Request(url, headers={"Accept": "application/json"})
    try:
        response = opener.open(request, timeout=10)
    except HTTPError as error:
        # Un 502 es una respuesta HTTP que debemos poder comprobar.
        response = error

    with response:
        return response.status, response.headers.get_content_type(), response.read()


def validate_response(status: int, content_type: str, body: bytes, expected: str) -> None:
    expected_status = 200 if expected == "success" else 502
    if status != expected_status:
        raise ValueError(f"Se esperaba HTTP {expected_status}; llego HTTP {status}.")
    if content_type != "application/json":
        raise ValueError(f"Se esperaba JSON; llego {content_type}.")

    data = json.loads(body)
    if not isinstance(data, dict):
        raise ValueError("Se esperaba un objeto JSON.")

    if expected == "success":
        if data.get("message") != SUCCESS_MESSAGE:
            raise ValueError("El mensaje no coincide con el contrato de FastAPI.")
    elif data.get("statusCode") != 502 or data.get("message") != ERROR_MESSAGE:
        raise ValueError("El 502 no contiene el error controlado del BFF.")


def wait_for_success(url: str, wait_seconds: int) -> None:
    deadline = time.monotonic() + wait_seconds
    last_error = "Todavia no se recibio una respuesta."
    print(f"Esperando el recorrido HTTP: {url}", flush=True)

    while True:
        try:
            status, content_type, body = read_response(url)
        except (URLError, OSError) as error:
            last_error = str(error)
        else:
            if status in (502, 503, 504):
                last_error = f"HTTP {status}: los servicios aun no estan disponibles."
            else:
                # Un JSON incorrecto o una ruta equivocada son fallos,
                # no motivos para seguir esperando el arranque.
                validate_response(status, content_type, body, "success")
                return

        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise ValueError(f"El recorrido no estuvo disponible: {last_error}")
        time.sleep(min(2, remaining))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("expected", choices=("success", "unavailable"))
    parser.add_argument("--url", default="http://127.0.0.1:4200/api/hello")
    parser.add_argument("--wait-seconds", type=int, default=120)
    args = parser.parse_args()
    if args.wait_seconds < 0:
        parser.error("--wait-seconds debe ser cero o mayor.")

    try:
        if args.expected == "success":
            wait_for_success(args.url, args.wait_seconds)
            print("OK: HTTP 200 y mensaje de FastAPI correctos.")
        else:
            validate_response(*read_response(args.url), "unavailable")
            print("OK: el BFF devolvio su error controlado HTTP 502.")
    except (ValueError, URLError, OSError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
