import os
import random
import pandas as pd
import music21 as m21
import numpy as np
import glob
import tkinter as tk
from tkinter import filedialog, simpledialog, messagebox, ttk
from tkinter.scrolledtext import ScrolledText
import json
import re
from collections import defaultdict, Counter, OrderedDict

class InstrumentSelection:
    """
    Classe auxiliar para armazenar as informações de seleção de um instrumento,
    incluindo a quantidade (dobras) e suas configurações específicas.
    """
    def __init__(self, name, count=0, config=None):
        self.name = name  # Nome do instrumento
        self.count = count  # Número de instâncias (0 = não selecionado)
        self.config = config or {}  # Configurações específicas (opcional)
    
    def __repr__(self):
        return f"InstrumentSelection({self.name}, count={self.count})"

def set_active_instruments_with_doubles(self_composer, instrument_selections):
    """
    Define os instrumentos ativos com suporte a múltiplas instâncias (dobras).
    
    Parâmetros:
    - instrument_selections: dicionário {nome_instrumento: quantidade}
    
    Retorna:
    - True se bem sucedido, False caso contrário
    """
    valid_instruments = []
    
    # CORREÇÃO: Melhor tratamento para adicionar instrumentos duplicados
    for inst_name, count in instrument_selections.items():
        if inst_name in self_composer.instruments and count > 0:
            # Tratamento especial para o piano (não adiciona sufixos)
            if inst_name in ["piano_direita", "piano_esquerda"]:
                valid_instruments.append(inst_name)
                continue
                
            # Para cada instrumento, adiciona o número especificado de instâncias
            for i in range(count):
                # Se for mais de uma instância, adiciona um sufixo numérico
                if count > 1:
                    inst_id = f"{inst_name}_{i+1}"  # Ex: "flauta_1", "flauta_2"
                else:
                    inst_id = inst_name
                
                valid_instruments.append(inst_id)
    
    if not valid_instruments:
        print("Nenhum instrumento válido selecionado. Mantendo configuração atual.")
        return False
    
    # CORREÇÃO: Não remover duplicatas de instrumentos que não são piano
    # Apenas garantir que não há duplicatas no caso do piano
    unique_instruments = []
    piano_right_added = False
    piano_left_added = False
    
    for inst in valid_instruments:
        if inst == "piano_direita" and not piano_right_added:
            piano_right_added = True
            unique_instruments.append(inst)
        elif inst == "piano_esquerda" and not piano_left_added:
            piano_left_added = True
            unique_instruments.append(inst)
        else:
            # Para outros instrumentos, adiciona normalmente (permitindo duplicatas)
            unique_instruments.append(inst)
    
    # Define os instrumentos ativos
    self_composer.active_instruments = unique_instruments
    
    # Cria um resumo para log
    instrument_counts = {}
    for inst in unique_instruments:
        # Extrai o nome base do instrumento (remove sufixos numéricos)
        if "_" in inst:
            parts = inst.split('_')
            if parts[0] == "piano":
                base_name = "piano"
            else:
                base_name = parts[0]
        else:
            base_name = inst
        
        instrument_counts[base_name] = instrument_counts.get(base_name, 0) + 1
    
    summary = []
    for inst, count in instrument_counts.items():
        if count > 1:
            summary.append(f"{inst.title()} ({count})")
        else:
            summary.append(inst.title())
    
    print(f"Instrumentos ativos definidos: {', '.join(summary)}")
    return True

# Correção para o método get_instrument_for_part
def get_instrument_for_part(self, inst_id):
    """
    Obtém o objeto de instrumento para uma parte específica, incluindo
    suporte para múltiplas instâncias do mesmo instrumento.
    
    Parâmetros:
    - inst_id: identificador do instrumento (pode incluir sufixo numérico)
    
    Retorna:
    - Objeto de instrumento music21 e suas configurações
    """
    # CORREÇÃO: Melhor tratamento para extrair o nome base do instrumento
    if "_" in inst_id:
        parts = inst_id.split('_')
        # Verifica se é um formato tipo 'flauta_1' ou 'piano_direita_1'
        if parts[0] == "piano" and len(parts) > 1:
            if parts[1] in ["direita", "esquerda"]:
                base_name = f"piano_{parts[1]}"
            else:
                # Formato alternativo como 'piano_1_direita'
                hand = "direita" if parts[-1] == "direita" else "esquerda" 
                base_name = f"piano_{hand}"
        else:
            base_name = parts[0]
    else:
        base_name = inst_id
    
    if base_name not in self.instruments:
        print(f"Instrumento base '{base_name}' não encontrado (de '{inst_id}')")
        return None
    
    # Obtém a definição do instrumento base
    instrument_obj, min_pitch, max_pitch, transposition = self.instruments[base_name]
    
    # Se for uma instância numerada, cria uma cópia do instrumento com nome ajustado
    if '_' in inst_id and not base_name.startswith("piano_"):
        import copy
        instrument_copy = copy.deepcopy(instrument_obj)
        
        # Extrai o número da sufixo
        suffix = None
        parts = inst_id.split('_')
        if len(parts) > 1 and parts[1].isdigit():
            suffix = parts[1]
        
        # Ajusta o nome da parte para indicar a numeração
        if suffix and hasattr(instrument_copy, 'partName') and instrument_copy.partName:
            instrument_copy.partName = f"{instrument_copy.partName} {suffix}"
        
        return (instrument_copy, min_pitch, max_pitch, transposition)
    
    return (instrument_obj, min_pitch, max_pitch, transposition)

def generate_multi_instrument_composition_with_doubles(self, title="Composição Orquestral", style="balanced", instruments=None, exact_length=None):
    """
    Versão modificada que suporta múltiplas instâncias do mesmo instrumento
    e respeita estritamente o comprimento desejado.
    """
    import music21 as m21
    import random
    
    if not self.rhythm_patterns or not self.pitch_patterns:
        print("Dados de análise insuficientes. Execute o carregamento dos dados primeiro.")
        return None
    
    # Define o estilo de composição
    self.current_style = style
    style_params = self.composition_templates.get(style, self.composition_templates["balanced"])
    
    # Define quais instrumentos usar
    if instruments is None:
        instruments_to_use = self.active_instruments
    else:
        instruments_to_use = [inst for inst in instruments if inst.split('_')[0] in self.instruments]
        if not instruments_to_use:
            instruments_to_use = ["piano_direita", "piano_esquerda"]
    
    print(f"Instrumentos a serem usados: {instruments_to_use}")
    
    # Cria uma nova partitura
    score = m21.stream.Score()
    
    # Adiciona metadados
    score.insert(0, m21.metadata.Metadata())
    score.metadata.title = title
    score.metadata.composer = "GrammarComposer AI"
    
    # Identifica instrumentos de piano para tratamento especial
    piano_parts = {part: idx for idx, part in enumerate(instruments_to_use) 
                  if part.startswith("piano_")}
    
    # Cria um dicionário para agrupar partes por instrumento (para o caso do piano)
    instrument_parts = {}
    
    # MELHORIA: Gerar a sequência de fórmulas de compasso ANTES de processar qualquer instrumento
    # e usar a mesma sequência para todos os instrumentos
    time_sig_sequence = None
    if self.use_variable_time_signatures:
        # Estima o número de compassos necessários (aproximadamente)
        # Ajustado para ser mais preciso baseado no comprimento e compasso atual
        beat_value = 1.0  # Padrão para 4/4
        try:
            numerator, denominator = map(int, self.time_signature.split('/'))
            beat_value = 4.0 / denominator
        except:
            pass
            
        events_per_measure = numerator * (4 / denominator)
        estimate_measures = int((exact_length if exact_length else self.composition_length) / events_per_measure) + 2
        
        print(f"Gerando sequência de {estimate_measures} fórmulas de compasso")
        time_sig_sequence = self.generate_time_signature_sequence(estimate_measures)
        print(f"Sequência de fórmulas gerada: {time_sig_sequence[:5]}...")
        
        # Armazena a sequência para uso em todos os instrumentos
        self._current_time_sig_sequence = time_sig_sequence
    
    # Gera partes para cada instrumento
    for inst_id in instruments_to_use:
        # Pula o piano por enquanto (tratado separadamente depois)
        if inst_id.startswith("piano_"):
            continue
            
        # Obtém configurações do instrumento
        instrument_info = self.get_instrument_for_part(inst_id)
        if not instrument_info:
            print(f"Instrumento não encontrado: {inst_id}")
            continue
            
        instrument_obj, min_pitch, max_pitch, transposition = instrument_info
        
        # Aplica ajustes específicos do estilo
        min_pitch = max(min_pitch, style_params["min_pitch"])
        max_pitch = min(max_pitch, style_params["max_pitch"])
        
        # Cria uma parte para o instrumento
        part = m21.stream.Part()
        
        # Adiciona o objeto de instrumento para obter o timbre correto no MIDI
        part.append(instrument_obj)
        
        # Adiciona a clave apropriada
        base_name = inst_id.split('_')[0]
        if base_name in self.instrument_clefs:
            part.append(self.instrument_clefs[base_name])
        
        # Adiciona informações de compasso e tonalidade
        ts = m21.meter.TimeSignature(self.time_signature)
        part.append(ts)
        
        ks = m21.key.Key(self.key_signature)
        part.append(ks)
        
        # Adiciona informação de andamento (apenas para o primeiro instrumento)
        if inst_id == instruments_to_use[0] or len(instrument_parts) == 0:
            mm = m21.tempo.MetronomeMark(number=self.tempo)
            part.append(mm)
        
        # MODIFICAÇÃO: Usar comprimento exato ou com variações pequenas
        if exact_length is not None:
            # Usar comprimento exato quando solicitado
            adjusted_length = exact_length
            adjusted_complexity = style_params["rhythm_complexity"]
        else:
            # Para manter a variação entre instrumentos, podemos modificar a complexidade rítmica
            # ligeiramente para cada instrumento, mas manter o comprimento constante
            complexity_variation = random.uniform(-0.1, 0.1)
            # MODIFICAÇÃO: Remover variação de comprimento para maior consistência
            adjusted_length = self.composition_length
            adjusted_complexity = max(0.1, min(0.9, style_params["rhythm_complexity"] + complexity_variation))
        
        # Gera a sequência rítmica para este instrumento
        rhythm_sequence = self._generate_rhythm_sequence(adjusted_length, adjusted_complexity)
        
        # Gera a sequência melódica para este instrumento, respeitando sua tessitura
        pitch_sequence = self._generate_pitch_sequence(adjusted_length, min_pitch, max_pitch)
        
        # Aplica transposição se necessário (para instrumentos transpositores)
        if transposition != 0:
            pitch_sequence = [p + transposition if p > 0 else p for p in pitch_sequence]
        
        # CORREÇÃO: Passa a sequência de fórmulas de compasso para garantir que todos os instrumentos
        # usem exatamente as mesmas mudanças de compasso
        self._create_score_from_sequences(part, rhythm_sequence, pitch_sequence, time_sig_sequence)
        
        # Armazena a parte no dicionário
        instrument_parts[inst_id] = part
        print(f"Parte criada para instrumento: {inst_id}")
    
    # Trata o piano como caso especial (duas mãos em um sistema)
    # Podemos ter múltiplos pianos (Piano 1, Piano 2, etc.)
    piano_groups = {}
    for piano_part, _ in sorted(piano_parts.items(), key=lambda x: x[1]):
        piano_base = piano_part.split('_')[0]  # "piano" sem o sufixo numérico
        piano_component = piano_part.split('_')[1]  # "direita" ou "esquerda" ou numérico
        
        # Agrupa as partes de piano
        group_key = "piano"  # Piano principal por padrão
        
        # Verifica se há um número depois de "piano_direita" ou "piano_esquerda"
        if "_" in piano_component:
            # Formato esperado: piano_direita_1, piano_esquerda_2, etc.
            hand, number = piano_component.split('_', 1)
            group_key = f"piano_{number}"
        elif piano_component.isdigit() or (len(piano_component) > 1 and piano_component[0].isdigit()):
            # Formato alternativo: piano_1_direita, piano_2_esquerda
            group_key = f"piano_{piano_component}"
        
        if group_key not in piano_groups:
            piano_groups[group_key] = []
        
        piano_groups[group_key].append(piano_part)
    
    # Debug para verificar os grupos de piano identificados
    print(f"Grupos de piano identificados: {piano_groups}")
    
    # Processa cada grupo de piano
    for group_key, group_parts in piano_groups.items():
        # Verifica se temos partes para as duas mãos
        has_right = any("direita" in p for p in group_parts)
        has_left = any("esquerda" in p for p in group_parts)
        
        # Só cria um grupo de piano se tivermos pelo menos uma mão
        if has_right or has_left:
            # Cria um grupo de staff para o piano
            piano_staff = m21.stream.PartStaff()
            
            # Define o nome do grupo de piano (Piano, Piano 2, etc.)
            piano_name = "Piano"
            if group_key != "piano":
                try:
                    num = group_key.split('_')[1]
                    piano_name = f"Piano {num}"
                except:
                    pass
            
            # Cria o instrumento de piano com nome correto
            piano_inst = m21.instrument.Piano()
            piano_inst.partName = piano_name
            piano_staff.insert(0, piano_inst)
            
            # Processa as partes para mão direita e esquerda
            for hand in ["direita", "esquerda"]:
                matching_parts = [p for p in group_parts if hand in p]
                
                if matching_parts:
                    # Use a primeira parte encontrada para esta mão
                    hand_part_id = matching_parts[0]
                    
                    # Gera a parte se ainda não existir
                    if hand_part_id not in instrument_parts:
                        # Obtém configurações do instrumento
                        base_name = f"piano_{hand}"
                        if base_name in self.instruments:
                            instrument_obj, min_pitch, max_pitch, transposition = self.instruments[base_name]
                            
                            # Aplica ajustes específicos do estilo
                            min_pitch = max(min_pitch, style_params["min_pitch"])
                            max_pitch = min(max_pitch, style_params["max_pitch"])
                            
                            # Cria uma parte para a mão
                            part = m21.stream.Part()
                            
                            # Adiciona o objeto de instrumento
                            part.append(instrument_obj)
                            
                            # Adiciona a clave apropriada
                            if base_name in self.instrument_clefs:
                                part.append(self.instrument_clefs[base_name])
                            
                            # Adiciona informações de compasso e tonalidade
                            ts = m21.meter.TimeSignature(self.time_signature)
                            part.append(ts)
                            
                            ks = m21.key.Key(self.key_signature)
                            part.append(ks)
                            
                            # MODIFICAÇÃO: Usar comprimento exato ou com variações pequenas
                            if exact_length is not None:
                                # Usar comprimento exato quando solicitado
                                adjusted_length = exact_length
                                adjusted_complexity = style_params["rhythm_complexity"]
                            else:
                                # CORREÇÃO: Remover variação de comprimento para maior consistência
                                complexity_variation = random.uniform(-0.1, 0.1)
                                adjusted_length = self.composition_length
                                adjusted_complexity = max(0.1, min(0.9, style_params["rhythm_complexity"] + complexity_variation))
                            
                            rhythm_sequence = self._generate_rhythm_sequence(adjusted_length, adjusted_complexity)
                            pitch_sequence = self._generate_pitch_sequence(adjusted_length, min_pitch, max_pitch)
                            
                            # CORREÇÃO: Passa a sequência de fórmulas de compasso para que o piano
                            # use exatamente as mesmas mudanças de compasso que os outros instrumentos
                            self._create_score_from_sequences(part, rhythm_sequence, pitch_sequence, time_sig_sequence)
                            
                            # Armazena a parte
                            instrument_parts[hand_part_id] = part
                            print(f"Parte de piano criada: {hand_part_id}")
                    
                    # Adiciona a parte ao grupo de piano
                    if hand_part_id in instrument_parts:
                        piano_staff.insert(0, instrument_parts[hand_part_id])
                        
                        # Remove a parte do dicionário para não ser adicionada duas vezes
                        del instrument_parts[hand_part_id]
            
            # Adiciona o grupo de piano à partitura
            score.insert(0, piano_staff)
            print(f"Grupo de piano adicionado: {piano_name}")
    
    # Adiciona as demais partes à partitura
    for inst_id, part in instrument_parts.items():
        score.insert(0, part)
        print(f"Parte adicionada à partitura final: {inst_id}")
    
    return score

# Modificação para o método generate_composition_with_exact_measures
def generate_composition_with_exact_measures(self, measure_count, title="Composição Gerada", style="balanced"):
    """
    Gera uma composição com um número específico de compassos.
    
    Parâmetros:
    - measure_count: número exato de compassos a serem gerados
    - title: título da composição
    - style: estilo de composição (melodic, rhythmic, balanced, experimental)
    
    Retorna:
    - Uma partitura music21 com o número específico de compassos
    """
    if not self.rhythm_patterns or not self.pitch_patterns:
        print("Dados de análise insuficientes. Execute o carregamento dos dados primeiro.")
        return None
    
    # Define o estilo de composição
    self.current_style = style
    style_params = self.composition_templates.get(style, self.composition_templates["balanced"])
    
    # Estima o número de eventos necessários para gerar o número de compassos desejado
    # Essa estimativa depende da fórmula de compasso atual
    time_sig = self.time_signature
    events_per_measure = 4  # Valor padrão para 4/4
    
    # Ajusta com base na fórmula de compasso
    if time_sig:
        try:
            num, denom = map(int, time_sig.split('/'))
            if denom == 4:
                events_per_measure = num
            elif denom == 8:
                events_per_measure = num / 2
            else:
                events_per_measure = num
        except:
            pass  # Usa o valor padrão se houver erro
    
    # Calcula o número aproximado de eventos necessários
    estimated_events = measure_count * events_per_measure
    original_length = self.composition_length
    self.composition_length = int(estimated_events)
    
    # Gera a composição com comprimento exato (sem variações aleatórias)
    if hasattr(self, 'generate_multi_instrument_composition_with_doubles'):
        # Usa o método melhorado com parâmetro de comprimento exato
        score = self.generate_multi_instrument_composition_with_doubles(
            title=title, 
            style=style,
            exact_length=int(estimated_events)  # Passa o valor exato para evitar variações
        )
    else:
        # Fallback para o método antigo
        score = self.generate_multi_instrument_composition(title=title, style=style)
    
    if score:
        # Verifica o número de compassos obtido
        first_part = score.parts[0]
        if isinstance(first_part, m21.stream.PartStaff):
            first_part = first_part.getElementsByClass('Part')[0]
        
        current_measures = len(first_part.getElementsByClass('Measure'))
        
        # Se o número de compassos não corresponde, tenta ajustar
        if current_measures != measure_count:
            attempts = 1
            max_attempts = 3
            
            while current_measures != measure_count and attempts < max_attempts:
                print(f"Ajustando composição: tentativa {attempts} ({current_measures} compassos vs. {measure_count} desejados)")
                
                # Calcula o fator de ajuste baseado na diferença
                adjustment_factor = measure_count / current_measures
                new_length = int(self.composition_length * adjustment_factor)
                
                # Aplica o novo comprimento
                self.composition_length = max(8, new_length)
                
                # Regenera a composição com comprimento exato
                if hasattr(self, 'generate_multi_instrument_composition_with_doubles'):
                    score = self.generate_multi_instrument_composition_with_doubles(
                        title=title, 
                        style=style,
                        exact_length=int(self.composition_length)  # Usa comprimento exato
                    )
                else:
                    score = self.generate_multi_instrument_composition(title=title, style=style)
                
                # Verifica novamente
                first_part = score.parts[0]
                if isinstance(first_part, m21.stream.PartStaff):
                    first_part = first_part.getElementsByClass('Part')[0]
                
                current_measures = len(first_part.getElementsByClass('Measure'))
                attempts += 1
            
            print(f"Resultado final: {current_measures} compassos (desejados: {measure_count})")
    
    # Restaura o comprimento original
    self.composition_length = original_length
    
    return score

# -------------------------------------------------
# Adicionar classe para mapear velocities para dinâmicas musicais
# -------------------------------------------------
class VelocityProcessor:
    """
    Classe para processar valores de velocity MIDI e mapear para dinâmicas musicais.
    """
    def __init__(self):
        # Intervalos de velocity MIDI para cada dinâmica musical
        self.dynamic_ranges = {
            "ppp": (1, 16),    # pianississimo
            "pp":  (16, 33),   # pianissimo
            "p":   (33, 49),   # piano
            "mp":  (49, 65),   # mezzo-piano
            "mf":  (65, 81),   # mezzo-forte
            "f":   (81, 97),   # forte
            "ff":  (97, 113),  # fortissimo
            "fff": (113, 128)  # fortississimo
        }
        
        # Valores médios de velocity para cada dinâmica (para conversão inversa)
        self.dynamic_values = {
            "ppp": 8,
            "pp": 24,
            "p": 40,
            "mp": 56,
            "mf": 72,
            "f": 88,
            "ff": 104,
            "fff": 120,
            "Silêncio": 0  # Para pausas
        }
    
    def get_dynamic_name(self, velocity):
        """
        Mapeia um valor de velocity MIDI (0-127) para uma marcação de dinâmica musical tradicional.
        """
        if velocity == 0:
            return "Silêncio"
            
        for name, (min_val, max_val) in self.dynamic_ranges.items():
            if min_val <= velocity < max_val:
                return name
                
        # Caso de valor extremo
        return "fff"
    
    def get_velocity_from_dynamic(self, dynamic_name):
        """
        Converte uma marcação de dinâmica musical para um valor de velocity MIDI.
        """
        return self.dynamic_values.get(dynamic_name, 64)  # 64 (mf) como valor padrão

