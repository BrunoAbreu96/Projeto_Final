"""Interface real do Streamlit, com base e credenciais exclusivamente sintéticas."""
from datetime import date, datetime, timedelta
import hashlib
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from brunus_mes.database import connect, initialize_database, seed_demo_stations
import brunus_mes.reporting as reporting
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
    assert not any(tab.label == "Administração" for tab in app.tabs)
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
    next(s for s in app.selectbox if s.label == "Turno").select(1).run()
    assert not app.exception
    values = {metric.label: metric.value for metric in app.metric}
    assert values["Peças produzidas"] == "1"
    assert values["Qualidade FTT"] == "100.0%"
    next(s for s in app.selectbox if s.label == "Turno").select(2).run()
    assert not app.exception
    # The active breakdown carries into shift 2, but the production does not.
    assert not any(metric.label == "Peças produzidas" for metric in app.metric)
    assert any("Sem registos de produção" in info.value for info in app.info)


def test_current_shift_defaults_and_return_button_preserve_manual_selection(demo, monkeypatch):
    _, day, _ = demo
    # At 00:30 the current shift is the previous civil day's shift 2.
    monkeypatch.setattr(reporting, "current_shift", lambda: (day, 2))
    app = app_for("operador")
    assert app.date_input[0].value == day
    assert next(s for s in app.selectbox if s.label == "Turno").value == 2
    app.date_input[0].set_value(day - timedelta(days=1)).run()
    next(s for s in app.selectbox if s.label == "Turno").select(3).run()
    app.run()
    assert app.date_input[0].value == day - timedelta(days=1)
    assert next(s for s in app.selectbox if s.label == "Turno").value == 3
    button(app, "Voltar ao turno atual").click().run()
    assert not app.exception
    assert app.date_input[0].value == day
    assert next(s for s in app.selectbox if s.label == "Turno").value == 2


def test_monitor_distinguishes_stopped_line_from_local_station_fault(demo):
    app = app_for("operador")
    assert not app.exception
    values = {metric.label: metric.value for metric in app.metric}
    assert values["Linhas configuradas"] == "2"
    assert values["Linhas paradas"] == "1"
    assert values["Avarias ativas agora"] == "1"
    assert any("Linha parada · 1 avaria(s) ativa(s)" == item.value for item in app.error)
    assert sum(item.value == "AVARIA LOCAL" for item in app.error) == 1
    assert sum(item.value == "SEM AVARIA LOCAL" for item in app.success) == 7
    assert any("requer uma sessão de técnico" in item.value for item in app.info)


def test_history_tables_present_readable_columns(demo):
    _, day, _ = demo
    app = app_for("operador")
    app.date_input[0].set_value(day).run()
    next(s for s in app.selectbox if s.label == "Turno").select(1).run()
    assert not app.exception
    production, breakdowns = [element.value for element in app.dataframe]
    assert list(production.columns) == ["Data/hora", "Linha", "Resultado", "Tempo de ciclo (s)"]
    assert production.iloc[0]["Resultado"] == "OK"
    assert "Paragem no turno (s)" in breakdowns.columns
    assert breakdowns.iloc[0]["Linha"] == "Main A"
    assert "started_in_shift" not in breakdowns.columns


def test_monitor_includes_every_configured_line(demo):
    path, _, _ = demo
    with connect(path) as conn:
        conn.execute("INSERT INTO cabines (main_line, estacao, nome_processo) VALUES (?, ?, ?)",
            ("Linha de teste C", "Estação 1", "Inspeção"))
    app = app_for("operador")
    assert not app.exception
    assert next(metric for metric in app.metric if metric.label == "Linhas configuradas").value == "3"
    assert any("Linha de teste C" in item.value for item in app.markdown)


def test_master_adds_a_station_and_monitor_updates(demo):
    path, _, _ = demo
    app = app_for("master")
    next(item for item in app.text_input if item.label == "Nome da nova linha").set_value("Linha C")
    next(item for item in app.text_input if item.label == "Nome da nova estação").set_value("Posto 1")
    next(item for item in app.text_input if item.label == "Processo da nova estação").set_value("Inspeção final")
    button(app, "Adicionar estação").click().run()
    assert not app.exception
    with connect(path) as conn:
        assert tuple(conn.execute("SELECT main_line,estacao,nome_processo FROM cabines WHERE main_line='Linha C'").fetchone()) == (
            "Linha C", "Posto 1", "Inspeção final")
    assert next(metric for metric in app.metric if metric.label == "Linhas configuradas").value == "3"


