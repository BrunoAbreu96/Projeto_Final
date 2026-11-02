"""Formulários de administração; validações e transações ficam nos serviços."""

import os
import sqlite3

import streamlit as st

from .backups import create_backup, list_backups, restore_backup
from .configuration import add_station, delete_station, update_station
from .database import get_db_path
from .demo import generate_demo_event
from .repository import stations
from .services import clear_demo_data, reset_active_breakdowns

ERRORS = (sqlite3.Error, OSError, ValueError, PermissionError, RuntimeError)


def _notice(kind, message):
    st.session_state["admin_notice"] = (kind, message)
    st.rerun()


def _success(message):
    _notice("success", message)


def _perform(action, message):
    try:
        result = action()
    except ERRORS as exc:
        _notice("error", f"Operação não concluída: {exc}")
    else:
        _success(message(result) if callable(message) else message)


def _configuration(profile):
    todas = stations()
    linhas = sorted({row["main_line"] for row in todas})
    st.subheader("Linhas e estações")
    st.caption("Uma linha é criada ao adicionar a sua primeira estação. A configuração aplica-se a esta instalação.")
    if todas:
        st.dataframe([{"Linha": row["main_line"], "Estação": row["estacao"], "Processo": row["nome_processo"]}
            for row in todas], hide_index=True, width="stretch")
    with st.expander("Adicionar estação", expanded=not todas):
        escolha = st.selectbox("Linha da nova estação", [None] + linhas,
            format_func=lambda value: "Criar uma nova linha" if value is None else value)
        with st.form("adicionar_estacao"):
            nova_linha = st.text_input("Nome da nova linha", max_chars=128) if escolha is None else escolha
            nome = st.text_input("Nome da nova estação", max_chars=128)
            processo = st.text_input("Processo da nova estação", max_chars=200)
            adicionar = st.form_submit_button("Adicionar estação")
        if adicionar:
            _perform(lambda: add_station(nova_linha, nome, processo, profile), "Estação adicionada.")
    if todas:
        with st.expander("Editar ou remover estação"):
            por_id = {row["id"]: row for row in todas}
            selecionada = st.selectbox("Estação a editar", list(por_id),
                format_func=lambda value: f"{por_id[value]['main_line']} · {por_id[value]['estacao']}")
            row = por_id[selecionada]
            st.caption("Com histórico, a linha e o nome são preservados. O processo pode ser atualizado. Só é possível remover estações sem avarias e sem produção na linha.")
            with st.form(f"editar_estacao_{selecionada}"):
                linha = st.text_input("Linha da estação", value=row["main_line"], max_chars=128)
                nome = st.text_input("Nome da estação", value=row["estacao"], max_chars=128)
                processo = st.text_input("Processo da estação", value=row["nome_processo"], max_chars=200)
                guardar = st.form_submit_button("Guardar estação")
            if guardar:
                _perform(lambda: update_station(selecionada, linha, nome, processo, profile), "Estação atualizada.")
            with st.form(f"remover_estacao_{selecionada}"):
                confirmar = st.checkbox("Confirmo a remoção desta estação sem histórico")
                remover = st.form_submit_button("Remover estação")
            if remover:
                _perform(lambda: delete_station(selecionada, profile, confirmed=confirmar), "Estação removida.")