class GenerativeGrammarComposer:
    """
    Classe para gerar composições musicais baseadas em gramáticas generativas
    usando os resultados das análises de padrões rítmicos e melódicos.
    """

    def add_orchestral_instruments(self):
        """
        Adiciona definições de instrumentos orquestrais ao compositor.
        """
        # Cada instrumento com partName explicitamente definido
        flute = m21.instrument.Flute()
        flute.partName = "Flauta"
        
        oboe = m21.instrument.Oboe()
        oboe.partName = "Oboé"
        
        clarinet = m21.instrument.Clarinet()
        clarinet.partName = "Clarinete"
        
        bassoon = m21.instrument.Bassoon()
        bassoon.partName = "Fagote"
        
        horn = m21.instrument.Horn()
        horn.partName = "Trompa"
        
        trumpet = m21.instrument.Trumpet()
        trumpet.partName = "Trompete"
        
        trombone = m21.instrument.Trombone()
        trombone.partName = "Trombone"
        
        tuba = m21.instrument.Tuba()
        tuba.partName = "Tuba"
        
        violin = m21.instrument.Violin()
        violin.partName = "Violino"
        
        viola = m21.instrument.Viola()
        viola.partName = "Viola"
        
        cello = m21.instrument.Violoncello()
        cello.partName = "Violoncelo"
        
        bass = m21.instrument.Contrabass()
        bass.partName = "Contrabaixo"
        
        piano = m21.instrument.Piano()
        piano.partName = "Piano"        

        # Dicionário com informações de instrumentos
        # Formato: nome: (classe music21, tessitura_min, tessitura_max, transposicao)
        self.instruments = OrderedDict({
                "flauta": (flute, 60, 96, 0),
                "oboé": (oboe, 58, 91, 0),
                "clarinete": (clarinet, 50, 89, -2),
                "fagote": (bassoon, 34, 72, 0),
                "trompa": (horn, 41, 77, -7),
                "trompete": (trumpet, 55, 82, -2),
                "trombone": (trombone, 36, 74, 0),
                "tuba": (tuba, 28, 58, 0),
                "violino": (violin, 55, 103, 0),
                "viola": (viola, 48, 91, 0),
                "violoncelo": (cello, 36, 79, 0),
                "contrabaixo": (bass, 28, 67, -12),
                "piano_direita": (piano, 60, 108, 0),
                "piano_esquerda": (piano, 21, 59, 0),
            })
        
        # Adicionar configurações de claves para os instrumentos
        self.instrument_clefs = {
            "flauta": m21.clef.TrebleClef(),
            "oboé": m21.clef.TrebleClef(),
            "clarinete": m21.clef.TrebleClef(),
            "fagote": m21.clef.BassClef(),
            "trompa": m21.clef.TrebleClef(),
            "trompete": m21.clef.TrebleClef(),
            "trombone": m21.clef.BassClef(),
            "tuba": m21.clef.BassClef(),
            "violino": m21.clef.TrebleClef(),
            "viola": m21.clef.AltoClef(),
            "violoncelo": m21.clef.BassClef(),
            "contrabaixo": m21.clef.BassClef(),
            "piano_direita": m21.clef.TrebleClef(),
            "piano_esquerda": m21.clef.BassClef(),
        }

    def _init_instruments(self):
        """
        Adiciona a definição de instrumentos disponíveis ao compositor.
        """
        # Adicionar instrumentos orquestrais
        self.add_orchestral_instruments()
        
        # Lista de instrumentos ativos na composição atual
        self.active_instruments = []
        
        # Por padrão, tornar apenas piano ativo
        self.active_instruments = ["piano_direita", "piano_esquerda"]

    def __init__(self):
        self.analysis_folder = None
        self.rhythm_patterns = {}  # Padrões rítmicos organizados por tipo e frequência
        self.pitch_patterns = {}   # Padrões melódicos organizados por tipo e frequência
        self.velocity_patterns = {}  # NOVO: Padrões de dinâmica organizados por tipo e frequência
        self.sequitur_rhythm_rules = {}  # Regras Sequitur para ritmos
        self.sequitur_pitch_rules = {}   # Regras Sequitur para melodias
        self.sequitur_velocity_rules = {}  # NOVO: Regras Sequitur para dinâmicas
        self.siatec_rhythm_patterns = {} # Padrões SIATEC para ritmos
        self.siatec_pitch_patterns = {}  # Padrões SIATEC para melodias
        self.siatec_velocity_patterns = {}  # NOVO: Padrões SIATEC para dinâmicas
        
        # Instancia o processador de velocities
        self.velocity_processor = VelocityProcessor()
        
        # Parâmetros de composição
        self.composition_length = 32  # Número de eventos musicais
        self.time_signature = '4/4'   # Fórmula de compasso padrão
        self.key_signature = 'C'      # Tonalidade padrão
        self.tempo = 90               # Andamento em BPM
        self.dynamics_mode = "pattern"  # NOVO: Modo de dinâmicas (pattern, fixed, or contour)
        self.fixed_dynamic = "mf"       # NOVO: Dinâmica fixa (quando no modo "fixed")
        
        # Configurações para fórmulas de compasso variáveis
        self.use_variable_time_signatures = False
        self.variable_time_signatures = ['4/4', '3/4', '3/8', '2/4', '6/8', '5/4', '5/8', '7/8']
        self.time_sig_change_probability = 0.2  # 20% de chance de mudar a cada compasso

        self.output_folder = None
        
        # Configurações avançadas
        self.use_ngrams = True
        self.use_sequitur = True
        self.use_siatec = True
        self.ngram_weight = 0.4       # Peso para padrões N-gram
        self.sequitur_weight = 0.3    # Peso para regras Sequitur
        self.siatec_weight = 0.3      # Peso para padrões SIATEC
        
        # Templates para tipos diferentes de composição (atualizados com dinâmicas)
        self.composition_templates = {
            "melodic": {
                "min_pitch": 60, 
                "max_pitch": 84, 
                "rhythm_complexity": 0.5,
                "min_dynamic": "mp",   # NOVO
                "max_dynamic": "f"     # NOVO
            },
            "rhythmic": {
                "min_pitch": 60, 
                "max_pitch": 72, 
                "rhythm_complexity": 0.8,
                "min_dynamic": "p",    # NOVO
                "max_dynamic": "ff"    # NOVO
            },
            "balanced": {
                "min_pitch": 55, 
                "max_pitch": 79, 
                "rhythm_complexity": 0.6,
                "min_dynamic": "mp",   # NOVO
                "max_dynamic": "mf"    # NOVO
            },
            "experimental": {
                "min_pitch": 48, 
                "max_pitch": 96, 
                "rhythm_complexity": 0.9,
                "min_dynamic": "pp",   # NOVO
                "max_dynamic": "fff"   # NOVO
            }
        }
        
        # Estilo de composição atual
        self.current_style = "balanced"
        
        # Inicialização dos instrumentos
        self._init_instruments()
        
    def generate_multi_instrument_composition(self, title="Composição Orquestral", style="balanced", instruments=None):
        """
        Gera uma nova composição com múltiplos instrumentos com base nos padrões analisados.
        
        Parâmetros:
        - title: título da composição
        - style: estilo de composição (melodic, rhythmic, balanced, experimental)
        - instruments: lista com nomes dos instrumentos a serem incluídos (se None, usa os instrumentos ativos)
        
        Retorna:
        - Uma partitura music21 com múltiplos instrumentos
        """
        if not self.rhythm_patterns or not self.pitch_patterns:
            print("Dados de análise insuficientes. Execute o carregamento dos dados primeiro.")
            return None
        
        # Define o estilo de composição
        self.current_style = style
        style_params = self.composition_templates.get(style, self.composition_templates["balanced"])
        
        # Define quais instrumentos usar
        if instruments is None:
            # Se não especificado, usa os instrumentos ativos
            instruments_to_use = self.active_instruments
        else:
            # Filtra apenas os instrumentos válidos da lista fornecida
            instruments_to_use = [inst for inst in instruments if inst in self.instruments]
            if not instruments_to_use:
                # Se nenhum instrumento válido, usa o padrão
                instruments_to_use = ["piano_direita", "piano_esquerda"]
        
        # Cria uma nova partitura
        score = m21.stream.Score()
        
        # Adiciona metadados
        score.insert(0, m21.metadata.Metadata())
        score.metadata.title = title
        score.metadata.composer = "GrammarComposer AI"
        
        # Trata o piano como caso especial (duas pautas em um sistema)
        has_piano = "piano_direita" in instruments_to_use or "piano_esquerda" in instruments_to_use
        
        # Cria um dicionário para agrupar partes por instrumento (para o caso do piano)
        instrument_parts = {}
        
        # Gera partes para cada instrumento
        for instrument_name in instruments_to_use:
            # Obtém configurações do instrumento
            if instrument_name not in self.instruments:
                continue
                
            instrument_obj, min_pitch, max_pitch, transposition = self.instruments[instrument_name]
            
            # Aplica ajustes específicos do estilo
            min_pitch = max(min_pitch, style_params["min_pitch"])
            max_pitch = min(max_pitch, style_params["max_pitch"])
            
            # Cria uma parte para o instrumento
            part = m21.stream.Part()
            
            # Adiciona o objeto de instrumento para obter o timbre correto no MIDI
            part.append(instrument_obj)
            
            # Adiciona a clave apropriada
            if instrument_name in self.instrument_clefs:
                part.append(self.instrument_clefs[instrument_name])
            
            # Adiciona informações de compasso e tonalidade
            ts = m21.meter.TimeSignature(self.time_signature)
            part.append(ts)
            
            ks = m21.key.Key(self.key_signature)
            part.append(ks)
            
            # Adiciona informação de andamento (apenas para o primeiro instrumento)
            if instrument_name == instruments_to_use[0]:
                mm = m21.tempo.MetronomeMark(number=self.tempo)
                part.append(mm)
            
            # Para manter a variação entre instrumentos, podemos modificar a complexidade rítmica
            # e o comprimento ligeiramente para cada instrumento
            complexity_variation = random.uniform(-0.1, 0.1)
            length_variation = random.randint(-4, 4)
            adjusted_length = max(8, self.composition_length + length_variation)
            adjusted_complexity = max(0.1, min(0.9, style_params["rhythm_complexity"] + complexity_variation))
            
            # Gera a sequência rítmica para este instrumento
            rhythm_sequence = self._generate_rhythm_sequence(adjusted_length, adjusted_complexity)
            
            # Gera a sequência melódica para este instrumento, respeitando sua tessitura
            pitch_sequence = self._generate_pitch_sequence(adjusted_length, min_pitch, max_pitch)
            
            # Aplica transposição se necessário (para instrumentos transpositores)
            if transposition != 0:
                pitch_sequence = [p + transposition if p > 0 else p for p in pitch_sequence]
            
            # Combina ritmos e alturas para criar a partitura
            self._create_score_from_sequences(part, rhythm_sequence, pitch_sequence)
            
            # Armazena a parte no dicionário
            instrument_parts[instrument_name] = part
        
        # Trata o piano como caso especial (duas mãos em um sistema)
        if has_piano and "piano_direita" in instrument_parts and "piano_esquerda" in instrument_parts:
            # Cria um grupo de staff para o piano
            piano_staff = m21.stream.PartStaff()
            piano_staff.insert(0, m21.instrument.Piano())
            
            # Adiciona as partes do piano ao grupo
            piano_staff.insert(0, instrument_parts["piano_direita"])
            piano_staff.insert(0, instrument_parts["piano_esquerda"])
            
            # Adiciona o grupo de piano à partitura
            score.insert(0, piano_staff)
            
            # Remove as partes individuais do piano do dicionário para não duplicá-las
            del instrument_parts["piano_direita"]
            del instrument_parts["piano_esquerda"]
        
        # Adiciona as demais partes à partitura
        for _, part in instrument_parts.items():
            score.insert(0, part)
        
        return score

    def set_active_instruments(self, instrument_list):
        """
        Define quais instrumentos estarão ativos para a próxima composição.
        
        Parâmetros:
        - instrument_list: lista com nomes dos instrumentos
        
        Retorna:
        - True se bem sucedido, False caso contrário
        """
        valid_instruments = []
        
        for inst in instrument_list:
            if inst in self.instruments:
                valid_instruments.append(inst)
            else:
                print(f"Instrumento '{inst}' não reconhecido e será ignorado.")
        
        if not valid_instruments:
            print("Nenhum instrumento válido na lista. Mantendo configuração atual.")
            return False
        
        self.active_instruments = valid_instruments
        print(f"Instrumentos ativos definidos: {', '.join(valid_instruments)}")
        return True        
    
    def get_available_instruments(self):
        """
        Retorna uma lista de todos os instrumentos disponíveis.
        """
        return list(self.instruments.keys())

    def get_active_instruments(self):
        """
        Retorna a lista de instrumentos atualmente ativos.
        """
        return self.active_instruments

    def select_analysis_folder(self):
        """
        Permite ao usuário selecionar a pasta contendo os resultados das análises.
        """
        root = tk.Tk()
        root.withdraw()
        folder_path = filedialog.askdirectory(
            title="Selecione a pasta com os resultados das análises"
        )
        
        if folder_path:
            self.analysis_folder = folder_path
            print(f"Pasta de análise selecionada: {self.analysis_folder}")
            return True
        return False
    
    def create_output_folder(self):
        """
        Cria uma pasta para salvar as composições geradas.
        """
        if not self.analysis_folder:
            print("Por favor, selecione primeiro a pasta de análise.")
            return False
        
        # Cria uma pasta dentro da pasta de análise
        self.output_folder = os.path.join(self.analysis_folder, "composicoes_geradas")
        if not os.path.exists(self.output_folder):
            os.makedirs(self.output_folder)
            print(f"Pasta para composições criada: {self.output_folder}")
        return True
    
    def load_analysis_data(self):
        """
        Carrega os dados de análise da pasta selecionada.
        """
        if not self.analysis_folder:
            print("Por favor, selecione primeiro a pasta de análise.")
            return False
        
        try:
            # Carregar dados de N-grams
            self._load_ngram_data()
            
            # Carregar dados de Sequitur
            self._load_sequitur_data()
            
            # Carregar dados de SIATEC
            self._load_siatec_data()
            
            print("Dados de análise carregados com sucesso!")
            return True
        
        except Exception as e:
            print(f"Erro ao carregar dados de análise: {e}")
            return False
    
    def _load_ngram_data(self):
        """
        Carrega os dados de análise de N-grams.
        """
       # Buscar arquivos CSV de análise de N-grams rítmicos
        rhythm_files = glob.glob(os.path.join(self.analysis_folder, "*rhythm_ngrams_n*.csv"))
        
        # Filtrar para usar preferencialmente os dados globais
        global_rhythm_files = [f for f in rhythm_files if "global_corpus" in f]
        if global_rhythm_files:
            rhythm_files = global_rhythm_files
        
        # Carregar padrões rítmicos
        for file in rhythm_files:
            try:
                df = pd.read_csv(file)
                if "Padrão" in df.columns and "Frequência" in df.columns:
                    for _, row in df.iterrows():
                        pattern_str = row["Padrão"]
                        frequency = row["Frequência"]
                        
                        # Extrair valores numéricos do formato string do padrão
                        pattern = self._extract_pattern_from_string(pattern_str)
                        
                        if pattern:
                            if pattern not in self.rhythm_patterns:
                                self.rhythm_patterns[pattern] = frequency
                            else:
                                self.rhythm_patterns[pattern] += frequency
            except Exception as e:
                print(f"Erro ao processar arquivo {file}: {e}")
        
        # Buscar arquivos CSV de análise de N-grams melódicos
        pitch_files = glob.glob(os.path.join(self.analysis_folder, "*pitch_ngrams_n*.csv"))
        
        # Filtrar para usar preferencialmente os dados globais
        global_pitch_files = [f for f in pitch_files if "global_corpus" in f]
        if global_pitch_files:
            pitch_files = global_pitch_files
        
        # Carregar padrões melódicos
        for file in pitch_files:
            try:
                df = pd.read_csv(file)
                if "Padrão" in df.columns and "Frequência" in df.columns:
                    for _, row in df.iterrows():
                        pattern_str = row["Padrão"]
                        frequency = row["Frequência"]
                        
                        # Extrair notas do formato string do padrão, preservando 'Rest'
                        pattern = self._extract_pattern_from_string(pattern_str)
                        
                        if pattern:
                            if pattern not in self.pitch_patterns:
                                self.pitch_patterns[pattern] = frequency
                            else:
                                self.pitch_patterns[pattern] += frequency
            except Exception as e:
                print(f"Erro ao processar arquivo {file}: {e}")
        
        # NOVO: Buscar arquivos CSV de análise de N-grams de velocities
        velocity_files = glob.glob(os.path.join(self.analysis_folder, "*velocity_ngrams_n*.csv"))
        
        # Filtrar para usar preferencialmente os dados globais
        global_velocity_files = [f for f in velocity_files if "global_corpus" in f]
        if global_velocity_files:
            velocity_files = global_velocity_files
        
        # Carregar padrões de dinâmica
        for file in velocity_files:
            try:
                df = pd.read_csv(file)
                if "Padrão" in df.columns and "Frequência" in df.columns:
                    for _, row in df.iterrows():
                        pattern_str = row["Padrão"]
                        frequency = row["Frequência"]
                        
                        # Extrair valores numéricos do formato string do padrão
                        pattern = self._extract_pattern_from_string(pattern_str)
                        
                        if pattern:
                            if pattern not in self.velocity_patterns:
                                self.velocity_patterns[pattern] = frequency
                            else:
                                self.velocity_patterns[pattern] += frequency
            except Exception as e:
                print(f"Erro ao processar arquivo de dinâmicas {file}: {e}")
    
    def _load_sequitur_data(self):
        """
        Carrega os dados de análise Sequitur.
        """
        # Buscar arquivos CSV de análise Sequitur para ritmos
        rhythm_files = glob.glob(os.path.join(self.analysis_folder, "*rhythm_analysis.csv"))
        
        # Filtrar para usar preferencialmente os dados globais
        global_rhythm_files = [f for f in rhythm_files if "global_corpus" in f]
        if global_rhythm_files:
            rhythm_files = global_rhythm_files
        
        # Carregar regras Sequitur para ritmos
        for file in rhythm_files:
            try:
                df = pd.read_csv(file)
                sequitur_rows = df[df["Tipo"].str.contains("Sequitur", na=False)]
                
                for _, row in sequitur_rows.iterrows():
                    rule = row.get("Padrão", "")
                    expansion = row.get("Expansão", "")
                    
                    if rule and expansion:
                        # Extrair valores do formato string da expansão
                        expansion_pattern = self._extract_pattern_from_string(expansion)
                        
                        if expansion_pattern:
                            # Adicione esta linha para verificar pausas nas regras rítmicas
                            if 'Rest' in str(expansion_pattern):
                                print(f"Processada regra Sequitur rítmica contendo pausas: {rule} -> {expansion_pattern}")
                                
                            self.sequitur_rhythm_rules[rule] = expansion_pattern
            except Exception as e:
                print(f"Erro ao processar regras Sequitur de ritmo em {file}: {e}")
        
        # Buscar arquivos CSV de análise Sequitur para melodias
        pitch_files = glob.glob(os.path.join(self.analysis_folder, "*pitch_analysis.csv"))
        
        # Filtrar para usar preferencialmente os dados globais
        global_pitch_files = [f for f in pitch_files if "global_corpus" in f]
        if global_pitch_files:
            pitch_files = global_pitch_files
        
        # Carregar regras Sequitur para melodias
        for file in pitch_files:
            try:
                df = pd.read_csv(file)
                sequitur_rows = df[df["Tipo"].str.contains("Sequitur", na=False)]
                
                for _, row in sequitur_rows.iterrows():
                    rule = row.get("Padrão", "")
                    expansion = row.get("Expansão", "")
                    
                    if rule and expansion:
                        # Extrair notas do formato string da expansão
                        expansion_pattern = self._extract_pattern_from_string(expansion)
                        
                        if expansion_pattern:
                            # Adicione esta linha para verificar pausas nas regras melódicas
                            if 'Rest' in str(expansion_pattern):
                                print(f"Processada regra Sequitur melódica contendo pausas: {rule} -> {expansion_pattern}")
                                
                            self.sequitur_pitch_rules[rule] = expansion_pattern
            except Exception as e:
                print(f"Erro ao processar regras Sequitur de melodia em {file}: {e}")

        # NOVO: Buscar arquivos CSV de análise Sequitur para velocities
        velocity_files = glob.glob(os.path.join(self.analysis_folder, "*velocity_analysis.csv"))
        
        # Filtrar para usar preferencialmente os dados globais
        global_velocity_files = [f for f in velocity_files if "global_corpus" in f]
        if global_velocity_files:
            velocity_files = global_velocity_files
        
        # Carregar regras Sequitur para velocities
        for file in velocity_files:
            try:
                df = pd.read_csv(file)
                sequitur_rows = df[df["Tipo"].str.contains("Sequitur", na=False)]
                
                for _, row in sequitur_rows.iterrows():
                    rule = row.get("Padrão", "")
                    expansion = row.get("Expansão", "")
                    
                    if rule and expansion:
                        # Extrair valores do formato string da expansão
                        expansion_pattern = self._extract_pattern_from_string(expansion)
                        
                        if expansion_pattern:
                            self.sequitur_velocity_rules[rule] = expansion_pattern
            except Exception as e:
                print(f"Erro ao processar regras Sequitur de dinâmica em {file}: {e}")                
    
    def _load_siatec_data(self):
        """
        Carrega os dados de análise SIATEC.
        """
        # Buscar arquivos CSV de análise SIATEC para ritmos
        rhythm_files = glob.glob(os.path.join(self.analysis_folder, "*rhythm_analysis.csv"))
        
        # Filtrar para usar preferencialmente os dados globais
        global_rhythm_files = [f for f in rhythm_files if "global_corpus" in f]
        if global_rhythm_files:
            rhythm_files = global_rhythm_files
        
        # Carregar padrões SIATEC para ritmos
        for file in rhythm_files:
            try:
                df = pd.read_csv(file)
                siatec_rows = df[df["Tipo"].str.contains("SIATEC", na=False)]
                
                for _, row in siatec_rows.iterrows():
                    pattern_str = row.get("Padrão", "")
                    occurrences = row.get("Ocorrências", "")
                    
                    if pattern_str:
                        # Extrair valores do formato string do padrão
                        pattern = self._extract_pattern_from_string(pattern_str)
                        
                        if pattern:
                            # Adicione esta linha para verificar pausas nos padrões rítmicos
                            if 'Rest' in str(pattern):
                                print(f"Processado padrão SIATEC rítmico contendo pausas: {pattern}")
                                
                            # Contar a frequência com base no número de ocorrências
                            freq = 1
                            if occurrences:
                                try:
                                    # Tenta contar o número de índices nas ocorrências
                                    occ_list = self._extract_pattern_from_string(occurrences)
                                    freq = len(occ_list) if occ_list else 1
                                except:
                                    pass
                            
                            self.siatec_rhythm_patterns[pattern] = freq
            except Exception as e:
                print(f"Erro ao processar padrões SIATEC de ritmo em {file}: {e}")
        
        # Buscar arquivos CSV de análise SIATEC para melodias
        pitch_files = glob.glob(os.path.join(self.analysis_folder, "*pitch_analysis.csv"))
        
        # Filtrar para usar preferencialmente os dados globais
        global_pitch_files = [f for f in pitch_files if "global_corpus" in f]
        if global_pitch_files:
            pitch_files = global_pitch_files
        
        # Carregar padrões SIATEC para melodias
        for file in pitch_files:
            try:
                df = pd.read_csv(file)
                siatec_rows = df[df["Tipo"].str.contains("SIATEC", na=False)]
                                
                for _, row in siatec_rows.iterrows():
                    pattern_str = row.get("Padrão", "")
                    occurrences = row.get("Ocorrências", "")
                    
                    if pattern_str:
                        # Extrair notas do formato string do padrão
                        pattern = self._extract_pattern_from_string(pattern_str)
                        
                        if pattern:
                            # Adicione esta linha para verificar pausas nos padrões melódicos
                            if 'Rest' in str(pattern):
                                print(f"Processado padrão SIATEC melódico contendo pausas: {pattern}")
                                
                            # Contar a frequência com base no número de ocorrências
                            freq = 1
                            if occurrences:
                                try:
                                    # Tenta contar o número de índices nas ocorrências
                                    occ_list = self._extract_pattern_from_string(occurrences)
                                    freq = len(occ_list) if occ_list else 1
                                except:
                                    pass
                            
                            self.siatec_pitch_patterns[pattern] = freq
            except Exception as e:
                print(f"Erro ao processar padrões SIATEC de melodia em {file}: {e}")

        # NOVO: Buscar arquivos CSV de análise SIATEC para velocities
        velocity_files = glob.glob(os.path.join(self.analysis_folder, "*velocity_analysis.csv"))
        
        # Filtrar para usar preferencialmente os dados globais
        global_velocity_files = [f for f in velocity_files if "global_corpus" in f]
        if global_velocity_files:
            velocity_files = global_velocity_files
        
        # Carregar padrões SIATEC para velocities
        for file in velocity_files:
            try:
                df = pd.read_csv(file)
                siatec_rows = df[df["Tipo"].str.contains("SIATEC", na=False)]
                                
                for _, row in siatec_rows.iterrows():
                    pattern_str = row.get("Padrão", "")
                    occurrences = row.get("Ocorrências", "")
                    
                    if pattern_str:
                        # Extrair valores numéricos do formato string do padrão
                        pattern = self._extract_pattern_from_string(pattern_str)
                        
                        if pattern:
                            # Contar a frequência com base no número de ocorrências
                            freq = 1
                            if occurrences:
                                try:
                                    # Tenta contar o número de índices nas ocorrências
                                    occ_list = self._extract_pattern_from_string(occurrences)
                                    freq = len(occ_list) if occ_list else 1
                                except:
                                    pass
                            
                            self.siatec_velocity_patterns[pattern] = freq
            except Exception as e:
                print(f"Erro ao processar padrões SIATEC de dinâmica em {file}: {e}")          

    def _generate_velocity_sequence(self, length, pitch_sequence=None, style_params=None):
        """
        Gera uma sequência de velocities (dinâmicas) com base nos padrões analisados.
        
        Parâmetros:
        - length: Comprimento da sequência a ser gerada
        - pitch_sequence: Sequência de alturas correspondente (opcional)
        - style_params: Parâmetros de estilo (opcional)
        
        Retorna:
        - Lista de valores de velocity (0-127)
        """
        velocity_sequence = []
        remaining_length = length
        
        # Define limites de dinâmica baseados no estilo
        min_dynamic = "pp"
        max_dynamic = "ff"
        
        if style_params:
            min_dynamic = style_params.get("min_dynamic", min_dynamic)
            max_dynamic = style_params.get("max_dynamic", max_dynamic)
        
        # Converte limites para valores de velocity
        min_velocity = self.velocity_processor.get_velocity_from_dynamic(min_dynamic)
        max_velocity = self.velocity_processor.get_velocity_from_dynamic(max_dynamic)
        
        # Se estiver no modo de dinâmica fixa, retorna uma sequência constante
        if self.dynamics_mode == "fixed":
            fixed_value = self.velocity_processor.get_velocity_from_dynamic(self.fixed_dynamic)
            return [fixed_value] * length
        
        # Pesos para cada fonte de padrões
        sources = []
        if self.velocity_patterns and self.use_ngrams:
            sources.append(("ngram", self.ngram_weight))
        if self.sequitur_velocity_rules and self.use_sequitur:
            sources.append(("sequitur", self.sequitur_weight))
        if self.siatec_velocity_patterns and self.use_siatec:
            sources.append(("siatec", self.siatec_weight))
        
        # Normaliza os pesos
        total_weight = sum([w for _, w in sources])
        normalized_sources = [(s, w/total_weight) for s, w in sources] if total_weight > 0 else []
        
        # Se não há fontes de padrões ou modo de contorno, gera baseado nas alturas
        if not sources or self.dynamics_mode == "contour":
            if pitch_sequence and len(pitch_sequence) >= length:
                # Mode de contorno: dinâmicas seguem o contorno melódico
                return self._generate_contour_based_velocities(pitch_sequence, min_velocity, max_velocity)
            else:
                # Gera uma sequência aleatória dentro dos limites de dinâmica
                for i in range(length):
                    velocity_value = random.randint(min_velocity, max_velocity)
                    velocity_sequence.append(velocity_value)
                return velocity_sequence
        
        # Gera a sequência baseada nos padrões
        while remaining_length > 0:
            # Escolhe a fonte de padrões com base nos pesos
            source_type = random.choices([s for s, _ in normalized_sources], 
                                         weights=[w for _, w in normalized_sources])[0]
            
            # Pega um padrão da fonte selecionada
            pattern = None
            if source_type == "ngram" and self.velocity_patterns:
                # Seleciona padrões com base em sua frequência
                patterns = list(self.velocity_patterns.keys())
                weights = list(self.velocity_patterns.values())
                pattern = random.choices(patterns, weights=weights)[0]
            
            elif source_type == "sequitur" and self.sequitur_velocity_rules:
                # Seleciona uma regra aleatória
                rule = random.choice(list(self.sequitur_velocity_rules.keys()))
                pattern = self.sequitur_velocity_rules[rule]
            
            elif source_type == "siatec" and self.siatec_velocity_patterns:
                # Seleciona padrões com base em sua frequência
                patterns = list(self.siatec_velocity_patterns.keys())
                weights = list(self.siatec_velocity_patterns.values())
                pattern = random.choices(patterns, weights=weights)[0]
            
            # Se não conseguiu obter um padrão, usa valor aleatório
            if not pattern:
                # Gera um único valor de velocity aleatório
                pattern = (random.randint(min_velocity, max_velocity),)
            
            # Adiciona o padrão à sequência, mas não mais que o comprimento restante
            for velocity in pattern[:remaining_length]:
                # Verifica se é um valor numérico
                if isinstance(velocity, (int, float)):
                    # Limita ao intervalo min-max
                    velocity_value = max(min_velocity, min(int(velocity), max_velocity))
                    velocity_sequence.append(velocity_value)
                    remaining_length -= 1
                else:
                    # Se não for numérico, pode ser uma referência a uma regra sequitur
                    # Nesse caso, tenta substituir pela expansão da regra
                    if velocity in self.sequitur_velocity_rules:
                        expansion = self.sequitur_velocity_rules[velocity]
                        for sub_velocity in expansion[:remaining_length]:
                            if isinstance(sub_velocity, (int, float)):
                                velocity_value = max(min_velocity, min(int(sub_velocity), max_velocity))
                                velocity_sequence.append(velocity_value)
                                remaining_length -= 1
                    else:
                        # Se não puder resolver, usa um valor médio
                        velocity_sequence.append(64)  # mf como valor padrão
                        remaining_length -= 1
        
        # Retorna a sequência gerada
        return velocity_sequence
    
    def _generate_contour_based_velocities(self, pitch_sequence, min_velocity=40, max_velocity=100):
        """
        Gera velocities baseadas no contorno melódico.
        Notas mais agudas tendem a ser mais fortes.
        
        Parâmetros:
        - pitch_sequence: Sequência de alturas (valores MIDI ou 'Rest')
        - min_velocity: Valor mínimo de velocity
        - max_velocity: Valor máximo de velocity
        
        Retorna:
        - Lista de valores de velocity (0-127)
        """
        velocity_sequence = []
        
        # Obter valores de pitch numéricos (ignore pausas)
        pitch_values = []
        for p in pitch_sequence:
            if isinstance(p, (int, float)) and p > 0:
                pitch_values.append(p)
            elif isinstance(p, str) and p != 'Rest':
                # Tenta converter usando music21
                try:
                    note_obj = m21.note.Note(p)
                    pitch_values.append(note_obj.pitch.midi)
                except:
                    pitch_values.append(60)  # Valor padrão
        
        # Se não há valores de pitch válidos, retorna uma sequência constante
        if not pitch_values:
            return [64] * len(pitch_sequence)  # mf como padrão
        
        # Obter o intervalo dos pitches para normalização
        min_pitch = min(pitch_values)
        max_pitch = max(pitch_values)
        pitch_range = max_pitch - min_pitch if max_pitch > min_pitch else 1
        
        # Gerar velocities baseadas na altura relativa
        for i, pitch in enumerate(pitch_sequence):
            if isinstance(pitch, (int, float)) and pitch > 0:
                # Normaliza o pitch e mapeia para o intervalo de velocity
                normalized = (pitch - min_pitch) / pitch_range
                velocity = min_velocity + normalized * (max_velocity - min_velocity)
                velocity_sequence.append(int(velocity))
            elif isinstance(pitch, str) and pitch != 'Rest':
                # Tenta converter usando music21
                try:
                    note_obj = m21.note.Note(pitch)
                    midi_pitch = note_obj.pitch.midi
                    normalized = (midi_pitch - min_pitch) / pitch_range
                    velocity = min_velocity + normalized * (max_velocity - min_velocity)
                    velocity_sequence.append(int(velocity))
                except:
                    velocity_sequence.append(64)  # Valor padrão (mf)
            else:
                # É uma pausa ou valor inválido
                velocity_sequence.append(0)  # Velocity 0 para pausas
        
        return velocity_sequence
    
    def _extract_pattern_from_string(self, pattern_str):
        """
        Extrai padrões de sua representação em string.
        Por exemplo, converte "(0.25, 0.5, 1.0)" para (0.25, 0.5, 1.0).
        """
        if not pattern_str or not isinstance(pattern_str, str):
            return None
        
        try:
            # Remove os caracteres de tuple e divide por vírgulas
            clean_str = pattern_str.strip("()[]'\"")
            
            # Trata o caso de string vazia após a limpeza
            if not clean_str:
                return None
                
            # Verifica se o padrão tem separadores (vírgulas ou espaços)
            if ',' in clean_str:
                parts = clean_str.split(',')
            elif ' ' in clean_str:
                parts = clean_str.split()
            else:
                # Se não tiver separadores, retorna como um único elemento
                return (clean_str,)
            
            # Limpa e converte cada parte
            result = []
            for part in parts:
                part = part.strip("'\" ")
                if part:
                    # Tenta converter para float se possível, caso contrário mantém como string
                    try:
                        if part.replace('.', '', 1).isdigit():
                            result.append(float(part))
                        else:
                            result.append(part)
                    except ValueError:
                        result.append(part)
            
            return tuple(result) if result else None
        
        except Exception as e:
            print(f"Erro ao extrair padrão da string '{pattern_str}': {e}")
            return None
    
    def generate_composition(self, title="Composição Gerada", style="balanced"):
        """
        Gera uma nova composição com base nos padrões analisados.
        """
        if not self.rhythm_patterns or not self.pitch_patterns:
            print("Dados de análise insuficientes. Execute o carregamento dos dados primeiro.")
            return None
        
        # Define o estilo de composição
        self.current_style = style
        style_params = self.composition_templates.get(style, self.composition_templates["balanced"])
        
        # Cria uma nova partitura
        score = m21.stream.Score()
        
        # Adiciona metadados
        score.insert(0, m21.metadata.Metadata())
        score.metadata.title = title
        score.metadata.composer = "GrammarComposer AI"
        
        # Cria uma parte para a composição
        part = m21.stream.Part()
        
        # Adiciona informações de compasso e tonalidade
        ts = m21.meter.TimeSignature(self.time_signature)
        part.append(ts)
        
        ks = m21.key.Key(self.key_signature)
        part.append(ks)
        
        # Adiciona informação de andamento
        mm = m21.tempo.MetronomeMark(number=self.tempo)
        part.append(mm)
        
        # Gera a sequência rítmica
        rhythm_sequence = self._generate_rhythm_sequence(self.composition_length, style_params["rhythm_complexity"])
        
        # Gera a sequência melódica
        pitch_sequence = self._generate_pitch_sequence(self.composition_length, style_params["min_pitch"], style_params["max_pitch"])
        
        # Combina ritmos e alturas para criar a partitura
        self._create_score_from_sequences(part, rhythm_sequence, pitch_sequence)
        
        # Adiciona a parte à partitura
        score.append(part)
        
        return score

    def generate_composition_with_exact_measures(self, measure_count, title="Composição Gerada", style="balanced"):
        """
        Gera uma composição com um número específico de compassos.
        
        Parâmetros:
        - measure_count: número exato de compassos a serem gerados
        - title: título da composição
        - style: estilo de composição (melodic, rhythmic, balanced, experimental)
        
        Retorna:
        - Uma partitura music21 com o número específico de compassos
        """
        if not self.rhythm_patterns or not self.pitch_patterns:
            print("Dados de análise insuficientes. Execute o carregamento dos dados primeiro.")
            return None
        
        # Define o estilo de composição
        self.current_style = style
        style_params = self.composition_templates.get(style, self.composition_templates["balanced"])
        
        # Estima o número de eventos necessários para gerar o número de compassos desejado
        # Essa estimativa depende da fórmula de compasso atual
        time_sig = self.time_signature
        events_per_measure = 4  # Valor padrão para 4/4
        
        # Ajusta com base na fórmula de compasso
        if time_sig:
            try:
                num, denom = map(int, time_sig.split('/'))
                if denom == 4:
                    events_per_measure = num
                elif denom == 8:
                    events_per_measure = num / 2
                else:
                    events_per_measure = num
            except:
                pass  # Usa o valor padrão se houver erro
        
        # Calcula o número aproximado de eventos necessários
        estimated_events = measure_count * events_per_measure
        original_length = self.composition_length
        self.composition_length = int(estimated_events)
        
        # Gera a composição
        if hasattr(self, 'generate_multi_instrument_composition_with_doubles'):
            score = self.generate_multi_instrument_composition_with_doubles(title=title, style=style)
        else:
            score = self.generate_multi_instrument_composition(title=title, style=style)
        
        if score:
            # Verifica o número de compassos obtido
            first_part = score.parts[0]
            if isinstance(first_part, m21.stream.PartStaff):
                first_part = first_part.getElementsByClass('Part')[0]
            
            current_measures = len(first_part.getElementsByClass('Measure'))
            
            # Se o número de compassos não corresponde, tenta ajustar
            if current_measures != measure_count:
                attempts = 1
                max_attempts = 3
                
                while current_measures != measure_count and attempts < max_attempts:
                    print(f"Ajustando composição: tentativa {attempts} ({current_measures} compassos vs. {measure_count} desejados)")
                    
                    # Calcula o fator de ajuste baseado na diferença
                    adjustment_factor = measure_count / current_measures
                    new_length = int(self.composition_length * adjustment_factor)
                    
                    # Aplica o novo comprimento
                    self.composition_length = max(8, new_length)
                    
                    # Regenera a composição
                    if hasattr(self, 'generate_multi_instrument_composition_with_doubles'):
                        score = self.generate_multi_instrument_composition_with_doubles(title=title, style=style)
                    else:
                        score = self.generate_multi_instrument_composition(title=title, style=style)
                    
                    # Verifica novamente
                    first_part = score.parts[0]
                    if isinstance(first_part, m21.stream.PartStaff):
                        first_part = first_part.getElementsByClass('Part')[0]
                    
                    current_measures = len(first_part.getElementsByClass('Measure'))
                    attempts += 1
                
                print(f"Resultado final: {current_measures} compassos (desejados: {measure_count})")
        
        # Restaura o comprimento original
        self.composition_length = original_length
        
        return score        
    
    def _generate_rhythm_sequence(self, length, complexity):
        """
        Gera uma sequência rítmica com base nos padrões analisados,
        garantindo compatibilidade com as fórmulas de compasso.
        """
        rhythm_sequence = []
        remaining_length = length
        
        # Obtém informações do compasso atual
        try:
            numerator, denominator = map(int, self.time_signature.split('/'))
            beat_value = 4.0 / denominator
            measure_duration = numerator * beat_value
            
            # MELHORIA: Lista de durações que fazem sentido no contexto do compasso atual
            if denominator == 4:  # Compassos em 4 (4/4, 3/4, etc)
                preferred_durations = [0.25, 0.5, 1.0, 2.0, 0.75, 1.5]
            elif denominator == 8:  # Compassos em 8 (6/8, 3/8, etc)
                preferred_durations = [0.125, 0.25, 0.5, 1.0, 0.375, 0.75]
            else:
                preferred_durations = [0.25, 0.5, 1.0, 2.0, 0.75, 1.5]
        except:
            # Padrão se não conseguir extrair informações do compasso
            preferred_durations = [0.25, 0.5, 1.0, 2.0, 0.75, 1.5]
            measure_duration = 4.0  # Assume 4/4
        
        # MELHORIA: Ajusta complexidade por compasso atual
        complexity_factor = min(measure_duration / 4.0, 1.0)  # Ajusta com base no tamanho do compasso
        adjusted_complexity = complexity * complexity_factor
        
        # Pesos para cada fonte de padrões
        sources = []
        if self.rhythm_patterns and self.use_ngrams:
            sources.append(("ngram", self.ngram_weight))
        if self.sequitur_rhythm_rules and self.use_sequitur:
            sources.append(("sequitur", self.sequitur_weight))
        if self.siatec_rhythm_patterns and self.use_siatec:
            sources.append(("siatec", self.siatec_weight))
        
        # Normaliza os pesos
        total_weight = sum([w for _, w in sources])
        normalized_sources = [(s, w/total_weight) for s, w in sources]
        
        while remaining_length > 0:
            # Escolhe a fonte de padrões com base nos pesos
            source_type = "ngram"  # padrão caso nenhuma fonte seja selecionada
            if normalized_sources:
                source_type = random.choices([s for s, _ in normalized_sources], 
                                            weights=[w for _, w in normalized_sources])[0]
            
            # Pega um padrão da fonte selecionada
            pattern = None
            if source_type == "ngram" and self.rhythm_patterns:
                # Seleciona padrões com base em sua frequência
                patterns = list(self.rhythm_patterns.keys())
                weights = list(self.rhythm_patterns.values())
                pattern = random.choices(patterns, weights=weights)[0]
            
            elif source_type == "sequitur" and self.sequitur_rhythm_rules:
                # Seleciona uma regra aleatória
                rule = random.choice(list(self.sequitur_rhythm_rules.keys()))
                pattern = self.sequitur_rhythm_rules[rule]
            
            elif source_type == "siatec" and self.siatec_rhythm_patterns:
                # Seleciona padrões com base em sua frequência
                patterns = list(self.siatec_rhythm_patterns.keys())
                weights = list(self.siatec_rhythm_patterns.values())
                pattern = random.choices(patterns, weights=weights)[0]
            
            # Se não conseguiu obter um padrão, cria valores aleatórios
            if not pattern:
                # Gera um único valor de duração aleatório como fallback
                durations = [0.25, 0.5, 1.0, 2.0, 0.75, 1.5]
                weights = [4, 6, 10, 2, 2, 1]  # Pesos que favorecem os mais comuns
                pattern = (random.choices(durations, weights=weights)[0],)
            
            # Adiciona o padrão à sequência, mas não mais que o comprimento restante
            for duration in pattern[:remaining_length]:
                # Verifica se é um valor numérico
                if isinstance(duration, (int, float)):
                    rhythm_sequence.append(duration)
                    remaining_length -= 1
                else:
                    # Se não for numérico, pode ser uma referência a uma regra sequitur
                    # Nesse caso, tenta substituir pela expansão da regra
                    if duration in self.sequitur_rhythm_rules:
                        expansion = self.sequitur_rhythm_rules[duration]
                        for sub_duration in expansion[:remaining_length]:
                            if isinstance(sub_duration, (int, float)):
                                rhythm_sequence.append(sub_duration)
                                remaining_length -= 1
                    else:
                        # Se não puder resolver, usa um valor padrão
                        rhythm_sequence.append(0.5)  # colcheia como valor padrão
                        remaining_length -= 1
        
        # Aplicar complexidade rítmica (ajustar a variabilidade dos padrões)
        if complexity > 0.7:
            # Maior complexidade: introduz mais variações rítmicas
            for i in range(len(rhythm_sequence)):
                if random.random() < (complexity - 0.7) * 3:  # Proporcional à complexidade
                    options = [0.125, 0.25, 0.5, 0.75, 1.0, 1.5]
                    rhythm_sequence[i] = random.choice(options)

        # Garantir que a sequência não esteja vazia
        if not rhythm_sequence:
            # Gerar uma sequência básica de semínimas (quarter notes)
            rhythm_sequence = [1.0] * max(4, length)
            print("Aviso: Gerada sequência rítmica padrão devido a dados insuficientes.")
        
        return rhythm_sequence                    
    
    def _generate_pitch_sequence(self, length, min_pitch=60, max_pitch=84):
        """
        Gera uma sequência de alturas (pitch) com base nos padrões analisados.
        Se os padrões estiverem em formato simbólico (ex: 'C4' ou 'Rest'), converte para valores MIDI.
        """
        pitch_sequence = []
        remaining_length = length
        
        # Pesos para cada fonte de padrões
        sources = []
        if self.pitch_patterns and self.use_ngrams:
            sources.append(("ngram", self.ngram_weight))
        if self.sequitur_pitch_rules and self.use_sequitur:
            sources.append(("sequitur", self.sequitur_weight))
        if self.siatec_pitch_patterns and self.use_siatec:
            sources.append(("siatec", self.siatec_weight))
        
        # Normaliza os pesos
        total_weight = sum([w for _, w in sources])
        normalized_sources = [(s, w/total_weight) for s, w in sources]
        
        # Se não há padrões ou sources vazias, cria uma sequência completamente aleatória
        if not sources:
            scales = {
                'C': [0, 2, 4, 5, 7, 9, 11],  # Escala maior de C (dó maior)
                'Am': [9, 11, 0, 2, 4, 5, 7]  # Escala menor de A (lá menor, relativa de C)
            }
            selected_scale = scales['C']  # Escala padrão
            
            for _ in range(length):
                # Gera notas dentro da escala selecionada
                scale_degree = random.randint(0, len(selected_scale) - 1)
                octave = random.randint(min_pitch // 12, max_pitch // 12)
                midi_value = (octave * 12) + selected_scale[scale_degree]
                
                # Limita ao intervalo min-max
                midi_value = max(min_pitch, min(midi_value, max_pitch))
                
                # Adicione algumas pausas aleatoriamente (10% de chance)
                if random.random() < 0.1:
                    midi_value = 0  # Pausa
                
                pitch_sequence.append(midi_value)
            
            return pitch_sequence
        
        while remaining_length > 0:
            # Escolhe a fonte de padrões com base nos pesos
            source_type = random.choices([s for s, _ in normalized_sources], 
                                        weights=[w for _, w in normalized_sources])[0]
            
            # Pega um padrão da fonte selecionada
            pattern = None
            if source_type == "ngram" and self.pitch_patterns:
                # Seleciona padrões com base em sua frequência
                patterns = list(self.pitch_patterns.keys())
                weights = list(self.pitch_patterns.values())
                pattern = random.choices(patterns, weights=weights)[0]
            
            elif source_type == "sequitur" and self.sequitur_pitch_rules:
                # Seleciona uma regra aleatória
                rule = random.choice(list(self.sequitur_pitch_rules.keys()))
                pattern = self.sequitur_pitch_rules[rule]
            
            elif source_type == "siatec" and self.siatec_pitch_patterns:
                # Seleciona padrões com base em sua frequência
                patterns = list(self.siatec_pitch_patterns.keys())
                weights = list(self.siatec_pitch_patterns.values())
                pattern = random.choices(patterns, weights=weights)[0]
            
            # Se não conseguiu obter um padrão, cria valores aleatórios
            if not pattern:
                # Gera um único valor de altura aleatório como fallback
                pattern = (random.randint(min_pitch, max_pitch),)
            
            # Adiciona o padrão à sequência, mas não mais que o comprimento restante
            for pitch in pattern[:remaining_length]:
                # Converte para MIDI se necessário
                midi_pitch = self._note_to_midi(pitch, min_pitch, max_pitch)
                
                # Verifica se o pitch está dentro do intervalo desejado e não é uma pausa
                if midi_pitch > 0 and (midi_pitch < min_pitch or midi_pitch > max_pitch):
                    # Ajusta para o intervalo desejado, mantendo a classe de altura
                    while midi_pitch < min_pitch:
                        midi_pitch += 12  # Sobe uma oitava
                    while midi_pitch > max_pitch:
                        midi_pitch -= 12  # Desce uma oitava
                
                pitch_sequence.append(midi_pitch)
                remaining_length -= 1
        
        # Garantir que a sequência não esteja vazia
        if not pitch_sequence:
            # Gerar uma sequência básica de notas da escala de Dó maior
            scale = [60, 62, 64, 65, 67, 69, 71, 72]  # C major scale
            pitch_sequence = [scale[i % len(scale)] for i in range(max(4, length))]
            print("Aviso: Gerada sequência melódica padrão devido a dados insuficientes.")
        
        return pitch_sequence

        # Função para converter nota simbólica para valor MIDI
    def _note_to_midi(self, pitch, min_pitch=0, max_pitch=127):
        """
        Converte uma nota em formato simbólico para valor MIDI.
        Permite lidar com valores 'Rest', valores numéricos, e notas simbólicas.
        """
        try:
            # Se for 'Rest', converte para 0 (pausa)
            if pitch == 'Rest':
                return 0
                
            # Se já for um número, retorna ele mesmo
            if isinstance(pitch, (int, float)):
                return int(pitch)
                
            # Tenta converter usando music21
            note_obj = m21.note.Note(pitch)
            return note_obj.pitch.midi
        except:
            # Se falhar, retorna um valor padrão no meio do intervalo
            return (min_pitch + max_pitch) // 2

    def set_time_signature_options(self, use_variable=False, time_signatures=None, change_probability=0.2):
        """
        Configura as opções de fórmula de compasso, incluindo opções para fórmulas variáveis.
        
        Parâmetros:
        - use_variable: se True, utiliza fórmulas de compasso variáveis
        - time_signatures: lista de strings com fórmulas de compasso permitidas
        - change_probability: probabilidade (0-1) de mudar a fórmula entre compassos
        """
        self.use_variable_time_signatures = use_variable
        
        if time_signatures:
            self.variable_time_signatures = time_signatures
        
        self.time_sig_change_probability = max(0.0, min(1.0, change_probability))
        
        print(f"Configuração de fórmulas de compasso:")
        print(f"- Usar fórmulas variáveis: {self.use_variable_time_signatures}")
        if self.use_variable_time_signatures:
            print(f"- Fórmulas disponíveis: {', '.join(self.variable_time_signatures)}")
            print(f"- Probabilidade de mudança: {self.time_sig_change_probability:.2f}")
        else:
            print(f"- Fórmula fixa: {self.time_signature}")       
    
    def _create_score_from_sequences(self, part, rhythm_sequence, pitch_sequence, velocity_sequence=None, time_sig_sequence=None):
        """
        Cria uma partitura a partir das sequências de ritmo, altura e velocity,
        garantindo que as durações sejam consistentes com as fórmulas de compasso.
        """
        import music21 as m21
        
        # Garante que as sequências tenham o mesmo tamanho
        length = min(len(rhythm_sequence), len(pitch_sequence))
        
        # Se não tiver velocities, cria uma sequência padrão
        if not velocity_sequence or len(velocity_sequence) < length:
            velocity_sequence = [64] * length  # 64 = mezzo-forte (padrão)
        
        # MELHORIA: Usa a sequência global de fórmulas de compasso se disponível
        if time_sig_sequence is None and hasattr(self, '_current_time_sig_sequence'):
            time_sig_sequence = self._current_time_sig_sequence
            print(f"Usando sequência compartilhada de fórmulas de compasso")
        
        # Inicializa com a primeira fórmula de compasso
        current_time_sig_idx = 0
        current_time_sig = self.time_signature
        if time_sig_sequence and len(time_sig_sequence) > 0:
            current_time_sig = time_sig_sequence[0]
        
        time_sig = m21.meter.TimeSignature(current_time_sig)
        part.append(time_sig)
        
        # Contador para manter o registro do progresso pelo compasso
        current_beat = 0
        measure = m21.stream.Measure(number=1)
        
        # Obtém o número de tempos por compasso da fórmula atual
        beats_per_measure = time_sig.numerator
        beat_type = time_sig.denominator
        
        # Ajusta a duração por batida com base no tipo de compasso
        # Ex: Em 4/4, um tempo = 1.0, em 3/8, um tempo = 0.5
        beat_value = 4.0 / beat_type
        
        # Total de duração esperado em um compasso (em quarter lengths)
        measure_duration = beats_per_measure * beat_value
        
        # MELHORIA: Registro das durações dos compassos para fins de depuração
        measure_durations = {}
        
        i = 0
        while i < length:
            duration = rhythm_sequence[i]
            midi_pitch = pitch_sequence[i]
            velocity_value = velocity_sequence[i] if velocity_sequence else 64
            
            # MELHORIA: Evita durações que podem causar problemas
            # Arredonda a duração para um valor válido para MusicXML 
            # que seja compatível com a fórmula de compasso atual
            valid_durations = [0.0625, 0.125, 0.25, 0.5, 0.75, 1.0, 1.5, 2.0, 3.0, 4.0]
            closest_duration = min(valid_durations, key=lambda x: abs(x - duration))
            
            # MELHORIA: Não permite que durações excedam a medida do compasso
            closest_duration = min(closest_duration, measure_duration)
            duration = closest_duration
            
            # Verifica se a nota cabe no compasso atual
            remaining_measure_duration = measure_duration - current_beat
            
            if duration <= remaining_measure_duration:
                # A nota cabe integralmente no compasso atual
                if midi_pitch > 0:  # Nota normal
                    n = m21.note.Note()
                    n.pitch.midi = midi_pitch
                    n.quarterLength = duration
                    # NOVO: Define a dinâmica
                    if velocity_value > 0:
                        n.volume.velocity = velocity_value
                else:  # Pausa (midi_pitch <= 0 ou quando encontra 'Rest')
                    n = m21.note.Rest()
                    n.quarterLength = duration
                
                # Adiciona a nota/pausa ao compasso atual
                measure.append(n)
                current_beat += duration
                
            else:
                # A nota não cabe integralmente no compasso atual,
                # precisamos dividir entre o compasso atual e o próximo
                
                # Parte que cabe no compasso atual
                first_part_duration = remaining_measure_duration
                
                if first_part_duration > 0:
                    if midi_pitch > 0:  # Nota normal
                        n1 = m21.note.Note()
                        n1.pitch.midi = midi_pitch
                        n1.quarterLength = first_part_duration
                        n1.tie = m21.tie.Tie('start')  # Inicia uma ligadura
                        # NOVO: Define a dinâmica
                        if velocity_value > 0:
                            n1.volume.velocity = velocity_value
                        measure.append(n1)
                    else:  # Pausa
                        r1 = m21.note.Rest()
                        r1.quarterLength = first_part_duration
                        measure.append(r1)
                
                # Adiciona o compasso atual à parte
                part.append(measure)
                
                # Cria um novo compasso
                new_measure_number = len(part.getElementsByClass('Measure')) + 1
                measure = m21.stream.Measure(number=new_measure_number)
                
                # Verifica se deve mudar a fórmula de compasso para o próximo compasso
                if time_sig_sequence and new_measure_number <= len(time_sig_sequence):
                    current_time_sig_idx = new_measure_number - 1
                    if current_time_sig_idx < len(time_sig_sequence):
                        current_time_sig = time_sig_sequence[current_time_sig_idx]
                        time_sig = m21.meter.TimeSignature(current_time_sig)
                        measure.append(time_sig)
                        
                        # Atualiza os valores para o novo compasso
                        beats_per_measure = time_sig.numerator
                        beat_type = time_sig.denominator
                        beat_value = 4.0 / beat_type
                        measure_duration = beats_per_measure * beat_value
                
                # Parte que vai para o próximo compasso
                second_part_duration = duration - first_part_duration
                
                if second_part_duration > 0:
                    if midi_pitch > 0:  # Nota normal
                        n2 = m21.note.Note()
                        n2.pitch.midi = midi_pitch
                        n2.quarterLength = second_part_duration
                        n2.tie = m21.tie.Tie('stop')  # Finaliza a ligadura
                        # NOVO: Define a dinâmica na segunda parte também
                        if velocity_value > 0:
                            n2.volume.velocity = velocity_value
                        measure.append(n2)
                    else:  # Pausa
                        r2 = m21.note.Rest()
                        r2.quarterLength = second_part_duration
                        measure.append(r2)
                    
                    current_beat = second_part_duration
                else:
                    current_beat = 0
                
            # Verifica se o compasso atual está completo
            if abs(current_beat - measure_duration) < 0.001:  # Compara com uma pequena tolerância
                # Adiciona o compasso completo à parte
                part.append(measure)
                
                # Cria um novo compasso
                new_measure_number = len(part.getElementsByClass('Measure')) + 1
                measure = m21.stream.Measure(number=new_measure_number)
                
                # Verifica se deve mudar a fórmula de compasso para o próximo compasso
                if time_sig_sequence and new_measure_number <= len(time_sig_sequence):
                    current_time_sig_idx = new_measure_number - 1
                    if current_time_sig_idx < len(time_sig_sequence):
                        current_time_sig = time_sig_sequence[current_time_sig_idx]
                        time_sig = m21.meter.TimeSignature(current_time_sig)
                        measure.append(time_sig)
                        
                        # Atualiza os valores para o novo compasso
                        beats_per_measure = time_sig.numerator
                        beat_type = time_sig.denominator
                        beat_value = 4.0 / beat_type
                        measure_duration = beats_per_measure * beat_value
                
                # Reseta o contador de tempo
                current_beat = 0
            
            # Avança para a próxima nota/pausa
            i += 1
        
        # Adiciona o último compasso se não estiver vazio
        if len(measure) > 0:
            # Se o último compasso não estiver completo, adiciona uma pausa para completar
            if current_beat < measure_duration and abs(current_beat - measure_duration) > 0.001:
                r = m21.note.Rest()
                r.quarterLength = measure_duration - current_beat
                measure.append(r)
            
            part.append(measure)
        
        # Realiza ajustes finais na parte
        part.makeBeams(inPlace=True)
        part.makeTies(inPlace=True)
        
        # NOVO: Adicionamos marcações de dinâmica à partitura para torná-las visíveis
        self._add_dynamic_markings(part, velocity_sequence)

    def _add_dynamic_markings(self, part, velocity_sequence):
        """
        Adiciona marcações de dinâmica à partitura com base na sequência de velocities.
        Isso faz com que as dinâmicas sejam visíveis na partitura, não apenas no MIDI.
        """
        import music21 as m21
        
        if not velocity_sequence:
            return
        
        # Obtém todas as notas (ignorando pausas)
        notes = part.flatten().notesAndRests
        
        # Identifica pontos onde a dinâmica muda significativamente
        current_dynamic = None
        dynamic_idx = 0
        
        for i, element in enumerate(notes):
            if i >= len(velocity_sequence):
                break
                
            if isinstance(element, m21.note.Rest):
                continue
                
            velocity = velocity_sequence[dynamic_idx]
            dynamic_idx += 1
            
            # Obtém a marcação de dinâmica
            dynamic_str = self.velocity_processor.get_dynamic_name(velocity)
            
            # Se a dinâmica mudou ou é o início, adiciona uma marcação
            if dynamic_str != current_dynamic:
                if dynamic_str != "Silêncio":  # Não adiciona marcação para pausas
                    # Dinâmicas devem estar em minúsculas para music21
                    dynamic_mark = m21.dynamics.Dynamic(dynamic_str.lower())
                    
                    # Adiciona a marcação antes da nota
                    element.dynamic = dynamic_mark
                    
                    # Atualiza a dinâmica atual
                    current_dynamic = dynamic_str
    
    def set_dynamics_mode(self, mode, fixed_dynamic=None):
        """
        Define o modo de dinâmicas para a composição.
        
        Parâmetros:
        - mode: "pattern" (baseado em padrões), "contour" (seguindo o contorno melódico),
                ou "fixed" (valor constante)
        - fixed_dynamic: Quando no modo "fixed", especifica a dinâmica a ser usada
        """
        valid_modes = ["pattern", "contour", "fixed"]
        if mode not in valid_modes:
            print(f"Modo de dinâmica inválido. Usando 'pattern' como padrão.")
            mode = "pattern"
        
        self.dynamics_mode = mode
        
        if mode == "fixed" and fixed_dynamic:
            # Verifica se é uma dinâmica válida
            valid_dynamics = list(self.velocity_processor.dynamic_values.keys())
            if fixed_dynamic in valid_dynamics:
                self.fixed_dynamic = fixed_dynamic
            else:
                print(f"Dinâmica fixa inválida. Usando 'mf' como padrão.")
                self.fixed_dynamic = "mf"
        
        print(f"Modo de dinâmicas definido para '{mode}'")
        if mode == "fixed":
            print(f"Dinâmica fixa: {self.fixed_dynamic}")
        
        return True        

    def generate_time_signature_sequence(self, num_measures):
        """
        Gera uma sequência de fórmulas de compasso para os compassos,
        garantindo transições musicalmente coerentes.
        """
        if not self.use_variable_time_signatures or not self.variable_time_signatures:
            # Se não estiver usando fórmulas variáveis, retorna a fórmula fixa para todos os compassos
            return [self.time_signature] * num_measures
        
        # MELHORIA: Organiza os compassos por grupos para transições mais suaves
        simple_meters = ['2/4', '3/4', '4/4']  # Compassos simples
        compound_meters = ['6/8', '9/8', '12/8']  # Compassos compostos
        asymmetric_meters = ['5/4', '5/8', '7/8']  # Compassos assimétricos
        
        # Filtra apenas os tipos disponíveis
        available_simple = [m for m in simple_meters if m in self.variable_time_signatures]
        available_compound = [m for m in compound_meters if m in self.variable_time_signatures]
        available_asymmetric = [m for m in asymmetric_meters if m in self.variable_time_signatures]
        
        # Se algum grupo estiver vazio, adiciona o padrão
        if not available_simple:
            available_simple = ['4/4']
        if not available_compound:
            available_compound = ['6/8']
        if not available_asymmetric:
            available_asymmetric = ['5/4']
        
        # MELHORIA: Prefere manter o mesmo tipo de compasso por alguns compassos seguidos
        time_sig_sequence = []
        current_time_sig = random.choice(self.variable_time_signatures)
        
        # Define por quanto tempo manter um tipo de compasso antes de mudar para outro grupo
        min_sequence_length = 2  # Mínimo de compassos na mesma fórmula
        max_sequence_length = 8  # Máximo de compassos na mesma fórmula
        
        i = 0
        while i < num_measures:
            # Decide quantos compassos seguidos usar a mesma fórmula
            max_possible = min(max_sequence_length, num_measures - i)
            if max_possible <= min_sequence_length:
                sequence_length = max_possible  # Sem aleatoriedade se não há intervalo
            else:
                sequence_length = random.randint(min_sequence_length, max_possible)
            
            # Adiciona a fórmula atual por sequence_length compassos
            time_sig_sequence.extend([current_time_sig] * sequence_length)
            i += sequence_length
            
            # Decide se a próxima fórmula será do mesmo grupo ou diferente
            if random.random() < 0.7:  # 70% de chance de permanecer no mesmo grupo
                if current_time_sig in available_simple:
                    current_time_sig = random.choice(available_simple)
                elif current_time_sig in available_compound:
                    current_time_sig = random.choice(available_compound)
                elif current_time_sig in available_asymmetric:
                    current_time_sig = random.choice(available_asymmetric)
                else:
                    current_time_sig = random.choice(self.variable_time_signatures)
            else:
                # Muda para um grupo diferente
                if current_time_sig in available_simple:
                    current_time_sig = random.choice(available_compound + available_asymmetric)
                elif current_time_sig in available_compound:
                    current_time_sig = random.choice(available_simple + available_asymmetric)
                elif current_time_sig in available_asymmetric:
                    current_time_sig = random.choice(available_simple + available_compound)
                else:
                    current_time_sig = random.choice(self.variable_time_signatures)
        
        # Corta para o tamanho exato necessário
        return time_sig_sequence[:num_measures]
    
    def _get_time_signature_from_part(self, part):
        """
        Obtém a fórmula de compasso da parte musical.
        """
        time_signatures = part.getElementsByClass('TimeSignature')
        if time_signatures:
            return time_signatures[0]
        else:
            # Valor padrão 4/4
            return m21.meter.TimeSignature('4/4')
        
    def _ensure_tempo_in_all_parts(self, score):
        """
        Garante que todas as partes tenham a marcação de andamento correta e visível.
        Esta versão assegura que o andamento seja exibido como texto na partitura.
        """
        import music21 as m21
        import copy
        
        # Faz uma cópia da partitura para evitar modificar o original involuntariamente
        score_copy = copy.deepcopy(score)
        
        # Remover todas as marcas de andamento existentes primeiro para evitar duplicações
        for mm in score_copy.recurse().getElementsByClass('MetronomeMark'):
            mm.activeSite.remove(mm)
        
        # Criar uma nova marca de andamento usando o tempo definido
        # Importante: configurar displayText=True para aparecer na partitura
        mm = m21.tempo.MetronomeMark(
            number=self.tempo,
            text=f'♩={self.tempo}',  # Texto padrão com semínima
            displayText=True         # Garante que o texto seja exibido
        )
        
        # Adicionar a marca de andamento no início da partitura
        if len(score_copy.elements) > 0 and isinstance(score_copy.elements[0], m21.metadata.Metadata):
            # Se o primeiro elemento é metadados, insira após ele
            score_copy.insert(0.0, mm)
        else:
            # Caso contrário, insira no início
            score_copy.insert(0, mm)
        
        # Garantir que cada parte tenha a marca de andamento no início
        part_with_tempo = None
        for part_index, part in enumerate(score_copy.parts):
            # Apenas a primeira parte precisa mostrar o andamento para evitar duplicações visuais
            if part_index == 0:
                # Verificar se é um grupo de partes (como piano)
                if isinstance(part, m21.stream.PartStaff):
                    # Para grupos como piano, adicione à primeira sub-parte
                    sub_parts = part.getElementsByClass('Part')
                    if sub_parts:
                        first_sub_part = sub_parts[0]
                        
                        # Remover marcas existentes
                        for old_mm in first_sub_part.getElementsByClass('MetronomeMark'):
                            first_sub_part.remove(old_mm)
                        
                        # Adicionar nova marca de andamento com texto visível
                        new_mm = m21.tempo.MetronomeMark(
                            number=self.tempo,
                            text=f'♩={self.tempo}',
                            displayText=True
                        )
                        first_sub_part.insert(0, new_mm)
                        part_with_tempo = first_sub_part
                else:
                    # Para partes normais
                    # Remover marcas existentes
                    for old_mm in part.getElementsByClass('MetronomeMark'):
                        part.remove(old_mm)
                    
                    # Adicionar nova marca de andamento com texto visível
                    new_mm = m21.tempo.MetronomeMark(
                        number=self.tempo,
                        text=f'♩={self.tempo}',
                        displayText=True
                    )
                    part.insert(0, new_mm)
                    part_with_tempo = part
        
        # Verificar se conseguimos adicionar a marca de andamento a alguma parte
        if part_with_tempo is None and score_copy.parts:
            # Se nenhuma parte tem a marca de andamento ainda, adiciona à primeira parte disponível
            for part in score_copy.parts:
                if isinstance(part, m21.stream.Part):
                    part.insert(0, m21.tempo.MetronomeMark(
                        number=self.tempo,
                        text=f'♩={self.tempo}',
                        displayText=True
                    ))
                    break
                elif isinstance(part, m21.stream.PartStaff):
                    sub_parts = part.getElementsByClass('Part')
                    if sub_parts:
                        sub_parts[0].insert(0, m21.tempo.MetronomeMark(
                            number=self.tempo,
                            text=f'♩={self.tempo}',
                            displayText=True
                        ))
                        break
        
        return score_copy

    def set_tempo_with_expression(self, tempo, expression=None):
        """
        Define o andamento com uma expressão textual opcional.
        
        Parâmetros:
        - tempo: valor numérico do andamento (BPM)
        - expression: expressão opcional (ex: "Allegro", "Andante", etc.)
        """
        self.tempo = tempo
        
        # Mapear andamentos comuns para expressões italianas padrão
        if expression is None:
            if tempo <= 40:
                self.tempo_expression = "Largo"
            elif tempo <= 60:
                self.tempo_expression = "Adagio"
            elif tempo <= 76:
                self.tempo_expression = "Andante"
            elif tempo <= 108:
                self.tempo_expression = "Moderato"
            elif tempo <= 132:
                self.tempo_expression = "Allegro"
            elif tempo <= 168:
                self.tempo_expression = "Vivace"
            else:
                self.tempo_expression = "Presto"
        else:
            self.tempo_expression = expression
            
        return True        
        
    def save_composition(self, score, filename, formats=None):
        """
        Salva a composição em um ou mais formatos com tratamento de andamento melhorado.
        """
        # Importar os na função para garantir disponibilidade
        import os
        import music21 as m21
        
        try:
            if not self.output_folder:
                print("Pasta de saída não definida. Criando pasta de saída...")
                if not self.create_output_folder():
                    # Se a criação da pasta falhar, tenta criar no diretório atual
                    self.output_folder = os.path.join(os.getcwd(), "composicoes_geradas")
                    if not os.path.exists(self.output_folder):
                        os.makedirs(self.output_folder)
                    print(f"Pasta para composições criada: {self.output_folder}")

            # Verifica se a pasta de saída existe e tem permissões de escrita
            if not os.path.exists(self.output_folder):
                print(f"Pasta de saída não existe. Tentando criar: {self.output_folder}")
                os.makedirs(self.output_folder)
            
            if not os.access(self.output_folder, os.W_OK):
                alt_folder = os.path.join(os.path.expanduser("~"), "musica_gerada")
                print(f"Sem permissão de escrita em {self.output_folder}. Usando pasta alternativa: {alt_folder}")
                if not os.path.exists(alt_folder):
                    os.makedirs(alt_folder)
                self.output_folder = alt_folder

            # MODIFICAÇÃO: Antes de salvar, garantir que o andamento está definido em todas as partes
            # usando a versão corrigida do método
            fixed_score = self._ensure_tempo_in_all_parts(score)            
            
            if not formats:
                formats = ['midi', 'musicxml']
            
            base_path = os.path.join(self.output_folder, filename)
            saved_files = []
            
            print(f"\nSalvando composição '{fixed_score.metadata.title}' como {filename}...")
            
            # Preparar uma versão corrigida da partitura para MusicXML
            musicxml_score = None
            
            for fmt in formats:
                try:
                    if fmt.lower() == 'midi':
                        # MODIFICAÇÃO: Preparar uma versão específica para MIDI com andamento explícito
                        midi_score = fixed_score.deepcopy()
                        
                        # Forçar a inclusão do tempo em todos os eventos MIDI
                        for p in midi_score.parts:
                            tempo_mark = m21.tempo.MetronomeMark(number=self.tempo)
                            # Verificar se é um PartStaff (piano)
                            if isinstance(p, m21.stream.PartStaff):
                                for sub_part in p.getElementsByClass('Part'):
                                    # Limpar tempos existentes
                                    for old_mm in sub_part.getElementsByClass('MetronomeMark'):
                                        sub_part.remove(old_mm)
                                    # Adicionar novo tempo
                                    sub_part.insert(0, tempo_mark)
                            else:
                                # Limpar tempos existentes
                                for old_mm in p.getElementsByClass('MetronomeMark'):
                                    p.remove(old_mm)
                                # Adicionar novo tempo
                                p.insert(0, tempo_mark)
                        
                        output_path = f"{base_path}.mid"
                        midi_score.write('midi', fp=output_path)
                        saved_files.append(output_path)
                        print(f"✓ Arquivo MIDI salvo como: {output_path}")
                        
                    elif fmt.lower() in ['musicxml', 'xml']:
                        # Usa a versão corrigida da partitura para MusicXML
                        if musicxml_score is None:
                            musicxml_score = self._fix_score_for_export(fixed_score)
                        
                        output_path = f"{base_path}.musicxml"
                        musicxml_score.write('musicxml', fp=output_path)
                        saved_files.append(output_path)
                        print(f"✓ Arquivo MusicXML salvo como: {output_path}")
                        
                    elif fmt.lower() == 'mxl':
                        # Usa a versão corrigida da partitura para MXL também
                        if musicxml_score is None:
                            musicxml_score = self._fix_score_for_export(fixed_score)
                        
                        output_path = f"{base_path}.mxl"
                        musicxml_score.write('mxl', fp=output_path)
                        saved_files.append(output_path)
                        print(f"✓ Arquivo MusicXML compactado salvo como: {output_path}")
                        
                except Exception as e:
                    print(f"✗ Erro ao salvar no formato {fmt}: {e}")
                    print(f"  Detalhes: {str(e)}")
                    
                    # Tentativa alternativa - força a geração direta com streams básicos
                    try:
                        print(f"  Tentando abordagem alternativa para salvar em {fmt}...")
                        
                        # Cria uma nova partitura com apenas as informações essenciais
                        simple_score = m21.stream.Score()
                        
                        # Adiciona metadados
                        simple_score.insert(0, m21.metadata.Metadata())
                        simple_score.metadata.title = fixed_score.metadata.title
                        simple_score.metadata.composer = fixed_score.metadata.composer
                        
                        # MODIFICAÇÃO: Adiciona uma marca de andamento global ANTES de qualquer outra coisa
                        mm = m21.tempo.MetronomeMark(number=self.tempo)
                        simple_score.insert(0, mm)
                        
                        # Copia apenas as partes principais
                        for i, part in enumerate(fixed_score.parts):
                            # Cria uma nova parte
                            new_part = m21.stream.Part()
                            
                            # Adiciona clave, tonalidade e andamento
                            ts = m21.meter.TimeSignature(self.time_signature)
                            new_part.append(ts)
                            
                            ks = m21.key.Key(self.key_signature)
                            new_part.append(ks)
                            
                            # MODIFICAÇÃO: Adiciona marca de andamento explicitamente à primeira parte
                            if i == 0:
                                new_part.insert(0, m21.tempo.MetronomeMark(number=self.tempo))
                            
                            # Copia cada nota/pausa individualmente
                            for n in part.flatten().notesAndRests:
                                if isinstance(n, m21.note.Note):
                                    new_note = m21.note.Note(n.pitch)
                                    new_note.quarterLength = n.quarterLength
                                    new_part.append(new_note)
                                else:
                                    new_rest = m21.note.Rest()
                                    new_rest.quarterLength = n.quarterLength
                                    new_part.append(new_rest)
                            
                            simple_score.append(new_part)
                        
                        # Tenta salvar a versão simplificada
                        if fmt.lower() == 'midi':
                            output_path = f"{base_path}_simple.mid"
                            simple_score.write('midi', fp=output_path)
                            saved_files.append(output_path)
                            print(f"✓ Arquivo MIDI simplificado salvo como: {output_path}")
                        elif fmt.lower() in ['musicxml', 'xml']:
                            output_path = f"{base_path}_simple.musicxml"
                            simple_score.write('musicxml', fp=output_path)
                            saved_files.append(output_path)
                            print(f"✓ Arquivo MusicXML simplificado salvo como: {output_path}")
                    except Exception as e2:
                        print(f"  ✗ Também falhou a abordagem alternativa: {e2}")
            
            if saved_files:
                # Copiar o arquivo de configuração para referência
                try:
                    config_path = os.path.join(self.output_folder, f"{filename}_config.txt")
                    with open(config_path, 'w', encoding='utf-8') as f:
                        f.write(f"Composição: {fixed_score.metadata.title}\n")
                        f.write(f"Estilo: {self.current_style}\n")
                        f.write(f"Comprimento: {self.composition_length} eventos\n")
                        f.write(f"Tonalidade: {self.key_signature}\n")
                        f.write(f"Compasso: {self.time_signature}\n")
                        f.write(f"Andamento: {self.tempo} BPM\n\n")  # MODIFICAÇÃO: Destaque para o andamento
                        f.write("Pesos dos algoritmos:\n")
                        f.write(f"- N-grams: {self.ngram_weight:.2f}\n")
                        f.write(f"- Sequitur: {self.sequitur_weight:.2f}\n")
                        f.write(f"- SIATEC: {self.siatec_weight:.2f}\n")
                        
                        # Informações adicionais úteis
                        f.write("\nObservações técnicas:\n")
                        f.write(f"- Total de partes: {len(fixed_score.parts)}\n")
                        
                        # Coletar nomes de instrumentos com segurança
                        instruments = []
                        for instrument in fixed_score.flatten().getElementsByClass('Instrument'):
                            if hasattr(instrument, 'partName') and instrument.partName:
                                instruments.append(instrument.partName)
                            else:
                                instruments.append(type(instrument).__name__)
                        
                        f.write(f"- Instrumentos: {', '.join(instruments)}\n")
                        
                    print(f"✓ Arquivo de configuração salvo como: {config_path}")
                    saved_files.append(config_path)
                except Exception as e:
                    print(f"✗ Erro ao salvar arquivo de configuração: {e}")
            
            if not saved_files:
                print("⚠ Nenhum arquivo foi salvo com sucesso.")
            else:
                print(f"✓ Total de {len(saved_files)} arquivo(s) salvo(s) com sucesso.")
            
            return saved_files
            
        except Exception as e:
            print(f"Erro crítico ao salvar composição: {e}")
            # Tenta uma abordagem minimalista como último recurso
            try:
                import os
                # Cria um diretório temporário no diretório home do usuário
                temp_dir = os.path.join(os.path.expanduser("~"), "temp_music")
                if not os.path.exists(temp_dir):
                    os.makedirs(temp_dir)
                    
                # Cria uma partitura extremamente simples
                s = m21.stream.Score()
                p = m21.stream.Part()
                
                # MODIFICAÇÃO: Adiciona o andamento no início
                mm = m21.tempo.MetronomeMark(number=self.tempo)
                s.insert(0, mm)
                p.insert(0, mm)
                
                # Adiciona algumas notas básicas
                for pitch in [60, 62, 64, 65]:
                    n = m21.note.Note(pitch)
                    n.quarterLength = 1.0
                    p.append(n)
                    
                s.append(p)
                
                # Tenta salvar
                output_path = os.path.join(temp_dir, f"{filename}_emergency.mid")
                s.write('midi', fp=output_path)
                print(f"✓ Arquivo de emergência salvo como: {output_path}")
                return [output_path]
            except Exception as e2:
                print(f"Falha na tentativa de emergência: {e2}")
                return []
    
    def generate_batch(self, num_compositions=5, styles=None):
        """
        Gera várias composições com diferentes configurações.
        """
        if not styles:
            styles = list(self.composition_templates.keys())
        
        compositions = []
        
        for i in range(num_compositions):
            # Seleciona um estilo aleatório da lista de estilos
            style = random.choice(styles)
            
            # Cria um título para a composição
            title = f"Composição {style.title()} #{i+1}"
            
            # Gera a composição
            score = self.generate_composition(title=title, style=style)
            
            if score:
                # Salva a composição
                filename = f"{style}_comp_{i+1}"
                saved_files = self.save_composition(score, filename)
                
                compositions.append({
                    'title': title,
                    'style': style,
                    'files': saved_files,
                    'score': score
                })
        
        return compositions
    
    def set_composition_params(self, length=None, time_sig=None, key=None, tempo=None):
        """
        Configura os parâmetros básicos da composição.
        """
        if length is not None and length > 0:
            self.composition_length = length
        
        if time_sig is not None:
            self.time_signature = time_sig
        
        if key is not None:
            self.key_signature = key
        
        if tempo is not None and tempo > 0:
            self.tempo = tempo
        
        print("Parâmetros de composição atualizados:")
        print(f"- Comprimento: {self.composition_length} eventos")
        print(f"- Fórmula de compasso: {self.time_signature}")
        print(f"- Tonalidade: {self.key_signature}")
        print(f"- Andamento: {self.tempo} BPM")
    
    def add_custom_template(self, name, min_pitch, max_pitch, rhythm_complexity):
        """
        Adiciona um template personalizado para composição.
        """
        if not name or not isinstance(name, str):
            print("Nome de template inválido.")
            return False
        
        self.composition_templates[name.lower()] = {
            "min_pitch": min_pitch,
            "max_pitch": max_pitch,
            "rhythm_complexity": rhythm_complexity
        }
        
        print(f"Template '{name}' adicionado com sucesso.")
        return True
    
    def display_templates(self):
        """
        Exibe os templates disponíveis.
        """
        print("Templates de composição disponíveis:")
        for name, params in self.composition_templates.items():
            print(f"- {name.title()}:")
            print(f"  * Intervalo de alturas: {params['min_pitch']} - {params['max_pitch']} (MIDI)")
            print(f"  * Complexidade rítmica: {params['rhythm_complexity']:.2f}")
            print()
    
    def set_algorithm_weights(self, ngram=None, sequitur=None, siatec=None):
        """
        Configura os pesos dos algoritmos na geração.
        """
        if ngram is not None:
            self.ngram_weight = max(0.0, min(1.0, ngram))
        
        if sequitur is not None:
            self.sequitur_weight = max(0.0, min(1.0, sequitur))
        
        if siatec is not None:
            self.siatec_weight = max(0.0, min(1.0, siatec))
        
        # Normaliza os pesos
        total = self.ngram_weight + self.sequitur_weight + self.siatec_weight
        if total > 0:
            self.ngram_weight /= total
            self.sequitur_weight /= total
            self.siatec_weight /= total
        
        print("Pesos dos algoritmos atualizados:")
        print(f"- N-grams: {self.ngram_weight:.2f}")
        print(f"- Sequitur: {self.sequitur_weight:.2f}")
        print(f"- SIATEC: {self.siatec_weight:.2f}")
    
    def preview_composition(self, score):
        """
        Mostra uma prévia da composição (versão texto).
        """
        if not score:
            print("Partitura não disponível para preview.")
            return
        
        print(f"Título: {score.metadata.title}")
        print(f"Compositor: {score.metadata.composer}")
        print("-" * 40)
        
        # Obtém a primeira parte
        if score.parts:
            part = score.parts[0]
            
            # Mostra informações básicas
            ts = part.getElementsByClass('TimeSignature')[0] if part.getElementsByClass('TimeSignature') else "4/4"
            ks = part.getElementsByClass('KeySignature')[0].asKey() if part.getElementsByClass('KeySignature') else "C"
            print(f"Compasso: {ts}")
            print(f"Tonalidade: {ks}")
            
            # Mostra os primeiros compassos
            for i, measure in enumerate(part.getElementsByClass('Measure')[:5]):
                print(f"Compasso {measure.number}:", end=" ")
                notes = []
                for element in measure.elements:
                    if isinstance(element, m21.note.Note):
                        notes.append(f"{element.nameWithOctave}({element.quarterLength})")
                    elif isinstance(element, m21.note.Rest):
                        notes.append(f"R({element.quarterLength})")
                print(" ".join(notes))
            
            if len(part.getElementsByClass('Measure')) > 5:
                print("...")
        
        print("-" * 40)
        print(f"Total de compassos: {len(score.parts[0].getElementsByClass('Measure'))}")

    def _fix_score_for_export(self, score):
        """
        Corrige problemas comuns com a partitura antes da exportação para MusicXML,
        garantindo que o andamento seja exibido com expressão.
        """
        import copy
        import music21 as m21
        
        # Cria uma cópia profunda da partitura para não modificar a original
        fixed_score = copy.deepcopy(score)
        
        # Para cada parte na partitura
        for part in fixed_score.parts:
            # Processa cada compasso na parte
            for measure in part.getElementsByClass('Measure'):
                # Corrige as notas e pausas no compasso
                for note_or_rest in measure.notesAndRests:
                    # Corrige durações problemáticas
                    if note_or_rest.duration.quarterLength not in [0.0625, 0.125, 0.25, 0.5, 0.75, 1.0, 1.5, 2.0, 3.0, 4.0]:
                        # Encontra a duração válida mais próxima
                        valid_durations = [0.0625, 0.125, 0.25, 0.5, 0.75, 1.0, 1.5, 2.0, 3.0, 4.0]
                        closest_duration = min(valid_durations, key=lambda x: abs(x - note_or_rest.duration.quarterLength))
                        print(f"Ajustando duração de {note_or_rest.duration.quarterLength} para {closest_duration}")
                        note_or_rest.duration.quarterLength = closest_duration
                    
                    # Corrige beam problems (problemas com hastes de colcheias/semicolcheias)
                    if hasattr(note_or_rest, 'beams') and note_or_rest.beams:
                        # Limpa todos os beams e deixa o music21 recalcular
                        note_or_rest.beams = None
        
        # Recalcula métricas (incluindo beams) da partitura inteira
        for part in fixed_score.parts:
            part.makeBeams(inPlace=True)
            part.makeAccidentals(inPlace=True)
            part.makeTies(inPlace=True)
        
        # Limpa marcas de andamento existentes para evitar duplicações
        for mm in fixed_score.flatten().getElementsByClass('MetronomeMark'):
            mm.activeSite.remove(mm)
        
        # Define a expressão de andamento se não estiver definida
        if not hasattr(self, 'tempo_expression'):
            self.set_tempo_with_expression(self.tempo)
        
        # Adicionar uma nova marca de andamento na primeira parte com a expressão textual
        tempo_text = f"{self.tempo_expression} (♩={self.tempo})"
        
        # Adiciona uma única marca de andamento global no início da partitura
        tempo_mark = m21.tempo.MetronomeMark(number=self.tempo, text=tempo_text, displayText=True)
        fixed_score.insert(0, tempo_mark)
        
        # Adiciona o andamento explicitamente apenas à primeira parte
        first_part = None
        
        for i, part in enumerate(fixed_score.parts):
            if i == 0:
                # Para o primeiro elemento da partitura
                if isinstance(part, m21.stream.PartStaff):
                    # Se for um piano ou outro instrumento com múltiplas pautas
                    sub_parts = part.getElementsByClass('Part')
                    if sub_parts:
                        first_part = sub_parts[0]
                        first_part.insert(0, m21.tempo.MetronomeMark(number=self.tempo, text=tempo_text, displayText=True))
                else:
                    # Para instrumentos normais
                    first_part = part
                    first_part.insert(0, m21.tempo.MetronomeMark(number=self.tempo, text=tempo_text, displayText=True))
        
        return fixed_score

    def _find_musescore_path(self):
        """
        Verifica se o MuseScore está instalado e retorna o caminho para o executável.
        
        Retorna:
        - Caminho para o executável do MuseScore ou None se não for encontrado
        """
        import os
        import platform
        import subprocess
        
        # Lista de possíveis comandos/caminhos do MuseScore
        musescore_commands = []
        
        system = platform.system()
        if system == "Linux":
            # Comandos para Linux
            musescore_commands = [
                "musescore", "mscore", "musescore3", "musescore4", 
                "mscore3", "mscore4",
                "/usr/bin/musescore", "/usr/bin/mscore",
                "/usr/bin/musescore3", "/usr/bin/musescore4",
                "/usr/local/bin/musescore", "/usr/local/bin/mscore",
                "/snap/bin/musescore"
            ]
        elif system == "Windows":
            # Caminhos para Windows
            musescore_commands = [
                r"C:\Program Files\MuseScore 3\bin\MuseScore3.exe",
                r"C:\Program Files\MuseScore 4\bin\MuseScore4.exe",
                r"C:\Program Files (x86)\MuseScore 3\bin\MuseScore3.exe",
                r"C:\Program Files (x86)\MuseScore 4\bin\MuseScore4.exe",
                r"C:\Program Files\MuseScore\bin\MuseScore.exe"
            ]
        elif system == "Darwin":  # macOS
            # Caminhos para macOS
            musescore_commands = [
                "/Applications/MuseScore 3.app/Contents/MacOS/mscore",
                "/Applications/MuseScore 4.app/Contents/MacOS/mscore",
                "/Applications/MuseScore.app/Contents/MacOS/mscore"
            ]
        
        # Tenta shutil.which — funciona em Linux, macOS E Windows
        import shutil as _shutil
        for name in ["musescore", "mscore", "musescore3", "musescore4", "MuseScore"]:
            found = _shutil.which(name)
            if found:
                return found

        # Verifica caminhos absolutos
        for cmd in musescore_commands:
            # Para comandos simples sem caminho absoluto, usa shutil.which
            if not os.path.isabs(cmd):
                found = _shutil.which(cmd.split()[0])
                if found:
                    return found
                continue
            
            # Para caminhos absolutos, verifica se o arquivo existe
            elif os.path.exists(cmd):
                return cmd
        
        # Se chegou aqui, não encontrou o MuseScore
        return None
        
    def _check_and_install_musescore(self):
        """
        Verifica se o MuseScore está instalado e oferece instruções para instalação se necessário.
        
        Retorna:
        - True se o MuseScore estiver instalado ou se o usuário optar por continuar sem ele
        - False se o usuário cancelar a operação
        """
        from tkinter import messagebox
        import platform
        import subprocess
        
        # Verifica se o MuseScore está instalado
        musescore_path = self._find_musescore_path()
        if musescore_path:
            print(f"MuseScore encontrado em: {musescore_path}")
            return True
        
        # Se não encontrou, mostra mensagem com instruções de instalação
        system = platform.system()
        
        message = "O MuseScore não foi encontrado no sistema. "
        
        if system == "Linux":
            message += "Para instalar no Ubuntu/Debian, execute no terminal:\n\n"
            message += "sudo apt install musescore3\n\n"
            message += "Ou via Flatpak:\n\n"
            message += "flatpak install flathub org.musescore.MuseScore"
        elif system == "Windows":
            message += "Por favor, baixe e instale o MuseScore em:\n\n"
            message += "https://musescore.org"
        elif system == "Darwin":  # macOS
            message += "Por favor, baixe e instale o MuseScore em:\n\n"
            message += "https://musescore.org\n\n"
            message += "Ou via Homebrew:\n\n"
            message += "brew install --cask musescore"
        
        # Pergunta se deseja abrir o site para download ou continuar sem o MuseScore
        if messagebox.askyesno("MuseScore não encontrado", 
                            message + "\n\nDeseja abrir o site para download?"):
            try:
                # Abre o site do MuseScore
                url = "https://musescore.org/download"
                
                if system == "Windows":
                    subprocess.Popen(["start", url], shell=True)
                elif system == "Darwin":  # macOS
                    subprocess.Popen(["open", url])
                else:  # Linux e outros
                    subprocess.Popen(["xdg-open", url])
                
                # Pergunta se deseja continuar sem o MuseScore
                return messagebox.askyesno("Continuar", 
                                        "Deseja continuar usando o programa sem o MuseScore?\n"
                                        "(Os arquivos serão salvos, mas você precisará abri-los manualmente)")
            except:
                # Se falhar ao abrir o navegador, pergunta se deseja continuar sem o MuseScore
                return messagebox.askyesno("Continuar", 
                                        "Não foi possível abrir o navegador. Visite musescore.org para baixar.\n\n"
                                        "Deseja continuar usando o programa sem o MuseScore?")
        else:
            # Se não quiser abrir o site, pergunta se deseja continuar sem o MuseScore
            return messagebox.askyesno("Continuar", 
                                    "Deseja continuar usando o programa sem o MuseScore?\n"
                                    "(Os arquivos serão salvos, mas você precisará abri-los manualmente)")
    
    def open_in_musescore(self, file_path):
        """
        Tenta abrir o arquivo no MuseScore, com suporte melhorado para Ubuntu e outros sistemas.
        Inclui múltiplas abordagens alternativas para garantir que o arquivo seja aberto.
        """
        import subprocess
        import platform
        import os
        import time
        
        if not os.path.exists(file_path):
            print(f"Arquivo não encontrado: {file_path}")
            return False
        
        print(f"Tentando abrir arquivo no MuseScore: {file_path}")
        
        # Verifica se o arquivo é acessível e tem tamanho > 0
        try:
            file_size = os.path.getsize(file_path)
            if file_size == 0:
                print(f"Aviso: O arquivo {file_path} está vazio (0 bytes).")
        except Exception as e:
            print(f"Aviso ao verificar arquivo: {e}")
        
        # Múltiplas tentativas com diferentes abordagens
        success = False
        approaches_tried = []
        
        # Abordagem 1: Usar music21 diretamente
        if file_path.endswith('.musicxml') or file_path.endswith('.xml') or file_path.endswith('.mxl'):
            approaches_tried.append("music21.show()")
            try:
                print("Tentativa 1: Usando music21.show()")
                score = m21.converter.parse(file_path)
                score.show()
                time.sleep(1)  # Pequena pausa para iniciar o processo
                success = True
                print("Partitura aberta com sucesso via music21.")
                return True
            except Exception as e:
                print(f"Tentativa 1 falhou: {e}")
        
        # Abordagem 2: Usar o sistema específico da plataforma
        system = platform.system()
        approaches_tried.append(f"Sistema específico ({system})")
        
        try:
            print(f"Tentativa 2: Usando comandos específicos do sistema {system}")
            if system == "Linux":  # Linux (incluindo Ubuntu)
                # Lista de possíveis comandos do MuseScore no Linux
                musescore_commands = [
                    "musescore", "mscore", "musescore3", "musescore4", 
                    "mscore3", "mscore4", "flatpak run org.musescore.MuseScore"
                ]
                
                # Tenta cada comando
                for cmd in musescore_commands:
                    try:
                        # Se for comando flatpak, precisa tratar diferente
                        if cmd.startswith("flatpak"):
                            cmd_parts = cmd.split()
                            cmd_parts.append(file_path)
                            process = subprocess.Popen(cmd_parts)
                        else:
                            # Verifica se o comando existe usando 'which'
                            import shutil as _sh
                            which_path = _sh.which(cmd.split()[0])
                            which_result = type('R', (), {
                                'returncode': 0 if which_path else 1,
                                'stdout': (which_path or '') + '\n'
                            })()
                            
                            if which_result.returncode == 0 and which_result.stdout.strip():
                                cmd_path = which_result.stdout.strip()
                                print(f"Encontrado MuseScore em: {cmd_path}")
                                
                                # Executa o comando
                                process = subprocess.Popen([cmd_path, file_path])
                                time.sleep(1)  # Pequena pausa
                                
                                if process.poll() is None:  # Se ainda estiver rodando
                                    print(f"MuseScore iniciado com o comando: {cmd_path}")
                                    success = True
                                    return True
                    except Exception as cmd_error:
                        print(f"  Erro com o comando {cmd}: {cmd_error}")
                
                # Se nenhum comando funcionou, tenta caminhos absolutos comuns
                if not success:
                    linux_paths = [
                        "/usr/bin/musescore", "/usr/bin/mscore",
                        "/usr/bin/musescore3", "/usr/bin/musescore4",
                        "/usr/local/bin/musescore", "/usr/local/bin/mscore",
                        "/snap/bin/musescore", "/var/lib/flatpak/exports/bin/org.musescore.MuseScore"
                    ]
                    
                    for path in linux_paths:
                        if os.path.exists(path) and os.access(path, os.X_OK):
                            try:
                                print(f"Tentando caminho absoluto: {path}")
                                process = subprocess.Popen([path, file_path])
                                time.sleep(1)
                                
                                if process.poll() is None:  # Se ainda estiver rodando
                                    print(f"MuseScore iniciado com o caminho: {path}")
                                    success = True
                                    return True
                            except Exception as path_error:
                                print(f"  Erro com o caminho {path}: {path_error}")
                
                # Como último recurso, tenta xdg-open
                if not success:
                    approaches_tried.append("xdg-open")
                    try:
                        print("Tentando abrir com xdg-open...")
                        subprocess.Popen(["xdg-open", file_path])
                        time.sleep(1)
                        print("Arquivo aberto com xdg-open")
                        return True
                    except Exception as e:
                        print(f"  Erro ao abrir com xdg-open: {e}")
            
            elif system == "Windows":
                approaches_tried.append("Windows paths")
                # Caminhos comuns do MuseScore no Windows
                musescore_paths = [
                    r"C:\Program Files\MuseScore 3\bin\MuseScore3.exe",
                    r"C:\Program Files\MuseScore 4\bin\MuseScore4.exe",
                    r"C:\Program Files (x86)\MuseScore 3\bin\MuseScore3.exe",
                    r"C:\Program Files (x86)\MuseScore 4\bin\MuseScore4.exe",
                    r"C:\Program Files\MuseScore\bin\MuseScore.exe"
                ]
                
                for ms_path in musescore_paths:
                    if os.path.exists(ms_path):
                        try:
                            print(f"Tentando caminho Windows: {ms_path}")
                            subprocess.Popen([ms_path, file_path])
                            time.sleep(1)
                            print(f"MuseScore iniciado com o caminho: {ms_path}")
                            success = True
                            return True
                        except Exception as path_error:
                            print(f"  Erro com o caminho {ms_path}: {path_error}")
                
                # Se não encontrou, tenta abrir com o aplicativo padrão
                if not success:
                    approaches_tried.append("Windows startfile")
                    try:
                        print("Tentando abrir com o aplicativo padrão do Windows...")
                        os.startfile(file_path)
                        print("Arquivo aberto com o aplicativo padrão do Windows")
                        return True
                    except Exception as e:
                        print(f"  Erro ao abrir com o aplicativo padrão: {e}")
            
            elif system == "Darwin":  # macOS
                approaches_tried.append("macOS paths")
                # Caminhos comuns do MuseScore no macOS
                musescore_paths = [
                    "/Applications/MuseScore 3.app/Contents/MacOS/mscore",
                    "/Applications/MuseScore 4.app/Contents/MacOS/mscore",
                    "/Applications/MuseScore.app/Contents/MacOS/mscore"
                ]
                
                for ms_path in musescore_paths:
                    if os.path.exists(ms_path):
                        try:
                            print(f"Tentando caminho macOS: {ms_path}")
                            subprocess.Popen([ms_path, file_path])
                            time.sleep(1)
                            print(f"MuseScore iniciado com o caminho: {ms_path}")
                            success = True
                            return True
                        except Exception as path_error:
                            print(f"  Erro com o caminho {ms_path}: {path_error}")
                
                # Se não encontrar, usa o comando 'open' do macOS
                if not success:
                    approaches_tried.append("macOS open")
                    try:
                        print("Tentando abrir com o comando 'open' do macOS...")
                        subprocess.Popen(["open", file_path])
                        print("Arquivo aberto com o comando 'open' do macOS")
                        return True
                    except Exception as e:
                        print(f"  Erro ao abrir com o comando 'open': {e}")
        
        except Exception as platform_error:
            print(f"Erro ao tentar métodos específicos da plataforma: {platform_error}")
        
        # Abordagem 3: Última tentativa - abrir qualquer aplicativo de música ou visualizador PDF
        if not success:
            approaches_tried.append("Generic alternatives")
            try:
                print("Tentativa 3: Buscando aplicativos alternativos...")
                
                # Lista de aplicativos possíveis
                alternative_apps = []
                
                if system == "Linux":
                    alternative_apps = ["audacity", "vlc", "totem", "evince", "firefox", "chromium-browser", "xdg-open"]
                elif system == "Windows":
                    # No Windows, vamos tentar primeiro o tipo de arquivo
                    try:
                        print("Tentando abrir pelo tipo de arquivo no Windows...")
                        os.startfile(file_path)
                        return True
                    except:
                        # Se falhar, continuamos com alternativas
                        pass
                    
                    # Programas alternativos no Windows
                    alternative_apps = [
                        r"C:\Program Files\VideoLAN\VLC\vlc.exe",
                        r"C:\Program Files (x86)\VideoLAN\VLC\vlc.exe",
                        r"C:\Program Files\Windows Media Player\wmplayer.exe"
                    ]
                elif system == "Darwin":  # macOS
                    alternative_apps = ["open", "/Applications/Audacity.app/Contents/MacOS/Audacity"]
                
                for app in alternative_apps:
                    try:
                        print(f"Tentando aplicativo alternativo: {app}")
                        subprocess.Popen([app, file_path])
                        time.sleep(1)
                        print(f"Arquivo aberto com: {app}")
                        return True
                    except Exception as app_error:
                        print(f"  Erro com o aplicativo {app}: {app_error}")
                        
            except Exception as alt_error:
                print(f"Erro ao tentar aplicativos alternativos: {alt_error}")
        
        # Se chegamos aqui, todas as tentativas falharam
        if not success:
            print(f"\nNão foi possível abrir o arquivo automaticamente. Tentativas realizadas: {', '.join(approaches_tried)}")
            print(f"\nO arquivo foi salvo em: {file_path}")
            print("\nVocê pode abrir o arquivo manualmente com um dos seguintes métodos:")
            print("- Instalando o MuseScore (https://musescore.org)")
            print("- Abrindo o arquivo diretamente no MuseScore após a instalação")
            print("- Usando outro visualizador de partitura ou player MIDI")
            
            if system == "Linux":
                print("\nPara instalar o MuseScore no Ubuntu/Debian: sudo apt install musescore3")
                print("Ou com Flatpak: flatpak install flathub org.musescore.MuseScore")
            
            return False
        
        return success

# --------------------------------------------------
# Interface gráfica para o compositor
# --------------------------------------------------

class ComposerGUI:
    """
    Interface gráfica para o Gerador de Gramática Composicional.
    """
    def __init__(self, master):
        self.master = master
        self.master.title("Compositor por Gramática Generativa")
        self.master.geometry("800x600")
        self.master.minsize(700, 500)
        
        self.composer = GenerativeGrammarComposer()
        self._apply_composer_fixes()
        self.current_composition = None
        self.compositions = []  # Lista para armazenar as composições geradas

        # Adicione após criar o compositor:
        # Certifique-se de que pelo menos o piano está ativo inicialmente
        if not self.composer.active_instruments:
            self.composer.set_active_instruments_with_doubles({"piano_direita": 1, "piano_esquerda": 1})        
        
        # Verificar se o MuseScore está instalado
        self.musescore_available = self.composer._find_musescore_path() is not None
        if not self.musescore_available:
            print("Aviso: MuseScore não foi encontrado no sistema.")
            # Não exibimos a mensagem aqui para não bloquear a inicialização
            # Será verificado apenas quando o usuário tentar abrir uma composição
        
        # Variáveis para instrumentos
        self.instrument_vars = {}
        
        self._create_ui()
    
    def _create_ui(self):
        """
        Cria a interface gráfica.
        """
        # Painel principal com abas
        self.notebook = ttk.Notebook(self.master)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Aba 1: Geração
        self.tab_generator = ttk.Frame(self.notebook)
        self.notebook.add(self.tab_generator, text="Gerador")
        
        # Aba 2: Instrumentos (NOVA)
        self.tab_instruments = ttk.Frame(self.notebook)
        self.notebook.add(self.tab_instruments, text="Instrumentos")
        
        # Aba 3: Configurações
        self.tab_settings = ttk.Frame(self.notebook)
        self.notebook.add(self.tab_settings, text="Configurações")
        
        # Aba 4: Ajuda
        self.tab_help = ttk.Frame(self.notebook)
        self.notebook.add(self.tab_help, text="Ajuda")
        
        # Aba 5: Composições
        self.tab_compositions = ttk.Frame(self.notebook)
        self.notebook.add(self.tab_compositions, text="Composições")
        
        # Configurar conteúdo das abas
        self._setup_generator_tab()
        self._setup_instruments_tab()  # NOVA
        self._setup_settings_tab()
        self._setup_help_tab()
        self._setup_compositions_tab()

        # Aba de Notação Contemporânea (Abjad) — carregada opcionalmente
        try:
            from gui_abjad_tab import AbjadTab
            self.abjad_tab = AbjadTab(self)
        except ImportError:
            pass  # Abjad não instalado — aba omitida sem erro

    def _setup_generator_tab(self):
        """
        Configura a aba do gerador com controles de andamento e número de compassos.
        Inclui opções para expressões de andamento.
        """
        # Frame superior: seleção de pastas e carregamento
        frame_top = ttk.LabelFrame(self.tab_generator, text="Carregar Dados")
        frame_top.pack(fill=tk.X, padx=10, pady=5)
        
        ttk.Button(frame_top, text="Selecionar Pasta de Análise", 
                command=self._select_analysis_folder).pack(side=tk.LEFT, padx=5, pady=5)
        
        self.lbl_folder = ttk.Label(frame_top, text="Nenhuma pasta selecionada")
        self.lbl_folder.pack(side=tk.LEFT, padx=5, pady=5, fill=tk.X, expand=True)
        
        ttk.Button(frame_top, text="Carregar Dados", 
                command=self._load_analysis_data).pack(side=tk.LEFT, padx=5, pady=5)
        
        # Frame do meio: parâmetros de composição
        frame_middle = ttk.LabelFrame(self.tab_generator, text="Parâmetros de Composição")
        frame_middle.pack(fill=tk.X, padx=10, pady=5)
        
        # Título
        ttk.Label(frame_middle, text="Título:").grid(row=0, column=0, padx=5, pady=5, sticky=tk.W)
        self.entry_title = ttk.Entry(frame_middle, width=30)
        self.entry_title.insert(0, "Composição Gerada")
        self.entry_title.grid(row=0, column=1, padx=5, pady=5, sticky=tk.W)
        
        # Estilo
        ttk.Label(frame_middle, text="Estilo:").grid(row=1, column=0, padx=5, pady=5, sticky=tk.W)
        self.combo_style = ttk.Combobox(frame_middle, values=list(self.composer.composition_templates.keys()))
        self.combo_style.current(2)  # "balanced" como padrão
        self.combo_style.grid(row=1, column=1, padx=5, pady=5, sticky=tk.W)
        
        # Frame para controles de andamento
        tempo_frame = ttk.Frame(frame_middle)
        tempo_frame.grid(row=2, column=0, columnspan=2, padx=5, pady=5, sticky=tk.W)
        
        # Andamento (BPM)
        ttk.Label(tempo_frame, text="Andamento (BPM):").grid(row=0, column=0, padx=5, pady=5, sticky=tk.W)
        self.spin_tempo = ttk.Spinbox(tempo_frame, from_=40, to=220, increment=4, width=5)
        self.spin_tempo.insert(0, str(self.composer.tempo))
        self.spin_tempo.grid(row=0, column=1, padx=5, pady=5, sticky=tk.W)
        
        # Expressão de Andamento
        ttk.Label(tempo_frame, text="Expressão:").grid(row=0, column=2, padx=(15,5), pady=5, sticky=tk.W)
        tempo_expressions = ["Auto", "Largo", "Adagio", "Andante", "Moderato", "Allegro", "Vivace", "Presto"]
        self.combo_tempo_expression = ttk.Combobox(tempo_frame, values=tempo_expressions, width=10)
        self.combo_tempo_expression.current(0)  # "Auto" como padrão
        self.combo_tempo_expression.grid(row=0, column=3, padx=5, pady=5, sticky=tk.W)
        
        # Função para atualizar a expressão de andamento automaticamente quando o valor BPM muda
        def update_tempo_expression(*args):
            try:
                if self.combo_tempo_expression.get() == "Auto":
                    bpm = int(self.spin_tempo.get())
                    if bpm <= 40:
                        self.lbl_tempo_desc.config(text="(Muito lento)")
                    elif bpm <= 60:
                        self.lbl_tempo_desc.config(text="(Lento)")
                    elif bpm <= 76:
                        self.lbl_tempo_desc.config(text="(Moderadamente lento)")
                    elif bpm <= 108:
                        self.lbl_tempo_desc.config(text="(Moderado)")
                    elif bpm <= 132:
                        self.lbl_tempo_desc.config(text="(Rápido)")
                    elif bpm <= 168:
                        self.lbl_tempo_desc.config(text="(Muito rápido)")
                    else:
                        self.lbl_tempo_desc.config(text="(Extremamente rápido)")
            except:
                self.lbl_tempo_desc.config(text="")
        
        # Descrição do andamento
        self.lbl_tempo_desc = ttk.Label(tempo_frame, text="(Moderado)")
        self.lbl_tempo_desc.grid(row=0, column=4, padx=5, pady=5, sticky=tk.W)
        
        # Vincula a função de atualização à spinbox de andamento
        self.spin_tempo.bind("<KeyRelease>", update_tempo_expression)
        self.spin_tempo.bind("<ButtonRelease-1>", update_tempo_expression)
        
        # Atualiza a descrição inicialmente
        update_tempo_expression()
        
        # MODIFICADO: Comprimento - agora com descrição mais intuitiva 
        ttk.Label(frame_middle, text="Eventos/Compassos:").grid(row=3, column=0, padx=5, pady=5, sticky=tk.W)
        
        # Frame para controles de comprimento
        length_frame = ttk.Frame(frame_middle)
        length_frame.grid(row=3, column=1, padx=5, pady=5, sticky=tk.W)
        
        self.spin_length = ttk.Spinbox(length_frame, from_=8, to=256, increment=4, width=5)
        self.spin_length.insert(0, str(self.composer.composition_length))
        self.spin_length.pack(side=tk.LEFT, padx=0, pady=0)
        
        # NOVO: Radio buttons para escolher entre eventos ou compassos
        self.length_type = tk.StringVar(value="events")
        ttk.Radiobutton(length_frame, text="Eventos", 
                        variable=self.length_type, 
                        value="events").pack(side=tk.LEFT, padx=(10,5), pady=0)
        ttk.Radiobutton(length_frame, text="Compassos", 
                        variable=self.length_type, 
                        value="measures").pack(side=tk.LEFT, padx=5, pady=0)
        
        # Botões de geração
        frame_buttons = ttk.Frame(frame_middle)
        frame_buttons.grid(row=4, column=0, columnspan=2, pady=10)
        
        ttk.Button(frame_buttons, text="Gerar Composição", 
                command=self._generate_composition).pack(side=tk.LEFT, padx=5)
        
        ttk.Button(frame_buttons, text="Gerar Lote", 
                command=self._generate_batch).pack(side=tk.LEFT, padx=5)
        
        # Frame inferior: log e preview
        frame_bottom = ttk.LabelFrame(self.tab_generator, text="Preview")
        frame_bottom.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        self.preview_text = ScrolledText(frame_bottom, wrap=tk.WORD, height=10)
        self.preview_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Frame de ações
        frame_actions = ttk.Frame(self.tab_generator)
        frame_actions.pack(fill=tk.X, padx=10, pady=5)
        
        ttk.Button(frame_actions, text="Salvar Partitura", 
                command=self._save_current_composition).pack(side=tk.LEFT, padx=5, pady=5)
        
        ttk.Button(frame_actions, text="Abrir no MuseScore", 
                command=self._open_in_musescore).pack(side=tk.LEFT, padx=5, pady=5)
    
    def _setup_settings_tab(self):
        """
        Configura a aba de configurações.
        """
        # Frame para pesos dos algoritmos
        frame_weights = ttk.LabelFrame(self.tab_settings, text="Pesos dos Algoritmos")
        frame_weights.pack(fill=tk.X, padx=10, pady=5)
        
        # N-grams
        ttk.Label(frame_weights, text="N-grams:").grid(row=0, column=0, padx=5, pady=5, sticky=tk.W)
        self.scale_ngram = ttk.Scale(frame_weights, from_=0, to=1, value=self.composer.ngram_weight, length=200)
        self.scale_ngram.grid(row=0, column=1, padx=5, pady=5)
        self.lbl_ngram = ttk.Label(frame_weights, text=f"{self.composer.ngram_weight:.2f}")
        self.lbl_ngram.grid(row=0, column=2, padx=5, pady=5)
        self.scale_ngram.configure(command=lambda v: self.lbl_ngram.configure(
            text=f"{float(v):.2f}"))
        
        # Sequitur
        ttk.Label(frame_weights, text="Sequitur:").grid(row=1, column=0, padx=5, pady=5, sticky=tk.W)
        self.scale_sequitur = ttk.Scale(frame_weights, from_=0, to=1, value=self.composer.sequitur_weight, length=200)
        self.scale_sequitur.grid(row=1, column=1, padx=5, pady=5)
        self.lbl_sequitur = ttk.Label(frame_weights, text=f"{self.composer.sequitur_weight:.2f}")
        self.lbl_sequitur.grid(row=1, column=2, padx=5, pady=5)
        self.scale_sequitur.configure(command=lambda v: self.lbl_sequitur.configure(
            text=f"{float(v):.2f}"))
        
        # SIATEC
        ttk.Label(frame_weights, text="SIATEC:").grid(row=2, column=0, padx=5, pady=5, sticky=tk.W)
        self.scale_siatec = ttk.Scale(frame_weights, from_=0, to=1, value=self.composer.siatec_weight, length=200)
        self.scale_siatec.grid(row=2, column=1, padx=5, pady=5)
        self.lbl_siatec = ttk.Label(frame_weights, text=f"{self.composer.siatec_weight:.2f}")
        self.lbl_siatec.grid(row=2, column=2, padx=5, pady=5)
        self.scale_siatec.configure(command=lambda v: self.lbl_siatec.configure(
            text=f"{float(v):.2f}"))
        
        ttk.Button(frame_weights, text="Aplicar Pesos", 
                   command=self._apply_weights).grid(row=3, column=1, padx=5, pady=10)
        
        # Frame para parâmetros de composição
        frame_params = ttk.LabelFrame(self.tab_settings, text="Parâmetros de Composição")
        frame_params.pack(fill=tk.X, padx=10, pady=5)
        
        # Tonalidade
        ttk.Label(frame_params, text="Tonalidade:").grid(row=0, column=0, padx=5, pady=5, sticky=tk.W)
        keys = ['C', 'G', 'D', 'A', 'E', 'B', 'F#', 'Db', 'Ab', 'Eb', 'Bb', 'F', 
                'Am', 'Em', 'Bm', 'F#m', 'C#m', 'G#m', 'Ebm', 'Bbm', 'Fm', 'Cm', 'Gm', 'Dm']
        self.combo_key = ttk.Combobox(frame_params, values=keys, width=5)
        self.combo_key.current(keys.index(self.composer.key_signature))
        self.combo_key.grid(row=0, column=1, padx=5, pady=5, sticky=tk.W)
        
        # Fórmula de compasso
        ttk.Label(frame_params, text="Compasso:").grid(row=1, column=0, padx=5, pady=5, sticky=tk.W)
        time_sigs = ['4/4', '3/4', '3/8', '2/4', '6/8', '9/8', '12/8', '5/4', '5/8', '7/8']
        self.combo_time_sig = ttk.Combobox(frame_params, values=time_sigs, width=5)
        self.combo_time_sig.current(time_sigs.index(self.composer.time_signature))
        self.combo_time_sig.grid(row=1, column=1, padx=5, pady=5, sticky=tk.W)

        # Adicionar este novo frame após frame_params
        frame_time_sig = ttk.LabelFrame(self.tab_settings, text="Configuração de Fórmulas de Compasso")
        frame_time_sig.pack(fill=tk.X, padx=10, pady=5)
        
        # Checkbox para habilitar fórmulas variáveis
        self.use_variable_ts = tk.BooleanVar(value=False)
        ttk.Checkbutton(frame_time_sig, text="Usar fórmulas de compasso variáveis",
                    variable=self.use_variable_ts).grid(row=0, column=0, columnspan=2, padx=5, pady=5, sticky=tk.W)
        
        # Lista de fórmulas disponíveis
        ttk.Label(frame_time_sig, text="Fórmulas disponíveis:").grid(row=1, column=0, padx=5, pady=5, sticky=tk.W)
        
        # Frame para os checkboxes de fórmulas
        ts_check_frame = ttk.Frame(frame_time_sig)
        ts_check_frame.grid(row=1, column=1, padx=5, pady=5, sticky=tk.W)
        
        # Todas as fórmulas disponíveis para seleção
        all_time_sigs = ['4/4', '3/4', '3/8', '2/4', '6/8', '9/8', '12/8', '5/4', '5/8', '7/8']
        self.ts_vars = {}
        
        # Cria checkboxes para cada fórmula
        for i, ts in enumerate(all_time_sigs):
            self.ts_vars[ts] = tk.BooleanVar(value=True if ts in self.composer.variable_time_signatures else False)
            ttk.Checkbutton(ts_check_frame, text=ts, variable=self.ts_vars[ts]).grid(
                row=i // 4, column=i % 4, padx=5, pady=2, sticky=tk.W)
        
        # Probabilidade de mudança
        ttk.Label(frame_time_sig, text="Probabilidade de mudança:").grid(row=2, column=0, padx=5, pady=5, sticky=tk.W)
        
        self.scale_ts_change = ttk.Scale(frame_time_sig, from_=0.0, to=1.0, value=0.2, length=200)
        self.scale_ts_change.grid(row=2, column=1, padx=5, pady=5, sticky=tk.W)
        self.lbl_ts_change = ttk.Label(frame_time_sig, text="0.20")
        self.lbl_ts_change.grid(row=2, column=2, padx=5, pady=5)
        self.scale_ts_change.configure(command=lambda v: self.lbl_ts_change.configure(
            text=f"{float(v):.2f}"))
        
        ttk.Button(frame_time_sig, text="Aplicar Configuração",
                command=self._apply_time_sig_config).grid(row=3, column=1, padx=5, pady=10)

        
        # Tempo (BPM)
        ttk.Label(frame_params, text="Tempo (BPM):").grid(row=2, column=0, padx=5, pady=5, sticky=tk.W)
        self.spin_tempo = ttk.Spinbox(frame_params, from_=40, to=200, increment=4, width=5)
        self.spin_tempo.insert(0, str(self.composer.tempo))
        self.spin_tempo.grid(row=2, column=1, padx=5, pady=5, sticky=tk.W)
        
        ttk.Button(frame_params, text="Aplicar Parâmetros", 
                   command=self._apply_params).grid(row=3, column=1, padx=5, pady=10)
        
        # Frame para templates
        frame_templates = ttk.LabelFrame(self.tab_settings, text="Templates de Composição")
        frame_templates.pack(fill=tk.X, padx=10, pady=5)
        
        self.tree_templates = ttk.Treeview(frame_templates, columns=("min", "max", "complexity"), 
                                           show="headings", height=4)
        self.tree_templates.heading("min", text="Pitch Mín")
        self.tree_templates.heading("max", text="Pitch Máx")
        self.tree_templates.heading("complexity", text="Complexidade")
        self.tree_templates.column("min", width=80)
        self.tree_templates.column("max", width=80)
        self.tree_templates.column("complexity", width=100)
        self.tree_templates.pack(fill=tk.X, padx=5, pady=5)
        
        # Preenche a árvore de templates
        self._update_template_tree()

    def _apply_time_sig_config(self):
        """
        Aplica as configurações de fórmula de compasso.
        """
        try:
            # Verifica se fórmulas variáveis estão ativadas
            use_variable = self.use_variable_ts.get()
            
            # Coleta as fórmulas selecionadas
            time_signatures = []
            for ts, var in self.ts_vars.items():
                if var.get():
                    time_signatures.append(ts)
            
            # Se nenhuma fórmula foi selecionada, usa a padrão
            if not time_signatures:
                time_signatures = ['4/4']
            
            # Obtém a probabilidade de mudança
            change_probability = float(self.scale_ts_change.get())
            
            # Aplica ao compositor
            self.composer.set_time_signature_options(
                use_variable=use_variable,
                time_signatures=time_signatures,
                change_probability=change_probability
            )
            
            self.log_message("Configuração de fórmulas de compasso aplicada.")
            
        except Exception as e:
            messagebox.showerror("Erro", f"Falha ao aplicar configuração de fórmulas de compasso: {e}")        
    
    def _setup_help_tab(self):
        """
        Configura a aba de ajuda.
        """
        help_text = """
        # Compositor por Gramática Generativa
        
        Esta aplicação gera composições musicais baseadas em padrões extraídos da análise de arquivos MIDI.
        
        ## Como usar:
        
        1. Na aba 'Gerador', selecione a pasta onde estão os resultados da análise prévia dos arquivos MIDI
        2. Clique em 'Carregar Dados' para processar os padrões encontrados
        3. Na aba 'Instrumentos', selecione quais instrumentos deseja incluir na composição
        4. Configure os parâmetros da composição desejada
        5. Clique em 'Gerar Composição' para criar uma nova peça musical
        6. Use 'Salvar Partitura' para exportar em formato MusicXML ou MIDI
        7. Use 'Abrir no MuseScore' para visualizar a partitura gerada
        
        ## Parâmetros principais:
        
        - **Título**: Nome da composição gerada
        - **Estilo**: Template predefinido que afeta características da composição
        - **Comprimento**: Número de eventos musicais (notas ou pausas) a serem gerados
        - **Instrumentos**: Seleção de instrumentos orquestrais a incluir na partitura
        
        ## Estilos disponíveis:
        
        - **Melodic**: Focado em padrões melódicos fluidos
        - **Rhythmic**: Ênfase em variações rítmicas
        - **Balanced**: Equilíbrio entre melodia e ritmo
        - **Experimental**: Combinações mais incomuns e variadas
        
        ## Configurações avançadas:
        
        Na aba 'Configurações', você pode ajustar:
        - Pesos dos diferentes algoritmos (N-grams, Sequitur, SIATEC)
        - Parâmetros musicais (tonalidade, compasso, andamento)
        - Templates de composição personalizados
        
        ## Sobre os algoritmos:
        
        - **N-grams**: Identifica sequências curtas e frequentes
        - **Sequitur**: Descobre padrões hierárquicos e regras gramaticais
        - **SIATEC**: Encontra padrões que se repetem em diferentes posições
        
        O compositor combina esses padrões para gerar material musical original seguindo as estruturas identificadas no corpus analisado, aplicando-os a diferentes instrumentos orquestrais.
        """
        
        text_help = ScrolledText(self.tab_help, wrap=tk.WORD)
        text_help.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        text_help.insert(tk.END, help_text)
        text_help.configure(state="disabled")

    def _setup_instruments_tab(self):
        """
        Configura a aba de seleção de instrumentos com suporte a múltiplas instâncias.
        """
        # Frame com lista de instrumentos disponíveis
        frame_instruments = ttk.LabelFrame(self.tab_instruments, text="Instrumentos Disponíveis")
        frame_instruments.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        # Cria um frame com scrollbar
        instruments_frame = ttk.Frame(frame_instruments)
        instruments_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Scrollbar
        scrollbar = ttk.Scrollbar(instruments_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Canvas para conter os controles
        canvas = tk.Canvas(instruments_frame, yscrollcommand=scrollbar.set)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        scrollbar.config(command=canvas.yview)
        
        # Frame interno para os controles
        inner_frame = ttk.Frame(canvas)
        canvas.create_window((0, 0), window=inner_frame, anchor='nw')
        
        # Variáveis para os spinboxes de quantidade
        self.instrument_vars = {}
        
        # Organiza instrumentos por famílias (inclui percussão)
        instrument_families = {
            "Madeiras": [
                "flauta", "flauta_piccolo", "oboé", "corne_inglês",
                "clarinete", "clarinete_baixo", "fagote", "contrafagote",
            ],
            "Metais": [
                "trompa", "trompete", "trombone", "trombone_baixo", "tuba",
            ],
            "Cordas": [
                "violino", "viola", "violoncelo", "contrabaixo",
            ],
            "Teclado": [
                "piano_direita", "piano_esquerda", "cravo",
            ],
            "Percussão — Altura Definida": [
                "marimba", "vibrafone", "xilofone", "glockenspiel",
                "crotales", "timpano",
            ],
            "Percussão — Caixa / Bumbo": [
                "caixa", "caixa_abafada", "rim_shot",
                "bumbo", "bumbo_acustico",
            ],
            "Percussão — Tom-Tons": [
                "tom_agudo", "tom_medio_agudo", "tom_medio_grave", "tom_grave",
                "floor_tom_agudo", "floor_tom_grave",
            ],
            "Percussão — Hi-Hat": [
                "hihat_fechado", "hihat_aberto",
                "hihat_pedal", "hihat_meio_aberto",
            ],
            "Percussão — Pratos": [
                "prato_crash", "prato_ride", "prato_ride_bell",
                "prato_china", "prato_splash", "prato_suspenso",
            ],
            "Percussão — Orquestral": [
                "triangulo", "triangulo_abafado",
                "woodblock_agudo", "woodblock_grave",
                "tamborim", "cowbell", "claves", "maracas",
                "tantã", "gongo", "pratos_a_2",
            ],
            "Bateria": [
                "bateria",
            ],
            "Vozes": [
                "soprano", "mezzo", "contralto",
                "tenor", "barítono", "baixo_voz",
            ],
        }

        # Nomes de exibição personalizados
        display_names_override = {
            "piano_direita":    "Piano (mão direita)",
            "piano_esquerda":   "Piano (mão esquerda)",
            "flauta_piccolo":   "Flauta Piccolo",
            "corne_inglês":     "Corne Inglês",
            "clarinete_baixo":  "Clarinete Baixo",
            "contrafagote":     "Contrafagote",
            "trombone_baixo":   "Trombone Baixo",
            "caixa_abafada":    "Caixa Abafada",
            "rim_shot":         "Rim Shot",
            "bumbo_acustico":   "Bumbo Acústico",
            "tom_agudo":        "Tom Agudo",
            "tom_medio_agudo":  "Tom Médio-Agudo",
            "tom_medio_grave":  "Tom Médio-Grave",
            "tom_grave":        "Tom Grave",
            "floor_tom_agudo":  "Floor Tom Agudo",
            "floor_tom_grave":  "Floor Tom Grave",
            "hihat_fechado":    "Hi-Hat Fechado",
            "hihat_aberto":     "Hi-Hat Aberto",
            "hihat_pedal":      "Hi-Hat Pedal",
            "hihat_meio_aberto":"Hi-Hat Meio-Aberto",
            "prato_crash":      "Prato Crash",
            "prato_ride":       "Prato Ride",
            "prato_ride_bell":  "Ride Bell",
            "prato_china":      "Prato China",
            "prato_splash":     "Prato Splash",
            "prato_suspenso":   "Prato Suspenso",
            "triangulo":        "Triângulo",
            "triangulo_abafado":"Triângulo Abafado",
            "woodblock_agudo":  "Woodblock Agudo",
            "woodblock_grave":  "Woodblock Grave",
            "pratos_a_2":       "Pratos a 2",
            "baixo_voz":        "Baixo",
        }

        # Instrumentos que não fazem sentido ter múltiplas instâncias
        max_one = {"piano_direita", "piano_esquerda", "cravo",
                   "bateria", "maracas", "claves"}

        row = 0
        # Cria seções por família
        for family, instruments in instrument_families.items():
            ttk.Label(inner_frame, text=family, font=("", 10, "bold")).grid(
                row=row, column=0, columnspan=2, sticky=tk.W,
                padx=5, pady=(10, 2))
            row += 1

            for instrument in instruments:
                display_name = display_names_override.get(
                    instrument, instrument.replace("_", " ").title()
                )

                ttk.Label(inner_frame, text=display_name).grid(
                    row=row, column=0, padx=(20, 5), pady=1, sticky=tk.W)

                self.instrument_vars[instrument] = tk.IntVar(value=0)

                spinbox = ttk.Spinbox(
                    inner_frame, from_=0, to=8, width=3,
                    textvariable=self.instrument_vars[instrument]
                )
                spinbox.grid(row=row, column=1, padx=5, pady=1, sticky=tk.W)

                if instrument in max_one:
                    spinbox.config(from_=0, to=1)

                row += 1

        # Configura o canvas para rolagem
        inner_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        
        # Botões de ação
        action_frame = ttk.Frame(self.tab_instruments)
        action_frame.pack(fill=tk.X, padx=10, pady=5)
        
        ttk.Button(action_frame, text="Zerar Tudo", 
                command=self._reset_all_instruments).pack(side=tk.LEFT, padx=5, pady=5)
        
        ttk.Button(action_frame, text="Configuração Solo", 
                command=self._set_solo_configuration).pack(side=tk.LEFT, padx=5, pady=5)
        
        ttk.Button(action_frame, text="Orquestra de Câmara", 
                command=self._set_chamber_orchestra).pack(side=tk.LEFT, padx=5, pady=5)
        
        ttk.Button(action_frame, text="Orquestra Completa",
                command=self._set_full_orchestra).pack(side=tk.LEFT, padx=5, pady=5)

        ttk.Button(action_frame, text="Ensemble Percussão",
                command=self._set_percussion_ensemble).pack(side=tk.LEFT, padx=5, pady=5)

        ttk.Button(action_frame, text="Aplicar Seleção",
                command=self._apply_instrument_selection).pack(side=tk.RIGHT, padx=5, pady=5)
        
        # Frame para mostrar instrumentos ativos
        active_frame = ttk.LabelFrame(self.tab_instruments, text="Instrumentos Ativos")
        active_frame.pack(fill=tk.X, padx=10, pady=5)
        
        self.active_instruments_text = ttk.Label(active_frame, text="Nenhum instrumento selecionado")
        self.active_instruments_text.pack(fill=tk.X, padx=5, pady=5)

        # NOVO: Adiciona seção para controle de dinâmicas
        dynamics_frame = ttk.LabelFrame(self.tab_instruments, text="Configuração de Dinâmicas")
        dynamics_frame.pack(fill=tk.X, padx=10, pady=5)
        
        # Modo de dinâmicas
        ttk.Label(dynamics_frame, text="Modo de dinâmicas:").grid(row=0, column=0, padx=5, pady=5, sticky=tk.W)
        self.dynamics_mode = tk.StringVar(value="pattern")
        dynamics_modes = [
            ("Baseado em Padrões", "pattern"),
            ("Seguindo Contorno Melódico", "contour"),
            ("Dinâmica Fixa", "fixed")
        ]
        
        modes_frame = ttk.Frame(dynamics_frame)
        modes_frame.grid(row=0, column=1, padx=5, pady=5, sticky=tk.W)
        
        for i, (text, mode) in enumerate(dynamics_modes):
            ttk.Radiobutton(modes_frame, text=text, variable=self.dynamics_mode, 
                          value=mode, command=self._update_dynamic_controls).grid(
                row=0, column=i, padx=10, pady=2, sticky=tk.W)
        
        # Seleção de dinâmica fixa (inicialmente desabilitada)
        self.fixed_dynamic_frame = ttk.Frame(dynamics_frame)
        self.fixed_dynamic_frame.grid(row=1, column=0, columnspan=2, padx=5, pady=5, sticky=tk.W)
        
        ttk.Label(self.fixed_dynamic_frame, text="Dinâmica fixa:").pack(side=tk.LEFT, padx=5)
        self.fixed_dynamic = tk.StringVar(value="mf")
        dynamics_options = ["ppp", "pp", "p", "mp", "mf", "f", "ff", "fff"]
        self.combo_fixed_dynamic = ttk.Combobox(self.fixed_dynamic_frame, 
                                              values=dynamics_options,
                                              textvariable=self.fixed_dynamic,
                                              width=5)
        self.combo_fixed_dynamic.current(4)  # "mf" como padrão
        self.combo_fixed_dynamic.pack(side=tk.LEFT, padx=5)
        
        # Botão para aplicar configurações de dinâmica
        ttk.Button(dynamics_frame, text="Aplicar Configurações de Dinâmica", 
                 command=self._apply_dynamics_settings).grid(
            row=2, column=0, columnspan=2, padx=5, pady=10)
        
        # Inicializa o estado dos controles
        self._update_dynamic_controls()        

    def _update_dynamic_controls(self):
        """
        Atualiza o estado dos controles de dinâmica com base no modo selecionado.
        """
        mode = self.dynamics_mode.get()
        
        if mode == "fixed":
            # Habilita controles de dinâmica fixa
            for child in self.fixed_dynamic_frame.winfo_children():
                child.configure(state="normal")
        else:
            # Desabilita controles de dinâmica fixa
            for child in self.fixed_dynamic_frame.winfo_children():
                if isinstance(child, ttk.Combobox):
                    child.configure(state="disabled")
    
    def _apply_dynamics_settings(self):
        """
        Aplica as configurações de dinâmica ao compositor.
        """
        try:
            mode = self.dynamics_mode.get()
            fixed_dynamic = self.fixed_dynamic.get() if mode == "fixed" else None
            
            if self.composer.set_dynamics_mode(mode, fixed_dynamic):
                self.log_message(f"Configurações de dinâmica aplicadas: modo '{mode}'")
                if mode == "fixed":
                    self.log_message(f"Dinâmica fixa: {fixed_dynamic}")
            else:
                self.log_message("Falha ao aplicar configurações de dinâmica.")
        except Exception as e:
            self.log_message(f"Erro ao aplicar configurações de dinâmica: {e}")
            messagebox.showerror("Erro", f"Falha ao aplicar configurações de dinâmica: {e}")        

    def _reset_all_instruments(self):
        """
        Zera a quantidade de todos os instrumentos.
        """
        for var in self.instrument_vars.values():
            var.set(0)

    def _set_solo_configuration(self):
        """
        Configura para um instrumento solo com piano.
        """
        # Primeiro zera tudo
        self._reset_all_instruments()
        
        # Configura para um instrumento solo com piano
        # Escolhe aleatoriamente um instrumento solo
        solo_options = [
            "flauta", "oboé", "clarinete", "fagote",  # Madeiras
            "violino", "viola", "violoncelo"          # Cordas
        ]
        solo_instrument = random.choice(solo_options)
        
        # Define o instrumento solo e o piano
        if solo_instrument in self.instrument_vars:
            self.instrument_vars[solo_instrument].set(1)
        
        self.instrument_vars["piano_direita"].set(1)
        self.instrument_vars["piano_esquerda"].set(1)

    def _set_chamber_orchestra(self):
        """
        Configura para uma orquestra de câmara típica.
        """
        # Primeiro zera tudo
        self._reset_all_instruments()
        
        # Configuração de orquestra de câmara
        chamber_config = {
            "flauta": 1, "oboé": 1, "clarinete": 1, "fagote": 1,  # Madeiras (1 de cada)
            "trompa": 2, "trompete": 1,                           # Metais (2 trompas, 1 trompete)
            "violino": 6, "viola": 2, "violoncelo": 2, "contrabaixo": 1  # Cordas
        }
        
        # Aplica a configuração
        for inst, count in chamber_config.items():
            if inst in self.instrument_vars:
                self.instrument_vars[inst].set(count)

    def _set_full_orchestra(self):
        """
        Configura para uma orquestra sinfônica completa.
        """
        self._reset_all_instruments()
        orchestra_config = {
            # Madeiras
            "flauta": 2, "flauta_piccolo": 1, "oboé": 2, "corne_inglês": 1,
            "clarinete": 2, "fagote": 2, "contrafagote": 1,
            # Metais
            "trompa": 4, "trompete": 2, "trombone": 3, "tuba": 1,
            # Cordas
            "violino": 16, "viola": 12, "violoncelo": 10, "contrabaixo": 8,
            # Percussão orquestral
            "timpano": 1, "caixa": 1, "prato_suspenso": 1, "pratos_a_2": 1,
            "triangulo": 1, "xilofone": 1, "vibrafone": 1, "marimba": 1,
        }
        for inst, count in orchestra_config.items():
            if inst in self.instrument_vars:
                self.instrument_vars[inst].set(count)

    def _set_percussion_ensemble(self):
        """
        Configura para um ensemble de percussão misto.
        Inclui instrumentos de altura definida e indefinida.
        """
        self._reset_all_instruments()
        perc_config = {
            # Altura definida
            "marimba": 1, "vibrafone": 1, "xilofone": 1,
            "timpano": 1, "crotales": 1,
            # Membranofones
            "caixa": 1, "bumbo": 1,
            "tom_agudo": 1, "tom_medio_agudo": 1,
            "tom_medio_grave": 1, "tom_grave": 1,
            # Idiofones
            "triangulo": 1, "woodblock_agudo": 1, "woodblock_grave": 1,
            "prato_suspenso": 1, "pratos_a_2": 1,
            "tamborim": 1, "cowbell": 1,
        }
        for inst, count in perc_config.items():
            if inst in self.instrument_vars:
                self.instrument_vars[inst].set(count)

    def _apply_composer_fixes(self):
        """
        Aplica as correções necessárias aos métodos da classe GenerativeGrammarComposer.
        Substitui os métodos problemáticos com implementações melhoradas.
        """
        import types
        
        # Definição das funções corrigidas aqui para garantir que estejam no escopo
        # Correção para o método _create_score_from_sequences
        def _create_score_from_sequences(self_composer, part, rhythm_sequence, pitch_sequence, velocity_sequence=None, time_sig_sequence=None):
            """
            Cria uma partitura a partir das sequências de ritmo, altura e opcionalmente dinâmica (velocity),
            com opção para fórmulas de compasso variáveis.
            Garante que as notas sejam corretamente distribuídas dentro dos limites de cada compasso.
            """
            import music21 as m21
            
            # Garante que as sequências tenham o mesmo tamanho
            length = min(len(rhythm_sequence), len(pitch_sequence))
            
            # Se não tiver velocities, cria uma sequência padrão
            if not velocity_sequence or len(velocity_sequence) < length:
                velocity_sequence = [64] * length  # 64 = mezzo-forte (padrão)
            
            # Inicializa com a primeira fórmula de compasso
            current_time_sig_idx = 0
            current_time_sig = self_composer.time_signature
            if time_sig_sequence and len(time_sig_sequence) > 0:
                current_time_sig = time_sig_sequence[0]
            
            time_sig = m21.meter.TimeSignature(current_time_sig)
            part.append(time_sig)
            
            # Contador para manter o registro do progresso pelo compasso
            current_beat = 0
            measure = m21.stream.Measure(number=1)
            
            # Obtém o número de tempos por compasso da fórmula atual
            beats_per_measure = time_sig.numerator
            beat_type = time_sig.denominator
            
            # Ajusta a duração por batida com base no tipo de compasso
            # Ex: Em 4/4, um tempo = 1.0, em 3/8, um tempo = 0.5
            beat_value = 4.0 / beat_type
            
            # Total de duração esperado em um compasso (em quarter lengths)
            measure_duration = beats_per_measure * beat_value
            
            i = 0
            while i < length:
                duration = rhythm_sequence[i]
                midi_pitch = pitch_sequence[i]
                velocity_value = velocity_sequence[i]  # Agora usamos o valor de velocity
                
                # Arredonda a duração para um valor válido para MusicXML
                valid_durations = [0.0625, 0.125, 0.25, 0.5, 0.75, 1.0, 1.5, 2.0, 3.0, 4.0]
                closest_duration = min(valid_durations, key=lambda x: abs(x - duration))
                duration = closest_duration
                
                # Verifica se a nota cabe no compasso atual
                remaining_measure_duration = measure_duration - current_beat
                
                if duration <= remaining_measure_duration:
                    # A nota cabe integralmente no compasso atual
                    if midi_pitch > 0:  # Nota normal
                        n = m21.note.Note()
                        n.pitch.midi = midi_pitch
                        n.quarterLength = duration
                        # Configura a velocity (dinâmica)
                        if velocity_value > 0:
                            n.volume.velocity = velocity_value
                    else:  # Pausa (midi_pitch <= 0 ou quando encontra 'Rest')
                        n = m21.note.Rest()
                        n.quarterLength = duration
                    
                    # Adiciona a nota/pausa ao compasso atual
                    measure.append(n)
                    current_beat += duration
                    
                else:
                    # A nota não cabe integralmente no compasso atual,
                    # precisamos dividir entre o compasso atual e o próximo
                    
                    # Parte que cabe no compasso atual
                    first_part_duration = remaining_measure_duration
                    
                    if first_part_duration > 0:
                        if midi_pitch > 0:  # Nota normal
                            n1 = m21.note.Note()
                            n1.pitch.midi = midi_pitch
                            n1.quarterLength = first_part_duration
                            n1.tie = m21.tie.Tie('start')  # Inicia uma ligadura
                            # Configura a velocity (dinâmica)
                            if velocity_value > 0:
                                n1.volume.velocity = velocity_value
                            measure.append(n1)
                        else:  # Pausa
                            r1 = m21.note.Rest()
                            r1.quarterLength = first_part_duration
                            measure.append(r1)
                    
                    # Adiciona o compasso atual à parte
                    part.append(measure)
                    
                    # Cria um novo compasso
                    new_measure_number = len(part.getElementsByClass('Measure')) + 1
                    measure = m21.stream.Measure(number=new_measure_number)
                    
                    # Verifica se deve mudar a fórmula de compasso para o próximo compasso
                    if time_sig_sequence and new_measure_number <= len(time_sig_sequence):
                        current_time_sig_idx = new_measure_number - 1
                        if current_time_sig_idx < len(time_sig_sequence):
                            current_time_sig = time_sig_sequence[current_time_sig_idx]
                            time_sig = m21.meter.TimeSignature(current_time_sig)
                            measure.append(time_sig)
                            
                            # Atualiza os valores para o novo compasso
                            beats_per_measure = time_sig.numerator
                            beat_type = time_sig.denominator
                            beat_value = 4.0 / beat_type
                            measure_duration = beats_per_measure * beat_value
                    
                    # Parte que vai para o próximo compasso
                    second_part_duration = duration - first_part_duration
                    
                    if second_part_duration > 0:
                        if midi_pitch > 0:  # Nota normal
                            n2 = m21.note.Note()
                            n2.pitch.midi = midi_pitch
                            n2.quarterLength = second_part_duration
                            n2.tie = m21.tie.Tie('stop')  # Finaliza a ligadura
                            # Configura a velocity (dinâmica) também na segunda parte
                            if velocity_value > 0:
                                n2.volume.velocity = velocity_value
                            measure.append(n2)
                        else:  # Pausa
                            r2 = m21.note.Rest()
                            r2.quarterLength = second_part_duration
                            measure.append(r2)
                        
                        current_beat = second_part_duration
                    else:
                        current_beat = 0
                    
                # Verifica se o compasso atual está completo
                if abs(current_beat - measure_duration) < 0.001:  # Compara com uma pequena tolerância
                    # Adiciona o compasso completo à parte
                    part.append(measure)
                    
                    # Cria um novo compasso
                    new_measure_number = len(part.getElementsByClass('Measure')) + 1
                    measure = m21.stream.Measure(number=new_measure_number)
                    
                    # Verifica se deve mudar a fórmula de compasso para o próximo compasso
                    if time_sig_sequence and new_measure_number <= len(time_sig_sequence):
                        current_time_sig_idx = new_measure_number - 1
                        if current_time_sig_idx < len(time_sig_sequence):
                            current_time_sig = time_sig_sequence[current_time_sig_idx]
                            time_sig = m21.meter.TimeSignature(current_time_sig)
                            measure.append(time_sig)
                            
                            # Atualiza os valores para o novo compasso
                            beats_per_measure = time_sig.numerator
                            beat_type = time_sig.denominator
                            beat_value = 4.0 / beat_type
                            measure_duration = beats_per_measure * beat_value
                    
                    # Reseta o contador de tempo
                    current_beat = 0
                
                # Avança para a próxima nota/pausa
                i += 1
            
            # Adiciona o último compasso se não estiver vazio
            if len(measure) > 0:
                # Se o último compasso não estiver completo, adiciona uma pausa para completar
                if current_beat < measure_duration and abs(current_beat - measure_duration) > 0.001:
                    r = m21.note.Rest()
                    r.quarterLength = measure_duration - current_beat
                    measure.append(r)
                
                part.append(measure)
            
            # Realiza ajustes finais na parte
            part.makeBeams(inPlace=True)
            part.makeTies(inPlace=True)

        # Correção para o método get_instrument_for_part
        def get_instrument_for_part(self_composer, inst_id):
            """
            Obtém o objeto de instrumento para uma parte específica, incluindo
            suporte para múltiplas instâncias do mesmo instrumento.
            
            Parâmetros:
            - inst_id: identificador do instrumento (pode incluir sufixo numérico)
            
            Retorna:
            - Objeto de instrumento music21 e suas configurações
            """
            # CORREÇÃO: Melhor tratamento para extrair o nome base do instrumento
            if "_" in inst_id:
                parts = inst_id.split('_')
                # Verifica se é um formato tipo 'flauta_1' ou 'piano_direita_1'
                if parts[0] == "piano" and len(parts) > 1:
                    if parts[1] in ["direita", "esquerda"]:
                        base_name = f"piano_{parts[1]}"
                    else:
                        # Formato alternativo como 'piano_1_direita'
                        hand = "direita" if parts[-1] == "direita" else "esquerda" 
                        base_name = f"piano_{hand}"
                else:
                    base_name = parts[0]
            else:
                base_name = inst_id
            
            if base_name not in self_composer.instruments:
                print(f"Instrumento base '{base_name}' não encontrado (de '{inst_id}')")
                return None
            
            # Obtém a definição do instrumento base
            instrument_obj, min_pitch, max_pitch, transposition = self_composer.instruments[base_name]
            
            # Se for uma instância numerada, cria uma cópia do instrumento com nome ajustado
            if '_' in inst_id and not base_name.startswith("piano_"):
                import copy
                instrument_copy = copy.deepcopy(instrument_obj)
                
                # Extrai o número da sufixo
                suffix = None
                parts = inst_id.split('_')
                if len(parts) > 1 and parts[1].isdigit():
                    suffix = parts[1]
                
                # Ajusta o nome da parte para indicar a numeração
                if suffix and hasattr(instrument_copy, 'partName') and instrument_copy.partName:
                    instrument_copy.partName = f"{instrument_copy.partName} {suffix}"
                
                return (instrument_copy, min_pitch, max_pitch, transposition)
            
            return (instrument_obj, min_pitch, max_pitch, transposition)

        # Correção para o método set_active_instruments_with_doubles
        def set_active_instruments_with_doubles(self_composer, instrument_selections):
            """
            Define os instrumentos ativos com suporte a múltiplas instâncias (dobras).
            
            Parâmetros:
            - instrument_selections: dicionário {nome_instrumento: quantidade}
            
            Retorna:
            - True se bem sucedido, False caso contrário
            """
            valid_instruments = []
            
            # CORREÇÃO: Implementação mais clara para lidar com casos específicos
            for inst_name, count in instrument_selections.items():
                if inst_name in self_composer.instruments and count > 0:
                    # Tratamento especial para o piano (não adiciona sufixos)
                    if inst_name in ["piano_direita", "piano_esquerda"]:
                        valid_instruments.append(inst_name)
                        continue
                        
                    # Para cada instrumento, adiciona o número especificado de instâncias
                    for i in range(count):
                        # Se for mais de uma instância, adiciona um sufixo numérico
                        if count > 1:
                            inst_id = f"{inst_name}_{i+1}"  # Ex: "flauta_1", "flauta_2"
                        else:
                            inst_id = inst_name
                        
                        valid_instruments.append(inst_id)
            
            if not valid_instruments:
                print("Nenhum instrumento válido selecionado. Mantendo configuração atual.")
                return False
            
            # CORREÇÃO: Garantir que não há duplicatas no caso do piano
            unique_instruments = []
            piano_parts = {"piano_direita": False, "piano_esquerda": False}
            
            for inst in valid_instruments:
                if inst in piano_parts:
                    if not piano_parts[inst]:  # Evita duplicatas
                        piano_parts[inst] = True
                        unique_instruments.append(inst)
                else:
                    unique_instruments.append(inst)
            
            # Define os instrumentos ativos
            self_composer.active_instruments = unique_instruments
            
            # Cria um resumo para log
            instrument_counts = {}
            for inst in unique_instruments:
                base_name = inst.split('_')[0]  # Remove o sufixo numérico
                instrument_counts[base_name] = instrument_counts.get(base_name, 0) + 1
            
            summary = []
            for inst, count in instrument_counts.items():
                if count > 1:
                    summary.append(f"{inst.title()} ({count})")
                else:
                    summary.append(inst.title())
            
            print(f"Instrumentos ativos definidos: {', '.join(summary)}")
            return True

        # Correção para o método generate_multi_instrument_composition_with_doubles
        def generate_multi_instrument_composition_with_doubles(self_composer, title="Composição Orquestral", style="balanced", instruments=None, exact_length=None):
            """
            Versão modificada que suporta múltiplas instâncias do mesmo instrumento
            e respeita estritamente o comprimento desejado.
            """
            import music21 as m21
            import random
            
            if not self_composer.rhythm_patterns or not self_composer.pitch_patterns:
                print("Dados de análise insuficientes. Execute o carregamento dos dados primeiro.")
                return None
            
            # Define o estilo de composição
            self_composer.current_style = style
            style_params = self_composer.composition_templates.get(style, self_composer.composition_templates["balanced"])
            
            # Define quais instrumentos usar
            if instruments is None:
                # Se não especificado, usa os instrumentos ativos
                instruments_to_use = self_composer.active_instruments
            else:
                # Filtra apenas os instrumentos válidos da lista fornecida
                instruments_to_use = [inst for inst in instruments if inst.split('_')[0] in self_composer.instruments]
                if not instruments_to_use:
                    # Se nenhum instrumento válido, usa o padrão
                    instruments_to_use = ["piano_direita", "piano_esquerda"]
            
            # Debug para verificar os instrumentos ativos
            print(f"Instrumentos a serem usados: {instruments_to_use}")
            
            # Cria uma nova partitura
            score = m21.stream.Score()
            
            # Adiciona metadados
            score.insert(0, m21.metadata.Metadata())
            score.metadata.title = title
            score.metadata.composer = "GrammarComposer AI"
            
            # Identifica instrumentos de piano para tratamento especial
            piano_parts = {part: idx for idx, part in enumerate(instruments_to_use) 
                        if part.startswith("piano_")}
            
            # Cria um dicionário para agrupar partes por instrumento (para o caso do piano)
            instrument_parts = {}
            
            # MELHORIA: Gerar a sequência de fórmulas de compasso ANTES de processar qualquer instrumento
            # e usar a mesma sequência para todos os instrumentos
            time_sig_sequence = None
            if self_composer.use_variable_time_signatures:
                # Estima o número de compassos necessários (aproximadamente)
                # Ajustado para ser mais preciso baseado no comprimento e compasso atual
                beat_value = 1.0  # Padrão para 4/4
                try:
                    numerator, denominator = map(int, self_composer.time_signature.split('/'))
                    beat_value = 4.0 / denominator
                except:
                    pass
                    
                events_per_measure = numerator * (4 / denominator)
                estimate_measures = int((exact_length if exact_length else self_composer.composition_length) / events_per_measure) + 2
                
                print(f"Gerando sequência de {estimate_measures} fórmulas de compasso")
                time_sig_sequence = self_composer.generate_time_signature_sequence(estimate_measures)
                print(f"Sequência de fórmulas gerada: {time_sig_sequence[:5]}...")
                
                # Armazena a sequência para uso em todos os instrumentos
                self_composer._current_time_sig_sequence = time_sig_sequence
            
            # Gera partes para cada instrumento
            for inst_id in instruments_to_use:
                # Pula o piano por enquanto (tratado separadamente depois)
                if inst_id.startswith("piano_"):
                    continue
                    
                # Obtém configurações do instrumento
                instrument_info = self_composer.get_instrument_for_part(inst_id)
                if not instrument_info:
                    print(f"Instrumento não encontrado: {inst_id}")
                    continue
                    
                instrument_obj, min_pitch, max_pitch, transposition = instrument_info
                
                # Aplica ajustes específicos do estilo
                min_pitch = max(min_pitch, style_params["min_pitch"])
                max_pitch = min(max_pitch, style_params["max_pitch"])
                
                # Cria uma parte para o instrumento
                part = m21.stream.Part()
                
                # Adiciona o objeto de instrumento para obter o timbre correto no MIDI
                part.append(instrument_obj)
                
                # Adiciona a clave apropriada
                base_name = inst_id.split('_')[0]
                if base_name in self_composer.instrument_clefs:
                    part.append(self_composer.instrument_clefs[base_name])
                
                # Adiciona informações de compasso e tonalidade
                ts = m21.meter.TimeSignature(self_composer.time_signature)
                part.append(ts)
                
                ks = m21.key.Key(self_composer.key_signature)
                part.append(ks)
                
                # Adiciona informação de andamento (apenas para o primeiro instrumento)
                if inst_id == instruments_to_use[0] or len(instrument_parts) == 0:
                    mm = m21.tempo.MetronomeMark(number=self_composer.tempo)
                    part.append(mm)
                
                # MODIFICAÇÃO: Usar comprimento exato ou com variações pequenas
                if exact_length is not None:
                    # Usar comprimento exato quando solicitado
                    adjusted_length = exact_length
                    adjusted_complexity = style_params["rhythm_complexity"]
                else:
                    # Para manter a variação entre instrumentos, podemos modificar a complexidade rítmica
                    # ligeiramente para cada instrumento, mas manter o comprimento constante
                    complexity_variation = random.uniform(-0.1, 0.1)
                    # MODIFICAÇÃO: Remover variação de comprimento para maior consistência
                    adjusted_length = self_composer.composition_length
                    adjusted_complexity = max(0.1, min(0.9, style_params["rhythm_complexity"] + complexity_variation))
                
                # CORREÇÃO: Chame os métodos usando self_composer e não self
                # Gera a sequência rítmica para este instrumento
                rhythm_sequence = self_composer._generate_rhythm_sequence(adjusted_length, adjusted_complexity)
                
                # Gera a sequência melódica para este instrumento, respeitando sua tessitura
                pitch_sequence = self_composer._generate_pitch_sequence(adjusted_length, min_pitch, max_pitch)
                
                # NOVO: Gera a sequência de velocity para este instrumento
                velocity_sequence = self_composer._generate_velocity_sequence(adjusted_length, pitch_sequence, style_params)
                
                # Aplica transposição se necessário (para instrumentos transpositores)
                if transposition != 0:
                    pitch_sequence = [p + transposition if p > 0 else p for p in pitch_sequence]
                
                # CORREÇÃO: Chame os métodos usando self_composer e não self
                # MODIFICADO: Passa a sequência de velocities para a criação da partitura
                # Em algum lugar dentro da função generate_multi_instrument_composition_with_doubles:
                velocity_sequence = self_composer._generate_velocity_sequence(adjusted_length, pitch_sequence, style_params)
                self_composer._create_score_from_sequences(part, rhythm_sequence, pitch_sequence, velocity_sequence, time_sig_sequence)
                
                # Armazena a parte no dicionário
                instrument_parts[inst_id] = part
                print(f"Parte criada para instrumento: {inst_id}")
            
            # Trata o piano como caso especial (duas mãos em um sistema)
            # Podemos ter múltiplos pianos (Piano 1, Piano 2, etc.)
            piano_groups = {}
            for piano_part, _ in sorted(piano_parts.items(), key=lambda x: x[1]):
                piano_base = piano_part.split('_')[0]  # "piano" sem o sufixo numérico
                piano_component = piano_part.split('_')[1]  # "direita" ou "esquerda" ou numérico
                
                # Agrupa as partes de piano
                group_key = "piano"  # Piano principal por padrão
                
                # Verifica se há um número depois de "piano_direita" ou "piano_esquerda"
                if "_" in piano_component:
                    # Formato esperado: piano_direita_1, piano_esquerda_2, etc.
                    hand, number = piano_component.split('_', 1)
                    group_key = f"piano_{number}"
                elif piano_component.isdigit() or (len(piano_component) > 1 and piano_component[0].isdigit()):
                    # Formato alternativo: piano_1_direita, piano_2_esquerda
                    group_key = f"piano_{piano_component}"
                
                if group_key not in piano_groups:
                    piano_groups[group_key] = []
                
                piano_groups[group_key].append(piano_part)
            
            # Debug para verificar os grupos de piano identificados
            print(f"Grupos de piano identificados: {piano_groups}")
            
            # Processa cada grupo de piano
            for group_key, group_parts in piano_groups.items():
                # Verifica se temos partes para as duas mãos
                has_right = any("direita" in p for p in group_parts)
                has_left = any("esquerda" in p for p in group_parts)
                
                # Só cria um grupo de piano se tivermos pelo menos uma mão
                if has_right or has_left:
                    # Cria um grupo de staff para o piano
                    piano_staff = m21.stream.PartStaff()
                    
                    # Define o nome do grupo de piano (Piano, Piano 2, etc.)
                    piano_name = "Piano"
                    if group_key != "piano":
                        try:
                            num = group_key.split('_')[1]
                            piano_name = f"Piano {num}"
                        except:
                            pass
                    
                    # Cria o instrumento de piano com nome correto
                    piano_inst = m21.instrument.Piano()
                    piano_inst.partName = piano_name
                    piano_staff.insert(0, piano_inst)
                    
                    # Processa as partes para mão direita e esquerda
                    for hand in ["direita", "esquerda"]:
                        matching_parts = [p for p in group_parts if hand in p]
                        
                        if matching_parts:
                            # Use a primeira parte encontrada para esta mão
                            hand_part_id = matching_parts[0]
                            
                            # Gera a parte se ainda não existir
                            if hand_part_id not in instrument_parts:
                                # Obtém configurações do instrumento
                                base_name = f"piano_{hand}"
                                if base_name in self_composer.instruments:
                                    instrument_obj, min_pitch, max_pitch, transposition = self_composer.instruments[base_name]
                                    
                                    # Aplica ajustes específicos do estilo
                                    min_pitch = max(min_pitch, style_params["min_pitch"])
                                    max_pitch = min(max_pitch, style_params["max_pitch"])
                                    
                                    # Cria uma parte para a mão
                                    part = m21.stream.Part()
                                    
                                    # Adiciona o objeto de instrumento
                                    part.append(instrument_obj)
                                    
                                    # Adiciona a clave apropriada
                                    if base_name in self_composer.instrument_clefs:
                                        part.append(self_composer.instrument_clefs[base_name])
                                    
                                    # Adiciona informações de compasso e tonalidade
                                    ts = m21.meter.TimeSignature(self_composer.time_signature)
                                    part.append(ts)
                                    
                                    ks = m21.key.Key(self_composer.key_signature)
                                    part.append(ks)
                                    
                                    # MODIFICAÇÃO: Usar comprimento exato ou com variações pequenas
                                    if exact_length is not None:
                                        # Usar comprimento exato quando solicitado
                                        adjusted_length = exact_length
                                        adjusted_complexity = style_params["rhythm_complexity"]
                                    else:
                                        # CORREÇÃO: Remover variação de comprimento para maior consistência
                                        complexity_variation = random.uniform(-0.1, 0.1)
                                        adjusted_length = self_composer.composition_length
                                        adjusted_complexity = max(0.1, min(0.9, style_params["rhythm_complexity"] + complexity_variation))
                                    
                                    rhythm_sequence = self_composer._generate_rhythm_sequence(adjusted_length, adjusted_complexity)
                                    pitch_sequence = self_composer._generate_pitch_sequence(adjusted_length, min_pitch, max_pitch)
                                    
                                    # CORREÇÃO: Passa a sequência de fórmulas de compasso para que o piano
                                    # use exatamente as mesmas mudanças de compasso que os outros instrumentos
                                    _create_score_from_sequences(self_composer, part, rhythm_sequence, pitch_sequence, time_sig_sequence)
                                    
                                    # Armazena a parte
                                    instrument_parts[hand_part_id] = part
                                    print(f"Parte de piano criada: {hand_part_id}")
                            
                            # Adiciona a parte ao grupo de piano
                            if hand_part_id in instrument_parts:
                                piano_staff.insert(0, instrument_parts[hand_part_id])
                                
                                # Remove a parte do dicionário para não ser adicionada duas vezes
                                del instrument_parts[hand_part_id]
                    
                    # Adiciona o grupo de piano à partitura
                    score.insert(0, piano_staff)
                    print(f"Grupo de piano adicionado: {piano_name}")
            
            # Adiciona as demais partes à partitura
            for inst_id, part in instrument_parts.items():
                score.insert(0, part)
                print(f"Parte adicionada à partitura final: {inst_id}")
            
            return score
        
        # Aplica as correções à classe GenerativeGrammarComposer
        setattr(self.composer.__class__, 'generate_multi_instrument_composition_with_doubles', 
                types.MethodType(generate_multi_instrument_composition_with_doubles, self.composer))
        setattr(self.composer.__class__, 'set_active_instruments_with_doubles', 
                types.MethodType(set_active_instruments_with_doubles, self.composer))
        setattr(self.composer.__class__, 'get_instrument_for_part', 
                types.MethodType(get_instrument_for_part, self.composer))
        setattr(self.composer.__class__, '_create_score_from_sequences', 
                types.MethodType(_create_score_from_sequences, self.composer))

    def _apply_instrument_selection(self):
        """
        Aplica a seleção atual de instrumentos com suporte a múltiplas instâncias.
        """
        # Coleta as seleções de instrumentos com suas quantidades
        instrument_selections = {}
        
        for instrument, var in self.instrument_vars.items():
            count = var.get()
            # CORREÇÃO: Assegura que o count seja um inteiro válido
            if isinstance(count, int) and count > 0:
                instrument_selections[instrument] = count
        
        if not instrument_selections:
            messagebox.showwarning("Aviso", "Nenhum instrumento selecionado. Selecionando piano como padrão.")
            # Define o piano como padrão
            self.instrument_vars["piano_direita"].set(1)
            self.instrument_vars["piano_esquerda"].set(1)
            instrument_selections = {"piano_direita": 1, "piano_esquerda": 1}
        
        # DEPURAÇÃO: Log detalhado da seleção de instrumentos
        debug_str = "Instrumento(s) selecionado(s):\n"
        for inst, count in instrument_selections.items():
            debug_str += f"  - {inst}: {count}\n"
        self.log_message(debug_str)
        
        # Atualiza a lista de instrumentos ativos no compositor
        try:
            # CORREÇÃO: Assegura que estamos usando o método correto
            if hasattr(self.composer, 'set_active_instruments_with_doubles'):
                if self.composer.set_active_instruments_with_doubles(instrument_selections):
                    # DEPURAÇÃO: Exibe os instrumentos ativos após aplicar a seleção
                    self.log_message(f"Instrumentos ativos após aplicação: {self.composer.active_instruments}")
                    
                    # Exibe os instrumentos ativos
                    self._update_active_instruments_display(instrument_selections)
                    self.log_message("Seleção de instrumentos aplicada com sucesso.")
                else:
                    messagebox.showerror("Erro", "Falha ao aplicar seleção de instrumentos.")
            else:
                messagebox.showerror("Erro", "Método 'set_active_instruments_with_doubles' não encontrado.")
        except Exception as e:
            self.log_message(f"Erro ao aplicar seleção de instrumentos: {e}")
            messagebox.showerror("Erro", f"Falha ao aplicar seleção de instrumentos: {e}")

    def _update_active_instruments_display(self, instrument_selections):
        """
        Atualiza o display de instrumentos ativos com as quantidades.
        
        Parâmetros:
        - instrument_selections: dicionário {nome_instrumento: quantidade}
        """
        # Cria um resumo para exibição, agrupando corretamente
        display_items = []
        
        # Organizar os instrumentos por tipo
        grouped_instruments = {}
        
        # Primeiro, agrupamos piano como um caso especial
        has_piano = False
        if "piano_direita" in instrument_selections or "piano_esquerda" in instrument_selections:
            has_piano = True
            
        # Processar outros instrumentos
        for inst, count in sorted(instrument_selections.items()):
            # Pula o piano (será tratado separadamente)
            if inst.startswith("piano_"):
                continue
            
            # Agrupa por nome base (sem sufixos)
            base_name = inst.split('_')[0]
            
            if base_name not in grouped_instruments:
                grouped_instruments[base_name] = 0
            
            grouped_instruments[base_name] += count
        
        # Adiciona piano primeiro, se presente
        if has_piano:
            display_items.append("Piano")
        
        # Adiciona os outros instrumentos com suas contagens
        for inst, count in sorted(grouped_instruments.items()):
            # Formata o nome do instrumento
            display_name = inst.title()
            
            # Adiciona a quantidade se for mais de 1
            if count > 1:
                display_items.append(f"{display_name} ({count})")
            else:
                display_items.append(display_name)
        
        # Atualiza o texto com a lista de instrumentos
        if display_items:
            self.active_instruments_text.config(text=", ".join(display_items))
            self.log_message("Seleção de instrumentos aplicada com sucesso!")
        else:
            self.active_instruments_text.config(text="Nenhum instrumento selecionado")     
    
    def _setup_compositions_tab(self):
        """
        Configura a aba de composições incluindo coluna para andamento.
        """
        # Frame superior com lista de composições
        frame_top = ttk.Frame(self.tab_compositions)
        frame_top.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        self.tree_compositions = ttk.Treeview(frame_top, 
                                            columns=("title", "style", "measures", "tempo", "instruments"), 
                                            show="headings", height=10)
        self.tree_compositions.heading("title", text="Título")
        self.tree_compositions.heading("style", text="Estilo")
        self.tree_compositions.heading("measures", text="Compassos")
        self.tree_compositions.heading("tempo", text="Andamento")  # Nova coluna
        self.tree_compositions.heading("instruments", text="Instrumentos")
        
        self.tree_compositions.column("title", width=200)
        self.tree_compositions.column("style", width=100)
        self.tree_compositions.column("measures", width=80)
        self.tree_compositions.column("tempo", width=80)  # Nova coluna
        self.tree_compositions.column("instruments", width=100)
        
        self.tree_compositions.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Scrollbar para a árvore
        scrollbar = ttk.Scrollbar(frame_top, orient=tk.VERTICAL, command=self.tree_compositions.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.tree_compositions.configure(yscrollcommand=scrollbar.set)
        
        # Frame inferior com ações
        frame_bottom = ttk.Frame(self.tab_compositions)
        frame_bottom.pack(fill=tk.X, padx=10, pady=5)
        
        ttk.Button(frame_bottom, text="Abrir Selecionada", 
                command=self._open_selected_composition).pack(side=tk.LEFT, padx=5, pady=5)
        
        ttk.Button(frame_bottom, text="Exportar Selecionada", 
                command=self._export_selected_composition).pack(side=tk.LEFT, padx=5, pady=5)
        
        ttk.Button(frame_bottom, text="Remover Selecionada", 
                command=self._remove_selected_composition).pack(side=tk.LEFT, padx=5, pady=5)
    
    def _select_analysis_folder(self):
        """
        Seleciona a pasta de análise.
        """
        if self.composer.select_analysis_folder():
            self.lbl_folder.config(text=f"Pasta: {os.path.basename(self.composer.analysis_folder)}")
            self.log_message(f"Pasta de análise selecionada: {self.composer.analysis_folder}")
    
    def _load_analysis_data(self):
        """
        Carrega os dados de análise.
        """
        if self.composer.load_analysis_data():
            self.log_message("Dados de análise carregados com sucesso!")
            self.composer.create_output_folder()
            self._update_template_tree()
        else:
            messagebox.showerror("Erro", "Falha ao carregar dados de análise.")

    def _generate_composition(self):
        """
        Gera uma composição respeitando estritamente a quantidade definida pelo usuário
        e o andamento (BPM) especificado, incluindo expressão de andamento.
        """
        if not self.composer.rhythm_patterns or not self.composer.pitch_patterns:
            messagebox.showwarning("Aviso", "Carregue os dados de análise antes de gerar uma composição.")
            return
        
        title = self.entry_title.get() or "Composição Gerada"
        style = self.combo_style.get() or "balanced"
        
        # Obter e configurar o andamento e expressão
        try:
            tempo = int(self.spin_tempo.get())
            if tempo < 20 or tempo > 300:
                # Se o valor estiver fora dos limites razoáveis, use o padrão
                tempo = 90
                self.log_message(f"Aviso: Andamento ajustado para {tempo} BPM (valor estava fora dos limites)")
            
            # Verificar expressão de andamento
            tempo_expression = self.combo_tempo_expression.get()
            if tempo_expression == "Auto":
                # Deixa a função determinar com base no BPM
                self.composer.set_tempo_with_expression(tempo)
                self.log_message(f"Andamento definido: {tempo} BPM ({self.composer.tempo_expression})")
            else:
                # Usa a expressão selecionada
                self.composer.set_tempo_with_expression(tempo, tempo_expression)
                self.log_message(f"Andamento definido: {tempo_expression} ({tempo} BPM)")
        except:
            tempo = 90
            self.composer.set_tempo_with_expression(tempo)
            self.log_message(f"Usando andamento padrão: {tempo} BPM ({self.composer.tempo_expression})")
        
        # Obter e configurar o comprimento
        try:
            length_value = int(self.spin_length.get())
            use_measures = self.length_type.get() == "measures"
        except:
            length_value = 32
            use_measures = False
        
        # Armazenar os valores originais para restauração posterior
        original_length = self.composer.composition_length
        
        try:
            self.log_message(f"Gerando composição '{title}' no estilo {style} com andamento {self.composer.tempo_expression} ({tempo} BPM)...")
            
            # Sincroniza instrument_vars → active_instruments ANTES de gerar.
            # Garante que a seleção visual da aba Instrumentos seja respeitada
            # sem exigir que o usuário clique em "Aplicar Seleção".
            instrument_selections_from_ui = {}
            for inst_id, var in self.instrument_vars.items():
                try:
                    count = int(var.get())
                except (ValueError, TypeError):
                    count = 0
                if count > 0:
                    instrument_selections_from_ui[inst_id] = count

            if instrument_selections_from_ui:
                self.composer.set_active_instruments_with_doubles(instrument_selections_from_ui)
                self.log_message(
                    f"Instrumentos sincronizados: "
                    f"{', '.join(sorted(instrument_selections_from_ui.keys()))}"
                )
            elif not self.composer.active_instruments:
                # Nenhum instrumento selecionado em nenhum lugar → padrão piano
                self.log_message("Aviso: Nenhum instrumento selecionado. Usando piano como padrão.")
                self.composer.set_active_instruments_with_doubles({"piano_direita": 1, "piano_esquerda": 1})
                if "piano_direita" in self.instrument_vars:
                    self.instrument_vars["piano_direita"].set(1)
                if "piano_esquerda" in self.instrument_vars:
                    self.instrument_vars["piano_esquerda"].set(1)
            
            # Abordagem diferente baseada no tipo de comprimento (eventos vs compassos)
            score = None
            if use_measures:
                self.log_message(f"Gerando exatamente {length_value} compassos...")
                
                # CORREÇÃO: Usar o método atualizado para gerar com número exato de compassos
                score = self.composer.generate_composition_with_exact_measures(
                    measure_count=length_value,
                    title=title,
                    style=style
                )
            else:
                # Eventos musicais: definir comprimento exato
                self.log_message(f"Gerando {length_value} eventos musicais...")
                
                # Modificar temporariamente o comprimento da composição
                self.composer.composition_length = length_value
                
                # Usar método com suporte a múltiplas instâncias e comprimento exato
                if hasattr(self.composer, 'generate_multi_instrument_composition_with_doubles'):
                    score = self.composer.generate_multi_instrument_composition_with_doubles(
                        title=title, 
                        style=style,
                        exact_length=length_value  # Passar comprimento exato
                    )
                else:
                    # Fallback para o método padrão
                    score = self.composer.generate_multi_instrument_composition(
                        title=title, 
                        style=style
                    )
            
            # Restaurar comprimento original após a geração
            self.composer.composition_length = original_length
            
            if score:
                # Garantir que o andamento está definido na partitura
                score = self.composer._ensure_tempo_in_all_parts(score)
                
                # Verificar o resultado final
                first_part = score.parts[0]
                if isinstance(first_part, m21.stream.PartStaff):
                    first_part_content = first_part.getElementsByClass('Part')
                    if first_part_content:
                        measure_count = len(first_part_content[0].getElementsByClass('Measure'))
                    else:
                        measure_count = 0
                else:
                    measure_count = len(first_part.getElementsByClass('Measure'))
                
                if use_measures:
                    if measure_count != length_value:
                        self.log_message(f"Nota: Foram gerados {measure_count} compassos (desejados: {length_value})")
                    else:
                        self.log_message(f"Gerados {measure_count} compassos com sucesso!")
                else:
                    self.log_message(f"Gerados {length_value} eventos musicais ({measure_count} compassos)")
                
                self.current_composition = score
                
                # Conta os instrumentos ativos corretamente, considerando dobras
                instrument_counts = {}
                for inst in self.composer.active_instruments:
                    # Extrai o nome base (sem sufixos numéricos)
                    if "_" in inst:
                        parts = inst.split("_")
                        if parts[0] == "piano" and len(parts) > 1:
                            if parts[1] in ["direita", "esquerda"]:
                                base_name = "piano"  # Agrupa ambas as mãos como "piano"
                            else:
                                # Ignorar sufixos numéricos também para piano
                                base_name = "piano"
                        else:
                            # Para outros instrumentos, remove sufixos numéricos
                            base_name = parts[0]
                    else:
                        base_name = inst
                    
                    instrument_counts[base_name] = instrument_counts.get(base_name, 0) + 1
                
                # Cria um resumo de instrumentos para exibição
                instruments_summary = []
                for inst, count in sorted(instrument_counts.items()):
                    # Não mostrar "piano_direita"/"piano_esquerda" separadamente
                    if inst == "piano":
                        if "Piano" not in instruments_summary:  # Evita duplicação
                            instruments_summary.append("Piano")
                    elif count > 1:
                        instruments_summary.append(f"{inst.title()} ({count})")
                    else:
                        instruments_summary.append(inst.title())
                
                # Inclui explicitamente o andamento no dicionário de informações
                comp_info = {
                    'title': title,
                    'style': style,
                    'measures': measure_count,
                    'tempo': tempo,
                    'tempo_expression': self.composer.tempo_expression,
                    'score': score,
                    'instruments': self.composer.active_instruments,
                    'instruments_summary': ", ".join(instruments_summary)
                }
                self.compositions.append(comp_info)
                self._update_compositions_tree()
                
                # Mostra uma prévia
                self.preview_composition(score)
                
                # Muda para a aba de composições
                self.notebook.select(4)
            else:
                self.log_message("Falha ao gerar composição.")
                    
        except Exception as e:
            self.log_message(f"Erro ao gerar composição: {e}")
            import traceback
            self.log_message(traceback.format_exc())
            messagebox.showerror("Erro", f"Ocorreu um erro ao gerar a composição: {e}")
    
    def _generate_batch(self):
        """
        Gera um lote de composições.
        """
        if not self.composer.rhythm_patterns or not self.composer.pitch_patterns:
            messagebox.showwarning("Aviso", "Carregue os dados de análise antes de gerar composições.")
            return
        
        try:
            count = simpledialog.askinteger("Lote de Composições", 
                                        "Quantas composições deseja gerar?",
                                        minvalue=1, maxvalue=10, initialvalue=3)
            if not count:
                return
            
            self.log_message(f"Gerando lote de {count} composições...")
            styles = list(self.composer.composition_templates.keys())
            
            new_compositions = []
            for i in range(count):
                # Seleciona um estilo aleatório da lista de estilos
                style = random.choice(styles)
                
                # Cria um título para a composição
                title = f"Composição {style.title()} #{i+1}"
                
                # Gera a composição multi-instrumento
                score = self.composer.generate_multi_instrument_composition(
                    title=title, 
                    style=style
                )
                
                if score:
                    # Salva a composição
                    filename = f"{style}_comp_{i+1}"
                    saved_files = self.composer.save_composition(score, filename)
                    
                    # Determina o número de compassos
                    first_part = score.parts[0]
                    if isinstance(first_part, m21.stream.PartStaff):
                        first_part = first_part.getElementsByClass('Part')[0]
                    measure_count = len(first_part.getElementsByClass('Measure'))
                    
                    new_compositions.append({
                        'title': title,
                        'style': style,
                        'measures': measure_count,
                        'files': saved_files,
                        'score': score,
                        'instruments': self.composer.get_active_instruments()
                    })
            
            if new_compositions:
                self.log_message(f"{len(new_compositions)} composições geradas com sucesso!")
                
                # Adiciona as novas composições à lista
                self.compositions.extend(new_compositions)
                
                # Atualiza a árvore de composições
                self._update_compositions_tree()
                
                # Muda para a aba de composições
                self.notebook.select(4)  # Índice 4 é a aba de composições
            else:
                self.log_message("Falha ao gerar o lote de composições.")
            
        except Exception as e:
            self.log_message(f"Erro ao gerar lote de composições: {e}")
            messagebox.showerror("Erro", f"Ocorreu um erro ao gerar as composições: {e}")
    
    def _save_current_composition(self):
        """
        Salva a composição atual.
        """
        if not self.current_composition:
            messagebox.showwarning("Aviso", "Nenhuma composição atual para salvar.")
            return
        
        try:
            filename = simpledialog.askstring("Salvar Composição", 
                                             "Nome do arquivo (sem extensão):",
                                             initialvalue=self.current_composition.metadata.title.replace(" ", "_").lower())
            
            if not filename:
                return
            
            formats = []
            if messagebox.askyesno("Formato", "Salvar em formato MIDI?"):
                formats.append('midi')
            if messagebox.askyesno("Formato", "Salvar em formato MusicXML?"):
                formats.append('musicxml')
            
            if not formats:
                messagebox.showwarning("Aviso", "Nenhum formato selecionado. Composição não será salva.")
                return
            
            saved_files = self.composer.save_composition(self.current_composition, filename, formats)
            
            if saved_files:
                self.log_message(f"Composição salva como: {', '.join(saved_files)}")
                
                # Pergunta se deseja abrir no MuseScore
                if messagebox.askyesno("Abrir no MuseScore", "Deseja abrir a composição no MuseScore?"):
                    self.composer.open_in_musescore(saved_files[0])
            else:
                self.log_message("Falha ao salvar a composição.")
                
        except Exception as e:
            self.log_message(f"Erro ao salvar composição: {e}")
            messagebox.showerror("Erro", f"Ocorreu um erro ao salvar a composição: {e}")
    
    def _open_in_musescore(self):
        """
        Tenta abrir a composição atual no MuseScore, garantindo que o andamento e expressão sejam preservados.
        """
        if not self.current_composition:
            messagebox.showwarning("Aviso", "Nenhuma composição atual para abrir.")
            return

        # Adicione esta verificação para garantir um andamento válido
        if self.composer.tempo <= 0:
            self.composer.tempo = 90  # Valor padrão razoável
        self.log_message(f"Usando andamento: {self.composer.tempo} BPM para a abertura no MuseScore")               
        
        # Verifica se o MuseScore está instalado se ainda não tiver feito isso
        if not hasattr(self, 'musescore_available') or self.musescore_available is None:
            self.musescore_available = self.composer._find_musescore_path() is not None
        
        # Se o MuseScore não estiver disponível, oferece opções para instalação
        if not self.musescore_available:
            if not self.composer._check_and_install_musescore():
                # Se o usuário optou por não continuar, aborta
                return
        
        try:
            # Salva temporariamente em MusicXML e MIDI
            temp_filename = "temp_composition"
            
            # Obter e aplicar o andamento atual da interface para a composição
            try:
                tempo = int(self.spin_tempo.get())
                tempo_expression = self.combo_tempo_expression.get()
                
                if tempo_expression == "Auto":
                    self.composer.set_tempo_with_expression(tempo)
                    self.log_message(f"Aplicando andamento de {self.composer.tempo_expression} ({tempo} BPM) à composição")
                else:
                    self.composer.set_tempo_with_expression(tempo, tempo_expression)
                    self.log_message(f"Aplicando andamento de {tempo_expression} ({tempo} BPM) à composição")
            except Exception as tempo_err:
                # Se falhar, tenta buscar da própria composição
                try:
                    mm_list = self.current_composition.flatten().getElementsByClass('MetronomeMark')
                    if mm_list:
                        current_tempo = mm_list[0].number
                        self.composer.set_tempo_with_expression(current_tempo)
                        self.log_message(f"Usando andamento da composição: {self.composer.tempo_expression} ({current_tempo} BPM)")
                    else:
                        # Busca nas composições armazenadas
                        for comp in self.compositions:
                            if comp.get('score') == self.current_composition:
                                if 'tempo' in comp:
                                    tempo = comp['tempo']
                                    expression = comp.get('tempo_expression', None)
                                    self.composer.set_tempo_with_expression(tempo, expression)
                                    self.log_message(f"Recuperado andamento dos metadados: {self.composer.tempo_expression} ({tempo} BPM)")
                                    break
                except Exception:
                    self.log_message(f"Aviso: Usando andamento padrão ({self.composer.tempo} BPM)")
            
            # Aplicar correções e andamento usando o método atualizado
            self.current_composition = self.composer._ensure_tempo_in_all_parts(self.current_composition)
            
            # Salvar como MusicXML e MIDI usando o método atualizado
            self.log_message("Salvando arquivo temporário...")
            saved_files = self.composer.save_composition(self.current_composition, temp_filename, ['musicxml', 'midi'])
            
            if saved_files:
                # Prioriza arquivos MusicXML para visualização
                musicxml_file = None
                midi_file = None
                
                for file in saved_files:
                    if file.endswith('.musicxml') or file.endswith('.xml'):
                        musicxml_file = file
                    elif file.endswith('.mid'):
                        midi_file = file
                
                # Usa o primeiro arquivo adequado que encontrar
                file_to_open = musicxml_file if musicxml_file else midi_file if midi_file else saved_files[0]
                
                self.log_message(f"Abrindo arquivo: {file_to_open} (Andamento: {self.composer.tempo_expression}, {self.composer.tempo} BPM)")
                
                # Tenta abrir com o MuseScore
                success = self.composer.open_in_musescore(file_to_open)
                
                if success:
                    self.log_message("Arquivo aberto com sucesso no MuseScore!")
                else:
                    # Se falhou, tenta abrir com o aplicativo padrão
                    try:
                        import os
                        import platform
                        import subprocess
                        
                        system = platform.system()
                        if system == "Windows":
                            os.startfile(file_to_open)
                        elif system == "Darwin":  # macOS
                            subprocess.Popen(["open", file_to_open])
                        else:  # Linux
                            subprocess.Popen(["xdg-open", file_to_open])
                            
                        self.log_message("Arquivo aberto com o aplicativo padrão do sistema.")
                    except Exception as e:
                        self.log_message(f"Não foi possível abrir o arquivo: {e}")
                        self.log_message(f"O arquivo foi salvo em: {file_to_open}")
                        
                        # Pergunta se deseja abrir o gerenciador de arquivos
                        if messagebox.askyesno("Arquivo Salvo", 
                                            f"O arquivo foi salvo em:\n{file_to_open}\n\n"
                                            "Deseja abrir o gerenciador de arquivos na pasta?"):
                            try:
                                folder = os.path.dirname(file_to_open)
                                if system == "Windows":
                                    os.startfile(folder)
                                elif system == "Darwin":  # macOS
                                    subprocess.Popen(["open", folder])
                                else:  # Linux
                                    subprocess.Popen(["xdg-open", folder])
                            except Exception as e2:
                                self.log_message(f"Erro ao abrir o gerenciador de arquivos: {e2}")
            else:
                self.log_message("Falha ao salvar a composição temporária.")
                
        except Exception as e:
            self.log_message(f"Erro ao processar a composição: {e}")
            messagebox.showerror("Erro", f"Ocorreu um erro ao processar a composição: {e}")
    
    def _apply_weights(self):
        """
        Aplica os pesos dos algoritmos.
        """
        try:
            ngram_weight = float(self.scale_ngram.get())
            sequitur_weight = float(self.scale_sequitur.get())
            siatec_weight = float(self.scale_siatec.get())
            
            self.composer.set_algorithm_weights(ngram=ngram_weight, 
                                               sequitur=sequitur_weight, 
                                               siatec=siatec_weight)
            
            self.log_message("Pesos dos algoritmos atualizados.")
            
        except Exception as e:
            messagebox.showerror("Erro", f"Falha ao aplicar pesos: {e}")
    
    def _apply_params(self):
        """
        Aplica os parâmetros de composição.
        """
        try:
            key = self.combo_key.get() or "C"
            time_sig = self.combo_time_sig.get() or "4/4"
            
            try:
                tempo = int(self.spin_tempo.get())
            except:
                tempo = 90
            
            self.composer.set_composition_params(time_sig=time_sig, key=key, tempo=tempo)
            
            self.log_message("Parâmetros de composição atualizados.")
            
        except Exception as e:
            messagebox.showerror("Erro", f"Falha ao aplicar parâmetros: {e}")
    
    def _update_template_tree(self):
        """
        Atualiza a árvore de templates.
        """
        # Limpa a árvore atual
        for item in self.tree_templates.get_children():
            self.tree_templates.delete(item)
        
        # Adiciona os templates
        for name, params in self.composer.composition_templates.items():
            self.tree_templates.insert("", "end", text=name, values=(
                params["min_pitch"], 
                params["max_pitch"], 
                f"{params['rhythm_complexity']:.2f}"
            ))
    
    def _update_compositions_tree(self):
        """
        Atualiza a árvore de composições incluindo informação de andamento e expressão.
        """
        # Limpa a árvore atual
        for item in self.tree_compositions.get_children():
            self.tree_compositions.delete(item)
        
        # Adiciona as composições
        for idx, comp in enumerate(self.compositions):
            # Verifica se há um resumo de instrumentos pré-calculado
            if 'instruments_summary' in comp:
                instruments_display = comp['instruments_summary']
            else:
                # Calcula um resumo dos instrumentos (compatibilidade com versões anteriores)
                # Conta os instrumentos únicas, agrupando dobras
                instrument_counts = {}
                for inst in comp.get("instruments", []):
                    base_name = inst.split('_')[0]  # Remove sufixo numérico
                    if base_name.startswith("piano"):
                        # Trata piano como um caso especial
                        base_name = "piano"
                    instrument_counts[base_name] = instrument_counts.get(base_name, 0) + 1
                
                # Formata para exibição
                instruments_list = []
                for inst, count in sorted(instrument_counts.items()):
                    if count > 1 and inst != "piano":
                        instruments_list.append(f"{inst.title()} ({count})")
                    else:
                        instruments_list.append(inst.title())
                
                # Número total de instrumentos diferentes (contando dobras)
                num_instruments = sum(instrument_counts.values())
                instruments_display = f"{num_instruments} ({', '.join(instruments_list)})"
            
            # Formata a informação de andamento
            if 'tempo_expression' in comp and 'tempo' in comp:
                tempo_display = f"{comp['tempo_expression']} ({comp['tempo']} BPM)"
            elif 'tempo' in comp:
                tempo_display = f"{comp['tempo']} BPM"
            else:
                tempo_display = "--"
            
            self.tree_compositions.insert("", "end", text=str(idx), values=(
                comp["title"], 
                comp["style"], 
                comp["measures"],
                tempo_display,  # Andamento com expressão
                instruments_display  # Instrumentos com dobras
            ))
    
    def _open_selected_composition(self):
        """
        Abre a composição selecionada.
        """
        selection = self.tree_compositions.selection()
        if not selection:
            messagebox.showwarning("Aviso", "Nenhuma composição selecionada.")
            return
        
        try:
            idx = int(self.tree_compositions.index(selection[0]))
            if 0 <= idx < len(self.compositions):
                comp = self.compositions[idx]
                self.current_composition = comp["score"]
                
                # Muda para a aba do gerador
                self.notebook.select(0)
                
                # Atualiza a prévia
                self.preview_composition(comp["score"])
                
                self.log_message(f"Composição '{comp['title']}' carregada.")
                
                # Se já tiver arquivos salvos, pergunta se deseja abrir
                if 'files' in comp and comp['files']:
                    if messagebox.askyesno("Abrir Arquivo", "Deseja abrir esta composição no MuseScore?"):
                        self.composer.open_in_musescore(comp['files'][0])
                
        except Exception as e:
            messagebox.showerror("Erro", f"Falha ao abrir composição: {e}")
            self.log_message(f"Erro detalhado: {str(e)}")
            import traceback
            self.log_message(traceback.format_exc())

    def _remove_selected_composition(self):
        """
        Remove a composição selecionada da lista.
        """
        selection = self.tree_compositions.selection()
        if not selection:
            messagebox.showwarning("Aviso", "Nenhuma composição selecionada.")
            return
        
        try:
            idx = int(self.tree_compositions.index(selection[0]))
            if 0 <= idx < len(self.compositions):
                comp = self.compositions[idx]
                
                if messagebox.askyesno("Confirmação", f"Remover a composição '{comp['title']}'?"):
                    del self.compositions[idx]
                    self._update_compositions_tree()
                    self.log_message(f"Composição '{comp['title']}' removida.")
                    
        except Exception as e:
            self.log_message(f"Erro ao remover composição: {e}")
            messagebox.showerror("Erro", f"Falha ao remover composição: {e}")            
    
    def _export_selected_composition(self):
        """
        Exporta a composição selecionada com melhorias para garantir o andamento correto.
        """
        selection = self.tree_compositions.selection()
        if not selection:
            messagebox.showwarning("Aviso", "Nenhuma composição selecionada.")
            return
        
        try:
            idx = int(self.tree_compositions.index(selection[0]))
            if 0 <= idx < len(self.compositions):
                comp = self.compositions[idx]
                score = comp["score"]
                
                # Garante que o andamento está configurado corretamente
                self.composer.tempo = comp.get('tempo', 90)  # Usa o andamento armazenado ou padrão
                score = self.composer._ensure_tempo_in_all_parts(score)
                
                # Solicita o nome do arquivo
                filename = simpledialog.askstring("Exportar Composição", 
                                                "Nome do arquivo (sem extensão):",
                                                initialvalue=score.metadata.title.replace(" ", "_").lower())
                
                if not filename:
                    return
                
                # Solicita os formatos
                formats = []
                if messagebox.askyesno("Formato", "Exportar em formato MIDI?"):
                    formats.append('midi')
                if messagebox.askyesno("Formato", "Exportar em formato MusicXML?"):
                    formats.append('musicxml')
                if messagebox.askyesno("Formato", "Exportar em formato MXL (compactado)?"):
                    formats.append('mxl')
                
                if not formats:
                    messagebox.showwarning("Aviso", "Nenhum formato selecionado. Composição não será exportada.")
                    return
                
                # Salva a composição
                saved_files = self.composer.save_composition(score, filename, formats)
                
                if saved_files:
                    self.log_message(f"Composição exportada como: {', '.join(saved_files)}")
                    
                    # Atualiza a informação de arquivos na composição
                    self.compositions[idx]['files'] = saved_files
                    
                    # Pergunta se deseja abrir no MuseScore
                    if messagebox.askyesno("Abrir no MuseScore", "Deseja abrir a composição no MuseScore?"):
                        music_xml_file = None
                        for file in saved_files:
                            if file.endswith('.musicxml') or file.endswith('.xml') or file.endswith('.mxl'):
                                music_xml_file = file
                                break
                        
                        # Prefere MusicXML sobre MIDI para visualização
                        file_to_open = music_xml_file if music_xml_file else saved_files[0]
                        self.composer.open_in_musescore(file_to_open)
                else:
                    self.log_message("Falha ao exportar a composição.")
                
        except Exception as e:
            self.log_message(f"Erro ao exportar composição: {e}")
            messagebox.showerror("Erro", f"Falha ao exportar composição: {e}")
    
    def log_message(self, message):
        """
        Adiciona uma mensagem ao log.
        """
        self.preview_text.insert(tk.END, message + "\n")
        self.preview_text.see(tk.END)

    def preview_composition(self, score):
        """
        Mostra uma prévia da composição multi-instrumento, incluindo andamento e expressão.
        """
        if not score:
            return
        
        self.preview_text.delete(1.0, tk.END)
        
        self.preview_text.insert(tk.END, f"Título: {score.metadata.title}\n")
        self.preview_text.insert(tk.END, f"Compositor: {score.metadata.composer}\n")
        self.preview_text.insert(tk.END, "-" * 40 + "\n")
        
        # Lista os instrumentos incluídos
        self.preview_text.insert(tk.END, "Instrumentos: ")
        instrument_names = []
        
        for part in score.parts:
            # Verifica se é uma parte normal ou um grupo (como piano)
            if isinstance(part, m21.stream.PartStaff):
                # Para grupos como piano
                staffGroup_instruments = part.getElementsByClass('Instrument')
                if staffGroup_instruments:
                    part_name = staffGroup_instruments[0].partName or "Piano"  # Valor padrão se for None
                    instrument_names.append(part_name)
            else:
                # Para partes normais
                instruments = part.getElementsByClass('Instrument')
                if instruments:
                    part_name = instruments[0].partName or type(instruments[0]).__name__  # Usar nome da classe se partName for None
                    instrument_names.append(part_name)
        
        self.preview_text.insert(tk.END, ", ".join([name for name in instrument_names if name is not None]) + "\n\n")
        
        # Obtém informações básicas da primeira parte
        if score.parts:
            first_part = score.parts[0]
            if isinstance(first_part, m21.stream.PartStaff):
                # Se for um grupo de partes (piano), pega a primeira parte real
                first_part = first_part.getElementsByClass('Part')[0]
            
            # Mostra informações básicas
            ts = first_part.getElementsByClass('TimeSignature')[0] if first_part.getElementsByClass('TimeSignature') else "4/4"
            ks = first_part.getElementsByClass('KeySignature')[0].asKey() if first_part.getElementsByClass('KeySignature') else "C"
            
            # Obtém informação de andamento
            mm = first_part.getElementsByClass('MetronomeMark')
            tempo_info = ""
            if mm:
                tempo = mm[0].number
                tempo_text = mm[0].text if hasattr(mm[0], 'text') and mm[0].text else f"♩={int(tempo)}"
                
                # Verifica se há expressão de andamento
                if hasattr(self.composer, 'tempo_expression'):
                    tempo_info = f"Andamento: {self.composer.tempo_expression} ({int(tempo)} BPM)"
                else:
                    tempo_info = f"Andamento: {tempo_text}"
            else:
                # Busca nas composições armazenadas
                tempo_info = "Andamento: Não definido"
                for comp in self.compositions:
                    if comp.get('score') == score:
                        if 'tempo_expression' in comp and 'tempo' in comp:
                            tempo_info = f"Andamento: {comp['tempo_expression']} ({comp['tempo']} BPM)"
                            break
                        elif 'tempo' in comp:
                            tempo_info = f"Andamento: {comp['tempo']} BPM"
                            break
            
            self.preview_text.insert(tk.END, f"Compasso: {ts} | Tonalidade: {ks} | {tempo_info}\n\n")

    # NOVO: Adiciona informações sobre as dinâmicas usadas
        self.preview_text.insert(tk.END, "\nDinâmicas Utilizadas:\n")
        
        # Busca as dinâmicas em cada parte
        dynamics_used = set()
        for part in score.parts:
            # Caso piano (PartStaff)
            if isinstance(part, m21.stream.PartStaff):
                for sub_part in part.getElementsByClass('Part'):
                    for dynamic in sub_part.flatten().getElementsByClass('Dynamic'):
                        dynamics_used.add(dynamic.value)
            # Caso instrumento normal
            else:
                for dynamic in part.flatten().getElementsByClass('Dynamic'):
                    dynamics_used.add(dynamic.value)
        
        # Se encontrou dinâmicas, mostra-as
        if dynamics_used:
            # Ordenar dinâmicas por intensidade
            dynamic_order = ["ppp", "pp", "p", "mp", "mf", "f", "ff", "fff"]
            sorted_dynamics = sorted(dynamics_used, key=lambda x: dynamic_order.index(x) if x in dynamic_order else -1)
            self.preview_text.insert(tk.END, f"  Marcações: {', '.join(sorted_dynamics)}\n")
            
            # Mostra o modo de dinâmica usado
            self.preview_text.insert(tk.END, f"  Modo de geração: {self.composer.dynamics_mode}\n")
            if self.composer.dynamics_mode == "fixed":
                self.preview_text.insert(tk.END, f"  Dinâmica fixa: {self.composer.fixed_dynamic}\n")
        else:
            self.preview_text.insert(tk.END, "  Nenhuma marcação de dinâmica encontrada\n")            
            
            # Mostra um preview reduzido das primeiras notas de cada instrumento
            self.preview_text.insert(tk.END, "Preview por instrumento:\n")
            
            for part_idx, part in enumerate(score.parts):
                # Determina o nome do instrumento
                if isinstance(part, m21.stream.PartStaff):
                    # Grupo de partes (como piano)
                    instruments = part.getElementsByClass('Instrument')
                    if instruments:
                        part_name = instruments[0].partName or "Piano"
                    else:
                        part_name = f"Parte {part_idx+1}"
                    
                    # Para pianos, mostra cada mão separadamente
                    for sub_part_idx, sub_part in enumerate(part.getElementsByClass('Part')):
                        hand = "direita" if sub_part_idx == 0 else "esquerda"
                        self.preview_text.insert(tk.END, f"  {part_name} (mão {hand}): ")
                        
                        # Mostra as primeiras notas
                        notes_preview = []
                        for measure in sub_part.getElementsByClass('Measure')[:2]:
                            for element in measure.notes[:3]:  # Primeiras 3 notas de cada compasso
                                if isinstance(element, m21.note.Note):
                                    notes_preview.append(element.nameWithOctave)
                                elif isinstance(element, m21.note.Rest):
                                    notes_preview.append("R")
                        
                        self.preview_text.insert(tk.END, " ".join(notes_preview) + "...\n")
                else:
                    # Parte normal
                    instruments = part.getElementsByClass('Instrument')
                    if instruments:
                        part_name = instruments[0].partName or type(instruments[0]).__name__
                    else:
                        part_name = f"Parte {part_idx+1}"
                    
                    self.preview_text.insert(tk.END, f"  {part_name}: ")
                    
                    # Mostra as primeiras notas
                    notes_preview = []
                    for measure in part.getElementsByClass('Measure')[:2]:
                        for element in measure.notes[:3]:  # Primeiras 3 notas de cada compasso
                            if isinstance(element, m21.note.Note):
                                notes_preview.append(element.nameWithOctave)
                            elif isinstance(element, m21.note.Rest):
                                notes_preview.append("R")
                    
                    self.preview_text.insert(tk.END, " ".join(notes_preview) + "...\n")
        
        self.preview_text.insert(tk.END, "-" * 40 + "\n")
        
        # Conta o total de compassos na primeira parte
        if score.parts:
            first_part = score.parts[0]
            if isinstance(first_part, m21.stream.PartStaff):
                # Se for um grupo de partes (piano), pega a primeira parte real
                first_part = first_part.getElementsByClass('Part')[0]
            
            measure_count = len(first_part.getElementsByClass('Measure'))
            self.preview_text.insert(tk.END, f"Total de compassos: {measure_count}\n")

# --------------------------------------------------
# Função principal para iniciar a aplicação
# --------------------------------------------------

def main():
    """
    Função principal que inicia a aplicação.
    """
    try:
        # Verifica disponibilidade da biblioteca music21
        import music21
        print(f"Music21 versão {music21.__version__} encontrada.")
    except ImportError:
        print("Erro: A biblioteca music21 não está instalada.")
        print("Por favor, instale usando: pip install music21")
        return
    
    root = tk.Tk()
    app = ComposerGUI(root)
    root.mainloop()

if __name__ == "__main__":
    main()