"""Convert native scene meshes while retaining transformed vertices and colours."""
from collections import defaultdict
from types import SimpleNamespace

import numpy as np

from .collada import write_road_dae


def write_scene_meshes(root, records, origin, visual_layers=()):
    groups = defaultdict(list)
    dropped = 0
    for record in records:
        vertices = np.asarray(record['Vertices'], dtype=float)
        raw_faces = np.asarray(record['Triangles'])
        color = np.asarray(record['Color'], dtype=float)
        if (vertices.ndim != 2 or vertices.shape[1] != 3 or not np.isfinite(vertices).all()
                or raw_faces.ndim != 2 or raw_faces.shape[1] != 3
                or raw_faces.dtype.kind not in 'iu' or not raw_faces.size
                or raw_faces.min() < 0 or raw_faces.max() >= len(vertices)
                or color.shape != (4,) or not np.isfinite(color).all()
                or (color < 0).any() or (color > 1).any()):
            raise ValueError('Invalid native scene mesh: ' + str(record.get('Handle')))
        faces = raw_faces.astype(np.int64)
        points = vertices[faces]
        keep = np.linalg.norm(np.cross(points[:, 1]-points[:, 0], points[:, 2]-points[:, 0]),axis=1) > 1e-12
        dropped += int((~keep).sum())
        if not keep.any():
            raise ValueError('Entire scene mesh is degenerate: ' + str(record.get('Handle')))
        key = (tuple(color.tolist()), record['Layer'] not in visual_layers)
        groups[key].append((vertices, faces[keep], record['Handle'], record['Layer']))
    meshes, materials = [], []
    for index, ((color, collision), parts) in enumerate(sorted(groups.items())):
        name = f'cdx_scene_{index:03d}'
        vertices, faces, count = [], [], 0
        for v, f, _, _ in parts:
            vertices.append(v); faces.append(f + count); count += len(v)
        geometry = SimpleNamespace(vertices=np.concatenate(vertices), triangles=np.concatenate(faces))
        filename = f'art/shapes/scene_{index:03d}.dae'
        write_road_dae(root / filename, geometry, origin, np.ones(len(geometry.triangles),dtype=bool),
                       material_names=(name, name+'_unused'), collision=collision)
        materials.append(dict(name=name,color=list(color),ground_type='CONCRETE'))
        meshes.append(dict(file=filename,role='scene',name=name,material=name,
            collision_type='Collision Mesh' if collision else 'None',
            vertices=count,triangles=len(geometry.triangles),
            source_handles=[p[2] for p in parts],source_layers=sorted({p[3] for p in parts})))
    return meshes, materials, dropped
