"""
Orquestrador mensal do pipeline de dados climáticos (secas/cheias).

Pensado para rodar via GitHub Actions (cron mensal), mas funciona igual
rodando localmente: `python main.py`.

O que faz:
1. Coleta o mês anterior de cada fonte configurada (INMET, HidroWeb/ANA, CEMADEN manual, Monitor de Secas manual);
2. Salva um CSV bruto por fonte em data/raw/;
3. Consolida tudo num único DataFrame padronizado;
4. Grava no banco SQLite local (data/clima.db) — arquivo simples, versionável no
   próprio repositório Git, sem depender de nenhum serviço externo pago;
5. Exporta o histórico completo em data/dados_consolidados.csv — esse arquivo
   é o que o Google Sheets lê direto do GitHub (via IMPORTDATA), pra alimentar
   o Looker Studio sem precisar de nenhum banco de dados externo.
"""

import os
import sys
import sqlite3
import datetime
import pandas as pd

sys.path.append(os.path.dirname(__file__))
from collectors import inmet, ibge, hidroweb, cemaden_stub, monitor_secas_stub  # noqa: E402

DIR_ATUAL = os.path.dirname(os.path.abspath(__file__))
DIR_DATA = os.path.join(DIR_ATUAL, "data")
DIR_RAW = os.path.join(DIR_DATA, "raw")
CAMINHO_DB = os.path.join(DIR_DATA, "clima.db")

# --- CONFIGURAÇÃO: ajuste com as estações que interessam ao seu painel ---
# Todas as estações automáticas do INMET no Rio Grande do Sul (RS) e em São Paulo (SP).
# O INMET não tem uma estação em cada cidade — esta é a cobertura máxima disponível
# nessa fonte para os dois estados. Algumas estações podem aparecer com status "Pane"
# (fora do ar temporariamente) — nesse caso o coletor só vai logar [ERRO] pra ela e
# seguir normalmente com as demais, sem quebrar o resto da coleta.
ESTACOES_INMET = [
    # --- Rio Grande do Sul (RS) ---
    "B828",  # ACEGUA
    "B843",  # AJURICABA
    "A826",  # ALEGRETE
    "B847",  # ALEGRETE (MARONNA)
    "A827",  # BAGE
    "B827",  # BAGE - CENTRO
    "B848",  # BARRA DO QUARAI
    "A840",  # BENTO GONCALVES
    "B856",  # BOM JESUS (INMET)
    "B857",  # BOM JESUS - SANTO INACIO
    "A812",  # CACAPAVA DO SUL
    "B822",  # CACHOEIRA DO SUL
    "B808",  # CACHOEIRINHA
    "A838",  # CAMAQUA
    "A897",  # CAMBARA DO SUL
    "A884",  # CAMPO BOM
    "A879",  # CANELA
    "A811",  # CANGUCU
    "B832",  # CAPAO DA CANOA
    "A887",  # CAPAO DO LEAO (PELOTAS)
    "B842",  # CARAZINHO
    "B858",  # CASCA
    # --- São Paulo (SP) ---
    "A736",  # ARIRANHA
    "A725",  # AVARE
    "A741",  # BARRA BONITA
    "A746",  # BARRA DO TURVO
    "A748",  # BARRETOS
    "A755",  # BARUERI
    "A705",  # BAURU
    "A764",  # BEBEDOURO
    "A765",  # BERTIOGA
    "A744",  # BRAGANCA PAULISTA
    "A769",  # CACHOEIRA PAULISTA
    "A706",  # CAMPOS DO JORDAO
    "A738",  # CASA BRANCA
]
ESTACOES_HIDROWEB = ["00847000"]   # códigos de estações telemétricas ANA (ajustar depois, com token)

# CEMADEN e Monitor de Secas não têm API - você baixa manualmente do site e
# solta os arquivos .xls/.xlsx dentro destas pastas. Pode colocar quantos
# arquivos quiser (um por mês, por estação/estado, etc) - o programa lê todos de uma vez.
PASTA_CEMADEN_MANUAL = os.path.join(DIR_RAW, "cemaden")
PASTA_MONITOR_SECAS_MANUAL = os.path.join(DIR_RAW, "monitor_secas")
# ---------------------------------------------------------------------


def mes_anterior():
    hoje = datetime.date.today()
    primeiro_dia_mes_atual = hoje.replace(day=1)
    ultimo_dia_mes_anterior = primeiro_dia_mes_atual - datetime.timedelta(days=1)
    return ultimo_dia_mes_anterior.year, ultimo_dia_mes_anterior.month


