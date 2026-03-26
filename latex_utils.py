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

import re

def escapar_latex(texto):
    if not texto: 
        return ""
    texto = str(texto)
    
    # O escudo inteligente: protege apenas o "%" e deixa os seus comandos de lista funcionarem!
    texto = re.sub(r'(?<!\\)%', r'\%', texto)
    
    return texto


def gerar_preview_web(texto):
    if not texto: 
        return ""
    
    t = str(texto)
    
    # 🧹 Faxina: Some com qualquer '£' antigo
    t = t.replace('£', '')
    
    # 1. Traduz formatações básicas
    t = re.sub(r'\\textbf\{(.*?)\}', r'**\1**', t, flags=re.DOTALL)
    t = re.sub(r'\\textit\{(.*?)\}', r'*\1*', t, flags=re.DOTALL)
    t = re.sub(r'\\underline\{(.*?)\}', r'<ins>\1</ins>', t, flags=re.DOTALL)
    t = re.sub(r'\\textcolor\{(.*?)\}\{(.*?)\}', r'<span style="color:\1;">\2</span>', t, flags=re.DOTALL)
    t = re.sub(r'\\section\*?\{(.*?)\}', r'### \1', t, flags=re.DOTALL)
    t = re.sub(r'\\subsection\*?\{(.*?)\}', r'#### \1', t, flags=re.DOTALL)
    
    # =========================================================
    # 2. O SEGREDO AQUI: Tratando Listas e Enumerações com HTML
    # =========================================================
    # A. Enumerate (Dinâmico: Números ou Letras)
    def replace_enum(m):
        formato = m.group(1) or ""  
        conteudo = m.group(2)       
        
        usar_letras = False
        if "a" in formato.lower() or "\\alph" in formato.lower():
            usar_letras = True
            
        partes = re.split(r'\s*\\item\s*', conteudo)
        texto_final = partes[0]
        letras = "abcdefghijklmnopqrstuvwxyz"
        
        for i, parte in enumerate(partes[1:]):
            # O re.sub "esmaga" qualquer Enter acidental, garantindo uma linha contínua
            parte_limpa = re.sub(r'\s+', ' ', parte).strip() 
            
            if usar_letras:
                marcador = f"**{letras[i % 26]})**"
            else:
                marcador = f"**{i + 1}.**"
                
            texto_final += f"\n\n{marcador} {parte_limpa}"
            
        return texto_final
    
    t = re.sub(r'\\begin\{enumerate\}(?:\[(.*?)\])?(.*?)\\end\{enumerate\}', replace_enum, t, flags=re.DOTALL)
    
    # B. Itemize (Bolinhas) em Markdown limpo
    def replace_item(m):
        conteudo = m.group(1)
        partes = re.split(r'\s*\\item\s*', conteudo)
        texto_final = partes[0]
        
        for parte in partes[1:]:
            parte_limpa = parte.lstrip()
            texto_final += f"\n\n* {parte_limpa}"
            
        return texto_final
    
    t = re.sub(r'\\begin\{itemize\}(?:\[.*?\])?(.*?)\\end\{itemize\}', replace_item, t, flags=re.DOTALL)
    
    # Fallback de segurança
    t = re.sub(r'\s*\\item\s+', r'\n\n* ', t)
    # =========================================================
    
    # 3. Mantém o aviso visual da Tabela
    t = re.sub(r'\\begin\{tabular\}.*?\\end\{tabular\}', 
                  r'<div style="padding:15px; background:#e3f2fd; border-left: 5px solid #2196f3; border-radius:5px; color:#0d47a1; margin:10px 0;">'
                  r'<b>📊 Tabela LaTeX Detectada</b><br>'
                  r'<small>O código está salvo! No PDF final ela sairá com todas as grades e colunas.</small></div>', 
                  t, flags=re.DOTALL)
    
    # 4. Garante as quebras de linha corretas para o Markdown
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