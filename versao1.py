import streamlit as st
import sqlite3
import pandas as pd
import plotly.express as px 
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

from datetime import datetime, timedelta
from difflib import SequenceMatcher

# =========================================================================
# --- 1. FUNÇÕES DE UTILIDADE E SEGURANÇA ---
# =========================================================================
def sanitizar_nome(texto):
    nfkd = unicodedata.normalize('NFKD', texto)
    return "".join([c for c in nfkd if not unicodedata.category(c).startswith('M')]).replace(" ", "_")

def escapar_latex(texto):
    if not texto: return ""
    texto = texto.replace('\u200b', '') # Remove caracteres fantasmas
    
    partes = texto.split('$')
    resultado = []
    for i, parte in enumerate(partes):
        if i % 2 == 0: # Texto normal: precisa escapar
            mapa = {'&': r'\&', '%': r'\%', '#': r'\#', '_': r'\_', '{': r'\{', '}': r'\}', '\\': r'\textbackslash{}'}
            for char, sub in mapa.items():
                parte = parte.replace(char, sub)
            resultado.append(parte)
        else: # É fórmula matemática: mantém o $ e não mexe em nada
            resultado.append(f"${parte}$")
    return "".join(resultado)

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
def inserir_questao(disc, ass, dif, enun, alts, pts, tipo, gab_disc=None, img=None, espaco="Linhas", espaco_linhas=4, gab_img=None):
    with sqlite3.connect('banco_provas.db') as conexao:
        cursor = conexao.cursor()
        cursor.execute('''INSERT INTO questoes (disciplina, assunto, dificuldade, enunciado, imagem, pontos, tipo, gabarito_discursivo, espaco_resposta, espaco_linhas, gabarito_imagem) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''', (disc, ass, dif, enun, img, float(pts), tipo, gab_disc, espaco, int(espaco_linhas), gab_img))
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

def buscar_questoes_filtradas(disciplina, limite=None, assunto="Todos", dificuldade="Todos", tipo="Todos", sortear=False, excluir_ids=None):
    with sqlite3.connect('banco_provas.db') as conexao:
        cursor = conexao.cursor()
        query = '''SELECT id, enunciado, imagem, pontos, tipo, gabarito_discursivo, espaco_resposta, espaco_linhas, dificuldade, assunto, gabarito_imagem FROM questoes WHERE disciplina = ?'''
        params = [disciplina]
        if assunto != "Todos": query += " AND assunto = ?"; params.append(assunto)
        if dificuldade != "Todos": query += " AND dificuldade = ?"; params.append(dificuldade)
        if tipo != "Todos": query += " AND tipo = ?"; params.append(tipo)
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
        subprocess.run([caminho_mac, '-interaction=nonstopmode', caminho_tex], capture_output=True)
        subprocess.run([caminho_mac, '-interaction=nonstopmode', caminho_tex], capture_output=True)
        if os.path.exists(caminho_pdf): return True
        else:
            st.error(f"⚠️ Falha real: O PDF não foi criado para {caminho_tex}")
            return False
    except Exception as e:
        st.error(f"⚠️ Erro ao tentar chamar o LaTeX no sistema: {e}")
        return False

# =========================================================================
# --- 5. LISTAS DE SÍMBOLOS E PAINEL FLUTUANTE ---
# =========================================================================
gregas = [("α", r"\alpha"), ("β", r"\beta"), ("γ", r"\gamma"), ("δ", r"\delta"), ("ε", r"\epsilon"), ("ζ", r"\zeta"), ("η", r"\eta"), ("θ", r"\theta"), ("κ", r"\kappa"), ("λ", r"\lambda"), ("μ", r"\mu"), ("ν", r"\nu"), ("ξ", r"\xi"), ("π", r"\pi"), ("ρ", r"\rho"), ("σ", r"\sigma"), ("τ", r"\tau"), ("φ", r"\phi"), ("χ", r"\chi"), ("ψ", r"\psi"), ("ω", r"\omega"), ("Γ", r"\Gamma"), ("Δ", r"\Delta"), ("Θ", r"\Theta"), ("Λ", r"\Lambda"), ("Σ", r"\Sigma"), ("Φ", r"\Phi"), ("Ω", r"\Omega")]
matematica = [("Fração", r"\frac{ }{ }"), ("Potência", r"^{ }"), ("Subscrito", r"_{ }"), ("Sub+Pot", r"_{ }^{ }"), ("Raiz √", r"\sqrt{ }"), ("Raiz N ∛", r"\sqrt[ ]{ }"), ("Parênteses ( )", r"\left(  \right)"), ("Colchetes [ ]", r"\left[  \right]"), ("Chaves { }", r"\left\{  \right\}"), ("Matriz 2x2", r"\begin{bmatrix} a & b \\ c & d \end{bmatrix}"), ("Vetor (v⃗)", r"\vec{v}"), ("Versor (n̂)", r"\hat{n}"), ("Ponto (ẋ)", r"\dot{x}"), ("2 Pontos (ẍ)", r"\ddot{x}"), ("Barra (x̄)", r"\bar{x}"), ("Maior/Igual ≥", r"\geq"), ("Menor/Igual ≤", r"\leq"), ("Diferente ≠", r"\neq"), ("Aprox ≈", r"\approx"), ("Infinito ∞", r"\infty"), ("Seta →", r"\to"), ("Graus °C", r"^\circ C"), ("Mais/Menos ±", r"\pm"), ("Multiplica ×", r"\times"), ("Negrito", r"\mathbf{ }"), ("Itálico", r"\mathit{ }")]
calculo = [("Limite", r"\lim_{x \to \infty}"), ("Integral ∫", r"\int"), ("Int. Definida", r"\int_{a}^{b}"), ("Int. Dupla ∬", r"\iint"), ("Int. Fechada ∮", r"\oint"), ("Somatório Σ", r"\sum_{i=1}^{n}"), ("Produtório Π", r"\prod_{i=1}^{n}"), ("Derivada d/dx", r"\frac{d}{dx}"), ("Derivada 2ª", r"\frac{d^2}{dx^2}"), ("Parcial ∂", r"\partial"), ("Gradiente ∇", r"\nabla"), ("Divergente", r"\nabla \cdot"), ("Rotacional", r"\nabla \times")]
fluidos = [("Bernoulli", r"P_1 + \frac{1}{2}\rho v_1^2 + \rho g z_1 = P_2 + \frac{1}{2}\rho v_2^2 + \rho g z_2"), ("Darcy-Weisbach", r"h_f = f \cdot \frac{L}{D} \cdot \frac{v^2}{2g}"), ("Reynolds", r"Re = \frac{\rho v D}{\mu}"), ("Continuidade", r"A_1 v_1 = A_2 v_2"), ("Empuxo", r"E = \rho_{liq} \cdot V_{sub} \cdot g"), ("Pressão Hidro.", r"P = P_{atm} + \rho g h")]
termo = [("1ª Lei", r"\Delta U = Q - W"), ("Gás Ideal", r"P V = n R T"), ("Trabalho Exp.", r"W = \int_{V_1}^{V_2} P dV"), ("Rendimento η", r"\eta = \frac{W_{liq}}{Q_{q}}"), ("Carnot", r"\eta_{max} = 1 - \frac{T_f}{T_q}"), ("Entropia ΔS", r"\Delta S = \int \frac{dQ_{rev}}{T}"), ("Calor Sensível", r"Q = m \cdot c \cdot \Delta T")]

def injetar_direto(comando, target_key):
    if target_key in st.session_state: st.session_state[target_key] += f" ${comando}$ "
    else: st.session_state[target_key] = f" ${comando}$ "

def painel_flutuante(target_key, prefix):
    with st.popover("🧮 Fórmulas", width="stretch"):
        tg, tm, tc, tf, tt = st.tabs(["αβγ", "Mat", "Cálc", "🌊", "🔥"])
        with tg:
            c = st.columns(4)
            for i, (l, cmd) in enumerate(gregas): c[i%4].button(l, key=f"{prefix}g{i}", on_click=injetar_direto, args=(cmd, target_key))
        with tm:
            c = st.columns(3)
            for i, (l, cmd) in enumerate(matematica): c[i%3].button(l, key=f"{prefix}m{i}", on_click=injetar_direto, args=(cmd, target_key))
        with tc:
            c = st.columns(3)
            for i, (l, cmd) in enumerate(calculo): c[i%3].button(l, key=f"{prefix}c{i}", on_click=injetar_direto, args=(cmd, target_key))
        with tf:
            c = st.columns(2)
            for i, (l, cmd) in enumerate(fluidos): c[i%2].button(l, key=f"{prefix}f{i}", on_click=injetar_direto, args=(cmd, target_key))
        with tt:
            c = st.columns(2)
            for i, (l, cmd) in enumerate(termo): c[i%2].button(l, key=f"{prefix}t{i}", on_click=injetar_direto, args=(cmd, target_key))

# =========================================================================
# --- 6. INICIALIZAÇÃO DA INTERFACE (STREAMLIT) ---
# =========================================================================
criar_base_de_dados()
st.set_page_config(page_title="Gerador da Mari", layout="wide", initial_sidebar_state="collapsed")


with st.sidebar:
    st.header("🛠️ Manutenção do Sistema")
    if st.button("🧹 Limpar Arquivos Temporários", width="stretch"):
        qtd_removidos = limpar_arquivos_temporarios()
        if qtd_removidos > 0: st.success(f"Limpeza concluída! {qtd_removidos} arquivos apagados.")
        else: st.info("A pasta já está limpa.")
            
    st.write("---")
    if st.button("💾 Fazer Backup Local", width="stretch"):
        nome_bkp = criar_backup_banco()
        if nome_bkp: st.success(f"Backup criado: {nome_bkp}")
        else: st.error("Falha ao criar o backup local.")
            
    if st.button("☁️ Forçar Backup iCloud", width="stretch"):
        if backup_para_icloud(): st.success("Sincronizado com o iCloud!")
        else: st.error("Falha na sincronização.")

# 🟢 OS 4 PILARES MESTRES DA SUA ARQUITETURA
aba_avaliacoes, aba_fabrica, aba_turmas, aba_sala = st.tabs([
    "📚 Central de Avaliações", "🏭 Fábrica de Disciplinas", "🏫 Semestres e Turmas", "🎮 Sala de Aula (Dojo)"
])