def coletar_tudo(ano: int, mes: int) -> pd.DataFrame:
    os.makedirs(DIR_RAW, exist_ok=True)
    dataframes = []

    # INMET
    for codigo in ESTACOES_INMET:
        try:
            df = inmet.coletar_mes(codigo, ano, mes)
            df.to_csv(os.path.join(DIR_RAW, f"inmet_{codigo}_{ano}{mes:02d}.csv"), index=False)
            dataframes.append(df)
            print(f"[OK] INMET {codigo}: {len(df)} registros")
        except Exception as e:
            print(f"[ERRO] INMET {codigo}: {e}")

    # HidroWeb / ANA
    if ESTACOES_HIDROWEB:
        try:
            df = hidroweb.coletar_mes(ESTACOES_HIDROWEB, ano, mes)
            df.to_csv(os.path.join(DIR_RAW, f"hidroweb_{ano}{mes:02d}.csv"), index=False)
            dataframes.append(df)
            print(f"[OK] HidroWeb: {len(df)} registros")
        except Exception as e:
            print(f"[ERRO] HidroWeb: {e}")

    # CEMADEN (manual — lê todos os arquivos .csv/.xls/.xlsx da pasta)
    os.makedirs(PASTA_CEMADEN_MANUAL, exist_ok=True)
    try:
        df = cemaden_stub.carregar_pasta_manual(PASTA_CEMADEN_MANUAL)
        if not df.empty:
            dataframes.append(df)
            print(f"[OK] CEMADEN (manual): {len(df)} registros")
        else:
            print(f"[AVISO] CEMADEN: nenhum arquivo .csv/.xls/.xlsx encontrado em {PASTA_CEMADEN_MANUAL}. "
                  f"Baixe no Mapa Interativo e coloque os arquivos nessa pasta antes de rodar.")
    except Exception as e:
        print(f"[ERRO] CEMADEN: {e}")

    # Monitor de Secas (manual — mesma lógica, lê todos os arquivos da pasta)
    os.makedirs(PASTA_MONITOR_SECAS_MANUAL, exist_ok=True)
    try:
        df = monitor_secas_stub.carregar_pasta_manual(PASTA_MONITOR_SECAS_MANUAL)
        if not df.empty:
            dataframes.append(df)
            print(f"[OK] Monitor de Secas (manual): {len(df)} registros")
        else:
            print(f"[AVISO] Monitor de Secas: nenhum arquivo .xls/.xlsx encontrado em {PASTA_MONITOR_SECAS_MANUAL}. "
                  f"Baixe em monitordesecas.ana.gov.br/dados-tabulares e coloque os arquivos nessa pasta antes de rodar.")
    except Exception as e:
        print(f"[ERRO] Monitor de Secas: {e}")

    if not dataframes:
        return pd.DataFrame(columns=["fonte", "estacao_codigo", "data", "variavel", "valor", "unidade"])

    return pd.concat(dataframes, ignore_index=True)


CHAVE_UNICA = ["fonte", "estacao_codigo", "data", "variavel"]


def salvar_no_banco(df: pd.DataFrame):
    """
    Grava os registros no SQLite, mas SUBSTITUINDO qualquer registro já existente
    com a mesma chave (fonte + estacao_codigo + data + variavel), em vez de só
    empilhar por cima. Isso é importante porque:
    - Os arquivos manuais do CEMADEN e do Monitor de Secas continuam na pasta
      raw/ permanentemente, então toda coleta mensal os lê de novo - sem essa
      troca, cada execução duplicaria os mesmos dados sem parar.
    - Se um valor for corrigido (ex: bug no script) e a coleta rodar de novo,
      o valor novo substitui o antigo em vez de conviver com o errado.
    """
    os.makedirs(DIR_DATA, exist_ok=True)
    conn = sqlite3.connect(CAMINHO_DB)

    existe_tabela = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='dados_climaticos'"
    ).fetchone()

    if existe_tabela:
        df_existente = pd.read_sql("SELECT * FROM dados_climaticos", conn)
        df_combinado = pd.concat([df_existente, df], ignore_index=True)
    else:
        df_combinado = df

    # Mantém a última ocorrência de cada chave (os dados novos, já que foram
    # concatenados por último), descartando duplicatas antigas.
    df_combinado = df_combinado.drop_duplicates(subset=CHAVE_UNICA, keep="last")

    df_combinado.to_sql("dados_climaticos", conn, if_exists="replace", index=False)
    conn.close()
    print(f"[OK] {len(df)} registros processados nesta coleta — banco agora tem {len(df_combinado)} registros no total")


def exportar_csv_consolidado():
    """
    Reexporta o histórico completo (todas as coletas já feitas, não só a
    deste mês) para data/dados_consolidados.csv. É esse arquivo que o Google
    Sheets lê direto do GitHub via IMPORTDATA, pra alimentar o Looker Studio.
    """
    conn = sqlite3.connect(CAMINHO_DB)
    existe_tabela = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='dados_climaticos'"
    ).fetchone()

    if not existe_tabela:
        conn.close()
        print("[AVISO] Tabela 'dados_climaticos' ainda não existe (nenhuma coleta teve sucesso "
              "ainda). Pulando exportação do CSV consolidado por enquanto.")
        return

    df_tudo = pd.read_sql("SELECT * FROM dados_climaticos", conn)
    conn.close()

    caminho_csv = os.path.join(DIR_DATA, "dados_consolidados.csv")
    df_tudo.to_csv(caminho_csv, index=False)
    print(f"[OK] CSV consolidado exportado: {caminho_csv} ({len(df_tudo)} linhas no total)")


def atualizar_referencia_ibge():
    """Roda com pouca frequência (municípios quase não mudam) — mantém tabela de apoio."""
    df = ibge.listar_municipios()
    os.makedirs(DIR_DATA, exist_ok=True)
    conn = sqlite3.connect(CAMINHO_DB)
    df.to_sql("municipios_ibge", conn, if_exists="replace", index=False)
    conn.close()
    print(f"[OK] Referência IBGE atualizada: {len(df)} municípios")


if __name__ == "__main__":
    ano, mes = mes_anterior()
    print(f"Coletando dados de {mes:02d}/{ano}...")

    df_final = coletar_tudo(ano, mes)
    if not df_final.empty:
        salvar_no_banco(df_final)
    else:
        print("[AVISO] Nenhum dado coletado neste mês.")

    try:
        atualizar_referencia_ibge()
    except Exception as e:
        print(f"[ERRO] Referência IBGE: {e}")

    try:
        exportar_csv_consolidado()
    except Exception as e:
        print(f"[ERRO] Exportação do CSV consolidado: {e}")
