import sqlite3
import io as sys_io
import pandas as pd
import streamlit as st
from datetime import datetime
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from streamlit_autorefresh import st_autorefresh

# ConfiguraÃ§Ã£o da PÃ¡gina Premium do Software Brunus
st.set_page_config(page_title="Brunus MES H-Cell", layout="wide", initial_sidebar_state="expanded")
DB_NAME = "data/brunus_dev.db"

# Auto-refresh a cada 1 segundo para monitorizaÃ§Ã£o contÃ­nua ultraveloz
st_autorefresh(interval=1000, key="brunus_refresh")

def consultar(sql, params=()):
    with sqlite3.connect(DB_NAME) as conn:
        return pd.read_sql_query(sql, conn, params=params)

def executar(sql, params=()):
    with sqlite3.connect(DB_NAME) as conn:
        conn.cursor().execute(sql, params)
        conn.commit()

# --- ðŸ›°ï¸ MOTOR DE SESSÃƒO PERSISTENTE ---
# --- AUTENTICACAO POR HASH ---
import hashlib
import hmac

def verificar_palavra_passe(palavra, hash_guardado):
    try:
        algoritmo, iteracoes, salt, digest = hash_guardado.split("$")
        if algoritmo != "pbkdf2_sha256":
            return False
        calculado = hashlib.pbkdf2_hmac(
            "sha256",
            palavra.encode("utf-8"),
            bytes.fromhex(salt),
            int(iteracoes)
        ).hex()
        return hmac.compare_digest(calculado, digest)
    except (ValueError, TypeError, AttributeError):
        return False

if "perfil" not in st.session_state:
    st.title("Brunus MES H-Cell Platform")
    st.subheader("Sistema de GestÃ£o de ProduÃ§Ã£o e Controlo Industrial")

    col_login, _ = st.columns(2)
    with col_login:
        perfil = st.selectbox(
            "Selecione o Perfil:",
            ["operador", "tecnico", "master"]
        )
        senha = st.text_input(
            "Palavra-passe de AutenticaÃ§Ã£o:",
            type="password"
        )

        if st.button("Autenticar no Sistema", use_container_width=True):
            try:
                hash_guardado = st.secrets["credenciais"][f"{perfil}_hash"]
            except (KeyError, FileNotFoundError):
                st.error("ConfiguraÃ§Ã£o de autenticaÃ§Ã£o indisponÃ­vel.")
                st.stop()

            if verificar_palavra_passe(senha, hash_guardado):
                st.session_state["perfil"] = perfil
                st.rerun()
            else:
                st.error("Credenciais invÃ¡lidas para o sistema Brunus.")

    st.stop()

st.sidebar.title("ðŸ›¡ï¸ Brunus Security")
st.sidebar.write(f"SessÃ£o Ativa: **{st.session_state['perfil'].upper()}**")

# --- ðŸ“¥ MÃ“DULO EXPORTAÃ‡ÃƒO EXCEL & PDF POR TURNO ---
st.sidebar.markdown("---")
st.sidebar.subheader("ðŸ“¥ RelatÃ³rios por Turno")

turno_selecionado = st.sidebar.selectbox(
    "Selecionar Turno de Trabalho:",
    ["Turno 1 (08:00 - 17:00)", "Turno 2 (17:00 - 01:00)", "Turno 3 (01:00 - 08:00)"]
)

df_prod_export = consultar("SELECT id, main_line, timestamp, status_peca, tempo_ciclo FROM historico_producao ORDER BY id DESC")
df_erros_export = consultar("""
    SELECT r.id, c.main_line, c.estacao, r.robo_afetado, r.codigo_erro, r.descricao, r.timestamp_inicio, r.timestamp_fim, r.status
    FROM registo_avarias r
    LEFT JOIN cabines c ON r.cabine_id = c.id
    ORDER BY r.id DESC
""")

