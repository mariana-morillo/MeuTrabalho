import sqlite3

# ---------------------------------------------------------
# 1. FUNÇÃO QUE CRIA A ESTRUTURA (O ALICERCE)
# ---------------------------------------------------------
def criar_base_de_dados():
    conexao = sqlite3.connect('banco_provas.db')
    cursor = conexao.cursor()

    # Cria a tabela de questões (se ela ainda não existir)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS questoes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            disciplina TEXT NOT NULL,
            assunto TEXT NOT NULL,
            dificuldade TEXT NOT NULL,
            enunciado TEXT NOT NULL
        )
    ''')

    # Cria a tabela de alternativas (se ela ainda não existir)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS alternativas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            questao_id INTEGER NOT NULL,
            texto TEXT NOT NULL,
            correta BOOLEAN NOT NULL CHECK (correta IN (0, 1)),
            FOREIGN KEY (questao_id) REFERENCES questoes (id)
        )
    ''')

    conexao.commit()
    conexao.close()
    print("1. Estrutura do banco de dados pronta e verificada.")

# ---------------------------------------------------------
# 2. FUNÇÃO QUE INSERE OS DADOS (AS QUESTÕES)
# ---------------------------------------------------------
def inserir_questao(disciplina, assunto, dificuldade, enunciado, alternativas):
    conexao = sqlite3.connect('banco_provas.db')
    cursor = conexao.cursor()

    cursor.execute('''
        INSERT INTO questoes (disciplina, assunto, dificuldade, enunciado)
        VALUES (?, ?, ?, ?)
    ''', (disciplina, assunto, dificuldade, enunciado))
    
    questao_id = cursor.lastrowid

    for texto, correta in alternativas:
        cursor.execute('''
            INSERT INTO alternativas (questao_id, texto, correta)
            VALUES (?, ?, ?)
        ''', (questao_id, texto, correta))

    conexao.commit()
    conexao.close()
    print("2. Questão cadastrada com sucesso!")

# ---------------------------------------------------------
# 3. EXECUTANDO O PROGRAMA
# ---------------------------------------------------------

# Passo A: Prepara o banco de dados
criar_base_de_dados()

# Passo B: Define a questão de Termodinâmica com notação LaTeX
enunciado_teste = r"Qual das equações abaixo representa a Primeira Lei da Termodinâmica para um sistema fechado, sabendo que $Q$ é o calor transferido para o sistema, $W$ é o trabalho realizado pelo sistema e $\Delta U$ é a variação da energia interna?"

alternativas_teste = [
    (r"$\Delta U = Q - W$", True),  
    (r"$\Delta U = Q + W$", False),
    (r"$W = Q - \Delta U$", False),
    (r"$\Delta U = 0$", False),
    (r"$Q = W$", False)
]

# Passo C: Salva a questão no banco de dados
inserir_questao("Termodinâmica", "Primeira Lei", "Média", enunciado_teste, alternativas_teste)