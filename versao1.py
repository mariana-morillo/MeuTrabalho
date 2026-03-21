import streamlit as st
import sqlite3
import pandas as pd
import plotly.express as plex 
import random
import os
# Força o Python do Mac a enxergar a pasta secreta do Homebrew (Zbar)
os.environ["DYLD_LIBRARY_PATH"] = "/opt/homebrew/lib:/usr/local/lib"
import subprocess
import jinja2
import unicodedata
import shutil
import math
import json
import qrcode
import cv2
import numpy as np
from fractions import Fraction
import re
from datetime import datetime, timedelta
from difflib import SequenceMatcher
import time

# =========================================================================
# --- 1. FUNÇÕES DE UTILIDADE E SEGURANÇA ---
# =========================================================================
def sanitizar_nome(texto):
    nfkd = unicodedata.normalize('NFKD', texto)
    return "".join([c for c in nfkd if not unicodedata.category(c).startswith('M')]).replace(" ", "_")

def escapar_latex(texto):
    if not texto: return ""
    texto = texto.replace('\u200b', '') # Remove caracteres fantasmas
    
    # CORREÇÃO: O 'flags=re.DOTALL' faz o escudo funcionar mesmo se tiver "Enter" no meio!
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
    
    # Faz uma cópia para processar sem alterar o original
    prev = texto
    
    # 1. ESTILOS DE TEXTO (£...£): Traduz LaTeX para HTML Web
    prev = re.sub(r'£\\textbf\{(.*?)\}£', r'<b>\1</b>', prev, flags=re.DOTALL)
    prev = re.sub(r'£\\textit\{(.*?)\}£', r'<i>\1</i>', prev, flags=re.DOTALL)
    prev = re.sub(r'£\\underline\{(.*?)\}£', r'<u>\1</u>', prev, flags=re.DOTALL)
    prev = re.sub(r'£\\textcolor\{(.*?)\}\{(.*?)\}£', r'<span style="color:\1;">\2</span>', prev, flags=re.DOTALL)
    prev = re.sub(r'£\\Large\{(.*?)\}£', r'<span style="font-size:24px; font-weight:bold;">\1</span>', prev, flags=re.DOTALL)
    prev = re.sub(r'£\\small\{(.*?)\}£', r'<span style="font-size:12px;">\1</span>', prev, flags=re.DOTALL)
    prev = re.sub(r'£\\section\*\{(.*?)\}£', r'<h3>\1</h3>', prev, flags=re.DOTALL)
    prev = re.sub(r'£\\subsection\*\{(.*?)\}£', r'<h4>\1</h4>', prev, flags=re.DOTALL)
    
    # 2. LISTAS E TÓPICOS
    prev = re.sub(r'£\\begin\{itemize\}(.*?)\\end\{itemize\}£', r'<ul>\1</ul>', prev, flags=re.DOTALL)
    prev = re.sub(r'£\\begin\{enumerate\}(.*?)\\end\{enumerate\}£', r'<ol>\1</ol>', prev, flags=re.DOTALL)
    prev = re.sub(r'\\item\s*(.*?)(?=\\item|</ul>|</ol>|$)', r'<li>\1</li>', prev, flags=re.DOTALL)
    
    # 3. TABELAS (Aviso Visual)
    prev = re.sub(r'£\\begin\{tabular\}.*?\\end\{tabular\}£', 
                  r'<div style="padding:15px; background:#e3f2fd; border-left: 5px solid #2196f3; border-radius:5px; color:#0d47a1; margin:10px 0;">'
                  r'<b>📊 Tabela LaTeX Detectada</b><br>'
                  r'<small>O código está salvo! No PDF final ela sairá com todas as grades e colunas.</small></div>', 
                  prev, flags=re.DOTALL)
    
    # 4. CÓDIGO, CITAÇÃO E REF (Recuperados!)
    prev = re.sub(r'£\\texttt\{(.*?)\}£', r'<code style="background:#f0f2f6; padding:2px 4px; border-radius:4px;">\1</code>', prev, flags=re.DOTALL)
    prev = re.sub(r'£\\cite\{(.*?)\}£', r'<sup style="color:blue; font-weight:bold;">[Cit: \1]</sup>', prev, flags=re.DOTALL)
    prev = re.sub(r'£\\ref\{(.*?)\}£', r'<sup style="color:red; font-weight:bold;">[Ref: \1]</sup>', prev, flags=re.DOTALL)
    
    # 5. LIMPEZA: Remove os £ restantes para não "sujar" a tela, 
    # mas MANTÉM os $ para o Streamlit renderizar a matemática automaticamente.
    prev = prev.replace('£', '')
    
    return prev
