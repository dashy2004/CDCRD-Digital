"""Regression of the actual IronPython handler with a transaction-aware fake API."""

import ast
import copy
from pathlib import Path
from types import SimpleNamespace

import pytest

SCRIPT = (
    Path(__file__).parents[1] / "revit/PanelLosas.extension/CDCRD Losas.tab/"
    "Losas.panel/UsoLosa.pushbutton/script.py"
)


class Parameter:
    StorageType = "String"
    IsReadOnly = False

    def __init__(self, value=""):
        self.value = value
        self.accept_set = True

    def AsString(self):
        return self.value

    def Set(self, value):
        if not self.accept_set:
            return False
        self.value = value
        return True


class Floor:
    def __init__(self, identity):
        self.Id = identity
        self.parameters = {}

    def LookupParameter(self, name):
        return self.parameters.get(name)

    def GetParameters(self, name):
        p = self.LookupParameter(name)
        return [] if p is None else [p]


class FakeDocument:
    Title = "SYNTHETIC-FLOORS"

    def __init__(self, count=42):
        self.floors = [Floor(i + 1) for i in range(count)]
        self.transactions = []
        self.stages = []
        self.delayed = []
        self.delayed_binding = False
        self.commit_results = []
        self.binding_ok = True
        self.start_result = "Started"
        self.after_commit = None
        self.corrupted = False
        self.log_failure = None

    def GetElement(self, identity):
        return next((f for f in self.floors if f.Id == identity), None)

    def Regenerate(self):
        raise AssertionError("Manual Regenerate is forbidden")

    def bind(self, _doc, name):
        if not self.binding_ok:
            raise RuntimeError("binding rejected")
        if self.delayed_binding:
            self.delayed.append(name)
        else:
            for f in self.floors:
                f.parameters[name] = Parameter()


class Transaction:
    def __init__(self, doc, title):
        self.doc, self.title = doc, title
        self.status = "Uninitialized"
        self.rollbacks = 0
        self.disposed = False
        doc.transactions.append(self)

    def Start(self):
        self.backup = copy.deepcopy([f.parameters for f in self.doc.floors])
        self.status = self.doc.start_result
        return self.status

    def GetFailureHandlingOptions(self):
        return self

    def SetClearAfterRollback(self, value):
        assert value is True
        return self

    def SetForcedModalHandling(self, value):
        assert value is True
        return self

    def SetFailureHandlingOptions(self, options):
        assert options is self
        return self

    def Commit(self):
        self.status = (
            self.doc.commit_results.pop(0) if self.doc.commit_results else "Committed"
        )
        if isinstance(self.status, Exception):
            self.doc.corrupted = True
            error, self.status = self.status, "Started"
            raise error
        if self.status == "Committed":
            for name in self.doc.delayed:
                for f in self.doc.floors:
                    f.parameters[name] = Parameter()
            self.doc.delayed = []
            if self.doc.after_commit:
                self.doc.after_commit(self)
        elif self.status == "RolledBack":
            self.restore()
        return self.status

    def restore(self):
        for f, original in zip(self.doc.floors, self.backup):
            f.parameters = copy.deepcopy(original)
        self.doc.delayed = []

    def RollBack(self):
        assert self.status == "Started"
        self.rollbacks += 1
        self.restore()
        self.status = "RolledBack"
        return self.status

    def GetStatus(self):
        return self.status

    def Dispose(self):
        assert self.status != "Pending"
        self.disposed = True


