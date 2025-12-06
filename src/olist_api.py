"""
Módulo para integração com a API do Tiny/Olist.
Permite enviar pedidos diretamente para o sistema Olist via API.

Documentação da API: https://tiny.com.br/api-docs/api2-pedidos-incluir
"""

import os
import requests
import json
from datetime import datetime
from typing import Dict, Any, List, Optional
import pandas as pd


# Configurações da API
TINY_API_BASE_URL = "https://api.tiny.com.br/api2"
TINY_API_INCLUIR_PEDIDO = f"{TINY_API_BASE_URL}/pedido.incluir.php"


def get_token() -> str:
    """
    Obtém o token da API a partir de variável de ambiente.
    
    Returns:
        str: Token da API
        
    Raises:
        ValueError: Se o token não estiver configurado
    """
    token = os.environ.get('OLIST_API_TOKEN')
    if not token:
        raise ValueError(
            "Token da API Olist não configurado. "
            "Configure a variável de ambiente OLIST_API_TOKEN"
        )
    return token


def converter_df_para_pedido_json(
    df: pd.DataFrame,
    cliente_id: str,
    cliente_nome: str,
    numero_pedido: Optional[str] = None,
    data_pedido: Optional[str] = None
) -> Dict[str, Any]:
    """
    Converte um DataFrame no formato Olist para o JSON aceito pela API do Tiny.
    
    Args:
        df: DataFrame com os itens do pedido (formato Olist)
        cliente_id: ID do cliente selecionado
        cliente_nome: Nome do cliente selecionado
        numero_pedido: Número da proposta/pedido (opcional)
        data_pedido: Data do pedido no formato dd/mm/yyyy (opcional)
        
    Returns:
        Dict com o pedido no formato JSON aceito pela API
    """
    # Formatar data
    if data_pedido is None:
        data_pedido = datetime.now().strftime("%d/%m/%Y")
    elif isinstance(data_pedido, pd.Timestamp):
        data_pedido = data_pedido.strftime("%d/%m/%Y")
    
    # Construir lista de itens
    itens = []
    for _, row in df.iterrows():
        # Pular linhas sem ID de produto válido
        id_produto = row.get('ID produto')
        if pd.isna(id_produto) or str(id_produto).strip() == '':
            continue
            
        item = {
            "item": {
                "id_produto": str(id_produto) if pd.notna(id_produto) else "",
                "descricao": str(row.get('Descrição', '')) if pd.notna(row.get('Descrição')) else "",
                "quantidade": float(row.get('Quantidade', 1)) if pd.notna(row.get('Quantidade')) else 1,
                "valor_unitario": float(row.get('Valor unitário', 0)) if pd.notna(row.get('Valor unitário')) else 0
            }
        }
        itens.append(item)
    
    # Construir estrutura do pedido
    pedido = {
        "pedido": {
            "data_pedido": data_pedido,
            "cliente": {
                "codigo": str(cliente_id),
                "nome": cliente_nome
            },
            "itens": itens,
            "situacao": "aberto"
        }
    }
    
    # Adicionar número do pedido se disponível
    if numero_pedido:
        pedido["pedido"]["numero_pedido_ecommerce"] = str(numero_pedido)
    
    return pedido


def enviar_pedido_olist(
    df: pd.DataFrame,
    cliente_id: str,
    cliente_nome: str,
    numero_pedido: Optional[str] = None,
    data_pedido: Optional[str] = None,
    token: Optional[str] = None
) -> Dict[str, Any]:
    """
    Envia um pedido para a API do Tiny/Olist.
    
    Args:
        df: DataFrame com os itens do pedido (formato Olist)
        cliente_id: ID do cliente
        cliente_nome: Nome do cliente
        numero_pedido: Número da proposta (opcional)
        data_pedido: Data do pedido (opcional)
        token: Token da API (se None, usa variável de ambiente)
        
    Returns:
        Dict com a resposta da API contendo status e detalhes
    """
    # Obter token
    if token is None:
        token = get_token()
    
    # Converter DataFrame para JSON do pedido
    pedido_json = converter_df_para_pedido_json(
        df, cliente_id, cliente_nome, numero_pedido, data_pedido
    )
    
    # Verificar se há itens no pedido
    if not pedido_json["pedido"]["itens"]:
        return {
            "status": "Erro",
            "erro": "Nenhum item válido encontrado no pedido",
            "pedido_enviado": pedido_json
        }
    
    # Preparar dados para envio
    pedido_str = json.dumps(pedido_json, ensure_ascii=False)
    
    data = {
        "token": token,
        "pedido": pedido_str,
        "formato": "JSON"
    }
    
    try:
        # Enviar requisição POST
        response = requests.post(
            TINY_API_INCLUIR_PEDIDO,
            data=data,
            timeout=30
        )
        response.raise_for_status()
        
        # Parsear resposta JSON
        resultado = response.json()
        
        # Adicionar informações extras ao resultado
        resultado["pedido_enviado"] = pedido_json
        resultado["itens_enviados"] = len(pedido_json["pedido"]["itens"])
        
        return resultado
        
    except requests.exceptions.Timeout:
        return {
            "status": "Erro",
            "erro": "Timeout na conexão com a API do Tiny",
            "pedido_enviado": pedido_json
        }
    except requests.exceptions.RequestException as e:
        return {
            "status": "Erro",
            "erro": f"Erro de conexão: {str(e)}",
            "pedido_enviado": pedido_json
        }
    except json.JSONDecodeError:
        return {
            "status": "Erro",
            "erro": "Resposta inválida da API (não é JSON)",
            "resposta_raw": response.text if 'response' in locals() else None,
            "pedido_enviado": pedido_json
        }


def validar_resposta_api(resposta: Dict[str, Any]) -> bool:
    """
    Valida se a resposta da API indica sucesso.
    
    Args:
        resposta: Dict com a resposta da API
        
    Returns:
        bool: True se o pedido foi incluído com sucesso
    """
    if not resposta:
        return False
    
    # Verificar estrutura da resposta do Tiny
    retorno = resposta.get("retorno", {})
    status = retorno.get("status", resposta.get("status", ""))
    
    return status.lower() == "ok"


def testar_conexao(token: Optional[str] = None) -> Dict[str, Any]:
    """
    Testa a conexão com a API do Tiny usando o endpoint de informações.
    
    Args:
        token: Token da API (se None, usa variável de ambiente)
        
    Returns:
        Dict com informações da conta ou erro
    """
    if token is None:
        token = get_token()
    
    url = f"{TINY_API_BASE_URL}/info.php"
    
    try:
        response = requests.get(
            url,
            params={"token": token, "formato": "JSON"},
            timeout=15
        )
        response.raise_for_status()
        return response.json()
    except Exception as e:
        return {
            "status": "Erro",
            "erro": str(e)
        }


if __name__ == "__main__":
    # Teste rápido de conexão
    import sys
    
    if len(sys.argv) > 1:
        test_token = sys.argv[1]
    else:
        test_token = None
    
    print("Testando conexão com API do Tiny/Olist...")
    resultado = testar_conexao(test_token)
    print(json.dumps(resultado, indent=2, ensure_ascii=False))
