"""Pruebas del despliegue sin credenciales ni conexiones a servicios reales."""

import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, call, patch
from urllib.error import HTTPError, URLError

import deploy_render as cd
import check_main as guard


COMMIT = "a" * 40
OTHER_COMMIT = "b" * 40
FRONTEND = "https://gastos-test-web.onrender.com"


def response(value=None, *, status=200, headers=None, body=None):
    if body is None:
        body = json.dumps(value).encode()
    return cd.Response(status, headers or {}, body)


def configuration():
    return {
        "repository": "https://github.com/aleharo2003/gastos",
        "branch": "main",
        "services": [
            {"name": name, "id": f"srv-{name}", "id_variable": f"RENDER_{name.upper()}_SERVICE_ID",
             "type": "static_site" if name == "web" else "web_service",
             "url": f"https://gastos-test-{name}.onrender.com"}
            for name in ("api", "bff", "web")
        ],
    }


def service_record(service):
    return {
        "id": service["id"], "type": service["type"],
        "repo": "https://github.com/aleharo2003/gastos.git",
        "branch": "main", "autoDeployTrigger": "off", "autoDeploy": "no",
        "serviceDetails": {"url": service["url"] + "/"},
    }


class TransportTests(unittest.TestCase):
    def test_authenticated_request_targets_render_and_disallows_redirects(self):
        transport = Mock()
        transport.open.return_value.__enter__ = Mock(return_value=transport.open.return_value)
        transport.open.return_value.__exit__ = Mock(return_value=False)
        transport.open.return_value.status = 200
        transport.open.return_value.headers = {"Content-Type": "application/json"}
        transport.open.return_value.read.return_value = b'{"id":"srv-api"}'
        with patch.object(cd, "build_opener", return_value=transport) as factory:
            result = cd.Render("synthetic-token").get("/services/srv-api")
        self.assertEqual(result, {"id": "srv-api"})
        req = transport.open.call_args.args[0]
        self.assertEqual(req.full_url, "https://api.render.com/v1/services/srv-api")
        self.assertEqual(req.get_header("Authorization"), "Bearer synthetic-token")
        handler = factory.call_args.args[0]
        self.assertIsInstance(handler, cd.NoRedirect)
        self.assertIsNone(handler.redirect_request(req, None, 302, "", {}, "https://other.example"))

    def test_get_retries_rate_limit_and_server_failure(self):
        with patch.object(cd, "request", side_effect=[response(status=429), response(status=503), response({"id": "srv-api"})]) as send, patch.object(cd.time, "sleep") as sleep:
            result = cd.Render("synthetic-token").get("/services/srv-api")
        self.assertEqual(result["id"], "srv-api")
        self.assertEqual(send.call_count, 3)
        self.assertEqual(sleep.call_args_list, [call(2), call(4)])

    def test_get_exhausts_retry_budget_and_does_not_retry_auth_failure(self):
        for status, attempts in ((503, 3), (401, 1)):
            with self.subTest(status=status), patch.object(cd, "request", return_value=response(status=status)) as send, patch.object(cd.time, "sleep"):
                with self.assertRaises(cd.DeployError):
                    cd.Render("synthetic-token").get("/services/srv-api")
                self.assertEqual(send.call_count, attempts)

    def test_post_is_not_repeated_after_rejection_or_network_ambiguity(self):
        for outcome in (response(status=429), response(status=503), cd.DeployError("network interruption")):
            with self.subTest(outcome=outcome), patch.object(cd, "request", side_effect=[outcome]) as send, patch.object(cd.time, "sleep") as sleep:
                with self.assertRaises(cd.DeployError):
                    cd.Render("synthetic-token").start("srv-api", COMMIT)
                send.assert_called_once()
                sleep.assert_not_called()

    def test_accepted_deploy_requires_identifier_and_sends_exact_commit(self):
        with patch.object(cd, "request", return_value=response({"id": "dep-example"}, status=201)) as send:
            self.assertEqual(cd.Render("synthetic-token").start("srv-api", COMMIT), "dep-example")
        self.assertEqual(json.loads(send.call_args.kwargs["data"]), {"commitId": COMMIT})
        for body in (b"", b"{}", b"not-json"):
            with self.subTest(body=body), patch.object(cd, "request", return_value=response(status=202, body=body)) as send:
                with self.assertRaisesRegex(cd.DeployError, "Revisar el panel antes de reintentar"):
                    cd.Render("synthetic-token").start("srv-api", COMMIT)
                send.assert_called_once()

    def test_network_error_is_redacted_and_http_error_remains_a_response(self):
        transport = Mock()
        transport.open.side_effect = URLError("synthetic-token")
        with patch.object(cd, "build_opener", return_value=transport):
            with self.assertRaises(cd.DeployError) as failure:
                cd.request("https://api.render.com/v1/services")
        self.assertNotIn("synthetic-token", str(failure.exception))
        transport.open.side_effect = HTTPError("https://example.test", 502, "bad gateway", {}, io.BytesIO(b"{}"))
        with patch.object(cd, "build_opener", return_value=transport):
            self.assertEqual(cd.request("https://example.test").status, 502)


