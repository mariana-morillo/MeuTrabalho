# db.py
import streamlit as st
import pandas as pd
from sqlalchemy import text
import random
from datetime import datetime
from difflib import SequenceMatcher

# =========================================================================
# --- CONEXÃO GLOBAL NA NUVEM (SUPABASE) ---
# =========================================================================
conn_central = st.connection("supabase", type="sql").engine.connect()

# =========================================================================
# --- FUNÇÕES "FANTASMAS" (Para não quebrar o seu app_provas.py) ---
# Como o Supabase faz tudo automático, não precisamos mais baixar/salvar cofre.
# =========================================================================
def get_db_name(): return ""
def baixar_banco_do_cofre(): pass
def salvar_banco_no_cofre(): pass
def criar_base_de_dados(): pass
def criar_backup_banco(): return None
def backup_para_icloud(): return False

# =========================================================================
# --- FUNÇÕES REAIS (TRADUZIDAS PARA POSTGRESQL) ---
# =========================================================================

def limpar_dados_teste():
    tabelas_para_limpar = ['resultados', 'correcoes_detalhadas', 'logs_comportamento', 'diario', 'atividades_sala']
    with conn_central:
        for tabela in tabelas_para_limpar:
            try: 
                conn_central.execute(text(f"DELETE FROM {tabela}"))
            except Exception as e:
                st.sidebar.error(f"Erro ao limpar {tabela}: {e}")
        conn_central.commit()
    return True

def inserir_questao(disc, ass, dif, enun, alts, pts, tipo, gab_disc=None, img=None, espaco="Linhas", espaco_linhas=4, gab_img=None, uso_quest="Prova Oficial"):
    with conn_central:
        # Insere a questão e já pega o ID gerado pelo banco (RETURNING id)
        sql_q = """
            INSERT INTO questoes (disciplina, assunto, dificuldade, enunciado, imagem, pontos, tipo, gabarito_discursivo, espaco_resposta, espaco_linhas, gabarito_imagem, uso_quest) 
            VALUES (:d, :a, :dif, :e, :img, :p, :t, :gd, :er, :el, :gimg, :u) 
            RETURNING id
        """
        params_q = {
            "d": disc, "a": ass, "dif": dif, "e": enun, "img": img, "p": float(pts), 
            "t": tipo, "gd": gab_disc, "er": espaco, "el": int(espaco_linhas), "gimg": gab_img, "u": uso_quest
        }
        
        resultado = conn_central.execute(text(sql_q), params_q)
        q_id = resultado.scalar() # Pega o ID retornado
        
        if tipo in ["Múltipla Escolha", "Verdadeiro ou Falso"]:
            for txt, corr, img_alt in alts:
                sql_a = "INSERT INTO alternativas (questao_id, texto, correta, imagem) VALUES (:qid, :t, :c, :img)"
                conn_central.execute(text(sql_a), {"qid": q_id, "t": txt, "c": int(corr), "img": img_alt})
        
        conn_central.commit()

def buscar_e_embaralhar_alternativas(q_id):
    alts = conn_central.execute(text('SELECT texto, correta, imagem FROM alternativas WHERE questao_id = :id'), {"id": q_id}).fetchall()
    alts_lista = list(alts) # Converte para lista para poder embaralhar
    random.shuffle(alts_lista)
    return alts_lista

def buscar_alternativas_originais(q_id):
    return conn_central.execute(text('SELECT texto, correta, imagem FROM alternativas WHERE questao_id = :id ORDER BY id'), {"id": q_id}).fetchall()

def carregar_configuracoes():
    try:
        res = conn_central.execute(text('SELECT instituicao, professor, departamento, curso, instrucoes, titulo, logo FROM configuracoes WHERE id = 1')).fetchone()
        return res
    except:
        return None

def salvar_configuracoes(inst, prof, dep, curso, instr, titulo, logo):
    with conn_central:
        # Apaga a config antiga (se houver) e insere a nova para não dar erro de ID duplicado
        conn_central.execute(text("DELETE FROM configuracoes WHERE id = 1"))
        sql = """
            INSERT INTO configuracoes (id, instituicao, professor, departamento, curso, instrucoes, titulo, logo) 
            VALUES (1, :i, :p, :d, :c, :ins, :t, :l)
        """
        conn_central.execute(text(sql), {"i": inst, "p": prof, "d": dep, "c": curso, "ins": instr, "t": titulo, "l": logo})
        conn_central.commit()

def excluir_questao(q_id):
    with conn_central:
        conn_central.execute(text('DELETE FROM alternativas WHERE questao_id = :id'), {"id": q_id})
        conn_central.execute(text('DELETE FROM questoes WHERE id = :id'), {"id": q_id})
        conn_central.commit()

