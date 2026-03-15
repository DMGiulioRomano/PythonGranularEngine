# exclusive_selector.py

from typing import Dict, List, Optional, Tuple
from parameters.parameter_schema import ParameterSpec

class ExclusiveGroupSelector:
    """
    Gestisce la selezione nei gruppi di parametri mutualmente esclusivi.
    
    Logica:
    1. Per ogni gruppo, controlla quali parametri sono specificati in YAML
    2. Se nessuno è specificato, usa quello con default non-None e priorità più alta
    3. Se più di uno è specificato, usa quello con priorità più alta
    
    Esempio per pitch_mode:
    - YAML ha 'semitones: 12' → seleziona pitch_semitones (priority=1)
    - YAML ha 'ratio: 2.0' → seleziona pitch_ratio (priority=2) 
    - YAML non ha nessuno → seleziona pitch_ratio (default=1.0, priority=2)
    - YAML ha entrambi → seleziona pitch_semitones (priority=1 vince)
    """
    
    @staticmethod
    def select_parameters(
        schema: List[ParameterSpec], 
        yaml_data: dict
    ) -> Tuple[Dict[str, ParameterSpec], Dict[str, List[ParameterSpec]]]:
        """
        Seleziona i parametri attivi per gruppi esclusivi.
        
        Returns:
            Tuple di:
            - selected_specs: {nome_parametro: ParameterSpec} per quelli selezionati
            - group_members: {gruppo: lista_specs} per debug
        """
        # 1. Raggruppa per exclusive_group
        groups: Dict[str, List[ParameterSpec]] = {}
        non_exclusive: List[ParameterSpec] = []
        
        for spec in schema:
            if spec.exclusive_group:
                group_name = spec.exclusive_group
                if group_name not in groups:
                    groups[group_name] = []
                groups[group_name].append(spec)
            else:
                non_exclusive.append(spec)
        
        # 2. Per ogni gruppo, seleziona UN parametro
        selected_specs = {}
        
        for group_name, group_specs in groups.items():
            # Ordina per priorità (più bassa = più alta priorità)
            sorted_specs = sorted(group_specs, key=lambda s: s.group_priority)
            
            # Cerca parametri specificati in YAML
            specified_specs = []
            for spec in sorted_specs:
                if ExclusiveGroupSelector._is_specified(spec, yaml_data):
                    specified_specs.append(spec)
            
            # Decisione
            chosen_spec = None
            
            if specified_specs:
                # Prendi il primo specificato (già ordinato per priorità)
                chosen_spec = specified_specs[0]
            else:
                # Nessuno specificato → prendi quello con default non-None e priorità più alta
                for spec in sorted_specs:
                    if spec.default is not None:
                        chosen_spec = spec
                        break
                        
            if chosen_spec:
                selected_specs[chosen_spec.name] = chosen_spec
        
        # 3. Aggiungi tutti i parametri non-esclusivi
        for spec in non_exclusive:
            selected_specs[spec.name] = spec
        
        return selected_specs, groups
    
    @staticmethod
    def _is_specified(spec: ParameterSpec, yaml_data: dict) -> bool:
        """
        Verifica se un parametro è specificato nell'YAML.
        
        Regole:
        1. Il percorso YAML esiste nel dict
        2. Il valore non è None (a meno che il default non sia None?)
        3. Per liste/dict: se esiste, è specificato
        """
        from shared.utils import get_nested

        value = get_nested(yaml_data, spec.yaml_path, None)
        
        # Caso speciale: default è None ma vogliamo comunque considerarlo specificato?
        # Es: semitones: None nel YAML → consideralo specificato (utente vuole None)
        if value is not None:
            return True
        
        # Se value è None, controlla se la chiave esiste nel percorso completo
        # Naviga manualmente per vedere se la chiave è presente ma con valore None
        keys = spec.yaml_path.split('.')
        current = yaml_data
        
        for key in keys:
            if isinstance(current, dict) and key in current:
                current = current[key]
            else:
                return False  # Chiave non trovata
        
        # Se arriviamo qui, la chiave esiste (anche se il valore è None)
        return True