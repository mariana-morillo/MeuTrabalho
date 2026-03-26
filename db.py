# db.py
import sqlite3
import pandas as pd
import os
import shutil
import random
from datetime import datetime
from difflib import SequenceMatcher
import streamlit as st
from supabase import create_client
# Substitua o bloco antigo por este:
URL = st.secrets.get("SUPABASE_URL")
KEY = st.secrets.get("SUPABASE_KEY")

if URL and KEY:
    try:
        supabase = create_client(str(URL), str(KEY)) # O str() garante que seja texto puro
    except:
        supabase = None
else:
    supabase = None
def get_db_name():
    """Descobre o nome do arquivo. Se for a Mariana logada, será banco_mariana.db"""
    if "usuario_logado" in st.session_state:
        return f"banco_{st.session_state.usuario_logado}.db"
    return "banco_provas.db"

def baixar_banco_do_cofre():
    """Traz o arquivo do Supabase para o Streamlit"""
    if not supabase: return
    nome_arquivo = get_db_name()
    try:
        res = supabase.storage.from_("bancos-sqlite").download(nome_arquivo)
        with open(nome_arquivo, "wb") as f:
            f.write(res)
    except Exception as e:
        # Se der erro aqui, a gente vai saber o motivo real
        st.error(f"Erro ao baixar banco do cofre: {e}")

def salvar_banco_no_cofre():
    """Leva o arquivo do Streamlit para o Supabase"""
    if not supabase: return
    nome_arquivo = get_db_name()
    if os.path.exists(nome_arquivo):
        try:
            with open(nome_arquivo, "rb") as f:
                supabase.storage.from_("bancos-sqlite").upload(
                    file=f, 
                    path=nome_arquivo, 
                    file_options={"x-upsert": "true"}
                )
        except Exception as e:
            st.error(f"Erro ao salvar no cofre: {e}")
# =========================================================================
# --- MANUTENÇÃO E BACKUP ---
# =========================================================================
def criar_backup_banco():
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    nome_backup = f"backup_questoes_{timestamp}.db"
    banco_atual = get_db_name()
    try: 
        if os.path.exists(banco_atual):
            shutil.copy2(banco_atual, nome_backup)
            return nome_backup
        else:
            return None
    except Exception as e: 
        st.error(f"Erro ao criar backup: {e}")
        return None

def backup_para_icloud():
    try:
        home = os.path.expanduser("~")
        pasta_icloud = os.path.join(home, "Library/Mobile Documents/com~apple~CloudDocs/Backup_GeradorProvas")
        if not os.path.exists(pasta_icloud): os.makedirs(pasta_icloud)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        destino = os.path.join(pasta_icloud, f"backup_provas_{timestamp}.db")
        banco_original = sqlite3.connect(get_db_name())
        banco_backup = sqlite3.connect(destino)
        with banco_backup: banco_original.backup(banco_backup)
        banco_backup.close()
        banco_original.close()
        return True
    except Exception as e:
        print(f"Erro no backup: {e}")
        return False

def obter_estatisticas_questoes(disciplina):
    conexao = sqlite3.connect(get_db_name())
    cursor = conexao.cursor()
    cursor.execute('SELECT tipo, COUNT(*) FROM questoes WHERE disciplina = ? GROUP BY tipo', (disciplina,))
    stats = cursor.fetchall()
    conexao.close()
    return {tipo: qtd for tipo, qtd in stats}

