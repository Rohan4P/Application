import json
from PySide6.QtCore import QSettings


def load_connections():
    try:
        settings = QSettings("VMS", "Connections")
        connections_json = settings.value("connections", "[]")
        return json.loads(connections_json)
    except Exception as e:
        print(f"Error loading connections: {e}")
        return []


def save_connections(connections):
    try:
        settings = QSettings("VMS", "Connections")
        settings.setValue("connections", json.dumps(connections))
    except Exception as e:
        print(f"Error saving connections: {e}")


def load_presets():
    """Load presets from QSettings with validation and migration support"""
    try:
        settings = QSettings("VMS", "Presets")
        presets_json = settings.value("presets", "[]")
        loaded_presets = json.loads(presets_json)

        # Validate and migrate old preset format if needed
        valid_presets = []
        for preset in loaded_presets:
            # If preset is in old format (just number/name), convert to new format
            if isinstance(preset, dict) and 'number' in preset:
                # This is already the new format
                valid_presets.append(preset)
            elif isinstance(preset, (list, tuple)) and len(preset) >= 2:
                # Convert old [number, name] format to new dict format
                valid_presets.append({
                    'number': preset[0],
                    'name': preset[1],
                    'type': 'positional' if preset[0] <= 79 else 'functional'
                })

        # Sort presets by number for consistency
        valid_presets.sort(key=lambda x: x['number'])
        return valid_presets

    except Exception as e:
        print(f"Error loading presets: {e}")
        # Return default empty list while preserving error for debugging
        return []


def save_presets(presets):
    """Save presets to QSettings with validation and backup"""
    try:
        # Validate presets before saving
        valid_presets = []
        seen_numbers = set()

        for preset in presets:
            # Basic validation
            if not isinstance(preset, dict):
                continue

            if 'number' not in preset or not isinstance(preset['number'], int):
                continue

            # Check for duplicates
            if preset['number'] in seen_numbers:
                continue
            seen_numbers.add(preset['number'])

            # Ensure type is set correctly based on number
            preset['type'] = 'positional' if preset['number'] <= 79 else 'functional'

            # Ensure name exists
            if 'name' not in preset or not preset['name']:
                preset['name'] = f"Preset {preset['number']}"

            valid_presets.append(preset)

        # Create backup before saving
        settings = QSettings("VMS", "Presets")
        current_presets = settings.value("presets", "[]")
        settings.setValue("presets_backup", current_presets)

        # Save the validated presets
        settings.setValue("presets", json.dumps(valid_presets))

    except Exception as e:
        print(f"Error saving presets: {e}")
