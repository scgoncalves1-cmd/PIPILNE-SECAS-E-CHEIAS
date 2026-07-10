"""
Coletor INMET - Estações Automáticas
API não-oficial (comunidade), sem necessidade de token: https://apitempo.inmet.gov.br

Endpoints usados:
- GET /estacoes/T                                -> lista de estações automáticas
- GET /estacao/{data_inicial}/{data_final}/{cod}  -> dados horários de uma estação no período
  (SEM "dados" no meio do caminho — essa é a correção: a versão com "/dados/"
  no meio retorna 404, confirmado em teste real.)
"""

import requests
import pandas as pd

BASE_URL = "https://apitempo.inmet.gov.br"

# Sem esse cabeçalho "de navegador", o servidor do INMET às vezes devolve uma
# resposta vazia (bloqueio simples contra clientes automatizados).
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
}

# Mapeamento de variáveis retornadas pela API para nomes padronizados do pipeline.
# A API costuma variar levemente os nomes dos campos; ajuste aqui se necessário
# após a primeira execução real (o script imprime as colunas originais recebidas).
CAMPO_PARA_VARIAVEL = {
    "CHUVA": ("precipitacao_mm", "mm"),
    "TEM_INS": ("temperatura_c", "°C"),
    "TEM_MAX": ("temperatura_max_c", "°C"),
    "TEM_MIN": ("temperatura_min_c", "°C"),
    "UMD_INS": ("umidade_relativa_pct", "%"),
    "PRE_INS": ("pressao_atm_mb", "mB"),
    "VEN_VEL": ("vento_vel_ms", "m/s"),
}


def listar_estacoes(tipo: str = "T") -> pd.DataFrame:
    """Lista estações automáticas (T) ou convencionais (M) do INMET."""
    resp = requests.get(f"{BASE_URL}/estacoes/{tipo}", headers=HEADERS, timeout=30)
    resp.raise_for_status()
    dados = resp.json()
    df = pd.DataFrame(dados)
    return df


def coletar_dados_estacao(codigo_estacao: str, data_inicial: str, data_final: str) -> pd.DataFrame:
    """
    Coleta dados horários de uma estação automática entre duas datas.
    Datas no formato 'YYYY-MM-DD'.
    """
    url = f"{BASE_URL}/estacao/{data_inicial}/{data_final}/{codigo_estacao}"
    resp = requests.get(url, headers=HEADERS, timeout=60)
    resp.raise_for_status()

    if not resp.text.strip():
        # Resposta vazia - a estação pode estar sem dados nesse período, ou
        # o servidor pode ter recusado o pedido silenciosamente.
        raise RuntimeError("resposta vazia do servidor (sem dados nesse período ou pedido recusado)")

    dados = resp.json()

    if not dados:
        return pd.DataFrame(columns=["fonte", "estacao_codigo", "data", "variavel", "valor", "unidade"])

    df_raw = pd.DataFrame(dados)
    print(f"[INMET] Colunas recebidas da API: {list(df_raw.columns)}")

    registros = []
    for _, row in df_raw.iterrows():
        data_medicao = row.get("DT_MEDICAO")
        hora_medicao = row.get("HR_MEDICAO", "0000")
        for campo, (variavel, unidade) in CAMPO_PARA_VARIAVEL.items():
            valor = row.get(campo)
            if valor is None or valor == "":
                continue
            registros.append({
                "fonte": "INMET",
                "estacao_codigo": codigo_estacao,
                "data": f"{data_medicao} {hora_medicao}",
                "variavel": variavel,
                "valor": valor,
                "unidade": unidade,
            })

    return pd.DataFrame(registros)


def coletar_mes(codigo_estacao: str, ano: int, mes: int) -> pd.DataFrame:
    """Atalho para coletar um mês inteiro (usado pela automação mensal)."""
    import calendar
    ultimo_dia = calendar.monthrange(ano, mes)[1]
    data_inicial = f"{ano:04d}-{mes:02d}-01"
    data_final = f"{ano:04d}-{mes:02d}-{ultimo_dia:02d}"
    return coletar_dados_estacao(codigo_estacao, data_inicial, data_final)


if __name__ == "__main__":
    # Exemplo manual de uso
    estacoes = listar_estacoes("T")
    print(estacoes.head())
