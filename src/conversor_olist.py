import pandas as pd
import sys
import traceback
import re # Para normalização
import os
import io
from typing import Union, BinaryIO
import gspread
import requests

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

def mapear_colunas_orcamento(df):
    """
    Mapeia as colunas do orçamento para nomes padronizados, independente de variações.
    
    Args:
        df: DataFrame do orçamento
    
    Returns:
        DataFrame com colunas mapeadas para nomes padronizados
    """
    mapeamento_colunas = {}
    
    # Criar cópia do DataFrame para não modificar o original
    df_mapeado = df.copy()
    
    # Normalizar nomes de colunas
    colunas_normalizadas = {col: normalizar_texto(col) for col in df.columns}
    
    # Mapear colunas para nomes padronizados
    for col_original, col_normalizada in colunas_normalizadas.items():
        if 'produto' in col_normalizada:
            mapeamento_colunas[col_original] = 'produto'
        elif 'quantidade' in col_normalizada or 'qtd' in col_normalizada or 'qtde' in col_normalizada:
            mapeamento_colunas[col_original] = 'quantidade'
        elif 'valor' in col_normalizada and ('unit' in col_normalizada or 'unitario' in col_normalizada or 'unitário' in col_normalizada):
            mapeamento_colunas[col_original] = 'valor unitário'
        elif 'valor' in col_normalizada and 'unit' not in col_normalizada:
            mapeamento_colunas[col_original] = 'valor'
        elif 'sku' in col_normalizada or 'código' in col_normalizada or 'codigo' in col_normalizada or 'cod' in col_normalizada:
            mapeamento_colunas[col_original] = 'sku'
    
    # Renomear colunas
    df_mapeado = df_mapeado.rename(columns=mapeamento_colunas)
    
    # Garantir que temos pelo menos as colunas essenciais
    colunas_essenciais = ['produto', 'quantidade', 'valor']
    colunas_encontradas = [col for col in colunas_essenciais if col in df_mapeado.columns]
    
    if len(colunas_encontradas) < 2:  # Pelo menos produto e quantidade/valor são necessários
        print(f"[CONVERSOR V6] AVISO: Não foi possível identificar colunas essenciais. Encontradas: {colunas_encontradas}", file=sys.stderr)
    
    return df_mapeado

def get_dataframe_from_google_sheet(sheet_url, sheet_name=None, header_row=0):
    try:
        # Construir a URL de exportação CSV
        # A URL fornecida pelo usuário já contém o GID da aba, o que é útil.
        # Exemplo: https://docs.google.com/spreadsheets/d/1qAuw2ebWPJmcy_gl4Qf48GfmnSGLZumDfs62fpG2BGA/edit?pli=1&gid=1582301730#gid=1582301730
        # Precisamos extrair o spreadsheet ID e o GID.
        
        # Extrair spreadsheet ID
        match_id = re.search(r'/spreadsheets/d/([a-zA-Z0-9-_]+)', sheet_url)
        if not match_id:
            raise ValueError(f"Não foi possível extrair o ID da planilha da URL: {sheet_url}")
        spreadsheet_id = match_id.group(1)

        # Extrair GID
        match_gid = re.search(r'gid=(\d+)', sheet_url)
        if not match_gid:
            raise ValueError(f"Não foi possível extrair o GID da planilha da URL: {sheet_url}")
        gid = match_gid.group(1)

        export_url = f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}/export?format=csv&gid={gid}"
        
        print(f"[CONVERSOR V6] Tentando baixar CSV de: {export_url}", file=sys.stderr)
        response = requests.get(export_url)
        response.raise_for_status() # Levanta um erro para códigos de status HTTP ruins
        
        df = pd.read_csv(io.StringIO(response.text))
        
        # Se o cabeçalho não for a primeira linha, precisamos ajustar
        if header_row > 0:
            # Ler novamente, mas pulando as linhas até o cabeçalho
            df = pd.read_csv(io.StringIO(response.text), skiprows=header_row)

        # Tenta converter colunas numéricas
        for col in df.columns:
            try:
                df[col] = pd.to_numeric(df[col], errors='ignore')
            except:
                pass
        
        return df
    except Exception as e:
        print(f"[CONVERSOR V6] Erro ao ler Google Sheet {sheet_url} (aba: {sheet_name}): {str(e)}", file=sys.stderr)
        raise