def gerar_pdf_brunus(turno, total_pecas, falhadas, mttr, custo, lucro):
    buffer = sys_io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, title="Brunus Industrial Report")
    story = []
    styles = getSampleStyleSheet()

    title_style = ParagraphStyle('TitleStyle', parent=styles['Heading1'], fontSize=22, textColor=colors.HexColor('#00f0ff'), spaceAfter=15)
    text_style = ParagraphStyle('TextStyle', parent=styles['Normal'], fontSize=11, spaceAfter=8)

    story.append(Paragraph(f"Brunus MES H-Cell - Relatorio Executivo", title_style))
    story.append(Paragraph(f"<b>Data de EmissÃ£o:</b> {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}", text_style))
    story.append(Paragraph(f"<b>Turno Auditado:</b> {turno}", text_style))
    story.append(Spacer(1, 15))

    dados_kpi = [
        ["Indicador Industrial", "Valor Registado"],
        ["Volume Processado Total", f"{total_pecas} un"],
        ["Pecas com Conformidade (OK)", f"{total_pecas - falhadas} un"],
        ["Scrap Rejeitado (Defeito)", f"{falhadas} un"],
        ["Tempo Medio de Reparacao (MTTR)", f"{mttr}"],
        ["Prejuizo por Downtime", f"EUR {custo:,.2f}"],
        ["Lucro Liquido Gerado", f"EUR {lucro:,.2f}"]
    ]
    t = Table(dados_kpi, colWidths=[250, 150])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (1,0), colors.HexColor('#1e1e24')),
        ('TEXTCOLOR', (0,0), (1,0), colors.white),
        ('FONTNAME', (0,0), (1,0), 'Helvetica-Bold'),
        ('BOTTOMPADDING', (0,0), (-1,-1), 8),
        ('BACKGROUND', (0,1), (-1,-1), colors.HexColor('#f8f9fa')),
        ('GRID', (0,0), (-1,-1), 1, colors.HexColor('#dddddd')),
    ]))
    story.append(t)

    doc.build(story)
    buffer.seek(0)
    return buffer

segundos_totais_n = 0
if not df_erros_export.empty:
    finais_n = (df_erros_export['timestamp_fim'].notna()) & ((df_erros_export['status'] == 'RESOLVED') | (df_erros_export['status'] == 'RESOLVIDO'))
    if finais_n.any():
        duracao_n = (pd.to_datetime(df_erros_export.loc[finais_n, 'timestamp_fim']) - pd.to_datetime(df_erros_export.loc[finais_n, 'timestamp_inicio'])).dt.total_seconds().astype(int)
        segundos_totais_n = sum(duracao_n.tolist())

prejuizo_downtime_n = (segundos_totais_n / 60) * 150
pecas_ok_n = len(df_prod_export[df_prod_export["status_peca"] == "OK"]) if not df_prod_export.empty else 0
pecas_falhadas_n = len(df_prod_export[df_prod_export["status_peca"] == "REJEITADA"]) if not df_prod_export.empty else 0

receita_bruta_n = pecas_ok_n * 300.00
lucro_teorico_n = pecas_ok_n * 100.00
prejuizo_scrap_n = pecas_falhadas_n * 35.00
lucro_liquido_n = lucro_teorico_n - (prejuizo_downtime_n + prejuizo_scrap_n)
mttr_txt = "0s"
if not df_erros_export.empty and finais_n.any():
    mttr_txt = f"{duracao_n.mean():.1f}s"

if not df_prod_export.empty or not df_erros_export.empty:
    pdf_data = gerar_pdf_brunus(turno_selecionado, len(df_prod_export), pecas_falhadas_n, mttr_txt, prejuizo_downtime_n, lucro_liquido_n)
    st.sidebar.download_button(
        label="ðŸ“„ Descarregar PDF do Turno",
        data=pdf_data,
        file_name=f"Relatorio_Brunus_Turno_{datetime.now().strftime('%Y%m%d')}.pdf",
        mime="application/pdf",
        use_container_width=True
    )
else:
    st.sidebar.caption("Aguardando ciclos para relatÃ³rios.")

if st.sidebar.button("Terminar SessÃ£o (Logout)", use_container_width=True):
    st.session_state.pop("perfil", None)
    st.rerun()

if st.session_state["perfil"] == "master":
    st.sidebar.markdown("---")
    st.sidebar.subheader("ðŸ‘‘ Comandos Master Pro")
    if st.sidebar.button("âš¡ ForÃ§ar Reset Global da CÃ©lula", use_container_width=True):
        executar("UPDATE cabines SET status = 'OK'")
        executar("UPDATE registo_avarias SET status = 'RESOLVIDO', timestamp_fim = ?", (datetime.now().isoformat(),))
        st.rerun()
    if st.sidebar.button("ðŸ—‘ï¸ Reset de Turno (Limpar Dados)", use_container_width=True):
        executar("DELETE FROM historico_producao")
        executar("DELETE FROM registo_avarias")
        executar("UPDATE cabines SET status = 'OK'")
        st.rerun()

