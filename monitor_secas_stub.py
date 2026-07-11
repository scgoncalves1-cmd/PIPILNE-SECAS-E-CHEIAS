"""
Coletor Monitor de Secas do Brasil (ANA/Cemaden) - LIMITAÇÃO CONHECIDA: sem link fixo pra baixar.

O Monitor de Secas (https://monitordesecas.ana.gov.br/dados-tabulares) tem um
botão de download em XLS, mas o download é disparado por JavaScript (não é um
link direto), então não dá pra automatizar com uma simples requisição HTTP.

FORMATO REAL DO ARQUIVO (confirmado com um XLS de exemplo):
Cada linha é um mês, e as colunas são o percentual da área (do estado/região
selecionada no site antes do download) em cada categoria de severidade da seca,
de forma cumulativa:
    mapas       | semSeca | s0s4  | s1s4 | s2s4 | s3s4 | s4
    Maio de 2026|    0    | 100   |  0   |  0   |  0   |  0

- semSeca = % da área sem seca
- s0s4    = % da área em seca S0 ou pior
- s1s4    = % da área em seca S1 ou pior
- s2s4    = % da área em seca S2 ou pior
- s3s4    = % da área em seca S3 ou pior
- s4      = % da área em seca S4 (excepcional)

IMPORTANTE: o arquivo não indica o estado/região dentro dos dados - isso é
definido pelo filtro escolhido no site ANTES de baixar. Por isso, nomeie o
arquivo baixado incluindo a UF, por exemplo:
    data/raw/monitor_secas/RS_monitor_secas.xlsx
    data/raw/monitor_secas/SP_monitor_secas.xlsx
O coletor extrai a UF a partir do nome do arquivo (os 2 primeiros caracteres,
antes do "_"). Se não conseguir identificar, marca a UF como "DESCONHECIDA".

PROCESSO MANUAL MENSAL:
Salve os arquivos baixados dentro de data/raw/monitor_secas/, um por
estado/consulta, nomeados como acima. Este coletor lê TODOS os arquivos
.xls/.xlsx dessa pasta de uma vez e junta tudo.
"""

import os
import re
import glob
import datetime
import pandas as pd

MESES_PT = {
    "janeiro": 1, "fevereiro": 2, "março": 3, "marco": 3, "abril": 4,
    "maio": 5, "junho": 6, "julho": 7, "agosto": 8, "setembro": 9,
    "outubro": 10, "novembro": 11, "dezembro": 12,
}

COLUNAS_CATEGORIA = ["semSeca", "s0s4", "s1s4", "s2s4", "s3s4", "s4"]


def _parse_mes_ano(texto: str):
    """Converte 'Maio de 2026' -> data(2026, 5, 1). Se não conseguir, devolve None."""
    if not isinstance(texto, str):
        return None
    m = re.match(r"([A-Za-zçÇ]+)\s+de\s+(\d{4})", texto.strip())
    if not m:
        return None
    nome_mes, ano = m.group(1).lower(), int(m.group(2))
    mes = MESES_PT.get(nome_mes)
    if not mes:
        return None
    return datetime.date(ano, mes, 1)


def _extrair_uf_do_nome(caminho_arquivo: str) -> str:
    """Espera nomes como 'RS_monitor_secas.xlsx' -> 'RS'. Ajuste aqui se usar outra convenção."""
    nome = os.path.basename(caminho_arquivo)
    partes = nome.replace(".xlsx", "").replace(".xls", "").split("_")
    possivel_uf = partes[0].strip().upper()
    if len(possivel_uf) == 2 and possivel_uf.isalpha():
        return possivel_uf
    return "DESCONHECIDA"


def _normalizar_um_arquivo(caminho_arquivo: str) -> pd.DataFrame:
    df_raw = pd.read_excel(caminho_arquivo)
    print(f"[Monitor de Secas] {os.path.basename(caminho_arquivo)} — colunas recebidas: {list(df_raw.columns)}")

    colunas_presentes = [c for c in COLUNAS_CATEGORIA if c in df_raw.columns]
    if "mapas" not in df_raw.columns or not colunas_presentes:
        raise ValueError(
            f"Cabeçalho de {os.path.basename(caminho_arquivo)} não bateu com o esperado "
            f"(colunas recebidas: {list(df_raw.columns)}). Ajuste este arquivo se a ANA "
            f"mudou o formato do XLS."
        )

    uf = _extrair_uf_do_nome(caminho_arquivo)

    registros = []
    for _, row in df_raw.iterrows():
        data_mes = _parse_mes_ano(row.get("mapas"))
        for categoria in colunas_presentes:
            valor = row.get(categoria)
            if pd.isna(valor):
                continue

            # Sanidade: essas colunas são sempre um percentual de área (0 a 100).
            # Alguns arquivos baixados do site vêm com célula corrompida/mal formatada
            # (ex: número gigante tipo notação científica) - descarta e avisa em vez
            # de deixar esse lixo entrar no painel.
            try:
                valor_num = float(valor)
            except (TypeError, ValueError):
                print(f"[AVISO] Monitor de Secas: valor não numérico em "
                      f"{os.path.basename(caminho_arquivo)} ({categoria}, {row.get('mapas')}): {valor!r} — ignorado.")
                continue
            if not (0 <= valor_num <= 100):
                print(f"[AVISO] Monitor de Secas: valor fora do intervalo esperado (0-100) em "
                      f"{os.path.basename(caminho_arquivo)} ({categoria}, {row.get('mapas')}): {valor_num} — ignorado.")
                continue

            registros.append({
                "fonte": "MonitorDeSecas-ANA",
                "estacao_codigo": uf,
                "data": data_mes.isoformat() if data_mes else None,
                "variavel": f"seca_{categoria}",
                "valor": valor_num,
                "unidade": "pct_area",
            })

    return pd.DataFrame(registros)


def carregar_pasta_manual(pasta: str) -> pd.DataFrame:
    """
    Lê todos os arquivos .xls/.xlsx dentro de `pasta` (baixados manualmente do
    Monitor de Secas) e devolve tudo junto, já padronizado.
    """
    arquivos = sorted(glob.glob(os.path.join(pasta, "*.xls")) + glob.glob(os.path.join(pasta, "*.xlsx")))
    if not arquivos:
        return pd.DataFrame(columns=["fonte", "estacao_codigo", "data", "variavel", "valor", "unidade"])

    dataframes = []
    for caminho in arquivos:
        try:
            dataframes.append(_normalizar_um_arquivo(caminho))
        except Exception as e:
            print(f"[ERRO] Monitor de Secas ao ler {os.path.basename(caminho)}: {e}")

    if not dataframes:
        return pd.DataFrame(columns=["fonte", "estacao_codigo", "data", "variavel", "valor", "unidade"])

    return pd.concat(dataframes, ignore_index=True)


if __name__ == "__main__":
    print(__doc__)
