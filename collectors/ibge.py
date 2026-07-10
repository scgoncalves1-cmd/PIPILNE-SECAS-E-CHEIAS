"""
Coletor IBGE - referência geográfica municipal + dados agregados (SIDRA).

O IBGE não produz dados climáticos diretos (chuva, temperatura), mas é essencial
como tabela de referência (município -> UF -> código IBGE) para cruzar com as
demais fontes (INMET, HidroWeb, CEMADEN), que costumam identificar estações por
coordenadas ou nomes de município.

APIs oficiais, sem necessidade de token:
- GET https://servicodados.ibge.gov.br/api/v1/localidades/municipios      -> lista de municípios
- GET https://apisidra.ibge.gov.br/values/t/{tabela}/n1/all/v/{variavel}  -> dados agregados (SIDRA)
"""

import requests
import pandas as pd

LOCALIDADES_URL = "https://servicodados.ibge.gov.br/api/v1/localidades/municipios"
SIDRA_URL = "https://apisidra.ibge.gov.br/values"


def _safe_get(d, *chave_caminho):
    """
    Navega por dicionários aninhados sem quebrar quando algum nível vem
    como None (o que acontece em alguns municípios na API do IBGE, já que
    nem todos têm microrregiao/mesorregiao preenchida da mesma forma).
    """
    atual = d
    for chave in chave_caminho:
        if not isinstance(atual, dict):
            return None
        atual = atual.get(chave)
    return atual


def listar_municipios() -> pd.DataFrame:
    """Retorna todos os municípios do Brasil com código IBGE, UF e região."""
    resp = requests.get(LOCALIDADES_URL, timeout=60)
    resp.raise_for_status()
    dados = resp.json()

    registros = []
    for m in dados:
        # Tenta primeiro pela divisão mais nova (regiao-imediata/regiao-intermediaria);
        # se não existir, cai para a divisão antiga (microrregiao/mesorregiao).
        uf = (
            _safe_get(m, "regiao-imediata", "regiao-intermediaria", "UF")
            or _safe_get(m, "microrregiao", "mesorregiao", "UF")
            or {}
        )
        registros.append({
            "municipio_codigo_ibge": m.get("id"),
            "municipio_nome": m.get("nome"),
            "uf_sigla": uf.get("sigla") if isinstance(uf, dict) else None,
            "uf_nome": uf.get("nome") if isinstance(uf, dict) else None,
            "regiao_nome": _safe_get(uf, "regiao", "nome") if isinstance(uf, dict) else None,
        })
    return pd.DataFrame(registros)


def consultar_tabela_sidra(tabela: str, variavel: str, nivel_territorial: str = "n1",
                            localidade: str = "all") -> pd.DataFrame:
    """
    Consulta uma tabela agregada do SIDRA (ex: dados de agropecuária, população etc.,
    úteis para cruzar impacto de secas/cheias com dados socioeconômicos).
    """
    url = f"{SIDRA_URL}/t/{tabela}/{nivel_territorial}/{localidade}/v/{variavel}"
    resp = requests.get(url, timeout=60)
    resp.raise_for_status()
    dados = resp.json()
    # A primeira linha do retorno da SIDRA é sempre o cabeçalho descritivo
    return pd.DataFrame(dados[1:]) if len(dados) > 1 else pd.DataFrame()


if __name__ == "__main__":
    municipios = listar_municipios()
    print(municipios.head())
    print(f"Total de municípios: {len(municipios)}")
