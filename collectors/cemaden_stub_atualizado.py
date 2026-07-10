"""
Coletor CEMADEN - LIMITAÇÃO CONHECIDA: não há API pública.

O CEMADEN disponibiliza dados de pluviômetros/estações via Mapa Interativo
(https://mapainterativo.cemaden.gov.br/):
1. Clique em "Estações" na barra de ferramentas do mapa e selecione o equipamento;
2. Clique no botão "Download de Dados";
3. Preencha nome/e-mail e envie — o CEMADEN manda um e-mail com o link do arquivo (XLS).
4. O download é limitado a 1 mês por vez, por isso normalmente você acumula
   vários arquivos (um por mês/estação) ao longo do tempo.

PROCESSO MANUAL MENSAL:
Salve todos os arquivos baixados dentro da pasta data/raw/cemaden/ (pode ter
quantos arquivos quiser ali - um por mês, por estação, etc). Este coletor lê
TODOS os arquivos .csv/.xls/.xlsx dessa pasta de uma vez e junta tudo.

NOTA: na prática, o link enviado por e-mail pelo CEMADEN costuma baixar um
arquivo .csv (o navegador renomeia automaticamente pra "data (1).csv",
"data (2).csv" etc quando baixa vários com o mesmo nome — isso não é problema,
o conteúdo de cada arquivo é lido normalmente).

IMPORTANTE: como o cabeçalho real do arquivo pode variar, o script imprime as
colunas recebidas de cada arquivo no console — ajuste `COLUNAS_POSSIVEIS`
abaixo conforme necessário depois de ver esse log.
"""

import os
import glob
import unicodedata
import pandas as pd


def _sem_acento(texto) -> str:
    """Remove acentos e deixa minúsculo, pra comparar nomes de coluna sem depender de acentuação."""
    if not isinstance(texto, str):
        return texto
    normalizado = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in normalizado if not unicodedata.combining(c)).strip().lower()


# Nomes de coluna conhecidos/prováveis do CEMADEN, já sem acento e minúsculo.
COLUNAS_POSSIVEIS = {
    "codestacao": "estacao_codigo",
    "codigoestacao": "estacao_codigo",
    "codigo da estacao": "estacao_codigo",
    "estacao": "estacao_codigo",
    "municipio": "estacao_codigo",
    "datahora": "data",
    "data": "data",
    "data/hora": "data",
    "datahoramedicao": "data",
    "valormedida": "valor",
    "valor": "valor",
    "chuva": "valor",
    "acumulado": "valor",
}


def _ler_arquivo_bruto(caminho_arquivo: str) -> pd.DataFrame:
    """Lê .csv com pandas.read_csv e .xls/.xlsx com pandas.read_excel."""
    extensao = os.path.splitext(caminho_arquivo)[1].lower()
    if extensao == ".csv":
        # O CEMADEN costuma usar ';' como separador e vírgula decimal (padrão BR).
        # Tenta primeiro nesse formato; se der erro de parsing, tenta o padrão internacional.
        try:
            return pd.read_csv(caminho_arquivo, sep=";", decimal=",", encoding="utf-8")
        except Exception:
            try:
                return pd.read_csv(caminho_arquivo, sep=";", decimal=",", encoding="latin1")
            except Exception:
                return pd.read_csv(caminho_arquivo)
    return pd.read_excel(caminho_arquivo)


def _normalizar_um_arquivo(caminho_arquivo: str) -> pd.DataFrame:
    df_raw = _ler_arquivo_bruto(caminho_arquivo)
    print(f"[CEMADEN] {os.path.basename(caminho_arquivo)} — colunas recebidas: {list(df_raw.columns)}")

    novas_colunas = {}
    for col in df_raw.columns:
        chave = _sem_acento(col)
        if chave in COLUNAS_POSSIVEIS:
            novas_colunas[col] = COLUNAS_POSSIVEIS[chave]
    df = df_raw.rename(columns=novas_colunas)

    if "estacao_codigo" not in df.columns or "data" not in df.columns or "valor" not in df.columns:
        raise ValueError(
            f"Cabeçalho de {os.path.basename(caminho_arquivo)} não bateu com o esperado "
            f"(colunas recebidas: {list(df_raw.columns)}). Ajuste COLUNAS_POSSIVEIS em "
            f"collectors/cemaden_stub.py com os nomes reais."
        )

    df["fonte"] = "CEMADEN"
    d