# BRUNUS MES — Manufacturing Execution System

**UFCD/UC 5425 — Opção B: Projeto livre.**

Aplicação de formação para monitorizar linhas de produção, qualidade das peças e avarias. A configuração inicial de demonstração inclui duas linhas e oito estações. Inclui simulador, autenticação por perfis, administração e relatórios PDF por data, turno e linha.

Os dados de demonstração são sintéticos. O indicador implementado é a **qualidade FTT**; o projeto não calcula OEE completo nem está ligado a um PLC real.

O GitHub disponibiliza o código e a documentação. Nesta versão, a aplicação é iniciada com Python e utilizada no navegador do computador onde é executada; abrir a página do repositório não inicia a aplicação.

## 1. Requisitos

- Python **3.11 ou superior**. Esta revisão foi verificada em Windows com Python **3.14.7**.
- Git para clonar o projeto.
- Tkinter para o utilitário gráfico de credenciais; no instalador Python para Windows está normalmente incluído.

As versões diretas verificadas estão fixadas em `requirements.txt`: Streamlit 1.66.1, streamlit-autorefresh 1.0.1, Pandas 3.1.0, ReportLab 5.1.0, asyncua 2.1.0 e pytest 9.1.1. A biblioteca asyncua está reservada para trabalho futuro; não constitui uma ligação industrial ativa.

## Executar

Depois de instalar as dependências da secção 2, abra **`iniciar_demo.bat` por duplo clique**, no Windows. O lançador usa o Python da `.venv`, abre a aplicação no navegador e apresenta na janela os acessos dos três perfis.

- A demonstração fica em `data/demo/`, com base e credenciais sintéticas próprias, excluídas do Git. Os dados e os acessos são conservados entre arranques.
- O duplo clique usa **modo manual**: o master escolhe os eventos no separador **Administração → Demonstração**, permitindo gerar e verificar cada evento.
- Na primeira preparação, são criados dados dos três turnos do dia anterior e alguns eventos no instante da preparação. A data desses registos mantém-se nos arranques seguintes.
- Mantenha a janela aberta. **Ctrl+C** termina os processos iniciados pelo lançador.

Alternativas no PowerShell:

```powershell
.\.venv\Scripts\python.exe .\iniciar_demo.py --manual
.\.venv\Scripts\python.exe .\iniciar_demo.py
```

O primeiro comando usa eventos manuais; o segundo inicia também o simulador contínuo. `--no-browser` evita abrir o navegador; `--prepare-only` prepara os ficheiros sem iniciar processos. Se precisar de redefinir os acessos sintéticos, use `--prepare-only --regenerate-credentials`. As credenciais da demonstração também ficam em `data/demo/acesso_demo.json`, apenas neste computador.

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

O Streamlit lê as credenciais em `.streamlit/secrets.toml`. O SQLite local usa um ficheiro e dispensa uma conta de servidor. O `.gitignore` exclui `.streamlit/secrets.toml`, `.env` e variantes locais de `.env`. Se cancelar antes de completar os três perfis, as credenciais existentes são conservadas.

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

