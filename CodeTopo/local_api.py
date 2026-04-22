from __future__ import annotations

import argparse
import json
import sys
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from mimetypes import guess_type
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "core"))

from analysis_service import UploadedFile, analyze_uploaded_files
from llm_providers import get_provider_catalog


def _json_response(handler: BaseHTTPRequestHandler, status: int, payload: dict) -> None:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
    handler.send_header("Access-Control-Allow-Headers", "Content-Type")
    handler.send_header("Cache-Control", "no-store")
    handler.end_headers()
    handler.wfile.write(body)


def _file_response(handler: BaseHTTPRequestHandler, file_path: Path) -> None:
    body = file_path.read_bytes()
    content_type = guess_type(str(file_path))[0] or "application/octet-stream"
    handler.send_response(HTTPStatus.OK)
    handler.send_header("Content-Type", f"{content_type}; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Cache-Control", "no-store, no-cache, must-revalidate")
    handler.send_header("Pragma", "no-cache")
    handler.send_header("Expires", "0")
    handler.end_headers()
    handler.wfile.write(body)


class LocalAPIHandler(BaseHTTPRequestHandler):
    server_version = "AIDocGeneratorLocalAPI/1.0"
    frontend_root = Path(__file__).parent / "frontend"

    def do_GET(self) -> None:
        if self.path in {"/", "/index.html", "/frontend/index.html"}:
            _file_response(self, self.frontend_root / "index.html")
            return
        if self.path == "/providers":
            _json_response(self, HTTPStatus.OK, {"ok": True, "providers": get_provider_catalog()})
            return
        _json_response(self, HTTPStatus.NOT_FOUND, {"ok": False, "error": "Not found"})

    def do_OPTIONS(self) -> None:
        self.send_response(HTTPStatus.NO_CONTENT)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()

    def do_POST(self) -> None:
        if self.path != "/analyze":
            _json_response(self, HTTPStatus.NOT_FOUND, {"ok": False, "error": "Not found"})
            return

        length = int(self.headers.get("Content-Length", "0"))
        raw_body = self.rfile.read(length)
        try:
            payload = json.loads(raw_body.decode("utf-8"))
        except json.JSONDecodeError:
            _json_response(self, HTTPStatus.BAD_REQUEST, {"ok": False, "error": "Invalid JSON body"})
            return

        try:
            files = [
                UploadedFile(path=item["path"], content=item["content"])
                for item in payload.get("files", [])
            ]
            result = analyze_uploaded_files(
                files=files,
                target_file=payload.get("targetFile", ""),
                api_key=payload.get("apiKey", ""),
                provider=payload.get("provider", "deepseek"),
                model=payload.get("model"),
                base_url=payload.get("baseUrl"),
            )
        except KeyError as exc:
            _json_response(
                self,
                HTTPStatus.BAD_REQUEST,
                {"ok": False, "error": f"Missing required field in files payload: {exc}"},
            )
            return
        except ValueError as exc:
            _json_response(self, HTTPStatus.BAD_REQUEST, {"ok": False, "error": str(exc)})
            return
        except RuntimeError as exc:
            _json_response(self, HTTPStatus.BAD_GATEWAY, {"ok": False, "error": str(exc)})
            return
        except Exception as exc:
            _json_response(
                self,
                HTTPStatus.INTERNAL_SERVER_ERROR,
                {"ok": False, "error": f"Unexpected server error: {exc}"},
            )
            return

        _json_response(
            self,
            HTTPStatus.OK,
            {
                "ok": True,
                "analysisMarkdown": result.analysis_markdown,
                "mermaidGraph": result.mermaid_graph,
                "numberedCode": result.numbered_code,
                "detectedFiles": result.detected_files,
                "resolvedTargetFile": result.resolved_target_file,
            },
        )

    def log_message(self, format: str, *args) -> None:
        return


def main() -> None:
    parser = argparse.ArgumentParser(description="Local API server for AI Doc Generator")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()

    server = ThreadingHTTPServer((args.host, args.port), LocalAPIHandler)
    print(f"Local API running at http://{args.host}:{args.port}")
    print(f"Open http://{args.host}:{args.port}/ in your browser.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping local API server.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
