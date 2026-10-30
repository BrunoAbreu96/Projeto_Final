# Relatório Técnico — BRUNUS MES

**Projeto:** BRUNUS MES — Manufacturing Execution System

**Autor:** Bruno Abreu

**Revisão:** 30 de outubro de 2026

**Referência:** [issue #1 — consolidar dados, relatórios e testes](https://github.com/BrunoAbreu96/Projeto_Final/issues/1)

## 1. Objetivo e âmbito

O BRUNUS MES é uma aplicação de formação para acompanhar produção, qualidade e avarias de duas linhas e oito estações. Esta revisão consolida o núcleo: relatórios por data e turno, alterações de estado transacionais e testes independentes da base industrial original.

A monitorização mostra o estado atual; indicadores e PDF mostram o período selecionado. Os dados são de demonstração. Não existe ligação a PLC real nem cálculo completo de OEE.

## 2. Tecnologias e arquitetura

SQLite permite demonstrar uma base relacional sem instalar um servidor. Para vários utilizadores e disponibilidade industrial, será necessário avaliar concorrência, infraestrutura e eventual migração para um servidor de base de dados.

Ambiente verificado: Windows, Python **3.14.7**. A versão mínima documentada é **3.11**, de acordo com as dependências. `requirements.txt` fixa as versões diretas verificadas de Streamlit, Pandas, ReportLab, streamlit-autorefresh, asyncua e pytest. A biblioteca asyncua não está integrada numa aquisição real.

| Componente | Responsabilidade |
|---|---|
| `dashboard.py` | Formulários, sessão e apresentação |
| `brunus_mes/auth.py` | Verificação PBKDF2-SHA256 |
| `brunus_mes/database.py` | Caminho configurável, ligações, esquema e migração |
| `brunus_mes/repository.py` | Consultas de estações e avarias ativas |
| `brunus_mes/services.py` | Autorização e operações transacionais |
| `brunus_mes/reporting.py` | Seleção temporal, métricas e modelo do relatório |
| `brunus_mes/pdf_report.py` | PDF sem novas consultas à base |
| `simulador_continuo.py` | Eventos sintéticos |
| `sql/criar_base_dados.sql` | Definição única do esquema |

As regras de negócio podem ser testadas sem iniciar Streamlit. A interface e o PDF recebem o mesmo modelo de relatório, evitando cálculos divergentes.

## 3. Modelo e integridade

| Tabela | Significado |
|---|---|
| `cabines` | Linha, estação, processo e estado atual |
| `historico_producao` | Saída final de linha: instante, estado da peça e ciclo |
| `registo_avarias` | Ocorrência associada a cabine, diagnóstico e intervalo |
| `sessao_ativa` | Estrutura histórica preservada; a autenticação usa a sessão Streamlit |

Um registo de produção representa o evento final de linha. Não foi acrescentada uma associação artificial a cabine, pois o simulador não regista cada passagem da peça pelas estações.

O esquema declara a chave estrangeira `registo_avarias.cabine_id → cabines.id`, campos obrigatórios e restrições de estados, datas e tempos de ciclo. Uma avaria ativa não tem fim; uma resolvida exige fim válido não anterior ao início. Cada ligação de persistência ativa `PRAGMA foreign_keys = ON`, define espera por bloqueio e é fechada após a operação.

O simulador usa a inicialização comum em vez de repetir o esquema. O caminho predefinido `data/brunus_dev.db` é ancorado à pasta do projeto. `BRUNUS_DB_PATH` e `--db` permitem bases separadas.

## 4. Migração e preservação do histórico

Uma base antiga não é modificada automaticamente ao abrir a aplicação. É necessária migração explícita:

```powershell
.\.venv\Scripts\python.exe -m brunus_mes.database migrate --db .\data\brunus_revisao.db
```

O procedimento recomendado é parar os processos e testar numa cópia, conservando a origem. A migração valida os dados em memória, guarda um backup SQLite consistente e reconstrói as tabelas numa transação. Preserva IDs, histórico e sequências de numeração; converte `RESOLVED` para `RESOLVIDO` e recalcula os estados atuais das cabines pelas avarias ativas. Uma base atualizada não volta a ser migrada.

Referências inválidas, dados incompatíveis ou estruturas adicionais não suportadas fazem abortar a operação, incluindo extensões de esquema cuja conservação automática não é garantida. Não se elimina histórico para satisfazer restrições. A correção requer análise numa cópia e uma decisão documentada. A validação preliminar pode falhar antes do backup automático; este não substitui a conservação da origem.

As bases industriais locais não foram utilizadas nos testes normais nem migradas como parte da validação automatizada.

## 5. Avarias, transações e perfis

A resolução usa uma transação com reserva de escrita para identificar a ocorrência ativa, guardar o fim e atualizar a cabine. Se houver outras ocorrências ativas nessa cabine, esta permanece em `ERRO`. Uma ocorrência resolvida não recebe novo fim. Qualquer falha desfaz a operação completa.

O encerramento global afeta apenas ocorrências ativas. A limpeza está identificada como demonstração, exige confirmação explícita e elimina produção e avarias na mesma transação que repõe as estações.

| Perfil | Consulta e PDF | Resolução | Encerramento e limpeza |
|---|---|---|---|
| Operador | Permitidos | Recusada | Recusados |
| Técnico | Permitidos | Permitida | Recusados |
| Master | Permitidos | Permitida | Permitidos |

As permissões são verificadas nos serviços. A autenticação conserva hashes PBKDF2-HMAC-SHA256 e comparação segura; rejeita configuração inválida. Credenciais permanecem fora do código e do Git. O gerador cria `.streamlit` numa instalação nova.

## 6. Turnos, indicadores e PDF

A data selecionada é a data civil de início do turno. O início pertence ao intervalo e o fim é exclusivo:

| Turno | Intervalo |
|---|---|
| 1 | 08:00–17:00 do próprio dia |
| 2 | 17:00 do próprio dia–01:00 do dia seguinte |
| 3 | 01:00–08:00 do próprio dia |

A produção é filtrada pelo intervalo e pela consulta. As duas consultas do relatório usam uma transação de leitura consistente.

**Ocorrências** contam pelo início da avaria. **Paragem** inclui avarias anteriores que coincidem com o turno, recortando cada intervalo. Uma avaria aberta conta até à consulta ou ao fim do turno. Intervalos sobrepostos da mesma linha são unidos; a soma entre linhas tem unidade **segundos-linha**. Não representa indisponibilidade física da célula.

**MTTR** é a média da duração completa das avarias iniciadas no turno e concluídas até à consulta. Pode incluir reparação posterior ao fim do turno. A interface e o PDF explicitam essa coorte.

**Qualidade FTT** é `OK / total × 100`. Sem produção, não há percentagem. O OEE completo exigiria também disponibilidade e desempenho com dados e definições adicionais.

As estimativas financeiras usam margem fictícia de 100 EUR/peça OK, custo de 35 EUR/peça rejeitada e 150 EUR/minuto-linha parado:

`resultado estimado = OK × 100 − rejeitadas × 35 − segundos-linha / 60 × 150`

Os parâmetros e a natureza simulada constam da interface e PDF. Não são lucro efetivamente apurado. O documento identifica data, turno, limites, consulta, totais e critérios. Sem dados, a interface mostra uma mensagem em vez de exportar histórico global como relatório de turno.

## 7. Testes efetivamente executados em 30/10/2026

As validações usam bases temporárias e dados sintéticos. A mesma suite foi executada no ambiente do projeto e numa instalação nova; as duas execuções não são somadas como testes distintos.

| Validação | Resultado registado |
|---|---|
| Suite completa no ambiente do projeto | 109 aprovados, 1 teste privado ignorado, 4 avisos; 6,85 s |
| Mesma suite numa instalação nova | 109 aprovados, 1 teste privado ignorado, 4 avisos; 8,63 s |
| Interação Streamlit com AppTest | 5 aprovados, incluídos na suite completa |
| Autenticação | 25 aprovados, incluídos na suite completa |
| Instalação nova, Python 3.14.7, sem base original nem credenciais locais | Dependências de `requirements.txt` instaladas |
| `pip check` no ambiente novo | Sem incompatibilidades reportadas |
| Inicialização e simulação na cópia nova | 8 estações e 3 peças OK |
| Servidor Streamlit na instalação nova | Saúde HTTP 200 e página HTTP 200 |
| Compilação dos módulos Python com `compileall` | Concluída sem erros |
| PDF de demonstração, renderização e inspeção visual | Uma página; conteúdo e disposição verificados |

Os quatro avisos são `Pandas4Warning`, emitidos por uma rotina de gráficos do Streamlit que utiliza `reset_index(inplace=True)`. Indicam compatibilidade futura numa dependência; não houve falhas na suite.

O teste de aceitação prepara uma base nova, insere produção e avaria, verifica que uma linha parada não produz, recusa resolução por operador, resolve com técnico e confirma estado e duração de 300 segundos. Compara depois o relatório com a base: uma peça OK, uma ocorrência, MTTR de 300 segundos, 300 segundos-linha e custo fictício de 750 EUR. Por fim gera o PDF.

Foi ainda gerado, renderizado e inspecionado um PDF do turno 2 de 29/10/2026, entre as 17:00 e a 01:00 de 30/10, consultado às 08:00 de 30/10. Os dados sintéticos produziram 3 peças, 2 OK e 1 rejeitada, qualidade de 66,67%, 900 segundos-linha de paragem (600 na Main A e 300 na Main B), MTTR de 420 segundos e resultado estimado de −2 085 EUR. O documento final ocupa uma página.

A suite cobre ainda referências inválidas, campos e estados inválidos, migração com conservação de IDs, abortar migração inválida, rollback, várias avarias na mesma cabine, preservação de datas, confirmação de limpeza, turnos com meia-noite, limites temporais, sobreposições, avarias abertas, períodos vazios e hashes inválidos.

No ambiente isolado Windows, a pasta temporária padrão do pytest causou um erro de permissões antes do teste de aceitação. Uma pasta descartável dentro do projeto permite configurar esse armazenamento. A instalação e arranque foram também verificados fora desse isolamento. Erros de infraestrutura não foram registados como testes funcionais aprovados.

Para reproduzir:

```powershell
New-Item -ItemType Directory -Force -Path .\tmp | Out-Null
.\.venv\Scripts\python.exe -m pytest .\tests -q --basetemp .\tmp\pytest
```

O teste privado da base original só é ativado por `BRUNUS_ORIGINAL_DB`, abre em modo de leitura e é ignorado por defeito. A entrega não depende de dados industriais privados.

## 8. Instalação e critérios da issue

O README documenta ambiente virtual, dependências, criação de `data`, esquema, estações sintéticas, credenciais, simulador, dashboard, caminho configurável e migração. A instalação foi exercitada numa cópia apenas com os ficheiros publicáveis, sem `.venv`, credenciais, base original ou dados locais.

| Pedido | Implementação e evidência |
|---|---|
| Relatórios por data e turno | `reporting.py`, `pdf_report.py`, testes de limites e interseções |
| Integridade e esquema único | SQL, `database.py`, testes de esquema e migração |
| Resolução consistente | Serviços e testes de atomicidade e avarias simultâneas |
| Resets que preservam histórico encerrado | Autorização, confirmação e rollback |
| Indicadores e estimativas claros | FTT, segundos-linha e fórmulas documentados |
| Separação de responsabilidades | Package `brunus_mes` e apresentação Streamlit |
| Testes reproduzíveis | Dados sintéticos e fluxo de aceitação |
| Instalação e apresentação | Cópia nova verificada, textos UTF-8 e documentação |

## 9. Limitações e trabalho futuro

- Datas usam horas locais sem fuso. A mudança de hora de verão/inverno pode tornar durações ambíguas; uma utilização real deve definir UTC e apresentação local.
- Não há integração PLC validada, OEE completo, contabilização real ou garantia de operação industrial.
- O esquema não reconstrói informação histórica ausente. Uma migração recusada pode exigir revisão manual numa cópia.
- A autenticação por perfis não inclui gestão individual de utilizadores, recuperação de credenciais ou auditoria completa de intervenções.
- Carga e concorrência industriais exigem testes próprios e avaliação da persistência.
- É necessária política de backups e conservação. A limpeza de demonstração elimina o histórico da base selecionada após confirmação.

Esta revisão é local. Commit, publicação no GitHub e encerramento da issue são ações distintas da criação dos ficheiros.

## 10. Registo histórico de atividades de 26/10/2026

Registo conservado da versão anterior. Não representa as horas da revisão de 30/10/2026.

**Período histórico:** 09h00–13h00.

### 09h00–10h00 — Revisão do ambiente e autenticação

- Revisão do estado do projeto e dos ficheiros existentes.
- Análise das alterações ao mecanismo de autenticação.
- Verificação manual dos perfis e do logout.

### 10h00–11h00 — Proteção dos ficheiros e controlo de versões

- Revisão das regras do `.gitignore`.
- Verificação da exclusão de configurações sensíveis e bases de dados locais.
- Análise das alterações pendentes no repositório.

### 11h00–12h00 — Base de dados e script SQL

- Análise da estrutura da base de dados SQLite.
- Identificação das tabelas existentes.
- Criação e teste do script SQL numa base de dados temporária.

### 12h00–13h00 — Documentação técnica

- Preparação do README com instruções do projeto.
- Organização do relatório técnico.
- Identificação dos testes e tarefas ainda necessários.

## 11. Registo da aula de 30/10/2026

**Horário da aula:** 11h00–13h00, indicado pelo autor. Os commits utilizam a data e a hora reais do respetivo registo.

Trabalho realizado nesta revisão:

- Implementação dos critérios da issue #1 relativos a integridade, avarias, resets, turnos e relatórios.
- Separação entre apresentação, persistência, operações, autenticação e cálculos.
- Validação com dados sintéticos e instalação nova; resultados na secção 7.
- Atualização das instruções de instalação, migração e demonstração.

A entrega final da formação está prevista para **26/11/2026**. A avaliação orienta a prioridade: funcionamento demonstrável, coerência com os pedidos do formador e decisões técnicas que o autor consiga explicar.

A distribuição comercial está em análise: instalação na empresa com acesso pelo navegador ou programa Windows com janela própria. A subscrição mensal é um objetivo futuro e não está implementada nesta revisão. Esta discussão não altera o núcleo validado nem constitui uma decisão definitiva de distribuição.