# =========================================================================
# PILAR 1: CENTRAL DE AVALIAÇÕES
# =========================================================================
with aba_avaliacoes:
    st.header("📚 Central de Avaliações e Banco de Questões")
    
    sub_cad, sub_edit, sub_gen, sub_corr = st.tabs([
        "📝 1. Cadastrar Questão", "🔍 2. Editar Banco", "⚙️ 3. Gerar Prova (PDF)", "📸 4. Corrigir Lote"
    ])
    
    # --- SUB-ABA 1.1: CADASTRAR ---
    with sub_cad:
        if st.session_state.get('limpar_proxima_cad'):
            keys_texto = ["enun_input", "gab_input_cad"]
            for k in list(st.session_state.keys()):
                if k.startswith("t_alt_cad_") or k in keys_texto: st.session_state[k] = ""
            st.session_state.uploader_reset_cad = st.session_state.get('uploader_reset_cad', 0) + 1
            st.session_state.limpar_proxima_cad = False

        c1, c2, c3 = st.columns([0.25, 0.35, 0.4])
        with c1: t_q = st.selectbox("Tipo", ["Múltipla Escolha", "Verdadeiro ou Falso", "Discursiva", "Numérica"], key="cad_tipo")
        with c2: d_c = st.selectbox("Disciplina", ["Termodinâmica", "Mecânica dos Fluidos", "TCC 1"], key="cad_disc")
        with c3: ass_c = st.text_input("Assunto", placeholder="Ex: Ciclos Térmicos", key="cad_ass")

        c4, c5, c6, c7 = st.columns([0.2, 0.2, 0.3, 0.3])
        with c4: dif_c = st.selectbox("Dificuldade", ["Fácil", "Média", "Difícil"], key="cad_dif")
        with c5: p_c = st.number_input("Pontos", min_value=0.1, value=1.0, key="cad_pt")
        with c6: esp_c = st.selectbox("Espaço", ["Linhas", "Quadriculado", "Caixa Vazia", "Nenhum"], key="cad_esp")
        with c7: tam_c = st.number_input("Tamanho (cm)", min_value=1, value=4, key="cad_tam")

        st.write("---")
        c_e1, c_e2 = st.columns([0.85, 0.15])
        with c_e1: e_c = st.text_area("Enunciado da Questão:", key="enun_input", height=120)
        with c_e2: 
            st.write(" ")
            painel_flutuante("enun_input", "cad_enun_")

        pode_gravar = True
        if e_c.strip():
            with st.expander("👁️ Pré-visualização do Enunciado", expanded=True): st.markdown(e_c)
            id_duplicado = detectar_duplicata(e_c, d_c)
            if id_duplicado:
                st.error(f"🚫 **Questão idêntica!** Já existe no banco (ID: {id_duplicado}).")
                pode_gravar = False
            else:
                similares = buscar_questoes_proximas(e_c, d_c, limite=0.75)
                if similares:
                    st.warning(f"🔔 **Atenção:** Encontrei {len(similares)} questões muito parecidas.")
                    with st.expander("Ver similares para comparar"):
                        for s in similares[:3]: st.write(f"- ID {s['id']} ({s['percentual']:.1f}% similar): {s['texto'][:100]}...")
                    confirmar_similar = st.checkbox("Esta questão é diferente. Quero salvar mesmo assim.", key="chk_sim")
                    if not confirmar_similar: pode_gravar = False

        reset_id = st.session_state.get('uploader_reset_cad', 0)
        i_c = st.file_uploader("Upload de Imagem (Enunciado)", type=["png", "jpg", "jpeg"], key=f"up_enun_cad_{reset_id}")
        
        alts_final, gab_d_final, gab_img_final = [], None, None
        letras = "ABCDEFGHIJ"
        
        if t_q == "Múltipla Escolha":
            if "n_opt" not in st.session_state: st.session_state.n_opt = 4
            cb1, cb2 = st.columns([0.2, 0.8])
            if cb1.button("➕ Adicionar Linha"): st.session_state.n_opt += 1
            if cb2.button("➖ Remover Linha") and st.session_state.n_opt > 2: st.session_state.n_opt -= 1
            for i in range(st.session_state.n_opt):
                col_c, col_t, col_p, col_i = st.columns([0.1, 0.45, 0.15, 0.3]) 
                corr = col_c.checkbox(f"**{letras[i]}**", key=f"c_alt_cad_{i}") 
                txt = col_t.text_input(f"Alt {letras[i]}", label_visibility="collapsed", key=f"t_alt_cad_{i}")
                with col_p: painel_flutuante(f"t_alt_cad_{i}", f"p_alt_{i}_")
                img_alt = col_i.file_uploader(f"Img {letras[i]}", type=["png", "jpg", "jpeg"], key=f"i_alt_cad_{i}_{reset_id}", label_visibility="collapsed")
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
            c_g1, c_g2 = st.columns([0.85, 0.15])
            with c_g1: gab_d_final = st.text_area("Texto da Resolução", key="gab_input_cad", height=100)
            with c_g2: 
                st.write(" ")
                painel_flutuante("gab_input_cad", "cad_gab_")
            gab_img_final = st.file_uploader("Upload de Imagem (Resolução)", type=["png", "jpg", "jpeg"], key=f"gab_img_cad_{reset_id}")

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

            inserir_questao(d_c, ass_c, dif_c, e_c, alts_para_banco, p_c, t_q, gab_d_final, img_n, esp_c, tam_c, gab_img_n)
            st.success("✅ Questão guardada com sucesso!")
            st.session_state.limpar_proxima_cad = True
            st.rerun()

    # --- SUB-ABA 1.2: EDITAR BANCO ---
    with sub_edit:
        conn = sqlite3.connect('banco_provas.db')
        df_todas = pd.read_sql('SELECT id, disciplina, assunto, dificuldade, tipo, enunciado FROM questoes ORDER BY id DESC', conn)
        conn.close()

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
                id_editar = int(q_sel.split(" | ")[0].replace("ID ", ""))
                conn = sqlite3.connect('banco_provas.db')
                c = conn.cursor()
                c.execute('SELECT disciplina, assunto, dificuldade, enunciado, imagem, pontos, tipo, gabarito_discursivo, espaco_resposta, espaco_linhas, gabarito_imagem FROM questoes WHERE id=?', (id_editar,))
                q_data = c.fetchone()
                
                if q_data:
                    q_disc, q_ass, q_dif, q_enun, q_img, q_pts, q_tipo, q_gab_disc, q_esp, q_esp_l, q_gab_img = q_data

                    st.write("---")
                    c1, c2, c3 = st.columns([0.25, 0.35, 0.4])
                    with c1: n_tipo = st.selectbox("Tipo", ["Múltipla Escolha", "Verdadeiro ou Falso", "Discursiva", "Numérica"], index=["Múltipla Escolha", "Verdadeiro ou Falso", "Discursiva", "Numérica"].index(q_tipo), key="ed_tipo")
                    with c2: n_disc = st.selectbox("Disciplina", ["Termodinâmica", "Mecânica dos Fluidos", "TCC 1"], index=["Termodinâmica", "Mecânica dos Fluidos", "TCC 1"].index(q_disc) if q_disc in ["Termodinâmica", "Mecânica dos Fluidos", "TCC 1"] else 0, key="ed_disc")
                    with c3: n_ass = st.text_input("Assunto", value=q_ass if q_ass else "", key="ed_ass")

                    c4, c5, c6, c7 = st.columns([0.2, 0.2, 0.3, 0.3])
                    lista_dif = ["Fácil", "Média", "Difícil"]
                    with c4: n_dif = st.selectbox("Dificuldade", lista_dif, index=lista_dif.index(q_dif) if q_dif in lista_dif else 1, key="ed_dif")
                    with c5: n_pts = st.number_input("Pontos", min_value=0.1, value=float(q_pts), step=0.5, key="ed_pts")
                    lista_esp = ["Linhas", "Quadriculado", "Caixa Vazia", "Nenhum"]
                    with c6: n_esp = st.selectbox("Espaço", lista_esp, index=lista_esp.index(q_esp) if q_esp in lista_esp else 0, key="ed_esp")
                    with c7: n_tam = st.number_input("Tamanho (cm)", min_value=1, value=int(q_esp_l), key="ed_tam")

                    st.write("---")
                    key_enun = f"ed_enun_{id_editar}"
                    if key_enun not in st.session_state: st.session_state[key_enun] = q_enun
                    
                    c_e1, c_e2 = st.columns([0.85, 0.15])
                    with c_e1: n_enun_final = st.text_area("Enunciado da Questão:", key=key_enun, height=120)
                    with c_e2: 
                        st.write(" ")
                        painel_flutuante(key_enun, "ed_p_e_")

                    if q_img: st.caption(f"🖼️ Imagem Atual: {q_img}")
                    n_img_up = st.file_uploader("Trocar Imagem (Enunciado)", type=["png", "jpg", "jpeg"], key="ed_img_up")

                    c.execute('SELECT texto, correta, imagem FROM alternativas WHERE questao_id = ? ORDER BY id', (id_editar,))
                    alts_q = c.fetchall()
                    alts_modificadas, alts_imagens_novas = [], {}
                    gab_d_final = q_gab_disc
                    n_img_gab_up = None
                    letras = "ABCDEFGHIJ"

                    if n_tipo == "Múltipla Escolha":
                        n_opt_key = f"ed_n_opt_{id_editar}"
                        if n_opt_key not in st.session_state: st.session_state[n_opt_key] = max(len(alts_q), 4)
                        cb1, cb2 = st.columns([0.2, 0.8])
                        if cb1.button("➕ Adicionar Linha", key="ed_add_l"): st.session_state[n_opt_key] += 1
                        if cb2.button("➖ Remover Linha", key="ed_rm_l") and st.session_state[n_opt_key] > 2: st.session_state[n_opt_key] -= 1

                        for j in range(st.session_state[n_opt_key]):
                            col_c, col_t, col_p, col_i = st.columns([0.1, 0.45, 0.15, 0.3])
                            corr_val = bool(alts_q[j][1]) if j < len(alts_q) else False
                            img_atual_alt = alts_q[j][2] if j < len(alts_q) else None
                            corr = col_c.checkbox(f"**{letras[j]}**", value=corr_val, key=f"ed_c_alt_{j}")
                            key_txt_alt = f"ed_t_alt_{id_editar}_{j}"
                            if key_txt_alt not in st.session_state: st.session_state[key_txt_alt] = alts_q[j][0] if j < len(alts_q) else ""
                            txt = col_t.text_input(f"Alt {letras[j]}", label_visibility="collapsed", key=key_txt_alt)
                            with col_p: painel_flutuante(key_txt_alt, f"ed_p_alt_{j}_")
                            if img_atual_alt: col_i.caption(f"Atual: {img_atual_alt}")
                            up_img_alt = col_i.file_uploader(f"Img {letras[j]}", type=["png", "jpg", "jpeg"], key=f"ed_i_alt_{j}", label_visibility="collapsed")
                            alts_imagens_novas[j] = up_img_alt if up_img_alt else img_atual_alt
                            alts_modificadas.append((txt, corr))

                    elif n_tipo == "Verdadeiro ou Falso":
                        is_verdadeiro = any(a[0] == "Verdadeiro" and a[1] for a in alts_q)
                        resp = st.radio("Gabarito:", ["Verdadeiro", "Falso"], index=0 if is_verdadeiro else 1, horizontal=True, key="ed_vf")
                        alts_modificadas = [("Verdadeiro", resp == "Verdadeiro"), ("Falso", resp == "Falso")]
                        
                    elif n_tipo == "Numérica":
                        gab_num_atual = int(q_gab_disc) if q_gab_disc and q_gab_disc.isdigit() else 0
                        gab_num = st.number_input("Resposta Exata (0 a 99):", min_value=0, max_value=99, value=gab_num_atual, step=1, key="ed_num")
                        gab_d_final = str(gab_num).zfill(2)
                        st.info(f"Gabarito salvo como: **{gab_d_final}**")
                        if q_gab_img: st.caption(f"🖼️ Gabarito Imagem Atual: {q_gab_img}")
                        n_img_gab_up = st.file_uploader("Trocar Imagem da Resolução", type=["png", "jpg", "jpeg"], key="ed_img_gab")

                    else: # Discursiva
                        key_gab = f"ed_gab_input_{id_editar}"
                        if key_gab not in st.session_state: st.session_state[key_gab] = q_gab_disc if q_gab_disc else ""
                        c_g1, c_g2 = st.columns([0.85, 0.15])
                        with c_g1: gab_d_final = st.text_area("Gabarito da Professora", key=key_gab, height=100)
                        with c_g2: 
                            st.write(" ")
                            painel_flutuante(key_gab, "ed_p_g_")
                        if q_gab_img: st.caption(f"🖼️ Gabarito Imagem Atual: {q_gab_img}")
                        n_img_gab_up = st.file_uploader("Trocar imagem da Resolução", type=["png", "jpg", "jpeg"], key="ed_img_gab_up")

                    st.write("---")
                    c_btn1, c_btn2 = st.columns(2)
                    if c_btn1.button("💾 Salvar Alterações no Banco", type="primary", width="stretch"):
                        img_final = q_img
                        if n_img_up: 
                            img_final = sanitizar_nome(n_img_up.name)
                            with open(img_final, "wb") as f: f.write(n_img_up.getbuffer())
                        img_gab_final = q_gab_img
                        if n_img_gab_up:
                            img_gab_final = sanitizar_nome(n_img_gab_up.name)
                            with open(img_gab_final, "wb") as f: f.write(n_img_gab_up.getbuffer())

                        c.execute('''UPDATE questoes SET disciplina=?, assunto=?, dificuldade=?, enunciado=?, pontos=?, espaco_resposta=?, espaco_linhas=?, tipo=?, imagem=?, gabarito_imagem=?, gabarito_discursivo=? WHERE id=?''', (n_disc, n_ass, n_dif, n_enun_final, n_pts, n_esp, n_tam, n_tipo, img_final, img_gab_final, gab_d_final, id_editar))
                        if n_tipo in ["Múltipla Escolha", "Verdadeiro ou Falso"]:
                            c.execute('DELETE FROM alternativas WHERE questao_id = ?', (id_editar,))
                            for j, data_alt in enumerate(alts_modificadas):
                                txt_alt, corr_alt = data_alt[0], data_alt[1]
                                img_alt_bd = None
                                if n_tipo == "Múltipla Escolha":
                                    img_alt_obj = alts_imagens_novas[j]
                                    if hasattr(img_alt_obj, 'getbuffer'):
                                        img_alt_bd = sanitizar_nome(img_alt_obj.name)
                                        with open(img_alt_bd, "wb") as f: f.write(img_alt_obj.getbuffer())
                                    else: img_alt_bd = img_alt_obj
                                c.execute('INSERT INTO alternativas (questao_id, texto, correta, imagem) VALUES (?, ?, ?, ?)', (id_editar, txt_alt, corr_alt, img_alt_bd))
                        conn.commit()
                        st.success("Tudo atualizado com sucesso no banco de dados!")
                        st.rerun()

                    if c_btn2.button("🗑️ Excluir Questão (Cuidado)", width="stretch"):
                        excluir_questao(id_editar)
                        st.warning("Questão apagada definitivamente.")
                        st.rerun()

                conn.close()
        else: st.info("O seu banco de questões ainda está vazio.")

    # --- SUB-ABA 1.3: GERAR PROVA (O SEU MOTOR DE PDF) ---
    with sub_gen:
        if "arquivos" not in st.session_state: st.session_state.arquivos = []
        if "prova_atual" not in st.session_state: st.session_state.prova_atual = []

        if "cabecalho_carregado" not in st.session_state:
            st.session_state.inp_inst, st.session_state.inp_prof, st.session_state.inp_dep, st.session_state.inp_cur, st.session_state.inp_instruc = carregar_configuracoes()
            st.session_state.inp_turma, st.session_state.inp_data = "", ""
            st.session_state.cabecalho_carregado = True

        c_cab1, c_cab2 = st.columns(2)
        inst_nome = c_cab1.text_input("Instituição", key="inp_inst")
        prof_nome = c_cab2.text_input("Professor(a)", key="inp_prof")
        c_cab3, c_cab4, c_cab5 = st.columns(3)
        depto, curs, turma_p = c_cab3.text_input("Depto", key="inp_dep"), c_cab4.text_input("Curso", key="inp_cur"), c_cab5.text_input("Turma", key="inp_turma")
        c_cab6, c_cab7 = st.columns(2)
        data_p = c_cab6.text_input("Data", key="inp_data")
        titulo_doc = c_cab7.text_input("Título do Documento", value="Avaliação 01", key="inp_titulo")
        
        logo_up = st.file_uploader("Logo da Instituição (PNG/JPG)", type=["png", "jpg", "jpeg"])
        instrucoes = st.text_area("Instruções", key="inp_instruc")
        
        st.write("---")
        st.subheader("📋 Identificação dos Alunos nas Provas")
        
        modo_id = st.radio("Como deseja identificar as provas?", ["Em Branco (Sem Nome/RA)", "Usar Turma Cadastrada", "Upload Temporário de Lista"], horizontal=True)
        arquivo_lista = None
        alunos_selecionados_df = None
        q_a = 1

        if modo_id == "Em Branco (Sem Nome/RA)":
            st.info("💡 O sistema gerará cópias genéricas (ex: Versão A-001, A-002).")
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

        st.subheader("🎯 Seleção de Questões")
        col_p1, col_p2, col_p3 = st.columns(3) 
        d_p = col_p1.selectbox("Disciplina", ["Termodinâmica", "Mecânica dos Fluidos", "TCC 1"], key="g_disc")
        q_v = col_p2.number_input("Versões", 1, 10, 1)
        layout_colunas = col_p3.radio("Layout", ["1 Coluna", "2 Colunas"], horizontal=True)
        num_colunas = 2 if layout_colunas == "2 Colunas" else 1

        modo_selecao = st.radio("Modo", ["Sorteio Automático", "Escolha Manual"], horizontal=True)

        if modo_selecao == "Sorteio Automático":
            if "num_regras" not in st.session_state: st.session_state.num_regras = 1
            c_btn_r1, c_btn_r2, _ = st.columns([0.2, 0.2, 0.6])
            if c_btn_r1.button("➕ Adicionar Regra"): st.session_state.num_regras += 1; st.rerun()
            if c_btn_r2.button("➖ Remover Regra") and st.session_state.num_regras > 1: st.session_state.num_regras -= 1; st.rerun()

            regras = []
            for i in range(st.session_state.num_regras):
                c1, c2, c3, c4 = st.columns([0.15, 0.35, 0.25, 0.25])
                regras.append({
                    "qtd": c1.number_input(f"Qtd", 1, value=1, key=f"r_qtd_{i}"), 
                    "assunto": c2.selectbox(f"Assunto", obter_assuntos_da_disciplina(d_p), key=f"r_ass_{i}"), 
                    "dificuldade": c3.selectbox(f"Dif.", ["Todos", "Fácil", "Média", "Difícil"], key=f"r_dif_{i}"), 
                    "tipo": c4.selectbox(f"Tipo", ["Todos", "Múltipla Escolha", "Verdadeiro ou Falso", "Discursiva", "Numérica"], key=f"r_tip_{i}")
                })
                
            if st.button("🔍 Sortear Prova", type="primary"):
                base, usados = [], []
                for r in regras:
                    sorteadas = buscar_questoes_filtradas(d_p, r['qtd'], r['assunto'], r['dificuldade'], r['tipo'], True, usados)
                    base.extend(sorteadas)
                    usados.extend([q[0] for q in sorteadas])
                st.session_state.prova_atual = [{"id": q[0], "enunciado": q[1], "imagem": q[2], "pontos": q[3], "tipo": q[4], "gabarito": q[5], "espaco": q[6], "espaco_linhas": q[7], "dificuldade": q[8], "assunto": q[9], "gabarito_imagem": q[10]} for q in base]
                st.rerun()
        else:
            todas_q = buscar_questoes_filtradas(d_p)
            opcoes = {f"ID {q[0]} | {q[1][:60]}...": q for q in todas_q}
            sel = st.multiselect("Selecione as questões:", list(opcoes.keys()))
            if st.button("➕ Adicionar à Prova"):
                for n in sel:
                    q = opcoes[n]
                    if q[0] not in [x['id'] for x in st.session_state.prova_atual]:
                        st.session_state.prova_atual.append({"id": q[0], "enunciado": q[1], "imagem": q[2], "pontos": q[3], "tipo": q[4], "gabarito": q[5], "espaco": q[6], "espaco_linhas": q[7], "dificuldade": q[8], "assunto": q[9], "gabarito_imagem": q[10]})
                st.rerun()

        if st.session_state.prova_atual:
            st.write("---")
            st.subheader("👀 Ajustes Finos da Prova")
            pontos_totais, remover = 0, []
            for i, q in enumerate(st.session_state.prova_atual):
                with st.expander(f"Q{i+1} | {q['tipo']} | ID: {q['id']}"):
                    c_e1, c_e2 = st.columns(2)
                    novo_pt = c_e1.number_input("Pontos", value=float(q['pontos']), step=0.5, key=f"prev_pt_gen_{i}")
                    if c_e2.button("🗑️ Remover Questão", key=f"rm_p_gen_{i}"): remover.append(i)
                    pontos_totais += novo_pt

            if remover:
                for idx in sorted(remover, reverse=True): st.session_state.prova_atual.pop(idx)
                st.rerun()
            
            st.info(f"**Total de Pontos:** {pontos_totais}")
            
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
                        st.error("⚠️ Erro na Planilha! Colunas NOME e RA não identificadas.")
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
                        
                        if q_item['tipo'] == "Múltipla Escolha":
                            if opt_emb_a: alts = buscar_e_embaralhar_alternativas(q_item['id'])
                            else: alts = buscar_alternativas_originais(q_item['id'])
                            l_c, t_alts = "", []
                            for ia, (txt, corr, img_alt) in enumerate(alts): 
                                if img_alt and not os.path.exists(img_alt): img_alt = None
                                t_alts.append({"texto": escapar_latex(txt), "imagem": img_alt, "correta": corr})
                                if corr: l_c = "ABCDE"[ia]
                            d_pdf.append({"enunciado": en_s, "imagem": img_q, "pontos": q_item['pontos'], "tipo": q_item['tipo'], "alternativas": t_alts, "espaco": q_item['espaco'], "espaco_linhas": q_item['espaco_linhas'], "resposta_esperada": gab_txt, "gabarito_imagem": gab_img})
                            qr_obj[idx] = f"{l_c}|{q_item['pontos']}"
                        elif q_item['tipo'] == "Verdadeiro ou Falso":
                            alts = buscar_alternativas_originais(q_item['id']) 
                            l_c, t_alts = "", []
                            for ia, (txt, corr, img_alt) in enumerate(alts): 
                                if img_alt and not os.path.exists(img_alt): img_alt = None
                                t_alts.append({"texto": escapar_latex(txt), "imagem": img_alt, "correta": corr})
                                if corr: l_c = "V" if ia == 0 else "F" 
                            d_pdf.append({"enunciado": en_s, "imagem": img_q, "pontos": q_item['pontos'], "tipo": q_item['tipo'], "alternativas": t_alts, "espaco": q_item['espaco'], "espaco_linhas": q_item['espaco_linhas'], "resposta_esperada": gab_txt, "gabarito_imagem": gab_img})
                            qr_obj[idx] = f"{l_c}|{q_item['pontos']}"
                        elif q_item['tipo'] == "Numérica":
                            d_pdf.append({"enunciado": en_s, "imagem": img_q, "pontos": q_item['pontos'], "tipo": q_item['tipo'], "alternativas": [], "espaco": q_item['espaco'], "espaco_linhas": q_item['espaco_linhas'], "resposta_esperada": gab_txt, "gabarito_imagem": gab_img})
                            qr_obj[idx] = f"{str(q_item['gabarito']).zfill(2)}|{q_item['pontos']}"
                        else:
                            d_pdf.append({"enunciado": en_s, "imagem": img_q, "pontos": q_item['pontos'], "tipo": q_item['tipo'], "alternativas": [], "espaco": q_item['espaco'], "espaco_linhas": q_item['espaco_linhas'], "resposta_esperada": gab_txt, "gabarito_imagem": gab_img})
                            qr_obj[idx] = "DISC" 
                    
                    sufixo_arquivo = f"{sanitizar_nome(aluno_ra)}_{index}"
                    cod_secreto = f"0{v_num + 1}"
                    if modo_id == "Em Branco (Sem Nome/RA)": cod_secreto += f"-{id_unico}"
                    
                    dados_qrcode = {"ra": aluno_ra, "nome": aluno_nome, "v": let_v, "gab": qr_obj, "d": d_p}
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
                    tex_merge_provas = "\\documentclass{article}\n\\usepackage{pdfpages}\n\\begin{document}\n"
                    for p in pdfs_provas: tex_merge_provas += f"\\includepdf[pages=-]{{{p}}}\n"
                    tex_merge_provas += "\\end{document}"
                    with open("Lote_Provas_Turma.tex", 'w', encoding='utf-8') as f: f.write(tex_merge_provas)
                    if compilar_latex_mac("Lote_Provas_Turma.tex"): st.session_state.arquivos['provas'] = "Lote_Provas_Turma.pdf"

                if pdfs_gabaritos:
                    st.info("✅ Unificando gabaritos...")
                    tex_merge_gabs = "\\documentclass{article}\n\\usepackage{pdfpages}\n\\begin{document}\n"
                    for p in pdfs_gabaritos: tex_merge_gabs += f"\\includepdf[pages=-]{{{p}}}\n"
                    tex_merge_gabs += "\\end{document}"
                    with open("Lote_Gabaritos_Turma.tex", 'w', encoding='utf-8') as f: f.write(tex_merge_gabs)
                    if compilar_latex_mac("Lote_Gabaritos_Turma.tex"): st.session_state.arquivos['gabaritos'] = "Lote_Gabaritos_Turma.pdf"

                for p in pdfs_provas + pdfs_gabaritos:
                    if os.path.exists(p): os.remove(p)
                st.success("Processamento finalizado com sucesso!")
                limpar_arquivos_temporarios()

        if st.session_state.get("arquivos"):
            st.write("---")
            st.subheader("📥 Arquivos Prontos")
            c_dl1, c_dl2 = st.columns(2)
            arq_provas = st.session_state.arquivos.get('provas')
            if arq_provas and os.path.exists(arq_provas):
                with open(arq_provas, "rb") as pdf_file:
                    c_dl1.download_button(label="📄 Baixar Lote de PROVAS (Único PDF)", data=pdf_file, file_name=f"Provas_Turma_{datetime.now().strftime('%Y%m%d')}.pdf", type="primary", use_container_width=True, key="btn_dl_provas_mestre")
                    
            arq_gabs = st.session_state.arquivos.get('gabaritos')
            if arq_gabs and os.path.exists(arq_gabs):
                with open(arq_gabs, "rb") as pdf_file:
                    c_dl2.download_button(label="📝 Baixar Lote de GABARITOS (Único PDF)", data=pdf_file, file_name=f"Gabaritos_Turma_{datetime.now().strftime('%Y%m%d')}.pdf", use_container_width=True, key="btn_dl_gabs_mestre")

    # --- SUB-ABA 1.4: CORREÇÃO AUTOMÁTICA (O SEU MOTOR OPENCV) ---
    with sub_corr:
        with sqlite3.connect('banco_provas.db') as conn:
            turmas_df = pd.read_sql("SELECT id, nome FROM turmas", conn)
            if turmas_df.empty:
                st.warning("⚠️ Cadastre uma turma na aba 'Semestres e Turmas' antes de começar.")
            else:
                c_sel1, c_sel2, c_sel3 = st.columns(3)
                t_corr_nome = c_sel1.selectbox("📋 Turma:", turmas_df['nome'].tolist(), key="t_corr_final")
                id_t_corr = turmas_df[turmas_df['nome'] == t_corr_nome]['id'].values[0]
                
                discs_plan = pd.read_sql(f"SELECT DISTINCT disciplina FROM planejamento_notas WHERE turma_id = {id_t_corr}", conn)
                lista_disc_corr = discs_plan['disciplina'].tolist() if not discs_plan.empty else ["Termodinâmica", "Mecânica dos Fluidos", "TCC 1"]
                d_corr_sel = c_sel2.selectbox("📚 Disciplina:", lista_disc_corr, key="d_corr_final")
                
                df_plan = pd.read_sql(f"SELECT nome_avaliacao FROM planejamento_notas WHERE turma_id = {int(id_t_corr)} AND disciplina = '{d_corr_sel}'", conn)
                lista_ativ_plan = df_plan['nome_avaliacao'].tolist() if not df_plan.empty else []
                if lista_ativ_plan: prova_final_nome = c_sel3.selectbox("📝 Selecione a Prova:", lista_ativ_plan, key="p_corr_plan")
                else:
                    st.info("Nada planejado para esta disciplina.")
                    prova_final_nome = c_sel3.text_input("📝 Nome da Prova (Manual):", value="P1", key="p_corr_manual")

                st.write("---")
                st.markdown("⚙️ **Ajuste Fino da Leitura (Mira OpenCV)**")
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
                                    ra_m, nome_m = aluno_sel.split(" - ")
                                    dados_qr = {"ra": ra_m, "nome": nome_m, "gab": {}, "v": "A", "d": d_corr_sel}
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

                            for idx_q, (q_num, gab_val) in enumerate(sorted(gab.items(), key=lambda x: int(x[0]))):
                                certa_str, pts_q = str(gab_val).split("|")[0] if "|" in str(gab_val) else (str(gab_val), 1.0)
                                pts_q = float(pts_q)
                                y_base = ancoras_y[idx_q] if idx_q < len(ancoras_y) else ancoras_y[-1] + (38 * (idx_q - len(ancoras_y) + 1))
                                y_l, x_s = y_base - 12 + off_y, x_ancora + 65 + off_x
                                t_box = 24
                                
                                if certa_str not in ["A","B","C","D","E","V","F"]:
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
                                    qtd_b = 2 if certa_str in ["V", "F"] else 5
                                    letras_p = "VF" if certa_str in ["V", "F"] else "ABCDE"
                                    cores = [cv2.countNonZero(thresh[y_l:y_l+t_box, (x_s+j*p_x):(x_s+j*p_x)+t_box]) for j in range(qtd_b)]
                                    idx_max = int(np.argmax(cores))
                                    lido = letras_p[idx_max] if cores[idx_max] > 45 else "Branco"
                                    cv2.circle(overlay, (x_s+(idx_max*p_x)+12, y_l+12), 10, (0,255,0), -1)

                                if lido == certa_str: acertos_acumulados += pts_q
                                resumos.append({"Q": q_num, "Gabarito": certa_str, "Lido": lido, "OK": "✅" if lido == certa_str else "❌"})

                            st.image(cv2.addWeighted(overlay, 0.4, img, 0.6, 0), caption=f"🎯 Processada: {dados_qr['nome']}")
                            df_check = pd.DataFrame(resumos)
                            st.table(df_check.set_index("Q"))

                            c_n1, c_n2 = st.columns(2)
                            n_disc = c_n1.number_input(f"Nota Questões Abertas ({dados_qr['nome']}):", 0.0, 10.0, 0.0, 0.5, key=f"nd_{idx_img}")
                            nota_final_lote = acertos_acumulados + n_disc
                            c_n2.markdown(f"### 🏆 TOTAL: `{nota_final_lote:.2f}`")

                            if st.button(f"💾 Confirmar e Salvar: {dados_qr['nome']}", key=f"sv_{idx_img}"):
                                salvar_resultado_prova(dados_qr['nome'], dados_qr['ra'], d_corr_sel, dados_qr['v'], nota_final_lote, prova_final_nome)
                                st.success(f"✅ Nota de {dados_qr['nome']} enviada ao Boletim Mestre!")
                                
                        except Exception as e: st.error(f"Erro na pág {idx_img+1}: {e}")

