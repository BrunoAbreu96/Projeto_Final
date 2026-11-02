"""Apresentação Streamlit; operações e cálculos no package brunus_mes."""
from datetime import datetime
import sqlite3

import pandas as pd
import streamlit as st
from streamlit_autorefresh import st_autorefresh

from brunus_mes.auth import verify_password
from brunus_mes.database import MigrationRequired, check_database
from brunus_mes.pdf_report import generate_shift_pdf
from brunus_mes.reporting import TURNOS, build_shift_report, current_shift
from brunus_mes.repository import active_breakdowns, report_lines, stations
from brunus_mes.services import resolve_breakdown
from brunus_mes.ui_admin import render_administration

st.set_page_config(page_title="BRUNUS MES H-Cell", layout="wide")


def select_current_shift():
    """Atualiza os filtros apenas quando o utilizador pede o turno atual."""
    day, shift = current_shift()
    st.session_state["report_day"] = day
    st.session_state["report_shift"] = shift


if "perfil" not in st.session_state:
    st.title("BRUNUS MES H-Cell")
    st.subheader("Gestão de produção e controlo industrial")
    with st.form("autenticacao"):
        perfil = st.selectbox("Perfil", ["operador", "tecnico", "master"])
        senha = st.text_input("Palavra-passe", type="password")
        autenticar = st.form_submit_button("Autenticar", use_container_width=True)
    with st.expander("Ajuda para entrar"):
        st.write("**Operador:** consulta a produção, as avarias e os relatórios.")
        st.write("**Técnico:** também valida intervenções e resolve avarias.")
        st.write("**Master:** também configura estações, guarda cópias de segurança e gere a demonstração.")
        st.caption("As palavras-passe são definidas na instalação. Se não as recorda, o responsável pela instalação pode voltar a defini-las com gerar_credenciais.py.")
    if autenticar:
        try:
            hash_guardado = st.secrets["credenciais"][f"{perfil}_hash"]
        except (KeyError, FileNotFoundError):
            st.error("Configuração de autenticação indisponível. Execute gerar_credenciais.py.")
        else:
            if verify_password(senha, hash_guardado):
                st.session_state["perfil"] = perfil
                st.rerun()
            else:
                st.error("Credenciais inválidas.")
    st.stop()

perfil = st.session_state["perfil"]
if perfil not in {"operador", "tecnico", "master"}:
    st.session_state.clear()
    st.rerun()

st.sidebar.title("BRUNUS MES")
st.sidebar.write(f"Sessão ativa: **{perfil.upper()}**")
if st.sidebar.button("Terminar sessão", use_container_width=True):
    st.session_state.clear()
    st.rerun()
try:
    check_database()
except FileNotFoundError:
    st.info("Prepare a base de dados no terminal do projeto:")
    st.code("python -m brunus_mes.database init --demo", language="powershell")
    st.stop()
except MigrationRequired:
    st.warning("Esquema anterior: pare o simulador e faça a migração com cópia de segurança.")
    st.code("python -m brunus_mes.database migrate", language="powershell")
    st.stop()
except (sqlite3.Error, OSError) as exc:
    st.error(f"Não foi possível abrir a base de dados: {exc}")
    st.stop()

st_autorefresh(interval=2000, key="brunus_refresh")
st.sidebar.divider()
st.sidebar.subheader("Relatório por data e turno")
if "report_day" not in st.session_state or "report_shift" not in st.session_state:
    select_current_shift()
st.sidebar.button("Voltar ao turno atual", on_click=select_current_shift, use_container_width=True)
dia = st.sidebar.date_input("Data de início do turno", key="report_day")
turno = st.sidebar.selectbox("Turno", list(TURNOS), format_func=TURNOS.get, key="report_shift")
st.sidebar.caption("Turno 2: termina à 01:00 do dia seguinte. Horas civis locais, sem fuso horário.")
try:
    linhas_relatorio = [None] + report_lines()
except (sqlite3.Error, OSError) as exc:
    st.error(f"Não foi possível consultar as linhas do relatório: {exc}")
    st.stop()
if st.session_state.get("report_line") not in linhas_relatorio:
    st.session_state["report_line"] = None
linha_relatorio = st.sidebar.selectbox("Linha do relatório", linhas_relatorio,
    format_func=lambda value: "Todas as linhas" if value is None else value, key="report_line")

try:
    ativas = active_breakdowns()
    todas = stations()
except (sqlite3.Error, OSError) as exc:
    st.error(f"Não foi possível consultar a monitorização: {exc}")
    st.stop()
linhas = sorted({estacao["main_line"] for estacao in todas})
linhas_paradas = {avaria["main_line"] for avaria in ativas}

