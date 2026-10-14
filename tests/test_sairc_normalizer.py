from core.sairc_normalizer import detect_field, detect_fields, normalize_ai_output, normalize_result_value, numeric_expression_kind

def test_quantitative_comparator_is_preserved_and_blocked():
    value, number, _ = normalize_result_value('POTASIO', '<0,05')
    assert value == '<0.05'
    assert number == 0.05
    normalized = normalize_ai_output({'documento_identidad': '12345678', 'resultados': [{'analisis': 'Potasio', 'resultado': '<0,05'}]}, ruta_relativa='12345678_REA_laboratorio.pdf')
    assert normalized['sairc']['POTASIO'] == '<0.05'
    assert normalized['sairc']['POTASIO_estado'] == 'REVISAR'
    assert normalized['sairc']['POTASIO_motivo'] == 'resultado_cuantitativo_con_comparador'
    assert normalized['cabecera']['puede_cargarse_sairc'] == 'NO'

def test_interval_is_detected_but_negative_number_is_exact():
    assert numeric_expression_kind('10-20') == 'intervalo'
    assert numeric_expression_kind('-1.2') is None
    assert normalize_result_value('POTASIO', '4,5')[:2] == ('4.5', 4.5)

def test_historical_ocr_aliases_are_recognized():
    aliases = {'DETECCION DE ANTIGENO DE HEPATITIS B (HBS-AG)': 'HBSAG', 'ANTICUERPOS HIV1 Y HIV2': 'HIV', 'HEPATITIS B - HBC.(ANTICORE) TOTAL': 'ANTI_HBC', 'ANTI - H. I. V. 1/2': 'HIV', 'DOSAJE DE FOSFATA, ALCALINA': 'FOSFATASA_ALCALINA', 'HBS-AB': 'ANTI_HBS', 'REACCION V. D. R. L': 'VDRL', 'HEPATITIS BS ANTIC. CUANT.': 'ANTI_HBS', 'ANTI-HCB TOTAL': 'ANTI_HBC', 'HEPATITIS B AG. SUPERFICIE': 'HBSAG', 'HEPATITIS B (HBCA B)': 'ANTI_HBC', 'UREA1': 'UREA_PRE', 'UREA2': 'UREA_POST', 'FOSFORA': 'FOSFORO'}
    assert {label: detect_field(label) for label in aliases} == aliases

def test_detect_fields_finds_collapsed_electrolytes_and_keeps_urea_post_specific():
    assert detect_fields('ELECTROLITOS (NA, CL, K) SODIO POTASIO CLORO') == ['SODIO', 'POTASIO', 'CLORO']
    assert detect_fields('UREA POST') == ['UREA_POST']

def test_combined_urea_result_is_split_and_pru_is_calculated():
    normalized = normalize_ai_output({'documento_identidad': '12345678', 'resultados': [{'analisis': 'UREA', 'resultado': '168 (PRE) / 37 (POST)', 'unidades': 'mg/dL'}]}, ruta_relativa='12345678_REA_laboratorio.pdf')
    assert normalized['sairc']['UREA_PRE'] == '168'
    assert normalized['sairc']['UREA_POST'] == '37'
    assert normalized['sairc']['PRU'] == 77.98
    urea_rows = [row for row in normalized['resultados_normalizados'] if row['campo_sairc'].startswith('UREA_')]
    assert {row['resultado_original'] for row in urea_rows} == {'168 (PRE) / 37 (POST)'}

def test_combined_urea_accepts_pos_abbreviation():
    normalized = normalize_ai_output({'resultados': [{'analisis': 'UREA', 'resultado': '150 (PRE) / 33 (POS)'}]})
    assert normalized['sairc']['UREA_PRE'] == '150'
    assert normalized['sairc']['UREA_POST'] == '33'

def test_explicit_pru_is_preserved_when_urea_pair_is_unavailable():
    normalized = normalize_ai_output({'resultados': [{'analisis': 'PRU', 'resultado': '72.5', 'unidades': '%'}]})
    assert normalized['sairc']['PRU'] == '72.5'
    assert normalized['sairc']['PRU_estado'] == 'OK'

def test_thousands_formats_are_parsed_without_losing_magnitude():
    assert normalize_result_value('FERRITINA', '1,032.00')[:2] == ('1032', 1032.0)
    assert normalize_result_value('FERRITINA', '1 190')[:2] == ('1190', 1190.0)
    assert normalize_result_value('PTH', '1.445,0')[:2] == ('1445', 1445.0)

def test_hepatitis_and_transaminase_aliases_do_not_cross_map():
    assert detect_field('Anti-HBsAg') == 'ANTI_HBS'
    assert detect_field('Total Anti - HB Core') == 'ANTI_HBC'
    assert detect_field('PRUEBA DE SIFILIS; ANTICUERPO NO TREPONÉMICO; CUALTATIVO') == 'VDRL'

def test_anti_hbs_accepts_a_quantitative_titer_without_forcing_text_interpretation():
    normalized = normalize_ai_output({'resultados': [{'analisis': 'Anti-HBsAg', 'resultado': '16.85', 'unidades': 'mUI/mL'}]})
    assert normalized['sairc']['ANTI_HBS'] == '16.85'
    assert normalized['sairc']['ANTI_HBS_estado'] == 'OK'

def test_transferrin_saturation_label_is_not_collapsed_into_plain_transferrin():
    normalized = normalize_ai_output({'resultados': [{'analisis': 'TRANSFERRINA % DE SATURACION', 'resultado': '24', 'unidades': '%'}, {'analisis': 'TRANSFERRINA', 'resultado': '182', 'unidades': 'mg/dL'}]})
    assert normalized['sairc']['SAT_TRANSFERRINA'] == '24'
    assert normalized['sairc']['TRANSFERRINA'] == '182'
    assert len(normalized['resultados_normalizados']) == 2
