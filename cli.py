"""Operaciones de la edición Qt sin abrir una ventana."""
import argparse
import json
import os
from dataclasses import asdict


def main(argv=None):
    parser = argparse.ArgumentParser(description="SAIRC Qt / reconocimiento remoto")
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("extract", "retry"):
        command = commands.add_parser(name)
        command.add_argument("input", help="Carpeta de PDF originales")
        command.add_argument("workspace", help="Raíz de resultados de los cuatro hitos")
        command.add_argument("--provider", choices=["gemini", "mistral"], default="gemini")
        command.add_argument("--mode", choices=["vision", "ocr"], default="vision")
        command.add_argument("--model", required=True)
        command.add_argument("--authorize-external-processing", action="store_true", help="Autoriza envío remoto y costo para este lote")
        command.add_argument("--threads", type=int, default=2)
        command.add_argument("--max-pages", type=int, default=100)
        command.add_argument("--max-vision-pages", type=int, default=20)
        command.add_argument("--max-mb", type=int, default=50)
    consolidate = commands.add_parser("consolidate")
    consolidate.add_argument("cache", help="Hito 1 o carpeta histórica de respuestas IA")
    consolidate.add_argument("workspace")
    compare = commands.add_parser("compare")
    compare.add_argument("excel")
    compare.add_argument("reference")
    compare.add_argument("workspace")
    compare.add_argument("--pdf-root", required=True)
    args = parser.parse_args(argv)
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    from core.ai import AIConfig
    from core.comparador import compare_excels
    from core.processor import process_folder, reprocess_ai_cache, reprocess_temporary_errors
    from core.workspace import get_hito_paths

    app = QApplication.instance() or QApplication([])
    paths = get_hito_paths(args.workspace)
    try:
        if args.command in {"extract", "retry"}:
            key = os.environ.get(f"LAB_EXTRACTOR_{args.provider.upper()}_API_KEY", "") or os.environ.get("LAB_EXTRACTOR_API_KEY", "")
            config = AIConfig(provider=args.provider, model=args.model, api_key=key, reader_mode=args.mode, allow_external_processing=args.authorize_external_processing, max_pdf_pages=args.max_pages, max_vision_pages=args.max_vision_pages, max_pdf_mb=args.max_mb)
            progress = lambda payload: print(payload.get("message", ""), flush=True)
            if args.command == "extract":
                result = process_folder(args.input, config, progress_cb=progress, threads=args.threads, output_dir=str(paths.hito1))
            else:
                result = reprocess_temporary_errors(str(paths.hito1), args.input, config, progress_cb=progress, threads=args.threads)
            result = asdict(result)
        elif args.command == "consolidate":
            result = asdict(reprocess_ai_cache(args.cache, str(paths.hito2)))
        else:
            result = compare_excels(args.excel, args.reference, str(paths.hito4 / "reporte_priorizado_discrepancias_hito4.xlsx"), pdf_root=args.pdf_root, review_pdf_operation="copy")
        print(json.dumps(result, ensure_ascii=False, indent=2))
        app.processEvents()
        return 0
    except Exception as exc:
        message = str(exc)
        for key, value in os.environ.items():
            if value and key.startswith("LAB_EXTRACTOR_") and (key.endswith("API_KEY") or key.endswith("PASSWORD")):
                message = message.replace(value, "[oculto]")
        print(f"ERROR: {message}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
