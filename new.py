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

from datetime import datetime
from difflib import SequenceMatcher

# --- 1. FUNÇÕES DE UTILIDADE E SEGURANÇA ---
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
# 👇 COLE A FUNÇÃO NOVA AQUI 👇
def recortar_e_alinhar_folha(img_orig):
    # 1. Pega as medidas originais
    h_orig, w_orig = img_orig.shape[:2]
    
    # 2. Redimensiona para trabalhar mais rápido
    proporcao = 1000 / w_orig
    img_redim = cv2.resize(img_orig, (1000, int(h_orig * proporcao)))
    
    # 3. Tenta achar o papel (Canny + Contornos)
    gray = cv2.cvtColor(img_redim, cv2.COLOR_BGR2GRAY)
    blur = cv2.GaussianBlur(gray, (5, 5), 0)
    edged = cv2.Canny(blur, 50, 150)
    cnts, _ = cv2.findContours(edged, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    cnts = sorted(cnts, key=cv2.contourArea, reverse=True)[:5]

    for c in cnts:
        peri = cv2.arcLength(c, True)
        approx = cv2.approxPolyDP(c, 0.02 * peri, True)
        # Se achou algo com 4 pontas e que ocupa pelo menos 20% da foto
        if len(approx) == 4 and cv2.contourArea(c) > (1000 * int(h_orig * proporcao) * 0.2):
            pts = approx.reshape(4, 2)
            rect = np.zeros((4, 2), dtype="float32")
            s = pts.sum(axis=1)
            rect[0] = pts[np.argmin(s)]
            rect[2] = pts[np.argmax(s)]
            diff = np.diff(pts, axis=1)
            rect[1] = pts[np.argmin(diff)]
            rect[3] = pts[np.argmax(diff)]

            # 🟢 CORREÇÃO DO PAPEL CARTA: Calcula a proporção real do papel detectado!
            (tl, tr, br, bl) = rect
            widthA = np.sqrt(((br[0] - bl[0]) ** 2) + ((br[1] - bl[1]) ** 2))
            widthB = np.sqrt(((tr[0] - tl[0]) ** 2) + ((tr[1] - tl[1]) ** 2))
            maxWidth = max(int(widthA), int(widthB))
            if maxWidth == 0: maxWidth = 1000

            heightA = np.sqrt(((tr[0] - br[0]) ** 2) + ((tr[1] - br[1]) ** 2))
            heightB = np.sqrt(((tl[0] - bl[0]) ** 2) + ((tl[1] - bl[1]) ** 2))
            maxHeight = max(int(heightA), int(heightB))
            
            target_h = int(1000 * (maxHeight / float(maxWidth)))

            # Alinha respeitando o formato original (A4 ou Carta)
            dst = np.array([[0, 0], [999, 0], [999, target_h-1], [0, target_h-1]], dtype="float32")
            M = cv2.getPerspectiveTransform(rect, dst)
            return cv2.warpPerspective(img_redim, M, (1000, target_h))

    # Trava de segurança
    return img_redim
# --- 2. MANUTENÇÃO E BACKUP ---
def limpar_arquivos_temporarios():
    # Tirei o '.png' da lista geral para proteger suas figuras!
    extensoes_lixo = ['.tex', '.log', '.aux', '.out', '.toc']
    
    # Ficheiros que NUNCA podem ser apagados
    arquivos_protegidos = [
        'logo.png', 
        'banco_provas.db', 
        'app_provas.py', 
        'template_profissional.tex', 
        'template_gabarito.tex'
    ]
    
    removidos = 0
    # Listamos todos os ficheiros na pasta atual
    for f in os.listdir('.'):
        # Condição 1: É um arquivo de texto/log inútil do LaTeX
        is_lixo_padrao = any(f.endswith(ext) for ext in extensoes_lixo)
        
        # Condição 2: É um QR Code gerado temporariamente para a prova
        is_qr_code = f.startswith('qr_') and f.endswith('.png')
        
        # Se for lixo OU for QR code, nós apagamos
        if is_lixo_padrao or is_qr_code:
            # Só apagamos se NÃO for um ficheiro protegido e NÃO for o PDF final
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
        # Como deve ficar (separado e organizado):
        pasta_icloud = os.path.join(home, "Library/Mobile Documents/com~apple~CloudDocs/Backup_GeradorProvas")
        if not os.path.exists(pasta_icloud): os.makedirs(pasta_icloud)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        destino = os.path.join(pasta_icloud, f"backup_provas_{timestamp}.db")
        
        # Copia os dados de forma "viva" e segura
        banco_original = sqlite3.connect('banco_provas.db')
        banco_backup = sqlite3.connect(destino)
        with banco_backup:
            banco_original.backup(banco_backup)
        
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

# --- 3. BASE DE DADOS (CONFIGURAÇÃO TOTAL) ---
def criar_base_de_dados():
    with sqlite3.connect('banco_provas.db') as conn:
        cursor = conn.cursor()
        
        # 1. Tabelas de Provas e Questões
        cursor.execute('''CREATE TABLE IF NOT EXISTS questoes (id INTEGER PRIMARY KEY AUTOINCREMENT, disciplina TEXT, assunto TEXT, dificuldade TEXT, enunciado TEXT, imagem TEXT, pontos REAL, tipo TEXT, gabarito_discursivo TEXT, espaco_resposta TEXT, espaco_linhas INTEGER, gabarito_imagem TEXT)''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS alternativas (id INTEGER PRIMARY KEY AUTOINCREMENT, questao_id INTEGER, texto TEXT, correta BOOLEAN, imagem TEXT)''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS resultados (id INTEGER PRIMARY KEY AUTOINCREMENT, aluno_nome TEXT, aluno_ra TEXT, disciplina TEXT, versao TEXT, nota REAL, data_hora TEXT, avaliacao TEXT)''')
        
        # 2. Tabelas de Gestão de Sala
        cursor.execute('''CREATE TABLE IF NOT EXISTS turmas (id INTEGER PRIMARY KEY AUTOINCREMENT, nome TEXT)''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS alunos (id INTEGER PRIMARY KEY AUTOINCREMENT, turma_id INTEGER, nome TEXT, ra TEXT, avatar_style TEXT DEFAULT 'bottts')''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS diario (id INTEGER PRIMARY KEY AUTOINCREMENT, turma_id INTEGER, data TEXT, aluno_ra TEXT, presente BOOLEAN, status TEXT DEFAULT 'Presente', pontos_atividade REAL, pontos_comportamento REAL)''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS trabalhos_extras (id INTEGER PRIMARY KEY AUTOINCREMENT, turma_id INTEGER, disciplina TEXT, nome_atividade TEXT, aluno_ra TEXT, nota REAL, data TEXT)''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS planejamento_notas (id INTEGER PRIMARY KEY AUTOINCREMENT, turma_id INTEGER, disciplina TEXT, nome_avaliacao TEXT, peso REAL)''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS logs_comportamento (id INTEGER PRIMARY KEY AUTOINCREMENT, aluno_ra TEXT, turma_id INTEGER, data TEXT, pontos REAL, comentario TEXT, tipo TEXT)''') 
        
        # 3. Configurações Globais
        cursor.execute('''CREATE TABLE IF NOT EXISTS configuracoes (id INTEGER PRIMARY KEY CHECK (id = 1), instituicao TEXT, professor TEXT, departamento TEXT, curso TEXT, instrucoes TEXT)''')
        
        # --- MIGRATIONS (Proteção para não apagar dados antigos) ---
        cursor.execute("PRAGMA table_info(questoes)")
        colunas_q = [col[1] for col in cursor.fetchall()]
        migracoes_q = {
            "assunto": "TEXT DEFAULT 'Geral'",
            "espaco_resposta": "TEXT DEFAULT 'Linhas'",
            "espaco_linhas": "INTEGER DEFAULT 4",
            "dificuldade": "TEXT DEFAULT 'Média'",
            "gabarito_imagem": "TEXT" 
        }
        for col, definicao in migracoes_q.items():
            if col not in colunas_q: cursor.execute(f"ALTER TABLE questoes ADD COLUMN {col} {definicao}")
                
        cursor.execute("PRAGMA table_info(alternativas)")
        if "imagem" not in [col[1] for col in cursor.fetchall()]: 
            cursor.execute("ALTER TABLE alternativas ADD COLUMN imagem TEXT")
            
        cursor.execute("PRAGMA table_info(alunos)")
        if "avatar_style" not in [col[1] for col in cursor.fetchall()]: 
            cursor.execute("ALTER TABLE alunos ADD COLUMN avatar_style TEXT DEFAULT 'bottts'")

        cursor.execute("PRAGMA table_info(diario)")
        if "status" not in [col[1] for col in cursor.fetchall()]: 
            cursor.execute("ALTER TABLE diario ADD COLUMN status TEXT DEFAULT 'Presente'")
        
        cursor.execute('SELECT COUNT(*) FROM configuracoes')
        if cursor.fetchone()[0] == 0:
            cursor.execute("INSERT INTO configuracoes (id, instituicao, professor) VALUES (1, 'Sua Instituição', 'Profa. Mariana C. P. Morillo')")

        conn.commit()
    conn.close()

def inserir_questao(disc, ass, dif, enun, alts, pts, tipo, gab_disc=None, img=None, espaco="Linhas", espaco_linhas=4, gab_img=None):
    # O "with" garante que a conexão feche automaticamente no final
    with sqlite3.connect('banco_provas.db') as conexao:
        cursor = conexao.cursor()
        
        pts_float = float(pts)
        linhas_int = int(espaco_linhas)
        
        cursor.execute('''
            INSERT INTO questoes (
                disciplina, assunto, dificuldade, enunciado, imagem, 
                pontos, tipo, gabarito_discursivo, espaco_resposta, espaco_linhas, gabarito_imagem
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (disc, ass, dif, enun, img, pts_float, tipo, gab_disc, espaco, linhas_int, gab_img))
        
        q_id = cursor.lastrowid
        
        if tipo in ["Múltipla Escolha", "Verdadeiro ou Falso"]:
            for txt, corr, img_alt in alts:
                cursor.execute('INSERT INTO alternativas (questao_id, texto, correta, imagem) VALUES (?, ?, ?, ?)', 
                               (q_id, txt, corr, img_alt))
        
        conexao.commit()
    # Não precisa de conexao.close() aqui, o "with" já cuidou disso!
    conexao.close() # 👈 Só para garantir o fechamento total da porta do banco
# --- ATENÇÃO: AS DUAS FUNÇÕES ABAIXO FORAM CORRIGIDAS PARA LER AS IMAGENS ---

def buscar_e_embaralhar_alternativas(q_id):
    conexao = sqlite3.connect('banco_provas.db')
    cursor = conexao.cursor()
    # Agora o SELECT puxa a 'imagem' também
    cursor.execute('SELECT texto, correta, imagem FROM alternativas WHERE questao_id = ?', (q_id,))
    alts = cursor.fetchall()
    conexao.close()
    random.shuffle(alts)
    return alts

def buscar_alternativas_originais(q_id):
    conexao = sqlite3.connect('banco_provas.db')
    cursor = conexao.cursor()
    # Agora o SELECT puxa a 'imagem' também
    cursor.execute('SELECT texto, correta, imagem FROM alternativas WHERE questao_id = ? ORDER BY id', (q_id,))
    alts = cursor.fetchall()
    conexao.close()
    return alts

def carregar_configuracoes():
    conexao = sqlite3.connect('banco_provas.db')
    cursor = conexao.cursor()
    cursor.execute('SELECT instituicao, professor, departamento, curso, instrucoes FROM configuracoes WHERE id = 1')
    res = cursor.fetchone()
    conexao.close()
    return res

def salvar_configuracoes(inst, prof, dep, curso, instr):
    conexao = sqlite3.connect('banco_provas.db')
    cursor = conexao.cursor()
    cursor.execute('''
        UPDATE configuracoes 
        SET instituicao=?, professor=?, departamento=?, curso=?, instrucoes=? 
        WHERE id=1
    ''', (inst, prof, dep, curso, instr))
    conexao.commit(); conexao.close()



def excluir_questao(q_id):
    conexao = sqlite3.connect('banco_provas.db')
    cursor = conexao.cursor()
    cursor.execute('DELETE FROM alternativas WHERE questao_id = ?', (q_id,))
    cursor.execute('DELETE FROM questoes WHERE id = ?', (q_id,))
    conexao.commit(); conexao.close()

def obter_assuntos_da_disciplina(disciplina):
    conexao = sqlite3.connect('banco_provas.db')
    cursor = conexao.cursor()
    cursor.execute('SELECT DISTINCT assunto FROM questoes WHERE disciplina = ? AND assunto IS NOT NULL AND assunto != "" ORDER BY assunto', (disciplina,))
    res = [r[0] for r in cursor.fetchall()]
    conexao.close()
    return ["Todos"] + res

def buscar_questoes_filtradas(disciplina, limite=None, assunto="Todos", dificuldade="Todos", tipo="Todos", sortear=False, excluir_ids=None):
    conexao = sqlite3.connect('banco_provas.db')
    cursor = conexao.cursor()
    # Adicionado o 'gabarito_imagem' no final do SELECT
    query = '''SELECT id, enunciado, imagem, pontos, tipo, gabarito_discursivo, espaco_resposta, espaco_linhas, dificuldade, assunto, gabarito_imagem 
               FROM questoes WHERE disciplina = ?'''
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
    conexao.close()
    return q





def salvar_resultado_prova(nome, ra, disc, versao, nota, avaliacao="P1"):
    conexao = sqlite3.connect('banco_provas.db')
    cursor = conexao.cursor()
    agora = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    
    # 1. Trava de segurança: Adiciona a gaveta 'avaliacao' no banco se ela não existir
    cursor.execute("PRAGMA table_info(resultados)")
    colunas = [col[1] for col in cursor.fetchall()]
    if "avaliacao" not in colunas:
        cursor.execute("ALTER TABLE resultados ADD COLUMN avaliacao TEXT DEFAULT 'P1'")
    
    # 2. Verifica se o aluno já tem ESSA prova específica (ex: P1) salva para evitar duplicar a P1
    cursor.execute('SELECT id FROM resultados WHERE aluno_ra = ? AND disciplina = ? AND avaliacao = ?', (ra, disc, avaliacao))
    registro_existente = cursor.fetchone()
    
    if registro_existente:
        cursor.execute('UPDATE resultados SET nota = ?, data_hora = ?, versao = ? WHERE id = ?', (nota, agora, versao, registro_existente[0]))
    else:
        cursor.execute('INSERT INTO resultados (aluno_nome, aluno_ra, disciplina, versao, nota, data_hora, avaliacao) VALUES (?, ?, ?, ?, ?, ?, ?)', (nome, ra, disc, versao, nota, agora, avaliacao))
        
    conexao.commit()
    conexao.close()
    backup_para_icloud()

# --- 4. COMPILAÇÃO E JINJA ---
def configurar_jinja():
    return jinja2.Environment(block_start_string='<%', block_end_string='%>', variable_start_string='<<', variable_end_string='>>', trim_blocks=True, autoescape=False, loader=jinja2.FileSystemLoader(os.path.abspath('.')))

def compilar_latex_mac(caminho_tex):
    caminho_mac = "/Library/TeX/texbin/pdflatex"
    caminho_pdf = caminho_tex.replace('.tex', '.pdf')
    
    try:
        # 1ª Passada: Monta a estrutura da prova (Gera os avisos de Rerun do LaTeX)
        subprocess.run([caminho_mac, '-interaction=nonstopmode', caminho_tex], capture_output=True)
        
        # 2ª Passada: Roda novamente para somar os pontos e finalizar o PDF perfeitamente!
        subprocess.run([caminho_mac, '-interaction=nonstopmode', caminho_tex], capture_output=True)
        
        # O Python agora só verifica se o arquivo PDF nasceu de verdade
        if os.path.exists(caminho_pdf):
            return True
        else:
            st.error(f"⚠️ Falha real: O PDF não foi criado para {caminho_tex}")
            return False
            
    except Exception as e:
        st.error(f"⚠️ Erro ao tentar chamar o LaTeX no sistema: {e}")
        return False
def detectar_duplicata(enunciado, disciplina):
    conexao = sqlite3.connect('banco_provas.db')
    cursor = conexao.cursor()
    # Busca se já existe o mesmo enunciado na mesma disciplina
    cursor.execute('SELECT id FROM questoes WHERE enunciado = ? AND disciplina = ?', (enunciado, disciplina))
    resultado = cursor.fetchone()
    conexao.close()
    return resultado[0] if resultado else None
def calcular_percentual_similaridade(a, b):
    # Compara dois textos e devolve um valor entre 0 e 1
    return SequenceMatcher(None, a, b).ratio()

def buscar_questoes_proximas(enunciado_novo, disciplina, limite=0.8):
    conexao = sqlite3.connect('banco_provas.db')
    cursor = conexao.cursor()
    cursor.execute('SELECT id, enunciado FROM questoes WHERE disciplina = ?', (disciplina,))
    questoes_existentes = cursor.fetchall()
    conexao.close()

    encontradas = []
    # Convertemos para minúsculas para a comparação não ser prejudicada por Caps Lock
    texto_novo = enunciado_novo.lower().strip()
    
    for q_id, q_texto in questoes_existentes:
        # Compara em minúsculas
        similaridade = calcular_percentual_similaridade(texto_novo, q_texto.lower().strip())
        if similaridade >= limite:
            encontradas.append({"id": q_id, "texto": q_texto, "percentual": similaridade * 100})
    
    return sorted(encontradas, key=lambda x: x['percentual'], reverse=True)
# --- 5. INTERFACE (STREAMLIT) ---
criar_base_de_dados()
st.set_page_config(page_title="Gerador da Mari", layout="wide")
# --- SISTEMA DE ACESSO ---
st.sidebar.title("🔐 Portaria FAM")
perfil = st.sidebar.radio("Selecione o acesso:", ["🔒 Área da Professora", "🎓 Portal do Aluno"])

if perfil == "🎓 Portal do Aluno":
    st.title("🎓 Portal do Aluno")
    ra_login = st.sidebar.text_input("Digite seu RA para entrar:", type="password")
    
    if ra_login:
        conn = sqlite3.connect('banco_provas.db')
        # 🟢 AJUSTE AQUI: Usando params=[ra_login] para evitar que aspas quebrem o app
        aluno = pd.read_sql("SELECT * FROM alunos WHERE ra = ?", conn, params=[ra_login])
        
        if not aluno.empty:
            st.header(f"Bem-vindo, {aluno['nome'].values[0]}! 👋")
            c1, c2 = st.columns([0.3, 0.7])
            with c1:
                st.image(f"https://api.dicebear.com/7.x/{aluno['avatar_style'].values[0]}/svg?seed={ra_login}", width=150)
                novo_estilo = st.selectbox("Personalizar meu Avatar:", ["bottts", "avataaars", "pixel-art", "lorelei", "micah"])
                if st.button("Salvar Novo Visual"):
                    # 🟢 AJUSTE AQUI TAMBÉM
                    conn.execute("UPDATE alunos SET avatar_style=? WHERE ra=?", (novo_estilo, ra_login))
                    conn.commit()
                    st.rerun()
            with c2:
                st.subheader("📊 Meu Mural de Participação")
                logs = pd.read_sql(f"SELECT data, pontos, comentario, tipo FROM logs_comportamento WHERE aluno_ra = '{ra_login}' ORDER BY id DESC", conn)
                st.dataframe(logs, use_container_width=True, hide_index=True)
        else: st.error("RA não localizado.")
        conn.close()
    st.stop() # 🛑 BARREIRA: Aluno não vê nada do que está abaixo desta linha!
st.title("📚 Gerador de Provas da Mari")
# --- BARRA LATERAL DE MANUTENÇÃO ---
with st.sidebar:
    st.header("🛠️ Manutenção do Sistema")
    st.write("Use para manter o app rápido e seguro.")
    
    if st.button("🧹 Limpar Arquivos (Lixo do LaTeX)", width="stretch"):
        qtd_removidos = limpar_arquivos_temporarios()
        if qtd_removidos > 0:
            st.success(f"Limpeza concluída! {qtd_removidos} arquivos temporários apagados.")
        else:
            st.info("A pasta já está limpa, nenhum arquivo inútil encontrado.")
            
    st.write("---")
    st.write("🛡️ **Backups do Banco de Dados**")
    
    if st.button("💾 Fazer Backup Local", width="stretch"):
        nome_bkp = criar_backup_banco()
        if nome_bkp:
            st.success(f"Backup criado com sucesso: {nome_bkp}")
        else:
            st.error("Falha ao criar o backup local.")
            
    if st.button("☁️ Forçar Backup iCloud", width="stretch"):
        if backup_para_icloud():
            st.success("Cópia de segurança enviada para o iCloud!")
        else:
            st.error("Não foi possível sincronizar com o iCloud.")
aba_cad, aba_turmas, aba_gen, aba_edit, aba_corr, aba_caderneta, aba_hist, aba_sala = st.tabs([
    "📝 Cadastrar", "👥 Turmas", "⚙️ Gerar Provas", "🔍 Editar", "📸 Corrigir", "📖 Caderneta", "📊 Boletim Mestre", "🎮 Sala de Aula"
])

# --- LISTAS DE SÍMBOLOS EXPANDIDAS E CORRIGIDAS ---
gregas = [
    ("α", r"\alpha"), ("β", r"\beta"), ("γ", r"\gamma"), ("δ", r"\delta"), ("ε", r"\epsilon"), 
    ("ζ", r"\zeta"), ("η", r"\eta"), ("θ", r"\theta"), ("κ", r"\kappa"), ("λ", r"\lambda"), 
    ("μ", r"\mu"), ("ν", r"\nu"), ("ξ", r"\xi"), ("π", r"\pi"), ("ρ", r"\rho"), 
    ("σ", r"\sigma"), ("τ", r"\tau"), ("φ", r"\phi"), ("χ", r"\chi"), ("ψ", r"\psi"), 
    ("ω", r"\omega"), ("Γ", r"\Gamma"), ("Δ", r"\Delta"), ("Θ", r"\Theta"), ("Λ", r"\Lambda"), 
    ("Σ", r"\Sigma"), ("Φ", r"\Phi"), ("Ω", r"\Omega")
]

matematica = [
    # Estruturas e Agrupamentos
    ("Fração", r"\frac{ }{ }"), ("Potência", r"^{ }"), ("Subscrito", r"_{ }"), ("Sub+Pot", r"_{ }^{ }"), 
    ("Raiz √", r"\sqrt{ }"), ("Raiz N ∛", r"\sqrt[ ]{ }"), ("Parênteses ( )", r"\left(  \right)"), 
    ("Colchetes [ ]", r"\left[  \right]"), ("Chaves { }", r"\left\{  \right\}"), ("Matriz 2x2", r"\begin{bmatrix} a & b \\ c & d \end{bmatrix}"),
    
    # Acentos e Vetores (Restaurado)
    ("Vetor (v⃗)", r"\vec{v}"), ("Versor (n̂)", r"\hat{n}"), ("Ponto (ẋ)", r"\dot{x}"), 
    ("2 Pontos (ẍ)", r"\ddot{x}"), ("Barra (x̄)", r"\bar{x}"),
    
    # Lógica, Relações e Tipografia (Restaurado)
    ("Maior/Igual ≥", r"\geq"), ("Menor/Igual ≤", r"\leq"), ("Diferente ≠", r"\neq"), ("Aprox ≈", r"\approx"),
    ("Infinito ∞", r"\infty"), ("Seta →", r"\to"), ("Graus °C", r"^\circ C"), ("Mais/Menos ±", r"\pm"), 
    ("Multiplica ×", r"\times"), ("Negrito", r"\mathbf{ }"), ("Itálico", r"\mathit{ }")
]

calculo = [
    ("Limite", r"\lim_{x \to \infty}"), ("Integral ∫", r"\int"), ("Int. Definida", r"\int_{a}^{b}"), 
    ("Int. Dupla ∬", r"\iint"), ("Int. Fechada ∮", r"\oint"), ("Somatório Σ", r"\sum_{i=1}^{n}"), 
    ("Produtório Π", r"\prod_{i=1}^{n}"), ("Derivada d/dx", r"\frac{d}{dx}"), ("Derivada 2ª", r"\frac{d^2}{dx^2}"),
    ("Parcial ∂", r"\partial"), ("Gradiente ∇", r"\nabla"), ("Divergente", r"\nabla \cdot"), ("Rotacional", r"\nabla \times")
]

fluidos = [
    ("Bernoulli", r"P_1 + \frac{1}{2}\rho v_1^2 + \rho g z_1 = P_2 + \frac{1}{2}\rho v_2^2 + \rho g z_2"), 
    ("Darcy-Weisbach", r"h_f = f \cdot \frac{L}{D} \cdot \frac{v^2}{2g}"),
    ("Reynolds", r"Re = \frac{\rho v D}{\mu}"),
    ("Continuidade", r"A_1 v_1 = A_2 v_2"),
    ("Empuxo", r"E = \rho_{liq} \cdot V_{sub} \cdot g"),
    ("Pressão Hidro.", r"P = P_{atm} + \rho g h")
]

termo = [
    ("1ª Lei", r"\Delta U = Q - W"), 
    ("Gás Ideal", r"P V = n R T"),
    ("Trabalho Exp.", r"W = \int_{V_1}^{V_2} P dV"),
    ("Rendimento η", r"\eta = \frac{W_{liq}}{Q_{q}}"),
    ("Carnot", r"\eta_{max} = 1 - \frac{T_f}{T_q}"),
    ("Entropia ΔS", r"\Delta S = \int \frac{dQ_{rev}}{T}"),
    ("Calor Sensível", r"Q = m \cdot c \cdot \Delta T")
]

# --- O NOVO SISTEMA DE PAINEL FLUTUANTE (POPOVER) ---
def injetar_direto(comando, target_key):
    if target_key in st.session_state:
        st.session_state[target_key] += f" ${comando}$ "
    else:
        st.session_state[target_key] = f" ${comando}$ "

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


with aba_cad:
    st.subheader("📝 Registro Inteligente de Questões")
    
    # --- 1. LÓGICA DE LIMPEZA (MANTÉM) ---
    if st.session_state.get('limpar_proxima_cad'):
        keys_texto = ["enun_input", "gab_input_cad"]
        for k in list(st.session_state.keys()):
            if k.startswith("t_alt_cad_") or k in keys_texto:
                st.session_state[k] = ""
        st.session_state.uploader_reset_cad = st.session_state.get('uploader_reset_cad', 0) + 1
        st.session_state.limpar_proxima_cad = False

    # --- 2. ENTRADA DE DADOS BÁSICOS (MANTÉM) ---
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

    # --- 3. ENUNCIADO + SENSOR DE DUPLICIDADE (NOVIDADE AQUI) ---
    c_e1, c_e2 = st.columns([0.85, 0.15])
    with c_e1: 
        e_c = st.text_area("Enunciado da Questão:", key="enun_input", height=120)
    with c_e2: 
        st.write(" ")
        painel_flutuante("enun_input", "cad_enun_")

    pode_gravar = True # Variável que controla se o botão funciona

    if e_c.strip():
        with st.expander("👁️ Pré-visualização do Enunciado", expanded=True): 
            st.markdown(e_c)
        
        # O Robô trabalha enquanto você digita:
        id_duplicado = detectar_duplicata(e_c, d_c)
        if id_duplicado:
            st.error(f"🚫 **Questão idêntica!** Já existe no banco (ID: {id_duplicado}).")
            pode_gravar = False
        else:
            similares = buscar_questoes_proximas(e_c, d_c, limite=0.75)
            if similares:
                st.warning(f"🔔 **Atenção:** Encontrei {len(similares)} questões muito parecidas.")
                with st.expander("Ver similares para comparar"):
                    for s in similares[:3]:
                        st.write(f"- ID {s['id']} ({s['percentual']:.1f}% similar): {s['texto'][:100]}...")
                
                confirmar_similar = st.checkbox("Esta questão é diferente. Quero salvar mesmo assim.", key="chk_sim")
                if not confirmar_similar:
                    pode_gravar = False

    # --- 4. UPLOADS E ALTERNATIVAS (ISSO NÃO PODE SUMIR!) ---
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

    # --- 5. BOTÃO GUARDAR (AGORA COM TRAVA INTELIGENTE) ---
    if st.button("💾 Guardar Questão", type="primary", width="stretch", disabled=not pode_gravar):
        # Todo o processo de salvar imagens e banco (MANTÉM IGUAL)
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
# --- ABA 2: GESTÃO DE TURMAS (OPERAÇÃO: MATRÍCULAS E DATAS) ---
with aba_turmas:
    st.header("👥 Painel de Operação: Turmas, Matrículas e Datas")
    
    from datetime import datetime, timedelta
    
    with sqlite3.connect('banco_provas.db') as conn:
        conn.execute('''CREATE TABLE IF NOT EXISTS turmas (id INTEGER PRIMARY KEY, nome TEXT UNIQUE)''')
        conn.execute('''CREATE TABLE IF NOT EXISTS alunos (id INTEGER PRIMARY KEY, turma_id INTEGER, nome TEXT, ra TEXT, email TEXT, observacoes TEXT)''')
        conn.execute('''CREATE TABLE IF NOT EXISTS matriculas_disciplina (id INTEGER PRIMARY KEY, turma_id INTEGER, disciplina TEXT, aluno_id INTEGER)''')
        conn.execute('''CREATE TABLE IF NOT EXISTS cronograma_detalhado (id INTEGER PRIMARY KEY, turma_id INTEGER, disciplina TEXT, num_aula INTEGER, data TEXT, tema TEXT, objetivos_aula TEXT, conteudo_detalhado TEXT, referencias_aula TEXT, materiais_link TEXT)''')
        
        conn.execute('''CREATE TABLE IF NOT EXISTS plano_ensino_turma 
                        (id INTEGER PRIMARY KEY, turma_id INTEGER, disciplina TEXT, ementa TEXT, objetivos TEXT, 
                         competencias TEXT, egresso TEXT, conteudo_prog TEXT, metodologia TEXT, recursos TEXT, 
                         avaliacao TEXT, aps TEXT, bib_basica TEXT, bib_complementar TEXT, outras_ref TEXT)''')
        
        conn.execute('''CREATE TABLE IF NOT EXISTS planejamento_notas (id INTEGER PRIMARY KEY, turma_id INTEGER, disciplina TEXT, nome_avaliacao TEXT, peso REAL, data_prevista TEXT)''')
        conn.execute('''CREATE TABLE IF NOT EXISTS diario_conteudo (id INTEGER PRIMARY KEY, turma_id INTEGER, disciplina TEXT, data TEXT, conteudo_real TEXT, observacao TEXT)''')
        
        # 💉 VACINA DE DADOS: Força a criação das colunas de Perfil e FAM
        for col, tipo in [('email', 'TEXT'), ('observacoes', 'TEXT')]:
            try: conn.execute(f"ALTER TABLE alunos ADD COLUMN {col} {tipo}")
            except: pass
            
        colunas_fam_turma = ['competencias', 'egresso', 'conteudo_prog', 'metodologia', 'recursos', 'avaliacao', 'aps', 'bib_basica', 'bib_complementar', 'outras_ref']
        for col in colunas_fam_turma:
            try: conn.execute(f"ALTER TABLE plano_ensino_turma ADD COLUMN {col} TEXT")
            except: pass
            
        conn.commit()

        # ... (daqui para baixo continua normal: with st.expander("➕ 1. Cadastrar Turma..."))

        with st.expander("➕ 1. Cadastrar Turma Base e Importar Lista Geral de Alunos", expanded=False):
            col_t1, col_t2 = st.columns(2)
            with col_t1:
                st.write("**Criar Turma**")
                n_t = st.text_input("Nome da Turma:", placeholder="Ex: Eng. Mecânica 2026")
                if st.button("Criar Turma", use_container_width=True) and n_t:
                    try:
                        conn.execute('INSERT INTO turmas (nome) VALUES (?)', (n_t,))
                        conn.commit(); st.success("Turma criada!")
                    except: st.error("Turma já existe.")
            with col_t2:
                t_db = pd.read_sql('SELECT * FROM turmas', conn)
                if not t_db.empty:
                    st.write("**Importar Lista (Excel/CSV)**")
                    t_up = st.selectbox("Turma:", t_db['nome'].tolist())
                    id_up = t_db[t_db['nome'] == t_up]['id'].values[0]
                    arq = st.file_uploader("Arquivo com NOME e RA:", type=['xlsx', 'csv'])
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

        st.write("---")
        t_db = pd.read_sql('SELECT * FROM turmas', conn)
        if t_db.empty:
            st.info("Crie uma turma acima para começar.")
        else:
            st.markdown("### ⚙️ Gestão da Turma")
            t_ativa = st.selectbox("📍 Selecione a Turma para gerenciar:", t_db['nome'].tolist())
            id_t_ativa = t_db[t_db['nome'] == t_ativa]['id'].values[0]
            
            modelos_disponiveis = pd.read_sql("SELECT DISTINCT titulo_modelo FROM modelos_ensino", conn)['titulo_modelo'].dropna().tolist()
            
            if not modelos_disponiveis:
                st.warning("⚠️ Crie um Modelo de Disciplina na aba 'Fábrica de Disciplinas' primeiro.")
            else:
                d_ativa = st.selectbox("📚 Disciplina a ser trabalhada nesta turma:", modelos_disponiveis)
                
                tabs_op = st.tabs(["🎓 1. Matricular Alunos", "🗓️ 2. Gerar Calendário Real", "⚖️ 3. Pesos de Notas", "📊 4. Painel da Turma"])

                with tabs_op[0]:
                    st.markdown(f"**Alunos cursando {d_ativa} em {t_ativa}**")
                    alunos_turma = pd.read_sql(f"SELECT id, nome, ra FROM alunos WHERE turma_id={id_t_ativa} ORDER BY nome", conn)
                    if alunos_turma.empty:
                        st.info("Nenhum aluno base cadastrado nesta turma.")
                    else:
                        matriculados = pd.read_sql(f"SELECT aluno_id FROM matriculas_disciplina WHERE turma_id={id_t_ativa} AND disciplina='{d_ativa}'", conn)['aluno_id'].tolist()
                        alunos_dict = dict(zip(alunos_turma['nome'], alunos_turma['id']))
                        nomes_pre_selecionados = [nome for nome, id_al in alunos_dict.items() if id_al in matriculados]
                        selecionados = st.multiselect("Selecione os alunos cursantes (ótimo para filtrar DP):", options=alunos_turma['nome'].tolist(), default=nomes_pre_selecionados if matriculados else alunos_turma['nome'].tolist())
                        if st.button("💾 Salvar Matrículas"):
                            conn.execute("DELETE FROM matriculas_disciplina WHERE turma_id=? AND disciplina=?", (int(id_t_ativa), d_ativa))
                            for nome in selecionados:
                                conn.execute("INSERT INTO matriculas_disciplina (turma_id, disciplina, aluno_id) VALUES (?,?,?)", (int(id_t_ativa), d_ativa, int(alunos_dict[nome])))
                            conn.commit(); st.success(f"Matrículas atualizadas!")

                with tabs_op[1]:
                    c1, c2 = st.columns(2)
                    d_ini = c1.date_input("Início das aulas:", datetime.today())
                    d_fim = c2.date_input("Fim do semestre:", datetime.today() + timedelta(days=120))
                    dias_w = st.multiselect("Dias da semana com aula:", ["Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado"], default=["Segunda"])
                    feriados = st.text_input("Feriados (separados por vírgula):", placeholder="21/04/2026")
                    
                    if st.button("🚀 Gerar Cronograma Real"):
                        m_ensino = conn.execute("SELECT * FROM modelos_ensino WHERE titulo_modelo=?", (d_ativa,)).fetchone()
                        molde_aulas = conn.execute("SELECT num_aula, tema, objetivos_aula, conteudo_detalhado, referencias_aula, materiais_link FROM roteiro_mestre WHERE titulo_modelo=? ORDER BY num_aula", (d_ativa,)).fetchall()
                        if not molde_aulas: st.error("Molde vazio na Fábrica!"); st.stop()
                        
                        conn.execute("DELETE FROM cronograma_detalhado WHERE turma_id=? AND disciplina=?", (int(id_t_ativa), d_ativa))
                        conn.execute("DELETE FROM plano_ensino_turma WHERE turma_id=? AND disciplina=?", (int(id_t_ativa), d_ativa))
                        
                        conn.execute('''INSERT INTO plano_ensino_turma (turma_id, disciplina, ementa, objetivos, competencias, egresso, conteudo_prog, metodologia, recursos, avaliacao, aps, bib_basica, bib_complementar, outras_ref) 
                                        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)''', 
                                     (int(id_t_ativa), d_ativa, m_ensino[2], m_ensino[3], m_ensino[4], m_ensino[5], m_ensino[6], m_ensino[7], m_ensino[8], m_ensino[9], m_ensino[10], m_ensino[11], m_ensino[12], m_ensino[13]))
                        
                        mapa = {"Segunda":0,"Terça":1,"Quarta":2,"Quinta":3,"Sexta":4,"Sábado":5}
                        idx_dias = [mapa[d] for d in dias_w]
                        list_f = [f.strip() for f in feriados.split(",") if f.strip()]
                        
                        curr, a_idx = d_ini, 0
                        while curr <= d_fim and a_idx < len(molde_aulas):
                            ds = curr.strftime("%d/%m/%Y")
                            if curr.weekday() in idx_dias and ds not in list_f:
                                n, t, o, c, r, m = molde_aulas[a_idx]
                                conn.execute("INSERT INTO cronograma_detalhado (turma_id, disciplina, num_aula, data, tema, objetivos_aula, conteudo_detalhado, referencias_aula, materiais_link) VALUES (?,?,?,?,?,?,?,?,?)", 
                                             (int(id_t_ativa), d_ativa, n, ds, t, o, c, r, m))
                                a_idx += 1
                            curr += timedelta(days=1)
                        conn.commit(); st.success(f"Cronograma agendado!")

                # --- LIGAÇÃO RESTAURADA COM O BOLETIM MESTRE ---
                with tabs_op[2]:
                    st.markdown(f"**Pesos das avaliações de {d_ativa}** (Alimenta o Boletim)")
                    df_p = pd.read_sql(f"SELECT nome_avaliacao, peso, data_prevista FROM planejamento_notas WHERE turma_id={id_t_ativa} AND disciplina='{d_ativa}'", conn)
                    ed_p = st.data_editor(df_p if not df_p.empty else pd.DataFrame([{"nome_avaliacao": "P1", "peso": 4.0, "data_prevista": ""}]), num_rows="dynamic", use_container_width=True)
                    if st.button("💾 Salvar Pesos"):
                        conn.execute(f"DELETE FROM planejamento_notas WHERE turma_id={id_t_ativa} AND disciplina='{d_ativa}'")
                        for _, r in ed_p.iterrows():
                            conn.execute("INSERT INTO planejamento_notas (turma_id, disciplina, nome_avaliacao, peso, data_prevista) VALUES (?,?,?,?,?)", (int(id_t_ativa), d_ativa, r['nome_avaliacao'], r['peso'], r['data_prevista']))
                        conn.commit(); st.success("Pesos atualizados!")

                with tabs_op[3]:
                    df_cron = pd.read_sql(f"SELECT num_aula as 'Aula', data as 'Data', tema as 'Tema' FROM cronograma_detalhado WHERE turma_id={id_t_ativa} AND disciplina='{d_ativa}' ORDER BY num_aula", conn)
                    if df_cron.empty:
                        st.info("Calendário ainda não gerado.")
                    else:
                        st.markdown(f"#### 🎓 Alunos Matriculados e Perfis")
                        alunos_m = pd.read_sql(f"SELECT a.id, a.nome as Nome, a.ra as RA, a.email, a.observacoes FROM alunos a JOIN matriculas_disciplina m ON a.id = m.aluno_id WHERE m.turma_id={id_t_ativa} AND m.disciplina='{d_ativa}' ORDER BY a.nome", conn)
                        if not alunos_m.empty:
                            st.dataframe(alunos_m[['Nome', 'RA']], use_container_width=True, hide_index=True)
                            with st.expander("🔍 Editar Detalhes e Observações do Aluno"):
                                al_sel = st.selectbox("Selecione um aluno:", alunos_m['Nome'].tolist())
                                if al_sel:
                                    det_al = alunos_m[alunos_m['Nome'] == al_sel].iloc[0]
                                    c_det1, c_det2 = st.columns(2)
                                    email_al = c_det1.text_input("E-mail para contato:", value=det_al['email'] or "", key=f"em_{det_al['id']}")
                                    obs_al = c_det2.text_area("Notas (TDAH, dificuldades):", value=det_al['observacoes'] or "", key=f"obs_{det_al['id']}")
                                    if st.button("💾 Salvar Perfil", key=f"btn_{det_al['id']}", use_container_width=True):
                                        conn.execute("UPDATE alunos SET email=?, observacoes=? WHERE id=?", (email_al, obs_al, int(det_al['id'])))
                                        conn.commit(); st.success("Perfil atualizado!")
                        
                        st.write("---")
                        st.markdown(f"#### 🗓️ Cronograma Real (Planejado vs. Executado)")
                        df_plan = pd.read_sql(f"SELECT * FROM cronograma_detalhado WHERE turma_id={id_t_ativa} AND disciplina='{d_ativa}' ORDER BY num_aula", conn)
                        df_real = pd.read_sql(f"SELECT data, conteudo_real, observacao FROM diario_conteudo WHERE turma_id={id_t_ativa} AND disciplina='{d_ativa}'", conn)

                        for _, aula in df_plan.iterrows():
                            reg = df_real[df_real['data'] == aula['data']]
                            icone = "✅" if not reg.empty else "📅"
                            with st.expander(f"{icone} Aula {aula['num_aula']} - {aula['data']} - {aula['tema']}"):
                                ca, cb = st.columns(2)
                                with ca:
                                    st.markdown("**📝 Planejado (Roteiro)**")
                                    st.write(f"**Conteúdo:** {aula['conteudo_detalhado'] or 'Sem detalhamento'}")
                                    if aula['materiais_link']: st.link_button("🔗 Abrir Material", aula['materiais_link'])
                                with cb:
                                    st.markdown("**🖋️ Diário de Sala**")
                                    if not reg.empty:
                                        st.success(f"**Realizado:** {reg['conteudo_real'].iloc[0]}")
                                        st.info(f"**Observações:** {reg['observacao'].iloc[0]}")
                                    else: st.warning("Aula ainda não realizada.")
with aba_gen:
    if "arquivos" not in st.session_state: st.session_state.arquivos = []
    if "prova_atual" not in st.session_state: st.session_state.prova_atual = []

    st.subheader("⚙️ 1. Configuração do Cabeçalho")
    if "cabecalho_carregado" not in st.session_state:
        st.session_state.inp_inst, st.session_state.inp_prof, st.session_state.inp_dep, st.session_state.inp_cur, st.session_state.inp_instruc = carregar_configuracoes()
        st.session_state.inp_turma, st.session_state.inp_data = "", ""
        st.session_state.cabecalho_carregado = True

    c_cab_b1, c_cab_b2, c_cab_b3 = st.columns([0.3, 0.3, 0.4])
    if c_cab_b1.button("🔄 Carregar Padrão"): st.rerun()
    if c_cab_b2.button("🧹 Limpar Campos"):
        for k in ["inp_inst", "inp_prof", "inp_dep", "inp_cur", "inp_turma", "inp_data", "inp_instruc"]: st.session_state[k] = ""
        st.rerun()
    if c_cab_b3.button("💾 Salvar como Padrão"):
        salvar_configuracoes(st.session_state.inp_inst, st.session_state.inp_prof, st.session_state.inp_dep, st.session_state.inp_cur, st.session_state.inp_instruc)
        st.success("Padrão atualizado!")

    c_cab1, c_cab2 = st.columns(2)
    inst_nome = c_cab1.text_input("Instituição", key="inp_inst")
    prof_nome = c_cab2.text_input("Professor(a)", key="inp_prof")
    c_cab3, c_cab4, c_cab5 = st.columns(3)
    depto, curs, turma_p = c_cab3.text_input("Depto", key="inp_dep"), c_cab4.text_input("Curso", key="inp_cur"), c_cab5.text_input("Turma", key="inp_turma")
    # Procure as colunas c_cab6 e c_cab7 e troque por isso:
    c_cab6, c_cab7 = st.columns(2)
    data_p = c_cab6.text_input("Data", key="inp_data")
    # Colocamos o título ao lado da data para economizar espaço
    titulo_doc = c_cab7.text_input("Título do Documento", value="Avaliação 01", key="inp_titulo")
    
    # A Logo e as Instruções ficam embaixo ocupando a largura toda
    logo_up = st.file_uploader("Logo da Instituição (PNG/JPG)", type=["png", "jpg", "jpeg"])
    instrucoes = st.text_area("Instruções", key="inp_instruc")
    # --- NOVO: CAMPO PARA LISTA DE ALUNOS ---
    st.write("---")
    st.subheader("📋 Identificação dos Alunos nas Provas")
    
    modo_id = st.radio("Como deseja identificar as provas?", 
                       ["Em Branco (Sem Nome/RA)", "Usar Turma Cadastrada", "Upload Temporário de Lista"], horizontal=True)
    
    arquivo_lista = None
    alunos_selecionados_df = None
    q_a = 1 # Valor padrão de segurança

    # A PERGUNTA SÓ APARECE SE ESCOLHER "EM BRANCO"
    if modo_id == "Em Branco (Sem Nome/RA)":
        st.info("💡 Como não há uma lista de nomes, o sistema precisa saber quantas cópias genéricas deve criar.")
        q_a = st.number_input("Quantas provas em branco deseja gerar?", min_value=1, max_value=300, value=30)
        
    elif modo_id == "Upload Temporário de Lista":
        st.caption("Suba um Excel/CSV que será usado apenas agora e não será salvo no banco.")
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
                selecao = st.multiselect("Selecione os alunos (deixe vazio para gerar para a turma toda):", opcoes_alunos)
                
                if selecao: # Se escolheu nomes específicos
                    alunos_selecionados_df = alunos_da_turma[alunos_da_turma['NOME'].isin(selecao)]
                else: # Se não escolheu nenhum, pega todos
                    alunos_selecionados_df = alunos_da_turma
                st.success(f"{len(alunos_selecionados_df)} aluno(s) selecionado(s) para a prova.")
            else:
                st.warning("Esta turma ainda não tem alunos cadastrados.")
        else:
            st.warning("Nenhuma turma cadastrada. Vá à aba 'Turmas'.")
        conn.close()

    st.subheader("🎯 2. Seleção de Questões")
    
    # ERAM 4 COLUNAS, AGORA SÃO 3 (A de 'Alunos' sumiu daqui!)
    col_p1, col_p2, col_p3 = st.columns(3) 
    d_p = col_p1.selectbox("Disciplina", ["Termodinâmica", "Mecânica dos Fluidos", "TCC 1"], key="g_disc")
    q_v = col_p2.number_input("Versões", 1, 10, 1)
    layout_colunas = col_p3.radio("Layout", ["1 Coluna", "2 Colunas"], horizontal=True)
    
    # Transforma a escolha em um número (1 ou 2) para mandar pro arquivo LaTeX
    num_colunas = 2 if layout_colunas == "2 Colunas" else 1

    modo_selecao = st.radio("Modo", ["Sorteio Automático", "Escolha Manual"], horizontal=True)

    if modo_selecao == "Sorteio Automático":
        if "num_regras" not in st.session_state: st.session_state.num_regras = 1
        
        # 👇 BOTÕES RESTAURADOS PARA ADICIONAR/REMOVER REGRAS 👇
        c_btn_r1, c_btn_r2, _ = st.columns([0.2, 0.2, 0.6])
        if c_btn_r1.button("➕ Adicionar Regra"): 
            st.session_state.num_regras += 1
            st.rerun()
        if c_btn_r2.button("➖ Remover Regra") and st.session_state.num_regras > 1: 
            st.session_state.num_regras -= 1
            st.rerun()

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
        if st.button("➕ Adicionar"):
            for n in sel:
                q = opcoes[n]
                if q[0] not in [x['id'] for x in st.session_state.prova_atual]:
                    st.session_state.prova_atual.append({"id": q[0], "enunciado": q[1], "imagem": q[2], "pontos": q[3], "tipo": q[4], "gabarito": q[5], "espaco": q[6], "espaco_linhas": q[7], "dificuldade": q[8], "assunto": q[9], "gabarito_imagem": q[10]})
            st.rerun()

    # --- SEÇÃO 3: PRÉVIA E EDIÇÃO TOTAL ---
    if st.session_state.prova_atual:
        st.write("---")
        st.subheader("👀 3. Prévia Rápida e Ajustes Finos")
        pontos_totais, remover = 0, []
        
        for i, q in enumerate(st.session_state.prova_atual):
            with st.expander(f"Q{i+1} | {q['tipo']} | Assunto: {q['assunto']} | ID: {q['id']}"):
                
                c_m1, c_m2, c_m3 = st.columns([0.4, 0.3, 0.3])
                n_assunto = c_m1.text_input("Assunto", value=q['assunto'], key=f"prev_ass_{i}")
                
                lista_dif = ["Fácil", "Média", "Difícil"]
                n_dif = c_m2.selectbox("Dificuldade", lista_dif, index=lista_dif.index(q['dificuldade']) if q['dificuldade'] in lista_dif else 1, key=f"prev_dif_{i}")
                
                lista_tipos = ["Múltipla Escolha", "Verdadeiro ou Falso", "Discursiva", "Numérica"]
                n_tipo = c_m3.selectbox("Tipo de Questão", lista_tipos, index=lista_tipos.index(q['tipo']), key=f"prev_tipo_{i}")

                if f"prev_enun_{i}" not in st.session_state: st.session_state[f"prev_enun_{i}"] = q['enunciado']
                
                c_en1, c_en2 = st.columns([0.85, 0.15])
                with c_en1: n_enun = st.text_area("Enunciado", key=f"prev_enun_{i}", height=100)
                with c_en2: 
                    st.write(" ")
                    painel_flutuante(f"prev_enun_{i}", f"prev_p_e_{i}_")
                
                # Preview devolvido na Geração!
                if n_enun:
                    st.markdown("**Preview LaTeX:**")
                    st.markdown(n_enun)

                if q.get('imagem'): st.caption(f"🖼️ Imagem Enunciado Atual: {q['imagem']}")
                n_img = st.file_uploader("Trocar Imagem do Enunciado", type=["png", "jpg", "jpeg"], key=f"prev_img_{i}")

                c_e1, c_e2, c_e3 = st.columns(3)
                novo_pt = c_e1.number_input("Pontos", value=float(q['pontos']), step=0.5, key=f"prev_pt_{i}")
                n_esp = c_e2.selectbox("Espaço", ["Linhas", "Quadriculado", "Caixa Vazia", "Nenhum"], index=["Linhas", "Quadriculado", "Caixa Vazia", "Nenhum"].index(q['espaco']), key=f"prev_esp_{i}")
                n_tam = c_e3.number_input("Tamanho", 1, 20, value=int(q['espaco_linhas']), key=f"prev_tam_{i}")
                
                letras = "ABCDEFGHIJ"
                alts_modificadas, gab_d_final = [], q['gabarito']
                n_img_gab = None
                alts_imagens_novas = {}
                
                conn = sqlite3.connect('banco_provas.db')
                c = conn.cursor()
                c.execute('SELECT texto, correta, imagem FROM alternativas WHERE questao_id = ? ORDER BY id', (q['id'],))
                alts_q = c.fetchall()
                conn.close()
                
                if n_tipo == "Múltipla Escolha":
                    n_opt_key = f"n_opt_prev_{q['id']}"
                    if n_opt_key not in st.session_state: st.session_state[n_opt_key] = max(len(alts_q), 4)
                    
                    cb1, cb2 = st.columns([0.2, 0.8])
                    if cb1.button("➕ Adicionar Linha", key=f"prev_add_l_{i}"): st.session_state[n_opt_key] += 1
                    if cb2.button("➖ Remover Linha", key=f"prev_rm_l_{i}") and st.session_state[n_opt_key] > 2: st.session_state[n_opt_key] -= 1

                    for j in range(st.session_state[n_opt_key]):
                        col_c, col_t, col_p, col_i = st.columns([0.1, 0.45, 0.15, 0.3])
                        corr_val = bool(alts_q[j][1]) if j < len(alts_q) else False
                        img_atual_alt = alts_q[j][2] if j < len(alts_q) else None
                        
                        corr = col_c.checkbox(f"**{letras[j]}**", value=corr_val, key=f"prev_c_alt_{i}_{j}")
                        
                        key_txt_alt = f"prev_t_alt_{i}_{j}"
                        if key_txt_alt not in st.session_state: st.session_state[key_txt_alt] = alts_q[j][0] if j < len(alts_q) else ""
                        
                        txt = col_t.text_input(f"Alt {letras[j]}", label_visibility="collapsed", key=key_txt_alt)
                        with col_p: painel_flutuante(key_txt_alt, f"prev_p_alt_{i}_{j}_")
                        
                        if img_atual_alt: col_i.caption(f"Atual: {img_atual_alt}")
                        up_img_alt = col_i.file_uploader(f"Img {letras[j]}", type=["png", "jpg", "jpeg"], key=f"prev_i_alt_{i}_{j}", label_visibility="collapsed")
                        
                        alts_imagens_novas[j] = up_img_alt if up_img_alt else img_atual_alt
                        alts_modificadas.append((txt, corr))

                elif n_tipo == "Verdadeiro ou Falso":
                    is_verdadeiro = any(a[0] == "Verdadeiro" and a[1] for a in alts_q)
                    resp = st.radio("Gabarito:", ["Verdadeiro", "Falso"], index=0 if is_verdadeiro else 1, horizontal=True, key=f"prev_vf_{i}")
                    alts_modificadas = [("Verdadeiro", resp == "Verdadeiro"), ("Falso", resp == "Falso")]
                else:
                    c_g1, c_g2 = st.columns([0.85, 0.15])
                    if f"prev_gab_{i}" not in st.session_state: st.session_state[f"prev_gab_{i}"] = q['gabarito'] if q['gabarito'] else ""
                    with c_g1: gab_d_final = st.text_area("Gabarito da Professora", key=f"prev_gab_{i}", height=100)
                    with c_g2: 
                        st.write(" ")
                        painel_flutuante(f"prev_gab_{i}", f"prev_p_g_{i}_")
                    
                    if q.get('gabarito_imagem'): st.caption(f"🖼️ Imagem Gabarito Atual: {q['gabarito_imagem']}")
                    n_img_gab = st.file_uploader("Trocar imagem da Resolução", type=["png", "jpg", "jpeg"], key=f"prev_img_gab_{i}")

                c_btn1, c_btn2 = st.columns(2)
                if c_btn1.button("💾 Salvar Alteração no Banco", key=f"save_p_{i}", type="primary"):
                    img_final = q.get('imagem')
                    if n_img: 
                        img_final = sanitizar_nome(n_img.name)
                        with open(img_final, "wb") as f: f.write(n_img.getbuffer())
                        
                    img_gab_final = q.get('gabarito_imagem')
                    if n_img_gab:
                        img_gab_final = sanitizar_nome(n_img_gab.name)
                        with open(img_gab_final, "wb") as f: f.write(n_img_gab.getbuffer())

                    conn = sqlite3.connect('banco_provas.db')
                    c = conn.cursor()
                    c.execute('''UPDATE questoes SET enunciado=?, pontos=?, espaco_resposta=?, espaco_linhas=?, 
                                 assunto=?, dificuldade=?, tipo=?, imagem=?, gabarito_imagem=?, gabarito_discursivo=? WHERE id=?''', 
                              (n_enun, novo_pt, n_esp, n_tam, n_assunto, n_dif, n_tipo, img_final, img_gab_final, gab_d_final, q['id']))
                    
                    if n_tipo in ["Múltipla Escolha", "Verdadeiro ou Falso"]:
                        c.execute('DELETE FROM alternativas WHERE questao_id = ?', (q['id'],))
                        for j, data_alt in enumerate(alts_modificadas):
                            txt_alt, corr_alt = data_alt[0], data_alt[1]
                            img_alt_bd = None
                            if n_tipo == "Múltipla Escolha":
                                img_alt_obj = alts_imagens_novas[j]
                                if hasattr(img_alt_obj, 'getbuffer'):
                                    img_alt_bd = sanitizar_nome(img_alt_obj.name)
                                    with open(img_alt_bd, "wb") as f: f.write(img_alt_obj.getbuffer())
                                else:
                                    img_alt_bd = img_alt_obj
                            c.execute('INSERT INTO alternativas (questao_id, texto, correta, imagem) VALUES (?, ?, ?, ?)', (q['id'], txt_alt, corr_alt, img_alt_bd))
                            
                    conn.commit(); conn.close()
                    st.session_state.prova_atual[i].update({
                        "enunciado": n_enun, "pontos": novo_pt, "espaco": n_esp, "espaco_linhas": n_tam,
                        "assunto": n_assunto, "dificuldade": n_dif, "tipo": n_tipo, 
                        "imagem": img_final, "gabarito_imagem": img_gab_final, "gabarito": gab_d_final
                    })
                    st.success("Tudo salvo com sucesso no banco de dados!")
                    st.rerun()
                    
                if c_btn2.button("🗑️ Remover da Prova", key=f"rm_p_{i}"): remover.append(i)
                pontos_totais += novo_pt

        if remover:
            for idx in sorted(remover, reverse=True): st.session_state.prova_atual.pop(idx)
            st.rerun()
        
        # --- AVISO ANTI-DISTRAÇÃO DA MARI ---
        st.info(f"**Total de Pontos:** {pontos_totais}")
        
        if pontos_totais != 10.0:
            st.warning(f"⚠️ **Aviso:** A soma dos pontos está em **{pontos_totais}** (diferente de 10.0). A prova será gerada mesmo assim se você clicar em confirmar!")
        else:
            st.success("✅ Pontuação perfeita! A prova soma exatamente 10 pontos.")
        # ------------------------------------
        
        # 👇 NOVOS CONTROLES DE EMBARALHAMENTO 👇
        st.write("---")
        st.subheader("🔀 Regras de Criação")
        col_emb1, col_emb2 = st.columns(2)
        opt_emb_q = col_emb1.checkbox("Embaralhar a Ordem das Questões", value=True, help="Cada prova terá as questões em uma ordem diferente.")
        opt_emb_a = col_emb2.checkbox("Embaralhar as Alternativas (A, B, C...)", value=True, help="As opções corretas mudarão de letra para cada aluno.")

        if st.button("✅ 4. Confirmar e Gerar PDFs"):
            st.session_state.arquivos = {} 
            
            # --- NOVA LÓGICA DE DEFINIÇÃO DA LISTA DE ALUNOS ---
            if modo_id == "Em Branco (Sem Nome/RA)":
                df_alunos = pd.DataFrame({'NOME': ['__________________________'] * q_a, 'RA': ['__________'] * q_a})
                
            elif modo_id == "Usar Turma Cadastrada" and alunos_selecionados_df is not None:
                df_alunos = alunos_selecionados_df
                
            elif modo_id == "Upload Temporário de Lista" and arquivo_lista is not None:
                if arquivo_lista.name.endswith('.xlsx'): df_alunos = pd.read_excel(arquivo_lista)
                else: df_alunos = pd.read_csv(arquivo_lista, sep=None, engine='python')
                
                df_alunos.columns = df_alunos.columns.str.strip().str.upper()
                colunas_lidas = df_alunos.columns.tolist()
                
                sinonimos_nome = ['NOME', 'ALUNO', 'CANDIDATO', 'ESTUDANTE', 'NOME COMPLETO', 'NOME DO ALUNO']
                sinonimos_ra = ['RA', 'REGISTRO', 'MATRICULA', 'MATRÍCULA', 'ID', 'INSCRIÇÃO']
                
                col_n = next((col for col in colunas_lidas if col in sinonimos_nome), None)
                col_r = next((col for col in colunas_lidas if col in sinonimos_ra), None)
                
                if not col_n or not col_r:
                    st.error("⚠️ Erro na Planilha! Não consegui identificar as colunas NOME e RA.")
                    st.stop()
                df_alunos = df_alunos.rename(columns={col_n: 'NOME', col_r: 'RA'}).dropna(subset=['NOME', 'RA'])

            # PREVENÇÃO DE ERRO DA LOGO
            nome_logo = "logo.png"
            if logo_up is not None:
                nome_logo = sanitizar_nome(logo_up.name)
                with open(nome_logo, "wb") as f: f.write(logo_up.getbuffer())
            elif not os.path.exists("logo.png"):
                cv2.imwrite("logo.png", np.zeros((100, 100, 3), dtype=np.uint8) + 255)

            pdfs_provas = []
            pdfs_gabaritos = []

            for index, linha in df_alunos.iterrows():
                aluno_nome = str(linha['NOME'])
                aluno_ra = str(linha['RA']).replace('.0', '')
                
                # 🟢 IDENTIFICAÇÃO ÚNICA DA PROVA (A MÁGICA AQUI)
                v_num = index % q_v 
                let_v = "ABCDEFGHIJ"[v_num]
                
                if modo_id == "Em Branco (Sem Nome/RA)":
                    id_unico = f"{index+1:03d}" # Gera 001, 002...
                    let_v = f"{let_v}-{id_unico}" # Fica escondido no topo da prova: Versão A-001
                    titulo_gabarito = f"Cópia {id_unico} (Prova em Branco)"
                else:
                    titulo_gabarito = f"Aluno(a): {aluno_nome} (RA: {aluno_ra})"
                
                q_list = list(st.session_state.prova_atual)
                
                if opt_emb_q:
                    random.shuffle(q_list)
                    
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
                        
                    else: # Discursiva
                        d_pdf.append({"enunciado": en_s, "imagem": img_q, "pontos": q_item['pontos'], "tipo": q_item['tipo'], "alternativas": [], "espaco": q_item['espaco'], "espaco_linhas": q_item['espaco_linhas'], "resposta_esperada": gab_txt, "gabarito_imagem": gab_img})
                        qr_obj[idx] = "DISC" 
                
                # 🟢 GARANTINDO NOMES ÚNICOS PARA PROVAS EM BRANCO E CÓDIGO SECRETO
                sufixo_arquivo = f"{sanitizar_nome(aluno_ra)}_{index}"
                
                # 🕵️ Mapeando Letra para Número (A=01, B=02, C=03...)
                cod_secreto = f"0{v_num + 1}"
                if modo_id == "Em Branco (Sem Nome/RA)":
                    cod_secreto += f"-{id_unico}" # Fica: 01-001, 01-002...

                dados_qrcode = {"ra": aluno_ra, "nome": aluno_nome, "v": let_v, "gab": qr_obj, "d": d_p}
                qr_fn = f"qr_{sufixo_arquivo}.png"
                qrcode.make(json.dumps(dados_qrcode)).save(qr_fn)

                cab = {
                    "titulo_documento": escapar_latex(titulo_doc), # Título que você digitou no Streamlit
                    "logo_path": nome_logo,
                    "instituicao": escapar_latex(inst_nome),
                    "professor_nome": escapar_latex(prof_nome),
                    "disciplina_nome": escapar_latex(d_p),
                    "data": escapar_latex(data_p),
                    "turma": escapar_latex(turma_p),
                    "curso": escapar_latex(curs),
                    "instrucoes_texto": escapar_latex(instrucoes),
                    "num_copias": 1, 
                    "qr_path": qr_fn,
                    "versao_letra": let_v,
                    "colunas": num_colunas,
                    "aluno_nome": escapar_latex(aluno_nome) if modo_id != "Em Branco (Sem Nome/RA)" else "",
                    "aluno_ra": aluno_ra if modo_id != "Em Branco (Sem Nome/RA)" else "",
                    "titulo_gabarito": escapar_latex(titulo_gabarito),
                    "codigo_secreto": cod_secreto # <-- Enviando o código para o LaTeX
                }
                
                env = configurar_jinja()
                
                n_p = f"Prova_{sufixo_arquivo}"
                with open(f"{n_p}.tex", 'w', encoding='utf-8') as f: 
                    f.write(env.get_template('template_profissional.tex').render(**cab, questoes=d_pdf))
                if compilar_latex_mac(f"{n_p}.tex"):
                    pdfs_provas.append(f"{n_p}.pdf")
                    
                n_g = f"Gabarito_{sufixo_arquivo}"
                with open(f"{n_g}.tex", 'w', encoding='utf-8') as f: 
                    f.write(env.get_template('template_gabarito.tex').render(**cab, questoes=d_pdf))
                if compilar_latex_mac(f"{n_g}.tex"):
                    pdfs_gabaritos.append(f"{n_g}.pdf")

            # 📦 COSTURA FINAL DOS PDFs
            if pdfs_provas:
                st.info("📦 Unificando todas as provas em um único arquivo...")
                tex_merge_provas = "\\documentclass{article}\n\\usepackage{pdfpages}\n\\begin{document}\n"
                for p in pdfs_provas: tex_merge_provas += f"\\includepdf[pages=-]{{{p}}}\n"
                tex_merge_provas += "\\end{document}"
                with open("Lote_Provas_Turma.tex", 'w', encoding='utf-8') as f: f.write(tex_merge_provas)
                if compilar_latex_mac("Lote_Provas_Turma.tex"):
                    st.session_state.arquivos['provas'] = "Lote_Provas_Turma.pdf"

            if pdfs_gabaritos:
                st.info("✅ Unificando todos os gabaritos para a professora...")
                tex_merge_gabs = "\\documentclass{article}\n\\usepackage{pdfpages}\n\\begin{document}\n"
                for p in pdfs_gabaritos: tex_merge_gabs += f"\\includepdf[pages=-]{{{p}}}\n"
                tex_merge_gabs += "\\end{document}"
                with open("Lote_Gabaritos_Turma.tex", 'w', encoding='utf-8') as f: f.write(tex_merge_gabs)
                if compilar_latex_mac("Lote_Gabaritos_Turma.tex"):
                    st.session_state.arquivos['gabaritos'] = "Lote_Gabaritos_Turma.pdf"

            # 🧹 Faxina
            for p in pdfs_provas + pdfs_gabaritos:
                if os.path.exists(p): os.remove(p)

            st.success("Processamento finalizado com sucesso!")
            limpar_arquivos_temporarios()

    # --- BOTÕES DE DOWNLOAD ---
    if st.session_state.get("arquivos"):
        st.write("---")
        st.subheader("📥 Arquivos Prontos")
        
        c_dl1, c_dl2 = st.columns(2)
        
        arq_provas = st.session_state.arquivos.get('provas')
        if arq_provas and os.path.exists(arq_provas):
            with open(arq_provas, "rb") as pdf_file:
                c_dl1.download_button(
                    label="📄 Baixar Lote de PROVAS (Único PDF)", 
                    data=pdf_file, 
                    file_name=f"Provas_Turma_{datetime.now().strftime('%Y%m%d')}.pdf",
                    type="primary",
                    use_container_width=True,
                    key="btn_dl_provas_mestre"
                )
                
        arq_gabs = st.session_state.arquivos.get('gabaritos')
        if arq_gabs and os.path.exists(arq_gabs):
            with open(arq_gabs, "rb") as pdf_file:
                c_dl2.download_button(
                    label="📝 Baixar Lote de GABARITOS (Único PDF)", 
                    data=pdf_file, 
                    file_name=f"Gabaritos_Turma_{datetime.now().strftime('%Y%m%d')}.pdf",
                    use_container_width=True,
                    key="btn_dl_gabs_mestre"
                )
    # -----------------------------------------------------------
# --- ABA DE EDIÇÃO COMPLETA DO BANCO ---
with aba_edit:
    st.subheader("🔍 Gerenciar e Editar Banco de Questões")
    st.write("Edite todos os detalhes, fórmulas e imagens das questões salvas.")

    conn = sqlite3.connect('banco_provas.db')
    df_todas = pd.read_sql('SELECT id, disciplina, assunto, dificuldade, tipo, enunciado FROM questoes ORDER BY id DESC', conn)
    conn.close()

    if not df_todas.empty:
        col_f1, col_f2 = st.columns(2)
        disc_filtro = col_f1.selectbox("Filtrar por Disciplina:", ["Todas"] + list(df_todas['disciplina'].unique()), key="ed_filtro_disc")
        tipo_filtro = col_f2.selectbox("Filtrar por Tipo:", ["Todos"] + list(df_todas['tipo'].unique()), key="ed_filtro_tipo")

        df_filtrado = df_todas.copy()
        if disc_filtro != "Todas": df_filtrado = df_filtrado[df_filtrado['disciplina'] == disc_filtro]
        if tipo_filtro != "Todos": df_filtrado = df_filtrado[df_filtrado['tipo'] == tipo_filtro]

        opcoes_q = ["Escolha uma questão..."] + [f"ID {row['id']} | {row['disciplina']} | {row['assunto']} | {row['enunciado'][:50]}..." for _, row in df_filtrado.iterrows()]
        q_sel = st.selectbox("Selecione a questão:", opcoes_q, key="ed_q_sel")

        if q_sel != "Escolha uma questão...":
            id_editar = int(q_sel.split(" | ")[0].replace("ID ", ""))

            # Puxa TUDO do banco de dados
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
                # Chave única baseada no ID para não misturar textos de questões diferentes
                key_enun = f"ed_enun_{id_editar}"
                if key_enun not in st.session_state: st.session_state[key_enun] = q_enun
                
                c_e1, c_e2 = st.columns([0.85, 0.15])
                with c_e1: n_enun_final = st.text_area("Enunciado da Questão:", key=key_enun, height=120)
                with c_e2: 
                    st.write(" ")
                    painel_flutuante(key_enun, "ed_p_e_")

                if q_img: st.caption(f"🖼️ Imagem Atual: {q_img}")
                n_img_up = st.file_uploader("Trocar Imagem (Enunciado)", type=["png", "jpg", "jpeg"], key="ed_img_up")

                # Lógica das Alternativas
                c.execute('SELECT texto, correta, imagem FROM alternativas WHERE questao_id = ? ORDER BY id', (id_editar,))
                alts_q = c.fetchall()
                
                alts_modificadas = []
                alts_imagens_novas = {}
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

                # Botoes salvar/excluir
                st.write("---")
                c_btn1, c_btn2 = st.columns(2)
                if c_btn1.button("💾 Salvar Alterações no Banco", type="primary", width="stretch"):
                    # Salva as imagens se foram trocadas
                    img_final = q_img
                    if n_img_up: 
                        img_final = sanitizar_nome(n_img_up.name)
                        with open(img_final, "wb") as f: f.write(n_img_up.getbuffer())
                        
                    img_gab_final = q_gab_img
                    if n_img_gab_up:
                        img_gab_final = sanitizar_nome(n_img_gab_up.name)
                        with open(img_gab_final, "wb") as f: f.write(n_img_gab_up.getbuffer())

                    # Grava TUDO no banco
                    c.execute('''UPDATE questoes SET disciplina=?, assunto=?, dificuldade=?, enunciado=?, pontos=?, espaco_resposta=?, espaco_linhas=?, 
                                 tipo=?, imagem=?, gabarito_imagem=?, gabarito_discursivo=? WHERE id=?''', 
                              (n_disc, n_ass, n_dif, n_enun_final, n_pts, n_esp, n_tam, n_tipo, img_final, img_gab_final, gab_d_final, id_editar))
                    
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
                                else:
                                    img_alt_bd = img_alt_obj
                            c.execute('INSERT INTO alternativas (questao_id, texto, correta, imagem) VALUES (?, ?, ?, ?)', (id_editar, txt_alt, corr_alt, img_alt_bd))
                            
                    conn.commit()
                    st.success("Tudo atualizado com sucesso no banco de dados!")
                    st.rerun()

                if c_btn2.button("🗑️ Excluir Questão (Cuidado)", width="stretch"):
                    excluir_questao(id_editar)
                    st.warning("Questão apagada definitivamente.")
                    st.rerun()

            conn.close()
    else:
        st.info("O seu banco de questões ainda está vazio.")
# --- ABA DE CORREÇÃO: VERSÃO BLINDADA (COM ELEIÇÃO DE COLUNA) ---
# --- ABA DE CORREÇÃO: VERSÃO INTEGRADA AO PLANEJAMENTO (SEM PERDER O MOTOR) ---
with aba_corr:
    st.subheader("📸 Corretor Automático (Lote PDF ou Foto)")

    with sqlite3.connect('banco_provas.db') as conn:
        turmas_df = pd.read_sql("SELECT id, nome FROM turmas", conn)
        
        if turmas_df.empty:
            st.warning("⚠️ Cadastre uma turma na aba 'Turmas' antes de começar.")
        else:
            # --- 1. SELEÇÃO INTELIGENTE (Puxando do seu Plano de Aula) ---
            c_sel1, c_sel2, c_sel3 = st.columns(3)
            
            t_corr_nome = c_sel1.selectbox("📋 Turma:", turmas_df['nome'].tolist(), key="t_corr_final")
            id_t_corr = turmas_df[turmas_df['nome'] == t_corr_nome]['id'].values[0]
            
            discs_plan = pd.read_sql(f"SELECT DISTINCT disciplina FROM planejamento_notas WHERE turma_id = {id_t_corr}", conn)
            lista_disc_corr = discs_plan['disciplina'].tolist() if not discs_plan.empty else ["Termodinâmica", "Mecânica dos Fluidos", "TCC 1"]
            d_corr_sel = c_sel2.selectbox("📚 Disciplina:", lista_disc_corr, key="d_corr_final")
            
            # Aqui está a mágica: busca as provas que você já planejou!
            df_plan = pd.read_sql(f"SELECT nome_avaliacao FROM planejamento_notas WHERE turma_id = {int(id_t_corr)} AND disciplina = '{d_corr_sel}'", conn)
            lista_ativ_plan = df_plan['nome_avaliacao'].tolist() if not df_plan.empty else []
            
            if lista_ativ_plan:
                prova_final_nome = c_sel3.selectbox("📝 Selecione a Prova do Plano:", lista_ativ_plan, key="p_corr_plan")
            else:
                st.info("💡 Nada planejado para esta disciplina ainda.")
                prova_final_nome = c_sel3.text_input("📝 Nome da Prova (Manual):", value="P1", key="p_corr_manual")

            st.write("---")

            # --- 2. SEUS AJUSTES DE MIRA ORIGINAIS (NADA FOI APAGADO) ---
            st.markdown("⚙️ **Ajuste Fino da Leitura (Mira OpenCV)**")
            c_aj = st.columns(3) 
            off_x = c_aj[0].slider("Mira Horizontal", -500, 400, -47, key="g_x")
            off_y = c_aj[1].slider("Mira Vertical", -100, 150, 6, key="g_y")
            p_x = c_aj[2].slider("Espaço Bolinhas", 10, 80, 20, key="g_px")
            
            c_aj2 = st.columns(3)
            dist_num = c_aj2[0].slider("Pulo Unidade (Engenharia)", 5.0, 25.0, 10.20, step=0.1, key="g_dnum")
            anc_x_limite = c_aj2[1].slider("Busca Lateral (Âncora)", 50, 500, 350, key="g_anc_x")
            anc_y_topo = c_aj2[2].slider("Ignorar Topo (Âncora)", 0, 800, 269, key="g_anc_y")
            
            st.write("---")
            img_file = st.file_uploader("Envie o PDF ou Fotos das Provas", type=['png', 'jpg', 'jpeg', 'pdf'], key="up_vfinal")

            if img_file is not None:
                # --- 3. PROCESSAMENTO DE IMAGEM / PDF ---
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

                # --- 4. O ROBÔ DE CORREÇÃO (O MOTOR ROBUSTO) ---
                for idx_img, img_orig in enumerate(imagens_para_processar):
                    try:
                        img = recortar_e_alinhar_folha(img_orig) 
                        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

                        # Leitura do QR Code
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

                        # MOTOR DE ÂNCORAS E ELEIÇÃO DE COLUNA (Sua técnica de blindagem)
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

                        # --- 5. MOTOR DE CORREÇÃO (LÓGICA LETRA + NÚMERO) ---
                        acertos_acumulados, resumos, overlay = 0.0, [], img.copy()
                        gab = dados_qr.get("gab", {})
                        if not gab: # Gabarito de segurança se o QR falhar
                            for i, q in enumerate(st.session_state.get('prova_atual', [])):
                                if q['tipo'] != "Discursiva": gab[str(i+1)] = f"{q['gabarito']}|{q['pontos']}"

                        for idx_q, (q_num, gab_val) in enumerate(sorted(gab.items(), key=lambda x: int(x[0]))):
                            certa_str, pts_q = str(gab_val).split("|")[0] if "|" in str(gab_val) else (str(gab_val), 1.0)
                            pts_q = float(pts_q)

                            y_base = ancoras_y[idx_q] if idx_q < len(ancoras_y) else ancoras_y[-1] + (38 * (idx_q - len(ancoras_y) + 1))
                            y_l, x_s = y_base - 12 + off_y, x_ancora + 65 + off_x
                            t_box = 24
                            
                            if certa_str not in ["A","B","C","D","E","V","F"]:
                                # LÓGICA NUMÉRICA (Cálculos de Engenharia)
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
                                # LÓGICA LETRAS
                                qtd_b = 2 if certa_str in ["V", "F"] else 5
                                letras_p = "VF" if certa_str in ["V", "F"] else "ABCDE"
                                cores = [cv2.countNonZero(thresh[y_l:y_l+t_box, (x_s+j*p_x):(x_s+j*p_x)+t_box]) for j in range(qtd_b)]
                                idx_max = int(np.argmax(cores))
                                lido = letras_p[idx_max] if cores[idx_max] > 45 else "Branco"
                                cv2.circle(overlay, (x_s+(idx_max*p_x)+12, y_l+12), 10, (0,255,0), -1)

                            if lido == certa_str: acertos_acumulados += pts_q
                            resumos.append({"Q": q_num, "Gabarito": certa_str, "Lido": lido, "OK": "✅" if lido == certa_str else "❌"})

                        # Exibição e Notas Discursivas
                        st.image(cv2.addWeighted(overlay, 0.4, img, 0.6, 0), caption=f"🎯 Processada: {dados_qr['nome']}")
                        
                        df_check = pd.DataFrame(resumos)
                        st.table(df_check.set_index("Q"))

                        c_n1, c_n2 = st.columns(2)
                        n_disc = c_n1.number_input(f"Nota Questões Abertas ({dados_qr['nome']}):", 0.0, 10.0, 0.0, 0.5, key=f"nd_{idx_img}")
                        nota_final_lote = acertos_acumulados + n_disc
                        c_n2.markdown(f"### 🏆 TOTAL: `{nota_final_lote:.2f}`")

                        if st.button(f"💾 Confirmar e Salvar: {dados_qr['nome']}", key=f"sv_{idx_img}"):
                            # Usa 'prova_final_nome' que veio do seu Planejamento!
                            salvar_resultado_prova(dados_qr['nome'], dados_qr['ra'], d_corr_sel, dados_qr['v'], nota_final_lote, prova_final_nome)
                            st.success(f"✅ Nota de {dados_qr['nome']} enviada ao Boletim Mestre!")
                            
                    except Exception as e: st.error(f"Erro na pág {idx_img+1}: {e}")

# --- ABA 3: FÁBRICA DE DISCIPLINAS (SOMENTE CADASTRO DE MODELOS) ---
with aba_caderneta:
    st.header("📝 Fábrica de Disciplinas (Modelos Pedagógicos)")
    
    with sqlite3.connect('banco_provas.db') as conn:
        conn.execute('''CREATE TABLE IF NOT EXISTS modelos_ensino 
                        (id INTEGER PRIMARY KEY, titulo_modelo TEXT UNIQUE, ementa TEXT, objetivos_gerais TEXT, 
                         competencias TEXT, egresso TEXT, conteudo_programatico TEXT, metodologia TEXT, 
                         recursos TEXT, avaliacao TEXT, aps TEXT, bib_basica TEXT, bib_complementar TEXT, outras_ref TEXT)''')
        
        conn.execute('''CREATE TABLE IF NOT EXISTS roteiro_mestre 
                        (id INTEGER PRIMARY KEY, titulo_modelo TEXT, num_aula INTEGER, tema TEXT, 
                         objetivos_aula TEXT, conteudo_detalhado TEXT, referencias_aula TEXT, materiais_link TEXT)''')
        
        # 💉 VACINA DE DADOS: Força a criação das colunas FAM se a tabela for antiga
        colunas_fam = ['competencias', 'egresso', 'conteudo_programatico', 'metodologia', 'recursos', 'avaliacao', 'aps', 'bib_basica', 'bib_complementar', 'outras_ref']
        for col in colunas_fam:
            try: conn.execute(f"ALTER TABLE modelos_ensino ADD COLUMN {col} TEXT")
            except: pass
            
        conn.commit()

        # ... (daqui para baixo continua normal: st.markdown("### 📚 Selecione ou Crie..."))

        st.markdown("### 📚 Selecione ou Crie uma Disciplina")
        disciplinas_salvas = pd.read_sql("SELECT DISTINCT titulo_modelo FROM modelos_ensino", conn)['titulo_modelo'].dropna().tolist()
        
        c_d1, c_d2 = st.columns([0.6, 0.4])
        disc_selecionada = c_d1.selectbox("Disciplinas no Banco:", ["-- Nova Disciplina --"] + disciplinas_salvas)
        nome_disc = c_d2.text_input("Nome da Disciplina (Ex: Termodinâmica I):", value="" if disc_selecionada == "-- Nova Disciplina --" else disc_selecionada)

        if not nome_disc:
            st.info("Digite um nome ou selecione uma disciplina para começar o planejamento.")
        else:
            st.write("---")
            t_ensino, t_aula = st.tabs(["📄 1. Plano de Ensino Oficial", "🧬 2. Roteiro de Aulas (Tópicos)"])

            with t_ensino:
                d_m = pd.read_sql(f"SELECT * FROM modelos_ensino WHERE titulo_modelo='{nome_disc}'", conn)
                def get_v(f): return d_m[f].iloc[0] if not d_m.empty else ""
                
                with st.form("form_plano_mestre"):
                    st.markdown(f"#### Estrutura Pedagógica: {nome_disc}")
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
                    aps_f = c6.text_area("🔬 Atividades Práticas (APS):", value=get_v('aps'))
                    st.markdown("---")
                    bib_b = st.text_area("📚 Referência Básica:", value=get_v('bib_basica'))
                    bib_c = st.text_area("📚 Referência Complementar:", value=get_v('bib_complementar'))
                    orf_f = st.text_area("📚 Outras Referências:", value=get_v('outras_ref'))
                    
                    if st.form_submit_button("💾 Salvar Plano de Ensino"):
                        conn.execute("DELETE FROM modelos_ensino WHERE titulo_modelo=?", (nome_disc,))
                        conn.execute('''INSERT INTO modelos_ensino (titulo_modelo, ementa, objetivos_gerais, competencias, egresso, 
                                        conteudo_programatico, metodologia, recursos, avaliacao, aps, bib_basica, bib_complementar, outras_ref) 
                                        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                                     (nome_disc, ementa, obj_g, comp, egr, prog, meto, recu, aval, aps_f, bib_b, bib_c, orf_f))
                        conn.commit(); st.success("Plano salvo com sucesso!"); st.rerun()

            with t_aula:
                st.markdown(f"#### 🧬 Temas e Roteiros: {nome_disc}")
                df_aulas = pd.read_sql(f"SELECT num_aula as Aula, tema as Tema FROM roteiro_mestre WHERE titulo_modelo='{nome_disc}' ORDER BY num_aula", conn)
                ed_aulas = st.data_editor(df_aulas, num_rows="dynamic", use_container_width=True, key="ed_roteiro_mestre")
                
                if st.button("💾 Atualizar Temas"):
                    for _, r in ed_aulas.iterrows():
                        check = conn.execute("SELECT id FROM roteiro_mestre WHERE titulo_modelo=? AND num_aula=?", (nome_disc, r['Aula'])).fetchone()
                        if check: conn.execute("UPDATE roteiro_mestre SET tema=? WHERE id=?", (r['Tema'], check[0]))
                        else: conn.execute("INSERT INTO roteiro_mestre (titulo_modelo, num_aula, tema) VALUES (?,?,?)", (nome_disc, r['Aula'], r['Tema']))
                    conn.commit(); st.rerun()

                st.write("---")
                a_detalhe = st.selectbox("Selecione a aula para detalhar o roteiro:", df_aulas['Aula'].tolist() if not df_aulas.empty else [])
                if a_detalhe:
                    d_a = pd.read_sql(f"SELECT * FROM roteiro_mestre WHERE titulo_modelo='{nome_disc}' AND num_aula={a_detalhe}", conn).iloc[0]
                    with st.form("f_detalhe_aula_mestre"):
                        st.info(f"📍 Detalhando Aula {a_detalhe}: {d_a['tema']}")
                        obj_a = st.text_area("🎯 Objetivos da Aula:", value=d_a['objetivos_aula'] or "")
                        cont_a = st.text_area("📝 Roteiro Detalhado / Conteúdo:", value=d_a['conteudo_detalhado'] or "", height=150)
                        ref_a = st.text_area("📚 Referências da Aula:", value=d_a['referencias_aula'] or "")
                        link_a = st.text_input("🔗 Link do Material:", value=d_a['materiais_link'] or "")
                        if st.form_submit_button("💾 Salvar Roteiro da Aula"):
                            conn.execute("UPDATE roteiro_mestre SET objetivos_aula=?, conteudo_detalhado=?, referencias_aula=?, materiais_link=? WHERE titulo_modelo=? AND num_aula=?", 
                                         (obj_a, cont_a, ref_a, link_a, nome_disc, a_detalhe))
                            conn.commit(); st.success("Roteiro salvo na biblioteca!")