# --- INTERFACE DE MERCADO BRUNUS ---
st.markdown("""
    <div style="background-color:#111116; padding:20px; border-radius:10px; border-left: 5px solid #00f0ff; margin-bottom:20px;">
        <h1 style="color:white; margin:0;">ðŸŽï¸ Brunus H-Cell Automation Control</h1>
        <p style="color:#666; margin:5px 0 0 0;">Digital Twin & Performance Analytics Core (Porsche Line Sinc)</p>
    </div>
""", unsafe_allow_html=True)

aba1, aba2, aba3 = st.tabs(["ðŸ”§ MonitorizaÃ§Ã£o em Tempo Real", "ðŸ“Š EficiÃªncia & Qualidade OEE", "ðŸ“œ Logs de Auditoria & Pareto"])

# --- ABA 1: MONITORIZAÃ‡ÃƒO PARALELA, DIAGNÃ“STICO & TRATAMENTO DE REPARAÃ‡ÃƒO ---
with aba1:
    erros = consultar("SELECT r.*, c.main_line, c.estacao FROM registo_avarias r JOIN cabines c ON r.cabine_id = c.id WHERE r.status = 'ATIVO'")
    if not erros.empty:
        st.error("ðŸš¨ CRITICAL BREAKDOWN: CÃ‰LULA DE MONTAGEM BLOQUEADA")

        st.components.v1.html("""
            <script>
                if (!window.audioContext) { window.audioContext = new (window.AudioContext || window.webkitAudioContext)(); }
                function tocarBip() {
                    let osc = window.audioContext.createOscillator(); let gain = window.audioContext.createGain();
                    osc.type = 'sawtooth'; osc.frequency.setValueAtTime(880, window.audioContext.currentTime);
                    gain.gain.setValueAtTime(0.12, window.audioContext.currentTime);
                    osc.connect(gain); gain.connect(window.audioContext.destination);
                    osc.start(); osc.stop(window.audioContext.currentTime + 0.15);
                }
                if (!window.intervaloAlarme) { window.intervaloAlarme = setInterval(tocarBip, 800); }
            </script>
        """, height=0)

        for _, row in erros.iterrows():
            with st.expander(f"âŒ Falha Ativa: {row['main_line']} - {row['estacao']} ({row['codigo_erro']})", expanded=True):
                st.write(f"**DiagnÃ³stico:** {row['descricao']} | **InstruÃ§Ã£o TÃ©cnica:** {row['causa_provavel']}")
                if st.session_state["perfil"] in ["tecnico", "master"]:
                    # ReparaÃ§Ã£o blindada com ID estÃ¡tico e st.rerun() perfeitamente encadeado
                    if st.button(f"Validar IntervenÃ§Ã£o TÃ©cnica ({row['codigo_erro']})", key=f"reparar_{row['id']}"):
                        executar("UPDATE registo_avarias SET status = 'RESOLVIDO', timestamp_fim = ? WHERE id = ?", (datetime.now().isoformat(), row['id']))
                        executar("UPDATE cabines SET status = 'OK' WHERE id = ?", (row['cabine_id'],))
                        st.rerun()
    else:
        st.success("âœ… CÃ©lula de montagem em produÃ§Ã£o contÃ­nua nominal. Estado estÃ¡vel.")
        st.components.v1.html("<script>if(window.intervaloAlarme){clearInterval(window.intervaloAlarme); window.intervaloAlarme=null;}</script>", height=0)

    # --- ðŸš¨ INJECÃ‡ÃƒO DO ESTILO DA SIRENE DA POLÃCIA (HTML/CSS GLOBAL) ---
    st.markdown("""
        <style>
            @keyframes sirene_policia {
                0% { background-color: #ff0000; box-shadow: 0 0 20px #ff0000; color: white; }
                100% { background-color: #0000ff; box-shadow: 0 0 20px #0000ff; color: white; }
            }
            .sirene-container {
                animation: sirene_policia 0.3s infinite alternate;
                text-align: center;
                border-radius: 6px;
                padding: 10px;
                font-weight: bold;
                font-size: 14px;
            }
        </style>
    """, unsafe_allow_html=True)

    colA, colB = st.columns(2)
    with colA:
        st.markdown("### ðŸ’» MAIN A (Fluxo Esquerdo)")
        df_A = consultar("SELECT estacao, nome_processo, status FROM cabines WHERE main_line = 'Main A'")
        cols_cards_A = st.columns(4)
        for idx, row_card in df_A.iterrows():
            with cols_cards_A[idx % 4]:
                st.markdown(f"**{row_card['estacao']}**")
                if row_card['status'] == 'ERRO':
                    st.markdown('<div class="sirene-container">ðŸš¨ SIRENE</div>', unsafe_allow_html=True)
                else:
                    st.success("â— ONLINE")
                st.caption(row_card['nome_processo'])

    with colB:
        st.markdown("### ðŸ’» MAIN B (Fluxo Direito)")
        df_B = consultar("SELECT estacao, nome_processo, status FROM cabines WHERE main_line = 'Main B'")
        cols_cards_B = st.columns(4)
        for idx, row_card in df_B.iterrows():
            with cols_cards_B[idx % 4]:
                st.markdown(f"**{row_card['estacao']}**")
                if row_card['status'] == 'ERRO':
                    st.markdown('<div class="sirene-container">ðŸš¨ SIRENE</div>', unsafe_allow_html=True)
                else:
                    st.success("â— ONLINE")
                st.caption(row_card['nome_processo'])