def converter_orcamento_para_olist(
    arquivo_orcamento: Union[str, BinaryIO],
    url_mapeamento_produtos: str,
    url_clientes: str,
    id_cliente_selecionado: Union[str, int],
    caminho_modelo_saida_olist_com_dados: str
) -> pd.DataFrame:
    """
    Converte um arquivo de orçamento para o formato Olist.
    
    Args:
        arquivo_orcamento: Caminho do arquivo ou objeto BytesIO contendo o orçamento
        url_mapeamento_produtos: URL da planilha de mapeamento de produtos no Google Sheets
        url_clientes: URL da planilha de clientes no Google Sheets
        id_cliente_selecionado: ID do cliente selecionado
        caminho_modelo_saida_olist_com_dados: Caminho do arquivo modelo de saída (ainda local)
        
    Returns:
        DataFrame com o orçamento convertido no formato Olist
    """
    df_modelo_saida_temp = None
    colunas_modelo_olist = []
    produtos_nao_mapeados_log = [] # Lista para logar produtos não mapeados
    
    # Adicionar diagnóstico para verificar os arquivos
    print(f"[DIAGNÓSTICO] Verificando existência dos arquivos:")
    print(f"[DIAGNÓSTICO] Tipo arquivo_orcamento: {type(arquivo_orcamento)}")
    print(f"[DIAGNÓSTICO] url_mapeamento_produtos: {url_mapeamento_produtos}")
    print(f"[DIAGNÓSTICO] url_clientes: {url_clientes}")
    print(f"[DIAGNÓSTICO] caminho_modelo_saida_olist_com_dados: {caminho_modelo_saida_olist_com_dados} (Existe: {os.path.exists(caminho_modelo_saida_olist_com_dados)})")
    
    # Verificar se o arquivo modelo de saída local existe
    if not os.path.exists(caminho_modelo_saida_olist_com_dados):
        erro_msg = f"Arquivo de modelo de saída não encontrado: {caminho_modelo_saida_olist_com_dados}"
        print(f"[CONVERSOR V6] ERRO: {erro_msg}", file=sys.stderr)
        raise FileNotFoundError(erro_msg)
    
    print(f"[CONVERSOR V6] Iniciando conversão. Cliente ID: {id_cliente_selecionado}", file=sys.stderr)
    
    try:
        print(f"[CONVERSOR V6] Lendo planilha de mapeamento: {url_mapeamento_produtos}", file=sys.stderr)
        df_mapeamento = get_dataframe_from_google_sheet(url_mapeamento_produtos, sheet_name='CATÁLOGO')
        
        # Normalizar a coluna de busca no mapeamento
        if 'SKU' in df_mapeamento.columns:
            df_mapeamento['SKU_NORMALIZADO_BUSCA'] = df_mapeamento['SKU'].apply(normalizar_texto)
            print(f"[CONVERSOR V6] Coluna 'SKU' normalizada para busca em df_mapeamento.", file=sys.stderr)
        else:
            print(f"[CONVERSOR V6] ERRO: Coluna 'SKU' não encontrada em {url_mapeamento_produtos}", file=sys.stderr)
            return pd.DataFrame(columns=colunas_modelo_olist if colunas_modelo_olist else [])
        
        print(f"[CONVERSOR V6] Lendo planilha de clientes: {url_clientes}", file=sys.stderr)
        df_clientes = get_dataframe_from_google_sheet(url_clientes, sheet_name='clientes')
        
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
                df_orcamento_preview = pd.read_excel(xls_orc, sheet_name=0, nrows=20, header=None)
        else:  # BytesIO
            df_orcamento_preview = pd.read_excel(arquivo_orcamento, sheet_name=0, nrows=20, header=None)
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
        
        # Mapear colunas para nomes padronizados
        df_orcamento = mapear_colunas_orcamento(df_orcamento)
        
        # Extrair informações do orçamento
        num_proposta_orc = None
        data_proposta_orc = None
        
        # Melhorar a extração de número da proposta e data
        for i in range(linha_cabecalho):
            row = df_orcamento_preview.iloc[i]
            for j, cell in enumerate(row):
                if pd.notna(cell):
                    cell_str = str(cell).lower()
                    
                    # Extração de número da proposta
                    if 'proposta' in cell_str or 'orçamento' in cell_str or 'orcamento' in cell_str:
                        # Tentar extrair número da proposta da mesma célula
                        match = re.search(r'(?:proposta|orçamento|orcamento)[^\d]*(\d+)', cell_str)
                        if match:
                            num_proposta_orc = match.group(1)
                        # Se não encontrar na mesma célula, verificar a célula à direita
                        elif j+1 < len(row) and pd.notna(row[j+1]):
                            next_cell = str(row[j+1])
                            if re.match(r'^\d+$', next_cell.strip()):
                                num_proposta_orc = next_cell.strip()
                    
                    # Extração de data
                    if 'data' in cell_str:
                        # Verificar a célula à direita para data
                        if j+1 < len(row) and pd.notna(row[j+1]):
                            try:
                                # Tentar converter para data
                                data_cell = row[j+1]
                                if isinstance(data_cell, (pd.Timestamp, pd.DatetimeTZDtype)):
                                    data_proposta_orc = data_cell
                                else:
                                    # Tentar converter string para data
                                    data_proposta_orc = pd.to_datetime(data_cell, errors='coerce')
                                    if pd.isna(data_proposta_orc):
                                        # Tentar formatos comuns de data
                                        for fmt in ['%d/%m/%Y', '%d-%m-%Y', '%Y-%m-%d', '%d.%m.%Y']:
                                            try:
                                                data_proposta_orc = pd.to_datetime(data_cell, format=fmt)
                                                break
                                            except:
                                                continue
                            except Exception as e:
                                print(f"[CONVERSOR V6] Erro ao extrair data: {str(e)}", file=sys.stderr)
        
        # Filtrar apenas as linhas com produtos (remover linhas vazias ou de cabeçalho)
        # MODIFICAÇÃO: Considerar tanto produto quanto SKU para manter linhas
        if 'produto' in df_orcamento.columns and 'sku' in df_orcamento.columns:
            # Manter linhas que tenham produto OU sku preenchidos
            df_orcamento_itens = df_orcamento.dropna(subset=['produto', 'sku'], how='all')
            print(f"[CONVERSOR V6] Filtrando linhas com produto OU sku preenchidos. Linhas restantes: {len(df_orcamento_itens)}", file=sys.stderr)
        elif 'produto' in df_orcamento.columns:
            df_orcamento_itens = df_orcamento.dropna(subset=['produto'], how='all')
            print(f"[CONVERSOR V6] Filtrando linhas com produto preenchido. Linhas restantes: {len(df_orcamento_itens)}", file=sys.stderr)
        elif 'sku' in df_orcamento.columns:
            df_orcamento_itens = df_orcamento.dropna(subset=['sku'], how='all')
            print(f"[CONVERSOR V6] Filtrando linhas com sku preenchido. Linhas restantes: {len(df_orcamento_itens)}", file=sys.stderr)
        else:
            # Tentar encontrar uma coluna que possa conter produtos
            colunas_possiveis = [col for col in df_orcamento.columns if any(
                termo in normalizar_texto(col) for termo in ['produto', 'item', 'descricao', 'descrição']
            )]
            
            if colunas_possiveis:
                df_orcamento_itens = df_orcamento.dropna(subset=[colunas_possiveis[0]], how='all')
                # Renomear para 'produto' para compatibilidade
                df_orcamento_itens = df_orcamento_itens.rename(columns={colunas_possiveis[0]: 'produto'})
            else:
                # Se não encontrar nenhuma coluna adequada, usar a primeira coluna não numérica
                colunas_nao_numericas = [col for col in df_orcamento.columns 
                                        if not pd.api.types.is_numeric_dtype(df_orcamento[col])]
                
                if colunas_nao_numericas:
                    df_orcamento_itens = df_orcamento.dropna(subset=[colunas_nao_numericas[0]], how='all')
                    # Renomear para 'produto' para compatibilidade
                    df_orcamento_itens = df_orcamento_itens.rename(columns={colunas_nao_numericas[0]: 'produto'})
                else:
                    # Último recurso: usar a primeira coluna
                    primeira_coluna = df_orcamento.columns[0]
                    df_orcamento_itens = df_orcamento.dropna(subset=[primeira_coluna], how='all')
                    # Renomear para 'produto' para compatibilidade
                    df_orcamento_itens = df_orcamento_itens.rename(columns={primeira_coluna: 'produto'})
        
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
            produto_orcamento_original = linha_item.get('produto', pd.NA)
            qtde = linha_item.get('quantidade', pd.NA)
            if 'valor unitário' in linha_item:
                valor_unit = linha_item.get('valor unitário')
            elif 'valor' in linha_item:
                valor_unit = linha_item.get('valor')
            else:
                valor_unit = pd.NA

            # FILTRAR LINHAS DE TOTAL/SUBTOTAL
            produto_str = str(produto_orcamento_original).lower() if pd.notna(produto_orcamento_original) else ""
            palavras_total = ['total', 'subtotal', 'valor total', 'total geral', 'soma', 'sum']
            if any(palavra in produto_str for palavra in palavras_total):
                print(f"[CONVERSOR V6] Pulando linha de total: {produto_orcamento_original}", file=sys.stderr)
                continue

            # FILTRAR LINHAS SEM PRODUTO REAL
            if pd.isna(produto_orcamento_original) or str(produto_orcamento_original).strip() == '':
                print(f"[CONVERSOR V6] Pulando linha sem produto: {linha_item}", file=sys.stderr)
                continue

            # Verificar se temos SKU no orçamento
            sku_orcamento_original = None
            if 'sku' in linha_item and pd.notna(linha_item.get('sku')):
                sku_orcamento_original = linha_item.get('sku')
                sku_orcamento_busca_normalizado = normalizar_texto(sku_orcamento_original)
            else:
                sku_orcamento_busca_normalizado = None

            produto_orcamento_busca_normalizado = normalizar_texto(produto_orcamento_original) if pd.notna(produto_orcamento_original) else ""

            id_produto_olist = pd.NA
            descricao_produto_olist = pd.NA

            # Priorizar busca pelo SKU se disponível
            if sku_orcamento_original and sku_orcamento_busca_normalizado:
                produto_mapeado_df = df_mapeamento[
                    df_mapeamento['SKU_NORMALIZADO_BUSCA'] == sku_orcamento_busca_normalizado
                ]
                if not produto_mapeado_df.empty:
                    produto_mapeado = produto_mapeado_df.iloc[0]
                    id_produto_olist = produto_mapeado.get('ID', pd.NA)
                    descricao_produto_olist = produto_mapeado.get('MODELO OLIST', pd.NA)
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
            print(f"[CONVERSOR V6] Adicionando linha convertida: {linha_convertida}", file=sys.stderr)
            linhas_saida.append({col: linha_convertida.get(col, pd.NA) for col in colunas_modelo_olist})
        
        if produtos_nao_mapeados_log:
            print("[CONVERSOR V6] Produtos não mapeados:", file=sys.stderr)
            for produto in produtos_nao_mapeados_log:
                print(f"  - {produto}", file=sys.stderr)
        
        # Criar DataFrame de saída
        df_saida = pd.DataFrame(linhas_saida)
        
        # Preencher a coluna 'Situação' com 'Aguardando' para todas as linhas válidas
        if not df_saida.empty:
            df_saida['Situação'] = 'Aguardando'

        return df_saida
        
    except Exception as e:
        print(f"[CONVERSOR V6] Erro: {str(e)}\n{traceback.format_exc()}", file=sys.stderr)
        return pd.DataFrame(columns=colunas_modelo_olist if colunas_modelo_olist else [])

if __name__ == '__main__': 
    pass