1. Obter uma cópia do repositório e instalar as dependências da secção 2.
2. Abrir `iniciar_demo.bat` no Windows, conforme a secção [Executar](#executar), e entrar como `master` com a credencial apresentada na janela do lançador.
3. Em **Administração → Demonstração**, escolher uma linha disponível e gerar **Peça OK**. Se ambas estiverem paradas, resolver primeiro as avarias de uma linha.
4. Na mesma linha, gerar **Avaria na linha**. Em **Monitorização em tempo real**, confirmar a paragem e usar **Intervenções pendentes → Validar intervenção técnica** para a resolver.
5. Selecionar a data de início do turno, o turno dos eventos e a linha usada. Consultar os indicadores e usar **Descarregar PDF do turno** na barra lateral.
6. Executar os testes da secção 7 para reproduzir automaticamente o fluxo de base nova, produção, avaria, resolução e relatório com dados sintéticos.

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

| Perfil | Consultar e gerar PDF | Resolver avarias | Administração, backups e demonstração |
|---|---|---|---|
| `operador` | Sim | Não | Não |
| `tecnico` | Sim | Sim | Não |
| `master` | Sim | Sim | Sim |

As permissões são verificadas nos serviços, além da visibilidade dos botões. Resolver uma avaria e atualizar a cabine faz parte da mesma transação. Só ocorrências ativas são resolvidas; a cabine permanece em erro se tiver outra avaria ativa.

O início de sessão inclui **Ajuda para entrar**, com as diferenças entre perfis e a indicação do utilitário local para voltar a definir credenciais.

Na monitorização, os contadores mostram as linhas configuradas, as linhas paradas e as avarias ativas agora. Uma avaria suspende a produção de toda a linha no simulador; **SEM AVARIA LOCAL** apenas indica que a estação não tem uma avaria registada. As linhas e estações apresentadas são lidas da base, com cartões em duas colunas por linha.

O encerramento global afeta apenas avarias ativas e preserva as datas das resolvidas. **Eliminar dados de demonstração** apaga todo o histórico de produção e avarias da base selecionada, exige confirmação explícita e está limitado a `master`. A eliminação e a reposição das estações são atómicas.

### 5.1. Configuração de linhas e estações

O master dispõe de **Administração → Linhas e estações** para adicionar estações a uma linha existente ou criar uma linha com a primeira estação. Pode editar o processo; mudanças de linha/nome e remoção são recusadas quando a estação tem avarias associadas ou a linha já tem produção. A remoção exige confirmação explícita e nunca apaga histórico.

Os serviços validam campos e duplicados, usando uma transação por alteração. Não foi alterado o esquema SQL. O simulador conserva a configuração ao reiniciar; só povoa automaticamente uma base nova. Para uma base existente sem estações, use `init --demo` apenas se pretender adicionar a configuração de demonstração.

### 5.2. Criar eventos sem terminal

No modo iniciado por `iniciar_demo.bat`, entre como master e abra **Administração → Demonstração**. Escolha a linha, o evento **Peça OK**, **Peça rejeitada** ou **Avaria na linha**, e carregue em **Gerar evento**. Uma linha parada recusa novos eventos até resolução técnica. A resolução continua em **Monitorização em tempo real → Intervenções pendentes**.

O serviço exige master e `BRUNUS_DEMO_MODE=1`, definido pelo lançador para a base sintética. No arranque normal do dashboard, os controlos de geração manual ficam indisponíveis.

### 5.3. Cópias de segurança e recuperação

Em **Administração → Cópias de segurança**, o master pode criar e descarregar uma cópia SQLite consistente. As cópias ficam numa pasta `backups` junto à base selecionada. Não incluem as palavras-passe, que estão no ficheiro de credenciais da instalação.

Para recuperar, selecione uma cópia válida, confirme a operação e use **Recuperar cópia**. A aplicação valida esquema, dados, referências e estados, guarda primeiro o estado anterior e substitui o conteúdo numa única transação. Uma falha desfaz as alterações. Não substitui o ficheiro aberto nem usa uma cópia simples de uma base que esteja a ser escrita.

A recuperação aceita apenas cópias compatíveis da pasta dessa base; não é uma ferramenta de reparação de SQLite corrompido. No simulador contínuo, podem surgir novos eventos depois do ponto recuperado. O modo manual permite verificar o estado recuperado antes de gerar outros eventos. Guarde também cópias fora do computador para proteção contra avaria do equipamento.

## 6. Relatórios por data e turno

A aplicação abre com a **data de início do turno** e o turno correspondentes à hora local do computador. Entre as 00:00 e a 01:00, seleciona o turno 2 do dia anterior. Pode consultar outro período na barra lateral; a atualização automática preserva essa escolha. O botão **Voltar ao turno atual** repõe a data e o turno atuais.

O filtro **Linha do relatório** permite consultar todas as linhas ou apenas uma. Produção, qualidade, avarias, paragens e estimativas usam a mesma seleção; o PDF identifica essa linha. A lista inclui linhas do histórico mesmo sem estações atualmente configuradas. Os separadores, os filtros e as mensagens da administração mantêm-se durante as atualizações automáticas.

Horários disponíveis:

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

Em **06/11/2026**, uma cópia limpa do GitHub foi instalada em Windows com Python 3.14.7. A aplicação arrancou em modo manual e a suite teve **216 testes aprovados e 1 teste opcional ignorado**, com 30 avisos de compatibilidade futura do Pandas numa rotina de gráficos do Streamlit. Consulte o [relatório técnico](RELATORIO_TECNICO.md#7-testes-e-validação) para os resultados das revisões anteriores e os detalhes da validação.

## 8. Estrutura e limites

| Caminho | Responsabilidade |
|---|---|
| `dashboard.py` | Apresentação e interação Streamlit |
| `brunus_mes/auth.py` | Verificação das palavras-passe |
| `brunus_mes/database.py` | Ligações, inicialização e migração |
| `brunus_mes/repository.py` | Consultas de monitorização |
| `brunus_mes/services.py` | Resolução, encerramento e limpeza autorizados |
| `brunus_mes/configuration.py` | Configuração de estações com proteção do histórico |
| `brunus_mes/backups.py` | Cópias consistentes e recuperação transacional |
| `brunus_mes/demo.py` | Eventos manuais autorizados no modo de demonstração |
| `brunus_mes/ui_admin.py` | Formulários do separador Administração |
| `brunus_mes/reporting.py` | Turnos, dados do período e indicadores |
| `brunus_mes/pdf_report.py` | PDF a partir do modelo calculado |
| `sql/criar_base_dados.sql` | Esquema único |
| [docs/MODELO_DADOS.md](docs/MODELO_DADOS.md) | Diagrama e explicação do esquema atual |
| `simulador_continuo.py` | Eventos sintéticos |
| `iniciar_demo.py` / `iniciar_demo.bat` | Arranque isolado da demonstração |
| `tests/` | Validação com bases temporárias |

As datas são horas civis locais sem fuso. Numa mudança de hora de verão/inverno, a duração pode não representar o tempo físico decorrido; esta revisão não resolve essa ambiguidade. Não há aquisição real de PLC, OEE completo ou certificação industrial. Uma utilização real exige validar relógios, dados, infraestrutura e controlo de acessos.

Credenciais, bases, backups, ambientes virtuais e saídas de teste estão excluídos do Git. A cópia obtida pelo GitHub é preparada localmente através dos comandos deste README.

**Autor:** Bruno Abreu. **Repositório:** [Projeto_Final](https://github.com/BrunoAbreu96/Projeto_Final). **Critérios:** [issue #1](https://github.com/BrunoAbreu96/Projeto_Final/issues/1).
