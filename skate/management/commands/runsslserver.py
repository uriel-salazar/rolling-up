"""Development server that speaks HTTPS.

Django's ``runserver`` command only speaks plain HTTP, and the ``--ssl-*
options it had in old releases are gone. This command runs the same
development server (auto-reloader, static files, debug pages) wrapped in a
TLS socket, so tools that require a secure origin (browser APIs, mobile
clients, service workers) can talk to it over ``https://``.

Usage::

    python manage.py runsslserver
    python manage.py runsslserver 0.0.0.0:8443
"""

import os
import socket
import socketserver
import ssl
import subprocess
from pathlib import Path

from django.contrib.staticfiles.management.commands.runserver import (
    Command as StaticRunserverCommand,
)
from django.core.servers.basehttp import (
    ThreadedWSGIServer,
    WSGIServer,
    WSGIRequestHandler,
    get_internal_wsgi_application,
)
from django.db import connections
from django.utils import autoreload

DEFAULT_CERT_DIR = Path(__file__).resolve().parent.parent.parent / "certs"
DEFAULT_CERT = DEFAULT_CERT_DIR / "dev.crt"
DEFAULT_KEY = DEFAULT_CERT_DIR / "dev.key"


class SSLWSGIServer(WSGIServer):
    """WSGI server that terminates TLS on every accepted connection."""

    def __init__(self, *args, ssl_context=None, **kwargs):
        self.ssl_context = ssl_context
        super().__init__(*args, **kwargs)

    def get_request(self):
        sock, addr = self.socket.accept()
        try:
            sock = self.ssl_context.wrap_socket(sock, server_side=True)
        except ssl.SSLError as error:
            raise OSError(f"TLS handshake failed: {error}") from error
        return sock, addr


class SSLWSGIRequestHandler(WSGIRequestHandler):
    """Request handler that reports the request as coming over HTTPS."""

    def get_environ(self):
        env = super().get_environ()
        env["HTTPS"] = "on"
        env["wsgi.url_scheme"] = "https"
        return env


def ensure_certificate(cert_path, key_path):
    """Generate a self-signed certificate if one does not exist yet."""
    cert_path = Path(cert_path)
    key_path = Path(key_path)
    if cert_path.exists() and key_path.exists():
        return

    cert_path.parent.mkdir(parents=True, exist_ok=True)
    host = socket.gethostbyname(socket.gethostname())
    subprocess.run(
        [
            "openssl",
            "req",
            "-x509",
            "-newkey",
            "rsa:2048",
            "-nodes",
            "-keyout",
            str(key_path),
            "-out",
            str(cert_path),
            "-days",
            "365",
            "-subj",
            "/CN=localhost",
            "-addext",
            f"subjectAltName=DNS:localhost,DNS:*.localhost,IP:127.0.0.1,IP:{host}",
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    key_path.chmod(0o600)


def build_ssl_context(cert_path, key_path):
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(certfile=str(cert_path), keyfile=str(key_path))
    return context


class Command(StaticRunserverCommand):
    help = "Starts the development server over HTTPS with a self-signed certificate."

    protocol = "https"

    def add_arguments(self, parser):
        super().add_arguments(parser)
        parser.add_argument(
            "--certfile",
            default=os.environ.get("SSL_CERTFILE", str(DEFAULT_CERT)),
            help="Path to the SSL certificate.",
        )
        parser.add_argument(
            "--keyfile",
            default=os.environ.get("SSL_KEYFILE", str(DEFAULT_KEY)),
            help="Path to the SSL key.",
        )

    def inner_run(self, *args, **options):
        autoreload.raise_last_exception()

        threading = options["use_threading"]
        shutdown_message = options.get("shutdown_message", "")

        if not options["skip_checks"]:
            self.stdout.write("Performing system checks...\n\n")
            check_kwargs = super().get_check_kwargs(options)
            check_kwargs["display_num_errors"] = True
            self.check(**check_kwargs)
        self.check_migrations()
        for conn in connections.all(initialized_only=True):
            conn.close()

        ensure_certificate(options["certfile"], options["keyfile"])
        ssl_context = build_ssl_context(options["certfile"], options["keyfile"])

        try:
            handler = self.get_handler(*args, **options)
            self.run_server(
                self.addr,
                int(self.port),
                handler,
                ssl_context=ssl_context,
                ipv6=self.use_ipv6,
                threading=threading,
                on_bind=self.on_bind,
            )
        except OSError as error:
            self.stderr.write(f"Error: {error}")
            os._exit(1)
        except KeyboardInterrupt:
            if shutdown_message:
                self.stdout.write(shutdown_message)
            os._exit(0)

    def run_server(
        self, addr, port, handler, ssl_context, ipv6=False, threading=True, on_bind=None
    ):
        server_address = (addr, port)
        if threading:
            server_cls = type(
                "WSGIServer", (socketserver.ThreadingMixIn, SSLWSGIServer), {}
            )
        else:
            server_cls = SSLWSGIServer

        httpd = server_cls(
            server_address,
            SSLWSGIRequestHandler,
            ipv6=ipv6,
            ssl_context=ssl_context,
        )
        if on_bind is not None:
            on_bind(getattr(httpd, "server_port", port))
        if threading:
            httpd.daemon_threads = True
        httpd.set_app(handler)
        httpd.serve_forever()

    def run(self, **options):
        if options["use_reloader"]:
            autoreload.run_with_reloader(self.inner_run, **options)
        else:
            self.inner_run(None, **options)

    def get_handler(self, *args, **options):
        return super().get_handler(*args, **options)