def _backups(profile):
    st.subheader("Cópias de segurança")
    st.caption(f"Base selecionada: {get_db_path().name}. A cópia inclui configuração, produção e avarias; as palavras-passe são guardadas separadamente.")
    if st.button("Criar cópia de segurança"):
        _perform(lambda: create_backup(profile), lambda path: f"Cópia criada: {path.name}")
    copies = list_backups()
    if not copies:
        st.info("Ainda não existem cópias de segurança desta base.")
        return
    st.caption("As cópias ficam neste computador. Guarde também uma cópia externa para proteger os dados em caso de avaria do computador.")
    escolhida = st.selectbox("Cópia guardada", copies, format_func=lambda path: path.name)
    st.download_button("Descarregar cópia selecionada", escolhida.read_bytes(),
        file_name=escolhida.name, mime="application/vnd.sqlite3")
    with st.expander("Recuperar uma cópia"):
        st.warning("A recuperação substitui a configuração, a produção e as avarias pelo estado da cópia escolhida. É guardada uma cópia do estado anterior antes da alteração.")
        st.caption("No modo de demonstração manual, o ponto recuperado mantém-se até gerar outro evento. Com o simulador contínuo ativo, novos eventos podem surgir após a recuperação.")
        with st.form("restaurar_backup"):
            st.write(f"Cópia selecionada: **{escolhida.name}**")
            confirmar = st.checkbox("Confirmo a recuperação da cópia selecionada")
            recuperar = st.form_submit_button("Recuperar cópia")
        if recuperar:
            _perform(lambda: restore_backup(escolhida, profile, confirmed=confirmar),
                lambda path: f"Cópia recuperada. Estado anterior guardado em {path.name}.")


def _demonstration(profile):
    st.subheader("Demonstração")
    st.caption("Os eventos manuais permitem ensaiar produção, qualidade e manutenção com dados sintéticos.")
    if os.environ.get("BRUNUS_DEMO_MODE") == "1":
        linhas = sorted({row["main_line"] for row in stations()})
        if linhas:
            eventos = {"Peça OK": "OK", "Peça rejeitada": "REJEITADA", "Avaria na linha": "ERRO"}
            with st.form("evento_demo"):
                linha = st.selectbox("Linha do evento", linhas)
                evento = st.selectbox("Evento de demonstração", list(eventos))
                gerar = st.form_submit_button("Gerar evento")
            if gerar:
                try:
                    result = generate_demo_event(eventos[evento], linha, profile)
                except ERRORS as exc:
                    _notice("error", f"Evento não gerado: {exc}")
                else:
                    if result["event"] == "PARADA":
                        _notice("info", "A linha já tem uma avaria ativa. Resolva a avaria na monitorização antes de gerar produção ou outra avaria nesta linha.")
                    else:
                        _success(f"Evento gerado em {linha}: {evento}. Consulte a monitorização ou os indicadores do turno.")
        else:
            st.info("Adicione uma estação para poder gerar eventos.")
    else:
        st.info("Para gerar eventos neste painel, abra a demonstração através de iniciar_demo.bat.")
    st.divider()
    st.caption("Encerrar avarias preserva ocorrências já resolvidas.")
    if st.button("Encerrar todas as avarias ativas"):
        _perform(lambda: reset_active_breakdowns(profile), lambda total: f"Avarias encerradas: {total}.")
    with st.expander("Eliminar histórico de demonstração"):
        st.warning("A limpeza elimina todo o histórico de produção e avarias da base selecionada. A configuração das estações é conservada.")
        with st.form("limpeza_demo"):
            confirmar = st.checkbox("Confirmo a eliminação dos dados de demonstração")
            limpar = st.form_submit_button("Eliminar dados de demonstração")
        if limpar:
            _perform(lambda: clear_demo_data(profile, confirmed=confirmar), "Dados eliminados; estações repostas.")


def render_administration(profile):
    """A interface é adicional à autorização imposta em cada serviço."""
    if profile != "master":
        raise PermissionError("A administração está reservada ao master.")
    if notice := st.session_state.get("admin_notice"):
        kind, message = notice
        getattr(st, kind)(message)
        if st.button("Fechar mensagem"):
            st.session_state.pop("admin_notice", None)
            st.rerun()
    configuration, backups, demonstration = st.tabs(["Linhas e estações", "Cópias de segurança", "Demonstração"],
        key="admin_tabs", on_change="rerun")
    try:
        with configuration:
            _configuration(profile)
        with backups:
            _backups(profile)
        with demonstration:
            _demonstration(profile)
    except ERRORS as exc:
        st.error(f"Não foi possível consultar a administração: {exc}")
