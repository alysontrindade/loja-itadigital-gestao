import argparse
import os
import threading
import webbrowser

from waitress import serve

from app import create_app
from app.services.backup_service import BackupScheduler, run_daily_backup_if_needed


def main() -> None:
    parser = argparse.ArgumentParser(description="Servidor local Loja Itamarandiba")
    parser.add_argument(
        "--no-browser",
        action="store_true",
        help="Não abrir o navegador automaticamente ao iniciar",
    )
    args = parser.parse_args()

    app = create_app()
    settings = app.config["LOJA_SETTINGS"]

    run_daily_backup_if_needed(settings)
    scheduler = BackupScheduler(settings)
    scheduler.start()

    url = f"http://{settings.host}:{settings.port}"
    print(f"======================================================")
    print(f" Loja Itamarandiba — Sistema de Gestão Local")
    print(f" Endereço: {url}")
    print(f" Banco ativo: {settings.db_path}")
    print(f" Backups ZIP: {settings.backup_dir}")
    print(f" Pressione Ctrl+C para encerrar com segurança.")
    print(f"======================================================")

    abrir_navegador = not args.no_browser and os.environ.get("LOJA_NO_BROWSER") != "1"
    if abrir_navegador:
        threading.Timer(1.0, webbrowser.open, args=[url]).start()

    try:
        serve(app, host=settings.host, port=settings.port, threads=6)
    except KeyboardInterrupt:
        print("\nEncerrando servidor com segurança...")
    finally:
        scheduler.stop()
        app.extensions["engine"].dispose()


if __name__ == "__main__":
    main()
