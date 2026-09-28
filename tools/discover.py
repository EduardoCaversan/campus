"""Inspect public authentication structure; never emit input values or response bodies."""

import json
from urllib.parse import urlsplit

import httpx
from bs4 import BeautifulSoup

for url in (
    "https://sistemas2.utfpr.edu.br/dpls/sistema/aluno01/mpmenu.inicio",
    "https://moodle.utfpr.edu.br/login/index.php",
):
    try:
        response = httpx.get(url, follow_redirects=True, timeout=25)
        soup = BeautifulSoup(response.text, "html.parser")
        print(
            json.dumps(
                {
                    "host": urlsplit(response.url.__str__()).hostname,
                    "path": urlsplit(str(response.url)).path,
                    "status": response.status_code,
                    "forms": [
                        {
                            "method": f.get("method"),
                            "action_path": urlsplit(f.get("action", "")).path,
                            "inputs": [
                                {"name": i.get("name"), "type": i.get("type"), "id": i.get("id")}
                                for i in f.select("input")
                            ],
                        }
                        for f in soup.select("form")
                    ],
                    "scripts": [
                        urlsplit(s.get("src", "")).path for s in soup.select("script[src]")
                    ],
                },
                ensure_ascii=True,
            )
        )
    except Exception as exc:
        print(
            json.dumps(
                {
                    "host": urlsplit(url).hostname,
                    "state": "FAILED",
                    "error_type": type(exc).__name__,
                }
            )
        )