@pytest.fixture
def harness():
    doc = FakeDocument()
    tree = ast.parse(SCRIPT.read_text(encoding="utf-8"))
    cls = next(
        n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "PanelUsoLosa"
    )
    method = next(
        n
        for n in cls.body
        if isinstance(n, ast.FunctionDef) and n.name == "_escribir_params"
    )
    helpers = [
        n
        for n in tree.body
        if isinstance(n, ast.FunctionDef) and n.name == "_parametro_escritura"
    ]
    statuses = SimpleNamespace(
        Started="Started",
        Committed="Committed",
        RolledBack="RolledBack",
        Pending="Pending",
    )

    def record(event, **data):
        if doc.log_failure == event:
            raise OSError("log unavailable")
        doc.stages.append((event, data))

    scope = {
        "DB": SimpleNamespace(
            Transaction=Transaction,
            TransactionStatus=statuses,
            StorageType=SimpleNamespace(String="String"),
        ),
        "_crear_parametro_texto": doc.bind,
        "_log_parametros": record,
        "MessageBox": SimpleNamespace(
            Show=lambda text: doc.stages.append(("dialog", text))
        ),
    }
    exec(
        compile(
            ast.Module(body=helpers + [method], type_ignores=[]), str(SCRIPT), "exec"
        ),
        scope,
    )  # noqa: S102 -- Only local handler, no Revit/UI imports.
    panel = SimpleNamespace(
        doc=doc,
        filas=[{"el": f, "mark": "L%02d" % i} for i, f in enumerate(doc.floors)],
    )
    writes = {"Uso_Losa": {f["mark"]: "residential" for f in panel.filas}}
    return (
        doc,
        panel,
        writes,
        lambda data=writes: scope["_escribir_params"](
            panel, data, "synthetic parameters"
        ),
    )


def test_first_write_42_floors_without_manual_regeneration(harness):
    doc, panel, writes, run = harness
    assert run() == 42
    assert len(doc.transactions) == 1
    assert all(
        f.LookupParameter("Uso_Losa").AsString() == "residential" for f in doc.floors
    )


def test_commit_rollback_is_not_reported_as_saved(harness):
    doc, panel, writes, run = harness
    for f in doc.floors:
        f.parameters["Uso_Losa"] = Parameter("old")
    doc.commit_results = ["RolledBack"]
    with pytest.raises(Exception, match="RolledBack"):
        run()
    assert all(f.LookupParameter("Uso_Losa").AsString() == "old" for f in doc.floors)


def test_no_op_does_not_create_transaction(harness):
    doc, panel, writes, run = harness
    for f in doc.floors:
        f.parameters["Uso_Losa"] = Parameter("residential")
    assert run() == 0
    assert not doc.transactions


def test_delayed_bindings_require_two_verified_commits(harness):
    doc, panel, writes, run = harness
    doc.delayed_binding = True
    assert run() == 42
    assert len(doc.transactions) == 2
    assert all(t.status == "Committed" and t.disposed for t in doc.transactions)
    assert all(
        f.LookupParameter("Uso_Losa").AsString() == "residential" for f in doc.floors
    )
    assert "bindings_committed_values_pending" in [event for event, _ in doc.stages]


def test_binding_rejection_rolls_back_and_propagates(harness):
    doc, panel, writes, run = harness
    doc.binding_ok = False
    with pytest.raises(RuntimeError, match="binding rejected"):
        run()
    assert doc.transactions[0].rollbacks == 1
    assert all(not f.parameters for f in doc.floors)


@pytest.mark.parametrize("result", ["RolledBack", "Pending"])
def test_failed_binding_commit_never_starts_value_transaction(harness, result):
    doc, panel, writes, run = harness
    doc.delayed_binding = True
    doc.commit_results = [result]
    with pytest.raises(Exception, match=result):
        run()
    assert len(doc.transactions) == 1
    assert not any(event == "set_before" for event, _ in doc.stages)
    if result == "Pending":
        assert panel._params_pending is doc.transactions[0]
        assert not doc.transactions[0].disposed
        with pytest.raises(Exception, match="pendiente"):
            run()
        assert len(doc.transactions) == 1


def test_false_set_rolls_back_earlier_values(harness):
    doc, panel, writes, run = harness
    for f in doc.floors:
        f.parameters["Uso_Losa"] = Parameter("old")
    doc.floors[-1].parameters["Uso_Losa"].accept_set = False
    with pytest.raises(Exception, match="Set rechazado"):
        run()
    assert doc.transactions[0].rollbacks == 1
    assert all(f.LookupParameter("Uso_Losa").AsString() == "old" for f in doc.floors)


