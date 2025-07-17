import sys
import os
import traceback # Para log detalhado de exceções
import time
import contextlib
from pathlib import Path
import tempfile
# Adiciona o diretório pai de 'src' ao sys.path para permitir importações como 'from src.conversor_olist import ...'
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

# ===== INÍCIO DIAGNÓSTICO =====
print("Diretório atual:", os.getcwd())
# ===== FIM DIAGNÓSTICO =====

from flask import Flask, request, jsonify, send_file, render_template
import pandas as pd
import io # Para enviar o arquivo em memória
from werkzeug.utils import secure_filename # Para nomes de arquivo seguros

# Importa a função de conversão do outro arquivo .py
from conversor_olist import converter_orcamento_para_olist

app = Flask(__name__, static_folder='static', template_folder='static')

# Define o caminho base para os arquivos de dados que estão dentro de 'src'
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, 'data')
UPLOAD_FOLDER = os.path.join(BASE_DIR, 'uploads') # Para uploads temporários de orçamentos

# URLs das planilhas do Google Sheets
CLIENTES_SHEET_URL = "https://docs.google.com/spreadsheets/d/1qAuw2ebWPJmcy_gl4Qf48GfmnSGLZumDfs62fpG2BGA/edit?pli=1&gid=1582301730#gid=1582301730"
MAPEAMENTO_PRODUTOS_SHEET_URL = "https://docs.google.com/spreadsheets/d/1qAuw2ebWPJmcy_gl4Qf48GfmnSGLZumDfs62fpG2BGA/edit?pli=1&gid=1351609730#gid=1351609730"
MODELO_SAIDA_OLIST_FILENAME = "formato Olist(SAIDA).xlsx"
MODELO_SAIDA_OLIST_PATH = os.path.join(DATA_DIR, MODELO_SAIDA_OLIST_FILENAME)

# ===== INÍCIO DIAGNÓSTICO =====
print("Caminhos dos arquivos:")
print(f"MODELO_SAIDA_OLIST_PATH: {MODELO_SAIDA_OLIST_PATH} (Existe: {os.path.exists(MODELO_SAIDA_OLIST_PATH)})")
print(f"Arquivos em {DATA_DIR} (Existe: {os.path.exists(DATA_DIR)}):", os.listdir(DATA_DIR) if os.path.exists(DATA_DIR) else "Pasta não existe")
# ===== FIM DIAGNÓSTICO =====

# Criar diretório de uploads se não existir
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
ALLOWED_EXTENSIONS = {'xlsx'}

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def check_required_files():
    """Check if all required files exist and are readable."""
    # Certifique-se de que o diretório DATA_DIR existe
    os.makedirs(DATA_DIR, exist_ok=True)
    print(f"[CHECK] Verificando diretório de dados: {DATA_DIR} (Existe: {os.path.exists(DATA_DIR)})")
    
    required_files = {
        'modelo': MODELO_SAIDA_OLIST_PATH
    }
    
    missing_files = []
    for file_type, path in required_files.items():
        if not os.path.exists(path):
            missing_files.append(file_type)
            app.logger.error(f"Required file missing: {path}")
            print(f"[CHECK] Arquivo ausente: {path}")
        else:
            print(f"[CHECK] Arquivo encontrado: {path}")
    
    # Adicionar verificação de acessibilidade das URLs do Google Sheets aqui, se necessário
    # Por enquanto, assumimos que as URLs são acessíveis publicamente.

    return missing_files

@app.route('/')
def index():
    try:
        # Check for required files on startup
        missing_files = check_required_files()
        if missing_files:
            return render_template('error.html', 
                                error=f"Missing required files: {', '.join(missing_files)}. Please upload them first.")
        return render_template('index.html')
    except Exception as e:
        app.logger.error(f"Error rendering index: {str(e)}\n{traceback.format_exc()}")
        return jsonify({'error': 'Error loading application'}), 500

@app.route('/clientes', methods=['GET'])
def get_clientes():
    try:
        # Agora lê do Google Sheets
        from conversor_olist import get_dataframe_from_google_sheet
        df_clientes = get_dataframe_from_google_sheet(CLIENTES_SHEET_URL, sheet_name='clientes')
        
        if 'ID' in df_clientes.columns and 'Nome' in df_clientes.columns:
            df_clientes = df_clientes.dropna(subset=['Nome'])
            df_clientes['ID'] = df_clientes['ID'].astype(str)
            clientes_list = df_clientes[['ID', 'Nome']].to_dict(orient='records')
            return jsonify({'clientes': clientes_list})
        else:
            return jsonify({'error': 'Invalid client file structure in Google Sheet'}), 500
    except Exception as e:
        app.logger.error(f"Error loading clients from Google Sheet: {str(e)}\n{traceback.format_exc()}")
        return jsonify({'error': str(e), 'details': traceback.format_exc()}), 500