class ConfigurationTests(unittest.TestCase):
    def load(self, config, environ=None):
        environ = environ or {"GITHUB_REPOSITORY": "aleharo2003/gastos", **{f"RENDER_{name.upper()}_SERVICE_ID": f"srv-{name}" for name in ("api", "bff", "web")}}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "render-test.json"
            path.write_text(json.dumps(config), encoding="utf8")
            return cd.load_config(path, environ)

    def test_configuration_resolves_three_distinct_ids_and_normalizes_origins(self):
        config = configuration()
        config["services"][0]["url"] += "/"
        loaded = self.load(config)
        self.assertEqual([s["id"] for s in loaded["services"]], ["srv-api", "srv-bff", "srv-web"])
        self.assertEqual(loaded["services"][0]["url"], "https://gastos-test-api.onrender.com")

    def test_wrong_repository_branch_order_duplicate_or_missing_id_is_rejected(self):
        cases = []
        for field, value in (("branch", "feature/change"), ("repository", "https://github.com/another/repo")):
            config = configuration()
            config[field] = value
            cases.append((config, None))
        config = configuration()
        config["services"].reverse()
        cases.append((config, None))
        config = configuration()
        config["services"][1]["url"] = config["services"][0]["url"]
        cases.append((config, None))
        for ids in ({"RENDER_API_SERVICE_ID": "srv-api", "RENDER_BFF_SERVICE_ID": "srv-api", "RENDER_WEB_SERVICE_ID": "srv-web"}, {}):
            cases.append((configuration(), {"GITHUB_REPOSITORY": "aleharo2003/gastos", **ids}))
        for config, environ in cases:
            with self.subTest(config=config, environ=environ), self.assertRaises(cd.DeployError):
                self.load(config, environ)

    def test_credentials_paths_queries_and_non_https_origins_are_rejected(self):
        for url in (None, 42, "https://[", "http://example.test", "https://user:password@example.test", "https://example.test/path", "https://example.test?key=secret", "https://example.test/#fragment"):
            with self.subTest(url=url), self.assertRaises(cd.DeployError):
                cd.origin(url)

    def test_preflight_checks_all_three_services_and_accepts_legacy_off(self):
        config = configuration()
        records = [service_record(s) for s in config["services"]]
        del records[1]["autoDeployTrigger"]
        render = Mock()
        render.get.side_effect = records
        cd.preflight(render, config)
        self.assertEqual(render.get.call_args_list, [call(f"/services/{s['id']}") for s in config["services"]])
        render.start.assert_not_called()

    def test_preflight_rejects_each_destination_mismatch_before_any_start(self):
        mutations = {
            "id": "srv-other", "type": "static_site", "repo": "https://github.com/other/repo",
            "branch": "other", "autoDeployTrigger": "commit",
            "serviceDetails": {"url": "https://other.onrender.com"},
        }
        for field, value in mutations.items():
            config = configuration()
            records = [service_record(s) for s in config["services"]]
            records[1][field] = value
            render = Mock()
            render.get.side_effect = records
            with self.subTest(field=field), self.assertRaises(cd.DeployError):
                cd.rollout(render, config, COMMIT)
            render.start.assert_not_called()


