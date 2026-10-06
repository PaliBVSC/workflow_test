"""Build the fin facade in the running Archicad through the Tapir add-on.

    python build_facade.py [--settings fin-facade.json] [--origin X Y] [--keep]

--settings  a file saved with "Save .json" in the webapp. Without it the webapp defaults are used.
--origin    plan position of the facade's left end (default 0 0).
--keep      keep the elements of the previous build instead of replacing them.

Mapping: facade length runs along Archicad X, the facade faces -Y (south elevation),
fins become Columns, horizontal elements become Beams. All go on the Ground Floor,
on the layers "Facade - Fins" and "Facade - Horizontals".
"""
import argparse
import json
import os
import subprocess
import sys
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
LAST_BUILD = os.path.join(HERE, 'last_build.json')
MODEL = os.path.join(HERE, 'facade_model.json')
PORT = 19723
BATCH = 300


def tapir(name, params=None):
    body = {'command': 'API.ExecuteAddOnCommand', 'parameters': {
        'addOnCommandId': {'commandNamespace': 'TapirCommand', 'commandName': name},
        'addOnCommandParameters': params or {}}}
    req = urllib.request.Request(f'http://127.0.0.1:{PORT}', json.dumps(body).encode(), {'Content-Type': 'application/json'})
    res = json.load(urllib.request.urlopen(req, timeout=600))
    if not res.get('succeeded'):
        raise RuntimeError(f'{name} failed: {res.get("error", res)}')
    return res['result']['addOnCommandResponse']


def created_ids(response, what):
    ids, errors = [], 0
    for e in response['elements']:
        if 'elementId' in e:
            ids.append(e['elementId'])
        else:
            errors += 1
            if errors <= 3:
                print(f'  {what} not created: {e.get("error", e)}')
    return ids, errors


def layer_index(name):
    tapir('CreateLayers', {'layerDataArray': [{'name': name}], 'overwriteExisting': False})
    for a in tapir('GetAttributesByType', {'attributeType': 'Layer'})['attributes']:
        if a.get('name') == name:
            return a['index']
    raise RuntimeError(f'Layer "{name}" not found after creating it')


def set_layer(ids, index):
    for i in range(0, len(ids), BATCH):
        tapir('SetDetailsOfElements', {'elementsWithDetails': [
            {'elementId': e, 'details': {'layerIndex': index}} for e in ids[i:i + BATCH]]})


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--settings')
    ap.add_argument('--origin', nargs=2, type=float, default=[0.0, 0.0])
    ap.add_argument('--keep', action='store_true')
    args = ap.parse_args()

    cmd = ['node', os.path.join(HERE, 'export_model.js')] + ([args.settings] if args.settings else []) + [MODEL]
    subprocess.run(cmd, check=True)
    with open(MODEL, encoding='utf8') as f:
        model = json.load(f)
    ox, oy = args.origin

    if not args.keep and os.path.exists(LAST_BUILD):
        with open(LAST_BUILD, encoding='utf8') as f:
            old = json.load(f)
        if old:
            print(f'Removing {len(old)} elements from the previous build')
            for i in range(0, len(old), 1000):
                tapir('DeleteElements', {'elements': [{'elementId': e} for e in old[i:i + 1000]]})

    fins_layer = layer_index('Facade - Fins')
    hors_layer = layer_index('Facade - Horizontals')

    fins = [{
        'coordinates': {'x': ox + f['x'], 'y': oy - f['depth'] / 2, 'z': f['y0']},
        'height': f['y1'] - f['y0'], 'width': f['width'], 'depth': f['depth'],
        'isWidthAndHeightLinked': False, 'coreAnchor': 'Center', 'floorIndex': 0,
    } for f in model['fins']]
    hors = [{
        'begCoordinate': {'x': ox + h['x0'], 'y': oy - h['z']},
        'endCoordinate': {'x': ox + h['x1'], 'y': oy - h['z']},
        'zCoordinate': h['y'], 'width': h['depth'], 'height': h['thickness'],
        'isWidthAndHeightLinked': False, 'anchorPoint': 'Center', 'floorIndex': 0,
    } for h in model['horizontals']]

    fin_ids, hor_ids, errs = [], [], 0
    for i in range(0, len(fins), BATCH):
        ids, e = created_ids(tapir('CreateColumns', {'columnsData': fins[i:i + BATCH]}), 'Fin')
        fin_ids += ids; errs += e
    print(f'Fins: {len(fin_ids)} columns')
    for i in range(0, len(hors), BATCH):
        ids, e = created_ids(tapir('CreateBeams', {'beamsData': hors[i:i + BATCH]}), 'Horizontal')
        hor_ids += ids; errs += e
        print(f'  horizontals {len(hor_ids)}/{len(hors)}', end='\r')
    print(f'Horizontals: {len(hor_ids)} beams      ')

    with open(LAST_BUILD, 'w', encoding='utf8') as f:
        json.dump(fin_ids + hor_ids, f)
    set_layer(fin_ids, fins_layer)
    set_layer(hor_ids, hors_layer)
    print(f'Done. {errs} elements failed.' if errs else 'Done.')


if __name__ == '__main__':
    try:
        main()
    except urllib.error.URLError:
        sys.exit(f'Archicad is not answering on port {PORT}. Open a project in Archicad with Tapir loaded.')