with aba_fabrica:
    st.header("🏭 Fábrica de Disciplinas (Engenharia Pedagógica FAM)")
    
    with sqlite3.connect('banco_provas.db') as conn:
        st.markdown("### 📚 Selecione ou Crie um Molde de Disciplina")
        disciplinas_salvas = pd.read_sql("SELECT DISTINCT titulo_modelo FROM modelos_ensino", conn)['titulo_modelo'].dropna().tolist()
        
        c_d1, c_d2 = st.columns([0.6, 0.4])
        disc_selecionada = c_d1.selectbox("Modelos Salvos:", ["-- Criar Novo Molde --"] + disciplinas_salvas, key="f_sel_mestre_vFinal")
        nome_disc = c_d2.text_input("Nome da Disciplina:", value="" if disc_selecionada == "-- Criar Novo Molde --" else disc_selecionada)

        if nome_disc:
            t_ensino, t_aula = st.tabs(["📄 1. Plano de Ensino Oficial", "🧬 2. Roteiro Mestre de Aulas (FAM)"])

            with t_ensino:
                # Restauração total do Plano Mestre
                d_m = pd.read_sql(f"SELECT * FROM modelos_ensino WHERE titulo_modelo='{nome_disc}'", conn)
                def get_v(f): return d_m[f].iloc[0] if not d_m.empty and f in d_m.columns else ""
                with st.form("form_plano_mestre_completo"):
                    ementa = st.text_area("📖 Ementa:", value=get_v('ementa'), height=100)
                    c1, c2 = st.columns(2)
                    obj_g = c1.text_area("🎯 Objetivos Gerais:", value=get_v('objetivos_gerais'))
                    comp = c2.text_area("🛠️ Competências e Habilidades:", value=get_v('competencias'))
                    egr = st.text_area("🎓 Perfil do Egresso:", value=get_v('egresso'))
                    prog = st.text_area("📚 Conteúdo Programático:", value=get_v('conteudo_programatico'))
                    c3, c4 = st.columns(2)
                    meto = c3.text_area("🧪 Metodologia de Ensino:", value=get_v('metodologia'))
                    recu = c4.text_area("💻 Recursos Didáticos:", value=get_v('recursos'))
                    c5, c6 = st.columns(2)
                    aval = c5.text_area("📝 Sistema de Avaliação:", value=get_v('avaliacao'))
                    aps_mestre = c6.text_area("🔬 Atividades Práticas (APS):", value=get_v('aps'))
                    bib_b = st.text_area("📚 Referência Básica:", value=get_v('bib_basica'))
                    bib_c = st.text_area("📚 Referência Complementar:", value=get_v('bib_complementar'))
                    orf_f = st.text_area("📚 Outras Referências:", value=get_v('outras_ref'))
                    if st.form_submit_button("💾 Salvar Plano de Ensino Mestre", type="primary"):
                        conn.execute("DELETE FROM modelos_ensino WHERE titulo_modelo=?", (nome_disc,))
                        conn.execute("INSERT INTO modelos_ensino (titulo_modelo, ementa, objetivos_gerais, competencias, egresso, conteudo_programatico, metodologia, recursos, avaliacao, aps, bib_basica, bib_complementar, outras_ref) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", (nome_disc, ementa, obj_g, comp, egr, prog, meto, recu, aval, aps_mestre, bib_b, bib_c, orf_f))
                        conn.commit(); st.rerun()

            with t_aula:
                st.markdown(f"#### 🧬 Detalhamento da Sequência de Aulas")
                df_aulas = pd.read_sql(f"SELECT num_aula as Aula, tema as Tema FROM roteiro_mestre WHERE titulo_modelo='{nome_disc}' ORDER BY num_aula", conn)
                ed_aulas = st.data_editor(df_aulas, num_rows="dynamic", use_container_width=True, key=f"ed_roteiro_vFinal_{nome_disc}")
                if st.button("💾 Atualizar Lista de Aulas"):
                    for _, r in ed_aulas.iterrows():
                        check = conn.execute("SELECT id FROM roteiro_mestre WHERE titulo_modelo=? AND num_aula=?", (nome_disc, r['Aula'])).fetchone()
                        if not check: conn.execute("INSERT INTO roteiro_mestre (titulo_modelo, num_aula, tema) VALUES (?,?,?)", (nome_disc, r['Aula'], r['Tema']))
                    conn.commit(); st.rerun()

                st.write("---")
                a_det = st.selectbox("Selecione a aula para detalhar o Roteiro FAM:", df_aulas['Aula'].tolist() if not df_aulas.empty else [])
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
                        
                        st.markdown("#### 🔗 Gestão de Arquivos e Links")
                        cl1, cl2, cl3 = st.columns(3)
                        l_slides = cl1.text_input("📂 Link dos Slides:", value=d_a.get('link_slides') or "")
                        l_over = cl2.text_input("📝 Link Overleaf:", value=d_a.get('link_overleaf') or "")
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
    st.header("🏫 Gestão de Semestres e Turmas")
    
    with sqlite3.connect('banco_provas.db') as conn:
        st.markdown("### 📅 Filtrar Operação por Semestre")
        
        semestres_existentes = pd.read_sql("SELECT DISTINCT semestre FROM turmas", conn)['semestre'].dropna().tolist()
        if "2026.1" not in semestres_existentes: semestres_existentes.append("2026.1")
        
        semestre_ativo = st.selectbox("Selecione o Semestre Letivo:", sorted(semestres_existentes, reverse=True), label_visibility="collapsed")
        st.write("---")

        with st.expander("➕ Criar Nova Turma ou Importar Alunos (Base)", expanded=False):
            col_t1, col_t2 = st.columns(2)
            with col_t1:
                st.write("**Criar Turma**")
                n_t = st.text_input("Nome da Turma:", placeholder="Ex: Eng. Mecânica - Noturno")
                n_sem = st.text_input("Semestre de Criação:", value=semestre_ativo)
                if st.button("Criar Turma", use_container_width=True) and n_t:
                    try:
                        conn.execute('INSERT INTO turmas (nome, semestre) VALUES (?, ?)', (n_t, n_sem))
                        conn.commit(); st.success("Turma criada!"); st.rerun()
                    except: st.error("Turma já existe com este nome.")
            
            with col_t2:
                t_db_filtrado = pd.read_sql(f"SELECT * FROM turmas WHERE semestre='{semestre_ativo}'", conn)
                if not t_db_filtrado.empty:
                    st.write("**Importar Lista de Alunos (Excel/CSV)**")
                    t_up = st.selectbox("Turma de Destino:", t_db_filtrado['nome'].tolist())
                    id_up = t_db_filtrado[t_db_filtrado['nome'] == t_up]['id'].values[0]
                    arq = st.file_uploader("Arquivo (NOME e RA):", type=['xlsx', 'csv'])
                    if st.button("Importar", use_container_width=True) and arq:
                        df = pd.read_excel(arq) if arq.name.endswith('.xlsx') else pd.read_csv(arq, sep=None, engine='python')
                        df.columns = df.columns.str.strip().str.upper()
                        c_n = next((c for c in df.columns if c in ['NOME', 'ALUNO']), None)
                        c_r = next((c for c in df.columns if c in ['RA', 'MATRICULA']), None)
                        if c_n and c_r:
                            cursor = conn.cursor()
                            cursor.execute('SELECT ra FROM alunos WHERE turma_id = ?', (int(id_up),))
                            exist = [r[0] for r in cursor.fetchall()]
                            for _, row in df.dropna(subset=[c_n, c_r]).iterrows():
                                ra = str(row[c_r]).replace('.0', '').strip()
                                if ra not in exist:
                                    cursor.execute('INSERT INTO alunos (turma_id, nome, ra) VALUES (?, ?, ?)', (int(id_up), str(row[c_n]).strip(), ra))
                            conn.commit(); st.success("Alunos base importados!")

        t_db_ativa = pd.read_sql(f"SELECT * FROM turmas WHERE semestre='{semestre_ativo}'", conn)
        
        if t_db_ativa.empty:
            st.info(f"Nenhuma turma cadastrada no semestre {semestre_ativo}. Crie uma acima.")
        else:
            col_nav1, col_nav2 = st.columns([0.4, 0.6])
            t_ativa = col_nav1.selectbox("📍 Turma:", t_db_ativa['nome'].tolist())
            id_t_ativa = t_db_ativa[t_db_ativa['nome'] == t_ativa]['id'].values[0]
            
            modelos_disponiveis = pd.read_sql("SELECT DISTINCT titulo_modelo FROM modelos_ensino", conn)['titulo_modelo'].dropna().tolist()
            
            if not modelos_disponiveis:
                st.warning("⚠️ Você precisa criar um Molde de Disciplina na 'Fábrica' antes de operar uma Turma.")
            else:
                d_ativa = col_nav2.selectbox("📚 Disciplina cursada nesta turma:", modelos_disponiveis)
                
                sub_mat, sub_cron, sub_pesos, sub_boletim = st.tabs([
                    "🎓 1. Matrículas", "🗓️ 2. Cronograma Real", "⚖️ 3. Pesos de Notas", "📊 4. Boletim Mestre"
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
                        st.markdown("### 📋 Lista de Alunos e Anotações Pedagógicas")
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

                with sub_cron:
                    import holidays
                    st.markdown("### 🗓️ Planejador FAM: 20 Aulas e Eventos Fixos")
                    
                    # --- PASSO 1: CALENDÁRIO E DATAS FIXAS ---
                    with st.container(border=True):
                        st.markdown("#### 📅 Passo 1: Calendário e Provas")
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

                    # --- PASSO 2: MAPEADOR DE CONTEÚDO (VINCULAR FÁBRICA) ---
                    key_temp = f"temp_cron_{id_t_ativa}"
                    if key_temp in st.session_state:
                        st.write("---")
                        c_p2_1, c_p2_2 = st.columns([0.7, 0.3])
                        c_p2_1.markdown(f"#### 📝 Passo 2: Distribuir Conteúdo FAM")
                        
                        # --- NOVO BOTÃO DE LIMPAR ---
                        if c_p2_2.button("🗑️ Reiniciar Grade", use_container_width=True, help="Apaga o rascunho acima para gerar novas datas"):
                            del st.session_state[key_temp]
                            st.rerun()
                        
                        df_fab = pd.read_sql(f"SELECT num_aula, tema FROM roteiro_mestre WHERE titulo_modelo='{d_ativa}' ORDER BY num_aula", conn)
                        dict_fab = {f"Aula {row['num_aula']}: {row['tema']}": row['num_aula'] for _, row in df_fab.iterrows()}
                        opcoes_fab = ["-- Selecionar --", "Aula Extra / Revisão", "Prova N1", "Prova N2", "Prova N3", "Exame AR"] + list(dict_fab.keys())

                        if st.button("⚡ Preenchimento Sequencial Automático"):
                            ponteiro = 0
                            for i, _ in enumerate(st.session_state[key_temp]):
                                if any(x in st.session_state[key_temp][i]['tema_origem'] for x in ["Prova", "Exame", "AR"]): continue
                                if ponteiro < len(df_fab):
                                    st.session_state[key_temp][i]['tema_origem'] = f"Aula {df_fab.iloc[ponteiro]['num_aula']}: {df_fab.iloc[ponteiro]['tema']}"
                                    ponteiro += 1
                            st.rerun()

                        for idx, aula in enumerate(st.session_state[key_temp]):
                            with st.container(border=True):
                                c_d, c_s = st.columns([0.3, 0.7])
                                cor = "red" if any(x in aula['tema_origem'] for x in ["Prova", "Exame", "AR"]) else "blue"
                                c_d.markdown(f"<b style='color:{cor};'>Aula {aula['num_aula']} ({aula['data']})</b>", unsafe_allow_html=True)
                                st.session_state[key_temp][idx]['tema_origem'] = c_s.selectbox(f"Conteúdo para {aula['data']}:", options=opcoes_fab, 
                                                        index=opcoes_fab.index(aula['tema_origem']) if aula['tema_origem'] in opcoes_fab else 0,
                                                        key=f"mapeador_vFinal_{idx}")

                        if st.button("🚀 CONSOLIDAR E SALVAR CRONOGRAMA", type="primary", use_container_width=True):
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

                    # --- PASSO 3: PLANO DE AULA REAL ---
                    st.write("---")
                    st.markdown(f"### 🔍 Plano de aula real: {d_ativa}")
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
                                    
                                    st.markdown("**📂 Materiais:**")
                                    b1, b2, b3 = st.columns(3)
                                    n_ls = b1.text_input("Link Slides:", value=row['link_slides'] or "", key=f"v_ls_{idx}_vF")
                                    n_lo = b2.text_input("Link Overleaf:", value=row['link_overleaf'] or "", key=f"v_lo_{idx}_vF")
                                    n_le = b3.text_input("Extras:", value=row['link_extras'] or "", key=f"v_le_{idx}_vF")
                                    
                                    cb1, cb2, cb3 = st.columns(3)
                                    if n_ls: cb1.link_button("📂 Abrir Slides", n_ls, use_container_width=True)
                                    if n_lo: cb2.link_button("📝 Abrir Overleaf", n_lo, use_container_width=True, type="primary")
                                    if n_le: cb3.link_button("🌐 Link Extra", n_le, use_container_width=True)

                                    st.markdown("**💬 Atividade e Fórum do Dia:**")
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
                                    st.markdown("**🖋️ Diário Real:**")
                                    if pd.notna(row['conteudo_real']): st.success(row['conteudo_real'])
                                    else: st.info("Aguardando registro.")

                                st.write("---")
                                c_btn1, c_btn2, c_btn3 = st.columns([0.4, 0.4, 0.2])
                                sync = c_btn1.checkbox("🔄 Sincronizar na FÁBRICA", key=f"sy_{idx}_vF")
                                if c_btn2.button(f"💾 Salvar Aula {row['num_aula']}", key=f"bs_{idx}_vF", type="primary"):
                                    conn.execute("UPDATE cronograma_detalhado SET tema=?, tipo_aula=?, objetivos_aula=?, conteudo_detalhado=?, metodologia=?, aps_aula=?, link_slides=?, link_overleaf=?, link_extras=?, atividades=?, atividades_link=?, forum=?, forum_link=?, referencias_aula=? WHERE id=?", (n_t, n_tp, n_obj, n_cont, n_m, n_a, n_ls, n_lo, n_le, n_at_t, n_at_l, n_ft_t, n_ft_l, n_ref, row['id']))
                                    if sync: conn.execute("UPDATE roteiro_mestre SET tema=?, tipo_aula=?, objetivos_aula=?, conteudo_detalhado=?, metodologia=?, aps_aula=?, link_slides=?, link_overleaf=?, link_extras=?, atividades=?, atividades_link=?, forum=?, forum_link=?, referencias_aula=? WHERE titulo_modelo=? AND num_aula=?", (n_t, n_tp, n_obj, n_cont, n_m, n_a, n_ls, n_lo, n_le, n_at_t, n_at_l, n_ft_t, n_ft_l, n_ref, d_ativa, row['num_aula']))
                                    conn.commit(); st.toast("Salvo!"); st.rerun()
                                if c_btn3.button("🗑️ Deletar", key=f"bd_{idx}_vF"):
                                    conn.execute("DELETE FROM cronograma_detalhado WHERE id=?", (row['id'],)); conn.commit(); st.rerun()
                    else:
                        st.info("Utilize o Passo 1 para mapear as datas.")

                # =========================================================================
                # ✏️ 3. AVALIAÇÕES E LANÇAMENTO MANUAL DE NOTAS
                # =========================================================================
                # =========================================================================
                # ✏️ 3. AVALIAÇÕES E LANÇAMENTO DE NOTAS (TOTALMENTE ORGÂNICO)
                # =========================================================================
                with sub_pesos:
                    st.markdown("### 📊 Central Dinâmica de Notas e Médias")
                    
                    # 0. Busca prévia das atividades do Dojo para automatizar a quantidade
                    df_ativ_sala = pd.read_sql(f"SELECT data, aluno_ra as Matrícula, entregou FROM atividades_sala WHERE turma_id={id_t_ativa} AND disciplina='{d_ativa}' ORDER BY data", conn)
                    datas_unicas = df_ativ_sala['data'].unique() if not df_ativ_sala.empty else []
                    qtd_aulas_registradas = len(datas_unicas)

                    # 1. Configuração Parametrizada
                    with st.expander("⚙️ Configurar Avaliações (Nomes, Qtds, Pesos e Cortes)", expanded=False):
                        st.info("💡 As Atividades em Sala crescem sozinhas conforme você usa o Dojo. O descarte das piores notas (%) garante a tolerância de faltas.")
                        
                        col1, col2, col3, col4 = st.columns(4)
                        with col1:
                            st.markdown("**Provas Oficiais**")
                            n_p = st.text_input("Nome:", "Prova N", key="n_p")
                            q_p = st.number_input("Quantidade:", 0, 10, 2, key="q_p")
                            w_p = st.number_input("Peso Final (%):", 0, 100, 60, key="w_p")
                            c_p = st.number_input("Descartar Piores (%):", 0, 99, 0, step=5, key="corte_p", help="0 = Não descarta nenhuma.")
                        with col2:
                            st.markdown("**Listas / Exercícios**")
                            n_l = st.text_input("Nome:", "Lista", key="n_l")
                            q_l = st.number_input("Quantidade:", 0, 20, 3, key="q_l")
                            w_l = st.number_input("Peso Final (%):", 0, 100, 10, key="w_l")
                            c_l = st.number_input("Descartar Piores (%):", 0, 99, 0, step=5, key="corte_l")
                        with col3:
                            st.markdown("**Laboratório / Prática**")
                            n_lb = st.text_input("Nome:", "Lab", key="n_lb")
                            q_lb = st.number_input("Quantidade:", 0, 20, 2, key="q_lb")
                            w_lb = st.number_input("Peso Final (%):", 0, 100, 20, key="w_lb")
                            c_lb = st.number_input("Descartar Piores (%):", 0, 99, 0, step=5, key="corte_lb")
                        with col4:
                            st.markdown("**Ativ. em Sala (Dojo)**")
                            n_a = st.text_input("Prefixo:", "Ativ", key="n_a")
                            st.markdown(f"<div style='margin-bottom: 15px; color: #7f8c8d; font-size: 14px;'><i>{qtd_aulas_registradas} datas registradas</i></div>", unsafe_allow_html=True)
                            w_a = st.number_input("Peso Final (%):", 0, 100, 10, key="w_a")
                            c_a = st.number_input("Descartar Piores (%):", 0, 99, 25, step=5, key="corte_a")
                            
                        soma_pesos = w_p + w_l + w_lb + w_a
                        if soma_pesos != 100:
                            st.warning(f"⚠️ Atenção: A soma dos pesos está em {soma_pesos}%. O ideal é 100%.")

                    # 2. Definição Dinâmica das Colunas (A mágica do nome com data)
                    cols_provas = [f"{n_p}{i+1}" if n_p.endswith(" ") else f"{n_p} {i+1}" for i in range(int(q_p))]
                    cols_listas = [f"{n_l} {i+1}" for i in range(int(q_l))]
                    cols_labs =   [f"{n_lb} {i+1}" for i in range(int(q_lb))]
                    # Aqui criamos a coluna com a data visível para você não se perder
                    cols_ativs =  [f"{n_a} {i+1} ({dt[:5]})" for i, dt in enumerate(datas_unicas)]
                    
                    todas_cols_entrada = cols_provas + cols_listas + cols_labs + cols_ativs

                    # 3. Leitura dos Alunos
                    df_alunos = pd.read_sql(f"""
                        SELECT a.ra as Matrícula, a.nome as Nome 
                        FROM alunos a 
                        JOIN matriculas_disciplina m ON a.id = m.aluno_id 
                        WHERE m.turma_id={id_t_ativa} AND m.disciplina='{d_ativa}' 
                        ORDER BY a.nome
                    """, conn)

                    if df_alunos.empty:
                        st.warning("Não há alunos matriculados nesta disciplina.")
                    else:
                        # 4. Leitura do Banco Relacional e Merge
                        conn.execute("""
                            CREATE TABLE IF NOT EXISTS notas_flexiveis (
                                id INTEGER PRIMARY KEY AUTOINCREMENT,
                                turma_id INTEGER,
                                disciplina TEXT,
                                matricula TEXT,
                                avaliacao TEXT,
                                nota REAL
                            )
                        """)
                        df_notas_banco = pd.read_sql(f"SELECT matricula as Matrícula, avaliacao, nota FROM notas_flexiveis WHERE turma_id={id_t_ativa} AND disciplina='{d_ativa}'", conn)
                        
                        if not df_notas_banco.empty:
                            df_pivot = df_notas_banco.pivot_table(index='Matrícula', columns='avaliacao', values='nota', aggfunc='max').reset_index()
                            df_atual = pd.merge(df_alunos, df_pivot, on="Matrícula", how="left")
                        else:
                            df_atual = df_alunos.copy()

                        # --- A PONTE COM O DOJO (ATIVIDADES DE SALA) ---
                        if qtd_aulas_registradas > 0:
                            for i, data_ativ in enumerate(datas_unicas):
                                nome_coluna = cols_ativs[i]
                                notas_do_dia = df_ativ_sala[df_ativ_sala['data'] == data_ativ].copy()
                                notas_do_dia['nota_convertida'] = notas_do_dia['entregou'].apply(lambda x: 10.0 if x == 1 else 0.0)
                                mapa_notas = dict(zip(notas_do_dia['Matrícula'], notas_do_dia['nota_convertida']))
                                df_atual[nome_coluna] = df_atual['Matrícula'].map(mapa_notas).fillna(0.0)
                            
                        # Preenche colunas vazias
                        for col in todas_cols_entrada:
                            if col not in df_atual.columns: df_atual[col] = 0.0
                            df_atual[col] = pd.to_numeric(df_atual[col], errors='coerce').fillna(0.0)

                        # 5. Motor Matemático Universal
                        df_calc = df_atual.copy()
                        
                        nome_med_p = f"Média {n_p}" + (f" (-{c_p}%)" if c_p > 0 else "")
                        nome_med_l = f"Média {n_l}" + (f" (-{c_l}%)" if c_l > 0 else "")
                        nome_med_lb = f"Média {n_lb}" + (f" (-{c_lb}%)" if c_lb > 0 else "")
                        nome_med_a = f"Média {n_a}" + (f" (-{c_a}%)" if c_a > 0 else "")

                        def calc_media_com_corte(row, colunas_alvo, percentual_corte):
                            if not colunas_alvo: return 0.0
                            notas = row[colunas_alvo].tolist()
                            notas.sort(reverse=True)
                            if percentual_corte > 0:
                                manter = max(1, int(len(notas) * (1 - (percentual_corte / 100.0))))
                                notas_validas = notas[:manter]
                            else:
                                notas_validas = notas
                            return sum(notas_validas) / len(notas_validas) if notas_validas else 0.0

                        df_calc[nome_med_p] = df_calc.apply(lambda r: calc_media_com_corte(r, cols_provas, c_p), axis=1).round(2)
                        df_calc[nome_med_l] = df_calc.apply(lambda r: calc_media_com_corte(r, cols_listas, c_l), axis=1).round(2)
                        df_calc[nome_med_lb] = df_calc.apply(lambda r: calc_media_com_corte(r, cols_labs, c_lb), axis=1).round(2)
                        df_calc[nome_med_a] = df_calc.apply(lambda r: calc_media_com_corte(r, cols_ativs, c_a), axis=1).round(2)
                            
                        df_calc["MÉDIA FINAL"] = (
                            (df_calc[nome_med_p] * (w_p / 100.0)) +
                            (df_calc[nome_med_l] * (w_l / 100.0)) +
                            (df_calc[nome_med_lb] * (w_lb / 100.0)) +
                            (df_calc[nome_med_a] * (w_a / 100.0))
                        ).round(2)

                        # 6. Abas de Lançamento
                        t_manual, t_excel, t_auto = st.tabs(["✍️ Planilha Mestre", "📊 Importar Excel", "🤖 Corretor Automático"])

                        with t_manual:
                            st.caption("As colunas de 'Ativ' são criadas automaticamente e puxam os dados 100% da Aba Sala. O descarte opera silenciosamente nas médias em cinza.")
                            
                            colunas_display = ["Matrícula", "Nome"]
                            if cols_provas: colunas_display += cols_provas + [nome_med_p]
                            if cols_listas: colunas_display += cols_listas + [nome_med_l]
                            if cols_labs: colunas_display += cols_labs + [nome_med_lb]
                            if cols_ativs: colunas_display += cols_ativs + [nome_med_a]
                            colunas_display += ["MÉDIA FINAL"]
                            
                            col_config = {"Matrícula": st.column_config.TextColumn(disabled=True), "Nome": st.column_config.TextColumn(disabled=True)}
                            for col in [nome_med_p, nome_med_l, nome_med_lb, nome_med_a, "MÉDIA FINAL"]:
                                col_config[col] = st.column_config.NumberColumn(disabled=True, format="%.2f")
                                
                            for col in cols_ativs:
                                col_config[col] = st.column_config.NumberColumn(disabled=True, help="Registrado via Aba Sala (Dojo)")
                                
                            df_editado = st.data_editor(
                                df_calc[colunas_display],
                                column_config=col_config,
                                use_container_width=True,
                                hide_index=True,
                                key="editor_notas_dinamico_v4"
                            )
                            
                            if st.button("💾 Salvar Planilha Inteira", type="primary", use_container_width=True):
                                conn.execute("DELETE FROM notas_flexiveis WHERE turma_id=? AND disciplina=?", (int(id_t_ativa), d_ativa))
                                for _, row in df_editado.iterrows():
                                    mat = row['Matrícula']
                                    for col in todas_cols_entrada:
                                        if col in cols_ativs: continue # Não reescrevemos o que vem da sala
                                        
                                        val = row.get(col, 0.0)
                                        if pd.notna(val):
                                            conn.execute("INSERT INTO notas_flexiveis (turma_id, disciplina, matricula, avaliacao, nota) VALUES (?,?,?,?,?)", 
                                                         (int(id_t_ativa), d_ativa, mat, col, float(val)))
                                conn.commit()
                                st.success("Notas atualizadas e processadas!")
                                st.rerun()

                        with t_excel:
                            st.markdown("#### Importação em Massa (Excel/CSV)")
                            st.info("A planilha deve conter a coluna 'Matrícula' e o nome exato das avaliações configuradas.")
                            arquivo = st.file_uploader("Subir arquivo:", type=["xlsx", "csv"])
                            if arquivo:
                                st.warning("Conector de Excel pronto para ser ativado.")
                                
                        with t_auto:
                            st.markdown("#### Integração: Leitor de Cartão Resposta")
                            sel_p = st.selectbox("Qual prova deseja preencher automaticamente?", cols_provas if cols_provas else ["Nenhuma prova configurada"])
                            if st.button("🔄 Puxar Gabaritos"):
                                st.warning(f"Conector do Leitor aguardando dados para {sel_p}.")

                with sub_boletim:
                    st.markdown(f"### 📊 Boletim Mestre: {t_ativa} - {d_ativa}")
                    
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
                        
                        try: df_provas_raw = pd.read_sql(f"SELECT aluno_ra as RA, avaliacao, nota FROM resultados WHERE disciplina = '{d_ativa}'", conn)
                        except: df_provas_raw = pd.DataFrame()
                            
                        provas_cols = []
                        if not df_provas_raw.empty:
                            df_provas = df_provas_raw.pivot_table(index='RA', columns='avaliacao', values='nota', aggfunc='max').reset_index()
                            provas_cols = [c for c in df_provas.columns if c != 'RA']
                        else: df_provas = pd.DataFrame(columns=['RA'])
                        
                        df_trab_raw = pd.read_sql(f"SELECT aluno_ra as RA, nome_atividade, nota FROM trabalhos_extras WHERE turma_id = {id_t_ativa} AND disciplina = '{d_ativa}'", conn)
                        trab_cols = []
                        if not df_trab_raw.empty:
                            df_trab = df_trab_raw.pivot_table(index='RA', columns='nome_atividade', values='nota', aggfunc='max').reset_index()
                            trab_cols = [c for c in df_trab.columns if c != 'RA']
                        else: df_trab = pd.DataFrame(columns=['RA'])
                            
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
                        df = pd.merge(df, df_provas, on='RA', how='left')
                        df = pd.merge(df, df_trab, on='RA', how='left')
                        df = pd.merge(df, df_diario, on='RA', how='left')
                        df = pd.merge(df, df_dojo, on='RA', how='left')
                        
                        df['Total_Aulas'] = df['Total_Aulas'].fillna(0).astype(int)
                        df['Presentes'] = df['Presentes'].fillna(0).astype(int)
                        df['Atrasos'] = df['Atrasos'].fillna(0).astype(int)
                        df['Faltas'] = df['Faltas'].fillna(0).astype(int)
                        df['Saldo_Dojo'] = df['Saldo_Dojo'].fillna(0.0)
                        df['Positivos'] = df['Positivos'].fillna(0.0)
                        df['Negativos'] = df['Negativos'].fillna(0.0)
                        
                        df_pesos_plan = pd.read_sql(f"SELECT nome_avaliacao, peso FROM planejamento_notas WHERE turma_id = {id_t_ativa} AND disciplina = '{d_ativa}'", conn)
                        pesos = dict(zip(df_pesos_plan['nome_avaliacao'], df_pesos_plan['peso'])) if not df_pesos_plan.empty else {}
                        
                        # 🛠️ CORREÇÃO: Forçamos a soma a nascer como uma coluna (Series) do Pandas!
                        nota_ponderada_soma = pd.Series(0.0, index=df.index)
                        soma_dos_pesos = 0.0
                        
                        for p in provas_cols:
                            df[p] = df[p].fillna(0.0)
                            peso_atual = pesos.get(p, 1.0) 
                            nota_ponderada_soma += df[p] * peso_atual
                            soma_dos_pesos += peso_atual
                            
                        for t in trab_cols:
                            df[t] = df[t].fillna(0.0)
                            peso_atual = pesos.get(t, 1.0)
                            nota_ponderada_soma += df[t] * peso_atual
                            soma_dos_pesos += peso_atual
                        
                        if soma_dos_pesos == 0: soma_dos_pesos = 1
                        df['Média_Parcial'] = (nota_ponderada_soma / soma_dos_pesos).clip(upper=10.0)
                        df['Frequencia_%'] = df.apply(lambda x: (((x['Presentes'] + x['Atrasos']) / x['Total_Aulas']) * 100) if x['Total_Aulas'] > 0 else 100.0, axis=1)
                        
                        if aluno_sel != "Visão Geral da Turma": df = df[df['Aluno'] == aluno_sel]
                        
                        st.write("---")
                        col_chart, col_metrics = st.columns([0.4, 0.6])
                        
                        with col_chart:
                            total_pos = df['Positivos'].sum()
                            total_neg = df['Negativos'].sum()
                            
                            if total_pos + total_neg > 0:
                                fig = px.pie(values=[total_pos, total_neg], names=['Positivos', 'A Melhorar'], color=['Positivos', 'A Melhorar'], color_discrete_map={'Positivos':'#2ecc71', 'A Melhorar':'#e74c3c'}, hole=0.65)
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
                        colunas_mostrar = ['Aluno', 'RA']
                        if provas_cols: colunas_mostrar.extend(provas_cols)
                        if trab_cols: colunas_mostrar.extend(trab_cols)
                        colunas_mostrar.extend(['Média_Parcial', 'Frequencia_%', 'Presentes', 'Atrasos', 'Faltas', 'Saldo_Dojo'])
                        
                        df_tabela = df[colunas_mostrar].round(2).copy()
                        df_tabela = df_tabela.rename(columns={"Média_Parcial": "Média Acadêmica", "Frequencia_%": "Freq. %", "Saldo_Dojo": "⭐ Saldo Dojo"})
                        
                        st.dataframe(df_tabela, width="stretch", hide_index=True)
                        
                        nome_arquivo = f"Boletim_{semestre_ativo}_{t_ativa}_{d_ativa}.csv"
                        csv = df_tabela.to_csv(index=False).encode('utf-8-sig')
                        st.download_button("📥 Exportar Boletim em Excel", csv, nome_arquivo, "text/csv", type="primary")

# =========================================================================
# PILAR 4: GESTÃO DE AULA - VERSÃO FINAL (INCLUINDO ATIVIDADES DE SALA)
# =========================================================================
with aba_sala:
    # 🛡️ PROTEÇÃO DE PRIVACIDADE
    c_p1, c_p2 = st.columns([0.7, 0.3])
    with c_p2:
        modo_projetor = st.toggle("📽️ Modo Projetor", value=True)

    st.subheader("🎮 Gestão de Aula e Diário Pedagógico")
    
    with sqlite3.connect('banco_provas.db') as conn:
        # Criação das tabelas necessárias
        conn.execute('''CREATE TABLE IF NOT EXISTS diario_conteudo (id INTEGER PRIMARY KEY, turma_id INTEGER, disciplina TEXT, data TEXT, conteudo_real TEXT, observacao TEXT)''')
        conn.execute('''CREATE TABLE IF NOT EXISTS atividades_sala (id INTEGER PRIMARY KEY, turma_id INTEGER, disciplina TEXT, data TEXT, aluno_ra TEXT, entregou INTEGER)''')
        
        semestres_db = pd.read_sql("SELECT DISTINCT semestre FROM turmas ORDER BY semestre DESC", conn)
        sem_hj = semestres_db['semestre'].iloc[0] if not semestres_db.empty else "2026.1"
        turmas_df = pd.read_sql(f"SELECT id, nome FROM turmas WHERE semestre='{sem_hj}'", conn)
        
        if turmas_df.empty:
            st.info("Cadastre uma turma primeiro.")
        else:
            # 1. SELEÇÃO GLOBAL (Turma -> Disciplina -> Data)
            c_s1, c_s2, c_s3 = st.columns([0.35, 0.45, 0.20])
            t_aula_nome = c_s1.selectbox("📍 Turma:", ["-- Escolha --"] + turmas_df['nome'].tolist(), key="final_t_sel")
            
            if t_aula_nome != "-- Escolha --":
                id_t_aula = int(turmas_df[turmas_df['nome'] == t_aula_nome]['id'].values[0])
                discs_turma = pd.read_sql(f"SELECT DISTINCT disciplina FROM matriculas_disciplina WHERE turma_id={id_t_aula}", conn)
                lista_discs = discs_turma['disciplina'].tolist() if not discs_turma.empty else ["Nenhuma"]
                disc_aula = c_s2.selectbox("📚 Disciplina:", ["-- Escolha --"] + lista_discs, key="final_d_sel")

                if disc_aula != "-- Escolha --":
                    # Data Global para toda a operação da sala
                    data_aula_global = c_s3.date_input("📅 Data:", datetime.today(), key="data_global_sala")
                    data_str_global = data_aula_global.strftime("%d/%m/%Y")

                    # --- 2. SENSORES E TIMER (COM DESBLOQUEIO DE ÁUDIO E SOM SUAVE) ---
                    st.write("---")
                    col_t1, col_t2 = st.columns([0.4, 0.6])
                    with col_t1:
                        st.markdown("### ⏱️ Cronômetro")
                        t_min = st.number_input("Minutos para atividade:", 1, 120, 15, key="sala_t_min")
                        
                        c_t_btn1, c_t_btn2 = st.columns(2)
                        if c_t_btn1.button("🚀 Iniciar", use_container_width=True, key="btn_timer_iniciar"):
                            st.session_state['timer_end'] = datetime.now().timestamp() + (t_min * 60)
                            st.rerun()
                        if c_t_btn2.button("⏹️ Parar", use_container_width=True, key="btn_timer_parar"):
                            if 'timer_end' in st.session_state:
                                del st.session_state['timer_end']
                            st.rerun()
                            
                        if 'timer_end' in st.session_state:
                            end_time = st.session_state['timer_end']
                            html_timer = f"""
                            <div style="text-align: center; background: #f0f2f6; padding: 10px; border-radius: 10px; margin-top: 5px; box-shadow: inset 0px 0px 5px rgba(0,0,0,0.1); position: relative;">
                                <div id="timer_display" style="font-size: 45px; font-weight: bold; color: #2c3e50; font-family: monospace;">
                                    --:--
                                </div>
                                <button id="btn_som" onclick="initAudio()" style="position: absolute; top: 5px; right: 5px; background: #3498db; color: white; border: none; border-radius: 5px; padding: 5px 10px; cursor: pointer; font-size: 12px; font-weight: bold; box-shadow: 0px 2px 4px rgba(0,0,0,0.2);">🔊 Permitir Som</button>
                            </div>
                            <script>
                            const display = document.getElementById("timer_display");
                            const btnSom = document.getElementById("btn_som");
                            let endTime = {end_time};
                            let alertaTocado = false;
                            let ac = null;
                            
                            function initAudio() {{
                                window.AudioContext = window.AudioContext || window.webkitAudioContext;
                                ac = new AudioContext();
                                let osc = ac.createOscillator();
                                osc.connect(ac.destination);
                                osc.start(ac.currentTime);
                                osc.stop(ac.currentTime + 0.01);
                                btnSom.innerText = "✅ Áudio OK";
                                btnSom.style.background = "#2ecc71";
                                setTimeout(() => btnSom.style.display = "none", 1500);
                            }}
                            
                            function tocarAlarme() {{
                                if (!ac) {{
                                    window.AudioContext = window.AudioContext || window.webkitAudioContext;
                                    ac = new AudioContext();
                                }}
                                if (ac.state === 'suspended') ac.resume();
                                
                                // Função para criar um som de sino suave (sine wave)
                                function tocarDing(frequencia, tempoInicio) {{
                                    let os = ac.createOscillator();
                                    let gainNode = ac.createGain();
                                    
                                    os.type = 'sine'; // Onda senoidal (macia e agradável)
                                    os.frequency.setValueAtTime(frequencia, tempoInicio);
                                    
                                    // Envelope acústico: som entra suave e vai sumindo aos poucos
                                    gainNode.gain.setValueAtTime(0, tempoInicio);
                                    gainNode.gain.linearRampToValueAtTime(0.4, tempoInicio + 0.05);
                                    gainNode.gain.exponentialRampToValueAtTime(0.001, tempoInicio + 1.5);
                                    
                                    os.connect(gainNode);
                                    gainNode.connect(ac.destination);
                                    
                                    os.start(tempoInicio);
                                    os.stop(tempoInicio + 1.5);
                                }}
                                
                                // Toca duas notas musicais com um pequeno intervalo (Ding... Dong...)
                                let agora = ac.currentTime;
                                tocarDing(523.25, agora);       // Nota Dó (C5)
                                tocarDing(659.25, agora + 0.3); // Nota Mi (E5)
                            }}
                            
                            function formatTime(sec) {{
                                let m = Math.floor(sec / 60).toString().padStart(2, '0');
                                let se = (sec % 60).toString().padStart(2, '0');
                                return m + ":" + se;
                            }}
                            
                            const i = setInterval(() => {{
                                let now = Math.floor(Date.now() / 1000);
                                let s = Math.floor(endTime - now);
                                
                                if(s > 0) {{
                                    display.innerText = formatTime(s);
                                }} else {{
                                    display.innerText = "00:00";
                                    display.style.color = "white";
                                    display.parentElement.style.backgroundColor = "#e74c3c"; 
                                    
                                    if (!alertaTocado) {{
                                        alertaTocado = true;
                                        tocarAlarme();
                                    }}
                                    clearInterval(i);
                                }}
                            }}, 1000);
                            </script>
                            """
                            st.components.v1.html(html_timer, height=100)

                    with col_t2:
                        st.markdown("### 🔊 Medidor de Ruído")
                        st.components.v1.html("""<div style="text-align: center; background: #f0f2f6; padding: 10px; border-radius: 10px;"><canvas id="meter" width="300" height="40"></canvas><div id="status" style="font-family: sans-serif; font-size: 14px; font-weight: bold; margin-top: 5px;">Microfone Desligado</div></div><script>navigator.mediaDevices.getUserMedia({ audio: true }).then(stream => {const ac=new AudioContext();const an=ac.createAnalyser();const mic=ac.createMediaStreamSource(stream);mic.connect(an);an.fftSize=256;const d=new Uint8Array(an.frequencyBinCount);const can=document.getElementById('meter');const ctx=can.getContext('2d');const st=document.getElementById('status');function draw(){an.getByteFrequencyData(d);let sum=0;for(let i=0;i<d.length;i++)sum+=d[i];let av=sum/d.length;ctx.clearRect(0,0,can.width,can.height);let c="#2ecc71";if(av>40){c="#f39c12";st.innerText="⚠️ Sala Agitada";}if(av>65){c="#e74c3c";st.innerText="🛑 Silêncio!";}if(av<=40){st.innerText="✅ Nível de Ruído OK";}ctx.fillStyle=c;ctx.fillRect(0,0,(av/100)*can.width,can.height);requestAnimationFrame(draw);}draw();});</script>""", height=100)

                    st.write("---")
                    
                    # 🆕 NOVA ABA ADICIONADA AQUI: ✍️ Atividade de Sala
                    modo_aula = st.radio("O que vamos fazer agora?", ["⭐ Comportamento", "📅 Fazer Chamada", "✍️ Atividade de Sala", "🎲 Sortear Aluno", "👥 Grupos", "📝 Registrar Diário"], horizontal=True, key="radio_modo_v4")
                    
                    alunos_sala = pd.read_sql(f"""SELECT a.ra, a.nome, a.avatar_style, a.observacoes FROM alunos a 
                                                  JOIN matriculas_disciplina m ON a.id = m.aluno_id 
                                                  WHERE m.turma_id={id_t_aula} AND m.disciplina='{disc_aula}' ORDER BY a.nome""", conn)

                    # =========================================================================
                    # MODO 1: ⭐ COMPORTAMENTO (DIÁRIO VS TOTAL)
                    # =========================================================================
                    if modo_aula == "⭐ Comportamento":
                        query_alunos = f"""
                        SELECT aluno_ra, 
                               SUM(CASE WHEN data = '{data_str_global}' AND pontos > 0 THEN pontos ELSE 0 END) as dia_pos,
                               SUM(CASE WHEN data = '{data_str_global}' AND pontos < 0 THEN pontos ELSE 0 END) as dia_neg,
                               SUM(pontos) as total_geral
                        FROM logs_comportamento 
                        WHERE turma_id = {id_t_aula} AND aluno_ra != 'TURMA_INTEIRA'
                        GROUP BY aluno_ra
                        """
                        df_p = pd.read_sql(query_alunos, conn)
                        
                        query_turma = f"""
                        SELECT SUM(CASE WHEN data = '{data_str_global}' AND pontos > 0 THEN pontos ELSE 0 END) as dia_pos,
                               SUM(CASE WHEN data = '{data_str_global}' AND pontos < 0 THEN pontos ELSE 0 END) as dia_neg,
                               SUM(pontos) as total_geral
                        FROM logs_comportamento WHERE turma_id = {id_t_aula} AND aluno_ra = 'TURMA_INTEIRA'
                        """
                        df_t_pts = pd.read_sql(query_turma, conn)
                        
                        t_dia_pos = df_t_pts['dia_pos'].fillna(0).iloc[0]
                        t_dia_neg = abs(df_t_pts['dia_neg'].fillna(0).iloc[0])
                        t_total = df_t_pts['total_geral'].fillna(0).iloc[0]
                        
                        alunos_dojo = pd.merge(alunos_sala, df_p, left_on='ra', right_on='aluno_ra', how='left').fillna(0)

                        @st.dialog("Lançar FeedBack")
                        def modal_feedback(ra_alvo, nome_exibicao):
                            st.caption(f"Atalhos para {nome_exibicao} em {data_str_global}:")
                            
                            def salvar_acao_direta(motivo, valor_ponto):
                                with sqlite3.connect('banco_provas.db') as c:
                                    c.execute("INSERT INTO logs_comportamento (aluno_ra, turma_id, data, pontos, comentario, tipo) VALUES (?,?,?,?,?,?)", 
                                              (ra_alvo, id_t_aula, data_str_global, valor_ponto, motivo, "FeedBack"))
                                st.toast(f"✅ {motivo} registrado!")
                                st.rerun()

                            c1, c2 = st.columns(2)
                            if c1.button("❤️ Ajuda", key=f"m_aj_{ra_alvo}", use_container_width=True): salvar_acao_direta("Ajudando os colegas", 1.0)
                            if c2.button("🧐 Foco", key=f"m_fo_{ra_alvo}", use_container_width=True): salvar_acao_direta("Focado", 1.0)
                            if c1.button("💡 Participação", key=f"m_pa_{ra_alvo}", use_container_width=True): salvar_acao_direta("Participação", 1.0)
                            if c2.button("🏔️ Persistência", key=f"m_pe_{ra_alvo}", use_container_width=True): salvar_acao_direta("Persistência", 1.0)
                            if c1.button("📱 Celular", key=f"m_ce_{ra_alvo}", use_container_width=True): salvar_acao_direta("Usando celular", -1.0)
                            if c2.button("🗣️ Conversa", key=f"m_cv_{ra_alvo}", use_container_width=True): salvar_acao_direta("Conversa paralela", -1.0)
                                
                            st.write("---")
                            st.caption("Lançamento Personalizado:")
                            pts_in = st.number_input("Pts:", value=1.0, step=0.5, key=f"mip_{ra_alvo}")
                            mot_in = st.text_input("Motivo:", value="", key=f"mim_{ra_alvo}")
                            
                            if st.button("💾 Lançar Personalizado", key=f"mbsv_{ra_alvo}", type="primary", use_container_width=True):
                                motivo_final = mot_in if mot_in else "Avaliação personalizada"
                                salvar_acao_direta(motivo_final, pts_in)

                        cols = st.columns(6)
                        estilo_card = """
                            <div style='text-align: center; height: 145px; display: flex; flex-direction: column; justify-content: center; align-items: center;'>
                                {conteudo_topo}
                                <b style='font-size: 14px; margin-top: 5px; display: block;'>{nome}</b>
                                <div style='font-size: 14px; margin-top: 3px;'>
                                    <span style='color: #2ecc71;'>●</span> {dia_pos} | <span style='color: #e74c3c;'>●</span> {dia_neg}
                                </div>
                                <div style='font-size: 11px; color: #7f8c8d; margin-top: 2px; font-weight: 600;'>
                                    Total: ⭐ {total_geral}
                                </div>
                            </div>
                        """

                        with cols[0]:
                            with st.container(border=True):
                                st.markdown(estilo_card.format(conteudo_topo="<div style='font-size: 45px; line-height: 1;'>🌍</div>", nome="Toda Turma", dia_pos=int(t_dia_pos), dia_neg=int(t_dia_neg), total_geral=int(t_total)), unsafe_allow_html=True)
                                if st.button("FeedBack", key="btn_modal_turma", use_container_width=True):
                                    modal_feedback('TURMA_INTEIRA', 'Toda a Turma')

                        for idx, row in alunos_dojo.iterrows():
                            with cols[(idx + 1) % 6]:
                                with st.container(border=True):
                                    obs = row['observacoes'] if pd.notna(row['observacoes']) else ""
                                    alerta = "<span title='Nota Pedagógica'>⚠️</span>" if not modo_projetor and obs else ""
                                    avatar_html = f"<img src='https://api.dicebear.com/7.x/{row['avatar_style']}/svg?seed={row['ra']}' width='45' style='margin-bottom: 2px;'>"
                                    
                                    st.markdown(estilo_card.format(conteudo_topo=avatar_html, nome=row['nome'].split()[0] + alerta, dia_pos=int(row['dia_pos']), dia_neg=int(abs(row['dia_neg'])), total_geral=int(row['total_geral'])), unsafe_allow_html=True)
                                    if st.button("FeedBack", key=f"btn_modal_{row['ra']}", use_container_width=True):
                                        if not modo_projetor and obs: st.warning(f"Nota: {obs}")
                                        modal_feedback(row['ra'], row['nome'].split()[0])

                    # =========================================================================
                    # MODO 2: 📅 CHAMADA (COM ACUMULADO DE FALTAS)
                    # =========================================================================
                    elif modo_aula == "📅 Fazer Chamada":
                        st.info(f"Chamada referente ao dia: **{data_str_global}**")
                        
                        df_faltas = pd.read_sql(f"SELECT aluno_ra, COUNT(*) as total_faltas FROM diario WHERE turma_id={id_t_aula} AND status='Ausente' GROUP BY aluno_ra", conn)
                        dict_faltas = dict(zip(df_faltas['aluno_ra'], df_faltas['total_faltas']))
                        
                        estado_ch_key = f"ch_mem_{id_t_aula}_{data_str_global}"
                        if "mem_ch_key" not in st.session_state or st.session_state.mem_ch_key != estado_ch_key:
                            df_freq_dia = pd.read_sql(f"SELECT aluno_ra, status FROM diario WHERE turma_id={id_t_aula} AND data='{data_str_global}'", conn)
                            freq_dict = dict(zip(df_freq_dia['aluno_ra'], df_freq_dia['status']))
                            
                            st.session_state.mem_ch = {}
                            for _, row in alunos_sala.iterrows():
                                st.session_state.mem_ch[row['ra']] = freq_dict.get(row['ra'], "Presente")
                            st.session_state.mem_ch_key = estado_ch_key
                            
                        c_all1, c_all2, _ = st.columns([0.25, 0.25, 0.5])
                        if c_all1.button("🟢 Todos Presentes", use_container_width=True):
                            for ra_aluno in st.session_state.mem_ch: st.session_state.mem_ch[ra_aluno] = "Presente"
                            st.rerun()
                        if c_all2.button("🔴 Todos Ausentes", use_container_width=True):
                            for ra_aluno in st.session_state.mem_ch: st.session_state.mem_ch[ra_aluno] = "Ausente"
                            st.rerun()
                        st.write("---")
                        
                        cols_f = st.columns(6)
                        for idx, row in alunos_sala.iterrows():
                            ra = row['ra']; s = st.session_state.mem_ch.get(ra, "Presente")
                            faltas_acumuladas = dict_faltas.get(ra, 0)
                            
                            with cols_f[idx % 6]:
                                with st.container(border=True):
                                    st.markdown(f"<div style='text-align:center;'><img src='https://api.dicebear.com/7.x/{row['avatar_style']}/svg?seed={ra}' width='45'><br><small style='font-weight: bold;'>{row['nome'].split()[0]}</small><br><small style='color: #e74c3c; font-weight: 600;'>Faltas: {faltas_acumuladas}</small></div>", unsafe_allow_html=True)
                                    lbl = "🟢" if s=="Presente" else "🔴" if s=="Ausente" else "🟡"
                                    if st.button(lbl, key=f"bch_{ra}", use_container_width=True):
                                        st.session_state.mem_ch[ra] = {"Presente":"Ausente", "Ausente":"Atrasado", "Atrasado":"Presente"}[s]; st.rerun()
                                        
                        st.write("---")
                        if st.button("💾 Salvar Chamada Oficial", type="primary", use_container_width=True):
                            for ra_f, stt in st.session_state.mem_ch.items():
                                conn.execute("DELETE FROM diario WHERE turma_id=? AND data=? AND aluno_ra=?", (id_t_aula, data_str_global, ra_f))
                                conn.execute("INSERT INTO diario (turma_id, data, aluno_ra, presente, status) VALUES (?,?,?,?,?)", (id_t_aula, data_str_global, ra_f, stt!="Ausente", stt))
                            conn.commit(); st.success("Chamada Salva!")

                    # =========================================================================
                    # MODO NOVO: ✍️ ATIVIDADE DE SALA (COM CÁLCULO DE 25% DE DESCARTE)
                    # =========================================================================
                    elif modo_aula == "✍️ Atividade de Sala":
                        st.info(f"Registro de Atividade referente ao dia: **{data_str_global}**")
                        
                        # Busca o histórico para calcular a meta de 75%
                        df_hist_ativ = pd.read_sql(f"SELECT data, aluno_ra, entregou FROM atividades_sala WHERE turma_id={id_t_aula} AND disciplina='{disc_aula}'", conn)
                        total_aulas_ativ = df_hist_ativ['data'].nunique()
                        # Calcula a meta: O total de aulas dadas menos 25% de margem (arredondado para baixo o descarte)
                        descarte = int(total_aulas_ativ * 0.25)
                        meta_exigida = total_aulas_ativ - descarte if total_aulas_ativ > 0 else 0
                        
                        st.markdown(f"<div style='background-color:#e8f4f8; padding:15px; border-radius:10px; border-left: 5px solid #3498db; margin-bottom: 20px;'><b>📊 Estatísticas da Disciplina:</b> Você já aplicou atividades em {total_aulas_ativ} aulas diferentes. <br>Considerando a regra de 25% de descarte, o aluno precisa ter entregue pelo menos <b>{meta_exigida} atividades</b> para atingir a pontuação máxima.</div>", unsafe_allow_html=True)

                        estado_ativ_key = f"ativ_mem_{id_t_aula}_{data_str_global}"
                        if "mem_ativ_key" not in st.session_state or st.session_state.mem_ativ_key != estado_ativ_key:
                            df_ativ_hoje = df_hist_ativ[df_hist_ativ['data'] == data_str_global]
                            ativ_dict = dict(zip(df_ativ_hoje['aluno_ra'], df_ativ_hoje['entregou']))
                            
                            st.session_state.mem_ativ = {}
                            for _, row in alunos_sala.iterrows():
                                st.session_state.mem_ativ[row['ra']] = ativ_dict.get(row['ra'], 0) # Padrão: 0 (Não Fez)
                            st.session_state.mem_ativ_key = estado_ativ_key

                        # Botões em Massa
                        c_all1, c_all2, _ = st.columns([0.25, 0.25, 0.5])
                        if c_all1.button("✅ Todos Fizeram", use_container_width=True):
                            for ra_aluno in st.session_state.mem_ativ: st.session_state.mem_ativ[ra_aluno] = 1
                            st.rerun()
                        if c_all2.button("❌ Ninguém Fez", use_container_width=True):
                            for ra_aluno in st.session_state.mem_ativ: st.session_state.mem_ativ[ra_aluno] = 0
                            st.rerun()
                        st.write("---")

                        cols_f = st.columns(6)
                        for idx, row in alunos_sala.iterrows():
                            ra = row['ra']
                            entregou_hoje = st.session_state.mem_ativ.get(ra, 0)
                            
                            # Calcula quanto o aluno já entregou no semestre (não conta a tela atual se ainda não salvou)
                            entregas_aluno = df_hist_ativ[(df_hist_ativ['aluno_ra'] == ra) & (df_hist_ativ['entregou'] == 1)].shape[0]
                            cor_meta = "#2ecc71" if entregas_aluno >= meta_exigida and meta_exigida > 0 else "#e74c3c"
                            
                            with cols_f[idx % 6]:
                                with st.container(border=True):
                                    st.markdown(f"<div style='text-align:center;'><img src='https://api.dicebear.com/7.x/{row['avatar_style']}/svg?seed={ra}' width='45'><br><small style='font-weight: bold;'>{row['nome'].split()[0]}</small><br><small style='color: {cor_meta}; font-weight: 600;'>Fez: {entregas_aluno}/{meta_exigida}</small></div>", unsafe_allow_html=True)
                                    
                                    lbl = "✅ Fez (1)" if entregou_hoje == 1 else "❌ Não Fez (0)"
                                    if st.button(lbl, key=f"bativ_{ra}", use_container_width=True):
                                        st.session_state.mem_ativ[ra] = 1 if entregou_hoje == 0 else 0
                                        st.rerun()
                                        
                        st.write("---")
                        if st.button("💾 Salvar Atividades de Sala", type="primary", use_container_width=True):
                            for ra_f, ent in st.session_state.mem_ativ.items():
                                conn.execute("DELETE FROM atividades_sala WHERE turma_id=? AND disciplina=? AND data=? AND aluno_ra=?", (id_t_aula, disc_aula, data_str_global, ra_f))
                                conn.execute("INSERT INTO atividades_sala (turma_id, disciplina, data, aluno_ra, entregou) VALUES (?,?,?,?,?)", (id_t_aula, disc_aula, data_str_global, ra_f, ent))
                            conn.commit()
                            st.success("Atividades da aula salvas com sucesso!")

                    # =========================================================================
                    # MODO 3: 🎲 SORTEIO
                    # =========================================================================
                    elif modo_aula == "🎲 Sortear Aluno":
                        if alunos_sala.empty: st.warning("Sem alunos.")
                        else:
                            if 'al_sort' not in st.session_state or st.session_state.get('sort_id_t') != id_t_aula:
                                st.session_state.al_sort = alunos_sala.sample(1).iloc[0]; st.session_state.sort_id_t = id_t_aula
                            s = st.session_state.al_sort
                            n_ex = s['nome'].split()[0] + (f" {s['nome'].split()[-1][0]}." if len(s['nome'].split()) > 1 else "")
                            st.markdown(f"<div style='background-color:#1c9e5e; padding:40px; border-radius:15px; text-align:center;'><h2 style='color:white;'>Sua seleção aleatória é:</h2><div style='background-color:white; padding:30px; border-radius:20px; display:inline-block; min-width:350px;'><img src='https://api.dicebear.com/7.x/{s['avatar_style']}/svg?seed={s['ra']}' width='150'><h1 style='color:#2c3e50;'>{n_ex}</h1></div></div>", unsafe_allow_html=True)
                            if st.button("🔄 Sortear novamente", use_container_width=True): st.session_state.al_sort = alunos_sala.sample(1).iloc[0]; st.rerun()
                            c1, c2, c3 = st.columns(3)
                            if c1.button("💡 Respondeu bem (+1)"): conn.execute("INSERT INTO logs_comportamento (aluno_ra, turma_id, data, pontos, comentario, tipo) VALUES (?,?,?,?,?,?)", (s['ra'], id_t_aula, data_str_global, 1.0, "Sorteio - OK", "Bônus")); conn.commit(); st.toast("Salvo!"); st.rerun()
                            if c2.button("👍 Tentou (+0.5)"): conn.execute("INSERT INTO logs_comportamento (aluno_ra, turma_id, data, pontos, comentario, tipo) VALUES (?,?,?,?,?,?)", (s['ra'], id_t_aula, data_str_global, 0.5, "Sorteio - Tentou", "Bônus")); conn.commit(); st.toast("Salvo!"); st.rerun()
                            if c3.button("🗣️ Conversa (-1)"): conn.execute("INSERT INTO logs_comportamento (aluno_ra, turma_id, data, pontos, comentario, tipo) VALUES (?,?,?,?,?,?)", (s['ra'], id_t_aula, data_str_global, -1.0, "Sorteio - Ruim", "Atenção")); conn.commit(); st.toast("Salvo!"); st.rerun()

                    # =========================================================================
                    # MODO 4: 👥 GRUPOS (COM CONTAGEM E FILTRO DE PRESENÇAS)
                    # =========================================================================
                    elif modo_aula == "👥 Grupos":
                        if 'gs_mem' not in st.session_state or st.session_state.get('gs_id_t') != id_t_aula:
                            st.session_state.gs_mem = []; st.session_state.gs_id_t = id_t_aula
                        
                        total_alunos = len(alunos_sala)
                        df_chamada_hoje = pd.read_sql(f"SELECT aluno_ra, status FROM diario WHERE turma_id={id_t_aula} AND data='{data_str_global}'", conn)
                        
                        if not df_chamada_hoje.empty:
                            presentes = len(df_chamada_hoje[df_chamada_hoje['status'] == 'Presente'])
                            txt_info = f"👥 Turma: {total_alunos} alunos | ✅ Presentes na Chamada: {presentes} alunos"
                            ra_presentes = df_chamada_hoje[df_chamada_hoje['status'] == 'Presente']['aluno_ra'].tolist()
                            alunos_ativos_grupo = alunos_sala[alunos_sala['ra'].isin(ra_presentes)]
                        else:
                            txt_info = f"👥 Turma: {total_alunos} alunos | ⚠️ Salve a chamada antes para filtrar ausentes"
                            alunos_ativos_grupo = alunos_sala 
                        
                        if not st.session_state.gs_mem:
                            st.markdown(f"<div style='background-color:#d12229; padding:20px; border-radius:10px; text-align:center; color:white;'><h2>👥 Criador de Grupos</h2><p style='font-size: 16px; margin-bottom: 0; font-weight: 500;'>{txt_info}</p></div>", unsafe_allow_html=True)
                            tipo_g = st.radio("Como organizar?", ["Aleatório", "Manual"])
                            
                            if tipo_g == "Aleatório":
                                col_g1, col_g2 = st.columns([0.4, 0.6])
                                with col_g1:
                                    tam_grupo = st.number_input("Quantos alunos por grupo?", min_value=1, max_value=30, value=4, step=1, key="num_alunos_grupo")
                                
                                with col_g2:
                                    st.write("") 
                                    st.write("")
                                    if st.button("🎲 Sortear e Criar Grupos", type="primary", use_container_width=True):
                                        if alunos_ativos_grupo.empty:
                                            st.error("❌ Não há alunos presentes registrados para formar grupos!")
                                        else:
                                            shuf = alunos_ativos_grupo.sample(frac=1).to_dict('records')
                                            n_gs = max(1, len(shuf) // tam_grupo) if len(shuf) > 0 else 1
                                            gs = [{'nome': f'Grupo {i+1}', 'alunos': []} for i in range(n_gs)]
                                            for i, al in enumerate(shuf): 
                                                gs[i % n_gs]['alunos'].append(al)
                                            st.session_state.gs_mem = gs
                                            st.rerun()
                            else:
                                if 'al_disp' not in st.session_state: st.session_state.al_disp = alunos_ativos_grupo.to_dict('records'); st.session_state.gs_tmp = []
                                sel = st.multiselect("Alunos:", options=[a['nome'] for a in st.session_state.al_disp])
                                if st.button("➕ Adicionar Grupo"):
                                    al_g = [a for a in st.session_state.al_disp if a['nome'] in sel]
                                    st.session_state.al_disp = [a for a in st.session_state.al_disp if a['nome'] not in sel]
                                    st.session_state.gs_tmp.append({'nome': f"Grupo {len(st.session_state.gs_tmp)+1}", 'alunos': al_g}); st.rerun()
                                if st.button("🚀 Concluir"): st.session_state.gs_mem = st.session_state.gs_tmp; st.rerun()
                        else:
                            if st.button("🗑️ Desfazer Grupos"): st.session_state.gs_mem = []; st.rerun()
                            cg = st.columns(3)
                            for i, g in enumerate(st.session_state.gs_mem):
                                with cg[i % 3]:
                                    with st.container(border=True):
                                        st.markdown(f"<h4 style='text-align:center;'>{g['nome']}</h4>", unsafe_allow_html=True)
                                        
                                        avs = "".join([f"<div style='text-align:center; display:inline-block; width:75px; margin: 5px;'><img src='https://api.dicebear.com/7.x/{al['avatar_style']}/svg?seed={al['ra']}' width='45'><br><span style='font-size:13px; font-weight:600;'>{al['nome'].split()[0]}</span></div>" for al in g['alunos']])
                                        st.markdown(f"<div style='text-align:center; margin-bottom: 15px;'>{avs}</div>", unsafe_allow_html=True)
                                        
                                        with st.popover("⭐ Comportamento", use_container_width=True):
                                            if st.button("💡 Equipe Focada (+1)", key=f"bgp_{i}", use_container_width=True):
                                                for al in g['alunos']: conn.execute("INSERT INTO logs_comportamento (aluno_ra, turma_id, data, pontos, comentario, tipo) VALUES (?,?,?,?,?,?)", (al['ra'], id_t_aula, data_str_global, 1.0, f"Lab {g['nome']}", "Bônus"))
                                                conn.commit(); st.toast("Salvo!"); st.rerun()
                                        
                                        with st.popover("📝 Avaliar Trabalho", use_container_width=True):
                                            df_plan = pd.read_sql(f"SELECT nome_avaliacao FROM planejamento_notas WHERE turma_id={id_t_aula} AND disciplina='{disc_aula}'", conn)
                                            ativs = df_plan['nome_avaliacao'].tolist() if not df_plan.empty else ["L1", "P1", "Lab"]
                                            a_sel = st.selectbox("Atividade:", ativs, key=f"tn_g_{i}")
                                            n_sel = st.number_input("Nota:", 0.0, 10.0, 10.0, key=f"nt_g_{i}")
                                            if st.button("💾 Salvar Nota", key=f"sn_g_{i}", type="primary", use_container_width=True):
                                                for al in g['alunos']:
                                                    conn.execute("INSERT OR REPLACE INTO trabalhos_extras (turma_id, disciplina, nome_atividade, aluno_ra, nota, data) VALUES (?,?,?,?,?,?)", (id_t_aula, disc_aula, a_sel, al['ra'], n_sel, data_str_global))
                                                conn.commit(); st.toast("Salvo no Boletim!")

                    # =========================================================================
                    # MODO 5: 📝 DIÁRIO (COM PLANEJADO VS REALIZADO)
                    # =========================================================================
                    elif modo_aula == "📝 Registrar Diário":
                        st.info(f"Diário de Classe referente ao dia: **{data_str_global}**")
                        
                        exp = pd.read_sql(f"SELECT tema, conteudo_detalhado FROM cronograma_detalhado WHERE turma_id={id_t_aula} AND disciplina='{disc_aula}' AND data='{data_str_global}'", conn)
                        tema_planejado = exp['tema'].iloc[0] if not exp.empty else "Nenhum tema planejado para esta data."
                        conteudo_planejado = exp['conteudo_detalhado'].iloc[0] if not exp.empty else "Nenhum roteiro cadastrado."
                        
                        with st.container(border=True):
                            st.markdown("🎯 **O que estava planejado para hoje:**")
                            st.markdown(f"**Tema:** {tema_planejado}")
                            st.info(f"**Conteúdo Esperado:** {conteudo_planejado}")
                        
                        real = pd.read_sql(f"SELECT conteudo_real, observacao FROM diario_conteudo WHERE turma_id={id_t_aula} AND disciplina='{disc_aula}' AND data='{data_str_global}'", conn)
                        
                        c_real_banco = real['conteudo_real'].iloc[0] if not real.empty else conteudo_planejado
                        obs_banco = real['observacao'].iloc[0] if not real.empty else ""

                        st.markdown("---")
                        c_real = st.text_area("✍️ O que realmente foi dado em sala:", value=c_real_banco, key="area_real", height=100)
                        obs_d = st.text_area("💡 Observações Pedagógicas (ex: o que faltou dar, dúvidas gerais):", value=obs_banco, key="area_obs", height=80)
                        
                        if st.button("💾 Salvar Diário", type="primary", key="btn_save_dia", use_container_width=True):
                            conn.execute("DELETE FROM diario_conteudo WHERE turma_id=? AND disciplina=? AND data=?", (id_t_aula, disc_aula, data_str_global))
                            conn.execute("INSERT INTO diario_conteudo (turma_id, disciplina, data, conteudo_real, observacao) VALUES (?,?,?,?,?)", (id_t_aula, disc_aula, data_str_global, c_real, obs_d))
                            conn.commit(); st.success("Diário atualizado com sucesso!")