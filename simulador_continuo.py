import sqlite3
import random
import time
from datetime import datetime

DB_NAME = "data/brunus_dev.db"

def iniciar_base_dados_avancada():
    """Cria a estrutura de dados para 2 Mains, 8 Estações e 2 Robôs por cabine."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    # 1. Criar tabelas com colunas para identificar o Lado (Main) e o Robô afetado
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS cabines (
            id INTEGER PRIMARY KEY,
            main_line TEXT,
            estacao TEXT,
            nome_processo TEXT,
            status TEXT DEFAULT 'OK'
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS registo_avarias (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cabine_id INTEGER,
            robo_afetado TEXT,
            codigo_erro TEXT,
            descricao TEXT,
            causa_provavel TEXT,
            timestamp_inicio TEXT,
            timestamp_fim TEXT,
            status TEXT
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS historico_producao (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            main_line TEXT,
            timestamp TEXT,
            status_peca TEXT,
            tempo_ciclo REAL
        )
    """)

    # 2. Inserir as 8 Estações Reais da célula de montagem (Lado A e Lado B)
    estacoes_iniciais = [
        (1, 'Main A', 'Estação 1', 'Alimentação & Pick/Place Frame'),
        (2, 'Main A', 'Estação 2', 'Montagem e Aparafusamento PCB'),
        (3, 'Main A', 'Estação 3', 'União Óptica da Lente TFT'),
        (4, 'Main A', 'Estação 4', 'Teste de Fim de Linha (EOL) A'),
        (5, 'Main B', 'Estação 1', 'Alimentação & Pick/Place Frame'),
        (6, 'Main B', 'Estação 2', 'Montagem e Aparafusamento PCB'),
        (7, 'Main B', 'Estação 3', 'União Óptica da Lente TFT'),
        (8, 'Main B', 'Estação 4', 'Teste de Fim de Linha (EOL) B')
    ]

    for est in estacoes_iniciais:
        cursor.execute("""
            INSERT OR IGNORE INTO cabines (id, main_line, estacao, nome_processo)
            VALUES (?, ?, ?, ?)
        """, est)

    conn.commit()
    conn.close()
    print("🏭 Estrutura Industrial H-Cell (2 Mains, 8 Estações) Inicializada!")

def ciclo_fabrica_avancado():
    """Simula a produção paralela e avarias específicas por linha e robô."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    linha_atual = random.choice(["Main A", "Main B"])

    # Verificar se o lado atual está parado devido a algum erro ativo
    cursor.execute("""
        SELECT r.codigo_erro, c.estacao, r.robo_afetado
        FROM registo_avarias r
        JOIN cabines c ON r.cabine_id = c.id
        WHERE r.status = 'ATIVO' AND c.main_line = ?
    """, (linha_atual,))
    avaria = cursor.fetchone()

    if avaria:
        print(f"🛑 [{linha_atual} PARADA] Erro ativo na {avaria[1]} ({avaria[0]}): Falha no {avaria[2]}. Aguardando Rework...")
        conn.close()
        return

    tempo_ciclo = round(random.uniform(9.5, 12.8), 2)
    # Probabilidades corrigidas de sintaxe (92% OK, 5% Rejeitada, 3% Erro)
    evento = random.choices(["OK", "REJEITADA", "ERRO"], weights=(92, 5, 3))[0]

    if evento == "OK":
        cursor.execute("INSERT INTO historico_producao (main_line, timestamp, status_peca, tempo_ciclo) VALUES (?, ?, 'OK', ?)", (linha_atual, datetime.now().isoformat(), tempo_ciclo))
        print(f"✅ [{linha_atual}] Cluster Porsche OK! Tempo: {tempo_ciclo}s")

    elif evento == "REJEITADA":
        cursor.execute("INSERT INTO historico_producao (main_line, timestamp, status_peca, tempo_ciclo) VALUES (?, ?, 'REJEITADA', ?)", (linha_atual, datetime.now().isoformat(), tempo_ciclo))
        print(f"❌ [{linha_atual} - QUALIDADE] Falha geométrica detetada na lente.")

    else:
        # Ir buscar as cabines específicas da linha atual
        cursor.execute("SELECT id, estacao FROM cabines WHERE main_line = ?", (linha_atual,))
        cabines_da_linha = cursor.fetchall()
        cabine_sorteada = random.choice(cabines_da_linha)

        robo_sorteado = random.choice(["Robô 1", "Robô 2"])

        erros_complexos = [
            ("ERR_R_102", "Perda de sincronismo na trajetória fluida", "Efetuar calibração zero do eixo J3 do braço robótico."),
            ("ERR_R_205", "Alimentador de parafusos sem stock ou obstruído", "Verificar calha vibratória e repor parafusos M3."),
            ("ERR_R_308", "Falha de comunicação Ethernet/IP com o controlador", "Verificar cabo de rede do Robô e reiniciar switch da cabine.")
        ]
        cod, desc, causa = random.choice(erros_complexos)

        cursor.execute("UPDATE cabines SET status = 'ERRO' WHERE id = ?", (cabine_sorteada[0],))
        cursor.execute("""
            INSERT INTO registo_avarias (cabine_id, robo_afetado, codigo_erro, descricao, causa_provavel, timestamp_inicio, status)
            VALUES (?, ?, ?, ?, ?, ?, 'ATIVO')
        """, (cabine_sorteada[0], robo_sorteado, cod, desc, causa, datetime.now().isoformat()))

        print(f"⚠️ [AVARIA CRÍTICA] {linha_atual} -> {cabine_sorteada[1]} -> Falha no {robo_sorteado}! Código: {cod}")

    conn.commit()
    conn.close()

if __name__ == "__main__":
    iniciar_base_dados_avancada()
    while True:
        ciclo_fabrica_avancado()
        time.sleep(2)