st.title("BRUNUS MES · H-Cell")
st.caption(f"Dados de simulação · {len(linhas)} linhas · {len(todas)} estações configuradas.")
separadores = st.tabs(["Monitorização em tempo real", "Produção e qualidade", "Avarias e paragens"]
    + (["Administração"] if perfil == "master" else []), key="main_tabs", on_change="rerun")
monitor, indicadores, avarias = separadores[:3]
if perfil == "master":
    with separadores[3]:
        render_administration(perfil)
with monitor:
    st.subheader("Estado atual das linhas")
    st.caption(f"Consulta às {datetime.now():%d/%m/%Y %H:%M:%S} · Atualização automática a cada 2 segundos. Data, turno e linha selecionados só filtram os relatórios.")
    for col, label, value in zip(st.columns(3), ["Linhas configuradas", "Linhas paradas", "Avarias ativas agora"],
            [len(linhas), len(linhas_paradas), len(ativas)]):
        col.metric(label, value)
    if ativas:
        st.error("Há linhas paradas por avarias ativas.")
    else:
        st.success("Sem avarias ativas.")
    alarme = st.checkbox("Ativar aviso sonoro de avarias", value=False)
    if alarme and ativas:
        st.components.v1.html("""<script>
            const audio = new (window.AudioContext || window.webkitAudioContext)();
            const timer = setInterval(() => {
                audio.resume(); const osc = audio.createOscillator(); const gain = audio.createGain();
                osc.frequency.value = 880; gain.gain.value = 0.05;
                osc.connect(gain); gain.connect(audio.destination);
                osc.start(); osc.stop(audio.currentTime + 0.15);
            }, 1000);
            window.addEventListener('unload', () => {clearInterval(timer); audio.close();});
        </script>""", height=0)
    st.subheader("Intervenções pendentes")
    if ativas and perfil == "operador":
        st.info("A resolução de avarias requer uma sessão de técnico ou master.")
    for avaria in ativas:
        with st.expander(f"{avaria['main_line']} · {avaria['estacao']} · {avaria['codigo_erro']}", expanded=True):
            st.write(f"**Diagnóstico:** {avaria['descricao']}")
            st.write(f"**Instrução técnica:** {avaria['causa_provavel']}")
            st.caption(f"{avaria['robo_afetado']} · Início: {avaria['timestamp_inicio']}")
            if perfil in {"tecnico", "master"} and st.button("Validar intervenção técnica", key=f"resolver_{avaria['id']}"):
                try:
                    resolve_breakdown(avaria["id"], perfil)
                except (sqlite3.Error, ValueError, PermissionError) as exc:
                    st.error(f"Intervenção não concluída: {exc}")
                else:
                    st.rerun()
    st.subheader("Estações por linha")
    if not linhas:
        st.info("Sem estações configuradas. Inicialize os dados de demonstração com --demo.")
    colunas = st.columns(min(2, len(linhas)) or 1)
    for indice, linha in enumerate(linhas):
        with colunas[indice % len(colunas)]:
            st.markdown(f"### {linha}")
            locais = [e for e in todas if e["main_line"] == linha]
            avarias_linha = sum(avaria["main_line"] == linha for avaria in ativas)
            if avarias_linha:
                st.error(f"Linha parada · {avarias_linha} avaria(s) ativa(s)")
                st.caption("No simulador, uma avaria suspende a produção de toda a linha.")
            else:
                st.success("Linha sem avarias ativas")
                st.caption("O simulador pode gerar produção nesta linha.")
            cartoes = st.columns(min(2, len(locais)))
            for posicao, estacao in enumerate(locais):
                with cartoes[posicao % len(cartoes)]:
                    st.write(estacao["estacao"])
                    if estacao["status"] == "ERRO":
                        st.error("AVARIA LOCAL")
                    else:
                        st.success("SEM AVARIA LOCAL")
                    st.caption(estacao["nome_processo"])

try:
    report = build_shift_report(dia, turno, main_line=linha_relatorio)
except (sqlite3.Error, ValueError) as exc:
    st.error(f"Não foi possível calcular o relatório: {exc}")
    st.stop()
periodo = f"{report.start:%d/%m/%Y %H:%M} a {report.end:%d/%m/%Y %H:%M}"
ambito = "Todas as linhas" if report.main_line is None else f"Linha: {report.main_line}"
st.sidebar.caption(f"Período: {periodo}. Fim exclusivo.")
st.sidebar.caption(ambito)
if report.snapshot < report.start:
    st.sidebar.info("O turno selecionado ainda não começou.")
elif report.snapshot < report.end:
    st.sidebar.caption("Turno em curso: indicadores até à última atualização.")
else:
    st.sidebar.caption("O período do turno selecionado já terminou.")
if report.has_data:
    sufixo_linha = "" if report.main_line is None else "_" + "".join(
        character if character.isalnum() else "_" for character in report.main_line)[:50]
    st.sidebar.download_button("Descarregar PDF do turno", generate_shift_pdf(report),
        file_name=f"BRUNUS_{dia:%Y%m%d}_turno_{turno}{sufixo_linha}.pdf", mime="application/pdf", use_container_width=True)