# --- ABA 2: ANÃLISE DE PRODUTIVIDADE, OEE & FLUXO FINANCEIRO ---
with aba2:
    st.subheader("ðŸ“Š Painel de Performance Financeira e Operacional")
    df_prod = consultar("SELECT * FROM historico_producao")
    df_erros_fin = consultar("SELECT timestamp_inicio, timestamp_fim, status FROM registo_avarias")

    if not df_prod.empty:
        prod_A = len(df_prod[df_prod["main_line"] == "Main A"])
        prod_B = len(df_prod[df_prod["main_line"] == "Main B"])
        pecas_ok = len(df_prod[df_prod["status_peca"] == "OK"])
        pecas_falhadas = len(df_prod[df_prod["status_peca"] == "REJEITADA"])
        taxa_ftt = round((pecas_ok / len(df_prod)) * 100, 1) if len(df_prod) > 0 else 0

        # Estimativas financeiras do simulador â€” ajustar aos valores reais da fÃ¡brica
        lucro_por_peca_ok = 100.00
        custo_scrap_unidade = 35.00
        custo_downtime_minuto = 150.00

        lucro_bruto_teorico = pecas_ok * lucro_por_peca_ok
        prejuizo_scrap_total = pecas_falhadas * custo_scrap_unidade

        total_segundos_parados = 0
        if not df_erros_fin.empty:
            finais_fin = (df_erros_fin['timestamp_fim'].notna()) & ((df_erros_fin['status'] == 'RESOLVED') | (df_erros_fin['status'] == 'RESOLVIDO'))
            if finais_fin.any():
                total_segundos_parados = (pd.to_datetime(df_erros_fin.loc[finais_fin, 'timestamp_fim']) - pd.to_datetime(df_erros_fin.loc[finais_fin, 'timestamp_inicio'])).dt.total_seconds().sum()
        prejuizo_downtime_total = (total_segundos_parados / 60) * custo_downtime_minuto

        lucro_liquido_real = lucro_bruto_teorico - (prejuizo_scrap_total + prejuizo_downtime_total)
        faturamento_bruto = pecas_ok * 300.00

        col_f1, col_f2, col_f3, col_f4 = st.columns(4)
        if lucro_liquido_real >= 0:
            col_f1.metric(label="ðŸ’° Resultado Operacional Estimado", value=f"â‚¬ {lucro_liquido_real:,.2f}", delta=f"Faturado: â‚¬{faturamento_bruto:,.0f}")
        else:
            col_f1.metric(label="ðŸ’° Resultado Operacional Estimado", value=f"â‚¬ {lucro_liquido_real:,.2f}", delta="Alerta: OperaÃ§Ã£o em PrejuÃ­zo", delta_color="inverse")

        col_f2.metric(label="ðŸ“¦ Volume Total", value=f"{len(df_prod)} un", delta=f"Lado A: {prod_A} | Lado B: {prod_B}")
        col_f3.metric(label="âŒ PrejuÃ­zo (Scrap)", value=f"â‚¬ {prejuizo_scrap_total:,.2f}", delta=f"{pecas_falhadas} un rejeitadas", delta_color="inverse")
        col_f4.metric(label="ðŸ›‘ PrejuÃ­zo (Downtime)", value=f"â‚¬ {prejuizo_downtime_total:,.2f}", delta=f"{int(total_segundos_parados)}s de paragem", delta_color="inverse")

        st.markdown(f"**Indicador Global de Qualidade (FTT): {taxa_ftt}% (Meta de FÃ¡brica: 98.5%)**")
        st.progress(taxa_ftt / 100)
        st.markdown("---")

        cg1, cg2 = st.columns(2)
        with cg1:
            st.subheader("ðŸ“Š DistribuiÃ§Ã£o de PeÃ§as por Linha")
            st.bar_chart(df_prod["main_line"].value_counts())
        with cg2:
            st.subheader("â±ï¸ HistÃ³rico de Estabilidade de CadÃªncia (Segundos)")
            st.line_chart(df_prod["tempo_ciclo"])
    else:
        st.info("â„¹ï¸ Aguardando dados de produÃ§Ã£o do motor Brunus para iniciar a auditoria financeira...")