def obter_assuntos_da_disciplina(disciplina):
    res = conn_central.execute(text("SELECT DISTINCT assunto FROM questoes WHERE disciplina = :d AND assunto IS NOT NULL AND assunto != '' ORDER BY assunto"), {"d": disciplina}).fetchall()
    return ["Todos"] + [r[0] for r in res]

def buscar_questoes_filtradas(disciplina, limite=None, assunto="Todos", dificuldade="Todos", tipo="Todos", sortear=False, excluir_ids=None, uso="Todos"):
    query = "SELECT id, enunciado, imagem, pontos, tipo, gabarito_discursivo, espaco_resposta, espaco_linhas, dificuldade, assunto, gabarito_imagem, uso_quest FROM questoes WHERE disciplina = :d"
    params = {"d": disciplina}
    
    if assunto != "Todos": 
        query += " AND assunto = :a"
        params["a"] = assunto
    if dificuldade != "Todos": 
        query += " AND dificuldade = :dif"
        params["dif"] = dificuldade
    if tipo != "Todos": 
        query += " AND tipo = :t"
        params["t"] = tipo
    if uso != "Todos": 
        query += " AND uso_quest = :u"
        params["u"] = uso
    
    if excluir_ids:
        # Monta a string segura para a lista de IDs a excluir (ex: :id_0, :id_1, :id_2)
        placeholders = ', '.join([f":id_{i}" for i in range(len(excluir_ids))])
        query += f" AND id NOT IN ({placeholders})"
        for i, val in enumerate(excluir_ids): 
            params[f"id_{i}"] = val
            
    if sortear: 
        query += " ORDER BY RANDOM()"
    else: 
        query += " ORDER BY id DESC"
        
    if limite: 
        query += " LIMIT :l"
        params["l"] = limite
        
    return conn_central.execute(text(query), params).fetchall()

def salvar_resultado_prova(nome, ra, disc, versao, nota, avaliacao="P1"):
    with conn_central:
        agora = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
        registro_existente = conn_central.execute(text('SELECT id FROM resultados WHERE aluno_ra = :ra AND disciplina = :d AND avaliacao = :a'), {"ra": ra, "d": disc, "a": avaliacao}).fetchone()
        
        if registro_existente:
            conn_central.execute(text('UPDATE resultados SET nota = :n, data_hora = :dh, versao = :v WHERE id = :id'), {"n": nota, "dh": agora, "v": versao, "id": registro_existente[0]})
        else:
            conn_central.execute(text('INSERT INTO resultados (aluno_nome, aluno_ra, disciplina, versao, nota, data_hora, avaliacao) VALUES (:n, :ra, :d, :v, :nota, :dh, :a)'), {"n": nome, "ra": ra, "d": disc, "v": versao, "nota": nota, "dh": agora, "a": avaliacao})
        
        conn_central.commit()

def salvar_feedback_detalhado(ra, disc, prova, q_num, status, feedback):
    with conn_central:
        conn_central.execute(text("DELETE FROM correcoes_detalhadas WHERE aluno_ra=:ra AND disciplina=:d AND prova_nome=:p AND questao_num=:q"), {"ra": ra, "d": disc, "p": prova, "q": q_num})
        conn_central.execute(text("""INSERT INTO correcoes_detalhadas (aluno_ra, disciplina, prova_nome, questao_num, status, feedback_ia) 
                                     VALUES (:ra, :d, :p, :q, :s, :f)"""), {"ra": ra, "d": disc, "p": prova, "q": q_num, "s": status, "f": feedback})
        conn_central.commit()

def detectar_duplicata(enunciado, disciplina):
    res = conn_central.execute(text('SELECT id FROM questoes WHERE enunciado = :e AND disciplina = :d'), {"e": enunciado, "d": disciplina}).fetchone()
    return res[0] if res else None

def calcular_percentual_similaridade(a, b):
    return SequenceMatcher(None, a, b).ratio()

def buscar_questoes_proximas(enunciado_novo, disciplina, limite=0.8):
    questoes_existentes = conn_central.execute(text('SELECT id, enunciado FROM questoes WHERE disciplina = :d'), {"d": disciplina}).fetchall()
    encontradas = []
    texto_novo = enunciado_novo.lower().strip()
    
    for q_id, q_texto in questoes_existentes:
        similaridade = calcular_percentual_similaridade(texto_novo, q_texto.lower().strip())
        if similaridade >= limite: 
            encontradas.append({"id": q_id, "texto": q_texto, "percentual": similaridade * 100})
            
    return sorted(encontradas, key=lambda x: x['percentual'], reverse=True)
