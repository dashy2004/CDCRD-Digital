import importlib.util
from pathlib import Path
import tempfile
import unittest
import xml.etree.ElementTree as ET

spec=importlib.util.spec_from_file_location('people_meshes',Path(__file__).resolve().parents[1]/'tools/tech/people_meshes.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)


class PeopleMeshTest(unittest.TestCase):
    def test_material_faces_and_bindings_survive_visual_export(self):
        with tempfile.TemporaryDirectory() as folder:
            target=Path(folder)/'person.dae'
            module.write_pose(target,[[0,0,0],[1,0,0],[1,0,1],[0,0,1]],
                              [[0,1,2],[0,2,3]],['Skin','Shirt'],'actor_')
            root=ET.parse(target).getroot();ns={'c':module.NS}
            groups=root.findall('.//c:triangles',ns)
            self.assertEqual({g.get('material') for g in groups},{'actor_Skin','actor_Shirt'})
            self.assertEqual(sum(int(g.get('count')) for g in groups),2)
            binding=root.findall('.//c:instance_material',ns)
            self.assertEqual({m.get('target') for m in binding},{'#actor_Skin','#actor_Shirt'})
            self.assertNotIn('Colmesh-1',target.read_text())