def recortar_e_alinhar_folha(img_orig):
    h_orig, w_orig = img_orig.shape[:2]
    proporcao = 1000 / w_orig
    img_redim = cv2.resize(img_orig, (1000, int(h_orig * proporcao)))
    
    gray = cv2.cvtColor(img_redim, cv2.COLOR_BGR2GRAY)
    blur = cv2.GaussianBlur(gray, (5, 5), 0)
    edged = cv2.Canny(blur, 50, 150)
    cnts, _ = cv2.findContours(edged, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    cnts = sorted(cnts, key=cv2.contourArea, reverse=True)[:5]

    for c in cnts:
        peri = cv2.arcLength(c, True)
        approx = cv2.approxPolyDP(c, 0.02 * peri, True)
        if len(approx) == 4 and cv2.contourArea(c) > (1000 * int(h_orig * proporcao) * 0.2):
            pts = approx.reshape(4, 2)
            rect = np.zeros((4, 2), dtype="float32")
            s = pts.sum(axis=1)
            rect[0] = pts[np.argmin(s)]
            rect[2] = pts[np.argmax(s)]
            diff = np.diff(pts, axis=1)
            rect[1] = pts[np.argmin(diff)]
            rect[3] = pts[np.argmax(diff)]

            (tl, tr, br, bl) = rect
            widthA = np.sqrt(((br[0] - bl[0]) ** 2) + ((br[1] - bl[1]) ** 2))
            widthB = np.sqrt(((tr[0] - tl[0]) ** 2) + ((tr[1] - tl[1]) ** 2))
            maxWidth = max(int(widthA), int(widthB))
            if maxWidth == 0: maxWidth = 1000

            heightA = np.sqrt(((tr[0] - br[0]) ** 2) + ((tr[1] - br[1]) ** 2))
            heightB = np.sqrt(((tl[0] - bl[0]) ** 2) + ((tl[1] - bl[1]) ** 2))
            maxHeight = max(int(heightA), int(heightB))
            
            target_h = int(1000 * (maxHeight / float(maxWidth)))

            dst = np.array([[0, 0], [999, 0], [999, target_h-1], [0, target_h-1]], dtype="float32")
            M = cv2.getPerspectiveTransform(rect, dst)
            return cv2.warpPerspective(img_redim, M, (1000, target_h))

    return img_redim

# =========================================================================
# --- 2. MANUTENÇÃO E BACKUP ---
# =========================================================================
def limpar_arquivos_temporarios():
    extensoes_lixo = ['.tex', '.log', '.aux', '.out', '.toc']
    arquivos_protegidos = ['logo.png', 'banco_provas.db', 'app_provas.py', 'template_profissional.tex', 'template_gabarito.tex']
    removidos = 0
    for f in os.listdir('.'):
        is_lixo_padrao = any(f.endswith(ext) for ext in extensoes_lixo)
        is_qr_code = f.startswith('qr_') and f.endswith('.png')
        if is_lixo_padrao or is_qr_code:
            if f not in arquivos_protegidos and not f.endswith('.pdf'):
                try:
                    os.remove(f)
                    removidos += 1
                except Exception as e:
                    print(f"Não foi possível remover {f}: {e}")
    return removidos

def criar_backup_banco():
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    nome_backup = f"backup_questoes_{timestamp}.db"
    try: shutil.copy2('banco_provas.db', nome_backup); return nome_backup
    except: return None

def backup_para_icloud():
    try:
        home = os.path.expanduser("~")
        pasta_icloud = os.path.join(home, "Library/Mobile Documents/com~apple~CloudDocs/Backup_GeradorProvas")
        if not os.path.exists(pasta_icloud): os.makedirs(pasta_icloud)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        destino = os.path.join(pasta_icloud, f"backup_provas_{timestamp}.db")
        banco_original = sqlite3.connect('banco_provas.db')
        banco_backup = sqlite3.connect(destino)
        with banco_backup: banco_original.backup(banco_backup)
        banco_backup.close()
        banco_original.close()
        return True
    except Exception as e:
        print(f"Erro no backup: {e}")
        return False

def obter_estatisticas_questoes(disciplina):
    conexao = sqlite3.connect('banco_provas.db')
    cursor = conexao.cursor()
    cursor.execute('SELECT tipo, COUNT(*) FROM questoes WHERE disciplina = ? GROUP BY tipo', (disciplina,))
    stats = cursor.fetchall()
    conexao.close()
    return {tipo: qtd for tipo, qtd in stats}

# =========================================================================
# --- 3. BASE DE DADOS E QUERIES ---
# =========================================================================
def criar_base_de_dados():
    with sqlite3.connect('banco_provas.db') as conn:
        cursor = conn.cursor()
        
        # 1. Tabelas de Provas e Questões
        cursor.execute('''CREATE TABLE IF NOT EXISTS questoes (id INTEGER PRIMARY KEY AUTOINCREMENT, disciplina TEXT, assunto TEXT, dificuldade TEXT, enunciado TEXT, imagem TEXT, pontos REAL, tipo TEXT, gabarito_discursivo TEXT, espaco_resposta TEXT, espaco_linhas INTEGER, gabarito_imagem TEXT)''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS alternativas (id INTEGER PRIMARY KEY AUTOINCREMENT, questao_id INTEGER, texto TEXT, correta BOOLEAN, imagem TEXT)''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS resultados (id INTEGER PRIMARY KEY AUTOINCREMENT, aluno_nome TEXT, aluno_ra TEXT, disciplina TEXT, versao TEXT, nota REAL, data_hora TEXT, avaliacao TEXT)''')
        # No bloco "1. Tabelas de Provas e Questões", adicione esta linha:
        cursor.execute('''CREATE TABLE IF NOT EXISTS correcoes_detalhadas (id INTEGER PRIMARY KEY AUTOINCREMENT, aluno_ra TEXT, disciplina TEXT, prova_nome TEXT, questao_num INTEGER, status TEXT, feedback_ia TEXT)''')
        # 2. Tabelas de Gestão de Sala e Turmas
        cursor.execute('''CREATE TABLE IF NOT EXISTS turmas (id INTEGER PRIMARY KEY AUTOINCREMENT, nome TEXT UNIQUE, semestre TEXT DEFAULT '2026.1')''')
        # AQUI ADICIONAMOS A SENHA NO CREAT TABLE BASE
        cursor.execute('''CREATE TABLE IF NOT EXISTS alunos (id INTEGER PRIMARY KEY AUTOINCREMENT, turma_id INTEGER, nome TEXT, ra TEXT, avatar_style TEXT DEFAULT 'bottts', email TEXT, observacoes TEXT, senha TEXT DEFAULT '123456')''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS matriculas_disciplina (id INTEGER PRIMARY KEY, turma_id INTEGER, disciplina TEXT, aluno_id INTEGER)''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS diario (id INTEGER PRIMARY KEY AUTOINCREMENT, turma_id INTEGER, data TEXT, aluno_ra TEXT, presente BOOLEAN, status TEXT DEFAULT 'Presente', pontos_atividade REAL, pontos_comportamento REAL)''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS trabalhos_extras (id INTEGER PRIMARY KEY AUTOINCREMENT, turma_id INTEGER, disciplina TEXT, nome_atividade TEXT, aluno_ra TEXT, nota REAL, data TEXT)''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS planejamento_notas (id INTEGER PRIMARY KEY AUTOINCREMENT, turma_id INTEGER, disciplina TEXT, nome_avaliacao TEXT, peso REAL, data_prevista TEXT)''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS logs_comportamento (id INTEGER PRIMARY KEY AUTOINCREMENT, aluno_ra TEXT, turma_id INTEGER, data TEXT, pontos REAL, comentario TEXT, tipo TEXT)''') 
        cursor.execute('''CREATE TABLE IF NOT EXISTS diario_conteudo (id INTEGER PRIMARY KEY, turma_id INTEGER, disciplina TEXT, data TEXT, conteudo_real TEXT, observacao TEXT)''')
        
        # 3. Tabelas de Cronograma
        cursor.execute('''CREATE TABLE IF NOT EXISTS roteiro_mestre (id INTEGER PRIMARY KEY, titulo_modelo TEXT, num_aula INTEGER, tema TEXT, tipo_aula TEXT, objetivos_aula TEXT, conteudo_detalhado TEXT, metodologia TEXT, aps_aula TEXT, referencias_aula TEXT, materiais_link TEXT, atividades TEXT, forum TEXT, link_slides TEXT, link_overleaf TEXT, link_extras TEXT, atividades_link TEXT, forum_link TEXT)''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS cronograma_detalhado (id INTEGER PRIMARY KEY, turma_id INTEGER, disciplina TEXT, num_aula INTEGER, data TEXT, tema TEXT, tipo_aula TEXT, objetivos_aula TEXT, conteudo_detalhado TEXT, metodologia TEXT, aps_aula TEXT, referencias_aula TEXT, materiais_link TEXT, atividades TEXT, forum TEXT, link_slides TEXT, link_overleaf TEXT, link_extras TEXT, atividades_link TEXT, forum_link TEXT)''')

        # 4. Migrations de Segurança
        colunas_fam_completo = [
            ('tipo_aula', 'TEXT'), ('metodologia', 'TEXT'), ('aps_aula', 'TEXT'), 
            ('atividades', 'TEXT'), ('forum', 'TEXT'), ('materiais_link', 'TEXT'),
            ('objetivos_aula', 'TEXT'), ('conteudo_detalhado', 'TEXT'), ('referencias_aula', 'TEXT'),
            ('link_slides', 'TEXT'), ('link_overleaf', 'TEXT'), ('link_extras', 'TEXT'), 
            ('atividades_link', 'TEXT'), ('forum_link', 'TEXT')
        ]
        
        for col, tipo in colunas_fam_completo:
            try: conn.execute(f"ALTER TABLE roteiro_mestre ADD COLUMN {col} {tipo}")
            except: pass 
            try: conn.execute(f"ALTER TABLE cronograma_detalhado ADD COLUMN {col} {tipo}")
            except: pass
            
        # MIGRATION DA SENHA (Protege os alunos antigos)
        try: conn.execute("ALTER TABLE alunos ADD COLUMN senha TEXT DEFAULT '123456'")
        except: pass
        # Garante que ninguém fique com senha nula
        conn.execute("UPDATE alunos SET senha = '123456' WHERE senha IS NULL")

        # MIGRATION DOS ACESSÓRIOS DO AVATAR
        try: conn.execute("ALTER TABLE alunos ADD COLUMN avatar_opts TEXT DEFAULT ''")
        except: pass

        # 5. Configurações Globais
        cursor.execute('''CREATE TABLE IF NOT EXISTS configuracoes (id INTEGER PRIMARY KEY CHECK (id = 1), instituicao TEXT, professor TEXT, departamento TEXT, curso TEXT, instrucoes TEXT)''')

        conn.commit()

def limpar_dados_teste():
    tabelas_para_limpar = [
        'resultados', 
        'correcoes_detalhadas', 
        'logs_comportamento', 
        'diario', 
        'atividades_sala'
    ]
    with sqlite3.connect('banco_provas.db') as conn:
        cursor = conn.cursor()
        for tabela in tabelas_para_limpar:
            try:
                cursor.execute(f"DELETE FROM {tabela}")
            except:
                pass # Evita erro caso a tabela ainda não exista
        conn.commit()
    return True

def inserir_questao(disc, ass, dif, enun, alts, pts, tipo, gab_disc=None, img=None, espaco="Linhas", espaco_linhas=4, gab_img=None, uso_quest="Prova Oficial"):
    with sqlite3.connect('banco_provas.db') as conexao:
        cursor = conexao.cursor()
        # Migration automática de segurança para criar a coluna nas tabelas antigas
        try: cursor.execute("ALTER TABLE questoes ADD COLUMN uso_quest TEXT DEFAULT 'Prova Oficial'")
        except: pass
        
        cursor.execute('''INSERT INTO questoes (disciplina, assunto, dificuldade, enunciado, imagem, pontos, tipo, gabarito_discursivo, espaco_resposta, espaco_linhas, gabarito_imagem, uso_quest) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''', (disc, ass, dif, enun, img, float(pts), tipo, gab_disc, espaco, int(espaco_linhas), gab_img, uso_quest))
        q_id = cursor.lastrowid
        if tipo in ["Múltipla Escolha", "Verdadeiro ou Falso"]:
            for txt, corr, img_alt in alts:
                cursor.execute('INSERT INTO alternativas (questao_id, texto, correta, imagem) VALUES (?, ?, ?, ?)', (q_id, txt, corr, img_alt))
        conexao.commit()

def buscar_e_embaralhar_alternativas(q_id):
    with sqlite3.connect('banco_provas.db') as conexao:
        cursor = conexao.cursor()
        cursor.execute('SELECT texto, correta, imagem FROM alternativas WHERE questao_id = ?', (q_id,))
        alts = cursor.fetchall()
    random.shuffle(alts)
    return alts

def buscar_alternativas_originais(q_id):
    with sqlite3.connect('banco_provas.db') as conexao:
        cursor = conexao.cursor()
        cursor.execute('SELECT texto, correta, imagem FROM alternativas WHERE questao_id = ? ORDER BY id', (q_id,))
        alts = cursor.fetchall()
    return alts

def carregar_configuracoes():
    with sqlite3.connect('banco_provas.db') as conexao:
        cursor = conexao.cursor()
        cursor.execute('SELECT instituicao, professor, departamento, curso, instrucoes FROM configuracoes WHERE id = 1')
        res = cursor.fetchone()
    return res

def salvar_configuracoes(inst, prof, dep, curso, instr):
    with sqlite3.connect('banco_provas.db') as conexao:
        cursor = conexao.cursor()
        cursor.execute('''UPDATE configuracoes SET instituicao=?, professor=?, departamento=?, curso=?, instrucoes=? WHERE id=1''', (inst, prof, dep, curso, instr))
        conexao.commit()

def excluir_questao(q_id):
    with sqlite3.connect('banco_provas.db') as conexao:
        cursor = conexao.cursor()
        cursor.execute('DELETE FROM alternativas WHERE questao_id = ?', (q_id,))
        cursor.execute('DELETE FROM questoes WHERE id = ?', (q_id,))
        conexao.commit()

def obter_assuntos_da_disciplina(disciplina):
    with sqlite3.connect('banco_provas.db') as conexao:
        cursor = conexao.cursor()
        cursor.execute('SELECT DISTINCT assunto FROM questoes WHERE disciplina = ? AND assunto IS NOT NULL AND assunto != "" ORDER BY assunto', (disciplina,))
        res = [r[0] for r in cursor.fetchall()]
    return ["Todos"] + res

def buscar_questoes_filtradas(disciplina, limite=None, assunto="Todos", dificuldade="Todos", tipo="Todos", sortear=False, excluir_ids=None, uso="Todos"):
    with sqlite3.connect('banco_provas.db') as conexao:
        cursor = conexao.cursor()
        try: cursor.execute("ALTER TABLE questoes ADD COLUMN uso_quest TEXT DEFAULT 'Prova Oficial'")
        except: pass
        
        query = '''SELECT id, enunciado, imagem, pontos, tipo, gabarito_discursivo, espaco_resposta, espaco_linhas, dificuldade, assunto, gabarito_imagem, uso_quest FROM questoes WHERE disciplina = ?'''
        params = [disciplina]
        if assunto != "Todos": query += " AND assunto = ?"; params.append(assunto)
        if dificuldade != "Todos": query += " AND dificuldade = ?"; params.append(dificuldade)
        if tipo != "Todos": query += " AND tipo = ?"; params.append(tipo)
        if uso != "Todos": query += " AND uso_quest = ?"; params.append(uso)
        
        if excluir_ids:
            placeholders = ','.join('?' for _ in excluir_ids)
            query += f" AND id NOT IN ({placeholders})"
            params.extend(excluir_ids)
        if sortear: query += " ORDER BY RANDOM()"
        else: query += " ORDER BY id DESC"
        if limite: query += " LIMIT ?"; params.append(limite)
        cursor.execute(query, params)
        q = cursor.fetchall()
    return q

def salvar_resultado_prova(nome, ra, disc, versao, nota, avaliacao="P1"):
    with sqlite3.connect('banco_provas.db') as conexao:
        cursor = conexao.cursor()
        agora = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
        cursor.execute("PRAGMA table_info(resultados)")
        colunas = [col[1] for col in cursor.fetchall()]
        if "avaliacao" not in colunas:
            cursor.execute("ALTER TABLE resultados ADD COLUMN avaliacao TEXT DEFAULT 'P1'")
        cursor.execute('SELECT id FROM resultados WHERE aluno_ra = ? AND disciplina = ? AND avaliacao = ?', (ra, disc, avaliacao))
        registro_existente = cursor.fetchone()
        if registro_existente:
            cursor.execute('UPDATE resultados SET nota = ?, data_hora = ?, versao = ? WHERE id = ?', (nota, agora, versao, registro_existente[0]))
        else:
            cursor.execute('INSERT INTO resultados (aluno_nome, aluno_ra, disciplina, versao, nota, data_hora, avaliacao) VALUES (?, ?, ?, ?, ?, ?, ?)', (nome, ra, disc, versao, nota, agora, avaliacao))
        conexao.commit()
    backup_para_icloud()
def salvar_feedback_detalhado(ra, disc, prova, q_num, status, feedback):
    with sqlite3.connect('banco_provas.db') as conn:
        # Limpa feedbacks antigos dessa mesma prova para não duplicar
        conn.execute("DELETE FROM correcoes_detalhadas WHERE aluno_ra=? AND disciplina=? AND prova_nome=? AND questao_num=?", (ra, disc, prova, q_num))
        conn.execute('''INSERT INTO correcoes_detalhadas (aluno_ra, disciplina, prova_nome, questao_num, status, feedback_ia) 
                        VALUES (?, ?, ?, ?, ?, ?)''', (ra, disc, prova, q_num, status, feedback))
        conn.commit()
def detectar_duplicata(enunciado, disciplina):
    with sqlite3.connect('banco_provas.db') as conexao:
        cursor = conexao.cursor()
        cursor.execute('SELECT id FROM questoes WHERE enunciado = ? AND disciplina = ?', (enunciado, disciplina))
        resultado = cursor.fetchone()
    return resultado[0] if resultado else None

def calcular_percentual_similaridade(a, b):
    return SequenceMatcher(None, a, b).ratio()

def buscar_questoes_proximas(enunciado_novo, disciplina, limite=0.8):
    with sqlite3.connect('banco_provas.db') as conexao:
        cursor = conexao.cursor()
        cursor.execute('SELECT id, enunciado FROM questoes WHERE disciplina = ?', (disciplina,))
        questoes_existentes = cursor.fetchall()
    encontradas = []
    texto_novo = enunciado_novo.lower().strip()
    for q_id, q_texto in questoes_existentes:
        similaridade = calcular_percentual_similaridade(texto_novo, q_texto.lower().strip())
        if similaridade >= limite: encontradas.append({"id": q_id, "texto": q_texto, "percentual": similaridade * 100})
    return sorted(encontradas, key=lambda x: x['percentual'], reverse=True)

# =========================================================================
# --- 4. COMPILAÇÃO E JINJA ---
# =========================================================================
def configurar_jinja():
    return jinja2.Environment(block_start_string='<%', block_end_string='%>', variable_start_string='<<', variable_end_string='>>', trim_blocks=True, autoescape=False, loader=jinja2.FileSystemLoader(os.path.abspath('.')))

def compilar_latex_mac(caminho_tex):
    caminho_mac = "/Library/TeX/texbin/pdflatex"
    caminho_pdf = caminho_tex.replace('.tex', '.pdf')
    try:
        # Capturamos a saída (stdout) e o erro (stderr) em formato de texto
        resultado = subprocess.run([caminho_mac, '-interaction=nonstopmode', caminho_tex], 
                                   capture_output=True, text=True)
        
        # Guardamos o log completo na memória do site para você ler na barra lateral
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

# =========================================================================
# --- 5. LISTAS DE SÍMBOLOS E PAINEL FLUTUANTE ---
# =========================================================================
# A NOVA LISTA DE ESTILOS GERAIS (COM CÓDIGOS CORRIGIDOS)
estilo = [
    ("𝐁 Negrito", r"\textbf{texto}"), 
    ("𝐼 Itálico", r"\textit{texto}"), 
    ("U̲ Sublinh.", r"\underline{texto}"), 
    ("T Grande", r"\Large{texto}"), 
    ("t Pequeno", r"\small{texto}"), 
    ("🔴 Cor", r"\textcolor{red}{texto}"), 
    ("H1 Título", r"\section*{texto}"), 
    ("H2 Subtít.", r"\subsection*{texto}"), 
    ("• Tópicos", r"\begin{itemize} \item item 1 \item item 2 \end{itemize}"), 
    ("1. Lista", r"\begin{enumerate} \item item 1 \item item 2 \end{enumerate}"), 
    ("Tabela", r"\begin{tabular}{|c|c|} \hline Coluna A & Coluna B \\ \hline Dado 1 & Dado 2 \\ \hline \end{tabular}"), 
    ("Citação", r"\cite{referencia}"), 
    ("Referência", r"\ref{label}"),
    ("</> Código", r"\texttt{codigo}")
]
gregas = [("α", r"\alpha"), ("β", r"\beta"), ("γ", r"\gamma"), ("δ", r"\delta"), ("ε", r"\epsilon"), ("ζ", r"\zeta"), ("η", r"\eta"), ("θ", r"\theta"), ("κ", r"\kappa"), ("λ", r"\lambda"), ("μ", r"\mu"), ("ν", r"\nu"), ("ξ", r"\xi"), ("π", r"\pi"), ("ρ", r"\rho"), ("σ", r"\sigma"), ("τ", r"\tau"), ("φ", r"\phi"), ("χ", r"\chi"), ("ψ", r"\psi"), ("ω", r"\omega"), ("Γ", r"\Gamma"), ("Δ", r"\Delta"), ("Θ", r"\Theta"), ("Λ", r"\Lambda"), ("Σ", r"\Sigma"), ("Φ", r"\Phi"), ("Ω", r"\Omega")]
matematica = [(r"x/y", r"\frac{x}{y}"), ("xⁿ", r"x^{n}"), ("xₙ", r"x_{n}"), ("xₙʸ", r"x_{n}^{y}"), ("√x", r"\sqrt{x}"), ("ⁿ√x", r"\sqrt[n]{x}"), ("( )", r"\left(  \right)"), ("[ ]", r"\left[  \right]"), ("{ }", r"\left\{  \right\}"), ("[]₂ₓ₂", r"\begin{bmatrix} a & b \\ c & d \end{bmatrix}"), ("v⃗", r"\vec{v}"), ("n̂", r"\hat{n}"), ("ẋ", r"\dot{x}"), ("ẍ", r"\ddot{x}"), ("x̄", r"\bar{x}"), ("≥", r"\geq"), ("≤", r"\leq"), ("≠", r"\neq"), ("≈", r"\approx"), ("∞", r"\infty"), ("→", r"\to"), ("°C", r"^\circ C"), (" ±", r"\pm"), (" ×", r"\times")]
calculo = [("Lim", r"\lim_{x \to \infty}"), ("∫", r"\int"), ("∫ₐᵇ", r"\int_{a}^{b}"), ("∬", r"\iint"), ("∮", r"\oint"), ("Σ", r"\sum_{i=1}^{n}"), ("Π", r"\prod_{i=1}^{n}"), ("d/dx", r"\frac{d}{dx}"), ("d²/dx²", r"\frac{d^2}{dx^2}"), ("∂", r"\partial"), ("∇", r"\nabla"), ("∇⋅F", r"\nabla \cdot"), ("∇×F", r"\nabla \times")]
fluidos = [("Bernoulli", r"P_1 + \frac{1}{2}\rho v_1^2 + \rho g z_1 = P_2 + \frac{1}{2}\rho v_2^2 + \rho g z_2"), ("Darcy-Weisbach", r"h_f = f \cdot \frac{L}{D} \cdot \frac{v^2}{2g}"), ("Reynolds", r"Re = \frac{\rho v D}{\mu}"), ("Continuidade", r"A_1 v_1 = A_2 v_2"), ("Empuxo", r"E = \rho_{liq} \cdot V_{sub} \cdot g"), ("Pressão Hidro.", r"P = P_{atm} + \rho g h")]
termo = [("1ª Lei", r"\Delta U = Q - W"), ("Gás Ideal", r"P V = n R T"), ("Trabalho Exp.", r"W = \int_{V_1}^{V_2} P dV"), ("Rendimento η", r"\eta = \frac{W_{liq}}{Q_{q}}"), ("Carnot", r"\eta_{max} = 1 - \frac{T_f}{T_q}"), ("Entropia ΔS", r"\Delta S = \int \frac{dQ_{rev}}{T}"), ("Calor Sensível", r"Q = m \cdot c \cdot \Delta T")]

def injetar_direto(comando, target_key):
    if target_key in st.session_state: st.session_state[target_key] += f" ${comando}$ "
    else: st.session_state[target_key] = f" ${comando}$ "
# NOVA FUNÇÃO (para Textos, Tabelas e Tópicos com £)
def injetar_texto(comando, target_key):
    if target_key in st.session_state: st.session_state[target_key] += f" £{comando}£ "
    else: st.session_state[target_key] = f" £{comando}£ "

    

# =========================================================================
# --- 6. INICIALIZAÇÃO DA INTERFACE (STREAMLIT) ---
# =========================================================================
criar_base_de_dados()
st.set_page_config(page_title="Gerador da Mari", layout="wide", initial_sidebar_state="collapsed")
# === 🎨 AJUSTE DE DESIGN PROFISSIONAL CALIBRADO (CSS) ===
st.markdown("""
    <style>
    /* 1. TOPO DA TELA: Devolve espaço para as abas não sumirem */
    .block-container {
        padding-top: 3.5rem !important; 
        margin-top: 4px !important;
    }

    /* 2. BOTÕES: Mantém o tamanho slim e força a altura EXATA para todos */
    div[data-testid="stPopover"] button, 
    div.stButton button {
        height: 40px !important;
        min-height: 40px !important;
        max-height: 40px !important; 
        width: 100% !important; /* 🔥 A MÁGICA ACONTECE AQUI: Força a esticar! 🔥 */
        box-sizing: border-box !important; 
        padding: 0px 10px !important;
        font-size: 14px !important;
        line-height: 1.2 !important;
        display: flex !important;
        align-items: center !important;
        justify-content: center !important;
        white-space: nowrap !important; 
        overflow: hidden !important;    
    }
    

    /* 3. TÍTULOS (ENUNCIADO): Ajustado para NÃO encavalar nos botões */
    .stMarkdown p strong {
        font-size: 15px !important;
        color: #31333F !important;
        display: block !important;
        margin-bottom: 2px !important; /* Tiramos o negativo para não subir no texto */
        margin-top: 5px !important;
    }

    /* 4. COMPACTAÇÃO GERAL: Diminui o buraco entre as linhas */
    [data-testid="stVerticalBlock"] {
        gap: 0.7rem !important;
    }

    /* 5. LINHA DIVISÓRIA: Fina e discreta */
    hr { margin: 0.5rem 0 !important; }

    /* Ajuste para o texto dentro do botão não sumir */
    div[data-testid="stPopover"] p { font-size: 14px !important; margin: 0 !important; }
    </style>
""", unsafe_allow_html=True)

with st.sidebar:
    st.header("🛠️ Manutenção do Sistema")
    
    # 1. Limpeza de arquivos (Evita conflitos no LaTeX)
    if st.button("🧹 Limpar Arquivos Temporários", use_container_width=True):
        qtd_removidos = limpar_arquivos_temporarios()
        if qtd_removidos > 0: 
            st.success(f"Limpeza concluída! {qtd_removidos} arquivos apagados.")
        else: 
            st.info("A pasta já está limpa.")
            
    st.write("---")
    
    # 2. Segurança de Dados (Backups)
    if st.button("💾 Fazer Backup Local", use_container_width=True):
        nome_bkp = criar_backup_banco()
        if nome_bkp: st.success(f"Backup criado: {nome_bkp}")
        else: st.error("Falha ao criar o backup local.")
            
    if st.button("☁️ Forçar Backup iCloud", use_container_width=True):
        if backup_para_icloud(): st.success("Sincronizado com o iCloud!")
        else: st.error("Falha na sincronização.")

    # 3. O NOVO DEPURADOR (Sua "Caixa-Preta")
    st.write("---")
    st.subheader("🕵️ Depurador LaTeX")
    with st.expander("🐛 Ver Log de Compilação", expanded=False):
        if 'latex_log' in st.session_state and st.session_state.latex_log:
            st.code(st.session_state.latex_log, language="log")
            if st.button("🧹 Limpar Histórico do Log"):
                st.session_state.latex_log = ""
                st.rerun()
        else:
            st.info("Nenhum log gerado. Tente compilar uma prova.")

    st.write("---")
    st.subheader("⚠️ Zona de Perigo")
    if st.button("🚨 RESETAR DADOS DE TESTE", use_container_width=True):
        if limpar_dados_teste():
            st.success("Banco de dados resetado!")
            st.balloons()

# 🟢 OS 4 PILARES MESTRES DA SUA ARQUITETURA
aba_inicio, aba_avaliacoes, aba_fabrica, aba_turmas, aba_sala = st.tabs([
    " 🏠 Início", "🎯 Central de Avaliações", "🏭 Fábrica de Disciplinas", "🏫 Semestres e Turmas", "🎮 Sala de Aula (Dojo)"
])
# =========================================================================
# PILAR 0: TELA DE BOAS VINDAS E TUTORIAL
# =========================================================================
with aba_inicio:
    st.markdown("<h1 style='text-align: center; color: #2c3e50;'>👋 Bem-vinda ao Gerador da Mari!</h1>", unsafe_allow_html=True)
    st.markdown("<p style='text-align: center; font-size: 18px; color: #7f8c8d;'>Sua central completa de gestão acadêmica e ensino de Engenharia.</p>", unsafe_allow_html=True)
    st.write("---")

    col_h1, col_h2 = st.columns(2)
    
    with col_h1:
        st.markdown("""
        <div style="background-color: #e8f4fd; padding: 15px; border-radius: 8px; height: 140px; margin-bottom: 15px;">
            <b style="color: #0c5460; font-size: 16px;">🎯 Central de Avaliações</b><br><br>
            <span style="color: #0c5460; font-size: 15px;">Crie questões, gere provas em PDF com QR Code e corrija lotes inteiros de forma automática usando nossa visão computacional.</span>
        </div>
        """, unsafe_allow_html=True)
        
        st.markdown("""
        <div style="background-color: #edf7ed; padding: 15px; border-radius: 8px; height: 140px; margin-bottom: 15px;">
            <b style="color: #1e4620; font-size: 16px;">🏫 Semestres e Turmas</b><br><br>
            <span style="color: #1e4620; font-size: 15px;">Importe seus alunos, gerencie matrículas, configure os pesos das notas (Provas, Listas, Labs) e gere o Boletim Mestre final.</span>
        </div>
        """, unsafe_allow_html=True)

    with col_h2:
        st.markdown("""
        <div style="background-color: #fff8e1; padding: 15px; border-radius: 8px; height: 140px; margin-bottom: 15px;">
            <b style="color: #663c00; font-size: 16px;">🏭 Fábrica de Disciplinas</b><br><br>
            <span style="color: #663c00; font-size: 15px;">Monte o seu Plano de Ensino estruturado (Ementa, Bibliografia) e planeje o roteiro completo de aulas do semestre.</span>
        </div>
        """, unsafe_allow_html=True)

        st.markdown("""
        <div style="background-color: #fdeded; padding: 15px; border-radius: 8px; height: 140px; margin-bottom: 15px;">
            <b style="color: #5f2120; font-size: 16px;">🎮 Sala de Aula (Dojo)</b><br><br>
            <span style="color: #5f2120; font-size: 15px;">Seu painel ao vivo: faça chamadas rápidas, registre o diário, controle o tempo, sorteie alunos e aplique feedbacks de comportamento.</span>
        </div>
        """, unsafe_allow_html=True)

    st.write("---")
    st.subheader("💡 Como começar um novo semestre?")
    
    with st.expander("1️⃣ Preparando o Terreno (Passo a Passo)"):
        st.write("""
        1. **Crie a Turma:** Vá na aba *Semestres e Turmas* e cadastre a sua turma (Ex: Turma 2026.1).
        2. **Importe os Alunos:** Ainda na mesma aba, suba sua planilha de Excel/CSV com as colunas NOME e RA.
        3. **Crie a Disciplina:** Vá na *Fábrica de Disciplinas* e crie o molde (Ex: Termodinâmica ou Mecânica dos Fluidos) preenchendo o plano de aulas.
        4. **Faça as Matrículas:** Volte em *Semestres e Turmas*, selecione a turma e a disciplina, e matricule os alunos.
        5. **Defina as Notas:** Na sub-aba *Pesos de Notas*, configure quantas provas, listas e laboratórios a disciplina terá para gerar o Boletim.
        """)
        
    with st.expander("2️⃣ Dicas de Ouro 🏆"):
        st.write("""
        * **Fórmulas Matemáticas Rápidas:** Na hora de cadastrar questões, use a ferramenta `f(x)` para injetar equações complexas de fluidos e termodinâmica sem precisar digitar o código LaTeX inteiro.
        * **Modo Grupos:** No Dojo (Sala de Aula), a aba "Grupos" permite dividir a sala e lançar a nota de uma atividade prática para 4 ou 5 alunos de uma vez só!
        * **Segurança dos Dados:** Use a barra lateral 🛠️ para fazer backups regulares do seu banco de dados e sincronizar com a nuvem.
        """)
# =========================================================================
# PILAR 1: CENTRAL DE AVALIAÇÕES
# =========================================================================
with aba_avaliacoes:
    # A LINHA st.header FOI APAGADA DAQUI 
    
    # Substituição: declarando de forma explícita para o Pylance entender
    abas_centrais = st.tabs([
        "➕ 1. Cadastrar Questão", "🗂️ 2. Editar Banco", "🖨️ 3. Gerar Prova (PDF)", "📸 4. Corrigir Lote"
    ])
    sub_cad = abas_centrais[0]
    sub_edit = abas_centrais[1]
    sub_gen = abas_centrais[2]
    sub_corr = abas_centrais[3]
    
    # --- SUB-ABA 1.1: CADASTRAR ---
    with sub_cad:
        if st.session_state.get('limpar_proxima_cad'):
            keys_texto = ["enun_input", "gab_input_cad"]
            for k in list(st.session_state.keys()):
                if k.startswith("t_alt_cad_") or k in keys_texto: st.session_state[k] = ""
            st.session_state.uploader_reset_cad = st.session_state.get('uploader_reset_cad', 0) + 1
            st.session_state.limpar_proxima_cad = False
        st.markdown("**⚙️ Configuração**")
        
        c1, c2, c3, c_uso = st.columns([0.2, 0.25, 0.3, 0.25])
        with c1: t_q = st.selectbox("Tipo", ["Múltipla Escolha", "Verdadeiro ou Falso", "Discursiva", "Numérica"], key="cad_tipo")
        with c2: d_c = st.selectbox("Disciplina", ["Termodinâmica", "Mecânica dos Fluidos", "TCC 1"], key="cad_disc")
        with c3: ass_c = st.text_input("Assunto", placeholder="Ex: Ciclos", key="cad_ass")
        with c_uso: uso_c = st.selectbox("Uso da Questão", ["Prova Oficial", "Lista de Treino", "Dojo / Sala"], key="cad_uso")

        c4, c5, c6, c7 = st.columns([0.2, 0.2, 0.3, 0.3])
        with c4: dif_c = st.selectbox("Dificuldade", ["Fácil", "Média", "Difícil"], key="cad_dif")
        with c5: p_c = st.number_input("Pontos", min_value=0.1, value=1.0, key="cad_pt")
        with c6: esp_c = st.selectbox("Espaço", ["Linhas", "Quadriculado", "Caixa Vazia", "Nenhum"], key="cad_esp")
        with c7: tam_c = st.number_input("Tamanho (cm)", min_value=1, value=4, key="cad_tam")

        # --- BLOCO UNIFICADO: ELABORAÇÃO DO ENUNCIADO (SUB-ABA 1.1) ---
        st.write("---")
        
       
        
        st.markdown("**💬 Enunciado**")
        
        # 1. BARRA DE FERRAMENTAS (Lado a Lado no Topo)
        col_ferramentas = st.columns([0.15, 0.15, 0.15, 0.55])
         # Puxamos o reset_id para garantir que o upload de imagem limpe após salvar
        reset_id = st.session_state.get('uploader_reset_cad', 0)
        with col_ferramentas[0]:
            with st.popover("🖋️ Estilo", use_container_width=True):
                c = st.columns(2)
                for i, (l, cmd) in enumerate(estilo): 
                    c[i%2].button(l, key=f"cad_est_{i}", on_click=injetar_texto, args=(cmd, "enun_input"))
        
        with col_ferramentas[1]:
            with st.popover("🧮 f(x)", use_container_width=True):
                tg, tm, tc, tf, tt = st.tabs(["αβγ", "Mat", "Cálc", "🌊", "🔥"])
                with tg:
                    c = st.columns(4)
                    for i, (l, cmd) in enumerate(gregas): c[i%4].button(l, key=f"cad_gr_{i}", on_click=injetar_direto, args=(cmd, "enun_input"))
                with tm:
                    c = st.columns(3)
                    for i, (l, cmd) in enumerate(matematica): c[i%3].button(l, key=f"cad_mt_{i}", on_click=injetar_direto, args=(cmd, "enun_input"))
                with tc:
                    c = st.columns(3)
                    for i, (l, cmd) in enumerate(calculo): c[i%3].button(l, key=f"cad_cl_{i}", on_click=injetar_direto, args=(cmd, "enun_input"))
                with tf:
                    c = st.columns(2)
                    for i, (l, cmd) in enumerate(fluidos): c[i%2].button(l, key=f"cad_fl_{i}", on_click=injetar_direto, args=(cmd, "enun_input"))
                with tt:
                    c = st.columns(2)
                    for i, (l, cmd) in enumerate(termo): c[i%2].button(l, key=f"cad_tr_{i}", on_click=injetar_direto, args=(cmd, "enun_input"))

        with col_ferramentas[2]:
            with st.popover("🖼️ Imagem", use_container_width=True):
                i_c = st.file_uploader("Anexar Imagem", type=["png", "jpg", "jpeg"], key=f"up_enun_cad_{reset_id}", label_visibility="collapsed")
                if i_c: 
                    st.image(i_c, caption="Preview da Imagem", use_container_width=True)

        # 2. CAIXA DE TEXTO (Largura Total)
        e_c = st.text_area("Enunciado", key="enun_input", height=180, label_visibility="collapsed", placeholder="Escreva o enunciado aqui...")

        # 3. PREVIEW E LÓGICA DE SEGURANÇA (DUPLICATAS)
        pode_gravar = True
        if e_c.strip():
            with st.expander("👁️ Pré-visualização", expanded=True): 
                # O \u200b força o Streamlit a renderizar LaTeX misturado com HTML (tabelas/cores)
                st.markdown("\u200b" + gerar_preview_web(e_c), unsafe_allow_html=True)
            
            # Verificação de Duplicatas (Evita questões repetidas no seu banco)
            id_duplicado = detectar_duplicata(e_c, d_c)
            if id_duplicado:
                st.error(f"⚠️ **Questão idêntica!** Já existe no banco (ID: {id_duplicado}).")
                pode_gravar = False
            else:
                similares = buscar_questoes_proximas(e_c, d_c, limite=0.75)
                if similares:
                    st.warning(f"🔔 **Atenção:** Encontrei {len(similares)} questões muito parecidas.")
                    with st.expander("Ver similares para comparar"):
                        for s in similares[:3]: st.write(f"- ID {s['id']} ({s['percentual']:.1f}% similar): {s['texto'][:100]}...")
                    confirmar_similar = st.checkbox("Esta questão é diferente. Quero salvar mesmo assim.", key="chk_sim")
                    if not confirmar_similar: pode_gravar = False
        # --- FIM DO BLOCO UNIFICADO ---
        st.write("---")
        st.markdown("**💡 Resposta**")
        alts_final, gab_d_final, gab_img_final = [], None, None
        letras = "ABCDEFGHIJ"
        
        if t_q == "Múltipla Escolha":
            if "n_opt" not in st.session_state: st.session_state.n_opt = 4
            
            cb1, cb2, _ = st.columns([0.12, 0.12, 0.76])
            if cb1.button("➕ Linha", key="cad_add_l"): st.session_state.n_opt += 1; st.rerun()
            if cb2.button("➖ Linha", key="cad_rm_l") and st.session_state.n_opt > 2: st.session_state.n_opt -= 1; st.rerun()
            
            

            for i in range(st.session_state.n_opt):
                # Cada alternativa em um card visual separado
                with st.container(border=True):
                    # Linha 1: Barra de Ferramentas (Agora com Imagem em Popover)
                    c_check, c_est, c_fx, c_img = st.columns([0.1, 0.25, 0.25, 0.25])

                    corr = c_check.checkbox(letras[i], key=f"c_alt_cad_{i}")
                    
                    with c_est:
                        with st.popover("🖋️ Estilo", use_container_width=True):
                            c = st.columns(2)
                            for idx, (l, cmd) in enumerate(estilo): 
                                c[idx%2].button(l, key=f"alt_e_{i}_{idx}", on_click=injetar_texto, args=(cmd, f"t_alt_cad_{i}"))
                    
                    with c_fx:
                        with st.popover("🧮 f(x)", use_container_width=True):
                            tg, tm, tc, tf, tt = st.tabs(["α", "M", "C", "🌊", "🔥"])
                            with tg:
                                c = st.columns(4)
                                for idx, (l, cmd) in enumerate(gregas): c[idx%4].button(l, key=f"alt_g_{i}_{idx}", on_click=injetar_direto, args=(cmd, f"t_alt_cad_{i}"))
                            with tm:
                                c = st.columns(3)
                                for idx, (l, cmd) in enumerate(matematica): c[idx%3].button(l, key=f"alt_m_{i}_{idx}", on_click=injetar_direto, args=(cmd, f"t_alt_cad_{i}"))
                            with tc:
                                c = st.columns(3)
                                for idx, (l, cmd) in enumerate(calculo): c[idx%3].button(l, key=f"alt_c_{i}_{idx}", on_click=injetar_direto, args=(cmd, f"t_alt_cad_{i}"))
                            with tf:
                                c = st.columns(1)
                                for idx, (l, cmd) in enumerate(fluidos): c[0].button(l, key=f"alt_f_{i}_{idx}", on_click=injetar_direto, args=(cmd, f"t_alt_cad_{i}"))
                            with tt:
                                c = st.columns(1)
                                for idx, (l, cmd) in enumerate(termo): c[0].button(l, key=f"alt_t_{i}_{idx}", on_click=injetar_direto, args=(cmd, f"t_alt_cad_{i}"))

                    with c_img:
                        # Botão de imagem idêntico ao do enunciado
                        with st.popover("🖼️ Imagem", use_container_width=True):
                            img_alt = st.file_uploader(f"Imagem {letras[i]}", type=["png", "jpg", "jpeg"], key=f"i_alt_cad_{i}_{reset_id}", label_visibility="collapsed")

                    # Linha 2: Campo de Texto
                    txt = st.text_input(f"Texto da {letras[i]}", key=f"t_alt_cad_{i}", label_visibility="collapsed", placeholder=f"Alternativa {letras[i]}...")
                    
                    # Linha 3: Previews (Texto e Imagem)
                    if txt.strip():
                        st.markdown(f'<span style="color:#2ecc71;">↳</span> {gerar_preview_web(txt)}', unsafe_allow_html=True)
                    
                    if img_alt:
                        # Preview da imagem aparece automático após o upload
                        st.image(img_alt, width=150)
                    
                    alts_final.append((txt, corr, img_alt))
        
        elif t_q == "Verdadeiro ou Falso":
            resp = st.radio("Gabarito:", ["Verdadeiro", "Falso"], horizontal=True)
            alts_final = [("Verdadeiro", resp == "Verdadeiro", None), ("Falso", resp == "Falso", None)]
        
        elif t_q == "Numérica":
            
            gab_num = st.number_input("Resposta Exata (0 a 99):", min_value=0, max_value=99, step=1)
            gab_d_final = str(gab_num).zfill(2) 
            c_g1, c_g2 = st.columns([0.85, 0.15])
            with c_g1: st.info(f"O gabarito será salvo como: **{gab_d_final}**")
            gab_img_final = st.file_uploader("Upload de Imagem da Resolução", type=["png", "jpg", "jpeg"], key=f"gab_img_cad_{reset_id}")
            
        else: # Discursiva
            st.markdown("**💡 Resolução Detalhada**")
            
            # 1. BARRA DE FERRAMENTAS SUPERIOR (Lado a Lado)
            col_gab_ferr = st.columns([0.15, 0.15, 0.15, 0.55])
            
            with col_gab_ferr[0]:
                with st.popover("🖋️ Estilo", use_container_width=True):
                    c = st.columns(2)
                    for i, (l, cmd) in enumerate(estilo): 
                        c[i%2].button(l, key=f"gab_est_{i}", on_click=injetar_texto, args=(cmd, "gab_input_cad"))
            
            with col_gab_ferr[1]:
                with st.popover("🧮 f(x)", use_container_width=True):
                    tg, tm, tc, tf, tt = st.tabs(["αβγ", "Mat", "Cálc", "🌊", "🔥"])
                    with tg:
                        c = st.columns(4)
                        for i, (l, cmd) in enumerate(gregas): c[i%4].button(l, key=f"gab_gr_{i}", on_click=injetar_direto, args=(cmd, "gab_input_cad"))
                    with tm:
                        c = st.columns(3)
                        for i, (l, cmd) in enumerate(matematica): c[i%3].button(l, key=f"gab_mt_{i}", on_click=injetar_direto, args=(cmd, "gab_input_cad"))
                    with tc:
                        c = st.columns(3)
                        for i, (l, cmd) in enumerate(calculo): c[i%3].button(l, key=f"gab_cl_{i}", on_click=injetar_direto, args=(cmd, "gab_input_cad"))
                    with tf:
                        # Coluna única para nomes longos (Bernoulli, Reynolds...)
                        c = st.columns(1)
                        for i, (l, cmd) in enumerate(fluidos): c[0].button(l, key=f"gab_fl_{i}", on_click=injetar_direto, args=(cmd, "gab_input_cad"))
                    with tt:
                        c = st.columns(1)
                        for i, (l, cmd) in enumerate(termo): c[0].button(l, key=f"gab_tr_{i}", on_click=injetar_direto, args=(cmd, "gab_input_cad"))

            with col_gab_ferr[2]:
                with st.popover("🖼️ Imagem", use_container_width=True):
                    # O uploader fica aqui dentro, mas o preview aparece fora para você conferir
                    gab_img_final = st.file_uploader("Upload da Resolução", type=["png", "jpg", "jpeg"], key=f"gab_img_cad_{reset_id}", label_visibility="collapsed")

            # 2. CAIXA DE TEXTO (Largura Total para fórmulas longas)
            gab_d_final = st.text_area("Texto da Resolução", key="gab_input_cad", height=150, label_visibility="collapsed", placeholder="Explique o passo a passo da solução aqui...")

            # 3. PREVIEWS REATIVOS (Texto e Imagem)
            if gab_d_final.strip():
                with st.expander("👁️ Pré-visualização da Resolução", expanded=True):
                    # O \u200b garante que o Streamlit processe a matemática corretamente
                    st.markdown("\u200b" + gerar_preview_web(gab_d_final), unsafe_allow_html=True)
            
            if gab_img_final:
                st.image(gab_img_final, caption="👁️ Preview da Imagem da Resolução", width=400)
        st.write("---")
        if st.button("💾 Guardar Questão", type="primary", width="stretch", disabled=not pode_gravar):
            img_n = sanitizar_nome(i_c.name) if i_c else None
            if i_c:
                with open(img_n, "wb") as f: f.write(i_c.getbuffer())
            
            gab_img_n = sanitizar_nome(gab_img_final.name) if gab_img_final else None
            if gab_img_final:
                with open(gab_img_n, "wb") as f: f.write(gab_img_final.getbuffer())
            
            alts_para_banco = []
            for txt, corr, img_obj in alts_final:
                nome_img_alt = sanitizar_nome(img_obj.name) if img_obj else None
                if img_obj:
                    with open(nome_img_alt, "wb") as f: f.write(img_obj.getbuffer())
                alts_para_banco.append((txt, corr, nome_img_alt))

            # Adicione , uso_c no final dos parênteses da função:
            inserir_questao(d_c, ass_c, dif_c, e_c, alts_para_banco, p_c, t_q, gab_d_final, img_n, esp_c, tam_c, gab_img_n, uso_c)
            st.success("✅ Questão guardada com sucesso!")
            st.session_state.limpar_proxima_cad = True
            st.rerun()

    # --- SUB-ABA 1.2: EDITAR BANCO ---
    with sub_edit:
        conn = sqlite3.connect('banco_provas.db')
        df_todas = pd.read_sql('SELECT id, disciplina, assunto, dificuldade, tipo, enunciado FROM questoes ORDER BY id DESC', conn)
        conn.close()
        st.markdown("**🔍 Filtro**")
        if not df_todas.empty:
            col_f1, col_f2 = st.columns(2)
            disc_filtro = col_f1.selectbox("Filtrar por Disciplina:", ["Todas"] + list(df_todas['disciplina'].unique()), key="ed_filtro_disc")
            tipo_filtro = col_f2.selectbox("Filtrar por Tipo:", ["Todas"] + list(df_todas['tipo'].unique()), key="ed_filtro_tipo")

            df_filtrado = df_todas.copy()
            if disc_filtro != "Todas": df_filtrado = df_filtrado[df_filtrado['disciplina'] == disc_filtro]
            if tipo_filtro != "Todas": df_filtrado = df_filtrado[df_filtrado['tipo'] == tipo_filtro]

            opcoes_q = ["Escolha uma questão..."] + [f"ID {row['id']} | {row['disciplina']} | {row['assunto']} | {row['enunciado'][:50]}..." for _, row in df_filtrado.iterrows()]
            q_sel = st.selectbox("Selecione a questão para editar:", opcoes_q, key="ed_q_sel")
            
            
            if q_sel != "Escolha uma questão...":
                st.write("---")
                st.markdown("**⚙️ Configuração**")
                id_editar = int(q_sel.split(" | ")[0].replace("ID ", ""))
                conn = sqlite3.connect('banco_provas.db')
                c = conn.cursor()
                
                # --- MIGRATION DE SEGURANÇA: Cria a coluna nas questões antigas se ela não existir ---
                try: c.execute("ALTER TABLE questoes ADD COLUMN uso_quest TEXT DEFAULT 'Prova Oficial'")
                except: pass
                
                c.execute('SELECT disciplina, assunto, dificuldade, enunciado, imagem, pontos, tipo, gabarito_discursivo, espaco_resposta, espaco_linhas, gabarito_imagem, uso_quest FROM questoes WHERE id=?', (id_editar,))
                q_data = c.fetchone()
                
                if q_data:
                    q_disc, q_ass, q_dif, q_enun, q_img, q_pts, q_tipo, q_gab_disc, q_esp, q_esp_l, q_gab_img, q_uso = q_data

                    # --- 1. CONFIGURAÇÕES (LINHA COMPACTA) ---
                    c1, c2, c3, c_uso = st.columns([0.2, 0.25, 0.3, 0.25])
                    with c1: n_tipo = st.selectbox("Tipo", ["Múltipla Escolha", "Verdadeiro ou Falso", "Discursiva", "Numérica"], index=["Múltipla Escolha", "Verdadeiro ou Falso", "Discursiva", "Numérica"].index(q_tipo), key=f"ed_tipo_{id_editar}")
                    with c2: n_disc = st.selectbox("Disciplina", ["Termodinâmica", "Mecânica dos Fluidos", "TCC 1"], index=["Termodinâmica", "Mecânica dos Fluidos", "TCC 1"].index(q_disc) if q_disc in ["Termodinâmica", "Mecânica dos Fluidos", "TCC 1"] else 0, key=f"ed_disc_{id_editar}")
                    with c3: n_ass = st.text_input("Assunto", value=q_ass if q_ass else "", key=f"ed_ass_{id_editar}")
                    
                    lista_usos = ["Prova Oficial", "Lista de Treino", "Dojo / Sala"]
                    idx_uso = lista_usos.index(q_uso) if q_uso in lista_usos else 0
                    with c_uso: n_uso = st.selectbox("Uso da Questão", lista_usos, index=idx_uso, key=f"ed_uso_{id_editar}")

                    c4, c5, c6, c7 = st.columns([0.2, 0.15, 0.3, 0.35])
                    with c4: n_dif = st.selectbox("Dificuldade", ["Fácil", "Média", "Difícil"], index=["Fácil", "Média", "Difícil"].index(q_dif) if q_dif in ["Fácil", "Média", "Difícil"] else 1, key=f"ed_dif_{id_editar}")
                    with c5: n_pts = st.number_input("Pontos", min_value=0.1, value=float(q_pts), step=0.5, key=f"ed_pts_{id_editar}")
                    with c6: n_esp = st.selectbox("Espaço", ["Linhas", "Quadriculado", "Caixa Vazia", "Nenhum"], index=["Linhas", "Quadriculado", "Caixa Vazia", "Nenhum"].index(q_esp) if q_esp in ["Linhas", "Quadriculado", "Caixa Vazia", "Nenhum"] else 0, key=f"ed_esp_{id_editar}")
                    with c7: n_tam = st.number_input("Tamanho (cm)", min_value=1, value=int(q_esp_l), key=f"ed_tam_{id_editar}")
                    st.write("---")
                    # --- 2. ENUNCIADO (LAYOUT MAGNÉTICO + FÓRMULAS) ---
                    st.markdown("**💬 Enunciado**")
                    key_enun = f"ed_enun_input_{id_editar}"
                    if key_enun not in st.session_state: st.session_state[key_enun] = q_enun

                    # Declarando e usando as colunas desempacotadas
                    col_ed_1, col_ed_2, col_ed_3, _ = st.columns([0.15, 0.15, 0.15, 0.55])

                    with col_ed_1:
                        with st.popover("🖋️ Estilo", use_container_width=True):
                            ce = st.columns(2)
                            for idx, (l, cmd) in enumerate(estilo): ce[idx%2].button(l, key=f"ed_e_{id_editar}_{idx}", on_click=injetar_texto, args=(cmd, key_enun))
                    with col_ed_2:
                        with st.popover("🧮 f(x)", use_container_width=True):
                            tg, tm, tc, tf, tt = st.tabs(["αβγ", "Mat", "Cálc", "🌊", "🔥"])
                            with tg: 
                                cg_g = st.columns(4)
                                for i, (l, cmd) in enumerate(gregas): cg_g[i%4].button(l, key=f"ed_g_{id_editar}_{i}", on_click=injetar_direto, args=(cmd, key_enun))
                            with tm: 
                                cg_m = st.columns(3)
                                for i, (l, cmd) in enumerate(matematica): cg_m[i%3].button(l, key=f"ed_m_{id_editar}_{i}", on_click=injetar_direto, args=(cmd, key_enun))
                            with tc: 
                                cg_c = st.columns(3)
                                for i, (l, cmd) in enumerate(calculo): cg_c[i%3].button(l, key=f"ed_gc_{id_editar}_{i}", on_click=injetar_direto, args=(cmd, key_enun))
                            with tf: 
                                cg_f = st.columns(1)
                                for i, (l, cmd) in enumerate(fluidos): cg_f[0].button(l, key=f"ed_f_{id_editar}_{i}", on_click=injetar_direto, args=(cmd, key_enun))
                            with tt: 
                                cg_t = st.columns(1)
                                for i, (l, cmd) in enumerate(termo): cg_t[0].button(l, key=f"ed_t_{id_editar}_{i}", on_click=injetar_direto, args=(cmd, key_enun))
                    with col_ed_3:
                        with st.popover("🖼️ Imagem", use_container_width=True):
                            n_img_up = st.file_uploader("Trocar", type=["png", "jpg", "jpeg"], key=f"ed_up_enun_{id_editar}", label_visibility="collapsed")

                    n_enun_final = st.text_area("Enunciado", key=key_enun, height=150, label_visibility="collapsed")
                    
                    if q_img or n_img_up:
                        ci1, ci2 = st.columns(2)
                        if q_img: ci1.image(q_img, caption="🖼️ Atual", width=150)
                        if n_img_up: ci2.image(n_img_up, caption="🆕 Nova", width=150)
                    # --- 3. LÓGICA DE RESPOSTAS E GABARITOS PADRONIZADA ---
                    c.execute('SELECT texto, correta, imagem FROM alternativas WHERE questao_id = ? ORDER BY id', (id_editar,))
                    alts_q = c.fetchall(); alts_modificadas, alts_imagens_novas = [], {}
                    st.write("---")
                    
                    if n_tipo == "Múltipla Escolha":
                        st.markdown("**💡 Resposta (Alternativas)**")
                        n_opt_key = f"ed_n_opt_{id_editar}"
                        if n_opt_key not in st.session_state: st.session_state[n_opt_key] = max(len(alts_q), 4)
                        
                        cb1, cb2, _ = st.columns([0.12, 0.12, 0.76])
                        if cb1.button("➕ Linha", key=f"ed_add_alt_{id_editar}"): st.session_state[n_opt_key] += 1; st.rerun()
                        if cb2.button("➖ Linha", key=f"ed_rm_alt_{id_editar}") and st.session_state[n_opt_key] > 2: st.session_state[n_opt_key] -= 1; st.rerun()

                        for j in range(st.session_state[n_opt_key]):
                            with st.container(border=True):
                                c_chk, c_est, c_fx, c_img = st.columns([0.1, 0.25, 0.25, 0.25])
                                
                                corr_v = bool(alts_q[j][1]) if j < len(alts_q) else False
                                corr = c_chk.checkbox(letras[j], value=corr_v, key=f"ed_c_alt_{id_editar}_{j}")
                                
                                k_alt = f"ed_t_alt_v_{id_editar}_{j}"
                                if k_alt not in st.session_state: st.session_state[k_alt] = alts_q[j][0] if j < len(alts_q) else ""
                                
                                with c_est:
                                    with st.popover("🖋️ Estilo", use_container_width=True):
                                        c_b = st.columns(2)
                                        for idx, (l, cmd) in enumerate(estilo): 
                                            c_b[idx%2].button(l, key=f"ed_ae_{id_editar}_{j}_{idx}", on_click=injetar_texto, args=(cmd, k_alt))
                                
                                with c_fx:
                                    with st.popover("🧮 f(x)", use_container_width=True):
                                        tg, tm, tc, tf, tt = st.tabs(["αβγ", "Mat", "Cálc", "🌊", "🔥"])
                                        with tg:
                                            cb_g = st.columns(4)
                                            for idx, (l, cmd) in enumerate(gregas): cb_g[idx%4].button(l, key=f"ed_ag_{id_editar}_{j}_{idx}", on_click=injetar_direto, args=(cmd, k_alt))
                                        with tm:
                                            cb_m = st.columns(3)
                                            for idx, (l, cmd) in enumerate(matematica): cb_m[idx%3].button(l, key=f"ed_am_{id_editar}_{j}_{idx}", on_click=injetar_direto, args=(cmd, k_alt))
                                        with tc:
                                            cb_c = st.columns(3)
                                            for idx, (l, cmd) in enumerate(calculo): cb_c[idx%3].button(l, key=f"ed_ac_{id_editar}_{j}_{idx}", on_click=injetar_direto, args=(cmd, k_alt))
                                        with tf:
                                            cb_f = st.columns(1)
                                            for idx, (l, cmd) in enumerate(fluidos): cb_f[0].button(l, key=f"ed_af_{id_editar}_{j}_{idx}", on_click=injetar_direto, args=(cmd, k_alt))
                                        with tt:
                                            cb_t = st.columns(1)
                                            for idx, (l, cmd) in enumerate(termo): cb_t[0].button(l, key=f"ed_at_{id_editar}_{j}_{idx}", on_click=injetar_direto, args=(cmd, k_alt))

                                with c_img:
                                    with st.popover("🖼️ Imagem", use_container_width=True):
                                        up_ia = st.file_uploader("Trocar", type=["png", "jpg", "jpeg"], key=f"ed_ia_{id_editar}_{j}", label_visibility="collapsed")

                                txt_a = st.text_input("Texto", key=k_alt, label_visibility="collapsed")
                                if txt_a.strip(): st.markdown(f'<span style="color:#3498db;">↳</span> {gerar_preview_web(txt_a)}', unsafe_allow_html=True)
                                
                                if (j < len(alts_q) and alts_q[j][2]) or up_ia:
                                    cia = st.columns(2)
                                    if j < len(alts_q) and alts_q[j][2]: cia[0].image(alts_q[j][2], width=80, caption="Atual")
                                    if up_ia: cia[1].image(up_ia, width=80, caption="Nova")

                                alts_imagens_novas[j] = up_ia if up_ia else (alts_q[j][2] if j < len(alts_q) else None)
                                alts_modificadas.append((txt_a, corr))

                    elif n_tipo == "Verdadeiro ou Falso":
                        idx_banco = 0 if any(a[0] == "Verdadeiro" and a[1] for a in alts_q) else 1
                        st.markdown("**💡 Resposta**")
                        resp = st.radio("Gabarito:", ["Verdadeiro", "Falso"], index=idx_banco, horizontal=True, key=f"ed_vf_{id_editar}", label_visibility="collapsed")
                        alts_modificadas = [("Verdadeiro", resp == "Verdadeiro"), ("Falso", resp == "Falso")]

                    elif n_tipo == "Numérica":
                        st.markdown("**💡 Resposta Exata (Numérica)**")
                        val_atual = int(q_gab_disc) if str(q_gab_disc).isdigit() else 0
                        gab_num = st.number_input("Valor (0 a 99):", min_value=0, max_value=99, step=1, value=val_atual, key=f"ed_num_{id_editar}")
                        gab_d_final = str(gab_num).zfill(2)
                        
                        c_g1, c_gi = st.columns([0.85, 0.15])
                        with c_g1: st.info(f"O gabarito exato salvo será: **{gab_d_final}**")
                        with c_gi:
                            with st.popover("🖼️ Imagem", use_container_width=True):
                                n_img_g_up = st.file_uploader("Upload da Resolução", type=["png", "jpg", "jpeg"], key=f"ed_ig_num_{id_editar}", label_visibility="collapsed")
                        
                        if q_gab_img or locals().get('n_img_g_up'):
                            cg1, cg2 = st.columns(2)
                            if q_gab_img: cg1.image(q_gab_img, caption="Atual no Banco", width=150)
                            if locals().get('n_img_g_up'): cg2.image(n_img_g_up, caption="Nova Imagem", width=150)

                    elif n_tipo == "Discursiva":
                        st.markdown("**💡 Resolução Detalhada:**")
                        k_gab = f"ed_gab_input_{id_editar}"
                        if k_gab not in st.session_state: st.session_state[k_gab] = q_gab_disc if q_gab_disc else ""
                        
                        cge, cgf, cgi, _ = st.columns([0.15, 0.15, 0.15, 0.55])
                        with cge:
                            with st.popover("🖋️ Estilo", use_container_width=True):
                                c_gb = st.columns(2)
                                for i, (l, cmd) in enumerate(estilo): c_gb[i%2].button(l, key=f"ed_ge_{id_editar}_{i}", on_click=injetar_texto, args=(cmd, k_gab))
                        with cgf:
                            with st.popover("🧮 f(x)", use_container_width=True):
                                tg, tm, tc, tf, tt = st.tabs(["αβγ", "Mat", "Cálc", "🌊", "🔥"])
                                with tg: 
                                    cg_g = st.columns(4)
                                    for i, (l, cmd) in enumerate(gregas): cg_g[i%4].button(l, key=f"ed_gg_{id_editar}_{i}", on_click=injetar_direto, args=(cmd, k_gab))
                                with tm: 
                                    cg_m = st.columns(3)
                                    for i, (l, cmd) in enumerate(matematica): cg_m[i%3].button(l, key=f"ed_gm_{id_editar}_{i}", on_click=injetar_direto, args=(cmd, k_gab))
                                with tc: 
                                    cg_c = st.columns(3)
                                    for i, (l, cmd) in enumerate(calculo): cg_c[i%3].button(l, key=f"ed_gcalc_{id_editar}_{i}", on_click=injetar_direto, args=(cmd, k_gab))
                                with tf: 
                                    cg_f = st.columns(1)
                                    for i, (l, cmd) in enumerate(fluidos): cg_f[0].button(l, key=f"ed_gf_{id_editar}_{i}", on_click=injetar_direto, args=(cmd, k_gab))
                                with tt: 
                                    cg_t = st.columns(1)
                                    for i, (l, cmd) in enumerate(termo): cg_t[0].button(l, key=f"ed_gt_{id_editar}_{i}", on_click=injetar_direto, args=(cmd, k_gab))
                        with cgi:
                            with st.popover("🖼️ Imagem", use_container_width=True): 
                                n_img_g_up = st.file_uploader("Trocar Resolução", type=["png","jpg","jpeg"], key=f"ed_ig_disc_{id_editar}", label_visibility="collapsed")
                        
                        gab_d_final = st.text_area("Gabarito", key=k_gab, height=120, label_visibility="collapsed")
                        
                        if gab_d_final.strip(): st.markdown(f'<span style="color:#3498db;">↳</span> {gerar_preview_web(gab_d_final)}', unsafe_allow_html=True)
                            
                        if q_gab_img or locals().get('n_img_g_up'):
                            cg1, cg2 = st.columns(2)
                            if q_gab_img: cg1.image(q_gab_img, caption="Atual no Banco", width=150)
                            if locals().get('n_img_g_up'): cg2.image(n_img_g_up, caption="Nova", width=150)

                    
                    # --- 5. SALVAMENTO (MOTOR CORRIGIDO SEM ERRO DE SINTAXE) ---
                    st.write("---")
                    cb_s, cb_d, cb_e = st.columns([1, 1, 1])
                    
                    if cb_s.button("💾 Salvar Alterações", type="primary", use_container_width=True):
                        i_f = q_img
                        if n_img_up: 
                            i_f = sanitizar_nome(n_img_up.name)
                            with open(i_f, "wb") as f: f.write(n_img_up.getbuffer())
                        i_g_f = q_gab_img
                        if 'n_img_g_up' in locals() and n_img_g_up:
                            i_g_f = sanitizar_nome(n_img_g_up.name)
                            with open(i_g_f, "wb") as f: f.write(n_img_g_up.getbuffer())

                        val_gab = gab_d_final if 'gab_d_final' in locals() else q_gab_disc
                        c.execute('''UPDATE questoes SET disciplina=?, assunto=?, dificuldade=?, enunciado=?, pontos=?, espaco_resposta=?, espaco_linhas=?, tipo=?, imagem=?, gabarito_imagem=?, gabarito_discursivo=?, uso_quest=? WHERE id=?''', (n_disc, n_ass, n_dif, n_enun_final, n_pts, n_esp, n_tam, n_tipo, i_f, i_g_f, val_gab, n_uso, id_editar))
                        
                        if n_tipo in ["Múltipla Escolha", "Verdadeiro ou Falso"]:
                            c.execute('DELETE FROM alternativas WHERE questao_id = ?', (id_editar,))
                            for j, (t, co) in enumerate(alts_modificadas):
                                img_obj = alts_imagens_novas.get(j); img_bd = None
                                if hasattr(img_obj, 'getbuffer'):
                                    nome_f = sanitizar_nome(img_obj.name)
                                    with open(nome_f, "wb") as f: f.write(img_obj.getbuffer())
                                    img_bd = nome_f
                                else: img_bd = img_obj
                                c.execute('INSERT INTO alternativas (questao_id, texto, correta, imagem) VALUES (?, ?, ?, ?)', (id_editar, t, co, img_bd))
                        conn.commit(); st.success("✅ Tudo atualizado!"); st.rerun()

                    # O NOVO BOTÃO DE DUPLICAR AQUI:
                    if cb_d.button("💾 Salvar como Nova", use_container_width=True, help="Cria uma CÓPIA exata no banco (ideal para mudar valores)"):
                        i_f = q_img
                        if n_img_up: 
                            i_f = sanitizar_nome(n_img_up.name)
                            with open(i_f, "wb") as f: f.write(n_img_up.getbuffer())
                        i_g_f = q_gab_img
                        if 'n_img_g_up' in locals() and n_img_g_up:
                            i_g_f = sanitizar_nome(n_img_g_up.name)
                            with open(i_g_f, "wb") as f: f.write(n_img_g_up.getbuffer())
                            
                        val_gab = gab_d_final if 'gab_d_final' in locals() else q_gab_disc
                        
                        alts_para_inserir = []
                        if n_tipo in ["Múltipla Escolha", "Verdadeiro ou Falso"]:
                            for j, (t, co) in enumerate(alts_modificadas):
                                img_obj = alts_imagens_novas.get(j); img_bd = None
                                if hasattr(img_obj, 'getbuffer'):
                                    nome_f = sanitizar_nome(img_obj.name)
                                    with open(nome_f, "wb") as f: f.write(img_obj.getbuffer())
                                    img_bd = nome_f
                                else: img_bd = img_obj
                                alts_para_inserir.append((t, co, img_bd))
                        
                        # Injeta como uma QUESTÃO NOVA em vez de fazer Update
                        # Injeta como uma QUESTÃO NOVA em vez de fazer Update (agora com n_uso)
                        inserir_questao(n_disc, n_ass, n_dif, n_enun_final, alts_para_inserir, n_pts, n_tipo, val_gab, i_f, n_esp, n_tam, i_g_f, n_uso)
                        st.success("✅ Nova cópia salva no banco de dados!")
                        st.rerun()

                    if cb_e.button("🗑️ Excluir Permanente", use_container_width=True):
                        excluir_questao(id_editar); st.warning("Excluída!"); st.rerun()
                conn.close()
        else: st.info("O seu banco de questões ainda está vazio.")

    
    
    # --- SUB-ABA 1.3: GERAR PROVA (O SEU MOTOR DE PDF) ---
    with sub_gen:
        
        if "arquivos" not in st.session_state: st.session_state.arquivos = []
        if "prova_atual" not in st.session_state: st.session_state.prova_atual = []
        st.markdown("**📌1. Cabeçalho**")
        
        # Leve ajuste de segurança aqui para não dar erro na descompactação se o banco retornar vazio
        if "cabecalho_carregado" not in st.session_state:
            cfg = carregar_configuracoes()
            if cfg:
                st.session_state.inp_inst, st.session_state.inp_prof, st.session_state.inp_dep, st.session_state.inp_cur, st.session_state.inp_instruc = cfg
            else:
                st.session_state.inp_inst, st.session_state.inp_prof, st.session_state.inp_dep, st.session_state.inp_cur, st.session_state.inp_instruc = "", "", "", "", ""
            st.session_state.inp_turma, st.session_state.inp_data = "", ""
            st.session_state.cabecalho_carregado = True

        c_cab1, c_cab2 = st.columns(2)
        inst_nome = c_cab1.text_input("Instituição", key="inp_inst")
        prof_nome = c_cab2.text_input("Professor(a)", key="inp_prof")
        c_cab3, c_cab4, c_cab5 = st.columns(3)
        depto, curs, turma_p = c_cab3.text_input("Disciplina", key="inp_dep"), c_cab4.text_input("Curso", key="inp_cur"), c_cab5.text_input("Turma", key="inp_turma")
        c_cab6, c_cab7 = st.columns(2)
        data_p = c_cab6.text_input("Data", key="inp_data")
        titulo_doc = c_cab7.text_input("Título do Documento", value="Avaliação 01", key="inp_titulo")
        # --- A GRANDE NOVIDADE: O OBJETIVO DO DOCUMENTO ---
        tipo_doc_gen = st.radio("🎯 Objetivo do Documento:", ["Prova Oficial (Boletim)", "Atividade de Treino (Só Feedback)"], horizontal=True)
        logo_up = st.file_uploader("Logo da Instituição (PNG/JPG)", type=["png", "jpg", "jpeg"])
      
        instrucoes = st.text_area("Instruções", key="inp_instruc")
        
        # --- 🎮 SEUS BOTÕES DE CONTROLE DO CABEÇALHO ADICIONADOS AQUI ---
        cc1, cc2, cc3 = st.columns([0.4, 0.3, 0.3])
        if cc1.button("💾 Salvar como Padrão", use_container_width=True):
            salvar_configuracoes(inst_nome, prof_nome, depto, curs, instrucoes)
            st.success("✅ Cabeçalho salvo no banco de dados!")
            
        if cc2.button("🔄 Puxar do Banco", use_container_width=True):
            if "cabecalho_carregado" in st.session_state:
                del st.session_state["cabecalho_carregado"]
            st.rerun()
            
        if cc3.button("🧹 Limpar Campos", use_container_width=True):
            st.session_state.inp_inst = ""
            st.session_state.inp_prof = ""
            st.session_state.inp_dep = ""
            st.session_state.inp_cur = ""
            st.session_state.inp_instruc = ""
            st.rerun()
        
        st.write("---")

        st.markdown("**🆔 2. Identificação dos Alunos nas Provas**")
        
        modo_id = st.radio("Como deseja identificar as provas?", ["Em Branco (Sem Nome/RA)", "Usar Turma Cadastrada", "Upload Temporário de Lista"], horizontal=True)
        arquivo_lista = None
        alunos_selecionados_df = None
        q_a = 1

        if modo_id == "Em Branco (Sem Nome/RA)":
            st.info("🔔 O sistema gerará cópias genéricas (ex: Versão A-001, A-002).")
            q_a = st.number_input("Quantas provas deseja gerar?", min_value=1, max_value=300, value=30)
        elif modo_id == "Upload Temporário de Lista":
            arquivo_lista = st.file_uploader("Upload da Lista", type=['xlsx', 'csv'], key="up_lista_alunos")
        elif modo_id == "Usar Turma Cadastrada":
            conn = sqlite3.connect('banco_provas.db')
            turmas_db = pd.read_sql('SELECT * FROM turmas', conn)
            if not turmas_db.empty:
                t_escolhida = st.selectbox("Escolha a Turma:", turmas_db['nome'].tolist())
                id_t_escolhida = turmas_db[turmas_db['nome'] == t_escolhida]['id'].values[0]
                alunos_da_turma = pd.read_sql(f'SELECT nome as NOME, ra as RA FROM alunos WHERE turma_id = {id_t_escolhida}', conn)
                if not alunos_da_turma.empty:
                    opcoes_alunos = alunos_da_turma['NOME'].tolist()
                    selecao = st.multiselect("Selecione os alunos (vazio = turma toda):", opcoes_alunos)
                    if selecao: alunos_selecionados_df = alunos_da_turma[alunos_da_turma['NOME'].isin(selecao)]
                    else: alunos_selecionados_df = alunos_da_turma
                    st.success(f"{len(alunos_selecionados_df)} aluno(s) selecionado(s).")
                else: st.warning("Esta turma ainda não tem alunos cadastrados.")
            else: st.warning("Nenhuma turma cadastrada.")
            conn.close()
        st.write("---")
        st.markdown("**☑️ 3. Seleção de Questões**")
        col_p1, col_p2, col_p3 = st.columns(3) 
        d_p = col_p1.selectbox("Disciplina", ["Termodinâmica", "Mecânica dos Fluidos", "TCC 1"], key="g_disc")
        q_v = col_p2.number_input("Versões", 1, 10, 1)
        layout_colunas = col_p3.radio("Layout", ["1 Coluna", "2 Colunas"], horizontal=True)
        num_colunas = 2 if layout_colunas == "2 Colunas" else 1

        modo_selecao = st.radio("Modo", ["Sorteio Automático", "Escolha Manual"], horizontal=True)

        if modo_selecao == "Sorteio Automático":
            st.markdown("**🎰 Regras de Sorteio**")
            if "num_regras" not in st.session_state: st.session_state.num_regras = 1

            with st.container(border=True):
                c_h1, c_h2, c_h3, c_h4, c_h5 = st.columns([0.1, 0.25, 0.2, 0.2, 0.25])
                c_h1.markdown("**Qtd**")
                c_h2.markdown("**Assunto**")
                c_h3.markdown("**Dificuldade**")
                c_h4.markdown("**Tipo**")
                c_h5.markdown("**Objetivo**")

                regras = []
                for i in range(st.session_state.num_regras):
                    c1, c2, c3, c4, c5 = st.columns([0.1, 0.25, 0.2, 0.2, 0.25])
                    regras.append({
                        "qtd": c1.number_input(f"Qtd_{i}", 1, value=1, key=f"r_qtd_{i}", label_visibility="collapsed"), 
                        "assunto": c2.selectbox(f"Ass_{i}", obter_assuntos_da_disciplina(d_p), key=f"r_ass_{i}", label_visibility="collapsed"), 
                        "dificuldade": c3.selectbox(f"Dif_{i}", ["Todos", "Fácil", "Média", "Difícil"], key=f"r_dif_{i}", label_visibility="collapsed"), 
                        "tipo": c4.selectbox(f"Tip_{i}", ["Todos", "Múltipla", "V/F", "Discursiva", "Numérica"], key=f"r_tip_{i}", label_visibility="collapsed"),
                        "uso": c5.selectbox(f"Uso_{i}", ["Prova Oficial", "Lista de Treino", "Dojo / Sala", "Todos"], key=f"r_uso_{i}", label_visibility="collapsed")
                    })
                
                st.write("") 
                c_btn_r1, c_btn_r2, _ = st.columns([0.15, 0.15, 0.7])
                if c_btn_r1.button("➕ Regra", use_container_width=True): st.session_state.num_regras += 1; st.rerun()
                if c_btn_r2.button("➖ Regra", use_container_width=True) and st.session_state.num_regras > 1: st.session_state.num_regras -= 1; st.rerun()

            if st.button("🎲 Sortear Prova", type="primary", use_container_width=True):
                base, usados = [], []
                for r in regras:
                    tipo_mapeado = "Múltipla Escolha" if r['tipo'] == "Múltipla" else ("Verdadeiro ou Falso" if r['tipo'] == "V/F" else r['tipo'])
                    sorteadas = buscar_questoes_filtradas(d_p, r['qtd'], r['assunto'], r['dificuldade'], tipo_mapeado, True, usados, r['uso'])
                    base.extend(sorteadas)
                    usados.extend([q[0] for q in sorteadas])
                st.session_state.prova_atual = [{"id": q[0], "enunciado": q[1], "imagem": q[2], "pontos": q[3], "tipo": q[4], "gabarito": q[5], "espaco": q[6], "espaco_linhas": q[7], "dificuldade": q[8], "assunto": q[9], "gabarito_imagem": q[10]} for q in base]
                st.rerun()
        else:
            todas_q = buscar_questoes_filtradas(d_p)
            # A mágica aqui: o q[11] mostra a tag [Prova Oficial] ou [Lista de Treino] no menu dropdown!
            opcoes = {f"[{q[11]}] ID {q[0]} | {q[1][:50]}...": q for q in todas_q}
            
            sel = st.multiselect("Selecione as questões (Cuidado para não vazar questões de Prova Oficial em Listas!):", list(opcoes.keys()))
            if st.button("➕ Adicionar à Prova/Lista"):
                for n in sel:
                    q = opcoes[n]
                    if q[0] not in [x['id'] for x in st.session_state.prova_atual]:
                        st.session_state.prova_atual.append({"id": q[0], "enunciado": q[1], "imagem": q[2], "pontos": q[3], "tipo": q[4], "gabarito": q[5], "espaco": q[6], "espaco_linhas": q[7], "dificuldade": q[8], "assunto": q[9], "gabarito_imagem": q[10]})
                st.rerun()

        if st.session_state.prova_atual:
            st.write("---")
            st.markdown("**🎛️ 4. Ajustes Finos da Prova**")
            pontos_totais, remover = 0, []
            for i, q in enumerate(st.session_state.prova_atual):
                with st.expander(f"Q{i+1} | {q['tipo']} | ID: {q['id']}"):
                    
                    # --- 1. EDIÇÃO DO ENUNCIADO ---
                    st.markdown("**💬 Enunciado**")
                    key_enun_adj = f"adj_enun_{i}_{q['id']}"
                    if key_enun_adj not in st.session_state: st.session_state[key_enun_adj] = q['enunciado']
                    
                    col_adj_1, col_adj_2, col_adj_3, col_adj_4 = st.columns([0.15, 0.15, 0.15, 0.55])
                    with col_adj_1:
                            tg, tm, tc, tf, tt = st.tabs(["αβγ", "Mat", "Cálc", "🌊", "🔥"])
                            
                            with tg: 
                                cg = st.columns(4)
                                for k, (l, cmd) in enumerate(gregas): 
                                    cg[k%4].button(l, key=f"adj_g_{i}_{k}", on_click=injetar_direto, args=(cmd, key_enun_adj))
                            
                            with tm: 
                                cm = st.columns(3)
                                for k, (l, cmd) in enumerate(matematica): 
                                    cm[k%3].button(l, key=f"adj_m_{i}_{k}", on_click=injetar_direto, args=(cmd, key_enun_adj))
                            
                            with tc: 
                                cc = st.columns(3)
                                for k, (l, cmd) in enumerate(calculo): 
                                    cc[k%3].button(l, key=f"adj_c_{i}_{k}", on_click=injetar_direto, args=(cmd, key_enun_adj))
                            
                            with tf: 
                                cf = st.columns(1)
                                for k, (l, cmd) in enumerate(fluidos): 
                                    cf[0].button(l, key=f"adj_f_{i}_{k}", on_click=injetar_direto, args=(cmd, key_enun_adj))
                            
                            with tt: 
                                ct = st.columns(1)
                                for k, (l, cmd) in enumerate(termo): 
                                    ct[0].button(l, key=f"adj_t_{i}_{k}", on_click=injetar_direto, args=(cmd, key_enun_adj))
                    with col_adj_1:
                        with st.popover("🖼️ Imagem", use_container_width=True):
                            adj_img_up = st.file_uploader("Trocar", type=["png", "jpg", "jpeg"], key=f"adj_img_{i}_{q['id']}", label_visibility="collapsed")

                    novo_enun = st.text_area("Enunciado", key=key_enun_adj, height=100, label_visibility="collapsed")
                    st.session_state.prova_atual[i]['enunciado'] = novo_enun
                    
                    img_temp = q.get('imagem')
                    if adj_img_up:
                        img_temp = sanitizar_nome(f"temp_prova_{adj_img_up.name}")
                        with open(img_temp, "wb") as f: f.write(adj_img_up.getbuffer())
                        st.session_state.prova_atual[i]['imagem'] = img_temp
                    
                    if q.get('imagem') or adj_img_up:
                        ci1, ci2 = st.columns(2)
                        if q.get('imagem'): ci1.image(q['imagem'], caption="🖼️ Imagem Original", width=150)
                        if adj_img_up: ci2.image(adj_img_up, caption="🆕 Imagem para a Prova", width=150)

                    if novo_enun.strip():
                        st.markdown(f'<span style="color:#3498db;">↳</span> {gerar_preview_web(novo_enun)}', unsafe_allow_html=True)
                    
                    # --- 2. EDIÇÃO DO GABARITO E ALTERNATIVAS (PADRONIZADO) ---
                    novo_gab = q.get('gabarito', '')
                    img_gab_temp = q.get('gabarito_imagem') 
                    adj_ig_up = None 
                    
                    alts_modificadas_adj = [] 
                    alts_imagens_novas_adj = {}

                    if q['tipo'] == "Múltipla Escolha":
                        st.write("---")
                        st.markdown("**💡 Resposta (Alternativas)**")
                        st.caption("⚠️ Atenção: Edições nas alternativas SÓ vão para o PDF se você clicar em 'Atualizar no Banco' abaixo.")
                        
                        import sqlite3
                        with sqlite3.connect('banco_provas.db') as c_temp:
                            cursor_t = c_temp.cursor()
                            cursor_t.execute('SELECT texto, correta, imagem FROM alternativas WHERE questao_id = ? ORDER BY id', (q['id'],))
                            alts_q_adj = cursor_t.fetchall()
                            
                        n_opt_key_adj = f"adj_n_opt_{i}_{q['id']}"
                        if n_opt_key_adj not in st.session_state: st.session_state[n_opt_key_adj] = max(len(alts_q_adj), 4)
                        
                        cb1, cb2, _ = st.columns([0.12, 0.12, 0.76])
                        if cb1.button("➕ Linha", key=f"adj_add_alt_{i}"): st.session_state[n_opt_key_adj] += 1; st.rerun()
                        if cb2.button("➖ Linha", key=f"adj_rm_alt_{i}") and st.session_state[n_opt_key_adj] > 2: st.session_state[n_opt_key_adj] -= 1; st.rerun()

                        letras_adj = "ABCDEFGHIJ"
                        for j in range(st.session_state[n_opt_key_adj]):
                            with st.container(border=True):
                                c_chk, c_est, c_fx, c_img = st.columns([0.1, 0.25, 0.25, 0.25])
                                corr_v = bool(alts_q_adj[j][1]) if j < len(alts_q_adj) else False
                                corr = c_chk.checkbox(letras_adj[j], value=corr_v, key=f"adj_c_alt_{i}_{j}")
                                
                                k_alt = f"adj_t_alt_v_{i}_{j}"
                                if k_alt not in st.session_state: st.session_state[k_alt] = alts_q_adj[j][0] if j < len(alts_q_adj) else ""
                                
                                with c_est:
                                    with st.popover("🖋️ Estilo", use_container_width=True):
                                        c_b = st.columns(2)
                                        for idx, (l, cmd) in enumerate(estilo): c_b[idx%2].button(l, key=f"adj_ae_{i}_{j}_{idx}", on_click=injetar_texto, args=(cmd, k_alt))
                                with c_fx:
                                    with st.popover("🧮 f(x)", use_container_width=True):
                                        tg, tm, tc, tf, tt = st.tabs(["αβγ", "Mat", "Cálc", "🌊", "🔥"])
                                        with tg: 
                                            cg_g = st.columns(4)
                                            for idx, (l, cmd) in enumerate(gregas): cg_g[idx%4].button(l, key=f"adj_ag_{i}_{j}_{idx}", on_click=injetar_direto, args=(cmd, k_alt))
                                        with tm: 
                                            cg_m = st.columns(3)
                                            for idx, (l, cmd) in enumerate(matematica): cg_m[idx%3].button(l, key=f"adj_am_{i}_{j}_{idx}", on_click=injetar_direto, args=(cmd, k_alt))
                                        with tc: 
                                            cg_c = st.columns(3)
                                            for idx, (l, cmd) in enumerate(calculo): cg_c[idx%3].button(l, key=f"adj_ac_{i}_{j}_{idx}", on_click=injetar_direto, args=(cmd, k_alt))
                                        with tf: 
                                            cg_f = st.columns(1)
                                            for idx, (l, cmd) in enumerate(fluidos): cg_f[0].button(l, key=f"adj_af_{i}_{j}_{idx}", on_click=injetar_direto, args=(cmd, k_alt))
                                        with tt: 
                                            cg_t = st.columns(1)
                                            for idx, (l, cmd) in enumerate(termo): cg_t[0].button(l, key=f"adj_at_{i}_{j}_{idx}", on_click=injetar_direto, args=(cmd, k_alt))
                                        
                                with c_img:
                                    with st.popover("🖼️ Imagem", use_container_width=True):
                                        up_ia = st.file_uploader("Trocar", type=["png", "jpg", "jpeg"], key=f"adj_ia_{i}_{j}", label_visibility="collapsed")

                                txt_a = st.text_input("Texto", key=k_alt, label_visibility="collapsed")
                                if txt_a.strip(): st.markdown(f'<span style="color:#3498db;">↳</span> {gerar_preview_web(txt_a)}', unsafe_allow_html=True)
                                
                                if (j < len(alts_q_adj) and alts_q_adj[j][2]) or up_ia:
                                    cia = st.columns(2)
                                    if j < len(alts_q_adj) and alts_q_adj[j][2]: cia[0].image(alts_q_adj[j][2], width=80, caption="Atual")
                                    if up_ia: cia[1].image(up_ia, width=80, caption="Nova")

                                alts_imagens_novas_adj[j] = up_ia if up_ia else (alts_q_adj[j][2] if j < len(alts_q_adj) else None)
                                alts_modificadas_adj.append((txt_a, corr))

                    elif q['tipo'] == "Verdadeiro ou Falso":
                        import sqlite3
                        with sqlite3.connect('banco_provas.db') as c_temp:
                            cursor_t = c_temp.cursor()
                            cursor_t.execute('SELECT texto, correta, imagem FROM alternativas WHERE questao_id = ? ORDER BY id', (q['id'],))
                            alts_q_adj = cursor_t.fetchall()
                            
                        idx_banco = 0 if any(a[0] == "Verdadeiro" and a[1] for a in alts_q_adj) else 1
                        st.write("---")
                        st.markdown("**💡 Resposta (V/F)**")
                        st.caption("⚠️ Atenção: Alterações aqui SÓ vão para o PDF se você clicar em 'Atualizar no Banco'.")
                        resp = st.radio("Gabarito:", ["Verdadeiro", "Falso"], index=idx_banco, horizontal=True, key=f"adj_vf_{i}_{q['id']}", label_visibility="collapsed")
                        alts_modificadas_adj = [("Verdadeiro", resp == "Verdadeiro"), ("Falso", resp == "Falso")]

                    elif q['tipo'] == "Numérica":
                        st.write("---")
                        st.markdown("**💡 Resposta Exata (Numérica)**")
                        val_atual = int(novo_gab) if str(novo_gab).isdigit() else 0
                        novo_gab_num = st.number_input("Valor (0 a 99):", min_value=0, max_value=99, step=1, value=val_atual, key=f"adj_num_{i}_{q['id']}")
                        novo_gab = str(novo_gab_num).zfill(2)
                        st.session_state.prova_atual[i]['gabarito'] = novo_gab
                        
                        c_g1, c_gi = st.columns([0.85, 0.15])
                        with c_g1: st.info(f"O gabarito na prova será: **{novo_gab}**")
                        with c_gi:
                            with st.popover("🖼️ Imagem", use_container_width=True):
                                adj_ig_up = st.file_uploader("Upload", type=["png","jpg","jpeg"], key=f"adj_ig_num_{i}_{q['id']}", label_visibility="collapsed")
                                
                    elif q['tipo'] == "Discursiva":
                        st.write("---")
                        st.markdown("**💡 Resolução Detalhada:**")
                        key_gab_adj = f"adj_gab_{i}_{q['id']}"
                        if key_gab_adj not in st.session_state: st.session_state[key_gab_adj] = str(novo_gab)
                        
                        c_ge, c_gf, c_gi, _ = st.columns([0.15, 0.15, 0.15, 0.55])
                        with c_ge:
                            with st.popover("🖋️ Estilo", use_container_width=True):
                                c_gb = st.columns(2)
                                for k, (l, cmd) in enumerate(estilo): c_gb[k%2].button(l, key=f"adj_ge_{i}_{k}", on_click=injetar_texto, args=(cmd, key_gab_adj))
                        with c_gf:
                            with st.popover("🧮 f(x)", use_container_width=True):
                                tg, tm, tc, tf, tt = st.tabs(["αβγ", "Mat", "Cálc", "🌊", "🔥"])
                                with tg: 
                                    cg_g = st.columns(4)
                                    for k, (l, cmd) in enumerate(gregas): cg_g[k%4].button(l, key=f"adj_gg_{i}_{k}", on_click=injetar_direto, args=(cmd, key_gab_adj))
                                with tm: 
                                    cg_m = st.columns(3)
                                    for k, (l, cmd) in enumerate(matematica): cg_m[k%3].button(l, key=f"adj_gm_{i}_{k}", on_click=injetar_direto, args=(cmd, key_gab_adj))
                                with tc: 
                                    cg_c = st.columns(3)
                                    for k, (l, cmd) in enumerate(calculo): cg_c[k%3].button(l, key=f"adj_gc_{i}_{k}", on_click=injetar_direto, args=(cmd, key_gab_adj))
                                with tf: 
                                    c_f = st.columns(1)
                                    for k, (l, cmd) in enumerate(fluidos): c_f[0].button(l, key=f"adj_gf_{i}_{k}", on_click=injetar_direto, args=(cmd, key_gab_adj))
                                with tt: 
                                    c_t = st.columns(1)
                                    for k, (l, cmd) in enumerate(termo): c_t[0].button(l, key=f"adj_gt_{i}_{k}", on_click=injetar_direto, args=(cmd, key_gab_adj))
                        with c_gi:
                            with st.popover("🖼️ Imagem", use_container_width=True):
                                adj_ig_up = st.file_uploader("Upload", type=["png","jpg","jpeg"], key=f"adj_ig_disc_{i}_{q['id']}", label_visibility="collapsed")
                                
                        novo_gab_edit = st.text_area("Gabarito", key=key_gab_adj, height=120, label_visibility="collapsed")
                        st.session_state.prova_atual[i]['gabarito'] = novo_gab_edit
                        novo_gab = novo_gab_edit
                        
                        if novo_gab.strip(): st.markdown(f'<span style="color:#3498db;">↳</span> {gerar_preview_web(novo_gab)}', unsafe_allow_html=True)
                    
                    # Lógica de processamento de imagem compartilhada
                    if adj_ig_up:
                        img_gab_temp = sanitizar_nome(f"temp_gab_{adj_ig_up.name}")
                        with open(img_gab_temp, "wb") as f: f.write(adj_ig_up.getbuffer())
                        st.session_state.prova_atual[i]['gabarito_imagem'] = img_gab_temp
                        
                    if q['tipo'] in ["Discursiva", "Numérica"] and (q.get('gabarito_imagem') or adj_ig_up):
                        cg1, cg2 = st.columns(2)
                        if q.get('gabarito_imagem'): cg1.image(q['gabarito_imagem'], caption="Atual no Banco", width=150)
                        if adj_ig_up: cg2.image(adj_ig_up, caption="Nova", width=150)

                    st.write("---")

                    # --- 3. CONTROLES: NOTA, SALVAR NO BANCO E REMOVER ---
                    c_e1, c_e2, c_e_dup, c_e3 = st.columns([0.25, 0.25, 0.25, 0.25], vertical_alignment="bottom")
                    novo_pt = c_e1.number_input("Pontos", value=float(q['pontos']), step=0.5, key=f"prev_pt_gen_{i}")
                    
                    if c_e2.button("🆙 Atualizar", key=f"sv_banco_{i}_{q['id']}", use_container_width=True):
                        with sqlite3.connect('banco_provas.db') as conn_upd:
                            conn_upd.execute("UPDATE questoes SET enunciado=?, pontos=?, imagem=?, gabarito_imagem=?, gabarito_discursivo=? WHERE id=?", 
                                             (novo_enun, novo_pt, img_temp, img_gab_temp, novo_gab, q['id']))
                            
                            if q['tipo'] in ["Múltipla Escolha", "Verdadeiro ou Falso"]:
                                conn_upd.execute('DELETE FROM alternativas WHERE questao_id = ?', (q['id'],))
                                for j, (t, co) in enumerate(alts_modificadas_adj):
                                    img_obj = alts_imagens_novas_adj.get(j)
                                    img_bd = None
                                    if hasattr(img_obj, 'getbuffer'):
                                        nome_f = sanitizar_nome(img_obj.name)
                                        with open(nome_f, "wb") as f:
                                            f.write(img_obj.getbuffer())
                                        img_bd = nome_f
                                    else: img_bd = img_obj
                                    conn_upd.execute('INSERT INTO alternativas (questao_id, texto, correta, imagem) VALUES (?, ?, ?, ?)', (q['id'], t, co, img_bd))
                            
                            conn_upd.commit()
                        st.success(f"Questão atualizada no banco de dados!")

                    if c_e_dup.button("🧬 Clonar", key=f"dup_p_gen_{i}_{q['id']}", use_container_width=True, help="Duplica a questão aqui mesmo"):
                        import random
                        nova_q = q.copy() 
                        nova_q['id'] = f"{q['id']}_copy_{random.randint(1000,9999)}"
                        st.session_state.prova_atual.insert(i + 1, nova_q)
                        st.rerun()
                    
                    if c_e3.button("🗑️ Remover", key=f"rm_p_gen_{i}", use_container_width=True): 
                        remover.append(i)
                    
                    st.session_state.prova_atual[i]['pontos'] = novo_pt
                    pontos_totais += novo_pt
                    
                    

            if remover:
                for idx in sorted(remover, reverse=True): st.session_state.prova_atual.pop(idx)
                st.rerun()
            
            st.info(f"**Total de Pontos da Prova:** {pontos_totais}")
            st.write("---")
            col_emb1, col_emb2 = st.columns(2)
            opt_emb_q = col_emb1.checkbox("Embaralhar Ordem das Questões", value=True)
            opt_emb_a = col_emb2.checkbox("Embaralhar Alternativas", value=True)

            if st.button("✅ Confirmar e Gerar PDFs", type="primary", use_container_width=True):
                st.session_state.arquivos = {} 
                if modo_id == "Em Branco (Sem Nome/RA)":
                    df_alunos = pd.DataFrame({'NOME': ['__________________________'] * q_a, 'RA': ['__________'] * q_a})
                elif modo_id == "Usar Turma Cadastrada" and alunos_selecionados_df is not None:
                    df_alunos = alunos_selecionados_df
                elif modo_id == "Upload Temporário de Lista" and arquivo_lista is not None:
                    if arquivo_lista.name.endswith('.xlsx'): df_alunos = pd.read_excel(arquivo_lista)
                    else: df_alunos = pd.read_csv(arquivo_lista, sep=None, engine='python')
                    df_alunos.columns = df_alunos.columns.str.strip().str.upper()
                    colunas_lidas = df_alunos.columns.tolist()
                    sinonimos_nome = ['NOME', 'ALUNO', 'CANDIDATO', 'ESTUDANTE', 'NOME COMPLETO']
                    sinonimos_ra = ['RA', 'REGISTRO', 'MATRICULA', 'ID']
                    col_n = next((col for col in colunas_lidas if col in sinonimos_nome), None)
                    col_r = next((col for col in colunas_lidas if col in sinonimos_ra), None)
                    if not col_n or not col_r:
                        st.error("🚫 Erro na Planilha! Colunas NOME e RA não identificadas.")
                        st.stop()
                    df_alunos = df_alunos.rename(columns={col_n: 'NOME', col_r: 'RA'}).dropna(subset=['NOME', 'RA'])

                nome_logo = "logo.png"
                if logo_up is not None:
                    nome_logo = sanitizar_nome(logo_up.name)
                    with open(nome_logo, "wb") as f: f.write(logo_up.getbuffer())
                elif not os.path.exists("logo.png"):
                    cv2.imwrite("logo.png", np.zeros((100, 100, 3), dtype=np.uint8) + 255)

                pdfs_provas, pdfs_gabaritos = [], []

                for index, linha in df_alunos.iterrows():
                    aluno_nome = str(linha['NOME'])
                    aluno_ra = str(linha['RA']).replace('.0', '')
                    v_num = index % q_v 
                    let_v = "ABCDEFGHIJ"[v_num]
                    
                    if modo_id == "Em Branco (Sem Nome/RA)":
                        id_unico = f"{index+1:03d}" 
                        let_v = f"{let_v}-{id_unico}"
                        titulo_gabarito = f"Cópia {id_unico} (Prova em Branco)"
                    else:
                        titulo_gabarito = f"Aluno(a): {aluno_nome} (RA: {aluno_ra})"
                    
                    q_list = list(st.session_state.prova_atual)
                    if opt_emb_q: random.shuffle(q_list)
                        
                    d_pdf, qr_obj = [], {}
                    for idx, q_item in enumerate(q_list, 1):
                        en_s = escapar_latex(q_item['enunciado'])
                        img_q = q_item.get('imagem')
                        if img_q and not os.path.exists(img_q): img_q = None 
                        gab_txt = escapar_latex(str(q_item.get('gabarito', '')))
                        if gab_txt == "None": gab_txt = ""
                        gab_img = q_item.get('gabarito_imagem')
                        if gab_img and not os.path.exists(gab_img): gab_img = None
                        
                        # NOVO: O tipo da questão é salvo com segurança no dicionário d_pdf para ajudar o gabarito
                        
                        if q_item['tipo'] == "Múltipla Escolha":
                            if opt_emb_a: alts = buscar_e_embaralhar_alternativas(q_item['id'])
                            else: alts = buscar_alternativas_originais(q_item['id'])
                            l_c, t_alts = "", []
                            for ia, (txt, corr, img_alt) in enumerate(alts): 
                                if img_alt and not os.path.exists(img_alt): img_alt = None
                                t_alts.append({"texto": escapar_latex(txt), "imagem": img_alt, "correta": corr})
                                if corr: l_c = "ABCDE"[ia]
                            d_pdf.append({"enunciado": en_s, "imagem": img_q, "pontos": q_item['pontos'], "tipo": q_item['tipo'], "alternativas": t_alts, "espaco": q_item['espaco'], "espaco_linhas": q_item['espaco_linhas'], "resposta_esperada": gab_txt, "gabarito_imagem": gab_img})
                            qr_obj[idx] = f"{l_c}|{q_item['pontos']}|ME" # Na Múltipla Escolha
                        elif q_item['tipo'] == "Verdadeiro ou Falso":
                            alts = buscar_alternativas_originais(q_item['id']) 
                            l_c, t_alts = "", []
                            for ia, (txt, corr, img_alt) in enumerate(alts): 
                                if img_alt and not os.path.exists(img_alt): img_alt = None
                                t_alts.append({"texto": escapar_latex(txt), "imagem": img_alt, "correta": corr})
                                if corr: l_c = "V" if ia == 0 else "F" 
                            d_pdf.append({"enunciado": en_s, "imagem": img_q, "pontos": q_item['pontos'], "tipo": q_item['tipo'], "alternativas": t_alts, "espaco": q_item['espaco'], "espaco_linhas": q_item['espaco_linhas'], "resposta_esperada": gab_txt, "gabarito_imagem": gab_img})
                            qr_obj[idx] = f"{l_c}|{q_item['pontos']}|VF" # No Verdadeiro ou Falso
                        elif q_item['tipo'] == "Numérica":
                            d_pdf.append({"enunciado": en_s, "imagem": img_q, "pontos": q_item['pontos'], "tipo": q_item['tipo'], "alternativas": [], "espaco": q_item['espaco'], "espaco_linhas": q_item['espaco_linhas'], "resposta_esperada": gab_txt, "gabarito_imagem": gab_img})
                            qr_obj[idx] = f"{str(q_item['gabarito']).zfill(2)}|{q_item['pontos']}|NUM" # Na Numérica
                                
                        else:
                            d_pdf.append({"enunciado": en_s, "imagem": img_q, "pontos": q_item['pontos'], "tipo": q_item['tipo'], "alternativas": [], "espaco": q_item['espaco'], "espaco_linhas": q_item['espaco_linhas'], "resposta_esperada": gab_txt, "gabarito_imagem": gab_img})
                            qr_obj[idx] = "DISC|0.0|DISC" # Na Discursiva
                    
                    sufixo_arquivo = f"{sanitizar_nome(aluno_ra)}_{index}"
                    cod_secreto = f"0{v_num + 1}"
                    if modo_id == "Em Branco (Sem Nome/RA)": cod_secreto += f"-{id_unico}"
                    
                    tipo_salvar = "Treino" if "Treino" in tipo_doc_gen else "Oficial"
                    dados_qrcode = {"ra": aluno_ra, "nome": aluno_nome, "v": let_v, "gab": qr_obj, "d": d_p, "tp": tipo_salvar}
                    qr_fn = f"qr_{sufixo_arquivo}.png"
                    qrcode.make(json.dumps(dados_qrcode)).save(qr_fn)

                    cab = {
                        "titulo_documento": escapar_latex(titulo_doc), "logo_path": nome_logo, "instituicao": escapar_latex(inst_nome),
                        "professor_nome": escapar_latex(prof_nome), "disciplina_nome": escapar_latex(d_p), "data": escapar_latex(data_p),
                        "turma": escapar_latex(turma_p), "curso": escapar_latex(curs), "instrucoes_texto": escapar_latex(instrucoes),
                        "num_copias": 1, "qr_path": qr_fn, "versao_letra": let_v, "colunas": num_colunas,
                        "aluno_nome": escapar_latex(aluno_nome) if modo_id != "Em Branco (Sem Nome/RA)" else "",
                        "aluno_ra": aluno_ra if modo_id != "Em Branco (Sem Nome/RA)" else "",
                        "titulo_gabarito": escapar_latex(titulo_gabarito), "codigo_secreto": cod_secreto
                    }
                    env = configurar_jinja()
                    n_p = f"Prova_{sufixo_arquivo}"
                    with open(f"{n_p}.tex", 'w', encoding='utf-8') as f: f.write(env.get_template('template_profissional.tex').render(**cab, questoes=d_pdf))
                    if compilar_latex_mac(f"{n_p}.tex"): pdfs_provas.append(f"{n_p}.pdf")
                        
                    n_g = f"Gabarito_{sufixo_arquivo}"
                    with open(f"{n_g}.tex", 'w', encoding='utf-8') as f: f.write(env.get_template('template_gabarito.tex').render(**cab, questoes=d_pdf))
                    if compilar_latex_mac(f"{n_g}.tex"): pdfs_gabaritos.append(f"{n_g}.pdf")

                if pdfs_provas:
                    st.info("📦 Unificando provas...")
                    # Usamos 'empty' no pagestyle para não numerar o merge (as provas já têm sua numeração)
                    tex_merge_provas = "\\documentclass{article}\n\\usepackage[utf8]{inputenc}\n\\usepackage{pdfpages}\n\\begin{document}\n\\pagestyle{empty}\n"
                    for p in pdfs_provas: 
                        # 'fitpaper' ajusta o PDF final ao tamanho real da prova gerada
                        tex_merge_provas += f"\\includepdf[pages=-, fitpaper=true]{{{p}}}\n"
                    tex_merge_provas += "\\end{document}"
                    
                    with open("Lote_Provas_Turma.tex", 'w', encoding='utf-8') as f: f.write(tex_merge_provas)
                    if compilar_latex_mac("Lote_Provas_Turma.tex"): 
                        st.session_state.arquivos['provas'] = "Lote_Provas_Turma.pdf"

                if pdfs_gabaritos:
                    st.info("✅ Unificando gabaritos...")
                    # Configuramos o documento LaTeX para o merge
                    tex_merge_gabs = "\\documentclass{article}\n\\usepackage[utf8]{inputenc}\n\\usepackage{pdfpages}\n\\begin{document}\n\\pagestyle{empty}\n"
                    
                    for p in pdfs_gabaritos: 
                        # O 'fitpaper=true' garante que tabelas largas não sejam cortadas
                        tex_merge_gabs += f"\\includepdf[pages=-, fitpaper=true]{{{p}}}\n"
                    
                    tex_merge_gabs += "\\end{document}"
                    
                    # Guardamos o ficheiro .tex e compilamos
                    with open("Lote_Gabaritos_Turma.tex", 'w', encoding='utf-8') as f: 
                        f.write(tex_merge_gabs)
                    
                    if compilar_latex_mac("Lote_Gabaritos_Turma.tex"): 
                        st.session_state.arquivos['gabaritos'] = "Lote_Gabaritos_Turma.pdf"

                for p in pdfs_provas + pdfs_gabaritos:
                    if os.path.exists(p): os.remove(p)
                st.success("Processamento finalizado com sucesso!")
                limpar_arquivos_temporarios()

        if st.session_state.get("arquivos"):
            st.write("---")
            st.markdown("**📦 Arquivos Prontos**")
            c_dl1, c_dl2 = st.columns(2)
            arq_provas = st.session_state.arquivos.get('provas')
            if arq_provas and os.path.exists(arq_provas):
                with open(arq_provas, "rb") as pdf_file:
                    c_dl1.download_button(label="📥 Baixar Lote de PROVAS (Único PDF)", data=pdf_file, file_name=f"Provas_Turma_{datetime.now().strftime('%Y%m%d')}.pdf", type="primary", use_container_width=True, key="btn_dl_provas_mestre")
                    
            arq_gabs = st.session_state.arquivos.get('gabaritos')
            if arq_gabs and os.path.exists(arq_gabs):
                with open(arq_gabs, "rb") as pdf_file:
                    c_dl2.download_button(label="🗝️ Baixar Lote de GABARITOS (Único PDF)", data=pdf_file, file_name=f"Gabaritos_Turma_{datetime.now().strftime('%Y%m%d')}.pdf", use_container_width=True, key="btn_dl_gabs_mestre")
    
    # --- SUB-ABA 1.4: CORREÇÃO AUTOMÁTICA (O SEU MOTOR OPENCV) ---
    with sub_corr:
        
        with sqlite3.connect('banco_provas.db') as conn:
            st.markdown("**🔍 Filtro**")
            turmas_df = pd.read_sql("SELECT id, nome FROM turmas", conn)
            if turmas_df.empty:
                st.warning("⚠️ Cadastre uma turma na aba 'Semestres e Turmas' antes de começar.")
            else:
                c_sel1, c_sel2, c_sel3 = st.columns(3)
                t_corr_nome = c_sel1.selectbox("👥 Turma:", turmas_df['nome'].tolist(), key="t_corr_final")
                id_t_corr = turmas_df[turmas_df['nome'] == t_corr_nome]['id'].values[0]
                
                discs_plan = pd.read_sql(f"SELECT DISTINCT disciplina FROM planejamento_notas WHERE turma_id = {id_t_corr}", conn)
                lista_disc_corr = discs_plan['disciplina'].tolist() if not discs_plan.empty else ["Termodinâmica", "Mecânica dos Fluidos", "TCC 1"]
                d_corr_sel = c_sel2.selectbox("🏷️ Disciplina:", lista_disc_corr, key="d_corr_final")
                
                df_plan = pd.read_sql(f"SELECT nome_avaliacao FROM planejamento_notas WHERE turma_id = {int(id_t_corr)} AND disciplina = '{d_corr_sel}'", conn)
                lista_ativ_plan = df_plan['nome_avaliacao'].tolist() if not df_plan.empty else []
                if lista_ativ_plan: prova_final_nome = c_sel3.selectbox("📑 Selecione a Prova:", lista_ativ_plan, key="p_corr_plan")
                else:
                    st.info("Nada planejado para esta disciplina.")
                    prova_final_nome = c_sel3.text_input("🆔 Nome da Prova (Manual):", value="P1", key="p_corr_manual")

                st.write("---")
                st.markdown("**⚙️ Ajuste Fino da Leitura (Mira OpenCV)**")
                c_aj = st.columns(3) 
                off_x = c_aj[0].slider("Mira Horizontal", -500, 400, -47, key="g_x")
                off_y = c_aj[1].slider("Mira Vertical", -100, 150, 6, key="g_y")
                p_x = c_aj[2].slider("Espaço Bolinhas", 10, 80, 20, key="g_px")
                c_aj2 = st.columns(3)
                dist_num = c_aj2[0].slider("Pulo Unidade (Eng)", 5.0, 25.0, 10.20, step=0.1, key="g_dnum")
                anc_x_limite = c_aj2[1].slider("Busca Lateral (Âncora)", 50, 500, 350, key="g_anc_x")
                anc_y_topo = c_aj2[2].slider("Ignorar Topo (Âncora)", 0, 800, 269, key="g_anc_y")
                
                st.write("---")
                img_file = st.file_uploader("Envie o PDF ou Fotos das Provas", type=['png', 'jpg', 'jpeg', 'pdf'], key="up_vfinal")

                if img_file is not None:
                    imagens_para_processar = []
                    if img_file.name.lower().endswith('.pdf'):
                        import fitz
                        doc = fitz.open(stream=img_file.read(), filetype="pdf")
                        for page in doc:
                            pix = page.get_pixmap(dpi=200)
                            img_array = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.h, pix.w, pix.n)
                            img_array = cv2.cvtColor(img_array, cv2.COLOR_RGB2BGR) if pix.n >= 3 else cv2.cvtColor(img_array, cv2.COLOR_GRAY2BGR)
                            imagens_para_processar.append(img_array)
                    else:
                        bytes_data = np.asarray(bytearray(img_file.read()), dtype=np.uint8)
                        imagens_para_processar.append(cv2.imdecode(bytes_data, 1))

                    for idx_img, img_orig in enumerate(imagens_para_processar):
                        try:
                            img = recortar_e_alinhar_folha(img_orig) 
                            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
                            from pyzbar.pyzbar import decode as pyzbar_decode
                            dados_qr = None
                            roi_qr = gray[20:700, 20:600] 
                            for img_t in [roi_qr, cv2.resize(roi_qr, (0,0), fx=2, fy=2)]:
                                decoded = pyzbar_decode(img_t)
                                if decoded:
                                    try: dados_qr = json.loads(decoded[0].data.decode('utf-8')); break
                                    except: pass

                            if not dados_qr:
                                st.warning(f"⚠️ Pág {idx_img+1}: QR Code ilegível.")
                                alunos_db = pd.read_sql(f'SELECT nome, ra FROM alunos WHERE turma_id={id_t_corr}', conn)
                                lista_alunos = ["Escolha o aluno..."] + [f"{r['ra']} - {r['nome']}" for _, r in alunos_db.iterrows()]
                                aluno_sel = st.selectbox(f"Quem é o aluno da pág {idx_img+1}?", lista_alunos, key=f"sel_m_{idx_img}")
                                if aluno_sel != "Escolha o aluno...":
                                    if aluno_sel != "Escolha o aluno..." and " - " in aluno_sel:
                                        partes_aluno = aluno_sel.split(" - ")
                                        if len(partes_aluno) == 2:
                                            ra_m, nome_m = partes_aluno
                                            dados_qr = {"ra": ra_m, "nome": nome_m, "gab": {}, "v": "A", "d": d_corr_sel}
                                        else:
                                            st.error("Formato de aluno inválido no banco.")
                                            continue
                                    # Linha removida/corrigida para evitar o erro de unpack
                                else: continue

                            blur = cv2.GaussianBlur(gray, (5, 5), 0)

                            
                            _, thresh = cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
                            cnts, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
                            pontos_candidatos = []
                            for c in cnts:
                                (x, y, w, h) = cv2.boundingRect(c)
                                area = cv2.contourArea(c)
                                if 8 <= w <= 35 and 8 <= h <= 35 and area > 30:
                                    if 0 <= x < anc_x_limite and anc_y_topo < y < (img.shape[0] * 0.9):
                                        pontos_candidatos.append((int(x + w//2), int(y + h//2)))

                            if len(pontos_candidatos) < 2: 
                                st.error(f"❌ Pág {idx_img+1}: Marcadores não encontrados."); continue

                            contagem_x = {}
                            for px, py in pontos_candidatos:
                                fx = (px // 15) * 15
                                contagem_x[fx] = contagem_x.get(fx, 0) + 1
                            x_v = max(contagem_x, key=contagem_x.get)
                            p_finais = sorted([p for p in pontos_candidatos if abs(p[0] - x_v) < 20], key=lambda pt: pt[1])

                            ancoras_y, lista_x = [], []
                            for px, py in p_finais:
                                if not ancoras_y or abs(py - ancoras_y[-1]) > 25:
                                    ancoras_y.append(int(py)); lista_x.append(int(px))
                            x_ancora = int(np.mean(lista_x))

                            acertos_acumulados, resumos, overlay = 0.0, [], img.copy()
                            gab = dados_qr.get("gab", {})
                            if not gab:
                                for i, q in enumerate(st.session_state.get('prova_atual', [])):
                                    if q['tipo'] != "Discursiva": gab[str(i+1)] = f"{q['gabarito']}|{q['pontos']}"

                            idx_ancora = 0 # 🌟 CRIAMOS UM CONTADOR EXCLUSIVO PARA OS QUADRADINHOS
                            
                            for idx_q, (q_num, gab_val) in enumerate(sorted(gab.items(), key=lambda x: int(x[0]))):
                                
                                # 1. DESEMPACOTAMENTO BLINDADO (Aquele que sabe lidar com provas novas e antigas)
                                partes = str(gab_val).split("|")
                                if len(partes) == 3:
                                    certa_str, pts_q_str, tipo_q = partes
                                    pts_q = float(pts_q_str)
                                elif len(partes) == 2:
                                    certa_str, pts_q_str = partes
                                    pts_q = float(pts_q_str)
                                    tipo_q = "VF" if certa_str in ["V", "F"] else ("ME" if certa_str in ["A","B","C","D","E"] else "NUM")
                                else:
                                    certa_str, pts_q, tipo_q = "DISC", 0.0, "DISC"

                                if tipo_q == "DISC": continue # Ignora totalmente discursivas no OpenCV!

                                # 🌟 AGORA ELE USA O IDX_ANCORA (Só avança quando tem quadradinho)
                                y_base = ancoras_y[idx_ancora] if idx_ancora < len(ancoras_y) else ancoras_y[-1] + (38 * (idx_ancora - len(ancoras_y) + 1))
                                y_l, x_s = y_base - 12 + off_y, x_ancora + 65 + off_x
                                t_box = 24
                                
                                if tipo_q == "NUM": 
                                    x_u = int(x_s + (dist_num * p_x))
                                    def ler_col(x_ini):
                                        cores = [cv2.countNonZero(thresh[y_l:y_l+t_box, (x_ini+j*p_x):(x_ini+j*p_x)+t_box]) for j in range(10)]
                                        return int(np.argmax(cores)), max(cores)
                                    m_d, val_d = ler_col(x_s)
                                    m_u, val_u = ler_col(x_u)
                                    lido = f"{m_d}{m_u}" if val_d > 45 and val_u > 45 else "Branco"
                                    cv2.circle(overlay, (x_s+(m_d*p_x)+12, y_l+12), 10, (0,255,0), -1)
                                    cv2.circle(overlay, (x_u+(m_u*p_x)+12, y_l+12), 10, (0,255,0), -1)
                                else: 
                                    qtd_b = 2 if tipo_q == "VF" else 5
                                    letras_p = "VF" if tipo_q == "VF" else "ABCDE"
                                    cores = [cv2.countNonZero(thresh[y_l:y_l+t_box, (x_s+j*p_x):(x_s+j*p_x)+t_box]) for j in range(qtd_b)]
                                    idx_max = int(np.argmax(cores))
                                    lido = letras_p[idx_max] if cores[idx_max] > 45 else "Branco"
                                    cv2.circle(overlay, (x_s+(idx_max*p_x)+12, y_l+12), 10, (0,255,0), -1)

                                if lido == certa_str: acertos_acumulados += pts_q
                                resumos.append({"Q": q_num, "Gabarito": certa_str, "Lido": lido, "OK": "✅" if lido == certa_str else "❌"})
                                
                                idx_ancora += 1 # 🌟 SÓ PULA DE QUADRADINHO SE LEU UMA QUESTÃO OBJETIVA!

                            st.image(cv2.addWeighted(overlay, 0.4, img, 0.6, 0), caption=f"🎯 Processada: {dados_qr['nome']}")
                            df_check = pd.DataFrame(resumos)
                            st.table(df_check.set_index("Q"))

                            c_n1, c_n2 = st.columns(2)
                            n_disc = c_n1.number_input(f"Nota Questões Abertas ({dados_qr['nome']}):", 0.0, 10.0, 0.0, 0.5, key=f"nd_{idx_img}")
                            nota_final_lote = acertos_acumulados + n_disc
                            
                            tipo_lido = dados_qr.get("tp", "Oficial")
                            
                            if "Treino" in tipo_lido:
                                c_n2.markdown(f"### 🏋️ TREINO: `{nota_final_lote:.2f}` pts")
                            else:
                                c_n2.markdown(f"### 🏆 TOTAL: `{nota_final_lote:.2f}`")

                            if st.button(f"💾 Confirmar e Salvar: {dados_qr['nome']}", key=f"sv_{idx_img}", type="primary"):
                                
                                # 1. SALVA A NOTA NA PLANILHA OFICIAL (Sempre lança a nota no alvo selecionado)
                                conn.execute("DELETE FROM notas_flexiveis WHERE turma_id=? AND disciplina=? AND matricula=? AND avaliacao=?", (int(id_t_corr), d_corr_sel, dados_qr['ra'], prova_final_nome))
                                conn.execute("INSERT INTO notas_flexiveis (turma_id, disciplina, matricula, avaliacao, nota) VALUES (?,?,?,?,?)", (int(id_t_corr), d_corr_sel, dados_qr['ra'], prova_final_nome, float(nota_final_lote)))
                                conn.commit()
                                
                                st.toast(f"✅ Nota enviada para a Planilha ({prova_final_nome})!")
                                
                                # 2. SALVA O FEEDBACK NO PORTAL DO ALUNO
                                for r in resumos:
                                    status_q = "Correta" if r['OK'] == "✅" else "Incorreta"
                                    msg = f"Parabéns! Você acertou a questão {r['Q']}. Gabarito: {r['Gabarito']}." if status_q == "Correta" else f"Na questão {r['Q']}, a resposta lida foi {r['Lido']}, mas o esperado era {r['Gabarito']}."
                                    salvar_feedback_detalhado(dados_qr['ra'], d_corr_sel, prova_final_nome, r['Q'], status_q, msg)
                                
                                st.success(f"Tudo pronto para o aluno {dados_qr['nome']}!")
                                st.rerun()
                                for r in resumos:
                                    status_q = "Correta" if r['OK'] == "✅" else "Incorreta"
                                    
                                    # Mensagem personalizada conforme o tipo de erro
                                    if status_q == "Correta":
                                        msg = f"Parabéns! Você acertou a questão {r['Q']}. Gabarito: {r['Gabarito']}."
                                    else:
                                        msg = f"Na questão {r['Q']}, a resposta lida foi {r['Lido']}, mas o esperado era {r['Gabarito']}."
                                    
                                    salvar_feedback_detalhado(
                                        dados_qr['ra'], 
                                        d_corr_sel, 
                                        prova_final_nome, 
                                        r['Q'], 
                                        status_q, 
                                        msg
                                    )
                                
                                
                                st.rerun() # Opcional: recarrega a página para limpar a fila
                                
                        except Exception as e: st.error(f"Erro na pág {idx_img+1}: {e}")

with aba_fabrica:
    
    
    with sqlite3.connect('banco_provas.db') as conn:
        st.markdown("**✅ Selecione ou Crie um Molde de Disciplina**")
        disciplinas_salvas = pd.read_sql("SELECT DISTINCT titulo_modelo FROM modelos_ensino", conn)['titulo_modelo'].dropna().tolist()
        
        c_d1, c_d2 = st.columns([0.6, 0.4])
        disc_selecionada = c_d1.selectbox("Modelos Salvos:", ["-- Criar Novo Molde --"] + disciplinas_salvas, key="f_sel_mestre_vFinal")
        nome_disc = c_d2.text_input("Nome da Disciplina:", value="" if disc_selecionada == "-- Criar Novo Molde --" else disc_selecionada)

        if nome_disc:
            t_ensino, t_aula = st.tabs(["📄 1. Plano de Ensino Oficial", "🧭 2. Plano de Aulas"])

            with t_ensino:
                # Restauração total do Plano Mestre
                d_m = pd.read_sql(f"SELECT * FROM modelos_ensino WHERE titulo_modelo='{nome_disc}'", conn)
                def get_v(f): return d_m[f].iloc[0] if not d_m.empty and f in d_m.columns else ""
                with st.form("form_plano_mestre_completo"):
                    ementa = st.text_area("📖 Ementa:", value=get_v('ementa'), height=100)
                    c1, c2 = st.columns(2)
                    obj_g = c1.text_area("🏁 Objetivos Gerais:", value=get_v('objetivos_gerais'))
                    comp = c2.text_area("🏅 Competências e Habilidades:", value=get_v('competencias'))
                    egr = st.text_area("🎓 Perfil do Egresso:", value=get_v('egresso'))
                    prog = st.text_area("📁 Conteúdo Programático:", value=get_v('conteudo_programatico'))
                    c3, c4 = st.columns(2)
                    meto = c3.text_area("♟️ Metodologia de Ensino:", value=get_v('metodologia'))
                    recu = c4.text_area("🪄 Recursos Didáticos:", value=get_v('recursos'))
                    c5, c6 = st.columns(2)
                    aval = c5.text_area("📈 Sistema de Avaliação:", value=get_v('avaliacao'))
                    aps_mestre = c6.text_area("🏠 Atividades Práticas (APS):", value=get_v('aps'))
                    bib_b = st.text_area("📚 Referência Básica:", value=get_v('bib_basica'))
                    bib_c = st.text_area("📚 Referência Complementar:", value=get_v('bib_complementar'))
                    orf_f = st.text_area("📚 Outras Referências:", value=get_v('outras_ref'))
                    if st.form_submit_button("💾 Salvar Plano de Ensino Mestre", type="primary"):
                        conn.execute("DELETE FROM modelos_ensino WHERE titulo_modelo=?", (nome_disc,))
                        conn.execute("INSERT INTO modelos_ensino (titulo_modelo, ementa, objetivos_gerais, competencias, egresso, conteudo_programatico, metodologia, recursos, avaliacao, aps, bib_basica, bib_complementar, outras_ref) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", (nome_disc, ementa, obj_g, comp, egr, prog, meto, recu, aval, aps_mestre, bib_b, bib_c, orf_f))
                        conn.commit(); st.rerun()

            with t_aula:
                st.markdown("**🧭 Plano de aulas**")
                df_aulas = pd.read_sql(f"SELECT num_aula as Aula, tema as Tema FROM roteiro_mestre WHERE titulo_modelo='{nome_disc}' ORDER BY num_aula", conn)
                ed_aulas = st.data_editor(df_aulas, num_rows="dynamic", use_container_width=True, key=f"ed_roteiro_vFinal_{nome_disc}")
                if st.button("🆙 Atualizar Lista de Aulas"):
                    for _, r in ed_aulas.iterrows():
                        check = conn.execute("SELECT id FROM roteiro_mestre WHERE titulo_modelo=? AND num_aula=?", (nome_disc, r['Aula'])).fetchone()
                        if not check: conn.execute("INSERT INTO roteiro_mestre (titulo_modelo, num_aula, tema) VALUES (?,?,?)", (nome_disc, r['Aula'], r['Tema']))
                    conn.commit(); st.rerun()

                st.write("---")
                a_det = st.selectbox("Selecione a aula para detalhar o Roteiro :", df_aulas['Aula'].tolist() if not df_aulas.empty else [])
                if a_det:
                    d_a = pd.read_sql(f"SELECT * FROM roteiro_mestre WHERE titulo_modelo='{nome_disc}' AND num_aula={a_det}", conn).iloc[0]
                    with st.form(f"f_det_fab_vFinal_{a_det}"):
                        c_tp1, c_tp2 = st.columns([0.7, 0.3])
                        tema_f = c_tp1.text_input("Tema Principal:", value=d_a.get('tema') or "")
                        tipo_f = c_tp2.selectbox("Tipo:", ["Teórica", "Prática", "Laboratório", "Avaliação"], index=0)
                        
                        obj_f = st.text_area("Objetivos de Aprendizagem:", value=d_a.get('objetivos_aula') or "")
                        cont_f = st.text_area("Conteúdo:", value=d_a.get('conteudo_detalhado') or "", height=150)
                        
                        c_ped1, c_ped2 = st.columns(2)
                        meto_f = c_ped1.text_area("Metodologia de ensino:", value=d_a.get('metodologia') or "")
                        aps_f = c_ped2.text_area("Atividades práticas supervisionadas (APS):", value=d_a.get('aps_aula') or "")
                        
                        
                        cl1, cl2, cl3 = st.columns(3)
                        l_slides = cl1.text_input("📂 Slides:", value=d_a.get('link_slides') or "")
                        l_over = cl2.text_input("🔗 Link Overleaf:", value=d_a.get('link_overleaf') or "")
                        l_ext = cl3.text_input("🌐 Links Extras:", value=d_a.get('link_extras') or "")

                        st.write("---")
                        c_at1, c_at2 = st.columns([0.6, 0.4])
                        ativ_f = c_at1.text_area("Texto Atividade:", value=d_a.get('atividades') or "")
                        ativ_l = c_at2.text_input("Link Material Atividade:", value=d_a.get('atividades_link') or "")
                        
                        c_fo1, c_fo2 = st.columns([0.6, 0.4])
                        for_f = c_fo1.text_area("Texto Fórum:", value=d_a.get('forum') or "")
                        for_l = c_fo2.text_input("Link Material Fórum:", value=d_a.get('forum_link') or "")
                        
                        ref_f = st.text_area("Referências da aula:", value=d_a.get('referencias_aula') or "")

                        if st.form_submit_button("💾 Salvar Roteiro Mestre"):
                            conn.execute("""UPDATE roteiro_mestre SET tema=?, tipo_aula=?, objetivos_aula=?, conteudo_detalhado=?, metodologia=?, 
                                            aps_aula=?, referencias_aula=?, link_slides=?, link_overleaf=?, link_extras=?, atividades=?, atividades_link=?, forum=?, forum_link=? 
                                            WHERE titulo_modelo=? AND num_aula=?""", 
                                         (tema_f, tipo_f, obj_f, cont_f, meto_f, aps_f, ref_f, l_slides, l_over, l_ext, ativ_f, ativ_l, for_f, for_l, nome_disc, a_det))
                            conn.commit(); st.success("Molde global atualizado!"); st.rerun()
# =========================================================================
# PILAR 3: SEMESTRES E TURMAS (A OPERAÇÃO REAL + BOLETIM)
# =========================================================================
with aba_turmas:
    with sqlite3.connect('banco_provas.db') as conn:
        # --- 0. PREPARAÇÃO DE DATAS ---
        semestres_existentes = pd.read_sql("SELECT DISTINCT semestre FROM turmas", conn)['semestre'].dropna().tolist()
        if "2026.1" not in semestres_existentes: semestres_existentes.append("2026.1")
        sem_recente = sorted(semestres_existentes, reverse=True)[0]

        

        # --- 1. SISTEMA DE 3 ABAS (Substitui o Expander e os filtros soltos) ---
        t_operar, t_criar, t_importar = st.tabs(["🔍 Operar Turma", "➕ Criar Nova Turma", "📥 Importar Alunos"])

        # Inicializamos variáveis de controle
        id_t_ativa, d_ativa, t_ativa = None, None, None

        # --- ABA 1: OPERAR (AQUI FICAM OS SEUS FILTROS ORIGINAIS) ---
        with t_operar:
            c_f1, c_f2, c_f3 = st.columns(3)
            with c_f1:
                st.markdown("🌓 **Por Semestre**")
                semestre_ativo = st.selectbox("Selecione o Semestre Letivo:", sorted(semestres_existentes, reverse=True), label_visibility="collapsed", key="filt_sem_vFinal")
            
            t_db_ativa = pd.read_sql(f"SELECT * FROM turmas WHERE semestre='{semestre_ativo}'", conn)
            
            if not t_db_ativa.empty:
                with c_f2:
                    st.markdown("👥 **Turma:**")
                    t_ativa = st.selectbox("Escolha a Turma:", t_db_ativa['nome'].tolist(), label_visibility="collapsed", key="filt_t_vFinal")
                    id_t_ativa = t_db_ativa[t_db_ativa['nome'] == t_ativa]['id'].values[0]
                
                modelos_disponiveis = pd.read_sql("SELECT DISTINCT titulo_modelo FROM modelos_ensino", conn)['titulo_modelo'].dropna().tolist()
                with c_f3:
                    st.markdown("🏷️ **Disciplina:**")
                    if modelos_disponiveis:
                        d_ativa = st.selectbox("Disciplina cursada:", modelos_disponiveis, label_visibility="collapsed", key="filt_d_vFinal")
                    else:
                        st.warning("Crie um Molde na Fábrica.")
            else:
                st.info(f"Nenhuma turma em {semestre_ativo}")

        # --- ABA 2: CRIAR NOVA TURMA ---
        with t_criar:
            st.write("**Criar Turma**")
            col_c1, col_c2 = st.columns(2)
            n_t = col_c1.text_input("Nome da Turma:", placeholder="Ex: Engenharia Civil A", key="cad_n_t_vF")
            n_sem = col_c2.text_input("Semestre:", value=sem_recente, key="cad_s_t_vF")
            if st.button("🚀 Criar Turma", use_container_width=True):
                if n_t:
                    conn.execute('INSERT INTO turmas (nome, semestre) VALUES (?, ?)', (n_t, n_sem))
                    conn.commit(); st.success("Turma criada!"); st.rerun()

        # --- ABA 3: IMPORTAR ALUNOS ---
        with t_importar:
            st.markdown("**📥 Importar Lista (Excel/CSV)**")
            t_db_todas = pd.read_sql("SELECT * FROM turmas ORDER BY semestre DESC, nome ASC", conn)
            if not t_db_todas.empty:
                opcoes_turmas = [f"[{r['semestre']}] {r['nome']}" for _, r in t_db_todas.iterrows()]
                t_up_sel = st.selectbox("Turma de Destino:", opcoes_turmas, key="imp_t_dest_vF")
                arq = st.file_uploader("Arquivo (NOME e RA):", type=['xlsx', 'csv'], key="imp_t_arq_vF")
                if st.button("Iniciar Importação", use_container_width=True) and arq:
                    df = pd.read_excel(arq) if arq.name.endswith('.xlsx') else pd.read_csv(arq, sep=None, engine='python')
                    df.columns = df.columns.str.strip().str.upper()
                    c_n = next((c for c in df.columns if c in ['NOME', 'ALUNO']), None)
                    c_r = next((c for c in df.columns if c in ['RA', 'MATRICULA']), None)
                    if c_n and c_r:
                        nome_turma_pura = t_up_sel.split("] ", 1)[1]
                        id_up = t_db_todas[t_db_todas['nome'] == nome_turma_pura]['id'].values[0]
                        for _, row in df.dropna(subset=[c_n, c_r]).iterrows():
                            ra_limpo = str(row[c_r]).replace('.0', '').strip()
                            conn.execute('INSERT OR IGNORE INTO alunos (turma_id, nome, ra) VALUES (?, ?, ?)', (int(id_up), str(row[c_n]).strip(), ra_limpo))
                        conn.commit(); st.success("Importação concluída!"); st.rerun()

        # --- 2. ÁREA DE TRABALHO (Sub-Abas Pedagógicas) ---
        # Só aparece se Turma e Disciplina estiverem selecionadas na Aba "Operar"
        if id_t_ativa and d_ativa:
                st.write("---")
                sub_mat, sub_cron, sub_pesos, sub_boletim = st.tabs([
                    "🎓 1. Matrículas", "🗓️ 2. Plano de aulas", "⚖️ 3. Pesos de Notas", "🏆 4. Boletim Mestre"
                ])
                
                with sub_mat:
                    st.markdown(f"**Quais alunos de {t_ativa} farão {d_ativa}?**")
                    # Busca todos os alunos da base daquela turma
                    alunos_turma_base = pd.read_sql(f"SELECT id, nome, ra, email, observacoes FROM alunos WHERE turma_id={id_t_ativa} ORDER BY nome", conn)
                    
                    if alunos_turma_base.empty:
                        st.info("Importe a lista de alunos da turma no menu superior de 'Importação'.")
                    else:
                        # 1. GERENCIAMENTO DE MATRÍCULA
                        matriculados = pd.read_sql(f"SELECT aluno_id FROM matriculas_disciplina WHERE turma_id={id_t_ativa} AND disciplina='{d_ativa}'", conn)['aluno_id'].tolist()
                        alunos_dict = dict(zip(alunos_turma_base['nome'], alunos_turma_base['id']))
                        nomes_pre_selecionados = [nome for nome, id_al in alunos_dict.items() if id_al in matriculados]
                        
                        selecionados = st.multiselect("Selecione os matriculados nesta disciplina:", options=alunos_turma_base['nome'].tolist(), default=nomes_pre_selecionados if matriculados else alunos_turma_base['nome'].tolist())
                        
                        if st.button("💾 Salvar Matrículas da Disciplina"):
                            conn.execute("DELETE FROM matriculas_disciplina WHERE turma_id=? AND disciplina=?", (int(id_t_ativa), d_ativa))
                            for nome in selecionados:
                                conn.execute("INSERT INTO matriculas_disciplina (turma_id, disciplina, aluno_id) VALUES (?,?,?)", (int(id_t_ativa), d_ativa, int(alunos_dict[nome])))
                            conn.commit()
                            st.success(f"Matrículas de {d_ativa} atualizadas!")
                            st.rerun()

                        st.write("---")
                        
                        # 2. LISTA DE ALUNOS E EDIÇÃO DE ANOTAÇÕES (NOVO LAYOUT)
                        st.markdown("**🆔 Lista de Alunos e Anotações Pedagógicas**")
                        st.caption("Dica: Edite o Nome, E-mail ou as Anotações direto na tabela. O RA é bloqueado para segurança.")
                        
                        # Busca os dados reais dos alunos matriculados para edição
                        df_edit_lista = pd.read_sql(f"""
                            SELECT a.id, a.ra as RA, a.nome as Nome, a.email as E_mail, a.observacoes as [Anotações Pedagógicas]
                            FROM alunos a 
                            JOIN matriculas_disciplina m ON a.id = m.aluno_id 
                            WHERE m.turma_id={id_t_ativa} AND m.disciplina='{d_ativa}' 
                            ORDER BY a.nome
                        """, conn)

                        if not df_edit_lista.empty:
                            # Tabela Editável estilo Excel
                            df_resultado_edicao = st.data_editor(
                                df_edit_lista,
                                column_config={
                                    "id": None, # Esconde o ID interno
                                    "RA": st.column_config.TextColumn("RA", disabled=True), 
                                    "Nome": st.column_config.TextColumn("Nome do Aluno", width="medium"),
                                    "E_mail": st.column_config.TextColumn("E-mail"),
                                    "Anotações Pedagógicas": st.column_config.TextColumn("Notas (TDAH, Liderança, etc.)", width="large")
                                },
                                hide_index=True,
                                use_container_width=True,
                                key=f"editor_alunos_{id_t_ativa}_{d_ativa}"
                            )
                            
                            # Botão de salvamento em lote
                            if st.button("💾 Salvar Alterações na Lista", type="primary", use_container_width=True):
                                with sqlite3.connect('banco_provas.db') as c:
                                    for _, row in df_resultado_edicao.iterrows():
                                        c.execute("UPDATE alunos SET nome=?, email=?, observacoes=? WHERE id=?", 
                                                 (row['Nome'], row['E_mail'], row['Anotações Pedagógicas'], int(row['id'])))
                                st.success("Informações da lista de alunos atualizadas com sucesso!")
                                st.rerun()
                        else:
                            st.warning("Matricule os alunos primeiro para gerenciar as anotações.")
                st.write("---")
                with sub_cron:
                    import holidays
                    
                    # AS ABAS LADO A LADO EXATAMENTE COM SEUS NOMES
                    aba_planejador, aba_plano_real = st.tabs(["🔀 Planejador de Aulas", "🧭 Plano de aula real"])
                    
                    with aba_planejador:
                        # --- PASSO 1: CALENDÁRIO E DATAS FIXAS ---
                        with st.container(border=True):
                            st.markdown("**📅 Passo 1: Calendário e Provas**")
                            c1, c2, c3 = st.columns([0.3, 0.3, 0.4])
                            d_ini = c1.date_input("Início do Semestre:", datetime.today(), key="cr_ini_vFinal")
                            d_fim = c2.date_input("Fim do Semestre:", datetime.today() + timedelta(days=130), key="cr_fim_vFinal")
                            c_fer = c3.selectbox("📍 Cidade:", ["Nenhum", "Americana", "Campinas"], key="cr_city_vFinal")
                            
                            mapa_dias = {"Segunda":0, "Terça":1, "Quarta":2, "Quinta":3, "Sexta":4, "Sábado":5}
                            dias_w = st.multiselect("Dias com aula:", list(mapa_dias.keys()), default=["Segunda"], key="cr_dias_vFinal")
                            
                            st.write("**📍 Agendar Eventos Fixos (N1, N2, N3, AR):**")
                            if "df_fixas_vFinal" not in st.session_state:
                                st.session_state.df_fixas_vFinal = pd.DataFrame([{"Data": d_ini + timedelta(days=60), "Evento": "Prova N1"}, {"Data": d_ini + timedelta(days=110), "Evento": "Prova N2"}])
                            
                            ed_fixas = st.data_editor(st.session_state.df_fixas_vFinal, num_rows="dynamic", use_container_width=True, key="ed_fixas_vFinal",
                                                    column_config={"Data": st.column_config.DateColumn("Data", format="DD/MM/YYYY")})
                            
                            num_aulas_meta = st.number_input("Meta total de aulas:", min_value=1, value=20, key="meta_vFinal")
                            
                            anos = list(set([d_ini.year, d_fim.year]))
                            f_base = holidays.Brazil(subdiv='SP', years=anos)
                            f_per = {d: n for d, n in f_base.items() if d_ini <= d <= d_fim}
                            sel_f = st.multiselect("Pular feriados:", options=list(f_per.keys()), format_func=lambda x: f"{x.strftime('%d/%m/%Y')} - {f_per[x]}", default=list(f_per.keys()), key="sel_f_vFinal")
                            d_ext = st.text_input("Exceções (Bloqueios):", placeholder="Ex: 22/04/2026", key="ext_vFinal")

                            if st.button("📅 Gerar Grade de Datas Disponíveis", use_container_width=True):
                                dict_fixas = {row['Data']: row['Evento'] for _, row in ed_fixas.iterrows() if row['Data'] is not None}
                                idx_aulas = [mapa_dias[d] for d in dias_w]
                                datas_v = []
                                curr = d_ini
                                bloqueio_manual = [d.strip() for d in d_ext.split(",") if d.strip()]
                                
                                while curr <= d_fim and len(datas_v) < num_aulas_meta:
                                    ds_str = curr.strftime("%d/%m/%Y")
                                    if curr in sel_f or ds_str in bloqueio_manual:
                                        curr += timedelta(days=1); continue
                                    if curr.weekday() in idx_aulas:
                                        evento_fixo = dict_fixas.get(curr, "")
                                        datas_v.append({
                                            "data": ds_str, "num_aula": len(datas_v)+1, 
                                            "tema_origem": evento_fixo if evento_fixo else "-- Selecionar Conteúdo --",
                                            "tipo_aula": "Avaliação" if evento_fixo else "Teórica"
                                        })
                                    curr += timedelta(days=1)
                                st.session_state[f"temp_cron_{id_t_ativa}"] = datas_v; st.rerun()

                            # --- PASSO 2 DENTRO DA CAIXA ---
                            key_temp = f"temp_cron_{id_t_ativa}"
                            if key_temp in st.session_state:
                                st.write("") 
                                
                                df_fab = pd.read_sql(f"SELECT num_aula, tema FROM roteiro_mestre WHERE titulo_modelo='{d_ativa}' ORDER BY num_aula", conn)
                                dict_fab = {f"Aula {row['num_aula']}: {row['tema']}": row['num_aula'] for _, row in df_fab.iterrows()}
                                opcoes_fab = ["-- Selecionar --", "Aula Extra / Revisão", "Prova N1", "Prova N2", "Prova N3", "Exame AR"] + list(dict_fab.keys())

                                c_p2_1, c_p2_2, c_p2_3 = st.columns([0.4, 0.35, 0.25], vertical_alignment="bottom")
                                
                                # Seu texto original sem ###
                                c_p2_1.markdown("**📏 Passo 2: Distribuir Conteúdo**")
                                
                                if c_p2_2.button("⚡ Preenchimento Sequencial", use_container_width=True):
                                    ponteiro = 0
                                    for i, _ in enumerate(st.session_state[key_temp]):
                                        if any(x in st.session_state[key_temp][i]['tema_origem'] for x in ["Prova", "Exame", "AR"]): continue
                                        if ponteiro < len(df_fab):
                                            st.session_state[key_temp][i]['tema_origem'] = f"Aula {df_fab.iloc[ponteiro]['num_aula']}: {df_fab.iloc[ponteiro]['tema']}"
                                            ponteiro += 1
                                    st.rerun()

                                if c_p2_3.button("🗑️ Reiniciar Grade", use_container_width=True, help="Apaga o rascunho acima para gerar novas datas"):
                                    del st.session_state[key_temp]
                                    st.rerun()

                                for idx, aula in enumerate(st.session_state[key_temp]):
                                    with st.container(border=True):
                                        c_d, c_s = st.columns([0.3, 0.7])
                                        cor = "red" if any(x in aula['tema_origem'] for x in ["Prova", "Exame", "AR"]) else "blue"
                                        c_d.markdown(f"<b style='color:{cor};'>Aula {aula['num_aula']} ({aula['data']})</b>", unsafe_allow_html=True)
                                        st.session_state[key_temp][idx]['tema_origem'] = c_s.selectbox(f"Conteúdo para {aula['data']}:", options=opcoes_fab, 
                                                                                        index=opcoes_fab.index(aula['tema_origem']) if aula['tema_origem'] in opcoes_fab else 0,
                                                                                        key=f"mapeador_vFinal_{idx}")

                                if st.button("💾 CONSOLIDAR E SALVAR CRONOGRAMA", type="primary", use_container_width=True):
                                    conn.execute("DELETE FROM cronograma_detalhado WHERE turma_id=? AND disciplina=?", (int(id_t_ativa), d_ativa))
                                    for r in st.session_state[key_temp]:
                                        if r['tema_origem'] in dict_fab:
                                            d_f = pd.read_sql(f"SELECT * FROM roteiro_mestre WHERE titulo_modelo='{d_ativa}' AND num_aula={dict_fab[r['tema_origem']]}", conn).iloc[0].to_dict()
                                            dfinal = {k: (v if v is not None else "") for k, v in d_f.items()}
                                        else:
                                            dfinal = {k: "" for k in ["tema", "tipo_aula", "objetivos_aula", "conteudo_detalhado", "metodologia", "aps_aula", "referencias_aula", "link_slides", "link_overleaf", "link_extras", "atividades", "atividades_link", "forum", "forum_link"]}
                                            dfinal['tema'] = r['tema_origem']; dfinal['tipo_aula'] = "Avaliação" if "Prova" in r['tema_origem'] else "Teórica"

                                        conn.execute("""INSERT INTO cronograma_detalhado (turma_id, disciplina, num_aula, data, tema, tipo_aula, objetivos_aula, conteudo_detalhado, metodologia, aps_aula, referencias_aula, link_slides, link_overleaf, link_extras, atividades, atividades_link, forum, forum_link) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", 
                                                     (int(id_t_ativa), d_ativa, r['num_aula'], r['data'], dfinal['tema'], dfinal['tipo_aula'], dfinal['objetivos_aula'], dfinal['conteudo_detalhado'], dfinal['metodologia'], dfinal['aps_aula'], dfinal['referencias_aula'], dfinal['link_slides'], dfinal['link_overleaf'], dfinal['link_extras'], dfinal['atividades'], dfinal['atividades_link'], dfinal['forum'], dfinal['forum_link']))
                                    conn.commit(); st.success("Cronograma salvo!"); del st.session_state[key_temp]; st.rerun()

                    with aba_plano_real:
                        # --- PASSO 3: PLANO DE AULA REAL ---
                        # Seu texto original
                        
                        df_master = pd.read_sql(f"SELECT c.*, d.conteudo_real FROM cronograma_detalhado c LEFT JOIN diario_conteudo d ON c.turma_id = d.turma_id AND c.disciplina = d.disciplina AND c.data = d.data WHERE c.turma_id={id_t_ativa} AND c.disciplina='{d_ativa}' ORDER BY c.num_aula", conn)
                        
                        if not df_master.empty:
                            for idx, row in df_master.iterrows():
                                st_icon = "✅" if pd.notna(row['conteudo_real']) else "📅"
                                with st.expander(f"{st_icon} Aula {row['num_aula']} ({row['data']}) - {row['tema']}"):
                                    col_p, col_f = st.columns([0.65, 0.35])
                                    with col_p:
                                        st.markdown("**📝 Edição do Planejamento:**")
                                        c_p1, c_p2 = st.columns([0.7, 0.3])
                                        n_t = c_p1.text_input("Tema:", value=row['tema'], key=f"v_t_{idx}_vF")
                                        lista_tp = ["Teórica", "Prática", "Laboratório", "Avaliação"]
                                        t_at = row['tipo_aula'] if row['tipo_aula'] in lista_tp else "Teórica"
                                        n_tp = c_p2.selectbox("Tipo:", lista_tp, index=lista_tp.index(t_at), key=f"v_tp_{idx}_vF")
                                        
                                        n_obj = st.text_area("Objetivos:", value=row['objetivos_aula'] or "", key=f"v_o_{idx}_vF", height=70)
                                        n_cont = st.text_area("Conteúdo:", value=row['conteudo_detalhado'] or "", key=f"v_c_{idx}_vF", height=100)
                                        
                                        cp1, cp2 = st.columns(2)
                                        n_m = cp1.text_area("Metodologia de ensino:", value=row['metodologia'] or "", key=f"v_m_{idx}_vF")
                                        n_a = cp2.text_area("Atividades práticas supervisionadas (APS):", value=row['aps_aula'] or "", key=f"v_aps_{idx}_vF")
                                        
                                        
                                        b1, b2, b3 = st.columns(3)
                                        # SEM OS EMOJIS INVENTADOS!
                                        n_ls = b1.text_input("Link Slides:", value=row['link_slides'] or "", key=f"v_ls_{idx}_vF")
                                        n_lo = b2.text_input("Link Overleaf:", value=row['link_overleaf'] or "", key=f"v_lo_{idx}_vF")
                                        n_le = b3.text_input("Extras:", value=row['link_extras'] or "", key=f"v_le_{idx}_vF")
                                        
                                        cb1, cb2, cb3 = st.columns(3)
                                        if n_ls: cb1.link_button("📂 Abrir Slides", n_ls, use_container_width=True)
                                        if n_lo: cb2.link_button("🔗 Abrir Overleaf", n_lo, use_container_width=True, type="primary")
                                        if n_le: cb3.link_button("🌐 Link Extra", n_le, use_container_width=True)

                                        
                                        ca1, ca2 = st.columns([0.6, 0.4])
                                        n_at_t = ca1.text_area("Texto Atividade:", value=row['atividades'] or "", key=f"v_at_{idx}_vF")
                                        n_at_l = ca2.text_input("Link Material Ativ.:", value=row['atividades_link'] or "", key=f"v_al_{idx}_vF")
                                        if n_at_l: st.link_button("🚀 Ver Atividade", n_at_l)
                                        
                                        cf1, cf2 = st.columns([0.6, 0.4])
                                        n_ft_t = cf1.text_area("Texto Fórum:", value=row['forum'] or "", key=f"v_ft_{idx}_vF")
                                        n_ft_l = cf2.text_input("Link Material Fórum:", value=row['forum_link'] or "", key=f"v_fl_{idx}_vF")
                                        if n_ft_l: st.link_button("🚀 Ver Fórum", n_ft_l)

                                        n_ref = st.text_input("Referências:", value=row['referencias_aula'] or "", key=f"v_r_{idx}_vF")

                                    with col_f:
                                        st.markdown("**📖 Diário Real:**")
                                        if pd.notna(row['conteudo_real']): st.success(row['conteudo_real'])
                                        else: st.info("Aguardando registro.")
                                    c_btn1, c_btn2, c_btn3 = st.columns([0.4, 0.4, 0.2])
                                    sync = c_btn1.checkbox("🔄 Sincronizar na FÁBRICA", key=f"sy_{idx}_vF")
                                    if c_btn2.button(f"💾 Salvar Aula {row['num_aula']}", key=f"bs_{idx}_vF", type="primary"):
                                        conn.execute("UPDATE cronograma_detalhado SET tema=?, tipo_aula=?, objetivos_aula=?, conteudo_detalhado=?, metodologia=?, aps_aula=?, link_slides=?, link_overleaf=?, link_extras=?, atividades=?, atividades_link=?, forum=?, forum_link=?, referencias_aula=? WHERE id=?", (n_t, n_tp, n_obj, n_cont, n_m, n_a, n_ls, n_lo, n_le, n_at_t, n_at_l, n_ft_t, n_ft_l, n_ref, row['id']))
                                        if sync: conn.execute("UPDATE roteiro_mestre SET tema=?, tipo_aula=?, objetivos_aula=?, conteudo_detalhado=?, metodologia=?, aps_aula=?, link_slides=?, link_overleaf=?, link_extras=?, atividades=?, atividades_link=?, forum=?, forum_link=?, referencias_aula=? WHERE titulo_modelo=? AND num_aula=?", (n_t, n_tp, n_obj, n_cont, n_m, n_a, n_ls, n_lo, n_le, n_at_t, n_at_l, n_ft_t, n_ft_l, n_ref, d_ativa, row['num_aula']))
                                        conn.commit(); st.toast("Salvo!"); st.rerun()
                                    if c_btn3.button("🗑️ Deletar", key=f"bd_{idx}_vF"):
                                        conn.execute("DELETE FROM cronograma_detalhado WHERE id=?", (row['id'],)); conn.commit(); st.rerun()
                                st.write("---")
                                
                        else:
                            st.info("Utilize a aba 'Planejador de Datas' para mapear as aulas primeiro.")

                
                
                # =========================================================================
                # ✏️ 3. AVALIAÇÕES E LANÇAMENTO DE NOTAS (O CLÁSSICO COM EXTRAS)
                # =========================================================================
                with sub_pesos:
                    # --- 0. PREPARAÇÃO DE DADOS ---
                    df_ativ_sala = pd.read_sql(f"SELECT data, aluno_ra as Matrícula, entregou FROM atividades_sala WHERE turma_id={id_t_ativa} AND disciplina='{d_ativa}' ORDER BY data", conn)
                    datas_unicas = df_ativ_sala['data'].unique() if not df_ativ_sala.empty else []
                    qtd_aulas_registradas = len(datas_unicas)

                    st.markdown("**📊 Central Dinâmica de Notas e Médias**")

                    # --- 1. AS 4 ABAS LADO A LADO ---
                    t_manual, t_excel, t_auto, t_config = st.tabs([
                        "✍️ Planilha de Notas", 
                        "📊 Importar Notas", 
                        "🦾 Corretor Automático", 
                        "⚙️ Ajustar Pesos e Quantidades"
                    ])

                    # --- ABA 4: CONFIGURAÇÕES (AS CAIXAS CLÁSSICAS + EXTRAS) ---
                    with t_config:
                        st.info(f"⚡ Atualmente existem {qtd_aulas_registradas} aulas registradas no Dojo. Dica: Se uma categoria não existir no seu plano (ex: Lab), basta zerar a quantidade e o peso.")
                        
                        col_cfg1, col_cfg2 = st.columns(2)
                        with col_cfg1:
                            with st.container(border=True):
                                st.markdown("**📝 Provas Oficiais**")
                                n_p = st.text_input("Nome:", "Prova N", key="n_p")
                                q_p = st.number_input("Quantidade:", 0, 10, 2, key="q_p")
                                w_p = st.number_input("Peso Final (%):", 0, 100, 60, key="w_p")
                                c_p = st.number_input("Descartar Piores (%):", 0, 99, 0, step=5, key="corte_p")
                        with col_cfg2:
                            with st.container(border=True):
                                st.markdown("**📋 Listas / Exercícios**")
                                n_l = st.text_input("Nome:", "Lista", key="n_l")
                                q_l = st.number_input("Quantidade:", 0, 20, 3, key="q_l")
                                w_l = st.number_input("Peso Final (%):", 0, 100, 10, key="w_l")
                                c_l = st.number_input("Descartar Piores (%):", 0, 99, 0, step=5, key="corte_l")
                        
                        col_cfg3, col_cfg4 = st.columns(2)
                        with col_cfg3:
                            with st.container(border=True):
                                st.markdown("**🔬 Laboratório / Prática**")
                                n_lb = st.text_input("Nome:", "Lab", key="n_lb")
                                q_lb = st.number_input("Quantidade:", 0, 20, 2, key="q_lb")
                                w_lb = st.number_input("Peso Final (%):", 0, 100, 20, key="w_lb")
                                c_lb = st.number_input("Descartar Piores (%):", 0, 99, 0, step=5, key="corte_lb")
                        with col_cfg4:
                            with st.container(border=True):
                                st.markdown("**🥋 Ativ. em Sala (Dojo)**")
                                n_a = st.text_input("Prefixo:", "Ativ", key="n_a")
                                st.markdown("<br>", unsafe_allow_html=True) # Alinhamento sutil para manter simetria
                                w_a = st.number_input("Peso Final (%):", 0, 100, 10, key="w_a")
                                c_a = st.number_input("Descartar Piores (%):", 0, 99, 25, step=5, key="corte_a")

                        st.write("---")
                        st.markdown("### ➕ Categorias Extras")
                        st.caption("Crie atividades adicionais com o mesmo padrão de qualidade (Ex: Seminário, Projeto Integrador, ou Provas com pesos únicos).")
                        
                        if "num_extras" not in st.session_state: st.session_state.num_extras = 0
                        
                        # BOTOÕES CORRIGIDOS: Largura igualitária (50% / 50%) para não amassar o texto!
                        c_add, c_rm = st.columns(2)
                        if c_add.button("➕ Adicionar Categoria Extra", use_container_width=True): st.session_state.num_extras += 1; st.rerun()
                        if c_rm.button("➖ Remover Categoria Extra", use_container_width=True) and st.session_state.num_extras > 0: st.session_state.num_extras -= 1; st.rerun()
                        
                        extras_list = []
                        if st.session_state.num_extras > 0:
                            cols_ex = st.columns(2)
                            for i in range(st.session_state.num_extras):
                                with cols_ex[i % 2]:
                                    with st.container(border=True):
                                        st.markdown(f"**📌 Extra {i+1}**")
                                        ex_n = st.text_input("Nome:", f"Atividade Extra {i+1}", key=f"ex_n_{i}")
                                        ex_q = st.number_input("Quantidade:", 0, 20, 1, key=f"ex_q_{i}")
                                        ex_w = st.number_input("Peso Final (%):", 0, 100, 10, key=f"ex_w_{i}")
                                        ex_c = st.number_input("Descartar Piores (%):", 0, 99, 0, step=5, key=f"ex_c_{i}")
                                        if ex_n.strip():
                                            extras_list.append((ex_n.strip(), ex_q, ex_w, ex_c))

                        st.write("---")
                        soma_total = w_p + w_l + w_lb + w_a + sum([e[2] for e in extras_list])
                        cor_soma = "green" if abs(soma_total - 100.0) < 0.1 else "red"
                        st.markdown(f"**Soma Total dos Pesos:** <span style='color:{cor_soma}; font-size:18px;'>{soma_total:.1f}%</span>", unsafe_allow_html=True)

                        if st.button("🔄 Aplicar e Recalcular Médias", type="primary", use_container_width=True):
                            if abs(soma_total - 100.0) > 0.1:
                                st.error(f"⚠️ A soma dos pesos deve fechar em exatamente 100%. Atual: {soma_total:.1f}%.")
                            else:
                                cols_provas = [f"{n_p} {i+1}" for i in range(int(q_p))] if q_p > 0 and w_p > 0 else []
                                cols_listas = [f"{n_l} {i+1}" for i in range(int(q_l))] if q_l > 0 and w_l > 0 else []
                                cols_lab    = [f"{n_lb} {i+1}" for i in range(int(q_lb))] if q_lb > 0 and w_lb > 0 else []
                                bloco_ativ  = f"{n_a} (Dojo)"
                                
                                id_turma_seguro = int(id_t_ativa)

                                conn.execute("DELETE FROM planejamento_notas WHERE turma_id=? AND disciplina=?", (id_turma_seguro, d_ativa))

                                for nome in cols_provas: conn.execute("INSERT INTO planejamento_notas (turma_id, disciplina, nome_avaliacao, peso) VALUES (?,?,?,?)", (id_turma_seguro, d_ativa, nome, float(w_p) / max(1, int(q_p))))
                                for nome in cols_listas: conn.execute("INSERT INTO planejamento_notas (turma_id, disciplina, nome_avaliacao, peso) VALUES (?,?,?,?)", (id_turma_seguro, d_ativa, nome, float(w_l) / max(1, int(q_l))))
                                for nome in cols_lab: conn.execute("INSERT INTO planejamento_notas (turma_id, disciplina, nome_avaliacao, peso) VALUES (?,?,?,?)", (id_turma_seguro, d_ativa, nome, float(w_lb) / max(1, int(q_lb))))
                                
                                if w_a > 0: conn.execute("INSERT INTO planejamento_notas (turma_id, disciplina, nome_avaliacao, peso) VALUES (?,?,?,?)", (id_turma_seguro, d_ativa, bloco_ativ, float(w_a)))
                                
                                for ex_n, ex_q, ex_w, ex_c in extras_list:
                                    if ex_q > 0 and ex_w > 0:
                                        cols_extras_temp = [f"{ex_n} {j+1}" for j in range(int(ex_q))]
                                        for nome in cols_extras_temp:
                                            conn.execute("INSERT INTO planejamento_notas (turma_id, disciplina, nome_avaliacao, peso) VALUES (?,?,?,?)", (id_turma_seguro, d_ativa, nome, float(ex_w) / max(1, int(ex_q))))

                                conn.commit()
                                st.success("✅ Planejamento salvo! Colunas geradas na Planilha e no Boletim Mestre.")
                                st.rerun()

                    # --- 2. LÓGICA DE DEFINIÇÃO DE COLUNAS ---
                    cols_provas = [f"{n_p}{i+1}" if n_p.endswith(" ") else f"{n_p} {i+1}" for i in range(int(q_p))] if q_p > 0 and w_p > 0 else []
                    cols_listas = [f"{n_l} {i+1}" for i in range(int(q_l))] if q_l > 0 and w_l > 0 else []
                    cols_labs   = [f"{n_lb} {i+1}" for i in range(int(q_lb))] if q_lb > 0 and w_lb > 0 else []
                    cols_ativs  = [f"{n_a} {i+1} ({dt[:5]})" for i, dt in enumerate(datas_unicas)] if w_a > 0 else []
                    
                    cols_extras_todas = []
                    for ex_n, ex_q, ex_w, ex_c in extras_list:
                        if ex_q > 0 and ex_w > 0:
                            cols_extras_todas.extend([f"{ex_n} {j+1}" for j in range(int(ex_q))])

                    todas_cols_entrada = cols_provas + cols_listas + cols_labs + cols_ativs + cols_extras_todas

                    # --- 3. CARREGAMENTO DOS ALUNOS E CÁLCULOS ---
                    df_alunos = pd.read_sql(f"SELECT a.ra as Matrícula, a.nome as Nome FROM alunos a JOIN matriculas_disciplina m ON a.id = m.aluno_id WHERE m.turma_id={id_t_ativa} AND m.disciplina='{d_ativa}' ORDER BY a.nome", conn)

                    if not df_alunos.empty:
                        df_notas_banco = pd.read_sql(f"SELECT matricula as Matrícula, avaliacao, nota FROM notas_flexiveis WHERE turma_id={id_t_ativa} AND disciplina='{d_ativa}'", conn)
                        df_pivot = df_notas_banco.pivot_table(index='Matrícula', columns='avaliacao', values='nota', aggfunc='max').reset_index() if not df_notas_banco.empty else pd.DataFrame(columns=['Matrícula'])
                        df_atual = pd.merge(df_alunos, df_pivot, on="Matrícula", how="left")

                        if qtd_aulas_registradas > 0 and w_a > 0:
                            for i, data_ativ in enumerate(datas_unicas):
                                n_col = cols_ativs[i]
                                df_fatia = df_ativ_sala[df_ativ_sala['data'] == data_ativ]
                                mapa = dict(zip(df_fatia['Matrícula'], df_fatia['entregou'].apply(lambda x: 10.0 if x == 1 else 0.0)))
                                df_atual[n_col] = df_atual['Matrícula'].map(mapa).fillna(0.0)

                        for col in todas_cols_entrada:
                            if col not in df_atual.columns: df_atual[col] = 0.0
                            df_atual[col] = pd.to_numeric(df_atual[col], errors='coerce').fillna(0.0)

                        # Motor de Médias Mestre (Incluindo os Extras)
                        df_calc = df_atual.copy()
                        def calc_media(row, colunas, corte):
                            if not colunas: return 0.0
                            notas = sorted(row[colunas].tolist(), reverse=True)
                            if corte > 0:
                                manter = max(1, int(len(notas) * (1 - (corte / 100.0))))
                                notas = notas[:manter]
                            return sum(notas) / len(notas) if notas else 0.0

                        med_p = df_calc.apply(lambda r: calc_media(r, cols_provas, c_p), axis=1) if cols_provas else 0.0
                        med_l = df_calc.apply(lambda r: calc_media(r, cols_listas, c_l), axis=1) if cols_listas else 0.0
                        med_lb = df_calc.apply(lambda r: calc_media(r, cols_labs, c_lb), axis=1) if cols_labs else 0.0
                        med_a = df_calc.apply(lambda r: calc_media(r, cols_ativs, c_a), axis=1) if cols_ativs else 0.0

                        soma_medias_extras = 0.0
                        for ex_n, ex_q, ex_w, ex_c in extras_list:
                            if ex_q > 0 and ex_w > 0:
                                cols_ex_temp = [f"{ex_n} {j+1}" for j in range(int(ex_q))]
                                med_ex = df_calc.apply(lambda r: calc_media(r, cols_ex_temp, ex_c), axis=1)
                                df_calc[f"Média {ex_n}"] = med_ex
                                soma_medias_extras += med_ex * (ex_w / 100.0)

                        df_calc[f"Média {n_p}"] = med_p
                        df_calc[f"Média {n_l}"] = med_l
                        df_calc[f"Média {n_lb}"] = med_lb
                        df_calc[f"Média {n_a}"] = med_a

                        df_calc["MÉDIA FINAL"] = ((med_p*(w_p/100)) + (med_l*(w_l/100)) + (med_lb*(w_lb/100)) + (med_a*(w_a/100)) + soma_medias_extras).round(2)

                        # --- CONTEÚDO DAS OUTRAS ABAS ---
                        with t_manual:
                            st.caption("As colunas de 'Ativ' são automáticas do Dojo. Duplo clique para editar as outras.")
                            colunas_display = ["Matrícula", "Nome"] + todas_cols_entrada + ["MÉDIA FINAL"]
                            
                            # Trava a edição do que não pode ser alterado manualmente
                            col_config = {
                                "Matrícula": st.column_config.TextColumn(disabled=True),
                                "Nome": st.column_config.TextColumn(disabled=True),
                                "MÉDIA FINAL": st.column_config.NumberColumn(disabled=True)
                            }
                            for col in cols_ativs: col_config[col] = st.column_config.NumberColumn(disabled=True)
                                
                            df_ed = st.data_editor(df_calc[colunas_display], use_container_width=True, hide_index=True, column_config=col_config, key="ed_notas_vFinal")
                            
                            if st.button("💾 Salvar Planilha Inteira", type="primary", use_container_width=True):
                                conn.execute("DELETE FROM notas_flexiveis WHERE turma_id=? AND disciplina=?", (int(id_t_ativa), d_ativa))
                                for _, row in df_ed.iterrows():
                                    for col in todas_cols_entrada:
                                        if col in cols_ativs: continue # Atividades vêm do Dojo, não salva na tabela manual
                                        conn.execute("INSERT INTO notas_flexiveis (turma_id, disciplina, matricula, avaliacao, nota) VALUES (?,?,?,?,?)", (int(id_t_ativa), d_ativa, row['Matrícula'], col, float(row[col])))
                                conn.commit(); st.success("Notas salvas!"); st.rerun()

                        with t_excel:
                            st.markdown("#### 📊 Importar Notas via Planilha")
                            
                            # Puxa todas as colunas manuais (Provas, Listas, Labs e Extras), ignorando o Dojo automático
                            avaliacoes_importaveis = cols_provas + cols_listas + cols_labs + cols_extras_todas
                            
                            if avaliacoes_importaveis:
                                alvo_import = st.selectbox("Lançar notas na avaliação:", avaliacoes_importaveis, key="sel_alvo_import")
                                st.file_uploader(f"Subir arquivo para {alvo_import}:", type=["xlsx", "csv"], key="up_notas_excel")
                                
                                if st.button("📥 Processar Planilha", type="secondary", use_container_width=True):
                                    st.info(f"O sistema vai ler o arquivo, cruzar o RA do aluno e lançar as notas em '{alvo_import}'. (Lógica de processamento em construção)")
                            else:
                                st.warning("Crie e salve o planejamento na aba de 'Configurações' antes de importar notas.")

                        with t_auto:
                            st.markdown("#### 🦾 Corretor Automático")
                            
                            # Junta todas as avaliações que o robô pode corrigir (Provas, Listas, Labs e Extras)
                            avaliacoes_corrigiveis = cols_provas + cols_listas + cols_labs + cols_extras_todas
                            
                            # Adiciona a opção "Todas as Avaliações" no topo
                            opcoes_corretor = ["Todas as Avaliações"] + avaliacoes_corrigiveis if avaliacoes_corrigiveis else ["Nenhuma"]
                            
                            sel_p = st.selectbox("Selecione o lote para corrigir:", opcoes_corretor, key="sel_prova_auto")
                            
                            if st.button("🔄 Sincronizar com o Robô", type="primary", use_container_width=True): 
                                st.warning(f"Conectando a visão computacional para o lote: {sel_p}...")

                # =========================================================================
                # 🏆 4. BOLETIM MESTRE (O SINTÉTICO DA PROFESSORA)
                # =========================================================================
                with sub_boletim:
                    st.markdown(f"**🏆 Boletim Mestre: {t_ativa} - {d_ativa}**")
                    
                    alunos_bol_df = pd.read_sql(f"""SELECT a.ra as RA, a.nome as Aluno 
                                                    FROM alunos a JOIN matriculas_disciplina m ON a.id = m.aluno_id 
                                                    WHERE m.turma_id={id_t_ativa} AND m.disciplina='{d_ativa}'""", conn)
                    
                    if alunos_bol_df.empty:
                        st.warning("Não há alunos matriculados nesta disciplina.")
                    else:
                        import calendar
                        
                        hoje = datetime.today().date()
                        meses_pt = {1: 'janeiro', 2: 'fevereiro', 3: 'março', 4: 'abril', 5: 'maio', 6: 'junho', 7: 'julho', 8: 'agosto', 9: 'setembro', 10: 'outubro', 11: 'novembro', 12: 'dezembro'}
                        
                        col_f_tempo, col_f_aluno = st.columns(2)
                        filtro_tempo = col_f_tempo.selectbox("Filtrar Período (Opcional):", ["Semestre Inteiro", f"Este mês ({meses_pt[hoje.month]})", "Hoje", "Esta semana", "Semana passada"])
                        aluno_sel = col_f_aluno.selectbox("Filtrar Aluno:", ["Visão Geral da Turma"] + alunos_bol_df['Aluno'].tolist())

                        data_inicio, data_fim = None, None
                        if filtro_tempo == "Hoje": data_inicio = data_fim = hoje
                        elif filtro_tempo == "Esta semana":
                            data_inicio = hoje - timedelta(days=hoje.weekday())
                            data_fim = data_inicio + timedelta(days=6)
                        elif filtro_tempo == "Semana passada":
                            data_inicio = hoje - timedelta(days=hoje.weekday() + 7)
                            data_fim = data_inicio + timedelta(days=6)
                        elif filtro_tempo.startswith("Este mês"):
                            data_inicio = hoje.replace(day=1)
                            data_fim = hoje.replace(day=calendar.monthrange(hoje.year, hoje.month)[1])
                        
                        def filtrar_por_tempo(df_alvo):
                            if df_alvo.empty or filtro_tempo == "Semestre Inteiro": return df_alvo
                            df_alvo['data_dt'] = pd.to_datetime(df_alvo['data'], format='%d/%m/%Y', errors='coerce').dt.date
                            if data_inicio and data_fim: return df_alvo[(df_alvo['data_dt'] >= data_inicio) & (df_alvo['data_dt'] <= data_fim)]
                            return df_alvo
                            
                        df_diario_bruto = pd.read_sql(f"SELECT aluno_ra as RA, data, status FROM diario WHERE turma_id = {id_t_ativa}", conn)
                        df_dojo_bruto = pd.read_sql(f"SELECT aluno_ra as RA, data, pontos FROM logs_comportamento WHERE turma_id = {id_t_ativa} AND aluno_ra != 'TURMA_INTEIRA'", conn)
                        
                        df_diario_filtrado = filtrar_por_tempo(df_diario_bruto)
                        df_dojo_filtrado = filtrar_por_tempo(df_dojo_bruto)
                        
                        if not df_diario_filtrado.empty:
                            freq_pivot = df_diario_filtrado.pivot_table(index='RA', columns='status', aggfunc='size', fill_value=0).reset_index()
                            for col in ['Presente', 'Atrasado', 'Ausente']:
                                if col not in freq_pivot.columns: freq_pivot[col] = 0
                            freq_pivot['Total_Aulas'] = freq_pivot['Presente'] + freq_pivot['Atrasado'] + freq_pivot['Ausente']
                            freq_pivot.rename(columns={'Presente': 'Presentes', 'Atrasado': 'Atrasos', 'Ausente': 'Faltas'}, inplace=True)
                            df_diario = freq_pivot[['RA', 'Total_Aulas', 'Presentes', 'Atrasos', 'Faltas']]
                        else: df_diario = pd.DataFrame(columns=['RA', 'Total_Aulas', 'Presentes', 'Atrasos', 'Faltas'])

                        if not df_dojo_filtrado.empty:
                            df_dojo_filtrado['Positivos'] = df_dojo_filtrado['pontos'].apply(lambda x: x if x > 0 else 0)
                            df_dojo_filtrado['Negativos'] = df_dojo_filtrado['pontos'].apply(lambda x: abs(x) if x < 0 else 0)
                            df_dojo = df_dojo_filtrado.groupby('RA').agg({'pontos': 'sum', 'Positivos': 'sum', 'Negativos': 'sum'}).reset_index()
                            df_dojo.rename(columns={'pontos': 'Saldo_Dojo'}, inplace=True)
                        else: df_dojo = pd.DataFrame(columns=['RA', 'Saldo_Dojo', 'Positivos', 'Negativos'])
                        
                        df = alunos_bol_df.copy()
                        df = pd.merge(df, df_diario, on='RA', how='left')
                        df = pd.merge(df, df_dojo, on='RA', how='left')
                        
                        df['Total_Aulas'] = df['Total_Aulas'].fillna(0).astype(int)
                        df['Presentes'] = df['Presentes'].fillna(0).astype(int)
                        df['Atrasos'] = df['Atrasos'].fillna(0).astype(int)
                        df['Faltas'] = df['Faltas'].fillna(0).astype(int)
                        df['Saldo_Dojo'] = df['Saldo_Dojo'].fillna(0.0)
                        df['Positivos'] = df['Positivos'].fillna(0.0)
                        df['Negativos'] = df['Negativos'].fillna(0.0)
                        
                        # Injeta a Média Final que nós já calculamos, garantindo que os descartes (Cortes de %) e os Extras foram aplicados!
                        mapa_medias = dict(zip(df_calc['Matrícula'], df_calc['MÉDIA FINAL']))
                        df['Média_Parcial'] = df['RA'].map(mapa_medias).fillna(0.0)

                        df['Frequencia_%'] = df.apply(lambda x: (((x['Presentes'] + x['Atrasos']) / x['Total_Aulas']) * 100) if x['Total_Aulas'] > 0 else 100.0, axis=1)
                        
                        if aluno_sel != "Visão Geral da Turma": df = df[df['Aluno'] == aluno_sel]
                        
                        st.write("---")
                        col_chart, col_metrics = st.columns([0.4, 0.6])
                        
                        with col_chart:
                            total_pos = df['Positivos'].sum()
                            total_neg = df['Negativos'].sum()
                            
                            if total_pos + total_neg > 0:
                                fig = plex.pie(values=[total_pos, total_neg], names=['Positivos', 'A Melhorar'], color=['Positivos', 'A Melhorar'], color_discrete_map={'Positivos':'#2ecc71', 'A Melhorar':'#e74c3c'}, hole=0.65)
                                pct_pos = int((total_pos / (total_pos + total_neg)) * 100)
                                fig.update_layout(margin=dict(t=10, b=10, l=10, r=10), height=200, showlegend=False, annotations=[dict(text=f"{pct_pos}%", x=0.5, y=0.5, font_size=30, showarrow=False)])
                                st.plotly_chart(fig, use_container_width=True)
                            else: st.info("Sem dados de comportamento no Dojo.")
                        
                        with col_metrics:
                            c1, c2 = st.columns(2)
                            c1.metric("MÉDIA GERAL", f"{df['Média_Parcial'].mean():.2f}")
                            c2.metric("Média de Frequência", f"{df['Frequencia_%'].mean():.1f}%")
                            st.markdown(f"**Detalhe do Comportamento:** 🟢 {int(total_pos)} Positivos | 🔴 {int(total_neg)} A Melhorar")

                        st.write("---")
                        colunas_mostrar = ['Aluno', 'RA', 'Média_Parcial', 'Frequencia_%', 'Presentes', 'Atrasos', 'Faltas', 'Saldo_Dojo']
                        
                        df_tabela = df[colunas_mostrar].round(2).copy()
                        df_tabela = df_tabela.rename(columns={"Média_Parcial": "Média Acadêmica", "Frequencia_%": "Freq. %", "Saldo_Dojo": "⭐ Saldo Dojo"})
                        
                        st.dataframe(df_tabela, width="stretch", hide_index=True)
                        
                        nome_arquivo = f"Boletim_{semestre_ativo}_{t_ativa}_{d_ativa}.csv"
                        csv = df_tabela.to_csv(index=False).encode('utf-8-sig')
                        st.download_button("📤 Exportar Boletim em Excel", csv, nome_arquivo, "text/csv", type="primary")

# =========================================================================
# PILAR 4: GESTÃO DE AULA - VERSÃO INTEGRAL E SINCRONIZADA (V9.X)
# =========================================================================
with aba_sala:
    with sqlite3.connect('banco_provas.db') as conn:
        # 1. SETUP DE TABELAS (Garante que nada quebre se o banco for novo) 
        conn.execute('''CREATE TABLE IF NOT EXISTS diario_conteudo (id INTEGER PRIMARY KEY, turma_id INTEGER, disciplina TEXT, data TEXT, conteudo_real TEXT, observacao TEXT)''')
        conn.execute('''CREATE TABLE IF NOT EXISTS atividades_sala (id INTEGER PRIMARY KEY, turma_id INTEGER, disciplina TEXT, data TEXT, aluno_ra TEXT, entregou INTEGER)''')
        
        semestres_db = pd.read_sql("SELECT DISTINCT semestre FROM turmas ORDER BY semestre DESC", conn)
        sem_hj = semestres_db['semestre'].iloc[0] if not semestres_db.empty else "2026.1"
        turmas_df = pd.read_sql(f"SELECT id, nome FROM turmas WHERE semestre='{sem_hj}'", conn)
        
        if turmas_df.empty:
            st.info("Cadastre uma turma primeiro.")
        else:
            # SELEÇÃO GLOBAL (Turma -> Disciplina -> Data)
            c_s1, c_s2, c_s3, c_toggle = st.columns([0.3, 0.3, 0.2, 0.2], vertical_alignment="bottom")
            t_aula_nome = c_s1.selectbox("👥 Turma:", ["-- Escolha --"] + turmas_df['nome'].tolist(), key="final_t_sel")
            # O Modo Projetor fica na última coluna, alinhado por baixo
            with c_toggle:
                modo_projetor = st.toggle("📽️ Modo Projetor", value=True)
            if t_aula_nome != "-- Escolha --":
                id_t_sel = int(turmas_df[turmas_df['nome'] == t_aula_nome]['id'].values[0])
                discs_turma = pd.read_sql(f"SELECT DISTINCT disciplina FROM matriculas_disciplina WHERE turma_id={id_t_sel}", conn)
                lista_discs = discs_turma['disciplina'].tolist() if not discs_turma.empty else ["Nenhuma"]
                disc_sel = c_s2.selectbox("🏷️ Disciplina:", ["-- Escolha --"] + lista_discs, key="final_d_sel")

                if disc_sel != "-- Escolha --":
                    data_aula_global = c_s3.date_input("📅 Data:", datetime.today(), key="data_global_sala")
                    data_str_global = data_aula_global.strftime("%d/%m/%Y")

                    # --- 2. CRONÔMETRO E RUÍDO (Mantendo seu som suave) ---
                    st.write("---")
                    col_t1, col_t2 = st.columns([0.4, 0.6])
                    with col_t1:
                        st.markdown("### ⏱️ Cronômetro")
                        t_min = st.number_input("Minutos para atividade:", 1, 120, 15)
                        c_t_btn1, c_t_btn2 = st.columns(2)
                        if c_t_btn1.button("🚀 Iniciar", use_container_width=True):
                            st.session_state['timer_end'] = datetime.now().timestamp() + (t_min * 60); st.rerun()
                        if c_t_btn2.button("⏹️ Parar", use_container_width=True):
                            if 'timer_end' in st.session_state: del st.session_state['timer_end']; st.rerun()
                        
                        if 'timer_end' in st.session_state:
                            st.components.v1.html(f"""
                            <div style="text-align: center; background: #f0f2f6; padding: 10px; border-radius: 10px;">
                                <div id="timer_display" style="font-size: 45px; font-weight: bold; color: #2c3e50; font-family: monospace;">--:--</div>
                                <button id="btn_som" onclick="initAudio()" style="background: #3498db; color: white; border: none; border-radius: 5px; padding: 5px 10px; cursor: pointer;">🔊 Permitir Som</button>
                            </div>
                            <script>
                            let ac = null; function initAudio() {{ window.AudioContext = window.AudioContext || window.webkitAudioContext; ac = new AudioContext(); document.getElementById("btn_som").innerText="✅ OK"; }}
                            function alarme() {{ if(!ac) return; let o=ac.createOscillator(); let g=ac.createGain(); o.type='sine'; o.frequency.setValueAtTime(523.25, ac.currentTime); g.gain.setValueAtTime(0.4, ac.currentTime); g.gain.exponentialRampToValueAtTime(0.001, ac.currentTime+1.5); o.connect(g); g.connect(ac.destination); o.start(); o.stop(ac.currentTime+1.5); }}
                            const i = setInterval(() => {{
                                let s = Math.floor({st.session_state['timer_end']} - (Date.now()/1000));
                                if(s > 0) {{ document.getElementById("timer_display").innerText = Math.floor(s/60).toString().padStart(2,'0') + ":" + (s%60).toString().padStart(2,'0'); }}
                                else {{ document.getElementById("timer_display").innerText = "00:00"; alarme(); clearInterval(i); }}
                            }}, 1000);
                            </script>""", height=110)

                    with col_t2:
                        st.markdown("### 🔊 Medidor de Ruído")
                        st.components.v1.html("""
                            <div style="display: flex; flex-direction: column; justify-content: center; align-items: center; background: #f0f2f6; height: 110px; border-radius: 10px; padding: 10px; box-sizing: border-box;">
                                <canvas id="meter" width="300" height="35" style="background: #ffffff; border-radius: 5px; box-shadow: inset 0px 2px 5px rgba(0,0,0,0.05);"></canvas>
                                <div id="st" style="font-size:14px; font-weight:bold; margin-top:10px; color: #2c3e50;">🎤 Aguardando Microfone...</div>
                            </div>
                            <script>
                            navigator.mediaDevices.getUserMedia({audio:true}).then(s=>{
                                const ac=new AudioContext();
                                const an=ac.createAnalyser();
                                const mic=ac.createMediaStreamSource(s);
                                mic.connect(an);
                                const d=new Uint8Array(an.frequencyBinCount);
                                const can=document.getElementById('meter');
                                const ctx=can.getContext('2d');
                                function draw(){
                                    an.getByteFrequencyData(d);
                                    let av=d.reduce((a,b)=>a+b)/d.length;
                                    ctx.clearRect(0,0,300,35);
                                    ctx.fillStyle=(av>50?"#e74c3c":"#2ecc71");
                                    ctx.fillRect(0,0,(av/100)*300,35);
                                    document.getElementById('st').innerHTML=(av>50?"🛑 <b>Silêncio! Muito Barulho</b>":"✅ <b>Nível de Ruído OK</b>");
                                    requestAnimationFrame(draw);
                                }
                                draw();
                            }).catch(err => {
                                document.getElementById('st').innerHTML="⚠️ Microfone Bloqueado";
                            });
                            </script>
                        """, height=130)

                    st.write("---")
                    
                    # --- 🚨 SISTEMA DE ALERTAS DE DÚVIDAS ---
                    try:
                        conn.execute('''CREATE TABLE IF NOT EXISTS duvidas_alunos (id INTEGER PRIMARY KEY AUTOINCREMENT, turma_id INTEGER, disciplina TEXT, aluno_ra TEXT, data TEXT, mensagem TEXT, respondida BOOLEAN DEFAULT 0)''')
                        df_duvidas = pd.read_sql(f"SELECT id FROM duvidas_alunos WHERE turma_id={id_t_sel} AND disciplina='{disc_sel}' AND respondida=0", conn)
                        if not df_duvidas.empty:
                            qtd_duvidas = len(df_duvidas)
                            st.error(f"🚨 **VOCÊ TEM {qtd_duvidas} NOVA(S) DÚVIDA(S)!** Os alunos enviaram perguntas pelo Portal. Selecione a aba '📩 Responder Dúvidas' abaixo para visualizar.")
                    except Exception:
                        pass
                    # ----------------------------------------
                    
                    modo_aula = st.radio("Selecione a ação:", ["⭐ Comportamento", "🙋 Fazer Chamada", "✍️ Atividade de Sala", "🎲 Sortear Aluno", "👥 Grupos", "📖 Registrar Diário", "📩 Responder Dúvidas"], horizontal=True, key="radio_modo_final")
                    
                    # 🚀 BUSCA ALUNOS INCLUINDO AVATAR_OPTS PARA V9
                    alunos_sala = pd.read_sql(f"SELECT a.ra, a.nome, a.avatar_style, a.avatar_opts, a.observacoes FROM alunos a JOIN matriculas_disciplina m ON a.id = m.aluno_id WHERE m.turma_id={id_t_sel} AND m.disciplina='{disc_sel}' ORDER BY a.nome", conn)

                    # =========================================================
                    # MODO 1: ⭐ COMPORTAMENTO (DOJO COMPLETO)
                    # =========================================================
                    if modo_aula == "⭐ Comportamento":
                        df_p = pd.read_sql(f"SELECT aluno_ra, SUM(CASE WHEN data='{data_str_global}' AND pontos>0 THEN pontos ELSE 0 END) as dia_pos, SUM(CASE WHEN data='{data_str_global}' AND pontos<0 THEN pontos ELSE 0 END) as dia_neg, SUM(pontos) as total_geral FROM logs_comportamento WHERE turma_id={id_t_sel} GROUP BY aluno_ra", conn)
                        df_t_pts = pd.read_sql(f"SELECT SUM(CASE WHEN data='{data_str_global}' AND pontos>0 THEN pontos ELSE 0 END) as d_pos, SUM(CASE WHEN data='{data_str_global}' AND pontos<0 THEN pontos ELSE 0 END) as d_neg, SUM(pontos) as t_geral FROM logs_comportamento WHERE turma_id={id_t_sel} AND aluno_ra='TURMA_INTEIRA'", conn).iloc[0].fillna(0)
                        alunos_dojo = pd.merge(alunos_sala, df_p, left_on='ra', right_on='aluno_ra', how='left').fillna(0)

                        @st.dialog("Lançar FeedBack")
                        def modal_feedback(ra, nome):
                            st.write(f"Dar ponto para: **{nome}**")
                            def b_salvar(m, p):
                                with sqlite3.connect('banco_provas.db') as c:
                                    c.execute("INSERT INTO logs_comportamento (aluno_ra, turma_id, data, pontos, comentario, tipo) VALUES (?,?,?,?,?,?)", (ra, id_t_sel, data_str_global, p, m, "Feedback"))
                                st.rerun()
                            c1, c2 = st.columns(2)
                            if c1.button("❤️ Ajuda"): b_salvar("Ajudando os colegas", 1.0)
                            if c2.button("🧐 Foco"): b_salvar("Focado", 1.0)
                            if c1.button("💡 Participação"): b_salvar("Participação", 1.0)
                            if c2.button("🏔️ Persistência"): b_salvar("Persistência", 1.0)
                            if c1.button("📱 Celular"): b_salvar("Usando celular", -1.0)
                            if c2.button("🗣️ Conversa"): b_salvar("Conversa paralela", -1.0)
                            st.write("---")
                            p_i = st.number_input("Pts:", value=1.0, step=0.5); m_i = st.text_input("Motivo:")
                            if st.button("💾 Gravar"): b_salvar(m_i if m_i else "Avaliação", p_i)

                        cols = st.columns(6)
                        # --- CARD DA TURMA INTEIRA ---
                        with cols[0]:
                            with st.container(border=True):
                                st.markdown(f"<div style='text-align:center; height:140px;'><span style='font-size: 38px; line-height: 45px;'>🌍</span><br><b>Turma</b><br><small style='color:green;'>●</small>{int(df_t_pts['d_pos'])}|<small style='color:red;'>●</small>{int(abs(df_t_pts['d_neg']))}<br><small>⭐{int(df_t_pts['t_geral'])}</small></div>", unsafe_allow_html=True)
                                if st.button("Feedback", key="bt_t", use_container_width=True): modal_feedback('TURMA_INTEIRA', 'Toda a Turma')
                        # --- CARDS INDIVIDUAIS DOS ALUNOS ---
                        for idx, row in alunos_dojo.iterrows():
                            with cols[(idx+1)%6]:
                                with st.container(border=True):
                                    opts = row['avatar_opts'] if pd.notna(row['avatar_opts']) else ""
                                    url = f"https://api.dicebear.com/9.x/{row['avatar_style']}/svg?seed={row['ra']}{opts}"
                                    p_css = "image-rendering:pixelated;" if row['avatar_style'] == 'pixel-art' else ""
                                    st.markdown(f"<div style='text-align:center; height:140px;'><img src='{url}' width='45' style='{p_css}'><br><b>{row['nome'].split()[0]}</b><br><small style='color:green;'>●</small>{int(row['dia_pos'])}|<small style='color:red;'>●</small>{int(abs(row['dia_neg']))}<br><small>⭐{int(row['total_geral'])}</small></div>", unsafe_allow_html=True)
                                    if st.button("Feedback", key=f"f_{row['ra']}", use_container_width=True): 
                                        modal_feedback(row['ra'], row['nome'])

                    # =========================================================
                    # MODO 2: 📅 CHAMADA (ESTADO + FALTAS)
                    # =========================================================
                    elif modo_aula == "🙋 Fazer Chamada":
                        df_f = pd.read_sql(f"SELECT aluno_ra, COUNT(*) as total FROM diario WHERE turma_id={id_t_sel} AND status='Ausente' GROUP BY aluno_ra", conn)
                        dict_f = dict(zip(df_f['aluno_ra'], df_f['total']))
                        
                        if "m_ch" not in st.session_state:
                            df_dia = pd.read_sql(f"SELECT aluno_ra, status FROM diario WHERE turma_id={id_t_sel} AND data='{data_str_global}'", conn)
                            freq = dict(zip(df_dia['aluno_ra'], df_dia['status']))
                            st.session_state.m_ch = {r['ra']: freq.get(r['ra'], "Presente") for _, r in alunos_sala.iterrows()}
                        
                        c1, c2,c3, _ = st.columns([0.4, 0.4, 0.4, 2])
                        if c1.button("🟢 Presentes"): 
                            for r in st.session_state.m_ch: st.session_state.m_ch[r] = "Presente"
                            st.rerun()
                        if c2.button("🔴 Ausentes", use_container_width=True): 
                            for r in st.session_state.m_ch: st.session_state.m_ch[r] = "Ausente"
                            st.rerun()
                        if c3.button("💾 SALVAR"):
                            for ra, stt in st.session_state.m_ch.items():
                                conn.execute("DELETE FROM diario WHERE turma_id=? AND data=? AND aluno_ra=?", (id_t_sel, data_str_global, ra))
                                conn.execute("INSERT INTO diario (turma_id, data, aluno_ra, presente, status) VALUES (?,?,?,?,?)", (id_t_sel, data_str_global, ra, stt!="Ausente", stt))
                            conn.commit(); st.success("Salvo!"); st.rerun()
                        st.write("") # Dá um respiro
                        cols_f = st.columns(6)
                        for idx, row in alunos_sala.iterrows():
                            ra = row['ra']; s = st.session_state.m_ch.get(ra, "Presente")
                            opts = row['avatar_opts'] if pd.notna(row['avatar_opts']) else ""
                            url = f"https://api.dicebear.com/9.x/{row['avatar_style']}/svg?seed={ra}{opts}"
                            with cols_f[idx%6]:
                                with st.container(border=True):
                                    st.markdown(f"<div style='text-align:center;'><img src='{url}' width='45'><br><b>{row['nome'].split()[0]}</b><br><small style='color:red;'>Faltas: {dict_f.get(ra,0)}</small></div>", unsafe_allow_html=True)
                                    lbl = {"Presente":"🟢", "Ausente":"🔴", "Atrasado":"🟡"}[s]
                                    if st.button(lbl, key=f"ch_{ra}", use_container_width=True):
                                        st.session_state.m_ch[ra] = {"Presente":"Ausente", "Ausente":"Atrasado", "Atrasado":"Presente"}[s]; st.rerun()

                    # =========================================================
                    # MODO 3: ✍️ ATIVIDADE (REGRA DOS 25% + 9.X)
                    # =========================================================
                    elif modo_aula == "✍️ Atividade de Sala":
                        df_h = pd.read_sql(f"SELECT data, aluno_ra, entregou FROM atividades_sala WHERE turma_id={id_t_sel} AND disciplina='{disc_sel}'", conn)
                        tot_aulas = df_h['data'].nunique()
                        meta = tot_aulas - int(tot_aulas * 0.25) if tot_aulas > 0 else 0
                        st.info(f"📊 Meta: {meta} entregas (Fator descarte 25% aplicado)")

                        if "m_ativ" not in st.session_state:
                            df_hj = df_h[df_h['data'] == data_str_global]
                            d_hj = dict(zip(df_hj['aluno_ra'], df_hj['entregou']))
                            st.session_state.m_ativ = {r['ra']: d_hj.get(r['ra'], 0) for _, r in alunos_sala.iterrows()}

                        if st.button("💾 Salvar Atividades", type="primary"):
                            for ra, ent in st.session_state.m_ativ.items():
                                # ✅ CORRIGIDO AQUI!
                                conn.execute("DELETE FROM atividades_sala WHERE turma_id=? AND disciplina=? AND data=? AND aluno_ra=?", (id_t_sel, disc_sel, data_str_global, ra))
                                conn.execute("INSERT INTO atividades_sala (turma_id, disciplina, data, aluno_ra, entregou) VALUES (?,?,?,?,?)", (id_t_sel, disc_sel, data_str_global, ra, ent))
                            conn.commit(); st.success("Salvo!"); st.rerun()

                        cols_f = st.columns(6)
                        for idx, row in alunos_sala.iterrows():
                            ra = row['ra']; ent_hj = st.session_state.m_ativ.get(ra, 0)
                            tot_al = df_h[(df_h['aluno_ra']==ra) & (df_h['entregou']==1)].shape[0]
                            opts = row['avatar_opts'] if pd.notna(row['avatar_opts']) else ""
                            url = f"https://api.dicebear.com/9.x/{row['avatar_style']}/svg?seed={ra}{opts}"
                            with cols_f[idx%6]:
                                with st.container(border=True):
                                    cor = "green" if tot_al >= meta and meta > 0 else "red"
                                    st.markdown(f"<div style='text-align:center;'><img src='{url}' width='45'><br><b>{row['nome'].split()[0]}</b><br><small style='color:{cor};'>Fez: {tot_al}/{meta}</small></div>", unsafe_allow_html=True)
                                    if st.button("✅" if ent_hj else "❌", key=f"at_{ra}", use_container_width=True):
                                        st.session_state.m_ativ[ra] = 1 if ent_hj==0 else 0; st.rerun()

                    # =========================================================
                    # MODO 4: 🎲 SORTEIO (AVATAR V9)
                    # =========================================================
                    elif modo_aula == "🎲 Sortear Aluno":
                        if not alunos_sala.empty:
                            if st.button("🎲 Novo Sorteio", use_container_width=True): 
                                st.session_state.sort_al = alunos_sala.sample(1).iloc[0]
                            if "sort_al" in st.session_state:
                                s = st.session_state.sort_al
                                opts = s['avatar_opts'] if pd.notna(s['avatar_opts']) else ""
                                url = f"https://api.dicebear.com/9.x/{s['avatar_style']}/svg?seed={s['ra']}{opts}"
                                st.markdown(f"<div style='background:#1c9e5e; padding:30px; border-radius:15px; text-align:center;'><div style='background:white; padding:20px; border-radius:15px; display:inline-block;'><img src='{url}' width='130'><h2>{s['nome']}</h2></div></div>", unsafe_allow_html=True)

                    # =========================================================
                    # MODO 5: 👥 GRUPOS (INTEGRADO COM LABS, LISTAS E PROVAS)
                    # =========================================================
                    elif modo_aula == "👥 Grupos":
                        df_plan = pd.read_sql(
                            f"SELECT nome_avaliacao FROM planejamento_notas "
                            f"WHERE turma_id={id_t_sel} AND disciplina='{disc_sel}'",
                            conn
                        )

                        atividades_validas = df_plan['nome_avaliacao'].tolist()

                        if not atividades_validas:
                            st.error("⚠️ Nenhuma atividade configurada em 'Pesos e Quantidades'.")
                            st.stop()

                        if "gs_m" not in st.session_state:
                            st.session_state.gs_m = []

                        col_sel, col_undo = st.columns([0.75, 0.25], vertical_alignment="bottom")

                        atividade_escolhida = col_sel.selectbox(
                            "📌 Selecione a atividade para lançar nota nos grupos:",
                            atividades_validas,
                            key=f"atividade_grupo_{id_t_sel}_{disc_sel}"
                        )

                        if st.session_state.gs_m:
                            if col_undo.button("🗑️ Desfazer Grupos", use_container_width=True):
                                st.session_state.gs_m = []
                                st.rerun()

                        st.markdown("---")

                        if not st.session_state.gs_m:
                            t_f = st.radio("Tipo de formação:", ["Aleatório", "Manual"], horizontal=True)

                            if t_f == "Aleatório":
                                n_g = st.number_input("Alunos por grupo (Tamanho):", 1, 10, 4)
                                if st.button("🎲 Gerar Grupos Aleatórios", use_container_width=True):
                                    sh = alunos_sala.sample(frac=1).to_dict('records')
                                    gs = [sh[i:i + n_g] for i in range(0, len(sh), n_g)]
                                    st.session_state.gs_m = gs
                                    st.rerun()
                            else:
                                # --- INÍCIO DA FORMAÇÃO MANUAL ---
                                qtd_grupos = st.number_input("Quantidade de Grupos:", 1, 20, 4)
                                st.caption("Selecione os alunos para cada grupo abaixo:")
                                
                                # Prepara os alunos para a caixa de pesquisa
                                dict_alunos = {f"{row['ra']} - {row['nome']}": row.to_dict() for _, row in alunos_sala.iterrows()}
                                
                                grupos_manuais = []
                                for i in range(qtd_grupos):
                                    membros = st.multiselect(
                                        f"Membros do Grupo {i+1}:", 
                                        options=list(dict_alunos.keys()), 
                                        key=f"gm_{i}_{id_t_sel}_{disc_sel}"
                                    )
                                    # Pega os dados completos dos alunos selecionados
                                    grupos_manuais.append([dict_alunos[m] for m in membros])
                                
                                if st.button("✅ Confirmar Grupos Manuais", type="primary", use_container_width=True):
                                    # Filtra para não criar grupos vazios
                                    grupos_filtrados = [g for g in grupos_manuais if len(g) > 0]
                                    if grupos_filtrados:
                                        st.session_state.gs_m = grupos_filtrados
                                        st.rerun()
                                    else:
                                        st.warning("⚠️ Preencha pelo menos um grupo antes de confirmar.")
                                # --- FIM DA FORMAÇÃO MANUAL ---
                        else:
                            st.markdown(f"**🏷️ Lançando nota dos grupos em:** `{atividade_escolhida}`")

                            cg = st.columns(3)
                            for i, g in enumerate(st.session_state.gs_m):
                                with cg[i % 3]:
                                    with st.container(border=True):
                                        st.write(f"**Grupo {i+1}**")

                                        avs_h = "".join([
                                            f"<img src='https://api.dicebear.com/9.x/{a['avatar_style']}/svg?seed={a['ra']}"
                                            f"{(a['avatar_opts'] if pd.notna(a['avatar_opts']) else '')}' "
                                            f"width='35' style='margin-right:2px;'>"
                                            for a in g
                                        ])
                                        st.markdown(avs_h, unsafe_allow_html=True)

                                        st.write("")
                                        c_pts, c_btn = st.columns([0.5, 0.5], vertical_alignment="bottom")
                                        pts_v = c_pts.number_input(
                                            "Nota:",
                                            0.0, 10.0, 1.0, 0.5,
                                            key=f"pts_g_{i}"
                                        )

                                        if c_btn.button(
                                            f"💾 Lançar",
                                            key=f"btn_g_{i}",
                                            use_container_width=True
                                        ):
                                            with sqlite3.connect('banco_provas.db') as c_nota:
                                                for aluno in g:
                                                    c_nota.execute(
                                                        "DELETE FROM notas_flexiveis "
                                                        "WHERE turma_id=? AND disciplina=? AND matricula=? AND avaliacao=?",
                                                        (id_t_sel, disc_sel, aluno['ra'], atividade_escolhida)
                                                    )
                                                    c_nota.execute(
                                                        "INSERT INTO notas_flexiveis "
                                                        "(turma_id, disciplina, matricula, avaliacao, nota) "
                                                        "VALUES (?,?,?,?,?)",
                                                        (id_t_sel, disc_sel, aluno['ra'], atividade_escolhida, pts_v)
                                                    )
                                            st.toast(f"Nota salva em '{atividade_escolhida}' para o Grupo {i+1}!")

                    # =========================================================
                    # MODO 6: 📝 DIÁRIO (PEDAGÓGICO FAM)
                    # =========================================================
                    elif modo_aula == "📖 Registrar Diário":
                        exp = pd.read_sql(f"SELECT tema FROM cronograma_detalhado WHERE turma_id={id_t_sel} AND disciplina='{disc_sel}' AND data='{data_str_global}'", conn)
                        st.info(f"🎯 Planejado: {exp['tema'].iloc[0] if not exp.empty else 'Não agendado para hoje'}")
                        
                        real_db = pd.read_sql(f"SELECT conteudo_real FROM diario_conteudo WHERE turma_id={id_t_sel} AND disciplina='{disc_sel}' AND data='{data_str_global}'", conn)
                        c_real = st.text_area("O que realmente foi dado hoje?", value=real_db['conteudo_real'].iloc[0] if not real_db.empty else "")
                        
                        if st.button("💾 Salvar Diário", type="primary", use_container_width=True):
                            # ✅ CORRIGIDO AQUI TAMBÉM!
                            conn.execute("DELETE FROM diario_conteudo WHERE turma_id=? AND disciplina=? AND data=?", (id_t_sel, disc_sel, data_str_global))
                            conn.execute("INSERT INTO diario_conteudo (turma_id, disciplina, data, conteudo_real) VALUES (?,?,?,?)", (id_t_sel, disc_sel, data_str_global, c_real))
                            conn.commit(); st.success("Diário atualizado!")
                    # =========================================================
                    # MODO 7: 📩 RESPONDER DÚVIDAS (INTEGRAÇÃO COM PORTAL)
                    # =========================================================
                    elif modo_aula == "📩 Responder Dúvidas":
                        st.markdown("### 📩 Caixa de Entrada de Dúvidas")
                        st.caption("Aqui caem todas as dúvidas enviadas pelos alunos via Portal.")
                        
                        try:
                            df_todas_duvidas = pd.read_sql(f"""
                                SELECT d.id, d.data, d.mensagem, d.respondida, a.nome, a.ra, a.avatar_style, a.avatar_opts 
                                FROM duvidas_alunos d 
                                JOIN alunos a ON d.aluno_ra = a.ra 
                                WHERE d.turma_id={id_t_sel} AND d.disciplina='{disc_sel}' 
                                ORDER BY d.respondida ASC, d.id DESC
                            """, conn)
                            
                            if df_todas_duvidas.empty:
                                st.info("Nenhuma dúvida foi enviada nesta disciplina ainda. Oba! 🎉")
                            else:
                                for _, d_row in df_todas_duvidas.iterrows():
                                    cor_borda = "#e74c3c" if d_row['respondida'] == 0 else "#2ecc71"
                                    status_txt = "🔴 NÃO LIDA" if d_row['respondida'] == 0 else "🟢 RESOLVIDA"
                                    bg_color = "#fdf1f0" if d_row['respondida'] == 0 else "#f0fdf4"
                                    
                                    opts = d_row['avatar_opts'] if pd.notna(d_row['avatar_opts']) else ""
                                    url_avatar = f"https://api.dicebear.com/9.x/{d_row['avatar_style']}/svg?seed={d_row['ra']}{opts}"
                                    
                                    # Card da Dúvida com a carinha do aluno
                                    st.markdown(f"""
                                    <div style='border: 2px solid {cor_borda}; border-radius: 10px; padding: 15px; margin-bottom: 10px; background-color: {bg_color};'>
                                        <div style='display: flex; align-items: center; margin-bottom: 10px;'>
                                            <img src='{url_avatar}' width='50' style='background: white; border-radius: 50%; margin-right: 15px; border: 1px solid #ccc;'>
                                            <div style='flex-grow: 1;'>
                                                <b style='font-size: 16px;'>{d_row['nome']}</b> <span style='font-size: 12px; color: gray;'>({d_row['data']})</span><br>
                                                <span style='font-size: 12px; font-weight: bold;'>{status_txt}</span>
                                            </div>
                                        </div>
                                        <div style='font-size: 15px; margin-bottom: 10px; padding: 10px; background: white; border-radius: 5px; border-left: 3px solid #3498db;'>
                                            <i>"{d_row['mensagem']}"</i>
                                        </div>
                                    </div>
                                    """, unsafe_allow_html=True)
                                    
                                    col_btn1, col_btn2, col_btn3 = st.columns([0.4, 0.3, 0.3])
                                    
                                    # Ações (Ler, Reabrir ou Apagar)
                                    if d_row['respondida'] == 0:
                                        if col_btn1.button("✅ Marcar como Resolvida", key=f"btn_lida_{d_row['id']}", use_container_width=True, type="primary"):
                                            conn.execute(f"UPDATE duvidas_alunos SET respondida=1 WHERE id={d_row['id']}")
                                            conn.commit()
                                            st.rerun()
                                    else:
                                        if col_btn2.button("↩️ Reabrir Dúvida", key=f"btn_reabrir_{d_row['id']}", use_container_width=True):
                                            conn.execute(f"UPDATE duvidas_alunos SET respondida=0 WHERE id={d_row['id']}")
                                            conn.commit()
                                            st.rerun()
                                            
                                        if col_btn3.button("🗑️ Apagar Histórico", key=f"btn_del_duv_{d_row['id']}", use_container_width=True):
                                            conn.execute(f"DELETE FROM duvidas_alunos WHERE id={d_row['id']}")
                                            conn.commit()
                                            st.rerun()
                        except Exception as e:
                            st.warning(f"Sincronizando banco de dúvidas...")