import sqlite3
import re
import os

def importar_questoes_do_latex(caminho_arquivo, disciplina):
    if not os.path.exists(caminho_arquivo):
        print("Arquivo não encontrado!")
        return

    with open(caminho_arquivo, 'r', encoding='utf-8') as f:
        conteudo = f.read()

    # Regex para encontrar o bloco de cada questão (do \item até o próximo \item ou fim)
    # Ajustado para o padrão comum de enumerate do LaTeX
    padrao_questao = re.findall(r'\\item\s+(.*?)(?=\\item|\s*\\end{enumerate})', conteudo, re.DOTALL)

    conexao = sqlite3.connect('banco_provas.db')
    cursor = conexao.cursor()

    for bloco in padrao_questao:
        # Separa o enunciado das alternativas (procura o ambiente enumerate interno)
        partes = re.split(r'\\begin{enumerate}.*?\\item', bloco, flags=re.DOTALL)
        
        enunciado = partes[0].strip()
        
        # Tenta encontrar as alternativas se existirem
        alternativas_brutas = re.findall(r'\\item\s+(.*?)(?=\\item|\s*\\end{enumerate})', bloco, re.DOTALL)
        
        # Limpa o enunciado de comandos LaTeX que sobraram do split
        enunciado = re.sub(r'\\begin{enumerate}.*', '', enunciado, flags=re.DOTALL).strip()

        if enunciado:
            # Insere a questão (Assunto e Dificuldade ficam como 'Importado' para você editar depois)
            cursor.execute('''
                INSERT INTO questoes (disciplina, assunto, dificuldade, enunciado, pontos)
                VALUES (?, ?, ?, ?, ?)
            ''', (disciplina, "Importado", "Média", enunciado, 1.0))
            
            questao_id = cursor.lastrowid

            # Insere as alternativas (A primeira será marcada como correta por padrão para você revisar)
            for i, alt in enumerate(alternativas_brutas):
                correta = 1 if i == 0 else 0
                cursor.execute('''
                    INSERT INTO alternativas (questao_id, texto, correta)
                    VALUES (?, ?, ?)
                ''', (questao_id, alt.strip(), correta))

    conexao.commit()
    conexao.close()
    print(f"Sucesso! Questões de {disciplina} importadas.")

# --- EXECUTAR IMPORTAÇÃO ---
# Coloque o nome do seu arquivo .tex antigo aqui
# importar_questoes_do_latex("minha_lista_antiga.tex", "Termodinâmica")