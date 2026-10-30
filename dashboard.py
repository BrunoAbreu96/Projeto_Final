"""Apresentação Streamlit; operações e cálculos no package brunus_mes."""
from datetime import date
import sqlite3

import pandas as pd
import streamlit as st
from streamlit_autorefresh import st_autorefresh

from brunus_mes.auth import verify_password
from brunus_mes.database import MigrationRequired, check_database
from brunus_mes.pdf_report import generate_shift_pdf
from brunus_mes.reporting import TURNOS, build_shift_report
from brunus_mes.repository import active_breakdowns, stations
from brunus_mes.services import clear_demo_data, reset_active_breakdowns, resolve_breakdown

st.set_page_config(page_title="BRUNUS MES H-Cell", layout="wide")

if "perfil" not in st.session_state:
    st.title("BRUNUS MES H-Cell")
    st.subheader("Gestão de produção e controlo industrial")
    with st.form("autenticacao"):
        perfil = st.selectbox("Perfil", ["operador", "tecnico", "master"])
        senha = st.text_input("Palavra-passe", type="password")
        autenticar = st.form_submit_button("Autenticar", use_container_width=True)
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
dia = st.sidebar.date_input("Data de início do turno", value=date.today())
turno = st.sidebar.selectbox("Turno", list(TURNOS), format_func=TURNOS.get)
st.sidebar.caption("Turno 2: termina à 01:00 do dia seguinte. Horas civis locais, sem fuso horário.")

if perfil == "master":
    with st.sidebar.expander("Operações de demonstração"):
        st.caption("Encerrar avarias preserva ocorrências já resolvidas.")
        if st.button("Encerrar todas as avarias ativas"):
            try:
                total = reset_active_breakdowns(perfil)
            except (sqlite3.Error, ValueError, PermissionError) as exc:
                st.error(f"Operação não concluída: {exc}")
            else:
                st.success(f"Avarias encerradas: {total}.")
        st.warning("A limpeza elimina todo o histórico de produção e avarias desta base de demonstração.")
        with st.form("limpeza_demo"):
            confirmar = st.checkbox("Confirmo a eliminação dos dados de demonstração")
            limpar = st.form_submit_button("Eliminar dados de demonstração")
        if limpar:
            try:
                clear_demo_data(perfil, confirmed=confirmar)
            except (sqlite3.Error, ValueError, PermissionError) as exc:
                st.error(f"Limpeza não concluída: {exc}")
            else:
                st.success("Dados eliminados; estações repostas.")

st.title("BRUNUS MES · H-Cell")
st.caption("Monitorização de duas linhas e oito estações com dados de simulação.")
monitor, indicadores, avarias = st.tabs(["Monitorização em tempo real", "Produção e qualidade", "Avarias e paragens"])
with monitor:
    st.subheader("Estado atual das linhas")
    st.caption("Avarias atualmente ativas, independentemente do turno selecionado.")
    ativas = active_breakdowns()
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
    todas = stations()
    for coluna, linha in zip(st.columns(2), ("Main A", "Main B")):
        with coluna:
            st.markdown(f"### {linha}")
            locais = [e for e in todas if e["main_line"] == linha]
            if not locais:
                st.info("Sem estações. Inicialize dados de demonstração com --demo.")
            for cartao, estacao in zip(st.columns(max(1, len(locais))), locais):
                with cartao:
                    st.write(estacao["estacao"])
                    if estacao["status"] == "ERRO":
                        st.error("PARADA")
                    else:
                        st.success("ONLINE")
                    st.caption(estacao["nome_processo"])

try:
    report = build_shift_report(dia, turno)
except (sqlite3.Error, ValueError) as exc:
    st.error(f"Não foi possível calcular o relatório: {exc}")
    st.stop()
periodo = f"{report.start:%d/%m/%Y %H:%M} a {report.end:%d/%m/%Y %H:%M}"
st.sidebar.caption(f"Período: {periodo}. Fim exclusivo.")
if report.has_data:
    st.sidebar.download_button("Descarregar PDF do turno", generate_shift_pdf(report),
        file_name=f"BRUNUS_{dia:%Y%m%d}_turno_{turno}.pdf", mime="application/pdf", use_container_width=True)
else:
    st.sidebar.info("Sem dados para a data e o turno selecionados.")

with indicadores:
    st.subheader("Produção e qualidade do turno")
    st.caption(f"{report.shift_label} · {periodo} · Atualizado às {report.snapshot:%H:%M:%S}")
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
        st.dataframe(producao, hide_index=True, width="stretch")
    st.subheader("Estimativas financeiras de demonstração")
    st.caption("Parâmetros fictícios: margem 100 EUR/peça OK, rejeição 35 EUR/peça e paragem 150 EUR/minuto-linha. Não representam resultados contabilísticos.")
    for col, label, value in zip(st.columns(3), ["Resultado estimado", "Custo estimado de rejeição", "Custo estimado de paragem"],
            [report.estimated_result, report.estimated_scrap_cost, report.estimated_downtime_cost]):
        col.metric(label, f"EUR {value:,.2f}")
    st.caption("Resultado estimado = margem das peças OK − custo de rejeição − custo de paragem.")

with avarias:
    st.subheader("Avarias e paragens no período")
    st.caption(periodo)
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
        st.dataframe(historico, hide_index=True, width="stretch")
        iniciadas = historico[historico["started_in_shift"]]
        if not iniciadas.empty:
            local, causa = st.columns(2)
            with local:
                st.write("Frequência por estação: ocorrências iniciadas no turno")
                st.bar_chart((iniciadas["main_line"] + " · " + iniciadas["estacao"]).value_counts())
            with causa:
                st.write("Frequência por código de avaria")
                st.bar_chart(iniciadas["codigo_erro"].value_counts())