def test_readback_mismatch_is_not_reported_as_saved(harness):
    doc, panel, writes, run = harness
    doc.after_commit = lambda tx: setattr(
        doc.floors[-1].parameters["Uso_Losa"], "value", "changed"
    )
    with pytest.raises(Exception, match="relectura distinta"):
        run()
    assert doc.transactions[0].status == "Committed"
    assert doc.transactions[0].rollbacks == 0
    assert not any(event == "verified" for event, _ in doc.stages)


def test_unavailable_binding_after_commit_stops_before_any_set(harness):
    doc, panel, writes, run = harness
    doc.delayed_binding = True
    doc.after_commit = lambda tx: doc.floors[-1].parameters.clear()
    with pytest.raises(Exception, match="no disponible"):
        run()
    assert len(doc.transactions) == 1
    assert not any(event == "set_before" for event, _ in doc.stages)


def test_commit_exception_does_not_inspect_elements_after_failure(harness):
    doc, panel, writes, run = harness
    doc.commit_results = [RuntimeError("regeneration failure")]
    original = doc.GetElement

    def guarded_get(identity):
        assert not doc.corrupted
        return original(identity)

    doc.GetElement = guarded_get
    with pytest.raises(RuntimeError, match="regeneration failure"):
        run()
    assert doc.transactions[0].rollbacks == 1
    assert doc.transactions[0].disposed


@pytest.mark.parametrize(
    "problem", ["readonly", "storage", "duplicate", "deleted", "mark"]
)
def test_invalid_targets_fail_before_opening_transaction(harness, problem):
    doc, panel, writes, run = harness
    last = doc.floors[-1]
    p = Parameter("old")
    last.parameters["Uso_Losa"] = p
    if problem == "readonly":
        p.IsReadOnly = True
    elif problem == "storage":
        p.StorageType = "Integer"
    elif problem == "duplicate":
        last.GetParameters = lambda name: [p, Parameter()]
    elif problem == "deleted":
        doc.floors.remove(last)
    elif problem == "mark":
        panel.filas.append(panel.filas[-1])
    with pytest.raises(Exception):
        run()
    assert not doc.transactions


def test_failed_start_does_not_create_bindings(harness):
    doc, panel, writes, run = harness
    doc.start_result = "Error"
    with pytest.raises(Exception, match="Transaction.Start"):
        run()
    assert all(not f.parameters for f in doc.floors)
    assert doc.transactions[0].disposed


def test_all_five_parameter_fields_are_verified_and_then_idempotent(harness):
    doc, panel, writes, run = harness
    for name in ["Seccion_Losa", "Acero_X", "Acero_Y", "Acero_Apoyo"]:
        writes[name] = {f["mark"]: "synthetic value" for f in panel.filas}
    assert run() == 210
    assert all(len(f.parameters) == 5 for f in doc.floors)
    assert run() == 0
    assert len(doc.transactions) == 1


def load_function(name, scope):
    tree = ast.parse(SCRIPT.read_text(encoding="utf-8"))
    function = next(
        n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == name
    )
    exec(
        compile(ast.Module(body=[function], type_ignores=[]), str(SCRIPT), "exec"),
        scope,
    )
    return scope[name]


@pytest.mark.parametrize("previous", ["", "existing-shared-parameters.txt"])
@pytest.mark.parametrize("insert_ok", [True, False])
def test_binding_restores_application_setting_even_when_insert_fails(
    tmp_path, monkeypatch, previous, insert_ok
):
    import os
    import tempfile

    monkeypatch.setattr(tempfile, "gettempdir", lambda: str(tmp_path))
    group = SimpleNamespace(
        Name="test", Definitions=SimpleNamespace(get_Item=lambda name: object())
    )
    app = SimpleNamespace(
        SharedParametersFilename=previous,
        OpenSharedParameterFile=lambda: SimpleNamespace(Groups=[group]),
        Create=SimpleNamespace(
            NewCategorySet=lambda: SimpleNamespace(Insert=lambda cat: None),
            NewInstanceBinding=lambda cats: object(),
        ),
    )
    doc = SimpleNamespace(
        Application=app,
        Settings=SimpleNamespace(
            Categories=SimpleNamespace(get_Item=lambda cat: object())
        ),
        ParameterBindings=SimpleNamespace(Insert=lambda *args: insert_ok),
    )
    db = SimpleNamespace(
        BuiltInCategory=SimpleNamespace(OST_Floors="floor"),
        GroupTypeId=SimpleNamespace(Data="Data"),
    )
    bind = load_function(
        "_crear_parametro_texto", {"os": os, "DB": db, "GRUPO_PARAMS": "test"}
    )
    if insert_ok:
        bind(doc, "Uso_Losa")
    else:
        with pytest.raises(Exception, match="Binding rechazado"):
            bind(doc, "Uso_Losa")
    assert app.SharedParametersFilename == previous


