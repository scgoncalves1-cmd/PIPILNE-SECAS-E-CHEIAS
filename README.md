# Pipeline de dados climáticos (secas/cheias) — RS e SP

Coleta mensal e automática de dados de INMET, ANA/HidroWebService, IBGE (referência),
CEMADEN e Monitor de Secas, orquestrada pelo GitHub Actions — 100% gratuito, sem Azure
e sem servidor próprio.

## Estrutura

```
(raiz do repositório)
├── collectors/
│   ├── inmet.py               # API pública (sem token) - estações automáticas
│   ├── hidroweb.py            # API oficial ANA (HidroWebService) - precisa de identificador+senha
│   ├── ibge.py                # API pública (sem token) - referência municipal
│   ├── cemaden_stub.py        # sem API - lê todos os XLS/XLSX de data/raw/cemaden/
│   └── monitor_secas_stub.py  # sem API - lê todos os XLS/XLSX de data/raw/monitor_secas/
├── main.py                    # orquestrador: roda tudo e grava no banco
├── requirements.txt
├── .github/workflows/coleta-mensal.yml   # cron mensal do GitHub Actions
└── data/
    ├── clima.db                  # banco SQLite (gerado automaticamente, versionado no repo)
    ├── dados_consolidados.csv    # histórico completo (lido pelo Google Sheets via IMPORTDATA)
    └── raw/
        ├── cemaden/            # coloque aqui os .xls baixados do Mapa Interativo do CEMADEN
        └── monitor_secas/      # coloque aqui os .xlsx baixados do Monitor de Secas (RS_..., SP_...)
```

## Status de cada fonte

| Fonte | API? | O que fazer |
|---|---|---|
| INMET (estações automáticas) | Sim, pública, sem token | Já funciona — estações do RS e SP configuradas em `main.py` |
| ANA/HidroWebService | Sim, oficial, precisa de identificador (CPF/CNPJ) + senha | Pedir acesso por e-mail a hidro@ana.gov.br (assunto: "[seu CPF/CNPJ] - Solicitação de acesso à API HidroWebService para consumo de dados") e configurar os secrets `HIDROWEB_IDENTIFICADOR` e `HIDROWEB_SENHA` no GitHub |
| IBGE | Sim, pública, sem token | Já funciona — usado só como tabela de referência (município/UF) |
| CEMADEN | Não existe API | Baixar manualmente todo mês no Mapa Interativo (mapainterativo.cemaden.gov.br) e colocar os arquivos em `data/raw/cemaden/` |
| Monitor de Secas (ANA) | Não existe API | Baixar manualmente todo mês em monitordesecas.ana.gov.br/dados-tabulares e colocar os arquivos em `data/raw/monitor_secas/`, nomeados `RS_monitor_secas.xlsx` / `SP_monitor_secas.xlsx` |

Nota sobre o HidroWebService: essa API não permite pedir um mês específico do
passado — ela sempre devolve os últimos 30 dias a partir de hoje. Rodando a
coleta todo mês, mesmo assim se constrói um histórico contínuo com o tempo.

## Como colocar no ar (GitHub Actions)

1. Publique esta pasta como um repositório no GitHub (via GitHub Desktop).
2. Em Settings → Secrets and variables → Actions, crie os secrets
   `HIDROWEB_IDENTIFICADOR` (seu CPF/CNPJ) e `HIDROWEB_SENHA` (senha recebida
   por e-mail da ANA), quando a solicitação for aprovada.
3. O workflow `.github/workflows/coleta-mensal.yml` já roda automaticamente todo
   dia 2 do mês, às 06h UTC. Também dá pra disparar manualmente pela aba **Actions**
   (botão "Run workflow").
4. Cada execução grava/atualiza `data/clima.db` e `data/dados_consolidados.csv`,
   e commita o resultado de volta no repositório automaticamente.

## Banco de dados

Usa **SQLite** (`data/clima.db`), versionado junto com o código — zero custo,
zero serviço externo. Suficiente para o volume mensal deste projeto.

## BI (Google Sheets + Looker Studio)

1. No Google Sheets, use `=IMPORTDATA("https://raw.githubusercontent.com/SEU_USUARIO/SEU_REPO/main/data/dados_consolidados.csv")`
   pra puxar o histórico direto do GitHub.
2. Conecte essa planilha no **Looker Studio** (conector nativo do Google Sheets, gratuito)
   pra montar os gráficos/painéis.
3. Toda vez que o GitHub Actions rodar e atualizar o CSV, o Google Sheets e o Looker
   Studio atualizam sozinhos (o Sheets reconsulta o IMPORTDATA periodicamente).

## Rodando localmente para testar

```bash
pip install -r requirements.txt
python main.py
```

## Próximos ajustes recomendados

- Conferir os nomes de campo retornados pela API do INMET e da ANA na primeira
  execução real (os scripts imprimem as colunas recebidas no console) e ajustar
  os mapeamentos em `collectors/inmet.py` e `collectors/hidroweb.py` se necessário.
- Adicionar mais estações em `ESTACOES_INMET` / `ESTACOES_HIDROWEB` no `main.py`.
