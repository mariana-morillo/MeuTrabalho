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

import re

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
    # 2. O SEGREDO AQUI: Tratando Listas e Enumerações
    # =========================================================
    
    # A. Enumerate (Dinâmico: Números ou Letras)
    def replace_enum(m):
        formato = m.group(1) or ""  # Captura o que está dentro de [] (ex: [a)])
        conteudo = m.group(2)       # Captura o texto com os \item
        
        # Verifica se o utilizador pediu letras no formato
        usar_letras = False
        if "a" in formato.lower() or "\\alph" in formato.lower():
            usar_letras = True
            
        # Quebra o texto a cada \item encontrado
        partes = re.split(r'\s*\\item\s*', conteudo)
        texto_final = partes[0] # Mantém o que vier antes do primeiro \item
        letras = "abcdefghijklmnopqrstuvwxyz"
        
        # Aplica o marcador correto (letra ou número)
        for i, parte in enumerate(partes[1:]):
            if usar_letras:
                marcador = f"**{letras[i % 26]})**"
            else:
                marcador = f"**{i + 1}.**"
            texto_final += f"\n{marcador} {parte}"
            
        return texto_final
    
    # A regex agora captura o que estiver dentro do [...] no grupo 1, e o texto no grupo 2
    t = re.sub(r'\\begin\{enumerate\}(?:\[(.*?)\])?(.*?)\\end\{enumerate\}', replace_enum, t, flags=re.DOTALL)
    
    # B. Itemize (Bolinhas) - Troca o \item por "* "
    def replace_item(m):
        return re.sub(r'\s*\\item\s*', r'\n* ', m.group(1))
    
    t = re.sub(r'\\begin\{itemize\}(?:\[.*?\])?(.*?)\\end\{itemize\}', replace_item, t, flags=re.DOTALL)
    
    # Fallback de segurança: se sobrou algum \item solto sem \begin, vira bolinha
    t = re.sub(r'\s*\\item\s+', r'\n* ', t)

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