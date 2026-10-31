import xml.etree.ElementTree as ET
import numpy as np
import pytest
import json
from cdcrd_beamng.scene import write_scene_meshes
from cdcrd_beamng.package import build_package, verify_package


def mesh(layer='detail', **changes):
    return dict(Handle='AB/12', Layer=layer, Color=[.2,.3,.4,1],
                Vertices=[[10,20,2],[11,20,2],[10,21,2]], Triangles=[[0,1,2]], **changes)


def test_visual_layer_has_no_collision_node_and_preserves_coordinates(tmp_path):
    (tmp_path/'art/shapes').mkdir(parents=True)
    meshes, materials, dropped=write_scene_meshes(tmp_path,[mesh()],np.array([10,20,0]),['detail'])
    assert meshes[0]['collision_type']=='None'
    assert materials[0]['color']==[.2,.3,.4,1]
    root=ET.parse(tmp_path/meshes[0]['file'])
    nodes=root.findall('.//{*}node')
    assert not any(n.get('name')=='Colmesh-1' for n in nodes)
    positions=root.find('.//{*}float_array')
    assert list(map(float,positions.text.split()))==[0,0,2,1,0,2,0,1,2]
    assert dropped==0


def test_physical_groups_rebase_triangle_indices(tmp_path):
    (tmp_path/'art/shapes').mkdir(parents=True)
    meshes, _, _=write_scene_meshes(tmp_path,[mesh(),mesh()],np.zeros(3))
    assert meshes[0]['vertices']==6 and meshes[0]['triangles']==2
    root=ET.parse(tmp_path/meshes[0]['file'])
    indices=list(map(int,root.find('.//{*}triangles/{*}p').text.split()))
    assert indices[::3]==[0,1,2,3,4,5]
    assert any(n.get('name')=='Colmesh-1' for n in root.findall('.//{*}node'))


@pytest.mark.parametrize('faces',[[[0,1,8]],[[0.5,1,2]],[[0,0,0]]])
def test_invalid_or_empty_geometry_rejected(tmp_path,faces):
    record=mesh(); record['Triangles']=faces
    with pytest.raises(ValueError):write_scene_meshes(tmp_path,[record],np.zeros(3))


def test_exact_terrain_preserves_native_faces_and_requires_collision(tmp_path):
    terrain = {'vertices_abs_m': [[0,0,10],[16,0,11],[16,16,12],[0,16,10]],
               'triangles': [[0,1,2],[0,2,3]]}
    snapshot = tmp_path/'snapshot.json'
    snapshot.write_text(json.dumps({'schema':'cdcrd.civil3d.snapshot/1','units':'m',
                                    'surfaces':{'terrain':terrain,'road':terrain}}))
    output=tmp_path/'package'
    manifest=build_package(snapshot=snapshot, output=output,level_id='exact',
                           road_is_drivable=True,exact_terrain=True)
    assert manifest['terrain']['representation']=='mesh'
    native=next(m for m in manifest['meshes'] if m['role']=='terrain')
    root=ET.parse(output/native['file'])
    vertices=np.array(list(map(float,root.find('.//{*}float_array').text.split()))).reshape(-1,3)
    assert np.allclose(vertices+manifest['origin_abs_m'],terrain['vertices_abs_m'])
    triangles=list(map(int,root.find('.//{*}triangles/{*}p').text.split()))[::3]
    assert triangles==[0,1,2,0,2,3]
    native['collision_type']='None'
    (output/'manifest.json').write_text(json.dumps(manifest))
    with pytest.raises(ValueError,match='physical terrain mesh'):verify_package(output)
