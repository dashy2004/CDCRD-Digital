// Open drawings of the running session: list, open, activate and close without saving.
// Runs in the application context (session command): no document lock, no dialogs, never a save.
using System;
using System.IO;
using System.Linq;
using System.Text.Json.Nodes;
using Autodesk.AutoCAD.ApplicationServices;
using App = Autodesk.AutoCAD.ApplicationServices.Core.Application;

namespace Cdcrd.Documentos;

// Decision of whether a document may be closed, kept apart from the AutoCAD calls so it reads as a table.
internal static class ClosePolicy
{
    // modified == null means the state could not be read: treated as modified.
    internal static string Refusal(int openDocuments, bool? modified, bool discardChanges, bool isActive, string commandInProgress, string commandOfThisModule)
    {
        if (openDocuments <= 1) return "No se cierra el unico documento abierto: la sesion quedaria sin dibujo y el puente sin canal de comandos";
        if (modified != false && !discardChanges)
            return "El documento tiene cambios sin guardar" + (modified == null ? " (estado no legible)" : "") + "; no se cierra. Para descartarlos repita con descartar_cambios=true";
        bool busy = !string.IsNullOrEmpty(commandInProgress) && !(isActive && string.Equals(commandInProgress, commandOfThisModule, StringComparison.OrdinalIgnoreCase));
        if (busy) return "El documento tiene un comando en curso (" + commandInProgress + "); no se cierra";
        return null;
    }
}

internal static class DocumentosService
{
    internal static Action<string> QaCheckpoint = null;
    private static readonly string[] Actions = { "listar", "abrir", "activar", "cerrar" };

    private static string Text(JsonObject p, string key, bool required = true)
    {
        var s = p[key]?.GetValue<string>();
        if (s == null && !required) return null;
        if (string.IsNullOrWhiteSpace(s) || s.Length > 400 || s.Any(char.IsControl)) throw new ArgumentException("Texto requerido: " + key);
        return s;
    }
    private static bool Flag(JsonObject p, string key) => p[key]?.GetValue<bool>() ?? false;

    // Unsaved changes of any open document, active or not: DBMOD and Saved through the document's COM object.
    private static (bool? Modified, int? Dbmod) Dirty(Document doc)
    {
        try
        {
            dynamic com = DocumentExtension.GetAcadDocument(doc);
            int dbmod = Convert.ToInt32(com.GetVariable("DBMOD"));
            bool saved = com.Saved;
            return (dbmod != 0 || !saved, dbmod);
        }
        catch (Exception) { return (null, null); }
    }

    private static object Row(Document doc)
    {
        var (modified, dbmod) = Dirty(doc);
        return new
        {
            ruta = doc.Name, nombre = Path.GetFileName(doc.Name), con_nombre = doc.IsNamedDrawing, solo_lectura = doc.IsReadOnly, activo = doc.IsActive,
            modificado = modified, dbmod, comando_en_curso = doc.CommandInProgress
        };
    }

    private static Document[] All(DocumentCollection docs) => docs.Cast<Document>().ToArray();

    private static object State(DocumentCollection docs) => new { activo = docs.MdiActiveDocument?.Name, abiertos = docs.Count, documentos = All(docs).Select(Row).ToArray() };

    // A saved drawing is addressed by its full path; an unnamed one (Drawing1.dwg) by its name.
    private static Document Find(DocumentCollection docs, string key, bool required)
    {
        bool rooted = Path.IsPathFullyQualified(key);
        string wanted = rooted ? Path.GetFullPath(key) : key;
        var found = All(docs).Where(d => d.IsNamedDrawing
            ? rooted && string.Equals(Path.GetFullPath(d.Name), wanted, StringComparison.OrdinalIgnoreCase)
            : !rooted && string.Equals(Path.GetFileName(d.Name), wanted, StringComparison.OrdinalIgnoreCase)).ToArray();
        if (found.Length > 1) throw new ArgumentException("Documento ambiguo: " + key);
        if (found.Length == 0 && required) throw new ArgumentException("Documento no abierto en esta sesion: " + key + " (ruta completa para dibujos guardados, nombre para los que no tienen archivo)");
        return found.FirstOrDefault();
    }

    private static void Activate(DocumentCollection docs, Document doc)
    {
        if (docs.MdiActiveDocument == doc) return;
        if (!docs.DocumentActivationEnabled) throw new InvalidOperationException("La activacion de documentos esta deshabilitada en la sesion");
        docs.MdiActiveDocument = doc;
        if (docs.MdiActiveDocument != doc) throw new InvalidOperationException("Civil no activo el documento " + doc.Name);
    }

