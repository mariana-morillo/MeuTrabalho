# correcao.py
import streamlit as st
import sqlite3
import pandas as pd
import json
import cv2
import numpy as np
import os
# Força o Python do Mac a enxergar a pasta secreta do Homebrew (Zbar)
os.environ["DYLD_LIBRARY_PATH"] = "/opt/homebrew/lib:/usr/local/lib"

# Importa a função de gravar o feedback que já extraímos para o db.py!
from db import salvar_feedback_detalhado, salvar_banco_no_cofre, get_db_name

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

def renderizar_aba_correcao():
    with sqlite3.connect(get_db_name()) as conn:
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
            if lista_ativ_plan: prova_final_nome = c_sel3.selectbox("📑 Selecione a Prova (Se for Oficial):", lista_ativ_plan, key="p_corr_plan")
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
                                        dados_qr = {"ra": ra_m, "nome": nome_m, "gab": {}, "v": "A", "d": d_corr_sel, "tp": "Oficial"}
                                    else:
                                        st.error("Formato de aluno inválido no banco.")
                                        continue
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

                        idx_ancora = 0 
                        
                        for idx_q, (q_num, gab_val) in enumerate(sorted(gab.items(), key=lambda x: int(x[0]))):
                            
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

                            if tipo_q == "DISC": continue 

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
                            
                            idx_ancora += 1 

                        tipo_lido = dados_qr.get("tp", "Oficial")
                        
                        st.image(cv2.addWeighted(overlay, 0.4, img, 0.6, 0), caption=f"🎯 Processada: {dados_qr['nome']}")
                        df_check = pd.DataFrame(resumos)
                        st.table(df_check.set_index("Q"))

                        c_n1, c_n2 = st.columns(2)
                        n_disc = c_n1.number_input(f"Nota Questões Abertas ({dados_qr['nome']}):", 0.0, 10.0, 0.0, 0.5, key=f"nd_{idx_img}")
                        nota_final_lote = acertos_acumulados + n_disc
                        
                        if "Treino" in tipo_lido:
                            c_n2.markdown(f"### 🏋️ TREINO: `{nota_final_lote:.2f}` pts")
                            st.info("Como este documento foi gerado como 'Treino', a nota **não** irá para a Planilha Oficial. O aluno receberá apenas o feedback!")
                        else:
                            c_n2.markdown(f"### 🏆 TOTAL: `{nota_final_lote:.2f}`")

                        if st.button(f"💾 Confirmar e Salvar: {dados_qr['nome']}", key=f"sv_{idx_img}", type="primary"):
                            
                            # 1. SALVA A NOTA NA PLANILHA OFICIAL (Apenas se não for Treino)
                            # 1. SALVA A NOTA NA PLANILHA OFICIAL (Apenas se não for Treino)
                            if "Treino" not in tipo_lido:
                                conn.execute("DELETE FROM notas_flexiveis WHERE turma_id=? AND disciplina=? AND matricula=? AND avaliacao=?", (int(id_t_corr), d_corr_sel, dados_qr['ra'], prova_final_nome))
                                conn.execute("INSERT INTO notas_flexiveis (turma_id, disciplina, matricula, avaliacao, nota) VALUES (?,?,?,?,?)", (int(id_t_corr), d_corr_sel, dados_qr['ra'], prova_final_nome, float(nota_final_lote)))
                                conn.commit()
                                salvar_banco_no_cofre()
                                st.toast("✅ Nota Oficial enviada para a Planilha/Boletim!")
                            else:
                                st.toast("🏋️ Atividade de Treino: Apenas o feedback foi gravado.")
                            
                            # 2. SALVA O FEEDBACK NO PORTAL DO ALUNO
                            for r in resumos:
                                status_q = "Correta" if r['OK'] == "✅" else "Incorreta"
                                msg = f"Parabéns! Você acertou a questão {r['Q']}. Gabarito: {r['Gabarito']}." if status_q == "Correta" else f"Na questão {r['Q']}, a resposta lida foi {r['Lido']}, mas o esperado era {r['Gabarito']}."
                                salvar_feedback_detalhado(dados_qr['ra'], d_corr_sel, prova_final_nome, r['Q'], status_q, msg)
                            
                            st.success(f"Tudo pronto para o aluno {dados_qr['nome']}!")
                            st.rerun() 
                            
                    except Exception as e: st.error(f"Erro na pág {idx_img+1}: {e}")