class DeploymentTests(unittest.TestCase):
    def test_command_rejects_incomplete_sha_or_missing_secret_without_rollout(self):
        for commit in ("aff2bbee", COMMIT):
            with self.subTest(commit=commit), patch.dict(cd.os.environ, {}, clear=True), patch.object(cd.sys, "argv", ["deploy_render.py", "--commit", commit]), patch.object(cd, "rollout") as deploy, patch.object(cd.sys, "stderr", new_callable=io.StringIO):
                self.assertEqual(cd.main(), 1)
                deploy.assert_not_called()

    def test_waits_through_pending_states_until_expected_sha_is_live(self):
        render = Mock()
        render.get.side_effect = [{"id": "dep-api", "status": status, "commit": {"id": COMMIT}} for status in ("queued", "build_in_progress", "pre_deploy_in_progress", "update_in_progress", "live")]
        with patch.object(cd.time, "sleep"):
            cd.wait_live(render, configuration()["services"][0], "dep-api", COMMIT)
        self.assertEqual(render.get.call_count, 5)

    def test_failed_unknown_wrong_id_or_wrong_commit_never_counts_as_live(self):
        cases = [
            {"id": "dep-api", "status": status, "commit": {"id": COMMIT}}
            for status in (*sorted(cd.FAILED), "unexpected_status")
        ] + [
            {"id": "dep-other", "status": "live", "commit": {"id": COMMIT}},
            {"id": "dep-api", "status": "live", "commit": {"id": OTHER_COMMIT}},
            {"id": "dep-api", "status": "live"},
        ]
        for record in cases:
            render = Mock()
            render.get.return_value = record
            with self.subTest(record=record), self.assertRaises(cd.DeployError):
                cd.wait_live(render, configuration()["services"][0], "dep-api", COMMIT)

    def test_wait_deadline_stops_without_canceling_or_creating_another_deploy(self):
        render = Mock()
        render.get.return_value = {"id": "dep-api", "status": "build_in_progress"}
        with patch.object(cd.time, "monotonic", side_effect=[0, 901]), patch.object(cd.time, "sleep") as sleep:
            with self.assertRaisesRegex(cd.DeployError, "agotó la espera"):
                cd.wait_live(render, configuration()["services"][0], "dep-api", COMMIT)
        render.start.assert_not_called()
        sleep.assert_not_called()

    def test_rollout_order_and_stop_after_bff_verification_failure(self):
        config = configuration()
        for failing in (None, "bff"):
            events = []
            render = Mock()
            render.start.side_effect = lambda service_id, commit: events.append(("start", service_id, commit)) or f"dep-{service_id}"
            def verify(service, commit, origin):
                events.append(("verify", service["name"]))
                if service["name"] == failing:
                    raise cd.DeployError("controlled failure")
            def wait(render_arg, service, deploy_id, commit):
                events.append(("live", service["name"]))
            with self.subTest(failing=failing), patch.object(cd, "preflight", side_effect=lambda *_: events.append(("preflight",))), patch.object(cd, "summary"), patch.object(cd, "wait_live", side_effect=wait), patch.object(cd, "verify_public", side_effect=verify):
                if failing:
                    with self.assertRaises(cd.DeployError):
                        cd.rollout(render, config, COMMIT)
                else:
                    cd.rollout(render, config, COMMIT)
            expected = [("preflight",)]
            for name in (("api", "bff") if failing else ("api", "bff", "web")):
                expected.extend([("start", f"srv-{name}", COMMIT), ("live", name), ("verify", name)])
            self.assertEqual(events, expected)


