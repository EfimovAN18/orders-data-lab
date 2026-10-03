import argparse
import logging
import time

from orders_lab.config import get_settings
from orders_lab.db import make_engine
from orders_lab.models import Base
from orders_lab.pipeline.run import run_pipeline
from orders_lab.seed import seed_demo


def positive_int(value: str) -> int:
    number = int(value)
    if number <= 0:
        raise argparse.ArgumentTypeError("Число должно быть больше нуля")
    return number


def main() -> None:
    parser = argparse.ArgumentParser(description="Orders Data Lab — учебный проект для GitHub")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("init-db", help="Создать таблицы приложения")
    seed = subparsers.add_parser("seed", help="Добавить синтетические данные в пустую БД")
    seed.add_argument("--orders", type=positive_int, default=600)
    pipeline = subparsers.add_parser("pipeline", help="Проверить и загрузить полный снимок")
    pipeline.add_argument(
        "--interval", type=positive_int, help="Повторять через N секунд; Ctrl+C — выход"
    )
    subparsers.add_parser("report", help="Сформировать HTML, Markdown, JSON и CSV")
    subparsers.add_parser("demo", help="Создать демоданные, выполнить ETL и построить отчёт")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    settings = get_settings()
    engine = make_engine(settings.database_url)
    try:
        if args.command in {"init-db", "seed", "demo"}:
            Base.metadata.create_all(engine)
        if args.command == "init-db":
            print("Таблицы готовы.")
        if args.command in {"seed", "demo"}:
            created = seed_demo(engine, getattr(args, "orders", 600))
            print(
                "Демоданные созданы."
                if created
                else "База уже содержит данные; заполнение пропущено."
            )
        if args.command == "pipeline":
            while True:
                run_pipeline(engine, settings.warehouse, settings.raw_dir)
                if args.interval is None:
                    break
                time.sleep(args.interval)
        if args.command == "demo":
            run_pipeline(engine, settings.warehouse, settings.raw_dir)
        if args.command in {"report", "demo"}:
            from orders_lab.analytics.report import build_report

            metrics = build_report(settings.warehouse, settings.report_dir)
            print(f"Отчёт: {(settings.report_dir / 'index.html').resolve()}")
            print(
                f"Оплаченных заказов: {metrics['paid_orders']}; "
                f"выручка: {metrics['revenue_rub']} RUB"
            )
    except KeyboardInterrupt:
        print("\nРабота остановлена.")
    except Exception as exc:
        # Не выводим строки подключения и SQL с параметрами из исключений драйвера.
        logging.error("%s: проверьте конфигурацию и предыдущие шаги запуска.", type(exc).__name__)
        if isinstance(exc, ValueError):
            logging.error("%s", exc)
        raise SystemExit(1) from None
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
