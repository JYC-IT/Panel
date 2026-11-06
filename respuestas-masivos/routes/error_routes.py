"""Manejadores de errores globales para una experiencia de usuario amigable."""
from flask import render_template


def register_error_handlers(app):
    @app.errorhandler(404)
    def page_not_found(e):
        return (
            """<!doctype html>
            <html lang="es">
            <head><meta charset="utf-8"><title>404 - No Encontrado</title>
            <style>body{font-family:sans-serif;text-align:center;padding:50px;background:#0f172a;color:#f8fafc;}a{color:#38bdf8;text-decoration:none;}</style>
            </head>
            <body>
            <h1>404 | Página no encontrada</h1>
            <p>La página o recurso que buscas no existe o fue movido.</p>
            <p><a href="/">← Volver al Panel Principal</a></p>
            </body></html>""",
            404,
        )

    @app.errorhandler(500)
    def internal_server_error(e):
        return (
            """<!doctype html>
            <html lang="es">
            <head><meta charset="utf-8"><title>500 - Error Interno</title>
            <style>body{font-family:sans-serif;text-align:center;padding:50px;background:#0f172a;color:#f8fafc;}a{color:#38bdf8;text-decoration:none;}</style>
            </head>
            <body>
            <h1>500 | Error Interno del Servidor</h1>
            <p>Ocurrió un error inesperado al procesar la solicitud.</p>
            <p><a href="/">← Volver al Panel Principal</a></p>
            </body></html>""",
            500,
        )