# =========================================================================
# --- BASE DE DADOS E QUERIES ---
# =========================================================================
def criar_base_de_dados():
    with sqlite3.connect(get_db_name()) as conn:
        cursor = conn.cursor()
        
        # 1. Tabelas de Provas e Questões
        cursor.execute('''CREATE TABLE IF NOT EXISTS questoes (id INTEGER PRIMARY KEY AUTOINCREMENT, disciplina TEXT, assunto TEXT, dificuldade TEXT, enunciado TEXT, imagem TEXT, pontos REAL, tipo TEXT, gabarito_discursivo TEXT, espaco_resposta TEXT, espaco_linhas INTEGER, gabarito_imagem TEXT)''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS alternativas (id INTEGER PRIMARY KEY AUTOINCREMENT, questao_id INTEGER, texto TEXT, correta BOOLEAN, imagem TEXT)''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS resultados (id INTEGER PRIMARY KEY AUTOINCREMENT, aluno_nome TEXT, aluno_ra TEXT, disciplina TEXT, versao TEXT, nota REAL, data_hora TEXT, avaliacao TEXT)''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS correcoes_detalhadas (id INTEGER PRIMARY KEY AUTOINCREMENT, aluno_ra TEXT, disciplina TEXT, prova_nome TEXT, questao_num INTEGER, status TEXT, feedback_ia TEXT)''')
        
        # 2. Tabelas de Gestão de Sala e Turmas
        cursor.execute('''CREATE TABLE IF NOT EXISTS turmas (id INTEGER PRIMARY KEY AUTOINCREMENT, nome TEXT UNIQUE, semestre TEXT DEFAULT '2026.1')''')
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
            
        try: conn.execute("ALTER TABLE alunos ADD COLUMN senha TEXT DEFAULT '123456'")
        except: pass
        conn.execute("UPDATE alunos SET senha = '123456' WHERE senha IS NULL")

        try: conn.execute("ALTER TABLE alunos ADD COLUMN avatar_opts TEXT DEFAULT ''")
        except: pass
        
        try: conn.execute("ALTER TABLE questoes ADD COLUMN uso_quest TEXT DEFAULT 'Prova Oficial'")
        except: pass

        # 5. Configurações Globais
        cursor.execute('''CREATE TABLE IF NOT EXISTS configuracoes (id INTEGER PRIMARY KEY CHECK (id = 1), instituicao TEXT, professor TEXT, departamento TEXT, curso TEXT, instrucoes TEXT)''')

        conn.commit()

def limpar_dados_teste():
    tabelas_para_limpar = ['resultados', 'correcoes_detalhadas', 'logs_comportamento', 'diario', 'atividades_sala']
    with sqlite3.connect(get_db_name()) as conn:
        cursor = conn.cursor()
        for tabela in tabelas_para_limpar:
            try: 
                cursor.execute(f"DELETE FROM {tabela}")
            except Exception as e:
                st.sidebar.error(f"Erro ao limpar {tabela}: {e}")
        conn.commit()
    return True

def inserir_questao(disc, ass, dif, enun, alts, pts, tipo, gab_disc=None, img=None, espaco="Linhas", espaco_linhas=4, gab_img=None, uso_quest="Prova Oficial"):
    # Adicionamos timeout=15 para o banco "esperar na fila" a outra conexão fechar
    with sqlite3.connect(get_db_name(), timeout=15, check_same_thread=False) as conexao:
        cursor = conexao.cursor()
        
        # Executamos o ALTER TABLE com um try/except específico para não quebrar a transação
        try: 
            cursor.execute("ALTER TABLE questoes ADD COLUMN uso_quest TEXT DEFAULT 'Prova Oficial'")
        except sqlite3.OperationalError: 
            pass # Ignora silenciosamente se a coluna já existir
        
        cursor.execute('''INSERT INTO questoes (disciplina, assunto, dificuldade, enunciado, imagem, pontos, tipo, gabarito_discursivo, espaco_resposta, espaco_linhas, gabarito_imagem, uso_quest) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''', (disc, ass, dif, enun, img, float(pts), tipo, gab_disc, espaco, int(espaco_linhas), gab_img, uso_quest))
        
        q_id = cursor.lastrowid
        
        if tipo in ["Múltipla Escolha", "Verdadeiro ou Falso"]:
            for txt, corr, img_alt in alts:
                # Garantimos que o booleano de correção vire 1 ou 0 para o banco não se confundir
                cursor.execute('INSERT INTO alternativas (questao_id, texto, correta, imagem) VALUES (?, ?, ?, ?)', (q_id, txt, int(corr), img_alt))
        
        conexao.commit()