    internal static object Execute(JsonObject p, string commandName, out bool changed)
    {
        changed = false;
        if (!DateTimeOffset.TryParse(Text(p, "vence_utc"), out var expires) || expires < DateTimeOffset.UtcNow || expires > DateTimeOffset.UtcNow.AddMinutes(5))
            throw new ArgumentException("Solicitud vencida o plazo invalido");
        if (p["pid"]?.GetValue<int>() != Environment.ProcessId) throw new ArgumentException("PID distinto al esperado");
        string action = Text(p, "accion");
        if (!Actions.Contains(action)) throw new ArgumentException("Accion desconocida");
        var docs = App.DocumentManager;
        if (action == "listar") return State(docs);
        if (Environment.GetEnvironmentVariable("CDCRD_C3D_PERMITIR_COMANDOS") != "1") throw new InvalidOperationException("Comandos deshabilitados en esta sesion");
        if (action == "cerrar" && Flag(p, "descartar_cambios") && Environment.GetEnvironmentVariable("CDCRD_C3D_SOLO_LECTURA") == "1")
            throw new InvalidOperationException("Sesion en solo lectura: no se descartan cambios de un documento");
        // The receipt must say the session changed even when a later step fails (opened in the wrong mode, activated but not closed).
        string before = Fingerprint(docs);
        try
        {
            object detail = action switch
            {
                "abrir" => Open(docs, p),
                "activar" => ActivateByKey(docs, Text(p, "ruta")),
                _ => Close(docs, p, commandName)
            };
            return new { accion = action, detalle = detail, estado = State(docs) };
        }
        finally { changed = Fingerprint(docs) != before; }
    }

    private static string Fingerprint(DocumentCollection docs) =>
        (docs.MdiActiveDocument?.Name ?? "") + "|" + string.Join("|", All(docs).Select(d => d.Name + (d.IsReadOnly ? "*" : "")).OrderBy(n => n, StringComparer.OrdinalIgnoreCase));

    private static object Open(DocumentCollection docs, JsonObject p)
    {
        string raw = Text(p, "ruta");
        if (!Path.IsPathFullyQualified(raw)) throw new ArgumentException("ruta debe ser absoluta");
        string path = Path.GetFullPath(raw);
        if (!string.Equals(Path.GetExtension(path), ".dwg", StringComparison.OrdinalIgnoreCase)) throw new ArgumentException("Solo se abren archivos .dwg");
        if (!File.Exists(path)) throw new FileNotFoundException("No existe el archivo", path);
        bool readOnly = Flag(p, "solo_lectura");
        var open = Find(docs, path, false);
        if (open != null)
        {
            if (open.IsReadOnly != readOnly)
                throw new InvalidOperationException("El documento ya esta abierto " + (open.IsReadOnly ? "en solo lectura" : "con escritura") + "; cierrelo antes de abrirlo en otro modo");
            Activate(docs, open);
            return new { ruta = open.Name, ya_abierto = true, solo_lectura = open.IsReadOnly };
        }
        if (!readOnly)
        {
            // A drawing held by another process would raise the "open read-only?" dialog: refuse instead.
            try { using var probe = new FileStream(path, FileMode.Open, FileAccess.ReadWrite, FileShare.None); }
            catch (Exception ex) when (ex is IOException || ex is UnauthorizedAccessException)
            { throw new InvalidOperationException("El archivo esta en uso o no admite escritura; abralo con solo_lectura=true. " + ex.Message); }
        }
        if (!docs.DocumentActivationEnabled) throw new InvalidOperationException("La activacion de documentos esta deshabilitada en la sesion");
        object proxyNotice = App.GetSystemVariable("PROXYNOTICE");
        Document doc;
        try
        {
            App.SetSystemVariable("PROXYNOTICE", 0);
            QaCheckpoint?.Invoke("before-open");
            doc = DocumentCollectionExtension.Open(docs, path, readOnly);
        }
        finally { App.SetSystemVariable("PROXYNOTICE", proxyNotice); }
        if (doc == null) throw new InvalidOperationException("Civil no abrio el documento");
        Activate(docs, doc);
        if (doc.IsReadOnly != readOnly) throw new InvalidOperationException("El documento quedo abierto " + (doc.IsReadOnly ? "en solo lectura" : "con escritura") + ", distinto de lo pedido; revise y cierrelo");
        return new { ruta = doc.Name, ya_abierto = false, solo_lectura = doc.IsReadOnly };
    }

    private static object ActivateByKey(DocumentCollection docs, string key)
    {
        var doc = Find(docs, key, true);
        Activate(docs, doc);
        return new { ruta = doc.Name };
    }

    private static object Close(DocumentCollection docs, JsonObject p, string commandName)
    {
        string key = Text(p, "ruta");
        var doc = Find(docs, key, true);
        bool discard = Flag(p, "descartar_cambios");
        var (modified, dbmod) = Dirty(doc);
        string refusal = ClosePolicy.Refusal(docs.Count, modified, discard, doc.IsActive, doc.CommandInProgress, commandName);
        if (refusal != null) throw new InvalidOperationException(refusal + (dbmod.HasValue ? " [DBMOD=" + dbmod + "]" : ""));
        string name = doc.Name; bool wasActive = doc.IsActive;
        if (wasActive)
        {
            // Leave the document before closing it: the next active one is the requested or the first other one.
            string nextKey = Text(p, "activar_despues", false);
            var next = nextKey != null ? Find(docs, nextKey, true) : All(docs).First(d => d != doc);
            if (next == doc) throw new ArgumentException("activar_despues debe ser otro documento");
            Activate(docs, next);
        }
        QaCheckpoint?.Invoke("before-close");
        DocumentExtension.CloseAndDiscard(doc);
        if (All(docs).Any(d => string.Equals(d.Name, name, StringComparison.OrdinalIgnoreCase))) throw new InvalidOperationException("El documento sigue abierto tras el cierre: " + name);
        return new { cerrado = name, estaba_activo = wasActive, tenia_cambios = modified, cambios_descartados = modified != false, guardado = false };
    }
}
