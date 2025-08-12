import pandas as pd
import sys
import traceback
import re # Para normalização
import os
import io
from typing import Union, BinaryIO

def normalizar_texto(texto):
    if pd.isna(texto):
        return ""
    texto_str = str(texto).lower().strip()
    # Remover múltiplos espaços
    texto_str = re.sub(r'\s+', ' ', texto_str)
    return texto_str

def encontrar_linha_cabecalho(df_preview, palavras_chave_cabecalho):
    # Versão mais flexível que aceita variações como 'valor unitário' para 'valor'
    palavras_chave_normalizadas = [normalizar_texto(pc) for pc in palavras_chave_cabecalho]
    for i, row in df_preview.iterrows():
        valores_linha = [normalizar_texto(x) for x in row.tolist()]
        matches = 0
        for palavra_chave in palavras_chave_normalizadas:
            for valor in valores_linha:
                if palavra_chave in valor:
                    matches += 1
                    break
        if matches >= len(palavras_chave_normalizadas):
            return i
    # Versão original como fallback
    palavras_chave_normalizadas = [normalizar_texto(pc) for pc in palavras_chave_cabecalho]
    for i, row in df_preview.iterrows():
        valores_linha = [normalizar_texto(x) for x in row.tolist()]
        if all(palavra_chave in valores_linha for palavra_chave in palavras_chave_normalizadas):
            return i
    return None