def test_real_log_appends_complete_json_lines(tmp_path, monkeypatch):
    import io
    import json
    import os
    import tempfile

    monkeypatch.setattr(tempfile, "gettempdir", lambda: str(tmp_path))
    log = load_function("_log_parametros", {"os": os, "io": io, "json": json})
    log("commit_before", sesion="synthetic", parametro="Sección")
    log("commit_after", sesion="synthetic", estado="Committed")
    records = [
        json.loads(line)
        for line in (tmp_path / "plugin_losas_parametros.jsonl")
        .read_text()
        .splitlines()
    ]
    assert [r["evento"] for r in records] == ["commit_before", "commit_after"]
    assert records[0]["parametro"] == "Sección"
    assert all(r["utc"] and r["sesion"] == "synthetic" for r in records)


@pytest.mark.parametrize("event", ["begin", "set_after"])
def test_log_failure_stops_and_rolls_back_if_started(harness, event):
    doc, panel, writes, run = harness
    doc.log_failure = event
    with pytest.raises(OSError, match="log unavailable"):
        run()
    assert all(not f.parameters for f in doc.floors)
    if event == "begin":
        assert not doc.transactions
    else:
        assert doc.transactions[0].rollbacks == 1


def test_second_commit_failure_preserves_only_created_bindings(harness):
    doc, panel, writes, run = harness
    doc.delayed_binding = True
    doc.commit_results = ["Committed", "RolledBack"]
    with pytest.raises(Exception, match="RolledBack"):
        run()
    assert len(doc.transactions) == 2
    assert all(f.LookupParameter("Uso_Losa").AsString() == "" for f in doc.floors)
    assert not any(event == "verified" for event, _ in doc.stages)


def test_commit_return_and_final_status_must_both_confirm(harness):
    doc, panel, writes, run = harness
    # A finalizer can change GetStatus after Commit returns. Keep return independent.
    original_commit = Transaction.Commit

    def finalized_commit(self):
        result = original_commit(self)
        self.status = "RolledBack"
        return result

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(Transaction, "Commit", finalized_commit)
        with pytest.raises(Exception, match="Committed / RolledBack"):
            run()
    assert not any(event == "verified" for event, _ in doc.stages)


def test_guardar_reports_error_without_success_dialog():
    dialogs = []
    scope = {
        "MessageBox": SimpleNamespace(Show=dialogs.append),
        "_registrar_error": lambda text: "synthetic-error.log",
        "PARAM_USO": "Uso_Losa",
        "PARAM_SECCION": "Seccion_Losa",
        "PARAM_ACERO_X": "Acero_X",
        "PARAM_ACERO_Y": "Acero_Y",
        "PARAM_ACERO_APOYO": "Acero_Apoyo",
    }
    load_function("_seguro", scope)
    tree = ast.parse(SCRIPT.read_text(encoding="utf-8"))
    cls = next(
        n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "PanelUsoLosa"
    )
    method = next(
        n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == "guardar"
    )
    exec(
        compile(ast.Module(body=[method], type_ignores=[]), str(SCRIPT), "exec"), scope
    )

    def rejected(*args):
        raise RuntimeError("Commit rejected")

    panel = SimpleNamespace(
        _seleccion=lambda: {"L01": "residential"},
        _secciones=lambda **kwargs: {},
        _aceros=lambda: {},
        _escribir_params=rejected,
    )
    scope["guardar"](panel, None, None)
    assert len(dialogs) == 1
    assert "Commit rejected" in dialogs[0]
    assert "valores guardados" not in dialogs[0]
