"""Aislamiento obligatorio: ningun test puede cargar COM ni conectarse a SAFE."""
import sys
import threading
import types
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
com = types.ModuleType('comtypes')
com.client = types.ModuleType('comtypes.client')
def forbidden(*args, **kwargs):
    raise AssertionError('Este test intento usar COM real')
com.CoInitialize = forbidden
com.client.GetActiveObject = forbidden
com.client.CreateObject = forbidden
sys.modules['comtypes'] = com
sys.modules['comtypes.client'] = com.client

import comthread
from Safe import Safe


@pytest.fixture(autouse=True)
def no_com_thread():
    with patch.object(comthread, 'get_executor', return_value=None), \
         patch.object(comthread, '_COM_THREAD_ID', threading.get_ident()):
        yield


@pytest.fixture
def api():
    """Contrato py-> del wrapper/§6, estado sintetico; sin archivos de modelo."""
    model = MagicMock(name='SapModel')
    state = dict(coords={'P1': (1., 2., 3.), 'P2': (4., 5., 6.), 'P3': (7., 8., 9.)},
                 area=['P1', 'P2', 'P3'], prop='S1', opening=False,
                 selected=[], loads=[0.] * 6, units=9, filename='modelo.fdb',
                 effects=True, tables={}, pending=None)

    def coord(name, *args):
        return (*state['coords'][name], 0) if name in state['coords'] else (0., 0., 0., 1)
    model.PointObj.GetCoordCartesian.side_effect = coord
    model.GetModelFilename.side_effect = lambda: state['filename']
    model.GetVersion.return_value = ('23.3.0', 23.3, 0)
    model.GetPresentUnits.side_effect = lambda: state['units']
    model.GetModelIsLocked.return_value = False
    def units(value):
        if state['effects']: state['units'] = value
        return 0
    model.SetPresentUnits.side_effect = units
    model.PointObj.GetAllPoints.return_value = (3, ['P1','P2','P3'], [1.,4.,7.], [2.,5.,8.], [3.,6.,9.], 0)
    model.AreaObj.GetAllAreas.return_value = (1, ['A1'], [1], 3, [2], ['P1','P2','P3'], [1.,4.,7.], [2.,5.,8.], [3.,6.,9.], 0)
    model.AreaObj.GetProperty.side_effect = lambda name: (state['prop'], 0) if state['area'] else ('', 1)
    model.AreaObj.GetPoints.side_effect = lambda name: (len(state['area']), list(state['area']), 0)
    model.AreaObj.GetOpening.side_effect = lambda name: (state['opening'], 0)
    def setprop(name, prop, item=0):
        if state['effects']: state['prop'] = prop
        return 0
    model.AreaObj.SetProperty.side_effect = setprop
    def opening(name, flag, item=0):
        if state['effects']:
            state['opening'] = flag
            if flag: state['prop'] = 'None'
        return 0
    model.AreaObj.SetOpening.side_effect = opening
    def connectivity(name, n, pts):
        if state['effects']: state['area'] = list(pts)
        return 0
    model.EditArea.ChangeConnectivity.side_effect = connectivity
    def addpoint(x,y,z,name='',user=''):
        if state['effects']: state['coords']['NEW'] = (x,y,z)
        return ('NEW', 0)
    model.PointObj.AddCartesian.side_effect = addpoint
    model.AreaObj.AddByCoord.return_value = ([1.,4.,7.],[2.,5.,8.],[3.,6.,9.],'A1',0)
    def clear():
        if state['effects']: state['selected'] = []
        return 0
    model.SelectObj.ClearSelection.side_effect = clear
    def selected():
        return (len(state['selected']), [p[0] for p in state['selected']], [p[1] for p in state['selected']], 0)
    model.SelectObj.GetSelected.side_effect = selected
    for ns, kind in [('PointObj',1),('FrameObj',2),('AreaObj',5)]:
        def select(name, flag, item=0, kind=kind):
            if state['effects']: state['selected'].append((kind,name))
            return 0
        getattr(model, ns).SetSelected.side_effect = select
    def move(dx,dy,dz):
        if state['effects']:
            points = set()
            for kind,name in state['selected']:
                points.update([name] if kind == 1 else state['area'])
            for pt in points: state['coords'][pt] = tuple(a+d for a,d in zip(state['coords'][pt], (dx,dy,dz)))
        return 0
    model.EditGeneral.Move.side_effect = move
    def delete(name, item=0):
        if state['effects']: state['area'] = []
        return 0
    model.AreaObj.Delete.side_effect = delete
    def deletepoint(name, item=0):
        if state['effects']: state['coords'].pop(name, None)
        return 0
    model.PointObj.DeleteSpecialPoint.side_effect = deletepoint
    def load(name, pattern, vals, replace=False, csys='Global', item=0):
        if state['effects']: state['loads'] = [a+(0 if replace else b) for a,b in zip(vals, state['loads'])]
        return (list(vals), 0)
    model.PointObj.SetLoadForce.side_effect = load
    model.PointObj.GetLoadForce.side_effect = lambda name: (1,[name],['Dead'],[0],['Global'], *[[v] for v in state['loads']], 0)
    for ns, methods in {
        'PropMaterial':['SetMaterial','SetMPIsotropic','SetOConcrete_1','SetOConcrete','SetWeightAndMass','SetORebar_1','SetORebar'],
        'PropArea':['SetSlab'], 'PropAreaSpring':['SetAreaSpringProp'],
        'AreaObj':['SetSpringAssignment'], 'LoadPatterns':['Add'],
        'RespCombo':['Add','SetCaseList'], 'Analyze':['RunAnalysis'],
        'File':['Save','ImportFile','ExportFile'], 'View':['RefreshView'],
        'DesignConcreteSlab':['StartSlabDesign'],
    }.items():
        for method in methods: getattr(getattr(model,ns),method).return_value = 0
    model.PropArea.GetSlab.return_value = (6,2,'C1',400.,-1,'','guid',0)
    model.Analyze.GetCaseStatus.return_value = (1,['Dead'],[4],0)
    design = model.DesignConcreteSlab
    design.GetSummaryResultsFlexureAndShear.return_value = (*[[v] for v in ['L1','STRIP1','SPAN1','start','C1',11.,12.,'C2',13.,14.,'C3',15.,16.,'OK','A']],0)
    design.GetFlexureAndShear.return_value = (*[[v] for v in ['L1','STRIP1',1.,500.,'C1',11.,12.,13.,'C2',14.,15.,16.,17.,'C3',18.,19.,'OK',20.,21.,'A']],0)
    design.GetSummaryResultsSpanDefinition.return_value = (*[[v] for v in ['L1','STRIP1','SPAN1',10.,0.,10.,1.,2.,3.,4.]],0)
    design.DesignStrip.GetNameList.return_value = (1,['STRIP1'],0)
    design.DesignStrip.GetDesignStrip_1.return_value = (0,['P1','P2'],[1.,4.],[2.,5.],[3.,6.],[10.],[20.],[30.],[40.],[False],0)
    def openfile(path):
        if state['effects']: state['filename'] = path
        return 0
    model.File.OpenFile.side_effect = openfile
    model.File.NewBlank.side_effect = lambda: openfile('')
    # Estos esquemas se escriben explicitamente, independientes de las constantes de Safe.
    strip_fields = ['Name','NumSegs','StartPoint','EndPoint','WStartLeft','WStartRight','WEndLeft','WEndRight','AutoWiden','Layer','GUID']
    punch_fields = ['UniqueName','CheckPunchingShear','LocationType','Perimeter','EffDepthType','OpeningDef','RebarType']
    state['tables'] = {
        'Strip Object Connectivity': (strip_fields, [['STRIP1','1','P1','P2','10','20','30','40','No','A','g1']]),
        'Concrete Slab Design Overwrites - Punching Shear - General': (punch_fields, [['P1','Program Determined','Auto','Auto','Auto','Auto','None']]),
        'Spring Property Definitions - Area Springs': (['Name','NonlinOpt3','StiffU1','StiffU2','StiffU3'], [['SOIL','Compression Only','0','0','30']]),
        'Area Assignments - Area Springs': (['UniqueName','SpringProp'], [['A1','SOIL']]),
        'Soil Pressure': (['Name','Value'], [['P1','10']]),
    }
    db = model.DatabaseTables
    db.GetAvailableTables.side_effect = lambda: (len(state['tables']),list(state['tables']),list(state['tables']),[2]*len(state['tables']),0)
    def read(key, fields, group, version):
        columns, rows = state['tables'][key]
        return (list(fields),7,list(columns),len(rows),[v for row in rows for v in row],0)
    db.GetTableForDisplayArray.side_effect = read
    def metadata(key):
        cols,_ = state['tables'][key]
        return (7,len(cols),list(cols),list(cols),['desc']*len(cols),['']*len(cols),[f!='NumSegs' for f in cols],0)
    db.GetAllFieldsInTable.side_effect = metadata
    def queue(key, version, fields, n, flat):
        assert version == 7
        assert len(flat) == n * len(fields)
        state['pending'] = (key,list(fields),n,list(flat))
        return (version,list(fields),list(flat),0)
    db.SetTableForEditingArray.side_effect = queue
    def apply(fill):
        if state['effects']:
            key, fields, n, flat = state['pending']
            columns, old = state['tables'][key]
            rows=[]
            for i in range(n):
                values=dict(zip(fields,flat[i*len(fields):(i+1)*len(fields)]))
                values.setdefault('NumSegs','1')
                if values.get('GUID') == '': values['GUID']='generated-guid'
                rows.append([values[c] for c in columns])
            state['tables'][key] = (columns,rows)
        return (0,0,0,0,'',0)
    db.ApplyEditedTables.side_effect = apply
    safe = Safe()
    with patch.object(Safe, '_model', return_value=model), \
         patch('Safe.os.path.isfile',return_value=True), \
         patch('Safe.os.path.isdir',return_value=True), \
         patch('Safe.os.path.exists',return_value=False), \
         patch('Safe.os.path.getsize',return_value=123), \
         patch('Safe.os.makedirs'), patch('Safe.os.listdir',return_value=[]), \
         patch('shutil.copy2'):
        yield safe, model, state
