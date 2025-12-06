import os
import sys

# Carrega variáveis de ambiente do arquivo .env (se existir)
try:
    from dotenv import load_dotenv
    env_path = os.path.join(os.path.dirname(__file__), '.env')
    if os.path.exists(env_path):
        load_dotenv(env_path)
        print(f"✅ Variáveis de ambiente carregadas de {env_path}")
    else:
        print("⚠️ Arquivo .env não encontrado. Crie um arquivo .env com OLIST_API_TOKEN=seu_token")
except ImportError:
    print("⚠️ python-dotenv não instalado. Execute: pip install python-dotenv")

# Adiciona o diretório src ao path
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

# Imprime informações de diagnóstico
print("Diretório de execução:", os.getcwd())
print("Diretório src:", os.path.join(os.path.dirname(__file__), 'src'))
print("Arquivos na pasta src:", os.listdir(os.path.join(os.path.dirname(__file__), 'src')))

# Verifica e cria diretório de dados
data_dir = os.path.join(os.path.dirname(__file__), 'src', 'data')
os.makedirs(data_dir, exist_ok=True)

# Copia os arquivos necessários para data se não estiverem lá
src_dir = os.path.join(os.path.dirname(__file__), 'src')
arquivos_necessarios = [
    "clientes.xlsx",
    "PLanilha mapeamento Orçamento Olist.xlsx",
    "formato Olist(SAIDA).xlsx"
]

for arquivo in arquivos_necessarios:
    src_path = os.path.join(src_dir, arquivo)
    dst_path = os.path.join(data_dir, arquivo)
    
    if os.path.exists(src_path) and not os.path.exists(dst_path):
        print(f"Copiando {arquivo} para a pasta data...")
        import shutil
        shutil.copy2(src_path, dst_path)

# Importa a aplicação Flask
from src.main import app

if __name__ == '__main__':
    # Executa a aplicação em modo debug
    app.run(debug=True, host='0.0.0.0', port=5000)