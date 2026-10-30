# BRUNUS MES — Manufacturing Execution System

Aplicação de formação para monitorizar duas linhas de produção, oito estações, qualidade das peças e avarias. Inclui simulador, autenticação por perfis e relatórios PDF por data e turno.

Os dados de demonstração são sintéticos. O indicador implementado é a **qualidade FTT**; o projeto não calcula OEE completo nem está ligado a um PLC real.

O GitHub disponibiliza o código e a documentação. Nesta versão, a aplicação é iniciada com Python e utilizada no navegador do computador onde é executada; abrir a página do repositório não inicia a aplicação.

## 1. Requisitos

- Python **3.11 ou superior**. Esta revisão foi verificada em Windows com Python **3.14.7**.
- Git para clonar o projeto.
- Tkinter para o utilitário gráfico de credenciais; no instalador Python para Windows está normalmente incluído.

As versões diretas verificadas estão fixadas em `requirements.txt`: Streamlit 1.66.1, streamlit-autorefresh 1.0.1, Pandas 3.1.0, ReportLab 5.1.0, asyncua 2.1.0 e pytest 9.1.1. A biblioteca asyncua está reservada para trabalho futuro; não constitui uma ligação industrial ativa.

## 2. Instalação nova

Execute os comandos no PowerShell, na pasta do projeto:

