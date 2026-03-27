# planejamento.py
import streamlit as st
import sqlite3
import pandas as pd
from db import salvar_banco_no_cofre

def renderizar_aba_fabrica():
    with sqlite3.connect('banco_provas.db') as conn:
        st.markdown("**✅ Selecione ou Crie um Molde de Disciplina**")
        
        # Garante que a tabela exista antes de ler
        conn.execute('''CREATE TABLE IF NOT EXISTS modelos_ensino (
                        id INTEGER PRIMARY KEY AUTOINCREMENT, 
                        titulo_modelo TEXT UNIQUE, ementa TEXT, objetivos_gerais TEXT, 
                        competencias TEXT, egresso TEXT, conteudo_programatico TEXT, 
                        metodologia TEXT, recursos TEXT, avaliacao TEXT, aps TEXT, 
                        bib_basica TEXT, bib_complementar TEXT, outras_ref TEXT)''')
        
        disciplinas_salvas = pd.read_sql("SELECT DISTINCT titulo_modelo FROM modelos_ensino", conn)['titulo_modelo'].dropna().tolist()
        
        c_d1, c_d2 = st.columns([0.6, 0.4])
        disc_selecionada = c_d1.selectbox("Modelos Salvos:", ["-- Criar Novo Molde --"] + disciplinas_salvas, key="f_sel_mestre_vFinal")
        nome_disc = c_d2.text_input("Nome da Disciplina:", value="" if disc_selecionada == "-- Criar Novo Molde --" else disc_selecionada)

        if nome_disc:
            t_ensino, t_aula = st.tabs(["📄 1. Plano de Ensino Oficial", "🧭 2. Plano de Aulas"])

            with t_ensino:
                # Busca os dados do molde selecionado
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
                        conn.execute("""INSERT INTO modelos_ensino 
                            (titulo_modelo, ementa, objetivos_gerais, competencias, egresso, 
                            conteudo_programatico, metodologia, recursos, avaliacao, aps, 
                            bib_basica, bib_complementar, outras_ref) 
                            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""", 
                            (nome_disc, ementa, obj_g, comp, egr, prog, meto, recu, aval, aps_mestre, bib_b, bib_c, orf_f))
                        conn.commit()
                        salvar_banco_no_cofre()
                        st.success("Plano mestre salvo na nuvem!")
                        st.rerun()

            with t_aula:
                st.markdown("**🧭 Plano de aulas**")
                df_aulas = pd.read_sql(f"SELECT num_aula as Aula, tema as Tema FROM roteiro_mestre WHERE titulo_modelo='{nome_disc}' ORDER BY num_aula", conn)
                ed_aulas = st.data_editor(df_aulas, num_rows="dynamic", use_container_width=True, key=f"ed_roteiro_vFinal_{nome_disc}")
                
                if st.button("🆙 Atualizar Lista de Aulas"):
                    for _, r in ed_aulas.iterrows():
                        check = conn.execute("SELECT id FROM roteiro_mestre WHERE titulo_modelo=? AND num_aula=?", (nome_disc, r['Aula'])).fetchone()
                        if not check: 
                            conn.execute("INSERT INTO roteiro_mestre (titulo_modelo, num_aula, tema) VALUES (?,?,?)", (nome_disc, r['Aula'], r['Tema']))
                        else:
                            conn.execute("UPDATE roteiro_mestre SET tema=? WHERE titulo_modelo=? AND num_aula=?", (r['Tema'], nome_disc, r['Aula']))
                    conn.commit()
                    salvar_banco_no_cofre()
                    st.rerun()

                st.write("---")
                a_det = st.selectbox("Selecione a aula para detalhar o Roteiro:", df_aulas['Aula'].tolist() if not df_aulas.empty else [])
                if a_det:
                    d_a_res = pd.read_sql(f"SELECT * FROM roteiro_mestre WHERE titulo_modelo='{nome_disc}' AND num_aula={a_det}", conn)
                    if not d_a_res.empty:
                        d_a = d_a_res.iloc[0]
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
                                conn.execute("""UPDATE roteiro_mestre SET tema=?, tipo_aula=?, objetivos_aula=?, 
                                                conteudo_detalhado=?, metodologia=?, aps_aula=?, referencias_aula=?, 
                                                link_slides=?, link_overleaf=?, link_extras=?, atividades=?, 
                                                atividades_link=?, forum=?, forum_link=? 
                                                WHERE titulo_modelo=? AND num_aula=?""", 
                                             (tema_f, tipo_f, obj_f, cont_f, meto_f, aps_f, ref_f, l_slides, l_over, l_ext, 
                                              ativ_f, ativ_l, for_f, for_l, nome_disc, a_det))
                                conn.commit()
                                salvar_banco_no_cofre()
                                st.success("Molde global atualizado na nuvem!")
                                st.rerun()