class PublicVerificationTests(unittest.TestCase):
    def test_network_failure_and_non_json_loading_page_can_recover(self):
        with patch.object(cd, "request", side_effect=[cd.DeployError("temporary error"), response(body=b"<html>loading</html>"), response({"status": "ok"})]) as send, patch.object(cd.time, "monotonic", side_effect=[0, 1, 2]), patch.object(cd.time, "sleep"):
            result = cd.public_response("https://example.test/health", lambda r: r.json() == {"status": "ok"})
        self.assertEqual(result.json(), {"status": "ok"})
        self.assertEqual(send.call_count, 3)

    def test_temporary_failure_is_retried_without_authorization(self):
        with patch.object(cd, "request", side_effect=[response(status=503), response({"status": "ok"})]) as send, patch.object(cd.time, "sleep"):
            cd.public_response("https://example.test/health", lambda r: r.json() == {"status": "ok"}, frontend_origin=FRONTEND)
        self.assertEqual(send.call_count, 2)
        for request_call in send.call_args_list:
            self.assertEqual(request_call.kwargs["headers"]["Origin"], FRONTEND)
            self.assertNotIn("Authorization", request_call.kwargs["headers"])

    def test_wrong_json_payload_and_missing_cors_cannot_pass(self):
        for received in (response({"message": "wrong"}, headers={"access-control-allow-origin": FRONTEND}), response({"message": "Hola desde FastAPI"}), response({"message": "Hola desde FastAPI"}, headers={"access-control-allow-origin": "*"}), response({"message": "Hola desde FastAPI"}, headers={"access-control-allow-origin": FRONTEND, "access-control-allow-credentials": "true"})):
            def send(url, **kwargs):
                if url.endswith("/health"):
                    return response({"status": "ok"})
                if url.endswith("/version"):
                    return response({"commit": COMMIT})
                return received
            with self.subTest(received=received), patch.object(cd, "request", side_effect=send), patch.object(cd.time, "monotonic", side_effect=[0, 0, 0, 181]):
                with self.assertRaises(cd.DeployError):
                    cd.verify_public(configuration()["services"][1], COMMIT, FRONTEND)

    def test_bff_verifies_health_exact_version_message_and_origin(self):
        responses = [response({"status": "ok"}), response({"commit": COMMIT}), response({"message": "Hola desde FastAPI"}, headers={"access-control-allow-origin": FRONTEND})]
        with patch.object(cd, "request", side_effect=responses) as send:
            cd.verify_public(configuration()["services"][1], COMMIT, FRONTEND)
        self.assertEqual([c.args[0].split(".com")[-1] for c in send.call_args_list], ["/health", "/version", "/api/hello"])
        self.assertEqual(send.call_args_list[-1].kwargs["headers"]["Origin"], FRONTEND)

    def test_web_requires_expected_version_angular_html_and_local_javascript(self):
        responses = [response({"commit": COMMIT}), response(headers={"content-type": "text/html; charset=utf-8"}, body=b'<html><app-root></app-root><script type="module" src="main-test.js"></script></html>'), response(headers={"content-type": "text/javascript; charset=utf-8"}, body=b"console.log('app');")]
        with patch.object(cd, "request", side_effect=responses) as send:
            cd.verify_public(configuration()["services"][2], COMMIT, FRONTEND)
        self.assertEqual(send.call_args_list[-1].args[0], FRONTEND + "/main-test.js")

    def test_web_rejects_stale_version_non_angular_html_and_non_javascript_asset(self):
        good_html = response(headers={"content-type": "text/html"}, body=b'<app-root></app-root><script type="module" src="main.js"></script>')
        fixtures = [
            [response({"commit": OTHER_COMMIT})],
            [response({"commit": COMMIT}), response(headers={"content-type": "text/html"}, body=b"<html>loading</html>")],
            [response({"commit": COMMIT}), good_html, response(headers={"content-type": "text/html"}, body=b"<html>not an asset</html>")],
        ]
        for fixture in fixtures:
            requests = iter(fixture)
            def send(*args, **kwargs):
                return next(requests)
            clock = [0] * len(fixture) + [181]
            with self.subTest(fixture=fixture), patch.object(cd, "request", side_effect=send), patch.object(cd.time, "monotonic", side_effect=clock):
                with self.assertRaises(cd.DeployError):
                    cd.verify_public(configuration()["services"][2], COMMIT, FRONTEND)

    def test_foreign_module_does_not_trigger_an_external_download(self):
        responses = [response({"commit": COMMIT}), response(headers={"content-type": "text/html"}, body=b'<app-root></app-root><script type="module" src="https://other.test/main.js"></script>')]
        with patch.object(cd, "request", side_effect=responses) as send, self.assertRaisesRegex(cd.DeployError, "no contiene un módulo"):
            cd.verify_public(configuration()["services"][2], COMMIT, FRONTEND)
        self.assertEqual(send.call_count, 2)


