"""Export inspected, posed character meshes to static COLLADA animation frames.

The input is a private Blender bake. Characters are visual actors only; they
are not biomechanical pedestrians and must never be used to infer injuries.
"""
import argparse
from copy import deepcopy
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import xml.etree.ElementTree as ET

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from cdcrd_beamng.collada import NS, element, write_road_dae


def add_box(vertices, faces, materials, center, size, material):
    n = len(vertices)
    vertices.extend([[center[k] + size[k] * (.5 if i & (1 << k) else -.5)
                      for k in range(3)] for i in range(8)])
    triangles = [(0,2,3),(0,3,1),(4,5,7),(4,7,6),(0,1,5),(0,5,4),
                 (2,6,7),(2,7,3),(0,4,6),(0,6,2),(1,3,7),(1,7,5)]
    faces.extend([[n+i for i in f] for f in triangles]);materials.extend([material]*12)


def write_pose(path, vertices, faces, labels, prefix):
    geometry = SimpleNamespace(vertices=np.asarray(vertices), triangles=np.asarray(faces))
    write_road_dae(path, geometry, np.zeros(3), np.ones(len(faces), dtype=bool),
                   material_names=(prefix+'Skin', prefix+'unused'), collision=False)
    tree = ET.parse(path);root = tree.getroot();q = lambda s: '{'+NS+'}'+s
    mesh = root.find('.//'+q('mesh'));template = mesh.find(q('triangles'));mesh.remove(template)
    effects = root.find(q('library_effects'));materials = root.find(q('library_materials'))
    effect_template=deepcopy(effects[0]);material_template=deepcopy(materials[0]);effects.clear();materials.clear()
    binding = root.find('.//'+q('bind_material')+'/'+q('technique_common'));binding.clear()
    for label in sorted(set(labels)):
        name = prefix+label
        effect=deepcopy(effect_template);effect.set('id',name+'-effect');effects.append(effect)
        material=deepcopy(material_template);material.set('id',name);material.set('name',name)
        material.find(q('instance_effect')).set('url','#'+name+'-effect');materials.append(material)
        indices=[i for i,m in enumerate(labels) if m==label]
        triangles=deepcopy(template);triangles.set('count',str(len(indices)));triangles.set('material',name)
        triangles.find(q('p')).text=' '.join(str(v) for i in indices for j in faces[i] for v in (j,i,j))
        mesh.append(triangles)
        target=element(binding,'instance_material',symbol=name,target='#'+name)
        element(target,'bind_vertex_input',semantic='UVMap',input_semantic='TEXCOORD',input_set=0)
    tree.write(path, encoding='utf-8', xml_declaration=True)


def export(source, output):
    if output.exists():raise FileExistsError(output)
    poses=json.loads(source.read_text());output.mkdir(parents=True)
    colors={'Skin':[.48,.28,.17,1],'Eyes':[.015,.015,.018,1],'Hair':[.06,.055,.05,1],
            'Hair2':[.09,.08,.07,1],'Shirt':[.32,.33,.36,1],'Shirt2':[.32,.33,.36,1],
            'Pants':[.035,.06,.11,1],'Socks':[.12,.12,.14,1],'Shoes':[.025,.025,.03,1],
            'Backpack':[.12,.21,.36,1]}
    result={};mats={}
    for kind in ['adult','student']:
        prefix='cdx_actor_'+kind+'_';result[kind]=[]
        for index,pose in enumerate(poses if kind=='student' else poses[:1]):
            vertices=deepcopy(pose['vertices']);faces=deepcopy(pose['triangles']);labels=list(pose['materials'])
            if kind=='adult':
                # Glasses sit on the inspected eye plane; geometry stays private
                # to the character export and does not modify the source rig.
                for x in [-.033,.033]:
                    for dx,dz,sx,sz in [(0,.02,.062,.004),(0,-.02,.062,.004),(-.031,0,.004,.04),(.031,0,.004,.04)]:
                        add_box(vertices,faces,labels,[x+dx,-.16,1.587+dz],[sx,.006,sz],'Eyes')
                add_box(vertices,faces,labels,[0,-.16,1.59],[.012,.006,.004],'Eyes')
            else:
                add_box(vertices,faces,labels,[0,.15,1.11],[.23,.15,.31],'Backpack')
                vertices=(np.asarray(vertices)*(1.4/1.72)).tolist()
            name=kind+'_'+str(index).zfill(2)+'.dae';write_pose(output/name,vertices,faces,labels,prefix);result[kind].append(name)
        for label,color in colors.items():
            if kind=='student' and label in ['Shirt','Shirt2']:color=[.35,.60,.83,1]
            name=prefix+label
            mats[name]={'name':name,'mapTo':name,'class':'Material','version':1.5,'doubleSided':True,
                        'Stages':[{'baseColorFactor':color,'roughnessFactor':1,'metallicFactor':0}]}
    (output/'materials.json').write_text(json.dumps(mats,indent=2))
    (output/'poses.json').write_text(json.dumps(result,indent=2))
    print('EXPORTED_VISUAL_ACTORS', {k:len(v) for k,v in result.items()})


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('source',type=Path);p.add_argument('output',type=Path)
    a=p.parse_args();export(a.source,a.output)
