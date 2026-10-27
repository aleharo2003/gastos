"""Controles sin Docker ni conexiones: destinos temporales y resultado de drift."""

import importlib.util
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location("check_database", Path(__file__).with_name("check_database.py"))
ci = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = ci
SPEC.loader.exec_module(ci)

SOURCE = '''project_id = "gastos"
[api]
port = 54321
[db]
port = 54322
shadow_port = 54320
major_version = 17
[db.seed]
# Los datos de negocio no forman parte de esta comprobacion.
enabled = true
sql_paths = ["./seed.sql"]
'''
PROJECT = "gastos-ci-0123456789abcdef"


class ConfigTests(unittest.TestCase):
    def test_config_aislada_conserva_version_y_desactiva_semillas(self):
        result, port = ci.make_config(SOURCE, PROJECT, iter([61001, 61002, 61003]))
        parsed = ci.tomllib.loads(result)
        self.assertEqual(port, 61002)
        self.assertEqual(parsed["project_id"], PROJECT)
        self.assertEqual(parsed["db"]["major_version"], 17)
        self.assertFalse(parsed["db"]["seed"]["enabled"])
        self.assertEqual(SOURCE.splitlines()[0], 'project_id = "gastos"')

    def test_rechaza_identificador_del_desarrollo(self):
        with self.assertRaises(ci.CheckError):
            ci.make_config(SOURCE, "gastos", iter([61001, 61002, 61003]))

    def test_rechaza_config_sin_project_id(self):
        with self.assertRaises(ci.CheckError):
            ci.make_config(SOURCE.replace('project_id = "gastos"', ''), PROJECT, iter([1, 2, 3]))

    def test_rechaza_cambio_inesperado_de_semillas(self):
        with self.assertRaises(ci.CheckError):
            ci.make_config(SOURCE.replace("[db.seed]", "[otra]"), PROJECT, iter([1, 2, 3]))

    def test_no_cambia_puertos_comentados_ni_texto_de_urls(self):
        source = SOURCE + '\n# smtp_port = 54325\n[auth]\nsite_url = "http://localhost:3000"\n'
        result, _ = ci.make_config(source, PROJECT, iter([61001, 61002, 61003]))
        self.assertIn('# smtp_port = 54325', result)
        self.assertIn('site_url = "http://localhost:3000"', result)

    def test_comando_siempre_fija_workdir_temporal(self):
        fixture = ci.Fixture(Path("/tmp/gastos-db-ci-example"), PROJECT, 61002)
        command = fixture.cli("db", "reset", "--local", "--no-seed")
        self.assertEqual(command[3:5], ["--workdir", "/tmp/gastos-db-ci-example"])
        self.assertNotIn("--linked", command)
        self.assertNotIn("--db-url", command)

    def test_guard_detecta_project_id_alterado(self):
        with tempfile.TemporaryDirectory(prefix="gastos-db-ci-") as directory:
            root = Path(directory)
            (root / "supabase").mkdir()
            config, port = ci.make_config(SOURCE, PROJECT, iter([61001, 61002, 61003]))
            file = root / "supabase/config.toml"
            file.write_text(config)
            fixture = ci.Fixture(root, PROJECT, port)
            fixture.guard()
            file.write_text(config.replace(PROJECT, "gastos"))
            with self.assertRaises(ci.CheckError):
                fixture.guard()

    def test_container_con_etiqueta_ajena_se_rechaza(self):
        fixture = ci.Fixture(Path("/tmp/gastos-db-ci-example"), PROJECT, 61002)
        result = subprocess.CompletedProcess([], 0, '{"com.supabase.cli.project":"gastos"}', '')
        with patch.object(ci, "checked", return_value=result), self.assertRaises(ci.CheckError):
            ci.verify_container(fixture)

    def test_container_sin_etiqueta_se_rechaza(self):
        fixture = ci.Fixture(Path("/tmp/gastos-db-ci-example"), PROJECT, 61002)
        result = subprocess.CompletedProcess([], 0, 'null', '')
        with patch.object(ci, "checked", return_value=result), self.assertRaises(ci.CheckError):
            ci.verify_container(fixture)


class DriftTests(unittest.TestCase):
    def result(self, code, output):
        return subprocess.CompletedProcess([], code, "", output)

    def test_acepta_fallo_por_la_tabla_de_prueba(self):
        ci.require_drift(self.result(255, "New upgrade operations detected: remove_table gastos_ci_unversioned"))

    def test_rechaza_check_exitoso(self):
        with self.assertRaises(ci.CheckError):
            ci.require_drift(self.result(0, "No new upgrade operations detected."))

    def test_rechaza_fallo_de_red_como_prueba_de_drift(self):
        with self.assertRaises(ci.CheckError):
            ci.require_drift(self.result(1, "could not connect"))

    def test_rechaza_fallo_por_otro_objeto(self):
        with self.assertRaises(ci.CheckError):
            ci.require_drift(self.result(255, "New upgrade operations detected: otra_tabla"))


if __name__ == "__main__":
    unittest.main()
