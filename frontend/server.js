/**
 * 零依赖静态文件服务器（仅用 Node 内置模块）
 * 启动：npm run dev   或   node server.js
 * 访问：http://localhost:8501
 *
 * 作用：为 index.html 提供正确的 MIME 类型和 HTTP 访问，
 *       避免 file:// 协议下浏览器限制 ES module / fetch 等 API。
 */
const http = require("http");
const fs = require("fs");
const path = require("path");

const PORT = Number(process.env.PORT) || 8501;
const ROOT = __dirname;

const MIME = {
  ".html": "text/html; charset=utf-8",
  ".js":   "text/javascript; charset=utf-8",
  ".css":  "text/css; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".svg":  "image/svg+xml",
  ".png":  "image/png",
  ".ico":  "image/x-icon",
};

const server = http.createServer((req, res) => {
  // URL 安全处理：去掉 query，默认 index.html
  let url = req.url.split("?")[0];
  if (url === "/") url = "/index.html";

  const filePath = path.join(ROOT, decodeURIComponent(url));

  // 防止路径穿越
  if (!filePath.startsWith(ROOT)) {
    res.writeHead(403);
    res.end("403 Forbidden");
    return;
  }

  fs.readFile(filePath, (err, data) => {
    if (err) {
      res.writeHead(404, { "Content-Type": "text/plain; charset=utf-8" });
      res.end("404 Not Found: " + url);
      return;
    }
    const ext = path.extname(filePath).toLowerCase();
    const mime = MIME[ext] || "application/octet-stream";
    res.writeHead(200, { "Content-Type": mime });
    res.end(data);
  });
});

server.on("error", (err) => {
  if (err.code === "EADDRINUSE") {
    console.error(`\n❌ 端口 ${PORT} 已被占用！`);
    console.error(`   请关闭占用端口的进程，或修改 server.js 中的 PORT 为其他端口（如 8502）。\n`);
    process.exit(1);
  }
  console.error("Server error:", err);
  process.exit(1);
});

server.listen(PORT, "0.0.0.0", () => {
  console.log("┌─────────────────────────────────────────────┐");
  console.log("│  DietAgent Frontend                          │");
  console.log("│                                              │");
  console.log(`│  Local:  http://localhost:${PORT}              │`);
  console.log("│                                              │");
  console.log("│  按 Ctrl+C 停止                               │");
  console.log("└─────────────────────────────────────────────┘");
});