def test_report_line_filter_includes_history_without_current_stations(demo):
    path, day, _ = demo
    with connect(path) as conn:
        conn.execute("INSERT INTO historico_producao(main_line,timestamp,status_peca,tempo_ciclo) VALUES (?,?,?,?)",
            ("Histórica C", f"{day}T09:00:00", "REJEITADA", 12))
    app = app_for("operador")
    app.date_input[0].set_value(day).run()
    next(item for item in app.selectbox if item.label == "Turno").select(1).run()
    assert next(metric for metric in app.metric if metric.label == "Peças produzidas").value == "2"
    next(item for item in app.selectbox if item.label == "Linha do relatório").select("Histórica C").run()
    assert not app.exception
    assert next(metric for metric in app.metric if metric.label == "Peças produzidas").value == "1"
    assert next(metric for metric in app.metric if metric.label == "Qualidade FTT").value == "0.0%"
    assert next(metric for metric in app.metric if metric.label == "Linhas configuradas").value == "2"
    assert app.dataframe[0].value.iloc[0]["Linha"] == "Histórica C"
    app.run()
    assert next(item for item in app.selectbox if item.label == "Linha do relatório").value == "Histórica C"


def test_master_can_generate_a_demo_breakdown_from_interface(demo, monkeypatch):
    path, _, _ = demo
    monkeypatch.setenv("BRUNUS_DEMO_MODE", "1")
    app = app_for("master")
    next(item for item in app.selectbox if item.label == "Linha do evento").select("Main B")
    next(item for item in app.selectbox if item.label == "Evento de demonstração").select("Avaria na linha")
    button(app, "Gerar evento").click().run()
    assert not app.exception
    with connect(path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM registo_avarias WHERE status='ATIVO'").fetchone()[0] == 2
    assert next(metric for metric in app.metric if metric.label == "Linhas paradas").value == "2"
    assert any("Evento gerado em Main B" in item.value for item in app.success)


def test_technician_has_no_administration_controls(demo, monkeypatch):
    monkeypatch.setenv("BRUNUS_DEMO_MODE", "1")
    app = app_for("tecnico")
    assert not app.exception
    assert not any(tab.label == "Administração" for tab in app.tabs)
    assert not any(item.label in {"Gerar evento", "Adicionar estação", "Criar cópia de segurança"} for item in app.button)


def test_master_backup_and_confirmed_recovery_from_interface(demo):
    path, _, _ = demo
    app = app_for("master")
    app.session_state["main_tabs"] = "Administração"
    app.session_state["admin_tabs"] = "Cópias de segurança"
    app.run()
    button(app, "Criar cópia de segurança").click().run()
    assert not app.exception
    app.run()
    assert app.session_state["main_tabs"] == "Administração"
    assert app.session_state["admin_tabs"] == "Cópias de segurança"
    assert any("Cópia criada" in item.value for item in app.success)
    assert len(list((path.parent / "backups").glob("*.db"))) == 1
    with connect(path) as conn:
        conn.execute("INSERT INTO historico_producao(main_line,timestamp,status_peca,tempo_ciclo) VALUES ('Main B','2026-11-02T09:00:00','REJEITADA',11)")
    button(app, "Recuperar cópia").click().run()
    with connect(path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM historico_producao").fetchone()[0] == 2
    next(item for item in app.checkbox if item.label == "Confirmo a recuperação da cópia selecionada").check()
    button(app, "Recuperar cópia").click().run()
    assert not app.exception
    with connect(path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM historico_producao").fetchone()[0] == 1
    assert len(list((path.parent / "backups").glob("*.db"))) == 2


def test_missing_database_shows_setup_without_creating_file(tmp_path, monkeypatch):
    path = tmp_path / "absent" / "not-created.db"
    monkeypatch.setenv("BRUNUS_DB_PATH", str(path))
    app = app_for("operador")
    assert not app.exception
    assert any("database init --demo" in code.value for code in app.code)
    assert not path.exists()