```powershell
git clone https://github.com/BrunoAbreu96/Projeto_Final.git
cd Projeto_Final
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Se já tem uma cópia local, entre nessa pasta. Antes de utilizar uma base anterior, consulte a secção de migração.

Também pode obter uma cópia ZIP do repositório. Nesse caso, extraia-a, abra o PowerShell na pasta que contém `dashboard.py` e continue a partir de `python -m venv .venv`.

### 2.1. Preparar a base e as estações

```powershell
.\.venv\Scripts\python.exe -m brunus_mes.database init --demo
```

O comando cria automaticamente a pasta `data`, a base `data/brunus_dev.db` e oito estações de demonstração. Não insere produção nem avarias. Sem `--demo`, cria apenas o esquema. Repetir a inicialização de uma base atualizada não apaga o histórico.

O esquema único é `sql/criar_base_dados.sql`, utilizado também pelo simulador e pela migração. Uma base antiga é recusada até ser migrada explicitamente.

### 2.2. Configurar as credenciais

```powershell
.\.venv\Scripts\python.exe .\gerar_credenciais.py
```

O utilitário pede e confirma uma palavra-passe para cada perfil, cria `.streamlit` se necessário e guarda hashes PBKDF2-SHA256 em `.streamlit/secrets.toml`. O ficheiro contém `[credenciais]` e as chaves `operador_hash`, `tecnico_hash` e `master_hash`.

Cada palavra-passe deve ter pelo menos seis caracteres. Quem avalia ou instala uma cópia nova define as suas próprias credenciais através deste utilitário.

O ficheiro é local e está excluído do Git. Não publique palavras-passe nem hashes. Se cancelar antes de completar os três perfis, as credenciais existentes não são substituídas.

### 2.3. Iniciar simulador e dashboard

Num terminal:

```powershell
.\.venv\Scripts\python.exe .\simulador_continuo.py
```

Noutro terminal, na mesma pasta:

```powershell
.\.venv\Scripts\python.exe -m streamlit run .\dashboard.py
```

Abra o endereço apresentado pelo Streamlit. O simulador continua até premir `Ctrl+C`. Uma linha com avaria ativa deixa de produzir até à sua resolução.

Para executar três ciclos com evento OK numa base sem avarias ativas:

```powershell
.\.venv\Scripts\python.exe .\simulador_continuo.py --cycles 3 --interval 0 --seed 42 --event OK
```

O simulador aceita também `--event REJEITADA`, `--event ERRO`, `--db CAMINHO` e `--init-only`. Um evento forçado continua a respeitar uma linha parada por avaria.

### 2.4. Roteiro para o formador testar a partir do GitHub

1. Obter uma cópia do repositório e instalar as dependências, como descrito na secção 2.
2. Criar a base e as oito estações com `init --demo`, sem precisar de bases industriais privadas.
3. Executar `gerar_credenciais.py` e definir as palavras-passe dos três perfis.
4. Iniciar o simulador e o dashboard em dois terminais e abrir o endereço local apresentado pelo Streamlit.
5. Entrar como `master` ou `tecnico`, observar uma avaria e usar **Validar intervenção técnica**. Se as duas linhas tiverem avarias ativas, a produção fica parada até serem resolvidas.
6. Selecionar a data e o turno que contêm os dados gerados, consultar os indicadores e descarregar o PDF. Um período sem dados apresenta uma mensagem; não deve mostrar o histórico de outro turno.
7. Executar os testes da secção 7. O teste de aceitação reproduz automaticamente o fluxo de base nova, produção, avaria, resolução e relatório com dados sintéticos.

Para provocar uma avaria sem esperar por um evento aleatório, pare o simulador contínuo, execute o comando seguinte na base de teste e volte a iniciar o simulador:

```powershell
.\.venv\Scripts\python.exe .\simulador_continuo.py --cycles 1 --interval 0 --seed 42 --event ERRO
```

Se a linha escolhida já tiver uma avaria ativa, o comando respeita o bloqueio. Resolva as ocorrências existentes antes de repetir.

O endereço `localhost` apresentado pelo Streamlit corresponde ao computador que está a executar a aplicação. Para testar noutro computador, o formador deve iniciar a sua própria cópia seguindo estes passos. A versão descrita neste README não fornece um serviço público alojado.

## 3. Escolher outra base

O caminho predefinido é relativo à pasta do código. Para selecionar outra base, defina `BRUNUS_DB_PATH` antes de executar as ferramentas:

```powershell
$env:BRUNUS_DB_PATH = Join-Path (Get-Location) 'data/brunus_demo.db'
.\.venv\Scripts\python.exe -m brunus_mes.database init --demo
.\.venv\Scripts\python.exe .\simulador_continuo.py --cycles 3 --event OK --interval 0
.\.venv\Scripts\python.exe -m streamlit run .\dashboard.py
```

Defina a mesma variável em cada terminal usado pelo simulador e dashboard. Nas ferramentas CLI, `--db` tem prioridade. Um caminho relativo fornecido explicitamente é resolvido a partir da pasta de trabalho atual.

## 4. Migrar uma base sem apagar o histórico

1. Pare o simulador e o dashboard.
2. Trabalhe primeiro numa cópia e conserve a base original.
3. Migre explicitamente a cópia, substituindo os caminhos do exemplo pelos seus:

```powershell
Copy-Item -LiteralPath .\data\brunus_dev.db -Destination .\data\brunus_revisao.db
.\.venv\Scripts\python.exe -m brunus_mes.database migrate --db .\data\brunus_revisao.db
```

A migração valida os registos, cria um backup SQLite consistente junto à base (`*.backup_DATA_HORA.db`) e aplica a atualização numa única transação. Preserva IDs, histórico e sequências de numeração; normaliza `RESOLVED` para `RESOLVIDO` e recalcula o estado atual das cabines a partir das avarias ativas. Repetir a migração de uma base atualizada não volta a alterá-la.

Referências inválidas, campos em falta, datas incompatíveis ou estruturas adicionais não suportadas fazem a migração terminar com erro. Não elimina registos inválidos nem inventa valores. Reveja e corrija os dados numa cópia, com uma decisão documentada, antes de repetir. A validação pode falhar antes de criar o backup automático; conserve sempre a origem.

Depois de verificar os dados migrados, configure `BRUNUS_DB_PATH` para essa base. Não use a limpeza de demonstração para migrar dados.

## 5. Perfis e operações

| Perfil | Consultar e gerar PDF | Resolver avarias | Encerrar ativas e limpar demonstração |
|---|---|---|---|
| `operador` | Sim | Não | Não |
| `tecnico` | Sim | Sim | Não |
| `master` | Sim | Sim | Sim |

As permissões são verificadas nos serviços, além da visibilidade dos botões. Resolver uma avaria e atualizar a cabine faz parte da mesma transação. Só ocorrências ativas são resolvidas; a cabine permanece em erro se tiver outra avaria ativa.

O encerramento global afeta apenas avarias ativas e preserva as datas das resolvidas. **Eliminar dados de demonstração** apaga todo o histórico de produção e avarias da base selecionada, exige confirmação explícita e está limitado a `master`. A eliminação e a reposição das estações são atómicas.

## 6. Relatórios por data e turno

Selecione na barra lateral a **data de início do turno** e o turno:

| Turno | Início | Fim exclusivo |
|---|---|---|
| 1 | 08:00 da data selecionada | 17:00 da mesma data |
| 2 | 17:00 da data selecionada | 01:00 do dia seguinte |
| 3 | 01:00 da data selecionada | 08:00 da mesma data |

O turno 2 de 30/10/2026 abrange `[30/10 17:00, 31/10 01:00)`. O instante inicial pertence ao turno; o final pertence ao seguinte. Dashboard e PDF usam o mesmo modelo calculado e instante de consulta.

- **Produção:** saídas finais de linha dentro do intervalo e até à consulta. Um registo não representa uma passagem por cada cabine.
- **Ocorrências:** avarias cujo início pertence ao turno.
- **Paragem:** inclui avarias iniciadas antes do turno, apenas na parte coincidente. Uma avaria aberta termina, para o cálculo, na consulta ou no fim do turno, o que ocorrer primeiro.
- **Sobreposições:** intervalos da mesma linha são unidos. A soma entre linhas usa **segundos-linha**, não tempo de indisponibilidade da célula.
- **MTTR:** média da duração completa das avarias iniciadas no turno e concluídas até à consulta. Pode incluir reparação depois do fim do turno; não é a média dos intervalos recortados.
- **Qualidade FTT:** `peças OK / total × 100`. Sem produção não existe percentagem. Não inclui disponibilidade e desempenho necessários ao OEE completo.

Sem produção nem avarias relevantes, a interface apresenta uma mensagem e não oferece um PDF com dados de outro período. A monitorização em tempo real mostra o estado atual, independentemente do turno histórico selecionado.

### 6.1. Estimativas financeiras

Os parâmetros de demonstração são identificados na interface e no PDF:

| Parâmetro | Valor fictício |
|---|---|
| Margem por peça OK | 100 EUR/peça |
| Custo por peça rejeitada | 35 EUR/peça |
| Paragem | 150 EUR/minuto-linha |

`resultado estimado = OK × 100 − rejeitadas × 35 − segundos-linha / 60 × 150`

Estes valores não representam faturação nem lucro contabilístico apurado.

## 7. Testes reproduzíveis

```powershell
New-Item -ItemType Directory -Force -Path .\tmp | Out-Null
.\.venv\Scripts\python.exe -m pytest .\tests -q --basetemp .\tmp\pytest
```

Os testes normais usam bases temporárias e dados sintéticos. Cobrem esquema e referências inválidas, migração e rollback, perfis, avarias simultâneas, preservação do histórico, resets, turnos e meia-noite, sobreposições, estimativas, PDF, autenticação e interação Streamlit.

`--basetemp` seleciona uma pasta descartável no projeto, útil em ambientes que restringem a pasta temporária Windows. Não aponte esta opção para uma pasta com ficheiros que pretende guardar.

`tests/test_acceptance.py` percorre a demonstração pedida: base nova, estações, produção, avaria, tentativa não autorizada, resolução técnica, estado e duração, relatório e PDF.

O teste privado da base original fica ignorado por defeito. Só lê o caminho explicitamente indicado por `BRUNUS_ORIGINAL_DB`, em modo de leitura. Não é necessário para a suite normal nem acompanha os dados da entrega.

Na validação registada em **30/10/2026**, a suite teve **109 testes aprovados e 1 teste privado ignorado**, tanto no ambiente do projeto como numa instalação nova. Os quatro avisos emitidos são de compatibilidade futura do Pandas numa rotina de gráficos do Streamlit; não houve falhas. Consulte `RELATORIO_TECNICO.md` para resultados e limitações.

## 8. Estrutura e limites

| Caminho | Responsabilidade |
|---|---|
| `dashboard.py` | Apresentação e interação Streamlit |
| `brunus_mes/auth.py` | Verificação das palavras-passe |
| `brunus_mes/database.py` | Ligações, inicialização e migração |
| `brunus_mes/repository.py` | Consultas de monitorização |
| `brunus_mes/services.py` | Resolução, encerramento e limpeza autorizados |
| `brunus_mes/reporting.py` | Turnos, dados do período e indicadores |
| `brunus_mes/pdf_report.py` | PDF a partir do modelo calculado |
| `sql/criar_base_dados.sql` | Esquema único |
| `simulador_continuo.py` | Eventos sintéticos |
| `tests/` | Validação com bases temporárias |

As datas são horas civis locais sem fuso. Numa mudança de hora de verão/inverno, a duração pode não representar o tempo físico decorrido; esta revisão não resolve essa ambiguidade. Não há aquisição real de PLC, OEE completo ou certificação industrial. Uma utilização real exige validar relógios, dados, infraestrutura e controlo de acessos.

Credenciais, bases, backups, ambientes virtuais e saídas de teste estão excluídos do Git. A cópia obtida pelo GitHub é preparada localmente através dos comandos deste README.

**Autor:** Bruno Abreu. **Repositório:** [Projeto_Final](https://github.com/BrunoAbreu96/Projeto_Final). **Critérios:** [issue #1](https://github.com/BrunoAbreu96/Projeto_Final/issues/1).