def converter_orcamento_para_olist(
    arquivo_orcamento: Union[str, BinaryIO],
    caminho_mapeamento_produtos: str,
    caminho_clientes: str,
    id_cliente_selecionado: Union[str, int],
    caminho_modelo_saida_olist_com_dados: str
) -> pd.DataFrame:
    """
    Converte um arquivo de orçamento para o formato Olist.
    
    Args:
        arquivo_orcamento: Caminho do arquivo ou objeto BytesIO contendo o orçamento
        caminho_mapeamento_produtos: Caminho do arquivo de mapeamento de produtos
        caminho_clientes: Caminho do arquivo de clientes
        id_cliente_selecionado: ID do cliente selecionado
        caminho_modelo_saida_olist_com_dados: Caminho do arquivo modelo de saída
        
    Returns:
        DataFrame com o orçamento convertido no formato Olist
    """
    df_modelo_saida_temp = None
    colunas_modelo_olist = []
    produtos_nao_mapeados_log = [] # Lista para logar produtos não mapeados
    
    # Adicionar diagnóstico para verificar os arquivos
    print(f"[DIAGNÓSTICO] Verificando existência dos arquivos:")
    print(f"[DIAGNÓSTICO] Tipo arquivo_orcamento: {type(arquivo_orcamento)}")
    print(f"[DIAGNÓSTICO] caminho_mapeamento_produtos: {caminho_mapeamento_produtos} (Existe: {os.path.exists(caminho_mapeamento_produtos)})")
    print(f"[DIAGNÓSTICO] caminho_clientes: {caminho_clientes} (Existe: {os.path.exists(caminho_clientes)})")
    print(f"[DIAGNÓSTICO] caminho_modelo_saida_olist_com_dados: {caminho_modelo_saida_olist_com_dados} (Existe: {os.path.exists(caminho_modelo_saida_olist_com_dados)})")
    
    # Verificar se os arquivos existem antes de tentar abri-los
    # Não verificamos arquivo_orcamento quando é BytesIO
    arquivos_para_verificar = []
    if isinstance(arquivo_orcamento, str):
        arquivos_para_verificar.append((arquivo_orcamento, "orçamento"))
    
    arquivos_para_verificar.extend([
        (caminho_mapeamento_produtos, "mapeamento de produtos"),
        (caminho_clientes, "clientes"),
        (caminho_modelo_saida_olist_com_dados, "modelo de saída")
    ])
    
    for arquivo, descricao in arquivos_para_verificar:
        if not os.path.exists(arquivo):
            erro_msg = f"Arquivo de {descricao} não encontrado: {arquivo}"
            print(f"[CONVERSOR V6] ERRO: {erro_msg}", file=sys.stderr)
            raise FileNotFoundError(erro_msg)
    
    print(f"[CONVERSOR V6] Iniciando conversão. Cliente ID: {id_cliente_selecionado}", file=sys.stderr)
    
    try:
        print(f"[CONVERSOR V6] Lendo arquivo de mapeamento: {caminho_mapeamento_produtos}", file=sys.stderr)
        with pd.ExcelFile(caminho_mapeamento_produtos) as xls_map:
            df_mapeamento = pd.read_excel(xls_map, sheet_name='CATÁLOGO')
        
        # Normalizar a coluna de busca no mapeamento
        if 'SKU' in df_mapeamento.columns:
            df_mapeamento['SKU_NORMALIZADO_BUSCA'] = df_mapeamento['SKU'].apply(normalizar_texto)
            print(f"[CONVERSOR V6] Coluna 'SKU' normalizada para busca em df_mapeamento.", file=sys.stderr)
        else:
            print(f"[CONVERSOR V6] ERRO: Coluna 'SKU' não encontrada em {caminho_mapeamento_produtos}", file=sys.stderr)
            return pd.DataFrame(columns=colunas_modelo_olist if colunas_modelo_olist else [])
        
        print(f"[CONVERSOR V6] Lendo arquivo de clientes: {caminho_clientes}", file=sys.stderr)
        with pd.ExcelFile(caminho_clientes) as xls_cli:
            df_clientes = pd.read_excel(xls_cli, sheet_name='CLIENTES')
        
        print(f"[CONVERSOR V6] Lendo NOVO arquivo modelo de saída com dados: {caminho_modelo_saida_olist_com_dados}", file=sys.stderr)
        with pd.ExcelFile(caminho_modelo_saida_olist_com_dados) as xls_modelo_novo:
            if xls_modelo_novo.sheet_names:
                df_modelo_saida_temp = pd.read_excel(xls_modelo_novo, sheet_name=0)
                print(f"[CONVERSOR V6] Lida a primeira aba do NOVO modelo de saída: {xls_modelo_novo.sheet_names[0]}", file=sys.stderr)
            else:
                raise ValueError("O NOVO arquivo Excel modelo de saída não contém nenhuma aba.")
            
            colunas_modelo_olist = df_modelo_saida_temp.columns.tolist()
            print(f"[CONVERSOR V6] Colunas do NOVO modelo Olist: {colunas_modelo_olist}", file=sys.stderr)
        
        # Leitura do arquivo de orçamento
        print(f"[CONVERSOR V6] Lendo arquivo de orçamento", file=sys.stderr)
        if isinstance(arquivo_orcamento, str):
            with pd.ExcelFile(arquivo_orcamento) as xls_orc:
                df_orcamento_preview = pd.read_excel(xls_orc, sheet_name=0, nrows=20)
        else:  # BytesIO
            df_orcamento_preview = pd.read_excel(arquivo_orcamento, sheet_name=0, nrows=20)
            arquivo_orcamento.seek(0)  # Resetar posição para leitura posterior
        
        # Identificar linha de cabeçalho
        palavras_chave_cabecalho = ['produto', 'quantidade', 'valor']
        linha_cabecalho = encontrar_linha_cabecalho(df_orcamento_preview, palavras_chave_cabecalho)
        
        if linha_cabecalho is None:
            raise ValueError("Não foi possível identificar o cabeçalho do orçamento. Verifique se o arquivo contém as colunas necessárias.")
        
        # Ler o arquivo novamente, agora com o cabeçalho correto
        if isinstance(arquivo_orcamento, str):
            df_orcamento = pd.read_excel(arquivo_orcamento, sheet_name=0, header=linha_cabecalho)
        else:  # BytesIO
            df_orcamento = pd.read_excel(arquivo_orcamento, sheet_name=0, header=linha_cabecalho)
        
        # Normalizar nomes de colunas
        df_orcamento.columns = [col.lower().strip() for col in df_orcamento.columns]
        
        # Extrair informações do orçamento
        num_proposta_orc = None
        data_proposta_orc = None
        
        # Tentar extrair número da proposta e data
        for i in range(linha_cabecalho):
            row = df_orcamento_preview.iloc[i]
            for cell in row:
                if pd.notna(cell):
                    cell_str = str(cell).lower()
                    if 'proposta' in cell_str or 'orçamento' in cell_str or 'orcamento' in cell_str:
                        # Tentar extrair número da proposta
                        match = re.search(r'(?:proposta|orçamento|orcamento)[^\d]*(\d+)', cell_str)
                        if match:
                            num_proposta_orc = match.group(1)
                    
                    if 'data' in cell_str:
                        # Tentar extrair data
                        try:
                            # Verificar se há uma data na mesma linha
                            for other_cell in row:
                                if pd.notna(other_cell):
                                    if isinstance(other_cell, (pd.Timestamp, pd.DatetimeTZDtype)):
                                        data_proposta_orc = other_cell
                                        break
                                    elif isinstance(other_cell, str):
                                        # Tentar converter string para data com dayfirst=True para formato brasileiro (dia/mês/ano)
                                        try:
                                            data_proposta_orc = pd.to_datetime(other_cell, dayfirst=True, errors='coerce')
                                            if not pd.isna(data_proposta_orc):
                                                break
                                        except:
                                            continue
                        except Exception as e:
                            print(f"[CONVERSOR V6] Erro ao extrair data: {str(e)}", file=sys.stderr)
        
        # Filtrar apenas as linhas com produtos (remover linhas vazias ou de cabeçalho)
        df_orcamento_itens = df_orcamento.dropna(subset=['produto'], how='all')
        
        # Buscar informações do cliente
        info_cliente_df = pd.DataFrame()
        if not df_clientes.empty and 'ID' in df_clientes.columns:
            try:
                coluna_id_tipo = df_clientes['ID'].dtype
                id_cliente_selecionado_str = str(id_cliente_selecionado)
                
                if pd.api.types.is_numeric_dtype(coluna_id_tipo):
                    try:
                        id_cliente_convertido = int(float(id_cliente_selecionado_str))
                    except ValueError:
                        id_cliente_convertido = float(id_cliente_selecionado_str)
                else:
                    id_cliente_convertido = id_cliente_selecionado_str
                    
                info_cliente_df = df_clientes[df_clientes['ID'] == id_cliente_convertido]
            except Exception as e:
                print(f"[CONVERSOR V6] Erro ao buscar cliente: {str(e)}", file=sys.stderr)
        
        if info_cliente_df.empty:
            raise ValueError(f"Cliente com ID '{id_cliente_selecionado}' não encontrado")
        
        info_cliente = info_cliente_df.iloc[0]
        id_contato_cliente = info_cliente['ID']
        nome_contato_cliente = info_cliente['Nome']
        
        # Processamento dos itens
        linhas_saida = []
        for index, linha_item in df_orcamento_itens.iterrows():
            produto_orcamento_original = linha_item.get('produto')
            qtde = linha_item.get('quantidade')
            valor_unit = linha_item.get('valor unitário')
            
            if pd.isna(produto_orcamento_original) and pd.isna(qtde) and pd.isna(valor_unit):
                continue
            
            # FILTRAR LINHAS DE TOTAL/SUBTOTAL
            produto_str = str(produto_orcamento_original).lower() if pd.notna(produto_orcamento_original) else ""
            palavras_total = ['total', 'subtotal', 'valor total', 'total geral', 'soma', 'sum']
            if any(palavra in produto_str for palavra in palavras_total):
                print(f"[CONVERSOR V6] Pulando linha de total: {produto_orcamento_original}", file=sys.stderr)
                continue
                
            # Verificar se temos SKU no orçamento
            sku_orcamento_original = None
            # Verificar se a coluna 'sku' existe no DataFrame
            if 'sku' in linha_item and pd.notna(linha_item.get('sku')):
                sku_orcamento_original = linha_item.get('sku')
                sku_orcamento_busca_normalizado = normalizar_texto(sku_orcamento_original)
            
            produto_orcamento_busca_normalizado = normalizar_texto(produto_orcamento_original)
            
            id_produto_olist = pd.NA
            descricao_produto_olist = pd.NA
            
            # Priorizar busca pelo SKU se disponível
            if sku_orcamento_original and sku_orcamento_busca_normalizado:
                produto_mapeado_df = df_mapeamento[
                    df_mapeamento['SKU_NORMALIZADO_BUSCA'] == sku_orcamento_busca_normalizado
                ]
                
                # Se encontrou pelo SKU, preenche ID e descrição
                if not produto_mapeado_df.empty:
                    produto_mapeado = produto_mapeado_df.iloc[0]
                    id_produto_olist = produto_mapeado.get('ID', pd.NA)
                    descricao_produto_olist = produto_mapeado.get('MODELO OLIST', pd.NA)
                # Se não encontrar pelo SKU, tenta pelo modelo como fallback
                elif produto_orcamento_busca_normalizado:
                    produto_mapeado_df = df_mapeamento[
                        df_mapeamento['MODELO'].apply(normalizar_texto) == produto_orcamento_busca_normalizado
                    ]
                    
                    if not produto_mapeado_df.empty:
                        produto_mapeado = produto_mapeado_df.iloc[0]
                        id_produto_olist = produto_mapeado.get('ID', pd.NA)
                        descricao_produto_olist = produto_mapeado.get('MODELO OLIST', pd.NA)
                    else:
                        produtos_nao_mapeados_log.append(
                            f"'{sku_orcamento_busca_normalizado}' (SKU Original: '{sku_orcamento_original}')"
                        )
            # Se não tiver SKU, busca pelo modelo (compatibilidade com versões anteriores)
            elif produto_orcamento_busca_normalizado:
                produto_mapeado_df = df_mapeamento[
                    df_mapeamento['MODELO'].apply(normalizar_texto) == produto_orcamento_busca_normalizado
                ]
                
                if not produto_mapeado_df.empty:
                    produto_mapeado = produto_mapeado_df.iloc[0]
                    id_produto_olist = produto_mapeado.get('ID', pd.NA)
                    descricao_produto_olist = produto_mapeado.get('MODELO OLIST', pd.NA)
                else:
                    produtos_nao_mapeados_log.append(
                        f"'{produto_orcamento_busca_normalizado}' (Original: '{produto_orcamento_original}')"
                    )
            
            # Só incluir informações de cabeçalho se houver um produto válido
            if pd.notna(produto_orcamento_original) or pd.notna(sku_orcamento_original):
                linha_convertida = {
                    'Número da proposta': num_proposta_orc if num_proposta_orc is not None else pd.NA,
                    'Data': data_proposta_orc if data_proposta_orc is not None else pd.NA,
                    'ID contato': id_contato_cliente,
                    'Nome do contato': nome_contato_cliente,
                    'ID produto': id_produto_olist,
                    'Descrição': descricao_produto_olist,
                    'Quantidade': qtde if pd.notna(qtde) else pd.NA,
                    'Valor unitário': valor_unit if pd.notna(valor_unit) else pd.NA
                }
                
                linhas_saida.append({col: linha_convertida.get(col, pd.NA) for col in colunas_modelo_olist})
        
        if produtos_nao_mapeados_log:
            print("[CONVERSOR V6] Produtos não mapeados:", file=sys.stderr)
            for produto in produtos_nao_mapeados_log:
                print(f"  - {produto}", file=sys.stderr)
        
        # Criar DataFrame de saída
        df_saida = pd.DataFrame(linhas_saida)
        
        # Preencher 'Situação' apenas nas linhas onde 'produto' está preenchido
        if not df_saida.empty and 'produto' in df_saida.columns:
            linhas_com_produto = df_saida['produto'].notna() & (df_saida['produto'].astype(str).str.strip() != '')
            df_saida.loc[linhas_com_produto, 'Situação'] = 'Aguardando'

        return df_saida
        
    except Exception as e:
        print(f"[CONVERSOR V6] Erro: {str(e)}\n{traceback.format_exc()}", file=sys.stderr)
        return pd.DataFrame(columns=colunas_modelo_olist if colunas_modelo_olist else [])

if __name__ == '__main__': 
    pass
