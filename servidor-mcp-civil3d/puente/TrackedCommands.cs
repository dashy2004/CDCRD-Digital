using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json.Nodes;
using System.Text.RegularExpressions;
using Autodesk.AutoCAD.ApplicationServices;
using Autodesk.AutoCAD.EditorInput;
using Autodesk.AutoCAD.Geometry;
using Autodesk.AutoCAD.Runtime;
using App=Autodesk.AutoCAD.ApplicationServices.Core.Application;
using Exception=System.Exception;

namespace Cdcrd.Civil3dBridge
{
    internal static class TrackedCommands
    {
        internal static readonly CommandReceipts Receipts=new CommandReceipts();
        private sealed record Pending(Document Document,string Name,string Command,object[] Arguments);
        // Only the CAD thread touches pending; socket readers use Receipts only.
        private static readonly Dictionary<string,Pending> pending=new Dictionary<string,Pending>();
        private static bool subscribed;
        internal static object Queue(Document document,JsonObject p)
        {
            string command=p["comando"]?.GetValue<string>() ?? "";
            string normalized=command.TrimStart('_','.','-').ToUpperInvariant();
            if(!Regex.IsMatch(command,@"^[_.-]*[A-Za-z][A-Za-z0-9_]*$") ||
                normalized.StartsWith("CDCRD",StringComparison.Ordinal) ||
                new[]{"OPEN","CLOSE","CLOSEALL","QUIT","EXIT","NEW","QNEW","NETLOAD","APPLOAD","SCRIPT"}.Contains(normalized))
                throw new ArgumentException("Se requiere un comando de dibujo, sin LISP ni cambios de documento/plugin.");
            if(!string.IsNullOrEmpty(document.CommandInProgress))throw new InvalidOperationException("El documento tiene un comando activo.");
            var args=new List<object>{command};
            var supplied=p["argumentos"] as JsonArray ?? new JsonArray();
            if(supplied.Count>128)throw new ArgumentException("Maximo 128 argumentos.");
            foreach(var value in supplied)
            {
                if(value is JsonArray point && (point.Count==2||point.Count==3))
                {
                    var xyz=point.Select(v=>v.GetValue<double>()).ToArray();
                    if(xyz.Any(x=>!double.IsFinite(x)))throw new ArgumentException("Punto no finito.");
                    args.Add(new Point3d(xyz[0],xyz[1],xyz.Length==3?xyz[2]:0));
                }
                else if(value is JsonValue scalar && scalar.TryGetValue<string>(out var text))
                {
                    if(text.Length>4096||text.Any(char.IsControl))throw new ArgumentException("Argumento con controles o demasiado largo.");
                    args.Add(text);
                }
                else if(value is JsonValue number && number.TryGetValue<double>(out var real)&&double.IsFinite(real))args.Add(real);
                else throw new ArgumentException("Argumentos admitidos: texto, numero finito o punto [x,y,z].");
            }
            if(!subscribed){App.DocumentManager.DocumentToBeDestroyed+=Closing;subscribed=true;}
            foreach(var old in pending.Keys.Where(id=>!Receipts.Active(id)).ToArray())pending.Remove(old);
            string id=Receipts.Add(document.Name,command);
            pending[id]=new Pending(document,document.Name,normalized,args.ToArray());
            try{document.SendStringToExecute("CDCRDEXEC "+id+"\n",true,false,false);}
            catch(Exception e){pending.Remove(id);Receipts.Finish(id,"fallido",e.Message);throw;}
            return Receipts.Get(id);
        }
        private static void Closing(object sender,DocumentCollectionEventArgs e)
        {
            foreach(var pair in pending.Where(x=>ReferenceEquals(x.Value.Document,e.Document)).ToArray())
            {Receipts.Finish(pair.Key,"desconocido","Documento cerrado antes de recibir finalizacion.");pending.Remove(pair.Key);}
        }
        internal static void Shutdown()
        {
            foreach(var id in pending.Keys)Receipts.Finish(id,"desconocido","Puente detenido; comprobar dibujo antes de reintentar.");
            pending.Clear();
            if(subscribed){App.DocumentManager.DocumentToBeDestroyed-=Closing;subscribed=false;}
        }
        internal static void Execute()
        {
            var doc=App.DocumentManager.MdiActiveDocument;
            var answer=doc.Editor.GetString(new PromptStringOptions("Ticket: "){AllowSpaces=false});
            if(answer.Status!=PromptStatus.OK)return;
            string id=answer.StringResult;
            if(!pending.TryGetValue(id,out var item))return;
            if(!ReferenceEquals(item.Document,doc) || !string.Equals(item.Name,doc.Name,StringComparison.OrdinalIgnoreCase))
            {Receipts.Finish(id,"fallido","El ticket pertenece a otro documento.");pending.Remove(id);return;}
            if(!Receipts.Start(id)){pending.Remove(id);return;}
            bool ended=false,failed=false,cancelled=false;
            CommandEventHandler onStart=(s,e)=>Receipts.Event(id,"inicio:"+e.GlobalCommandName);
            CommandEventHandler onEnd=(s,e)=>{if(e.GlobalCommandName.TrimStart('_','.','-').Equals(item.Command,StringComparison.OrdinalIgnoreCase))ended=true;Receipts.Event(id,"fin:"+e.GlobalCommandName);};
            CommandEventHandler onFail=(s,e)=>{failed=true;Receipts.Event(id,"fallo:"+e.GlobalCommandName);};
            CommandEventHandler onCancel=(s,e)=>{cancelled=true;Receipts.Event(id,"cancelacion:"+e.GlobalCommandName);};
            doc.CommandWillStart+=onStart;doc.CommandEnded+=onEnd;
            doc.CommandFailed+=onFail;doc.CommandCancelled+=onCancel;
            try
            {
                doc.Editor.Command(item.Arguments);
                Receipts.Finish(id,cancelled?"cancelado":failed?"fallido":ended?"terminado":"desconocido");
            }
            catch(Exception e){Receipts.Finish(id,cancelled?"cancelado":"fallido",e.Message);}
            finally
            {
                doc.CommandWillStart-=onStart;doc.CommandEnded-=onEnd;
                doc.CommandFailed-=onFail;doc.CommandCancelled-=onCancel;
                pending.Remove(id);
            }
        }
    }
    public class TrackedCommandEntry
    {
        [CommandMethod("CDCRDEXEC",CommandFlags.Modal)]
        public void Execute()=>TrackedCommands.Execute();
    }
    internal static partial class Handlers
    {
        private static object CmdTracked(JsonObject p,string method)
        {
            if(!BridgeServer.AllowCommands)throw new BridgeException(Rpc.ErrForbidden,"Comandos deshabilitados.");
            ExigirEscritura(method,p);
            return TrackedCommands.Queue(Doc(),p);
        }
    }
}
