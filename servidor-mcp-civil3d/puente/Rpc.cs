// CDCRD-Digital - puente MCP para Civil 3D 2027
// Capa JSON-RPC y control de aprobaciones. No depende de la API de Civil 3D.
using System;
using System.Collections.Generic;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;

namespace Cdcrd.Civil3dBridge
{
    internal static class Rpc
    {
        public static readonly JsonSerializerOptions Opts = new JsonSerializerOptions { WriteIndented = false };

        public static string Ok(JsonNode id, object result)
        {
            var o = new JsonObject
            {
                ["jsonrpc"] = "2.0",
                ["id"] = id == null ? null : id.DeepClone(),
                ["result"] = JsonSerializer.SerializeToNode(result, Opts)
            };
            return o.ToJsonString();
        }

        public static string Err(JsonNode id, int code, string message, string data = null)
        {
            var e = new JsonObject { ["code"] = code, ["message"] = message };
            if (data != null) e["data"] = data;
            var o = new JsonObject
            {
                ["jsonrpc"] = "2.0",
                ["id"] = id == null ? null : id.DeepClone(),
                ["error"] = e
            };
            return o.ToJsonString();
        }

        // Codigos propios: -32000 ocupado, -32001 sin documento, -32002 aprobacion, -32003 no permitido
        public const int ErrBusy = -32000;
        public const int ErrNoDoc = -32001;
        public const int ErrApproval = -32002;
        public const int ErrForbidden = -32003;
        public const int ErrInternal = -32603;
        public const int ErrMethod = -32601;
        public const int ErrParams = -32602;
    }

    // Toda operacion que escribe en el dibujo exige un token de un solo uso ligado
    // al hash exacto de metodo + parametros. Evita que una herramienta de escritura
    // se ejecute con parametros distintos a los que se mostraron al operador.
    internal static class Approvals
    {
        private static readonly Dictionary<string, string> Tokens = new Dictionary<string, string>();
        private static readonly object Gate = new object();

        public static string Hash(string method, JsonNode prms)
        {
            JsonNode copy = prms == null ? new JsonObject() : prms.DeepClone();
            if (copy is JsonObject jo) jo.Remove("token");
            string canon = method + "|" + Canonical(copy);
            using (var sha = SHA256.Create())
                return Convert.ToHexString(sha.ComputeHash(Encoding.UTF8.GetBytes(canon)));
        }

        private static string Canonical(JsonNode n)
        {
            if (n == null) return "null";
            if (n is JsonObject o)
            {
                var keys = new List<string>();
                foreach (var kv in o) keys.Add(kv.Key);
                keys.Sort(StringComparer.Ordinal);
                var sb = new StringBuilder("{");
                for (int i = 0; i < keys.Count; i++)
                {
                    if (i > 0) sb.Append(',');
                    sb.Append(JsonSerializer.Serialize(keys[i])).Append(':').Append(Canonical(o[keys[i]]));
                }
                return sb.Append('}').ToString();
            }
            if (n is JsonArray a)
            {
                var sb = new StringBuilder("[");
                for (int i = 0; i < a.Count; i++)
                {
                    if (i > 0) sb.Append(',');
                    sb.Append(Canonical(a[i]));
                }
                return sb.Append(']').ToString();
            }
            return n.ToJsonString();
        }

        public static string Issue(string hash)
        {
            string token = Guid.NewGuid().ToString("N");
            lock (Gate)
            {
                if (Tokens.Count > 64) Tokens.Clear();
                Tokens[token] = hash;
            }
            return token;
        }

        public static bool Consume(string token, string hash)
        {
            if (string.IsNullOrEmpty(token)) return false;
            lock (Gate)
            {
                string stored;
                if (!Tokens.TryGetValue(token, out stored)) return false;
                Tokens.Remove(token);
                return stored == hash;
            }
        }
    }
}
