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

def gerar_preview_web(texto):
    if not texto: return ""
    import re
    
    prev = texto
    prev = re.sub(r'£\\textbf\{(.*?)\}£', r'<b>\1</b>', prev, flags=re.DOTALL)
    prev = re.sub(r'£\\textit\{(.*?)\}£', r'<i>\1</i>', prev, flags=re.DOTALL)
    prev = re.sub(r'£\\underline\{(.*?)\}£', r'<u>\1</u>', prev, flags=re.DOTALL)
    prev = re.sub(r'£\\textcolor\{(.*?)\}\{(.*?)\}£', r'<span style="color:\1;">\2</span>', prev, flags=re.DOTALL)
    prev = re.sub(r'£\\Large\{(.*?)\}£', r'<span style="font-size:24px; font-weight:bold;">\1</span>', prev, flags=re.DOTALL)
    prev = re.sub(r'£\\small\{(.*?)\}£', r'<span style="font-size:12px;">\1</span>', prev, flags=re.DOTALL)
    prev = re.sub(r'£\\section\*\{(.*?)\}£', r'<h3>\1</h3>', prev, flags=re.DOTALL)
    prev = re.sub(r'£\\subsection\*\{(.*?)\}£', r'<h4>\1</h4>', prev, flags=re.DOTALL)
    
    prev = re.sub(r'£\\begin\{itemize\}(.*?)\\end\{itemize\}£', r'<ul>\1</ul>', prev, flags=re.DOTALL)
    prev = re.sub(r'£\\begin\{enumerate\}(.*?)\\end\{enumerate\}£', r'<ol>\1</ol>', prev, flags=re.DOTALL)
    prev = re.sub(r'\\item\s*(.*?)(?=\\item|</ul>|</ol>|$)', r'<li>\1</li>', prev, flags=re.DOTALL)
    
    prev = re.sub(r'£\\begin\{tabular\}.*?\\end\{tabular\}£', 
                  r'<div style="padding:15px; background:#e3f2fd; border-left: 5px solid #2196f3; border-radius:5px; color:#0d47a1; margin:10px 0;">'
                  r'<b>📊 Tabela LaTeX Detectada</b><br>'
                  r'<small>O código está salvo! No PDF final ela sairá com todas as grades e colunas.</small></div>', 
                  prev, flags=re.DOTALL)
    
    prev = re.sub(r'£\\texttt\{(.*?)\}£', r'<code style="background:#f0f2f6; padding:2px 4px; border-radius:4px;">\1</code>', prev, flags=re.DOTALL)
    prev = re.sub(r'£\\cite\{(.*?)\}£', r'<sup style="color:blue; font-weight:bold;">[Cit: \1]</sup>', prev, flags=re.DOTALL)
    prev = re.sub(r'£\\ref\{(.*?)\}£', r'<sup style="color:red; font-weight:bold;">[Ref: \1]</sup>', prev, flags=re.DOTALL)
    
    prev = prev.replace('£', '')
    return prev

def configurar_jinja():
    return jinja2.Environment(block_start_string='<%', block_end_string='%>', variable_start_string='<<', variable_end_string='>>', trim_blocks=True, autoescape=False, loader=jinja2.FileSystemLoader(os.path.abspath('.')))

def compilar_latex_mac(caminho_tex):
    caminho_pdf = caminho_tex.replace('.tex', '.pdf')
    try:
        # A MÁGICA AQUI: adicionamos encoding='utf-8', errors='replace'
        resultado = subprocess.run(['pdflatex', '-interaction=nonstopmode', caminho_tex], 
                                   capture_output=True, text=True, encoding='utf-8', errors='replace')
        
        st.session_state.latex_log = f"--- LOG DE {caminho_tex} ---\n" + resultado.stdout + "\n" + resultado.stderr
        
        if os.path.exists(caminho_pdf): 
            return True
        else:
            st.error(f"⚠️ O PDF não foi gerado. Olhe o Log na barra lateral para ver o motivo!")
            return False
    except Exception as e:
        st.session_state.latex_log = f"ERRO CRÍTICO DO SISTEMA:\n{str(e)}"
        st.error(f"🚫 Falha ao tentar chamar o LaTeX: {e}")
        return False