import os
import requests
from supabase import create_client, Client
import streamlit as st


# 1. Coloque suas credenciais do Supabase aqui!
URL_SUPABASE = st.secrets.get("SUPABASE_URL")
CHAVE_SUPABASE = st.secrets.get("SUPABASE_KEY")
NOME_BUCKET = "imagens_provas"

try:
    # O str() garante que o Python entenda os segredos como texto puro
    supabase: Client = create_client(str(URL_SUPABASE), str(CHAVE_SUPABASE))
except Exception as e:
    print(f"Erro ao conectar no Supabase: {e}")
    supabase = None

def subir_imagem_nuvem(arquivo_upload, nome_arquivo):
    """Sobe a foto para o Bucket e devolve a URL pública para salvar no banco"""
    if not supabase or not arquivo_upload: return None
    
    try:
        bytes_img = arquivo_upload.getvalue()
        # Envia para a nuvem (upsert=true substitui se já existir uma com o mesmo nome)
        supabase.storage.from_(NOME_BUCKET).upload(
            path=nome_arquivo, 
            file=bytes_img, 
            file_options={"content-type": arquivo_upload.type, "upsert": "true"}
        )
        # Pega o link público da imagem gerada
        url_publica = supabase.storage.from_(NOME_BUCKET).get_public_url(nome_arquivo)
        return url_publica
    except Exception as e:
        st.error(f"Erro ao subir imagem para a nuvem: {e}")
        return None

def baixar_imagem_para_latex(url_ou_caminho, nome_temporario):
    """O LaTeX precisa do arquivo físico. Esta função baixa a URL rapidinho só para gerar o PDF"""
    if not url_ou_caminho: return None
    
    # Se for uma URL (imagem nova do Supabase), ele baixa.
    if str(url_ou_caminho).startswith("http"):
        try:
            resposta = requests.get(url_ou_caminho)
            if resposta.status_code == 200:
                with open(nome_temporario, 'wb') as f:
                    f.write(resposta.content)
                return nome_temporario
        except:
            return None
    # Se for uma imagem antiga que ainda está salva no seu Mac
    elif os.path.exists(str(url_ou_caminho)):
        return url_ou_caminho
        
    return None