def remove_file_with_retry(file_path, max_retries=3, delay=1):
    """Remove um arquivo com tentativas múltiplas caso esteja em uso."""
    for attempt in range(max_retries):
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
            return True
        except PermissionError:
            if attempt < max_retries - 1:
                time.sleep(delay)
                continue
            raise
        except Exception:
            raise
    return False

@app.route('/processar', methods=['POST'])
def processar_arquivo():
    try:
        # Check required files first
        missing_files = check_required_files()
        if missing_files:
            return jsonify({
                'error': 'Missing required files',
                'details': {'missing': missing_files}
            }), 500

        if 'arquivo_excel' not in request.files:
            return jsonify({'error': 'No Excel file uploaded'}), 400
        
        file = request.files['arquivo_excel']
        cliente_id_str = request.form.get('cliente_id')

        if not cliente_id_str:
            return jsonify({'error': 'No client ID provided'}), 400

        if file.filename == '':
            return jsonify({'error': 'Empty filename'}), 400

        if not file or not allowed_file(file.filename):
            return jsonify({'error': 'Invalid file type. Use .xlsx'}), 400

        # Create in-memory file
        input_excel = io.BytesIO(file.read())
        
        try:
            df_convertido = converter_orcamento_para_olist(
                input_excel,
                MAPEAMENTO_PRODUTOS_SHEET_URL, # Passa a URL do Google Sheet
                CLIENTES_SHEET_URL, # Passa a URL do Google Sheet
                cliente_id_str,
                MODELO_SAIDA_OLIST_PATH
            )

            if df_convertido.empty:
                return jsonify({'error': 'No data processed'}), 500

            # Buscar nome do cliente para o nome do arquivo
            from conversor_olist import get_dataframe_from_google_sheet
            df_clientes = get_dataframe_from_google_sheet(CLIENTES_SHEET_URL, sheet_name='clientes')
            nome_cliente = None
            if 'ID' in df_clientes.columns and 'Nome' in df_clientes.columns:
                info_cliente_df = df_clientes[df_clientes['ID'].astype(str) == str(cliente_id_str)]
                if not info_cliente_df.empty:
                    nome_cliente = info_cliente_df.iloc[0]['Nome']
            if not nome_cliente:
                nome_cliente = f"cliente_{cliente_id_str}"
            # Sanitizar nome para arquivo
            nome_cliente_sanit = ''.join(c for c in str(nome_cliente) if c.isalnum() or c in ('-_')).replace(' ', '_')
            nome_arquivo = f"orcamento_convertido_olist_{nome_cliente_sanit}.xlsx"

            # Create output file in memory
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                df_convertido.to_excel(writer, index=False, sheet_name='Sheet1')
            output.seek(0)
            
            return send_file(
                output,
                mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                as_attachment=True,
                download_name=nome_arquivo
            )

        except Exception as e:
            app.logger.error(f"Error processing file: {str(e)}\n{traceback.format_exc()}")
            return jsonify({
                'error': 'Error processing file',
                'details': {
                    'message': str(e),
                    'traceback': traceback.format_exc()
                }
            }), 500

    except Exception as e:
        app.logger.error(f"Unexpected error: {str(e)}\n{traceback.format_exc()}")
        return jsonify({
            'error': 'Unexpected error',
            'details': {
                'message': str(e),
                'traceback': traceback.format_exc()
            }
        }), 500

# @app.route('/upload_mapeamento', methods=['POST'])
# def upload_mapeamento():
#     # Esta rota pode ser removida ou adaptada se o upload de arquivos locais não for mais necessário.
#     # Por enquanto, vamos mantê-la, mas ela não será usada para as planilhas do Google Sheets.
#     return jsonify({'message': 'Upload de arquivos locais desativado. Use as planilhas do Google Sheets.'}), 400

@app.errorhandler(500)
def internal_error(error):
    app.logger.error(f"Internal server error: {str(error)}\n{traceback.format_exc()}")
    return jsonify({
        'error': 'Internal server error',
        'details': {
            'message': str(error),
            'traceback': traceback.format_exc()
        }
    }), 500

@app.errorhandler(404)
def not_found_error(error):
    return jsonify({
        'error': 'Resource not found',
        'details': {'message': str(error)}
    }), 404

# Para desenvolvimento local
if __name__ == '__main__':
    import logging
    import tempfile
    log_file = os.path.join(tempfile.gettempdir(), 'flask_app.log')
    logging.basicConfig(
        filename=log_file,
        level=logging.DEBUG,
        format='%(asctime)s %(levelname)s: %(message)s'
    )
    app.logger.info('Iniciando aplicação...')
    app.run(host='0.0.0.0', port=5000, debug=True)

# Para Vercel - necessário para serverless
app = app