class MainGuardTests(unittest.TestCase):
    def run_guard(self, commit=COMMIT, environ=None):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "output"
            settings = {
                "GITHUB_REPOSITORY": "aleharo2003/gastos",
                "GITHUB_TOKEN": "synthetic-github-token",
                "GITHUB_OUTPUT": str(output),
            }
            settings.update(environ or {})
            with patch.dict(cd.os.environ, settings, clear=True), patch.object(cd.sys, "argv", ["check_main.py", "--commit", commit]), patch.object(cd.sys, "stderr", new_callable=io.StringIO):
                status = guard.main()
            return status, output.read_text() if output.exists() else ""

    def test_equal_sha_enables_deploy_and_advanced_main_skips_without_render(self):
        for observed, expected in ((COMMIT, "true"), (OTHER_COMMIT, "false")):
            with self.subTest(observed=observed), patch.object(guard, "current_main", return_value=observed), patch.object(guard, "summary"), patch.object(cd, "Render") as render:
                status, output = self.run_guard()
            self.assertEqual(status, 0)
            self.assertEqual(output, f"deploy={expected}\n")
            render.assert_not_called()

    def test_incomplete_or_invalid_requested_sha_never_queries_main(self):
        for commit in ("aff2bbee", "x" * 40, ""):
            with self.subTest(commit=commit), patch.object(guard, "current_main") as read:
                status, output = self.run_guard(commit)
            self.assertEqual(status, 1)
            self.assertEqual(output, "")
            read.assert_not_called()

    def test_missing_or_malformed_repository_and_missing_token_never_send_http(self):
        for repository, token in (("", "token"), ("owner", "token"), ("https://github.com/owner/repo", "token"), ("owner/repo/extra", "token"), ("aleharo2003/gastos", "")):
            with self.subTest(repository=repository, token=token), patch.object(guard, "request") as send:
                status, output = self.run_guard(environ={"GITHUB_REPOSITORY": repository, "GITHUB_TOKEN": token})
            self.assertEqual(status, 1)
            self.assertEqual(output, "")
            send.assert_not_called()

    def test_github_authorization_uses_shared_client_without_redirects(self):
        self.assertIs(guard.request, cd.request)
        transport = Mock()
        transport.open.return_value.__enter__ = Mock(return_value=transport.open.return_value)
        transport.open.return_value.__exit__ = Mock(return_value=False)
        transport.open.return_value.status = 200
        transport.open.return_value.headers = {"Content-Type": "application/json"}
        transport.open.return_value.read.return_value = json.dumps({"object": {"sha": COMMIT}}).encode()
        with patch.object(cd, "build_opener", return_value=transport) as factory:
            observed = guard.current_main("aleharo2003/gastos", "synthetic-github-token")
        self.assertEqual(observed, COMMIT)
        req = transport.open.call_args.args[0]
        self.assertEqual(req.full_url, "https://api.github.com/repos/aleharo2003/gastos/git/ref/heads/main")
        self.assertEqual(req.get_header("Authorization"), "Bearer synthetic-github-token")
        self.assertIsInstance(factory.call_args.args[0], cd.NoRedirect)

    def test_invalid_token_or_github_failure_never_enables_deploy(self):
        for outcome in (response(status=401), response(status=403), response(status=429), response(status=503), cd.DeployError("connection failed")):
            with self.subTest(outcome=outcome), patch.object(guard, "request", side_effect=[outcome]) as send, patch.object(cd, "Render") as render:
                status, output = self.run_guard()
            self.assertEqual(status, 1)
            self.assertNotIn("deploy=true", output)
            send.assert_called_once()
            render.assert_not_called()

    def test_github_must_return_valid_json_and_a_full_sha(self):
        for result in (response(body=b"<html>error</html>"), response([]), response({}), response({"object": "invalid"}), response({"object": ["invalid"]}), response({"object": 42}), response({"object": {"sha": "aff2bbee"}}), response({"object": {"sha": None}})):
            with self.subTest(result=result), patch.object(guard, "request", return_value=result):
                status, output = self.run_guard()
            self.assertEqual(status, 1)
            self.assertEqual(output, "")

    def test_missing_output_file_configuration_cannot_enable_the_next_step(self):
        with patch.object(guard, "current_main", return_value=COMMIT):
            status, output = self.run_guard(environ={"GITHUB_OUTPUT": ""})
        self.assertEqual(status, 1)
        self.assertEqual(output, "")


if __name__ == "__main__":
    unittest.main()
