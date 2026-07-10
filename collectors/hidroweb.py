"""
Coletor ANA / HidroWebService - dados de chuva, nível de rio (cota) e vazão.

A ANA migrou o sistema antigo (snirh.gov.br/hidroweb/rest/api) para um novo
serviço chamado HidroWebService, documentado aqui:
https://www.gov.br/ana/pt-br/assuntos/monitoramento-e-eventos-criticos/monitoramento-hidrologico/orientacoes-manuais/manuais/manual-hidrowebservice_publica.pdf

COMO OBTER ACESSO:
1. Envie um e-mail para hidro@ana.gov.br com o assunto:
   "[seu CPF ou CNPJ] - Solicitação de acesso à API HidroWebService para consumo de dados"
2. No corpo, informe: nome completo (e instituição, se houver), CPF/CNPJ,
   e-mail de contato, e uma breve explicação do uso.
3. Você receberá uma senha por e-mail. O CPF/CNPJ usado no cadastro é o
   "identificador" (usuário) de login.

Diferente do sistema antigo, aqui a autenticação é feita em duas etapas:
1. Pede um token (válido por 60 min) usando identificador + senha.
2. Usa esse token (Bearer) nas chamadas de consulta de dados.

Configure as credenciais como variáveis de ambiente:
- HIDROWEB_IDENTIFICADOR (seu CPF ou CNPJ)
- HIDROWEB_SENHA (senha recebida por e-mail)
"""

import os
import time
import requests
import pandas as pd

BASE_URL = "https://www.ana.gov.br/hidrowebservice/EstacoesTelemetricas"

HIDROWEB_IDENTIFICADOR = os.environ.get("HIDROWEB_IDENTIFICADOR", "")
HIDROWEB_SENHA = os.environ.get("HIDROWEB_SENHA", "")

# Cache simples do token em memória (evita pedir um token novo a cada chamada,
# já que o manual da ANA avisa que pedidos de autenticação em alta frequência
# podem levar ao bloqueio automático do IP).
_token_cache = {"token": None, "obtido_em": 0}
VALIDADE_TOKEN_SEGUNDOS = 55 * 60  # 55 min (o token dura 60 min; margem de segurança)


def _obter_token() -> str:
    """Autentica com identificador+senha e retorna um token Bearer válido."""
    agora = time.time()
    if _token_cache["token"] and (agora - _token_cache["obtido_em"]) < VALIDADE_TOKEN_SEGUNDOS:
        return _token_cache["token"]

    if not HIDROWEB_IDENTIFICADOR or not HIDROWEB_SENHA:
        raise RuntimeError(
            "HIDROWEB_IDENTIFICADOR e/ou HIDROWEB_SENHA não configurados. "
            "Solicite acesso em hidro@ana.gov.br (ver instruções no topo deste arquivo)."
        )

    url = f"{BASE_URL}/OAUth/v1"
    headers = {
        "Identificador": HIDROWEB_IDENTIFICADOR,
        "Senha": HIDROWEB_SENHA,
    }
    resp = requests.get(url, headers=headers, timeout=30)
    resp.raise_for_status()
    dados = resp.json()

    token = dados.get("items", {}).get("tokenautenticacao")
    if not token:
        raise RuntimeError(f"Não foi possível obter token. Resposta da API: {dados}")

    _token_cache["token"] = token
    _token_cache["obtido_em"] = agora
    return token


def consultar_serie_estacao(codigo_estacao: str, dias: int = 30) -> pd.DataFrame:
    """
    Busca a série telemétrica (chuva, cota/nível, vazão) de uma estação nos
    últimos N dias. A API não permite escolher um mês específico do passado -
    trabalha sempre com uma janela "últimos N dias" a partir de hoje.
    Valores aceitos de `dias` pela API: 30, 15 (ver DIAS_30 / DIAS_15 no manual).
    """
    token = _obter_token()
    url = f"{BASE_URL}/HidroinfoanaSerieTelemetricaAdotada/v1"
    params = {
        "CodigoDaEstacao": codigo_estacao,
        "TipoFiltroData": "DATA_LEITURA",
        "RangeIntervaloDeBusca": f"DIAS_{dias}",
    }
    headers = {"Authorization": f"Bearer {token}"}
    resp = requests.get(url, params=params, headers=headers, timeout=60)
    resp.raise_for_status()
    dados = resp.json()

    itens = dados.get("items", [])
    if not itens:
        return pd.DataFrame(columns=["fonte", "estacao_codigo", "data", "variavel", "valor", "unidade"])

    registros = []
    for item in itens:
        data_medicao = item.get("Data_Hora_Medicao")
        mapeamento = {
            "Chuva_Adotada": ("precipitacao_mm", "mm"),
            "Cota_Adotada": ("nivel_rio_cm", "cm"),
            "Vazao_Adotada": ("vazao_m3s", "m3/s"),
        }
        for campo, (variavel, unidade) in mapeamento.items():
            valor = item.get(campo)
            if valor is None or valor == "":
                continue
            registros.append({
                "fonte": "HidroWeb-ANA",
                "estacao_codigo": item.get("codigoestacao", codigo_estacao),
                "data": data_medicao,
                "variavel": variavel,
                "valor": valor,
                "unidade": unidade,
            })

    return pd.DataFrame(registros)


def coletar_mes(codigos_estacoes: list, ano: int, mes: int) -> pd.DataFrame:
    """
    Mantido com essa assinatura por compatibilidade com o main.py, mas a API
    do HidroWebService não permite pedir um mês específico do passado — ela
    sempre retorna os últimos 30 dias a partir de hoje. Os parâmetros ano/mes
    são ignorados aqui; rodando isso mensalmente já garante boa cobertura contínua.
    """
    dataframes = []
    for codigo in codigos_estacoes:
        try:
            df = consultar_serie_estacao(codigo, dias=30)
            dataframes.append(df)
            print(f"[HidroWeb] Estação {codigo}: {len(df)} registros")
        except Exception as e:
            print(f"[ERRO] HidroWeb estação {codigo}: {e}")

    if not dataframes:
        return pd.DataFrame(columns=["fonte", "estacao_codigo", "data", "variavel", "valor", "unidade"])
    return pd.concat(dataframes, ignore_index=True)


if __name__ == "__main__":
    if not HIDROWEB_IDENTIFICADOR or not HIDROWEB_SENHA:
        print("[AVISO] Credenciais não configuradas. Solicite acesso em hidro@ana.gov.br "
              "(ver instruções no topo deste arquivo).")
    else:
        df = consultar_serie_estacao("15400000")
        print(df.head())