# --- NOVO CONTEÚDO PARA A ABA DE HISTÓRICO (BOLETIM MESTRE DINÂMICO) ---
with aba_hist:
    st.subheader("📊 Histórico e Boletim Mestre")
    
    from datetime import timedelta
    import calendar
    import plotly.express as px # <-- Gráfico de Rosca do ClassDojo
    
    conn = sqlite3.connect('banco_provas.db')
    
    turmas_df = pd.read_sql("SELECT id, nome FROM turmas", conn)
    disciplinas_df = pd.read_sql("SELECT DISTINCT disciplina FROM resultados", conn)
    lista_disc = disciplinas_df['disciplina'].tolist() if not disciplinas_df.empty else ["Termodinâmica", "Mecânica dos Fluidos", "TCC 1"]
    
    if turmas_df.empty:
        st.info("Nenhuma turma cadastrada. Vá à aba 'Turmas' para criar uma e começar!")
    else:
        c_f1, c_f2, c_f3 = st.columns(3)
        turma_sel = c_f1.selectbox("📋 Turma:", turmas_df['nome'].tolist())
        disc_sel = c_f2.selectbox("📚 Disciplina:", lista_disc)
        
        id_t = turmas_df[turmas_df['nome'] == turma_sel]['id'].values[0]
        alunos_df = pd.read_sql(f"SELECT ra as RA, nome as Aluno FROM alunos WHERE turma_id = {id_t}", conn)
        
        if alunos_df.empty:
            st.warning(f"A turma '{turma_sel}' ainda não tem alunos cadastrados.")
        else:
            lista_alunos = ["Todos"] + alunos_df['Aluno'].tolist()
            aluno_sel = c_f3.selectbox("🎓 Aluno:", lista_alunos)
            
            st.write("---")
            st.markdown("### 📅 Relatórios de Frequência e Comportamento")
            
            # --- LÓGICA DE DATAS INSPIRADA NO CLASSDOJO ---
            hoje = datetime.today().date()
            meses_pt = {1: 'janeiro', 2: 'fevereiro', 3: 'março', 4: 'abril', 5: 'maio', 6: 'junho', 7: 'julho', 8: 'agosto', 9: 'setembro', 10: 'outubro', 11: 'novembro', 12: 'dezembro'}
            
            opcoes_data = [
                f"Este mês ({meses_pt[hoje.month]})", 
                "Hoje", 
                "Ontem", 
                "Esta semana", 
                "Semana passada", 
                "Todas as datas", 
                "Intervalo de datas personalizado"
            ]
            
            filtro_tempo = st.selectbox("Período de Análise:", opcoes_data)
            
            data_inicio, data_fim = None, None
            
            if filtro_tempo == "Hoje":
                data_inicio = data_fim = hoje
            elif filtro_tempo == "Ontem":
                data_inicio = data_fim = hoje - timedelta(days=1)
            elif filtro_tempo == "Esta semana":
                data_inicio = hoje - timedelta(days=hoje.weekday())
                data_fim = data_inicio + timedelta(days=6)
            elif filtro_tempo == "Semana passada":
                data_inicio = hoje - timedelta(days=hoje.weekday() + 7)
                data_fim = data_inicio + timedelta(days=6)
            elif filtro_tempo.startswith("Este mês"):
                data_inicio = hoje.replace(day=1)
                ultimo_dia = calendar.monthrange(hoje.year, hoje.month)[1]
                data_fim = hoje.replace(day=ultimo_dia)
            elif filtro_tempo == "Intervalo de datas personalizado":
                datas_selecionadas = st.date_input("Selecione o período (Início e Fim):", [hoje - timedelta(days=7), hoje])
                if len(datas_selecionadas) == 2:
                    data_inicio, data_fim = datas_selecionadas
                else:
                    data_inicio = data_fim = datas_selecionadas[0]
            
            def filtrar_por_tempo(df_alvo):
                if df_alvo.empty or filtro_tempo == "Todas as datas": 
                    return df_alvo
                df_alvo['data_dt'] = pd.to_datetime(df_alvo['data'], format='%d/%m/%Y', errors='coerce').dt.date
                if data_inicio and data_fim:
                    return df_alvo[(df_alvo['data_dt'] >= data_inicio) & (df_alvo['data_dt'] <= data_fim)]
                return df_alvo
            
            # --- 1. Provas Escaneadas ---
            try:
                df_provas_raw = pd.read_sql(f"SELECT aluno_ra as RA, avaliacao, nota FROM resultados WHERE disciplina = '{disc_sel}'", conn)
            except:
                df_provas_raw = pd.DataFrame()
                
            provas_cols = []
            if not df_provas_raw.empty:
                df_provas = df_provas_raw.pivot_table(index='RA', columns='avaliacao', values='nota', aggfunc='max').reset_index()
                provas_cols = [c for c in df_provas.columns if c != 'RA']
            else:
                df_provas = pd.DataFrame(columns=['RA'])
            
            # --- 2. Trabalhos Extras ---
            df_trab_raw = pd.read_sql(f"SELECT aluno_ra as RA, nome_atividade, nota FROM trabalhos_extras WHERE turma_id = {id_t} AND disciplina = '{disc_sel}'", conn)
            trab_cols = []
            if not df_trab_raw.empty:
                df_trab = df_trab_raw.pivot_table(index='RA', columns='nome_atividade', values='nota', aggfunc='max').reset_index()
                trab_cols = [c for c in df_trab.columns if c != 'RA']
            else:
                df_trab = pd.DataFrame(columns=['RA'])
                
            # --- BUSCA BRUTA: DIÁRIO E DOJO (Agora busca tudo perfeitamente!) ---
            df_diario_bruto = pd.read_sql(f"SELECT aluno_ra as RA, data, status FROM diario WHERE turma_id = {id_t}", conn)
            # 🟢 PUXA ABSOLUTAMENTE TUDO (Positivos, Negativos, Ocultos)
            df_dojo_bruto = pd.read_sql(f"SELECT aluno_ra as RA, data, pontos FROM logs_comportamento WHERE turma_id = {id_t} AND aluno_ra != 'TURMA_INTEIRA'", conn)
            
            df_diario_filtrado = filtrar_por_tempo(df_diario_bruto)
            df_dojo_filtrado = filtrar_por_tempo(df_dojo_bruto)
            
            # --- 3. Processamento do Diário ---
            if not df_diario_filtrado.empty:
                freq_pivot = df_diario_filtrado.pivot_table(index='RA', columns='status', aggfunc='size', fill_value=0).reset_index()
                for col in ['Presente', 'Atrasado', 'Ausente']:
                    if col not in freq_pivot.columns: freq_pivot[col] = 0
                freq_pivot['Total_Aulas'] = freq_pivot['Presente'] + freq_pivot['Atrasado'] + freq_pivot['Ausente']
                freq_pivot.rename(columns={'Presente': 'Presentes', 'Atrasado': 'Atrasos', 'Ausente': 'Faltas'}, inplace=True)
                df_diario = freq_pivot[['RA', 'Total_Aulas', 'Presentes', 'Atrasos', 'Faltas']]
            else:
                df_diario = pd.DataFrame(columns=['RA', 'Total_Aulas', 'Presentes', 'Atrasos', 'Faltas'])

            # --- 4. Processamento do Dojo com Divisão de Pontos ---
            if not df_dojo_filtrado.empty:
                df_dojo_filtrado['Positivos'] = df_dojo_filtrado['pontos'].apply(lambda x: x if x > 0 else 0)
                df_dojo_filtrado['Negativos'] = df_dojo_filtrado['pontos'].apply(lambda x: abs(x) if x < 0 else 0)
                df_dojo = df_dojo_filtrado.groupby('RA').agg({'pontos': 'sum', 'Positivos': 'sum', 'Negativos': 'sum'}).reset_index()
                df_dojo.rename(columns={'pontos': 'Saldo_Dojo'}, inplace=True)
            else:
                df_dojo = pd.DataFrame(columns=['RA', 'Saldo_Dojo', 'Positivos', 'Negativos'])
            
            # --- A GRANDE MESCLA ---
            df = alunos_df.copy()
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
            
            df_pesos_plan = pd.read_sql(f"SELECT nome_avaliacao, peso FROM planejamento_notas WHERE turma_id = {id_t} AND disciplina = '{disc_sel}'", conn)
            pesos = dict(zip(df_pesos_plan['nome_avaliacao'], df_pesos_plan['peso'])) if not df_pesos_plan.empty else {}
            
            nota_ponderada_soma = 0.0
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
            df['Nota_Final'] = (nota_ponderada_soma / soma_dos_pesos).clip(upper=10.0)
            df['Frequencia_%'] = df.apply(lambda x: (((x['Presentes'] + x['Atrasos']) / x['Total_Aulas']) * 100) if x['Total_Aulas'] > 0 else 100.0, axis=1)
            
            if aluno_sel != "Todos": df = df[df['Aluno'] == aluno_sel]
            
            # --- 📊 O GRÁFICO DE ROSCA DO CLASSDOJO ---
            st.write("---")
            col_chart, col_metrics = st.columns([0.4, 0.6])
            
            with col_chart:
                total_pos = df['Positivos'].sum()
                total_neg = df['Negativos'].sum()
                
                if total_pos + total_neg > 0:
                    fig = px.pie(
                        values=[total_pos, total_neg], 
                        names=['Positivos', 'A Melhorar'],
                        color=['Positivos', 'A Melhorar'],
                        color_discrete_map={'Positivos':'#2ecc71', 'A Melhorar':'#e74c3c'},
                        hole=0.65
                    )
                    # Coloca a % de positivos no meio da rosca
                    pct_pos = int((total_pos / (total_pos + total_neg)) * 100)
                    fig.update_layout(
                        margin=dict(t=10, b=10, l=10, r=10), height=200, showlegend=False, 
                        annotations=[dict(text=f"{pct_pos}%", x=0.5, y=0.5, font_size=30, showarrow=False)]
                    )
                    st.plotly_chart(fig, use_container_width=True)
                else:
                    st.info("Sem dados de comportamento no período.")
            
            with col_metrics:
                c1, c2 = st.columns(2)
                c1.metric("MÉDIA GERAL ACADÊMICA", f"{df['Nota_Final'].mean():.2f}")
                c2.metric(f"Saldo Dojo ({filtro_tempo.split(' (')[0]})", f"{df['Saldo_Dojo'].mean():.1f} ⭐")
                st.markdown(f"**Detalhe do Comportamento:** 🟢 {int(total_pos)} Positivos | 🔴 {int(total_neg)} A Melhorar")

            # --- TABELA FINAL ---
            st.write("---")
            st.markdown(f"### 📋 Relatório Final: {turma_sel} - {disc_sel}")
            
            colunas_mostrar = ['Aluno', 'RA']
            if provas_cols: colunas_mostrar.extend(provas_cols)
            if trab_cols: colunas_mostrar.extend(trab_cols)
            colunas_mostrar.extend(['Nota_Final', 'Frequencia_%', 'Presentes', 'Atrasos', 'Faltas', 'Positivos', 'Negativos', 'Saldo_Dojo'])
            
            df_tabela = df[colunas_mostrar].round(2).copy()
            df_tabela = df_tabela.rename(columns={
                "Nota_Final": "Média Acadêmica",
                "Frequencia_%": "Freq. %", 
                "Positivos": "🟢 Positivos",
                "Negativos": "🔴 A Melhorar",
                "Saldo_Dojo": "⭐ Saldo Dojo"
            })
            
            st.dataframe(df_tabela, width="stretch", hide_index=True)
            
            nome_arquivo = f"Relatorio_FAM_{turma_sel}_{disc_sel}_{filtro_tempo.split(' (')[0].replace(' ', '_')}.csv"
            csv = df_tabela.to_csv(index=False).encode('utf-8-sig')
            st.download_button("📥 Baixar Excel do Relatório", csv, nome_arquivo, "text/csv")
            
    conn.close()