else:
    st.sidebar.info("Sem dados para a data e o turno selecionados.")

with indicadores:
    st.subheader("Produção e qualidade do turno")
    st.caption(f"{ambito} · {report.shift_label} · {periodo} · Atualizado às {report.snapshot:%H:%M:%S}")
    if not report.production:
        st.info("Sem registos de produção neste período.")
    else:
        for col, label, value in zip(st.columns(4), ["Peças produzidas", "Peças OK", "Peças rejeitadas", "Qualidade FTT"],
                [report.total_pieces, report.ok_pieces, report.rejected_pieces, f"{report.quality_percent:.1f}%"]):
            col.metric(label, value)
        st.progress(report.quality_percent / 100)
        st.caption("FTT = peças OK / total de peças × 100. Mede qualidade; OEE completo exige também disponibilidade e desempenho.")
        producao = pd.DataFrame(report.production)
        por_linha, por_ciclo = st.columns(2)
        with por_linha:
            st.write("Produção por linha")
            st.bar_chart(producao["main_line"].value_counts())
        with por_ciclo:
            st.write("Tempo de ciclo (segundos)")
            st.line_chart(producao.set_index("timestamp")["tempo_ciclo"])
        st.dataframe(producao[["timestamp", "main_line", "status_peca", "tempo_ciclo"]].rename(columns={
            "timestamp": "Data/hora", "main_line": "Linha", "status_peca": "Resultado", "tempo_ciclo": "Tempo de ciclo (s)",
        }), hide_index=True, width="stretch")
    st.subheader("Estimativas financeiras de demonstração")
    st.caption("Parâmetros fictícios: margem 100 EUR/peça OK, rejeição 35 EUR/peça e paragem 150 EUR/minuto-linha. Não representam resultados contabilísticos.")
    for col, label, value in zip(st.columns(3), ["Resultado estimado", "Custo estimado de rejeição", "Custo estimado de paragem"],
            [report.estimated_result, report.estimated_scrap_cost, report.estimated_downtime_cost]):
        col.metric(label, f"EUR {value:,.2f}")
    st.caption("Resultado estimado = margem das peças OK − custo de rejeição − custo de paragem.")

with avarias:
    st.subheader("Avarias e paragens no período")
    st.caption(f"{ambito} · {periodo}")
    if not report.breakdowns:
        st.info("Sem avarias iniciadas ou paragens sobrepostas ao período.")
    else:
        for col, label, value in zip(st.columns(4), ["Avarias iniciadas no turno", "Avarias com paragem no turno", "Avarias ainda ativas no corte", "Paragem acumulada"],
                [report.occurrences, report.overlapping_breakdowns, report.active_breakdowns, f"{report.downtime_line_seconds:.1f} s-linha"]):
            col.metric(label, value)
        st.caption("Paragens recortadas ao período e à atualização. Sobreposições na mesma linha contam uma vez. As linhas somam segundos-linha; este valor não é a indisponibilidade da célula.")
        for linha, segundos in report.downtime_by_line.items():
            st.write(f"**{linha}:** {segundos:.1f} segundos de paragem.")
        mttr = "Sem reparações concluídas" if report.mttr_seconds is None else f"{report.mttr_seconds:.1f} s"
        st.metric("MTTR das avarias iniciadas no turno e concluídas até ao corte", mttr)
        st.caption("MTTR: duração completa dessas reparações, incluindo tempo fora do turno. Avarias ativas excluídas da média.")
        historico = pd.DataFrame(report.breakdowns)
        tabela_avarias = historico[["main_line", "estacao", "codigo_erro", "descricao", "timestamp_inicio",
            "timestamp_fim", "status", "downtime_seconds", "started_in_shift", "active_at_snapshot"]].rename(columns={
            "main_line": "Linha", "estacao": "Estação", "codigo_erro": "Código", "descricao": "Descrição",
            "timestamp_inicio": "Início", "timestamp_fim": "Fim registado", "status": "Estado registado",
            "downtime_seconds": "Paragem no turno (s)", "started_in_shift": "Iniciada no turno",
            "active_at_snapshot": "Ativa à consulta",
        })
        st.dataframe(tabela_avarias, hide_index=True, width="stretch")
        iniciadas = historico[historico["started_in_shift"]]
        if not iniciadas.empty:
            local, causa = st.columns(2)
            with local:
                st.write("Frequência por estação: ocorrências iniciadas no turno")
                st.bar_chart((iniciadas["main_line"] + " · " + iniciadas["estacao"]).value_counts())
            with causa:
                st.write("Frequência por código de avaria")
                st.bar_chart(iniciadas["codigo_erro"].value_counts())
