# latex_utils.py
import re
import unicodedata
import os
import subprocess
import jinja2
import streamlit as st

def sanitizar_nome(texto):
    nfkd = unicodedata.normalize('NFKD', texto)
    return "".join([c for c in nfkd if not unicodedata.category(c).startswith('M')]).replace(" ", "_")

def escapar_latex(texto):
    if not texto: return ""
    texto = texto.replace('\u200b', '') # Remove caracteres fantasmas
    
    partes = re.split(r'(\$.*?\$|£.*?£)', texto, flags=re.DOTALL)
    
    resultado = []
    for parte in partes:
        if parte.startswith('$') and parte.endswith('$'):
            resultado.append(parte) # É matemática
        elif parte.startswith('£') and parte.endswith('£'):
            resultado.append(parte[1:-1]) # É formatação de texto
        else:
            # Texto normal
            mapa = {'&': r'\&', '%': r'\%', '#': r'\#', '_': r'\_', '{': r'\{', '}': r'\}', '\\': r'\textbackslash{}'}
            for char, sub in mapa.items():
                parte = parte.replace(char, sub)
            resultado.append(parte)
            
    return "".join(resultado)

import re

def gerar_preview_web(texto):
    if not texto: 
        return ""
    
    t = str(texto)
    
    # 🧹 Faxina: Some com qualquer '£' antigo que tenha ficado no banco
    t = t.replace('£', '')
    
    # 1. Traduz negrito, itálico e sublinhado
    t = re.sub(r'\\textbf\{(.*?)\}', r'**\1**', t, flags=re.DOTALL)
    t = re.sub(r'\\textit\{(.*?)\}', r'*\1*', t, flags=re.DOTALL)
    t = re.sub(r'\\underline\{(.*?)\}', r'<ins>\1</ins>', t, flags=re.DOTALL)
    
    # Mantém as cores
    t = re.sub(r'\\textcolor\{(.*?)\}\{(.*?)\}', r'<span style="color:\1;">\2</span>', t, flags=re.DOTALL)
    
    # 2. Traduz Títulos
    t = re.sub(r'\\section\*?\{(.*?)\}', r'### \1', t, flags=re.DOTALL)
    t = re.sub(r'\\subsection\*?\{(.*?)\}', r'#### \1', t, flags=re.DOTALL)
    
    # 3. Traduz Listas
    t = t.replace(r'\begin{itemize}', '')
    t = t.replace(r'\end{itemize}', '')
    t = t.replace(r'\begin{enumerate}', '')
    t = t.replace(r'\end{enumerate}', '')
    t = re.sub(r'\\item\s+', r'* ', t)
    
    # 4. Mantém o aviso visual da Tabela
    t = re.sub(r'\\begin\{tabular\}.*?\\end\{tabular\}', 
                  r'<div style="padding:15px; background:#e3f2fd; border-left: 5px solid #2196f3; border-radius:5px; color:#0d47a1; margin:10px 0;">'
                  r'<b>📊 Tabela LaTeX Detectada</b><br>'
                  r'<small>O código está salvo! No PDF final ela sairá com todas as grades e colunas.</small></div>', 
                  t, flags=re.DOTALL)
    
    # 5. Garante as quebras de linha
    t = t.replace('\n', '  \n')
    
    return t

def configurar_jinja():
    return jinja2.Environment(block_start_string='<%', block_end_string='%>', variable_start_string='<<', variable_end_string='>>', trim_blocks=True, autoescape=False, loader=jinja2.FileSystemLoader(os.path.abspath('.')))

def compilar_latex_mac(caminho_tex):
    caminho_pdf = caminho_tex.replace('.tex', '.pdf')
    try:
        import subprocess
        # Tiramos o text=True. Vamos pegar os dados brutos (bytes)
        resultado = subprocess.run(['pdflatex', '-interaction=nonstopmode', caminho_tex], 
                                   capture_output=True)
        
        # Decodificamos 'na marra', ignorando qualquer caractere problemático
        log_stdout = resultado.stdout.decode('utf-8', errors='ignore') if resultado.stdout else ""
        log_stderr = resultado.stderr.decode('utf-8', errors='ignore') if resultado.stderr else ""
        
        import streamlit as st
        st.session_state.latex_log = f"--- LOG DE {caminho_tex} ---\n" + log_stdout + "\n" + log_stderr
        
        if os.path.exists(caminho_pdf): 
            return True
        else:
            st.error(f"⚠️ O PDF não foi gerado. Olhe o Log na barra lateral para ver o motivo!")
            return False
            
    except Exception as e:
        import streamlit as st
        st.session_state.latex_log = f"ERRO CRÍTICO DO SISTEMA:\n{str(e)}"
        st.error(f"🚫 Falha ao tentar chamar o LaTeX: {e}")
        return False