# --- ABA 8: SALA DE AULA (DOJO + DIÁRIO DE CLASSE LIGADO AO CRONOGRAMA) ---
with aba_sala:
    st.subheader("🎮 Gestão de Aula e Diário Pedagógico")
    
    with sqlite3.connect('banco_provas.db') as conn:
        conn.execute('''CREATE TABLE IF NOT EXISTS diario_conteudo 
                        (id INTEGER PRIMARY KEY, turma_id INTEGER, disciplina TEXT, data TEXT, conteudo_real TEXT, observacao TEXT)''')
        
        turmas_df = pd.read_sql("SELECT id, nome FROM turmas", conn)
        
        if turmas_df.empty:
            st.info("Cadastre uma turma primeiro.")
        else:
            c_s1, c_s2 = st.columns([0.4, 0.6])
            t_aula_nome = c_s1.selectbox("Selecione a turma em aula:", turmas_df['nome'].tolist(), key="sel_sala")
            id_t_aula = turmas_df[turmas_df['nome'] == t_aula_nome]['id'].values[0]

            # 1. SENSORES E TIMER
            st.write("---")
            col_t1, col_t2 = st.columns([0.4, 0.6])
            with col_t1:
                st.markdown("### ⏱️ Cronômetro")
                t_min = st.number_input("Minutos para atividade:", 1, 120, 15)
                if st.button("🚀 Iniciar Atividade", use_container_width=True): st.toast(f"Cronômetro de {t_min} min iniciado!")
            with col_t2:
                st.markdown("### 🔊 Medidor de Ruído")
                st.components.v1.html("""<div style="text-align: center; background: #f0f2f6; padding: 10px; border-radius: 10px;"><canvas id="meter" width="300" height="40" style="border-radius: 5px;"></canvas><div id="status" style="font-family: sans-serif; font-size: 14px; font-weight: bold; margin-top: 5px;">Microfone Desligado</div></div><script>navigator.mediaDevices.getUserMedia({ audio: true }).then(stream => {const audioContext = new AudioContext();const analyser = audioContext.createAnalyser();const microphone = audioContext.createMediaStreamSource(stream);microphone.connect(analyser);analyser.fftSize = 256;const dataArray = new Uint8Array(analyser.frequencyBinCount);const canvas = document.getElementById('meter');const ctx = canvas.getContext('2d');const status = document.getElementById('status');function draw() {analyser.getByteFrequencyData(dataArray);let sum = 0;for(let i=0; i<dataArray.length; i++) sum += dataArray[i];let average = sum / dataArray.length;ctx.clearRect(0, 0, canvas.width, canvas.height);let color = "#2ecc71";if(average > 40) { color = "#f39c12"; status.innerText = "⚠️ Sala Agitada"; }if(average > 65) { color = "#e74c3c"; status.innerText = "🛑 Silêncio!"; }if(average <= 40) { status.innerText = "✅ Nível de Ruído OK"; }ctx.fillStyle = color;ctx.fillRect(0, 0, (average/100) * canvas.width, canvas.height);requestAnimationFrame(draw);}draw();}).catch(err => { document.getElementById('status').innerText = "Erro no Microfone"; });</script>""", height=100)

            st.write("---")
            # "Planejar Semestre" foi removido daqui pois agora você tem o Gerador de Calendário na Aba Turmas!
            modo_aula = st.radio("O que vamos fazer agora?", 
                                 ["⭐ Participação", "📅 Fazer Chamada", "🎲 Sortear Aluno", "👥 Grupos", "📝 Registrar Diário de Aula"], 
                                 horizontal=True)
            
            alunos_sala = pd.read_sql(f"""SELECT a.ra, a.nome, a.avatar_style 
                                          FROM alunos a JOIN matriculas_disciplina m ON a.id = m.aluno_id 
                                          WHERE m.turma_id={id_t_aula}""", conn)
            # Fallback caso ainda não tenha feito as matrículas específicas por disciplina
            if alunos_sala.empty: alunos_sala = pd.read_sql(f"SELECT ra, nome, avatar_style FROM alunos WHERE turma_id = {id_t_aula}", conn)

            # --- MODO: REGISTRAR AULA (DIÁRIO LIGADO AO CRONOGRAMA NOVO) ---
            if modo_aula == "📝 Registrar Diário de Aula":
                st.markdown("### 📖 Diário de Classe (Planejado x Realizado)")
                discs_turma = pd.read_sql(f"SELECT DISTINCT disciplina FROM cronograma_detalhado WHERE turma_id={id_t_aula}", conn)
                
                if discs_turma.empty:
                    st.warning("Nenhum cronograma gerado para esta turma. Gere-o na Aba 'Turmas'.")
                else:
                    disc_d = st.selectbox("📚 Disciplina:", discs_turma['disciplina'].tolist(), key="disc_d")
                    data_d = st.date_input("📅 Data da Aula:", datetime.today())
                    data_str = data_d.strftime("%d/%m/%Y")
                    
                    # 🟢 PUXA DO SEU CRONOGRAMA GERADO!
                    expectativa = pd.read_sql(f"SELECT tema, conteudo_detalhado FROM cronograma_detalhado WHERE turma_id={id_t_aula} AND disciplina='{disc_d}' AND data='{data_str}'", conn)
                    
                    if not expectativa.empty: 
                        st.info(f"🎯 **Sua Expectativa para Hoje (Tema):** {expectativa['tema'].iloc[0]}\n\n**Roteiro Planejado:** {expectativa['conteudo_detalhado'].iloc[0]}")
                        conteudo_inicial = expectativa['conteudo_detalhado'].iloc[0]
                    else:
                        st.warning("Não há aula planejada para esta data no cronograma.")
                        conteudo_inicial = ""
                        
                    conteudo_real = st.text_area("✍️ O que foi realmente dado em sala:", value=conteudo_inicial)
                    obs_d = st.text_area("💡 Observações Pedagógicas (Dificuldades da turma, lembretes):")
                    
                    if st.button("💾 Salvar Registro no Diário", type="primary", use_container_width=True):
                        c = conn.cursor()
                        c.execute("SELECT id FROM diario_conteudo WHERE turma_id=? AND disciplina=? AND data=?", (int(id_t_aula), disc_d, data_str))
                        if c.fetchone(): c.execute("UPDATE diario_conteudo SET conteudo_real=?, observacao=? WHERE turma_id=? AND disciplina=? AND data=?", (conteudo_real, obs_d, int(id_t_aula), disc_d, data_str))
                        else: c.execute("INSERT INTO diario_conteudo (turma_id, disciplina, data, conteudo_real, observacao) VALUES (?, ?, ?, ?, ?)", (int(id_t_aula), disc_d, data_str, conteudo_real, obs_d))
                        conn.commit(); st.success("✅ Diário atualizado com sucesso! (Visível no painel da Turma)")

            # --- MODO: ⭐ PARTICIPAÇÃO (MANTIDO INTACTO) ---
            elif modo_aula == "⭐ Participação":
                df_p = pd.read_sql(f"SELECT aluno_ra, SUM(CASE WHEN pontos > 0 THEN pontos ELSE 0 END) as pos, SUM(CASE WHEN pontos < 0 THEN pontos ELSE 0 END) as neg, SUM(pontos) as total FROM logs_comportamento WHERE turma_id = {id_t_aula} AND aluno_ra != 'TURMA_INTEIRA' GROUP BY aluno_ra", conn)
                df_t_pts = pd.read_sql(f"SELECT SUM(CASE WHEN pontos > 0 THEN pontos ELSE 0 END) as pos, SUM(CASE WHEN pontos < 0 THEN pontos ELSE 0 END) as neg FROM logs_comportamento WHERE turma_id = {id_t_aula} AND aluno_ra = 'TURMA_INTEIRA'", conn)
                t_pos = df_t_pts['pos'].fillna(0).iloc[0]; t_neg = abs(df_t_pts['neg'].fillna(0).iloc[0])
                alunos_dojo = pd.merge(alunos_sala, df_p, left_on='ra', right_on='aluno_ra', how='left').fillna(0)
                st.markdown("### 🏆 Top 3 da Turma")
                top3 = alunos_dojo.sort_values('total', ascending=False).head(3)
                if not top3.empty and top3['total'].sum() > 0:
                    ctop = st.columns(3); medalhas = ["🥇", "🥈", "🥉"]
                    for i, (_, row) in enumerate(top3.iterrows()): ctop[i].markdown(f"**{medalhas[i]} {row['nome'].split()[0]}** ({row['total']} pts)")
                cols = st.columns(6)
                with cols[0]:
                    with st.container(border=True):
                        st.markdown(f"<div style='text-align: center;'><div style='font-size: 45px; line-height: 60px;'>🌍</div><div style='font-size: 14px; font-weight: bold;'>Toda a Turma</div><div style='font-size: 14px;'>🟢 {int(t_pos)} | 🔴 {int(t_neg)}</div></div>", unsafe_allow_html=True)
                        with st.popover("Feedback", use_container_width=True):
                            if st.button("💡 Todos Focados (+1)", use_container_width=True): conn.execute("INSERT INTO logs_comportamento (aluno_ra, turma_id, data, pontos, comentario, tipo) VALUES (?, ?, ?, ?, ?, ?)", ('TURMA_INTEIRA', int(id_t_aula), datetime.now().strftime("%d/%m/%Y"), 1.0, "Turma Focada", "Bônus")); conn.commit(); st.rerun()
                            if st.button("🗣️ Barulho Coletivo (-1)", use_container_width=True): conn.execute("INSERT INTO logs_comportamento (aluno_ra, turma_id, data, pontos, comentario, tipo) VALUES (?, ?, ?, ?, ?, ?)", ('TURMA_INTEIRA', int(id_t_aula), datetime.now().strftime("%d/%m/%Y"), -1.0, "Barulho", "Atenção")); conn.commit(); st.rerun()
                for idx, row in alunos_dojo.iterrows():
                    with cols[(idx + 1) % 6]:
                        with st.container(border=True):
                            st.markdown(f"<div style='text-align: center;'><img src='https://api.dicebear.com/7.x/{row['avatar_style']}/svg?seed={row['ra']}' width='60'><div style='font-size: 14px; font-weight: bold; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;'>{row['nome'].split()[0]}</div><div style='font-size: 14px;'>🟢 {int(row['pos'])} | 🔴 {int(abs(row['neg']))}</div></div>", unsafe_allow_html=True)
                            with st.popover("Feedback", use_container_width=True):
                                if st.button("💡 Part. (+1)", key=f"p1_{row['ra']}"): conn.execute("INSERT INTO logs_comportamento (aluno_ra, turma_id, data, pontos, comentario, tipo) VALUES (?, ?, ?, ?, ?, ?)", (row['ra'], int(id_t_aula), datetime.now().strftime("%d/%m/%Y"), 1.0, "Participação", "Bônus")); conn.commit(); st.rerun()
                                if st.button("🗣️ Conversa (-1)", key=f"n1_{row['ra']}", use_container_width=True): conn.execute("INSERT INTO logs_comportamento (aluno_ra, turma_id, data, pontos, comentario, tipo) VALUES (?, ?, ?, ?, ?, ?)", (row['ra'], int(id_t_aula), datetime.now().strftime("%d/%m/%Y"), -1.0, "Conversa", "Atenção")); conn.commit(); st.rerun()
                                st.write("---"); pts_c = st.number_input("Pts", value=1.0, step=0.5, key=f"cpts_{row['ra']}")
                                msg_c = st.text_input("Motivo", key=f"cmsg_{row['ra']}")
                                if st.button("Salvar Motivo", key=f"cbtn_{row['ra']}", use_container_width=True):
                                    if msg_c: conn.execute("INSERT INTO logs_comportamento (aluno_ra, turma_id, data, pontos, comentario, tipo) VALUES (?, ?, ?, ?, ?, ?)", (row['ra'], int(id_t_aula), datetime.now().strftime("%d/%m/%Y"), pts_c, msg_c, "Bônus" if pts_c > 0 else "Atenção")); conn.commit(); st.rerun()

            # --- MODO: 📅 FAZER CHAMADA (MANTIDO INTACTO) ---
            elif modo_aula == "📅 Fazer Chamada":
                data_aula = st.date_input("Data da Aula:", datetime.today())
                data_str_c = data_aula.strftime("%d/%m/%Y")
                if "freq_mem" not in st.session_state or st.session_state.get("freq_t_id") != id_t_aula:
                    st.session_state.freq_mem = {row['ra']: "Presente" for _, row in alunos_sala.iterrows()}
                    st.session_state.freq_t_id = id_t_aula
                c_btn1, c_btn2, c_btn3 = st.columns([0.3, 0.3, 0.4])
                if c_btn1.button("🟢 Marcar Todos Presentes", use_container_width=True):
                    for ra in st.session_state.freq_mem: st.session_state.freq_mem[ra] = "Presente"; st.rerun()
                if c_btn2.button("🔴 Marcar Todos Ausentes", use_container_width=True):
                    for ra in st.session_state.freq_mem: st.session_state.freq_mem[ra] = "Ausente"; st.rerun()
                cols_f = st.columns(6)
                for idx, row in alunos_sala.iterrows():
                    ra = row['ra']; st_at = st.session_state.freq_mem[ra]
                    with cols_f[idx % 6]:
                        with st.container(border=True):
                            st.markdown(f"<div style='text-align: center;'><img src='https://api.dicebear.com/7.x/{row['avatar_style']}/svg?seed={ra}' width='50'><div style='font-size:14px; font-weight:bold;'>{row['nome'].split()[0]}</div></div>", unsafe_allow_html=True)
                            if st_at == "Presente":
                                if st.button("🟢", key=f"f_{ra}", use_container_width=True): st.session_state.freq_mem[ra] = "Ausente"; st.rerun()
                            elif st_at == "Ausente":
                                if st.button("🔴", key=f"f_{ra}", use_container_width=True): st.session_state.freq_mem[ra] = "Atrasado"; st.rerun()
                            else:
                                if st.button("🟡", key=f"f_{ra}", use_container_width=True): st.session_state.freq_mem[ra] = "Presente"; st.rerun()
                if st.button("💾 Salvar Frequência da Turma", type="primary", use_container_width=True):
                    c = conn.cursor(); c.execute("DELETE FROM diario WHERE turma_id = ? AND data = ?", (int(id_t_aula), data_str_c))
                    for ra, s in st.session_state.freq_mem.items():
                        c.execute('''INSERT INTO diario (turma_id, data, aluno_ra, presente, status, pontos_atividade, pontos_comportamento) VALUES (?, ?, ?, ?, ?, 0.0, 10.0)''', (int(id_t_aula), data_str_c, ra, (True if s in ["Presente", "Atrasado"] else False), s))
                    conn.commit(); st.success("Frequência salva!")

            # --- MODO: 🎲 SORTEAR ALUNO (MANTIDO INTACTO) ---
            elif modo_aula == "🎲 Sortear Aluno":
                if alunos_sala.empty: st.warning("Sem alunos.")
                else:
                    if 'aluno_sorteado' not in st.session_state or st.session_state.get('sorteio_turma_id') != id_t_aula:
                        st.session_state.aluno_sorteado = alunos_sala.sample(1).iloc[0]; st.session_state.sorteio_turma_id = id_t_aula
                    s = st.session_state.aluno_sorteado
                    n_ex = s['nome'].split()[0] + (f" {s['nome'].split()[-1][0]}." if len(s['nome'].split()) > 1 else "")
                    st.markdown(f"<div style='background-color: #1c9e5e; padding: 50px 20px; border-radius: 15px; text-align: center;'><h2 style='color: white;'>Sua seleção aleatória é:</h2><div style='background-color: white; padding: 40px; border-radius: 20px; display: inline-block; box-shadow: 0 8px 16px rgba(0,0,0,0.2); min-width: 400px;'><img src='https://api.dicebear.com/7.x/{s['avatar_style']}/svg?seed={s['ra']}' width='160'><h1 style='color: #2c3e50;'>{n_ex}</h1></div></div>", unsafe_allow_html=True)
                    if st.button("🔄 Sortear novamente", use_container_width=True): st.session_state.aluno_sorteado = alunos_sala.sample(1).iloc[0]; st.rerun()
                    st.write("---"); c_p1, c_p2, c_n1 = st.columns(3)
                    if c_p1.button("💡 Respondeu bem (+1)", use_container_width=True): conn.execute("INSERT INTO logs_comportamento (aluno_ra, turma_id, data, pontos, comentario, tipo) VALUES (?, ?, ?, ?, ?, ?)", (s['ra'], int(id_t_aula), datetime.now().strftime("%d/%m/%Y"), 1.0, "Sorteio - OK", "Bônus")); conn.commit(); st.toast("Salvo!"); st.rerun()
                    if c_p2.button("👍 Tentou (+0.5)", use_container_width=True): conn.execute("INSERT INTO logs_comportamento (aluno_ra, turma_id, data, pontos, comentario, tipo) VALUES (?, ?, ?, ?, ?, ?)", (s['ra'], int(id_t_aula), datetime.now().strftime("%d/%m/%Y"), 0.5, "Sorteio - Tentou", "Bônus")); conn.commit(); st.toast("Salvo!"); st.rerun()
                    if c_n1.button("🗣️ Conversa (-1)", use_container_width=True): conn.execute("INSERT INTO logs_comportamento (aluno_ra, turma_id, data, pontos, comentario, tipo) VALUES (?, ?, ?, ?, ?, ?)", (s['ra'], int(id_t_aula), datetime.now().strftime("%d/%m/%Y"), -1.0, "Sorteio - Ruim", "Atenção")); conn.commit(); st.toast("Salvo!"); st.rerun()

            # --- MODO: 👥 GRUPOS (MANTIDO INTACTO) ---
            elif modo_aula == "👥 Grupos":
                if 'grupos_sala' not in st.session_state or st.session_state.get('grupos_turma_id') != id_t_aula:
                    st.session_state.grupos_sala = []; st.session_state.grupos_turma_id = id_t_aula
                if not st.session_state.grupos_sala:
                    st.markdown("<div style='background-color: #d12229; padding: 20px; border-radius: 10px; text-align: center; color: white;'><h2>👥 Criador de Grupos</h2></div>", unsafe_allow_html=True)
                    tipo_g = st.radio("Como quer organizar?", ["Aleatório", "Manual"])
                    if tipo_g == "Aleatório":
                        c_t1, c_t2, c_t3, c_t4, c_t5 = st.columns(5)
                        def gerar_auto(tam):
                            shuf = alunos_sala.sample(frac=1).to_dict('records'); n_g = max(1, len(shuf) // tam)
                            gs = [{'nome': f'Grupo {i+1}', 'alunos': []} for i in range(n_g)]
                            for i, al in enumerate(shuf): gs[i % n_g]['alunos'].append(al)
                            st.session_state.grupos_sala = gs; st.rerun()
                        if c_t1.button("2"): gerar_auto(2)
                        if c_t2.button("3"): gerar_auto(3)
                        if c_t3.button("4"): gerar_auto(4)
                        if c_t4.button("5"): gerar_auto(5)
                        if c_t5.button("6"): gerar_auto(6)
                    else:
                        if 'al_disp' not in st.session_state: st.session_state.al_disp = alunos_sala.to_dict('records'); st.session_state.gs_tmp = []
                        sel = st.multiselect("Alunos:", options=[a['nome'] for a in st.session_state.al_disp])
                        if st.button("➕ Adicionar Grupo"):
                            al_g = [a for a in st.session_state.al_disp if a['nome'] in sel]
                            st.session_state.al_disp = [a for a in st.session_state.al_disp if a['nome'] not in sel]
                            st.session_state.gs_tmp.append({'nome': f"Grupo {len(st.session_state.gs_tmp)+1}", 'alunos': al_g}); st.rerun()
                        if st.button("🚀 Concluir"): st.session_state.grupos_sala = st.session_state.gs_tmp; st.rerun()
                else:
                    if st.button("🗑️ Desfazer Grupos"): st.session_state.pop('grupos_sala'); st.rerun()
                    cg = st.columns(3)
                    for i, g in enumerate(st.session_state.grupos_sala):
                        with cg[i % 3]:
                            with st.container(border=True):
                                st.markdown(f"<h4 style='text-align: center;'>{g['nome']}</h4>", unsafe_allow_html=True)
                                av_h = "<div style='display: flex; flex-wrap: wrap; justify-content: center; gap: 8px;'>"
                                for al in g['alunos']: av_h += f"<div style='text-align: center; width: 55px;'><img src='https://api.dicebear.com/7.x/{al['avatar_style']}/svg?seed={al['ra']}' width='45'><div style='font-size: 10px; font-weight: bold;'>{al['nome'].split()[0]}</div></div>"
                                st.markdown(av_h + "</div>", unsafe_allow_html=True)
                                with st.popover("⭐ Comportamento"):
                                    if st.button("💡 Equipe (+1)", key=f"gp1_{i}"):
                                        for al in g['alunos']: conn.execute("INSERT INTO logs_comportamento (aluno_ra, turma_id, data, pontos, comentario, tipo) VALUES (?, ?, ?, ?, ?, ?)", (al['ra'], int(id_t_aula), datetime.now().strftime("%d/%m/%Y"), 1.0, f"Ponto {g['nome']}", "Bônus"))
                                        conn.commit(); st.toast("Salvo!"); st.rerun()
                                with st.popover("📝 Avaliar Trabalho"):
                                    disc_g = st.selectbox("Disciplina:", ["Termodinâmica", "Mecânica dos Fluidos", "TCC 1"], key=f"dg_{i}")
                                    df_pl = pd.read_sql(f"SELECT nome_avaliacao FROM planejamento_notas WHERE turma_id={int(id_t_aula)} AND disciplina='{disc_g}'", conn)
                                    lista_p = df_pl['nome_avaliacao'].tolist() if not df_pl.empty else []
                                    nome_t = st.selectbox("Atividade:", lista_p, key=f"tn_{i}") if lista_p else st.text_input("Nome:", key=f"tn_{i}")
                                    nota_t = st.number_input("Nota:", 0.0, 10.0, 10.0, key=f"nt_{i}")
                                    if st.button("💾 Salvar Nota", key=f"sn_{i}", type="primary"):
                                        for al in g['alunos']:
                                            c = conn.cursor(); c.execute("SELECT id FROM trabalhos_extras WHERE turma_id=? AND disciplina=? AND nome_atividade=? AND aluno_ra=?", (int(id_t_aula), disc_g, nome_t, al['ra']))
                                            res = c.fetchone()
                                            if res: c.execute("UPDATE trabalhos_extras SET nota=? WHERE id=?", (nota_t, res[0]))
                                            else: c.execute("INSERT INTO trabalhos_extras (turma_id, disciplina, nome_atividade, aluno_ra, nota, data) VALUES (?, ?, ?, ?, ?, ?)", (int(id_t_aula), disc_g, nome_t, al['ra'], nota_t, datetime.now().strftime("%d/%m/%Y")))
                                        conn.commit(); st.toast("Notas salvas!"); st.rerun()