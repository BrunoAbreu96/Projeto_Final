# BRUNUS MES — Auditoria técnica inicial

## Âmbito e proteção do projeto

Esta pasta contém uma cópia dos ficheiros recebidos. Os ficheiros originais não foram alterados. A base de dados copiada contém os dados que existiam no momento da análise; usar sempre uma cópia separada para testes que possam criar, atualizar ou apagar registos.

## Estado verificado

- Os quatro ficheiros Python passam a análise sintática (`ast.parse`).
- A base de dados SQLite passa `PRAGMA integrity_check` (`ok`).
- A base de dados contém 8 cabines, 3.627 registos de produção e 124 registos de avarias.
- Produção registada: Main A — 1.742 peças (1.648 OK, 94 rejeitadas); Main B — 1.885 peças (1.778 OK, 107 rejeitadas).
- Avarias: 122 resolvidas e 2 ativas no momento da análise.
- A tabela `sessao_ativa` contém um perfil global (`master`) guardado desde 12/10/2026; este mecanismo não isola sessões de vários utilizadores.
- O ambiente de análise não tem Streamlit, `streamlit-autorefresh` nem `asyncua` instalados. Por isso, foi possível verificar a sintaxe e a base de dados, mas não executar o dashboard completo nem ligar a um PLC real.

## Problemas prioritários encontrados

### P0 — Segurança e integridade dos dados

1. Credenciais (`operador`, `tecnico`, `master`) estão embutidas no `dashboard.py` e repetidas num ficheiro de texto.
2. O perfil é persistido numa única linha de `sessao_ativa`. Um utilizador pode herdar o perfil de outro; o logout de uma sessão pode afetar as restantes.
3. O botão de reset apaga permanentemente o histórico de produção e de avarias. Para um projeto industrial, preferir filtros por período, confirmação explícita, cópia de segurança e registo de auditoria; evitar apagar histórico operacional.
4. O reset global marca todas as avarias como resolvidas sem validação individual, o que pode falsificar o histórico.

### P1 — Consistência funcional

5. A seleção de turno não filtra os registos. Os relatórios usam os dados de todos os períodos, embora o título indique um turno.
6. O `driver_industrial.py` insere uma peça a cada leitura em que o sinal booleano permanece `True`; um sinal mantido por vários ciclos pode duplicar peças e faturação. Deve ser detetada a transição de sinal (flanco) ou usado um identificador de evento.
7. O driver industrial não tem ciclo de reconexão/tratamento robusto para falhas OPC UA; uma exceção pode terminar o processo.
8. O driver escreve o estado `ERRO` na cabine, mas não repõe o estado da cabine quando o erro do PLC desaparece. A resolução de uma avaria no dashboard também pode marcar a cabine `OK` sem confirmar o estado atual do PLC.
9. `simulador.py` espera uma tabela `cabines` com coluna `nome` e insere produção sem `main_line`; o esquema avançado e o dashboard esperam `main_line`, `estacao` e `nome_processo`. Os dois simuladores não são compatíveis entre si quando partilham a mesma base de dados.
10. O `simulador.py` pode bloquear a produção de ambas as linhas por qualquer avaria ativa; o simulador contínuo bloqueia apenas a linha afetada. A regra de negócio precisa de ser uniforme.
11. O relatório PDF e os indicadores financeiros calculam totais globais, não o turno selecionado. Os valores de receita/custo estão fixos no código e devem ser identificados como pressupostos simulados, não como valores reais da fábrica.
12. O indicador apresentado como OEE é essencialmente FTT/qualidade; OEE requer disponibilidade, desempenho e qualidade, com tempo planeado e ciclo ideal definidos.
13. MTTR, custo de paragem e Pareto são calculados sobre o histórico completo; avarias ativas não têm duração final e não entram nesses cálculos.
14. O dashboard usa `unsafe_allow_html` e JavaScript para a sirene. Convém isolar o CSS, evitar HTML dinâmico com dados não confiáveis e dar ao utilizador um controlo para silenciar o alarme.

## Sequência recomendada

1. Congelar os originais e trabalhar apenas numa cópia de desenvolvimento.
2. Uniformizar o esquema SQLite e centralizar as operações de base de dados, com transações e chaves estrangeiras.
3. Corrigir autenticação/sessões e permissões sem apagar o histórico.
4. Definir um contrato único de evento de produção/avaria e alinhar ambos os simuladores e o driver.
5. Corrigir deduplicação de sinais, reconexão e transições de estado no driver (testável sem PLC através de simulação).
6. Implementar filtro real por turno/período, separar FTT de OEE e identificar custos simulados.
7. Modernizar a interface e criar testes automáticos/documentação de execução.

## Limitações desta auditoria

A análise baseia-se nos ficheiros e na base de dados fornecidos. As tags OPC UA e a comunicação com o PLC não foram verificadas num equipamento real. Não foram instaladas dependências nem executada a aplicação nesta etapa.
