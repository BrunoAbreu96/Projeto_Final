"""Interface real do Streamlit, com base e credenciais exclusivamente sintéticas."""
from datetime import date, datetime, timedelta
import hashlib
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from brunus_mes.database import connect, initialize_database, seed_demo_stations
from simulador_continuo import ciclo_fabrica_avancado

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def demo(tmp_path, monkeypatch):
    path = tmp_path / "ui.db"
    initialize_database(path)
    seed_demo_stations(path)
    monkeypatch.setenv("BRUNUS_DB_PATH", str(path))
    day = date.today() - timedelta(days=1)
    ciclo_fabrica_avancado(path, event="OK", main_line="Main A", now=datetime.combine(day, datetime.min.time()).replace(hour=9))
    failure = ciclo_fabrica_avancado(path, event="ERRO", main_line="Main A", now=datetime.combine(day, datetime.min.time()).replace(hour=9, minute=5))
    return path, day, failure["id"]


def app_for(profile=None):
    app = AppTest.from_file(str(ROOT / "dashboard.py"), default_timeout=20)
    salt = "a1" * 16
    digest = hashlib.pbkdf2_hmac("sha256", b"demo-test", bytes.fromhex(salt), 1000).hex()
    # AppTest injects these values in memory; it never reads or writes real secrets.
    app.secrets = {"credenciais": {f"{p}_hash": f"pbkdf2_sha256$1000${salt}${digest}" for p in ("operador", "tecnico", "master")}}
    if profile:
        app.session_state["perfil"] = profile
    return app.run()


def button(app, label):
    return next(value for value in app.button if value.label == label)


def test_login_wrong_password_then_operator_and_logout(demo):
    app = app_for()
    app.text_input[0].set_value("errada")
    button(app, "Autenticar").click().run()
    assert any("Credenciais inválidas" in error.value for error in app.error)
    app.text_input[0].set_value("demo-test")
    button(app, "Autenticar").click().run()
    assert not app.exception
    assert app.session_state["perfil"] == "operador"
    assert not any(b.label == "Validar intervenção técnica" for b in app.button)
    assert not any(b.label == "Eliminar dados de demonstração" for b in app.button)
    button(app, "Terminar sessão").click().run()
    assert not app.exception
    assert any(b.label == "Autenticar" for b in app.button)


def test_technician_resolves_breakdown_from_interface(demo):
    path, _, breakdown_id = demo
    app = app_for("tecnico")
    assert not app.exception
    button(app, "Validar intervenção técnica").click().run()
    assert not app.exception
    with connect(path) as conn:
        row = conn.execute("SELECT status, timestamp_fim FROM registo_avarias WHERE id=?", (breakdown_id,)).fetchone()
        assert row["status"] == "RESOLVIDO"
        assert row["timestamp_fim"]
        assert conn.execute("SELECT COUNT(*) FROM cabines WHERE status='ERRO'").fetchone()[0] == 0


def test_master_clear_requires_confirmation_in_interface(demo):
    path, _, _ = demo
    app = app_for("master")
    assert not app.exception
    button(app, "Eliminar dados de demonstração").click().run()
    with connect(path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM historico_producao").fetchone()[0] == 1
    assert any("confirmação explícita" in error.value for error in app.error)
    confirmation = next(c for c in app.checkbox if c.label.startswith("Confirmo a eliminação"))
    confirmation.check()
    button(app, "Eliminar dados de demonstração").click().run()
    assert not app.exception
    with connect(path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM historico_producao").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM registo_avarias").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM cabines").fetchone()[0] == 8


def test_selected_date_and_shift_control_displayed_metrics(demo):
    _, day, _ = demo
    app = app_for("operador")
    app.date_input[0].set_value(day).run()
    assert not app.exception
    values = {metric.label: metric.value for metric in app.metric}
    assert values["Peças produzidas"] == "1"
    assert values["Qualidade FTT"] == "100.0%"
    next(s for s in app.selectbox if s.label == "Turno").select(2).run()
    assert not app.exception
    # The active breakdown carries into shift 2, but the production does not.
    assert not any(metric.label == "Peças produzidas" for metric in app.metric)
    assert any("Sem registos de produção" in info.value for info in app.info)


def test_missing_database_shows_setup_without_creating_file(tmp_path, monkeypatch):
    path = tmp_path / "absent" / "not-created.db"
    monkeypatch.setenv("BRUNUS_DB_PATH", str(path))
    app = app_for("operador")
    assert not app.exception
    assert any("database init --demo" in code.value for code in app.code)
    assert not path.exists()