def buscar_e_embaralhar_alternativas(q_id):
    with sqlite3.connect(get_db_name()) as conexao:
        cursor = conexao.cursor()
        cursor.execute('SELECT texto, correta, imagem FROM alternativas WHERE questao_id = ?', (q_id,))
        alts = cursor.fetchall()
    random.shuffle(alts)
    return alts

def buscar_alternativas_originais(q_id):
    with sqlite3.connect(get_db_name()) as conexao:
        cursor = conexao.cursor()
        cursor.execute('SELECT texto, correta, imagem FROM alternativas WHERE questao_id = ? ORDER BY id', (q_id,))
        alts = cursor.fetchall()
    return alts

def carregar_configuracoes():
    with sqlite3.connect(get_db_name()) as conexao:
        cursor = conexao.cursor()
        cursor.execute('SELECT instituicao, professor, departamento, curso, instrucoes FROM configuracoes WHERE id = 1')
        res = cursor.fetchone()
    return res

def salvar_configuracoes(inst, prof, dep, curso, instr):
    with sqlite3.connect(get_db_name()) as conexao:
        cursor = conexao.cursor()
        cursor.execute('''UPDATE configuracoes SET instituicao=?, professor=?, departamento=?, curso=?, instrucoes=? WHERE id=1''', (inst, prof, dep, curso, instr))
        conexao.commit()

def excluir_questao(q_id):
    # Mesma trava de segurança adicionada aqui
    with sqlite3.connect(get_db_name(), timeout=15, check_same_thread=False) as conexao:
        cursor = conexao.cursor()
        cursor.execute('DELETE FROM alternativas WHERE questao_id = ?', (q_id,))
        cursor.execute('DELETE FROM questoes WHERE id = ?', (q_id,))
        conexao.commit()

def obter_assuntos_da_disciplina(disciplina):
    with sqlite3.connect(get_db_name()) as conexao:
        cursor = conexao.cursor()
        cursor.execute('SELECT DISTINCT assunto FROM questoes WHERE disciplina = ? AND assunto IS NOT NULL AND assunto != "" ORDER BY assunto', (disciplina,))
        res = [r[0] for r in cursor.fetchall()]
    return ["Todos"] + res

def buscar_questoes_filtradas(disciplina, limite=None, assunto="Todos", dificuldade="Todos", tipo="Todos", sortear=False, excluir_ids=None, uso="Todos"):
    with sqlite3.connect(get_db_name()) as conexao:
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
    with sqlite3.connect(get_db_name()) as conexao:
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
    with sqlite3.connect(get_db_name()) as conn:
        conn.execute("DELETE FROM correcoes_detalhadas WHERE aluno_ra=? AND disciplina=? AND prova_nome=? AND questao_num=?", (ra, disc, prova, q_num))
        conn.execute('''INSERT INTO correcoes_detalhadas (aluno_ra, disciplina, prova_nome, questao_num, status, feedback_ia) 
                        VALUES (?, ?, ?, ?, ?, ?)''', (ra, disc, prova, q_num, status, feedback))
        conn.commit()

def detectar_duplicata(enunciado, disciplina):
    with sqlite3.connect(get_db_name()) as conexao:
        cursor = conexao.cursor()
        cursor.execute('SELECT id FROM questoes WHERE enunciado = ? AND disciplina = ?', (enunciado, disciplina))
        resultado = cursor.fetchone()
    return resultado[0] if resultado else None

def calcular_percentual_similaridade(a, b):
    return SequenceMatcher(None, a, b).ratio()

def buscar_questoes_proximas(enunciado_novo, disciplina, limite=0.8):
    with sqlite3.connect(get_db_name()) as conexao:
        cursor = conexao.cursor()
        cursor.execute('SELECT id, enunciado FROM questoes WHERE disciplina = ?', (disciplina,))
        questoes_existentes = cursor.fetchall()
    encontradas = []
    texto_novo = enunciado_novo.lower().strip()
    for q_id, q_texto in questoes_existentes:
        similaridade = calcular_percentual_similaridade(texto_novo, q_texto.lower().strip())
        if similaridade >= limite: encontradas.append({"id": q_id, "texto": q_texto, "percentual": similaridade * 100})
    return sorted(encontradas, key=lambda x: x['percentual'], reverse=True)