# --- ABA 3: HISTÃ“RICO, MTTR, PARETO & CUSTO FINANCEIRO ---
with aba3:
    st.subheader("ðŸ“œ Engenharia de ManutenÃ§Ã£o & Impacto Financeiro")
    df_hist = consultar("SELECT r.id, c.main_line, c.estacao, r.robo_afetado, r.codigo_erro, r.descricao, r.timestamp_inicio, r.timestamp_fim, r.status FROM registo_avarias r LEFT JOIN cabines c ON r.cabine_id = c.id ORDER BY r.id DESC")

    if not df_hist.empty:
        df_hist['Tempo de IntervenÃ§Ã£o'] = "â±ï¸ Ativo..."
        tempos = []
        finais = (df_hist['timestamp_fim'].notna()) & ((df_hist['status'] == 'RESOLVED') | (df_hist['status'] == 'RESOLVIDO'))
        df_hist['Custo da Paragem'] = "â±ï¸ A calcular..."

        if finais.any():
            duracao = (pd.to_datetime(df_hist.loc[finais, 'timestamp_fim']) - pd.to_datetime(df_hist.loc[finais, 'timestamp_inicio'])).dt.total_seconds().astype(int)
            tempos = duracao.tolist()
            df_hist.loc[finais, 'Tempo de IntervenÃ§Ã£o'] = [f"{d//60} min {d%60}s" if d//60 > 0 else f"{d%60}s" for d in duracao]
            custos_calculados = (duracao / 60) * 150
            df_hist.loc[finais, 'Custo da Paragem'] = custos_calculados.map("â‚¬{:,.2f}".format)

        cols_metricas = st.columns(3)
        cols_metricas[0].metric("Eventos Registados no Turno", len(df_hist))

        if tempos:
            cols_metricas[1].metric("Tempo MÃ©dio de ReparaÃ§Ã£o (MTTR)", f"{sum(tempos)/len(tempos):.1f}s")
            segundos_totais = sum(tempos)
            prejuizo_total = (segundos_totais / 60) * 150
            cols_metricas[2].metric(label="PrejuÃ­zo por Downtime (Turno)", value=f"â‚¬{prejuizo_total:,.2f}", delta="Cost Rate: 150â‚¬/min", delta_color="inverse")
        else:
            cols_metricas[1].metric("Tempo MÃ©dio de ReparaÃ§Ã£o (MTTR)", "0s")
            cols_metricas[2].metric(label="PrejuÃ­zo por Downtime (Turno)", value="â‚¬0.00")

        st.markdown("---")
        col_esq, col_dir = st.columns(2)
        with col_esq:
            st.subheader("ðŸ“ Pareto: Onde estÃ£o as paragens? (Local)")
            df_hist["Local da Falha"] = df_hist["main_line"].fillna("Mains") + " - " + df_hist["estacao"].fillna("EstaÃ§Ã£o") + " (" + df_hist["robo_afetado"].fillna("RobÃ´") + ")"
            st.bar_chart(df_hist["Local da Falha"].value_counts())
        with col_dir:
            st.subheader("ðŸ” Pareto: Quais sÃ£o as avarias mais frequentes? (Causa)")
            df_hist["Tipo de Defeito"] = df_hist["codigo_erro"] + " - " + df_hist["descricao"]
            st.bar_chart(df_hist["Tipo de Defeito"].value_counts())

        st.markdown("---")
        st.subheader("ðŸ“‹ Logs Gerais Auditados com AnÃ¡lise de Custo")
        colunas_tabela = ['main_line', 'estacao', 'robo_afetado', 'codigo_erro', 'Tempo de IntervenÃ§Ã£o', 'Custo da Paragem', 'status']
        st.dataframe(df_hist[colunas_tabela], hide_index=True, use_container_width=True)
    else:
        st.info("âœ… Nenhuma paragem registada no turno atual. Custo de Downtime: â‚¬0.00")
