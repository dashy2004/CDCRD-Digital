using System;
namespace Autodesk.AutoCAD.Runtime {
 public interface IExtensionApplication { void Initialize(); void Terminate(); }
 public enum CommandFlags { Session }
 public class CommandMethodAttribute : Attribute { public CommandMethodAttribute(string name, CommandFlags flags) {} }
}
namespace Autodesk.AutoCAD.ApplicationServices {
 public class Editor { public void WriteMessage(string text) {} }
 public class Document { public Editor Editor { get; } = new Editor(); }
 public class DocumentCollection { public Document MdiActiveDocument { get; } = new Document(); }
}
namespace Autodesk.AutoCAD.ApplicationServices.Core {
 public static class Application {
  public static event EventHandler Idle;
  public static Autodesk.AutoCAD.ApplicationServices.DocumentCollection DocumentManager { get; } = new();
  public static void Pump() => Idle?.Invoke(null, EventArgs.Empty);
 }
}
namespace Cdcrd.Civil3dBridge {
 internal static class Handlers {
  public const string Version = "fixture";
  public static void CapturarHandlePrincipal() {}
  public static object DiagDialogosSinHilo() => new { hilo = "socket" };
  public static object Dispatch(string name, System.Text.Json.Nodes.JsonObject p) => name;
 }
}
